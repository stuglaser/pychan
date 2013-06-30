Go-style Chan for Python
========================

Implements Go's chan type in Python.

Install with ``pip install chan``

Usage
-----

You can ``put`` onto channels, and ``get`` from them

.. code-block:: Python

    c = Chan()

    # Thread 1
    c.put("Hello")

    # Thread 2
    print "Heard: %s" % c.get()

Channels can be closed (usually by the sender).
Iterating over a channel gives all values until the channel is closed

.. code-block:: Python

    c = Chan()

    # Thread 1
    c.put("It's")
    c.put("just")
    c.put("contradiction")

    # Thread 2
    for thing in c:
        print "Heard:", thing

You can wait on multiple channels using ``chanselect``.  Pass it a list of input channels and another of output channels, and it will return when any of the channels is ready

.. code-block:: Python

    def fan_in(outchan, input1, input2):
        while True:
            chan, value = chanselect([input1, input2], [])
            if chan == input1:
                outchan.put("From 1: " + str(value))
            else:
                outchan.put("From 2 " + str(value))

You can see more examples in the "examples" directory.

.. image:: https://nojsstats.appspot.com/UA-41669691-1/github.com
