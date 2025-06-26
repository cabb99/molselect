# Biopython backend for molselect

class BiopythonArray:
    def __init__(self, data, index=None, name=None):
        import numpy as np
        # Handle if data is already a BiopythonArray or similar
        if hasattr(data, 'data') and hasattr(data, 'index'):
            if index is None:
                self.data = list(data.data)
                self.index = list(data.index)
            else:
                # Reindex data to match the provided index
                idx_map = {i: v for i, v in zip(data.index, data.data)}
                self.data = [idx_map.get(i, False) for i in index]
                self.index = list(index)
        else:
            if index is not None:
                index = list(index)
                data = list(data)
                # Sort by index to ensure consistent order
                order = np.argsort(index)
                self.index = [index[i] for i in order]
                self.data = [data[i] for i in order]
            else:
                self.data = list(data)
                self.index = list(range(len(self.data)))
        self.name = name

    def _align_with(self, other):
        # Returns (self_data, other_data, index) aligned by index (order of self.index)
        idx_map = {i: v for i, v in zip(other.index, other.data)}
        aligned_other = [idx_map.get(i, False) for i in self.index]
        return self.data, aligned_other, self.index

    def __and__(self, other):
        a, b, idx = self._align_with(other)
        result = [ai and bi for ai, bi in zip(a, b)]
        return BiopythonArray(result, idx)

    def __or__(self, other):
        # Short-circuit logic: if self True, result True; else use other's value (aligned)
        a, b, idx = self._align_with(other)
        result = [ai if ai else bi for ai, bi in zip(a, b)]
        return BiopythonArray(result, idx)

    def __xor__(self, other):
        a, b, idx = self._align_with(other)
        result = [bool(ai) ^ bool(bi) for ai, bi in zip(a, b)]
        return BiopythonArray(result, idx)

    def __invert__(self):
        return BiopythonArray([not a for a in self.data], self.index)

    def __eq__(self, other):
        if hasattr(other, 'data') and hasattr(other, 'index'):
            a, b, idx = self._align_with(other)
            result = [ai == bi for ai, bi in zip(a, b)]
            return BiopythonArray(result, idx)
        return BiopythonArray([a == other for a in self.data], self.index)

    def __ne__(self, other):
        if hasattr(other, 'data') and hasattr(other, 'index'):
            a, b, idx = self._align_with(other)
            result = [ai != bi for ai, bi in zip(a, b)]
            return BiopythonArray(result, idx)
        return BiopythonArray([a != other for a in self.data], self.index)

    def __lt__(self, other):
        if hasattr(other, 'data') and hasattr(other, 'index'):
            a, b, idx = self._align_with(other)
            result = [ai < bi for ai, bi in zip(a, b)]
            return BiopythonArray(result, idx)
        return BiopythonArray([a < other for a in self.data], self.index)

    def __le__(self, other):
        if hasattr(other, 'data') and hasattr(other, 'index'):
            a, b, idx = self._align_with(other)
            result = [ai <= bi for ai, bi in zip(a, b)]
            return BiopythonArray(result, idx)
        return BiopythonArray([a <= other for a in self.data], self.index)

    def __gt__(self, other):
        if hasattr(other, 'data') and hasattr(other, 'index'):
            a, b, idx = self._align_with(other)
            result = [ai > bi for ai, bi in zip(a, b)]
            return BiopythonArray(result, idx)
        return BiopythonArray([a > other for a in self.data], self.index)

    def __ge__(self, other):
        if hasattr(other, 'data') and hasattr(other, 'index'):
            a, b, idx = self._align_with(other)
            result = [ai >= bi for ai, bi in zip(a, b)]
            return BiopythonArray(result, idx)
        return BiopythonArray([a >= other for a in self.data], self.index)

    def __add__(self, other):
        if hasattr(other, 'data') and hasattr(other, 'index'):
            a, b, idx = self._align_with(other)
            result = [ai + bi for ai, bi in zip(a, b)]
            return BiopythonArray(result, idx)
        return BiopythonArray([a + other for a in self.data], self.index)

    def __sub__(self, other):
        if hasattr(other, 'data') and hasattr(other, 'index'):
            a, b, idx = self._align_with(other)
            result = [ai - bi for ai, bi in zip(a, b)]
            return BiopythonArray(result, idx)
        return BiopythonArray([a - other for a in self.data], self.index)

    def __mul__(self, other):
        if hasattr(other, 'data') and hasattr(other, 'index'):
            a, b, idx = self._align_with(other)
            result = [ai * bi for ai, bi in zip(a, b)]
            return BiopythonArray(result, idx)
        return BiopythonArray([a * other for a in self.data], self.index)

    def __truediv__(self, other):
        if hasattr(other, 'data') and hasattr(other, 'index'):
            a, b, idx = self._align_with(other)
            result = [ai / bi for ai, bi in zip(a, b)]
            return BiopythonArray(result, idx)
        return BiopythonArray([a / other for a in self.data], self.index)

    def __floordiv__(self, other):
        if hasattr(other, 'data') and hasattr(other, 'index'):
            a, b, idx = self._align_with(other)
            result = [ai // bi for ai, bi in zip(a, b)]
            return BiopythonArray(result, idx)
        return BiopythonArray([a // other for a in self.data], self.index)

    def __mod__(self, other):
        if hasattr(other, 'data') and hasattr(other, 'index'):
            a, b, idx = self._align_with(other)
            result = [ai % bi for ai, bi in zip(a, b)]
            return BiopythonArray(result, idx)
        return BiopythonArray([a % other for a in self.data], self.index)

    def __pow__(self, other):
        if hasattr(other, 'data') and hasattr(other, 'index'):
            a, b, idx = self._align_with(other)
            result = [ai ** bi for ai, bi in zip(a, b)]
            return BiopythonArray(result, idx)
        return BiopythonArray([a ** other for a in self.data], self.index)

    def __neg__(self):
        return BiopythonArray([-a for a in self.data], self.index)

    def astype(self, dtype):
        if dtype == str:
            return BiopythonArray([str(a) for a in self.data], self.index)
        if dtype == bool:
            return BiopythonArray([bool(a) for a in self.data], self.index)
        return self

    def copy(self):
        return BiopythonArray(self.data[:], self.index[:], self.name)

    def set_by_index(self, index, value):
        new_data = self.data[:]
        idx_map = {idx: i for i, idx in enumerate(self.index)}
        if hasattr(value, 'data') and hasattr(value, 'index'):
            value_map = {idx: v for idx, v in zip(value.index, value.data)}
            for idx in index:
                if idx in idx_map:
                    new_data[idx_map[idx]] = value_map.get(idx, False)
        else:
            for idx in index:
                if idx in idx_map:
                    new_data[idx_map[idx]] = value
        return BiopythonArray(new_data, self.index, self.name)

    @classmethod
    def filled(cls, value, index):
        return cls([value] * len(index), index)

    def all(self):
        return all(self.data)

    def any(self):
        return any(self.data)

    def isin(self, values):
        return BiopythonArray([v in values for v in self.data], self.index)

    def unique(self):
        return list(set(self.data))

    def __getitem__(self, idx):
        if hasattr(idx, 'data') and hasattr(idx, 'index'):
            # Masked selection
            return BiopythonArray([d for d, m in zip(self.data, idx.data) if m], [i for i, m in zip(self.index, idx.data) if m])
        if isinstance(idx, list):
            return BiopythonArray([self.data[i] for i in idx], [self.index[i] for i in idx])
        return self.data[idx]

    def __repr__(self):
        return f"BiopythonArray({self.data})"

from typing import Any, Sequence

def import_biopython():
    global Structure
    from Bio.PDB import Structure

class BiopythonStructure:
    def __init__(self, structure: Any):
        import_biopython()
        self.structure = structure
        self.index = [atom.get_serial_number() for atom in structure.get_atoms()]
        self.columns = ['name', 'resname', 'chain', 'x', 'y', 'z', 'bfactor', 'occupancy', 'element', 'a', 'b', 's']
        self.df = self._extract_atom_data()
    def _extract_atom_data(self):
        data = {col: [] for col in self.columns}
        data['a'] = []
        data['b'] = []
        data['s'] = []
        atoms = sorted(self.structure.get_atoms(), key=lambda atom: atom.get_serial_number())
        for atom in atoms:
            data['name'].append(atom.get_name())
            data['resname'].append(atom.get_parent().get_resname())
            data['chain'].append(atom.get_parent().get_parent().get_id())
            data['x'].append(atom.get_coord()[0])
            data['y'].append(atom.get_coord()[1])
            data['z'].append(atom.get_coord()[2])
            data['bfactor'].append(atom.get_bfactor())
            data['occupancy'].append(atom.get_occupancy())
            data['element'].append(atom.element)
            data['a'].append(getattr(atom, 'a', 0))
            data['b'].append(getattr(atom, 'b', 0))
            data['s'].append(getattr(atom, 's', ''))
        return data
    def get_property(self, key):
        if key == 'index':
            return BiopythonArray(self.index, self.index, name='index')
        return BiopythonArray(self.df[key], self.index)
    def select(self, mask):
        selected = {k: [v for v, m in zip(self.df[k], mask.data) if m] for k in self.df}
        new_index = [i for i, m in zip(self.index, mask.data) if m]
        new_struct = BiopythonStructure.__new__(BiopythonStructure)
        new_struct.structure = self.structure
        new_struct.df = selected
        new_struct.index = new_index
        new_struct.columns = self.columns
        return new_struct
    def get_coordinates(self, columns: Sequence[str]):
        return [[self.df[c][i] for c in columns] for i in range(len(self.index))]
    def minimum_pairwise_distances(self, target):
        coords1 = self.get_coordinates(['x', 'y', 'z'])
        coords2 = target.get_coordinates(['x', 'y', 'z'])
        def euclidean(p1, p2):
            return sum((a - b) ** 2 for a, b in zip(p1, p2)) ** 0.5
        min_dists = []
        for p1 in coords1:
            min_dist = min(euclidean(p1, p2) for p2 in coords2)
            min_dists.append(min_dist)
        return BiopythonArray(min_dists, index=self.index)
    def len(self):
        return len(self.index)
    def array_filled(self, value):
        return BiopythonArray([value] * len(self.index), self.index)
    def array_values(self, values):
        return BiopythonArray(values, index=self.index)
    def equals(self, other):
        return self.df == other.df
