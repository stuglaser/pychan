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
        self.closed = False

        self.group.wishes.append(self)

    def __repr__(self):
        return "<Wish %s %r>" % (
            'p' if self.kind == WISH_PRODUCE else 'c',
            self.value)

    @property
    def fulfilled(self):
        return self.group.fulfilled

    def fulfill(self, value=None, closed=False):
        """group must be locked"""
        assert not self.fulfilled
        self.closed = closed
        self.group.fulfilled_by = self
        self.group.cond.notify()
        if self.kind == WISH_PRODUCE:
            return self.value
        else:
            self.value = value
            return


class ChanClosed(Exception):
    def __init__(self, *args, **kwargs):
        self.which = kwargs.pop('which')
        super(ChanClosed, self).__init__(*args, **kwargs)


class RingBuffer(object):
    def __init__(self, buflen):
        self.buf = [None] * buflen
        self.next_pop = 0
        self._len = 0

    @property
    def cap(self):
        return len(self.buf)

    def push(self, value):
        if self._len == len(self.buf):
            raise IndexError()
        next_push = (self.next_pop + self._len) % len(self.buf)
        self.buf[next_push] = value
        self._len += 1

    def pop(self):
        if self._len == 0:
            raise IndexError()
        value = self.buf[self.next_pop]
        self.buf[self.next_pop] = None  # Safety
        self.next_pop = (self.next_pop + 1) % len(self.buf)
        self._len -= 1
        return value

    def __len__(self):
        return self._len

    @property
    def empty(self):
        return self._len == 0

    @property
    def full(self):
        return self._len == len(self.buf)


class Chan(object):
    def __init__(self, buflen=0):
        self._lock = threading.Lock()
        self._closed = False

        if buflen > 0:
            self._buf = RingBuffer(buflen)
        else:
            self._buf = None

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
        # Fulfills a waiting producer, returning its value, or raising Empty if
        # no fulfillable producers are waiting.
        def fulfill_waiting_producer():
            while True:
                if self._waiting_producers:
                    produce_wish = self._waiting_producers.pop(0)
                    with produce_wish.group.lock:
                        if not produce_wish.group.fulfilled:
                            return produce_wish.fulfill()
                else:
                    raise Empty()

        if self._buf is not None and not self._buf.empty:
            value = self._buf.pop()
            try:
                # Cycles a producer's value onto the buffer
                produced = fulfill_waiting_producer()
                self._buf.push(produced)
            except Empty:
                pass
            return value
        else:
            return fulfill_waiting_producer()

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
            elif self._buf is not None and not self._buf.full:
                self._buf.push(value)
                return
            else:
                raise Full()

    def get(self):
        with self._lock:
            try:
                return self._get_nowait()
            except Empty:
                pass

            if self._closed:
                raise ChanClosed(which=self)

            group = WishGroup()
            wish = Wish(group, WISH_CONSUME, self)
            self._waiting_consumers.append(wish)

        with group.lock:
            while not group.fulfilled:
                group.cond.wait()

        if wish.closed:
            raise ChanClosed(which=self)
        return wish.value

    def put(self, value):
        with self._lock:
            if self._closed:
                raise ChanClosed(which=self)
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
        if wish.closed:
            raise ChanClosed(which=self)

    def close(self):
        with self._lock:
            if self._closed:
                raise RuntimeError("Channel double-closed")
            self._closed = True

            # Copies waiting wishes, to be fulfilled when the Chan is unlocked.
            wishes = self._waiting_producers[:] + self._waiting_consumers[:]

        for wish in wishes:
            with wish.group.lock:
                if not wish.fulfilled:
                    wish.fulfill(closed=True)

    @property
    def closed(self):
        with self._lock:
            return self._closed and not self._waiting_producers

    def __iter__(self):
        return self

    def next(self):
        try:
            return self.get()
        except ChanClosed:
            raise StopIteration


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
      Raises ChanClosed(which=Chan) - If any channel is closed
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
            if wish.chan._closed:
                raise ChanClosed(which=wish.chan)

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
    if wish.closed:
        raise ChanClosed(which=wish.chan)
    return wish.chan, wish.value


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
