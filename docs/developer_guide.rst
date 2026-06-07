Developer Guide
===============

This page details how to contribute to MolSelect.

TODO
----
[ ] Add test for recursive macro expansion.
[ ] Add handling for non default units
[ ] Use prody residue conventions for aliphatic, cyclic, etc including non-native aminoacids
[ ] Add methods to compute secondary structure
[ ] Add ability to handle "_" as a synonym for ""
[ ] Add ability to handle nan values in equations with comparisons


Implementing a fast path for sequence selection
-----------------------------------------------

``SequenceSelection.evaluate()`` builds 1-letter sequences by iterating atoms
in Python. This is backend-agnostic but slow for large structures. Backends can
provide an optional ``get_sequence(sequence_map)`` method to bypass the generic
loop.

**Contract:**

.. code-block:: python

    def get_sequence(self, sequence_map: dict[str, str]) -> dict[str, tuple[str, list[int]]]:
        """Build per-chain 1-letter sequences from residue names.

        Args:
            sequence_map: mapping of residue name -> 1-letter code.
                          Residues not in the map are skipped.

        Returns:
            dict mapping chain_id -> (sequence_string, residue_indices)
            where residue_indices[i] is the ``residue`` column value
            corresponding to sequence_string[i].
        """

**Example implementation for PandasStructure:**

.. code-block:: python

    def get_sequence(self, sequence_map):
        first = self.df.groupby(['chain', 'residue'], sort=False)['resname'].first()
        result = {}
        for (chain, res_idx), resname in first.items():
            code = sequence_map.get(resname.strip())
            if code is None:
                continue
            if chain not in result:
                result[chain] = ([], [])
            result[chain][0].append(code)
            result[chain][1].append(res_idx)
        return {k: (''.join(chars), indices) for k, (chars, indices) in result.items()}

This method is **not part of the Structure protocol** — it is an optional
optimization. ``SequenceSelection`` checks for it with
``hasattr(s, 'get_sequence')`` and falls back to the generic atom loop if
absent. Backends are not required to implement it.




