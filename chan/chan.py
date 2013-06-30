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
    """Chan objects allow multiple threads to communicate.

    :param buflen: Defines the size of the channel's internal buffer, or 0 if
                   the channel should be unbuffered.  An unbuffered channel
                   blocks on all put/get's, unless a corresponding get/put is
                   already waiting, while a buffered channel will accept puts
                   without blocking as long as the buffer is not full.

    """
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
        """Returns an item that was ``put`` onto the channel.

        ``get`` returns immediately if there are items in the channel's buffer
        or if another thread is blocked on ``put``.  Otherwise, it blocks until
        another thread puts an item onto this channel.

        :raises: :class:`ChanClosed` If the channel has been closed, the \
                 buffer is empty, and no threads are waiting on ``put``.

        """
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
        """Places an item onto the channel.

        ``put`` returns immediately if the channel's buffer has room, or if
        another thread is blocked on ``get``.  Otherwise, ``put`` will block
        until another thread calls ``get``.

        :param value: The value to place on the channel.  It is unwise to
                      modify ``value`` afterwards, since the other thread will
                      receive it directly, and not just a copy.  It can be any
                      type.

        :raises: :class:`ChanClosed` If the channel has already been closed.

        """
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
        """Closes the channel, allowing no further ``put`` operations.

        Once ``close`` is called, the channel allows in-progress ``put``
        operations to complete and the buffer to clear, and then 

        """
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
        """Returns True if the channel is closed.

        It may be better to call ``put`` or ``get`` and handle the
        :class:`ChanClosed` exception.

        """
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

    When this function returns, either a channel is closed, or one value has
    been pulled from the channels in ``consumers``, or one value has been
    pushed onto a channel in ``producers``.

    ``chanselect`` returns different values depending on which channel was
    ready first:

    - (:class:`Chan`, value) -- If a consume channel is first.
    - (:class:`Chan`, None) -- If a produce channel is first
    - Raises :class:`ChanClosed`\ ``(which=Chan)`` - If any channel is closed

    :param consumers: A list of :class:`Chan` objects to consume from.
    :param producers: A list of (:class:`Chan`, value), containing a channel
                      and a value to put into the channel.

    Here's a quick example.  Let's say we're waiting to receive on channels
    ``chan_a`` and ``chan_b``, and waiting to send on channels ``chan_c`` and
    ``chan_d``.  The call to ``chanselect`` looks something like this:

    .. code-block:: python

        ch, value = chanselect([chan_a, chan_b],
                               [(chan_c, 'C'), (chan_d, 'D')])
        if ch == chan_a:
            print("Got {} from A".format(value))
        elif ch == chan_b:
            print("Got {} from B".format(value))
        elif ch == chan_c:
            print("Sent on C")
        elif ch == chan_d:
            print("Sent on D")
        else:
            raise RuntimeError("Can't get here")

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
