.. _syntax-logic:

Boolean Logic
=============

Selections combine with the boolean operators ``and``, ``or``, ``not`` and
``xor``. Each operator below is covered by the ``logic`` cases of the
selection-contract test suite.

Operators
---------

.. code-block:: text

   oxygen and water
   oxygen or water
   not water
   oxygen xor water

``xor`` (exclusive or) is a MolSelect operator with no direct VMD/ProDy keyword;
it is equivalent to ``(a or b) and not (a and b)``.

Implicit AND
------------

Two selections written next to each other are combined with ``and``:

.. code-block:: text

   resname ALA name CA        is equivalent to   resname ALA and name CA
   water oxygen               is equivalent to   water and oxygen

.. note::

   VMD requires an explicit ``and`` between two property selections, so the
   contract compares the implicit form against an explicit ``and`` for VMD.

Precedence and grouping
-----------------------

``not`` binds tighter than ``and``, which binds tighter than ``or``. Parentheses
override the default precedence:

.. code-block:: text

   not water and name CA          parses as   (not water) and name CA
   oxygen and water or name CA    parses as   (oxygen and water) or name CA
   (oxygen or name CA) and noh
   ((water or oxygen) and noh) or name CB

Negation is an involution — an even number of ``not`` cancels:

.. code-block:: text

   not not water                 is equivalent to   water
   not not not not name CA       is equivalent to   name CA
