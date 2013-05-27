#!/usr/bin/env python
import collections
import threading
import time

class WTF(Exception):
    def __init__(self):
        super(WTF, self).__init__("WTF")


class WishGroup(object):
    def __init__(self):
        self.fulfilled_by = None
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)

    @property
    def fulfilled(self):
        return self.fulfilled_by is not None


class ProduceWish(object):
    def __init__(self, group, chan, value):
        self.group = group
        self.chan = chan
        self.value = value

    @property
    def fulfilled(self):
        return self.group.fulfilled

    def fulfill(self):
        """Must hold group.lock"""
        self.group.fulfilled_by = self
        self.group.cond.notify()
        return self.value


class ConsumeWish(object):
    def __init__(self, group, chan):
        self.group = group
        self.chan = chan

    @property
    def fulfilled(self):
        return self.group.fulfilled

    def fulfill(self, value):
        """Must hold group.lock"""
        self.value = value
        self.group.fulfilled_by = self
        self.group.cond.notify()


class WishFulfilled(Exception): pass
class ProduceWishFulfilled(WishFulfilled): pass
class ConsumeWishFulfilled(WishFulfilled): pass


def _fulfill_wish_pair(produce_wish, consume_wish):
    if produce_wish.group == consume_wish.group:
        raise WTF()
        # Always lock producer, then consumer
    with produce_wish.group.lock, consume_wish.group.lock:
        if produce_wish.fulfilled:
            raise ProduceWishFulfilled()
        if consume_wish.fulfilled:
            raise ConsumeWishFulfilled()

        consume_wish.fulfill(produce_wish.fulfill())


class Chan(object):
    def __init__(self):
        self._lock = threading.Lock()

        # TODO: Lists are inefficient lifo queues
        self._waiting_producers = []
        self._waiting_consumers = []

    def _submit_consume_wish(self, wish):
        with self._lock:
            while self._waiting_producers:
                try:
                    produce_wish = self._waiting_producers.pop(0)
                    _fulfill_wish_pair(produce_wish, wish)
                    return True  # Fulfilled successfully
                except ProduceWishFulfilled:
                    # This produce wish was already fulfilled.  Skip to next
                    pass
                except ConsumeWishFulfilled:
                    print "WEIRD: ConsumeWishFulfilled"
                    return True

            # Wish wasn't fulfilled.  Put it in the waiting queue
            self._waiting_consumers.append(wish)
            return False

    def _submit_produce_wish(self, wish):
        with self._lock:
            while self._waiting_consumers:
                try:
                    consume_wish = self._waiting_consumers.pop(0)
                    _fulfill_wish_pair(wish, consume_wish)
                    return True  # Fulfilled successfully
                except ConsumeWishFulfilled:
                    pass
                except ProduceWishFulfilled:
                    print "WEIRD: ProduceWishFulfilled"
                    return True

            # Wish wasn't fulfilled.  Put it in the waiting queue
            self._waiting_producers.append(wish)
            return False


    def get(self):
        group = WishGroup()
        wish = ConsumeWish(group, self)
        self._submit_consume_wish(wish)

        with group.lock:
            while not wish.fulfilled:
                group.cond.wait()

            return wish.value

    def put(self, value):
        group = WishGroup()
        wish = ProduceWish(group, self, value)
        self._submit_produce_wish(wish)

        with group.lock:
            while not wish.fulfilled:
                group.cond.wait()


def chanselect(consumers, producers):
    class Fulfilled(Exception): pass

    group = WishGroup()

    try:
        # Submits the consumer wishes
        for chan in consumers:
            wish = ConsumeWish(group, chan)
            if chan._submit_consume_wish(wish):
                raise Fulfilled()

        # Submits the producer wishes
        for chan, value in producers:
            wish = ProduceWish(group, chan, value)
            if chan._submit_produce_wish(wish):
                raise Fulfilled()

    except Fulfilled:
        pass

    with group.lock:
        while not group.fulfilled:
            group.cond.wait()

        # At this point, a wish has been fulfilled
        wish = group.fulfilled_by
        if isinstance(wish, ConsumeWish):
            return wish.chan, wish.value
        else:
            return wish.chan, None


def go(fn, *args, **kwargs):
    th = threading.Thread(
        target=fn,
        args=args,
        kwargs=kwargs)
    th.daemon = True
    th.start()
    return th

def printer(phrase, delay):
    while True:
        print phrase
        time.sleep(delay)

def say(chan, phrase, delay=0.5):
    n = 0
    while True:
        tosay = "%s(%d)" % (phrase, n)
        print "Saying", tosay
        chan.put(tosay)
        n += 1
        time.sleep(delay)

def listen(chan, prefix="Heard: "):
    while True:
        time.sleep(1)
        phrase = chan.get()
        print "%s%s" % (prefix, phrase)

def example_basic():
    c = Chan()
    go(say, c, "Hello")
    go(listen, c)
    go(say, c, "Woah")
    go(listen, c, "Also heard: ")

    time.sleep(5)


def athlete(chan, phrase, delay=1.0):
    time.sleep(delay)
    chan.put(phrase)

def printfirst(a, b):
    chan, value = chanselect([a, b], [])
    if chan == a:
        print "From A:", value
    elif chan == b:
        print "From B:", value
    else:
        raise WTF()


def example_select():
    a = Chan()
    b = Chan()
    go(printfirst, a, b)
    go(athlete, a, "AA", delay=0.8)
    go(athlete, b, "BB", delay=0.7)
    time.sleep(2)

#example_basic()
example_select()

'''
Goal

a = Chan()
b = Chan()
c = Chan()
d = Chan()

c.put(4)
c.get()
c.close()

getready, putready, closed = \
    chanselect(get=[a, b], put=[(c, 'cat'), (d, 'dog')], closed=[e, f])

getready: [], [(a, 'hi')], or [(a, 'hi'), (b, 'bye')]

putready: [], [c], [c, d]

closed: [], [e], [e, f]

'''
