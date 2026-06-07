.. _syntax-math:

Comparisons and Math
====================

Numeric fields (``x``, ``y``, ``z``, ``beta``, ``occupancy``, ``mass``, …) can be
filtered with comparison operators and combined with arithmetic and math
functions. Every operator and function below is covered by the
``comparison_math`` cases of the selection-contract test suite.

Comparison operators
--------------------

.. code-block:: text

   beta > 10
   beta < 10
   z >= 82.813
   occupancy <= 1
   occupancy == 1
   occupancy != 1
   name eq CA          # word form of ==
   residue ne 0        # word form of !=

Chained comparisons select a range in one expression:

.. code-block:: text

   20 <= x < 30        # equivalent to x >= 20 and x < 30

.. note::

   VMD does not support chained comparisons, so the contract compares them
   against an explicit ``and`` for VMD.

Arithmetic operators
--------------------

.. code-block:: text

   beta + 1 > 11
   beta - 1 > 9
   beta * 2 > 20
   beta / 2 > 5           # division
   beta % 3 < 1           # modulo
   x ** 2 < 10            # power (ProDy spells it x ^ 2)
   x^3 + y^3 + z^3 < 1000 # power
   beta // 3 >= 3         # floor division (MolSelect only)

.. note::

   ``**`` and ``^`` are both accepted for exponentiation (ProDy uses only
   ``^``). Floor division ``//`` is a MolSelect extension.

Math functions
--------------

The following functions are available and apply element-wise:

.. code-block:: text

   sin   cos   tan
   asin  acos  atan      (aliases: arcsin, arccos, arctan)
   sinh  cosh  tanh
   exp   log   log10     (alias: ln = log)
   sqrt  sq    sqr  square
   abs   floor ceil

Examples:

.. code-block:: text

   sqrt(x**2 + y**2 + z**2) < 100
   abs(x) > 5
   sin(x) > 0
   log10(x) > 1
   ceil(beta) == 10

.. note::

   Function-name spellings differ between engines (``sq`` in ProDy, ``sqr`` in
   VMD, ``square``/``sq``/``sqr`` in MolSelect; ``ln`` = ``log``;
   ``arcsin`` = ``asin``). The contract maps each MolSelect alias to the
   engine-native spelling. See :doc:`../Compatibility`.
