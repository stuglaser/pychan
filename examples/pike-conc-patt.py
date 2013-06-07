#!/usr/bin/env python
#
# Examples from the talk:
#   Rob Pike - Google I/O 2012 - Go Concurrency Patterns
#   http://www.youtube.com/watch?v=f6kdp27TYZs
#   http://code.google.com/p/go/source/browse/2012/concurrency.slide?repo=talks

from chan import Chan, chanselect, quickthread

from collections import namedtuple
from collections import OrderedDict
import time
import random
import sys

EXAMPLES = OrderedDict()


#---------------------------------------------------------------------------
#    Fan In
#---------------------------------------------------------------------------


def example_fan_in():
    def boring(message):
        def sender(message, c):
            i = 0
            while True:
                c.put("%s: %d" % (message, i))
                time.sleep(0.2 * random.random())
                i += 1

        c = Chan()
        quickthread(sender, message, c)
        return c

    def fan_in(input1, input2):
        def forwarder(input, output):
            while True:
                output.put(input.get())

        c = Chan()
        quickthread(forwarder, input1, c)
        quickthread(forwarder, input2, c)
        return c

    c = fan_in(boring("Joe"), boring("Ann"))
    for i in xrange(10):
        print c.get()
    print "You're both boring; I'm leaving."

EXAMPLES['fanin'] = example_fan_in


#---------------------------------------------------------------------------
#    Sequence
#---------------------------------------------------------------------------

def example_sequence():
    Message = namedtuple("Message", ['string', 'wait'])

    def boring(msg):
        c = Chan()
        wait_for_it = Chan()

        def sender():
            i = 0
            while True:
                c.put(Message("%s: %d" % (msg, i), wait_for_it))
                time.sleep(0.2 * random.random())
                wait_for_it.get()
                i += 1
        quickthread(sender)
        return c

    def fan_in(*input_list):
        def forward(input, output):
            while True:
                output.put(input.get())

        c = Chan()
        for input in input_list:
            quickthread(forward, input, c)
        return c

    c = fan_in(boring('Joe'), boring('Ann'))
    for i in xrange(5):
        msg1 = c.get(); print msg1.string
        msg2 = c.get(); print msg2.string
        msg1.wait.put(True)
        msg2.wait.put(True)
    print "You're all boring; I'm leaving"

EXAMPLES['sequence'] = example_sequence


#---------------------------------------------------------------------------
#    Select
#---------------------------------------------------------------------------

def example_select():
    def boring(msg):
        c = Chan()

        def sender():
            i = 0
            while True:
                c.put("%s: %d" % (msg, i))
                time.sleep(1.0 * random.random())
                i += 1
        quickthread(sender)
        return c

    def fan_in(input1, input2):
        c = Chan()

        def forward():
            while True:
                chan, value = chanselect([input1, input2], [])
                c.put(value)

        quickthread(forward)
        return c

    c = fan_in(boring("Joe"), boring("Ann"))
    for i in xrange(10):
        print c.get()
    print "You're both boring; I'm leaving."

EXAMPLES['select'] = example_select


#---------------------------------------------------------------------------
#    Timeout
#---------------------------------------------------------------------------

def timer(duration):
    def timer_thread(chan, duration):
        time.sleep(duration)
        chan.put(time.time())
    c = Chan()
    quickthread(timer_thread, c, duration)
    return c


def example_timeout():
    def boring(msg):
        c = Chan()

        def sender():
            i = 0
            while True:
                c.put("%s: %d" % (msg, i))
                time.sleep(1.5 * random.random())
                i += 1
        quickthread(sender)
        return c

    c = boring("Joe")
    while True:
        chan, value = chanselect([c, timer(1.0)], [])
        if chan == c:
            print value
        else:
            print "You're too slow."
            return

EXAMPLES['timeout'] = example_timeout


#---------------------------------------------------------------------------
#    RCV Quit
#---------------------------------------------------------------------------

def example_rcvquit():
    def boring(msg, quit):
        c = Chan()

        def sender():
            i = 0
            while True:
                time.sleep(1.0 * random.random())

                chan, _ = chanselect([quit], [(c, "%s: %d" % (msg, i))])
                if chan == quit:
                    quit.put("See you!")
                i += 1
        quickthread(sender)
        return c

    quit = Chan()
    c = boring("Joe", quit)
    for i in xrange(random.randint(0, 10), 0, -1):
        print c.get()
    quit.put("Bye!")
    print "Joe says:", quit.get()

EXAMPLES['rcvquit'] = example_rcvquit


#---------------------------------------------------------------------------
#    Daisy chain
#---------------------------------------------------------------------------

def example_daisy():
    def f(left, right):
        left.put(1 + right.get())

    N = 1000  # Python's threads aren't that lightweight
    leftmost = Chan()
    rightmost = leftmost
    left = leftmost
    for i in xrange(N):
        right = Chan()
        quickthread(f, left, right)
        left = right

    def putter():
        right.put(1)
    quickthread(putter)

    print leftmost.get()

EXAMPLES['daisy'] = example_daisy


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in EXAMPLES:
        print "Possible examples:"
        for example in EXAMPLES.iterkeys():
            print "  %s" % example
        return

    EXAMPLES[sys.argv[1]]()

if __name__ == '__main__':
    main()
