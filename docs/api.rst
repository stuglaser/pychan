.. _api:

API Reference
=============

.. module:: chan

This document describes the functions and objects used in pyChan.

Exceptions
----------

.. class:: ChanClosed(which=chan)

   Since :class:`ChanClosed` inherits from :class:`Exception`, it has
   the same parameters, with one addition:

   :param which: Keyword argument, indicating the :class:`Chan` that
                 was closed.

   .. attribute:: which

      Contains the :class:`Chan` object which was closed.


Chan Object
-----------

.. autoclass:: Chan
   :members:
   :inherited-members:

Multiplexing with ``chanselect``
--------------------------------

.. autofunction:: chanselect
