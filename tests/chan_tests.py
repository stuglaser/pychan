import random
import threading
import time
import unittest

from chan import Chan, chanselect, quickthread
from chan import ChanClosed, Timeout
from chan.chan import RingBuffer


def sayset(chan, phrases, delay=0.5):
    for ph in phrases:
        chan.put(ph)
        time.sleep(delay)
    chan.close()


def distributer(inchans, outchans, delay_max=0.5):
    inchans = inchans[:]  # Copy.  Will remove closed chans
    while True:
        try:
            _, value = chanselect(inchans, [])
            time.sleep(random.random() * delay_max)
        except ChanClosed as ex:
            inchans.remove(ex.which)
            continue
        _, _ = chanselect([], [(chan, value) for chan in outchans])


def accumulator(chan, into=None):
    if into is None:
        into = []
    for value in chan:
        into.append(value)


class RingBufferTests(unittest.TestCase):
    def test_pushpop(self):
        buf = RingBuffer(4)
        for i in range(12):
            buf.push(i)
            self.assertEqual(buf.pop(), i)

    def test_fillunfill(self):
        S = 4
        buf = RingBuffer(S)
        for i in range(12):
            for j in range(S):
                buf.push(100 * i + j)
            for j in range(S):
                self.assertEqual(buf.pop(), 100 * i + j)

            # Moves ahead one space
            buf.push('NaN')
            buf.pop()


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
        phrases = ['Hello_%03d' % x for x in range(1000)]
        firstchan = Chan()
        chan_layer1 = [Chan() for i in range(6)]
        lastchan = Chan()
        sayer = quickthread(sayset, firstchan, phrases, delay=0.001,
                            __name='sayer')

        # Distribute firstchan -> chan_layer1
        for i in range(12):
            outchans = [chan_layer1[(i+j) % len(chan_layer1)]
                        for j in range(3)]
            quickthread(distributer, [firstchan], outchans, delay_max=0.005,
                        __name='dist_layer1_%02d' % i)

        # Distribute chan_layer1 -> lastchan
        for i in range(12):
            inchans = [chan_layer1[(i+j) % len(chan_layer1)]
                       for j in range(0, 9, 3)]
            quickthread(distributer, inchans, [lastchan], delay_max=0.005,
                        __name='dist_layer2_%02d' % i)

        results = []
        quickthread(accumulator, lastchan, results, __name='accumulator')
        sayer.join(10)
        self.assertFalse(sayer.is_alive())
        time.sleep(1)  # Unsafe.  Lets the data propagate to the accumulator

        # Checks that none are missing, and there are no duplicates.
        self.assertEqual(len(results), len(phrases))
        self.assertEqual(set(results), set(phrases))

    def test_iter_and_closed(self):
        c = Chan()
        quickthread(sayset, c, [1, 2, 3], delay=0)

        def listener():
            it = iter(c)
            self.assertEqual(next(it), 1)
            self.assertEqual(next(it), 2)
            self.assertEqual(next(it), 3)
            self.assertRaises(StopIteration, it.__next__)
        t = quickthread(listener)

        time.sleep(0.1)
        self.assertFalse(t.is_alive())

    def test_putget_timeout(self):
        c = Chan()
        self.assertRaises(Timeout, c.put, 'x', timeout=0)
        self.assertRaises(Timeout, c.put, 'x', timeout=0.01)
        self.assertRaises(Timeout, c.get, timeout=0)
        self.assertRaises(Timeout, c.get, timeout=0.01)
        self.assertRaises(Timeout, c.put, 'x', timeout=0)

    def test_chanselect_timeout(self):
        a = Chan()
        b = Chan()
        c = Chan()
        self.assertRaises(Timeout, chanselect, [a, b], [(c, 42)], timeout=0)
        self.assertRaises(Timeout, chanselect, [a, b], [(c, 42)], timeout=0.01)

        # Verifies that chanselect didn't leave any wishes lying around.
        self.assertRaises(Timeout, a.put, 12, timeout=0)
        self.assertRaises(Timeout, c.get, timeout=0)

    def test_select_and_closed(self):
        a, b, c = [Chan() for _ in range(3)]
        out = Chan()
        quickthread(sayset, a, [0, 1, 2], delay=0.01, __name='sayset1')
        quickthread(sayset, b, [3, 4, 5], delay=0.01, __name='sayset2')
        quickthread(sayset, c, [6, 7, 8], delay=0.01, __name='sayset2')

        def fanin_until_closed(inchans, outchan):
            inchans = inchans[:]
            while inchans:
                try:
                    _, val = chanselect(inchans, [])
                    out.put(val)
                except ChanClosed as ex:
                    inchans.remove(ex.which)
            out.close()

        quickthread(fanin_until_closed, [a, b, c], out, __name='fanin')

        into = []
        acc = quickthread(accumulator, out, into)
        acc.join(10)
        self.assertFalse(acc.is_alive())

        results = set(into)
        self.assertEqual(len(results), 9)
        self.assertEqual(results, set(range(9)))

    def test_buf_simple(self):
        S = 5
        c = Chan(S)
        for i in range(S):
            c.put(i)
        c.close()

        results = list(c)
        self.assertEqual(results, list(range(S)))

    def test_buf_overfull(self):
        c = Chan(5)
        quickthread(sayset, c, list(range(20)), delay=0)
        time.sleep(0.1)  # Fill up buffer

        results = list(c)
        self.assertEqual(results, list(range(20)))

    def test_buf_kept_empty(self):
        c = Chan(5)
        quickthread(sayset, c, list(range(20)), delay=0.02)
        results = list(c)
        self.assertEqual(results, list(range(20)))

if __name__ == '__main__':
    unittest.main()
