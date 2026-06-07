.. _user-guide:

User Guide
===========

Quick Reference
-------------------

.. list-table:: Syntax Quick Reference
   :widths: 25 35
   :header-rows: 1

.. list-table:: Common Selection Keywords
   :widths: 20 60
   :header-rows: 1

   * - **Form**
     - **Examples**
   * - Flag
     - ``all``; ``protein``; ``water``; ``ion``
   * - Field filter
     - ``name CA CB``; ``resname ALA GLY``; ``index 0:10``; ``resid 1:4:2``
   * - Numeric & math
     - ``mass > 12``; ``-10 <= x < 0``; ``sqrt(x**2 + y**2 + z**2) < 10``; ``index % 2 == 1``
   * - Regex & quoting
     - ``name "C.*"``; ``resname "S.."``; ``name 'A 1'``; ``resnum `-3:16:1````
   * - Spatial & bonded
     - ``within 5 of water``; ``exwithin 3 of water``; ``bonded 1 to calpha``; ``exbonded 1 to calpha``
   * - Advanced selection
     - ``sequence MIEIK``; ``sequence "S[A-Z]{2}G"``; ``same residue as index 0``; ``same chain as index 0``
   * - Logical combination
     - ``resid 10 to 20 and backbone``; ``protein and same residue as within 5 of water``



.. tip::
    For details of available selection keywords and macros, refer to the following resources:
    
    - :doc:`keywords` — Comprehensive glossary of selection keywords and their usage.
    - :doc:`macros` — List of available macros with examples.

.. _selection-grammar:

Introduction
-----------------

The MolSelect grammar evaluates a query in four distinct layers. Each layer transforms data step by step:

1. **Arithmetic Expressions**
   
   Computes purely numeric values. These can be scalars or arrays, but they never reference atom properties.
   
   **Example:**
   ::
      sqrt(2 + 3*4)
      10 / 3

2. **Property (Attribute) Expressions**
   
   Extracts per-atom properties—coordinates, mass, dihedral angles, etc.—and combine them with arithmetic operators or functions.
   
   **Example:**
   ::
      x + y + z - 10
      log(occupancy)
      phi - psi

3. **Filter (Predicate) Expressions**
   
   Compares numeric or string expressions against literals, ranges, or regex patterns. Each yields a boolean mask (one `True`/`False` per atom).
   
   **Examples:**
   ::
      mass > 12
      resname 'ALA'
      name =~ "^C.*"

4. **Logical Combination**
   
   Combines boolean masks (list indicating which atoms are selected) into a final selection mask. Parentheses may be used to control precedence.
   
   **Example:**
   ::
      (resname ALA and mass > 12) or within 5 of water



Selection Language Overview
-------------------------------

Every query in MolSelect builds a Boolean mask (i.e., the set of atoms you’ll get back) by combining:

1. **Flags** (e.g., ``protein``, ``water``, ``charged``)
2. **Field filters** (e.g., ``name CA``, ``resname ALA``, ``mass > 12``)
3. **Spatial/bonded filters** (e.g., ``within 5 of ...``, ``bonded 1 to ...``)
4. **Structural helpers** (e.g., ``same residue as ...``)
5. **Sequence patterns** (e.g., ``sequence 'MIEIK'``)
6. **Macros & Variables** (see :ref:`macros`, :ref:`variables`)

Combine everything with ``and``, ``or``, ``xor``, ``not`` (see next section), and nest with parentheses.



Selection Grammar Reference
-------------------------------

Boolean Logic & Combining Filters
--------------------------------------

.. list-table:: Boolean Operators & Precedence
   :widths: 15 25 60
   :header-rows: 1

   * - Operator
     - Syntax
     - Example
   * - NOT
     - ``not``, ``!``
     - ``not water``
   * - AND
     - ``and``, ``&&``, ``&``, *implicit*
     - ``backbone and name CA``
   * - OR
     - ``or``, ``||``, ``|``
     - ``protein or water``
   * - XOR
     - ``xor``
     - ``protein xor nucleic``
   * - Grouping
     - ``(...)``
     - ``(protein or water) and not acidic``

**Operator precedence:** ``NOT`` > ``AND`` > ``XOR`` > ``OR``

.. tip::
   Writing two filters side-by-side implies AND:
   ::

     resname ALA CB   # same as "resname ALA and resname CB"

.. note::
   Writing ``resname ALA VAL LEU`` is equivalent to
   ``resname ALA or resname VAL or resname LEU``.

Basic Selections
---------------------

Boolean Flags
^^^^^^^^^^^^^

.. list-table:: Flag Categories
   :widths: 20 80
   :header-rows: 1

   * - Category
     - Keywords (see :ref:`residue-types`)
   * - Universals
     - ``all``, ``everything``, ``none``, ``nothing``
   * - Biomolecules
     - ``protein``, ``is_protein``, ``water``, ``waters``, ``dna``, ``rna``, ``lipid``, ``ion``, ``solvent``
   * - Residues
     - ``charged``, ``acidic``, ``basic``, ``polar``, ``hydrophobic``, ``aromatic``, ``aliphatic``, ``buried``, ``surface``, ``small``, ``medium``, ``large``
   * - Elements
     - ``carbon``, ``nitrogen``, ``oxygen``, ``hydrogen``, ``sulfur``, ``phosphorus``
   * - Structures
     - ``helix``, ``sheet``, ``coil``, ``turn``, ``bend``, ``bridge_beta``, ``pi_helix``, ``3_10_helix``

Field-Based Filters
^^^^^^^^^^^^^^^^^^^

.. list-table:: Field Filters
   :widths: 20 30 50
   :header-rows: 1

   * - Field
     - What it matches
     - Examples
   * - name
     - Atom name(s)
     - ``name CA``, ``name CA CB``
   * - resname
     - Residue name(s)
     - ``resname ALA``, ``resname ALA GLY``
   * - index
     - Zero-based atom index(s)
     - ``index 0 5 10``
   * - serial
     - PDB serial number(s)
     - ``serial 1:10:2``
   * - chain
     - Chain ID(s)
     - ``chain A``
   * - resid
     - Residue sequence numbers or ranges
     - ``resid 50 to 100``, ``resid 1:4``
   * - secondary
     - Secondary structure code (``H``, ``E``)
     - ``secondary H E``
   * - mass, occupancy, beta
     - Numeric fields
     - ``mass > 12``, ``occupancy = 1.0``
   * - x, y, z
     - Cartesian coordinates
     - ``x -25 to 25``
   * - phi, psi
     - Backbone dihedrals
     - ``phi -60 to -30``
   * - segment, pfrag, nfrag
     - Entity/fragment info
     - ``segment A``, ``pfrag 1``
   * - vx, vy, vz, fx, fy, fz
     - Velocities/forces
     - ``vx > 0``, ``fy < 0``

.. tip::
   See :doc:`keywords` for the full list of available fields.

.. warning::
   To select residues –3 to 5 you **must** write:
   ::
      
      resid `-3:5`

.. _macros:

Using Macros & Variables
------------------------

- **Macros** (``@foo``): refer to a named saved selection

  ::
     @ligand
     @protein

- **Variables** (``$var``): select by user-defined numeric/vector data

  ::
     name eq $atomname

.. _variables:

Optional “in” Keyword
---------------------

You can use ``in`` for property selection:

::
   mass 10 to 20       # same as
   mass in 10 to 20

Numeric Comparisons & Ranges
----------------------------

.. list-table:: Comparison Operators
   :widths: 15 20 40
   :header-rows: 1

   * - Symbol(s)
     - Meaning
     - Example
   * - ``=``, ``==``, ``eq``
     - equal
     - ``beta = 10``
   * - ``!=``, ``ne``
     - not equal
     - ``mass != 12``
   * - ``<``, ``lt``
     - less than
     - ``x < 0``
   * - ``<=``, ``le``
     - ≤
     - ``-10 <= x``
   * - ``>``, ``gt``
     - greater than
     - ``z > 5.5``
   * - ``>=``, ``ge``
     - ≥
     - ``y >= 3``

Chained comparisons work too:

::
   -5 <= x < 5

Ranges & Lists
^^^^^^^^^^^^^^

* **Range**

  ::
     resid 100 to 200
     1:4         # same as "1 to 4"
     1:10:3      # 1,4,7,10

* **Lists** (OR)

  ::
     resid 1 3 5 7
     mass 12.5 14.0 16.2

* **Backtick-quoted** for negatives or complex strings:

  ::
     resid `-3:5`
     name `A 1`

Arithmetic & Functions
----------------------

You can mix math right into comparisons or range endpoints:

* **Operators**: ``+``, ``-``, ``*``, ``/``, ``//``, ``%``, ``**``
* **Functions**: ``sin(x)``, ``cos(x)``, ``tan(x)``, ``sqrt()``, ``exp()``, ``log()``, ``abs()``, ``floor()``, ``ceil()``, ``sinh()``, ``cosh()``, ``tanh()``
* **Constants**: ``pi``, ``e``

::
   sqrt(x**2 + y**2 + z**2) < 10    # distance from origin
   mass + 10 > 50 and protein       # offset mass then compare
   abs(beta) = beta                 # check symmetry

.. note::
   ``sqrt(x**2 + y**2) < 10``        # OK  
   ``sqrt(25) < 10``                 # purely numeric—invalid as a mask

.. tip::
   If your math side is pure numeric, it uses the **number** grammar; if it touches a field (e.g. ``x``, ``mass``, ``resid``), it becomes a **math_expr** that yields an array.

Regular Expressions & Quoting
-----------------------------

Regex Matching
^^^^^^^^^^^^^^

* Operator: ``=~``
* Pattern in quotes:

  ::
     name =~ "^C[A,B]"
     resname =~ "A.*"

Quoting Styles
^^^^^^^^^^^^^^

.. list-table:: Quoting Styles
   :widths: 15 40 40
   :header-rows: 1

   * - Style
     - When to use
     - Example
   * - Double
     - simple strings, no ``"``
     - ``"CA"``, ``"A.*"``
   * - Single
     - strings with ``"`` inside
     - ``'A "chain"'``
   * - Backticks
     - ranges or multi-word values
     - ```-10:20```, ```A 1```

Escape quotes inside by backslash (``\"`` or ``\'``) as in any typical DSL.

.. tip::
   - Forgetting quotes: ``name A 1`` → two filters, not one.
   - Over-quoting regex: use double-quotes for regex, not backticks.
   - Mixing steps: ``1:4:2`` vs ``1 to 4`` (inclusive vs step).

Distance & Bonded Filters
-------------------------

Spatial Proximity
^^^^^^^^^^^^^^^^^

.. list-table:: Spatial/Bonded Syntax
   :widths: 30 70
   :header-rows: 1

   * - Syntax
     - Picks
   * - ``within N of <filter>``
     - atoms ≤ N Å from any atom in ``<filter>``
   * - ``exwithin N of <filter>``
     - same, excluding the atoms in ``<filter>`` itself

::
   within 5 of water
   protein within 3 of (resname ALA or resname GLY)
   not (within 2 of metal)

Chemical Bonds
^^^^^^^^^^^^^^

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Syntax
     - Picks
   * - ``bonded N to <filter>``
     - atoms exactly N bonds away from ``<filter>``
   * - ``exbonded N to <filter>``
     - same, excluding direct bonds to ``<filter>``

::
   bonded 1 to calpha
   exbonded 2 to name O

“Same As” & Sequence Patterns
-----------------------------

“Same As”
^^^^^^^^^

Capture the entire grouping (residue, chain, segment) that contains your seed selection:

::
   same residue as index 5       # whole residue of atom #5
   same chain as within 4 of water

.. tip::
   Use case: grab all sidechains around a catalytic metal.

Sequence Matching
^^^^^^^^^^^^^^^^^

Works on consecutive residues:

.. list-table:: Sequence Patterns
   :widths: 30 70
   :header-rows: 1

   * - Syntax
     - Meaning
   * - ``sequence "MIEIK"``
     - literal exact five-letter stretch
   * - ``sequence "^S[A-Z]{2}G"``
     - regex start-to-finish pattern
   * - ``sequence "."``
     - single-residue wildcard (any AA)
   * - ``sequence ".A.A."``
     - exactly 5 residues, A at positions 2 & 4

.. tip::
   - Use ``.`` for a single-residue wildcard, ``.*`` for any run.
   - Anchors ``^...$`` match the full sequence; omit for partial matches.

Putting It All Together
-----------------------

.. _putting-it-all-together:

Here’s how a real-world query might evolve:

1. **Start simple**

   ::
      resname ALA

2. **Add atom names**

   ::
      resname ALA and name CA CB

3. **Restrict by proximity**

   ::
      resname ALA name CA CB within 5 of water

4. **Exclude surface**

   ::
      resname ALA name CA CB within 5 of water and not surface

5. **Finalize with math**

   ::
      (resname ALA name CA CB within 5 of water) and sqrt(x**2+y**2+z**2) < 50

Feel free to mix flags, fields, math, spatial and sequence until your selection is laser-focused!

Pro Tips
--------

- See :ref:`putting-it-all-together` for a full walkthrough of building a complex query.
- Use the glossary for all field/category details.
- Try visualizing a PDB snippet with selected atoms (schematic coming soon).

Troubleshooting
---------------

.. tip::
   - Forgetting quotes: ``name A 1`` → two filters, not one.
   - Over-quoting regex: use double-quotes for regex, not backticks.
   - Mixing steps: ``1:4:2`` vs ``1 to 4`` (inclusive vs step).
   - Purely numeric math expressions (e.g. ``sqrt(25) < 10``) are not valid masks.

:ref:`macros` | :ref:`variables` | :ref:`putting-it-all-together`


