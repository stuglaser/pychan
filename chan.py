#!/usr/bin/env python
import collections
import threading
import time

class WTF(Exception):
    def __init__(self):
        super(WTF, self).__init__("WTF")

class Chan(object):
    def __init__(self):
        self.__lock = threading.Lock()
        self.__cond = threading.Condition(self.__lock)

        # TODO: Lists are inefficient lifo queues
        self.__waiting_producers = []
        self.__waiting_consumers = []

    def get(self):
        cond = threading.Condition(self.__lock)
        basket = []

        with self.__lock:
            self.__waiting_consumers.append((cond, basket))
            self.__cond.notify()
            while len(basket) == 0:
                cond.wait()

        return basket[0]

    def put(self, value):
        with self.__lock:
            while not self.__waiting_consumers:
                self.__cond.wait()

            cond, basket = self.__waiting_consumers.pop(0)

            basket.append(value)
            cond.notify()

def chanselect(listen, speak, closed):
    pass

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
    heard, _, _ = chanselect([a, b], [], [])
    chan, value = heard
    if chan == a:
        print "From A:", heard
    elif chan == b:
        print "From B:", heard
    else:
        raise WTF()


a = Chan()
b = Chan()
go(printfirst, a, b)
go(athlete, a, "AA", delay=0.8)
go(athlete, b, "BB", delay=0.7)
time.sleep(2)

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
