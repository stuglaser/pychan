.. _api:

API Reference
=============

.. module:: chan

This document describes the functions and objects used in pyChan.

Exceptions
----------

.. autoclass:: Error
   :members:

.. class:: ChanClosed(which=chan)

   Since :class:`ChanClosed` inherits from :class:`Error`, it has
   the same parameters as :class:`Exception`, with one addition:

   :param which: Keyword argument, indicating the :class:`Chan` that
                 was closed.

   .. attribute:: which

      Contains the :class:`Chan` object which was closed.

.. autoclass:: Timeout
   :members:


Chan Object
-----------

.. autoclass:: Chan
   :members:


Multiplexing with ``chanselect``
--------------------------------

.. autofunction:: chanselect
