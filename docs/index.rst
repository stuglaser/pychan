.. pyChan documentation master file, created by
   sphinx-quickstart on Sat Jun 29 18:34:08 2013.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

.. module:: chan

pyChan: Go-style channels for Python
====================================

Release v\ |version|.

pyChan implements Go's ``chan`` type in Python, making concurrent programming
in Python simple.

Install using ``pip install chan``

Source code at http://github.com/stuglaser/pychan

:ref:`api`

Usage
-----

You can use :func:`Chan.put` to place items onto a :class:`Chan`, and
:func:`Chan.get` to receive them:

.. code-block:: python

    c = Chan()

    # Thread 1
    c.put("Hello")

    # Thread 2
    print "Heard: %s" % c.get()

Channels can be closed (usually by the sender).
Iterating over a channel gives all values until the channel is closed

.. code-block:: python

    c = Chan()

    # Thread 1
    c.put("It's")
    c.put("just")
    c.put("contradiction")

    # Thread 2
    for thing in c:
        print "Heard:", thing

You can wait on multiple channels using :func:`chanselect`.  Pass it a list of input channels and another of output channels, and it will return when any of the channels is ready

.. code-block:: python

    def fan_in(outchan, input1, input2):
        while True:
            chan, value = chanselect([input1, input2], [])
            if chan == input1:
                outchan.put("From 1: " + str(value))
            else:
                outchan.put("From 2 " + str(value))

You can see more examples in the "examples" directory.


Contents:

.. toctree::
   :maxdepth: 2

   api



Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

