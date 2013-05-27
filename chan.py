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
        """
        Submits a ConsumeWish for processing by the channel.

        Returns True if the wish was fulfilled while the function exceuted.
        """
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
                    return True

            # Wish wasn't fulfilled.  Put it in the waiting queue
            self._waiting_consumers.append(wish)
            return False

    def _submit_produce_wish(self, wish):
        """
        Submits a ProduceWish for processing by the channel.

        Returns True if the wish was fulfilled while the function exceuted.
        """
        with self._lock:
            while self._waiting_consumers:
                try:
                    consume_wish = self._waiting_consumers.pop(0)
                    _fulfill_wish_pair(wish, consume_wish)
                    return True  # Fulfilled successfully
                except ConsumeWishFulfilled:
                    # This consume wish was already fulfilled.  Skip to next
                    pass
                except ProduceWishFulfilled:
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
    """Returns when exactly one consume or produce operation succeeds.

    When this function returns, either one value has been pulled from the
    channels in `consumers`, or one value has been pushed onto a channel in
    `producers`.

    Args:
      consumers: A list of Chan objects to consume from.
      producers: A list of (Chan, value), containing a channel and a value to
        put into the channel.

    Returns:
      Chan, value - If a consume channel is first
      Chan, None - If a produce channel is first

    """
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


import random
import unittest


def quickthread(fn, *args, **kwargs):
    th = threading.Thread(
        target=fn,
        args=args,
        kwargs=kwargs)
    th.daemon = True
    th.start()
    return th

def sayset(chan, phrases, delay=0.5):
    for ph in phrases:
        chan.put(ph)
        time.sleep(delay)

def distributer(inchans, outchans, delay_max=0.5):
    while True:
        _, value = chanselect(inchans, [])
        time.sleep(random.random() * delay_max)
        _, _ = chanselect([], [(chan, value) for chan in outchans])

def accumulator(chan, into):
    while True:
        value = chan.get()
        into.append(value)


class ChanTests(unittest.TestCase):
    def test_simple(self):
        chan = Chan()
        results = []
        quickthread(accumulator, chan, results)

        chan.put("Hello")
        time.sleep(0.01)  # Technically unsafe

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], "Hello")

    def test_nothing_lost(self):
        phrases = ['Hello_%03d' % x for x in xrange(1000)]
        firstchan = Chan()
        chan_layer1 = [Chan() for i in xrange(6)]
        lastchan = Chan()
        sayer = quickthread(sayset, firstchan, phrases, delay=0.001)

        # Distribute firstchan -> chan_layer1
        for i in xrange(12):
            outchans = [chan_layer1[(i+j)%len(chan_layer1)] for j in xrange(3)]
            quickthread(distributer, [firstchan], outchans, delay_max=0.005)

        # Distribute chan_layer1 -> lastchan
        for i in xrange(12):
            inchans = [chan_layer1[(i+j)%len(chan_layer1)]
                       for j in xrange(0, 9, 3)]
            quickthread(distributer, inchans, [lastchan], delay_max=0.005)

        results = []
        quickthread(accumulator, lastchan, results)

        sayer.join()
        time.sleep(1)

        # Checks that none are missing, and there are no duplicates.
        self.assertEqual(len(results), len(phrases))
        self.assertEqual(set(results), set(phrases))

unittest.main()

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
