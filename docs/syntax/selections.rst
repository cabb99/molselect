.. _syntax-selections:

Selection Syntax
================

A selection is an expression that evaluates to a set of atoms. MolSelect's
grammar follows the VMD/ProDy family of atom-selection languages. Every form
described here is exercised by the selection-contract test suite
(``molselect/python/tests/test_selection_contract.py``); where MolSelect
deliberately differs from VMD or ProDy, that difference is listed in
:doc:`../Compatibility`.

Flags and macros
----------------

A bare keyword selects every atom matching a named class. These come from the
macro table (see :doc:`../macros`):

.. code-block:: text

   all
   protein
   water
   nucleic
   backbone
   helix

Field filters
-------------

A field keyword followed by one or more values selects atoms whose property
equals any of the values (see :doc:`../keywords` for the full list):

.. code-block:: text

   name CA
   name CA CB
   resname ALA GLY
   chain A
   element O
   resid 4

String values may be quoted or given as regular expressions; see
`Regular expressions and quoting`_ below.

Value lists and ranges
----------------------

Integer and float fields accept lists and ranges. ``N:M`` is **inclusive** of
``M`` (matching VMD's ``N to M``); ``N:M:S`` adds a step:

.. code-block:: text

   serial 1 2 3
   resid 10 to 20
   index 0:10
   serial 0:10:2

.. note::

   MolSelect ``N:M`` includes the endpoint ``M``. ProDy's ``:`` range is
   exclusive of the endpoint, so the contract compares against ProDy's
   ``N to M`` form. The glued ``NtoM`` spelling (no spaces, e.g. ``resid 10to15``)
   is **not** yet supported.

Regular expressions and quoting
-------------------------------

Double-quoted values are treated as regular expressions; single quotes preserve
literal characters (including spaces and apostrophes):

.. code-block:: text

   name "C.*"
   name "C(A|B)"
   resname "S.."
   resname 'DG'
   name O5'

Spatial selections
------------------

Distance and set-membership operators build selections from other selections:

.. code-block:: text

   within 5 of water
   exwithin 3 of water
   same residue as index 0
   same chain as chain C

``within`` includes the reference atoms; ``exwithin`` excludes them. ``same
<field> as`` expands a selection to every atom sharing that field value.

Sequence selections
-------------------

``sequence`` matches one-letter residue sequences, as a literal or a regular
expression:

.. code-block:: text

   sequence MIEIK
   sequence "MI.*DKQ"

Combining selections
--------------------

Selections combine with the boolean operators described in :doc:`logic`, and
their numeric fields support the comparisons and math in :doc:`math`.
