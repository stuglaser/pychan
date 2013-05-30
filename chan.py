#!/usr/bin/env python
import collections
import contextlib
import random
import threading
import time


@contextlib.contextmanager
def all_locked(locks):
    try:
        for l in locks:
            l.acquire()
        yield
    finally:
        for l in locks:
            l.release()


class WTF(Exception):
    def __init__(self):
        super(WTF, self).__init__("WTF")


class Empty(Exception):
    pass

class Full(Exception):
    pass


class WishGroup(object):
    def __init__(self):
        self.fulfilled_by = None
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.wishes = []

    @property
    def fulfilled(self):
        return self.fulfilled_by is not None


WISH_PRODUCE = 0
WISH_CONSUME = 1

class Wish(object):
    def __init__(self, group, kind, chan, value=None):
        self.group = group
        self.kind = kind
        self.chan = chan
        self.value = value

        self.group.wishes.append(self)

    def __repr__(self):
        return "<Wish %s %r>" % (
            'p' if self.kind == WISH_PRODUCE else 'c',
            self.value)

    @property
    def fulfilled(self):
        return self.group.fulfilled

    def fulfill(self, value=None):
        """group must be locked"""
        self.group.fulfilled_by = self
        self.group.cond.notify()
        if self.kind == WISH_PRODUCE:
            return self.value
        else:
            self.value = value
            return


class Chan(object):
    def __init__(self):
        self._lock = threading.Lock()

        # TODO: Lists are inefficient lifo queues
        self._waiting_producers = []
        self._waiting_consumers = []

    def __repr__(self):
        return "<Chan 0x%x>" % id(self)

    def _get_nowait(self):
        """
        Returns a value from a waiting producer, or raises Empty

        Assumes that the Chan is locked.
        """
        while True:
            if self._waiting_producers:
                produce_wish = self._waiting_producers.pop(0)
                with produce_wish.group.lock:
                    if not produce_wish.group.fulfilled:
                        return produce_wish.fulfill()
            else:
                raise Empty()

    def _put_nowait(self, value):
        """
        Gives value to a waiting consumer, or raises Full

        Assumes that the Chan is locked.
        """
        while True:
            if self._waiting_consumers:
                consume_wish = self._waiting_consumers.pop(0)
                with consume_wish.group.lock:
                    if not consume_wish.group.fulfilled:
                        consume_wish.fulfill(value)
                        return
            else:
                raise Full()

    def get(self):
        with self._lock:
            try:
                return self._get_nowait()
            except Empty:
                pass
            group = WishGroup()
            wish = Wish(group, WISH_CONSUME, self)
            self._waiting_consumers.append(wish)

        with group.lock:
            while not group.fulfilled:
                group.cond.wait()

        return wish.value

    def put(self, value):
        with self._lock:
            try:
                self._put_nowait(value)
                return
            except Full:
                pass

            group = WishGroup()
            wish = Wish(group, WISH_PRODUCE, self, value)
            self._waiting_producers.append(wish)

        with group.lock:
            while not group.fulfilled:
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
    group = WishGroup()
    for chan in consumers:
        Wish(group, WISH_CONSUME, chan)
    for chan, value in producers:
        Wish(group, WISH_PRODUCE, chan, value)

    # Makes all cases fair
    random.shuffle(group.wishes)

    chan_locks_ordered = list(set(wish.chan._lock for wish in group.wishes))
    chan_locks_ordered.sort()

    with all_locked(chan_locks_ordered):
        # Checks for blocked threads that we can satisfy
        for wish in group.wishes:
            if wish.kind == WISH_CONSUME:
                try:
                    value = wish.chan._get_nowait()
                    return wish.chan, value
                except Empty:
                    pass
            else:  # PRODUCE
                try:
                    wish.chan._put_nowait(wish.value)
                    return wish.chan, None
                except Full:
                    pass

        # Enqueues wishes, to wait for fulfillment
        for wish in group.wishes:
            if wish.kind == WISH_CONSUME:
                wish.chan._waiting_consumers.append(wish)
            else:
                wish.chan._waiting_producers.append(wish)

    # Waits for the wish to be fulfilled
    with group.lock:
        while not group.fulfilled:
            group.cond.wait()

    # Removes the wishes from waiting queues
    with all_locked(chan_locks_ordered):
        for wish in group.wishes:
            if wish.kind == WISH_CONSUME:
                try:
                    wish.chan._waiting_consumers.remove(wish)
                except ValueError:
                    pass
            else:
                try:
                    wish.chan._waiting_producers.remove(wish)
                except ValueError:
                    pass

    wish = group.fulfilled_by
    return wish.chan, wish.value


import random
import unittest


def quickthread(fn, *args, **kwargs):
    name = kwargs.pop('__name', None)
    th = threading.Thread(
        name=name,
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
        sayer = quickthread(sayset, firstchan, phrases, delay=0.001,
                            __name='sayer')

        # Distribute firstchan -> chan_layer1
        for i in xrange(12):
            outchans = [chan_layer1[(i+j) % len(chan_layer1)]
                        for j in xrange(3)]
            quickthread(distributer, [firstchan], outchans, delay_max=0.005,
                        __name='dist_layer1_%02d' % i)

        # Distribute chan_layer1 -> lastchan
        for i in xrange(12):
            inchans = [chan_layer1[(i+j) % len(chan_layer1)]
                       for j in xrange(0, 9, 3)]
            quickthread(distributer, inchans, [lastchan], delay_max=0.005,
                        __name='dist_layer2_%02d' % i)

        results = []
        quickthread(accumulator, lastchan, results, __name='accumulator')
        sayer.join()
        time.sleep(1)

        # Checks that none are missing, and there are no duplicates.
        self.assertEqual(len(results), len(phrases))
        self.assertEqual(set(results), set(phrases))

if __name__ == '__main__':
    unittest.main()
