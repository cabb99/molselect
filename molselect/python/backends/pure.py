# Pure Python backend for molselect

class PureArray:
    def __init__(self, data, index=None, name=None):
        self.data = list(data)
        self.index = list(index) if index is not None else list(range(len(data)))
        self.name = name
    def __and__(self, other):
        return PureArray([a and b for a, b in zip(self.data, other.data)], self.index)
    def __or__(self, other):
        return PureArray([a or b for a, b in zip(self.data, other.data)], self.index)
    def __xor__(self, other):
        return PureArray([bool(a) ^ bool(b) for a, b in zip(self.data, other.data)], self.index)
    def __invert__(self):
        return PureArray([not a for a in self.data], self.index)
    def __eq__(self, other):
        if isinstance(other, PureArray):
            return PureArray([a == b for a, b in zip(self.data, other.data)], self.index)
        return PureArray([a == other for a in self.data], self.index)
    def __ne__(self, other):
        if isinstance(other, PureArray):
            return PureArray([a != b for a, b in zip(self.data, other.data)], self.index)
        return PureArray([a != other for a in self.data], self.index)
    def __lt__(self, other):
        if isinstance(other, PureArray):
            return PureArray([a < b for a, b in zip(self.data, other.data)], self.index)
        return PureArray([a < other for a in self.data], self.index)
    def __le__(self, other):
        if isinstance(other, PureArray):
            return PureArray([a <= b for a, b in zip(self.data, other.data)], self.index)
        return PureArray([a <= other for a in self.data], self.index)
    def __gt__(self, other):
        if isinstance(other, PureArray):
            return PureArray([a > b for a, b in zip(self.data, other.data)], self.index)
        return PureArray([a > other for a in self.data], self.index)
    def __ge__(self, other):
        if isinstance(other, PureArray):
            return PureArray([a >= b for a, b in zip(self.data, other.data)], self.index)
        return PureArray([a >= other for a in self.data], self.index)
    def __add__(self, other):
        if isinstance(other, PureArray):
            return PureArray([a + b for a, b in zip(self.data, other.data)], self.index)
        return PureArray([a + other for a in self.data], self.index)
    def __sub__(self, other):
        if isinstance(other, PureArray):
            return PureArray([a - b for a, b in zip(self.data, other.data)], self.index)
        return PureArray([a - other for a in self.data], self.index)
    def __mul__(self, other):
        if isinstance(other, PureArray):
            return PureArray([a * b for a, b in zip(self.data, other.data)], self.index)
        return PureArray([a * other for a in self.data], self.index)
    def __truediv__(self, other):
        if isinstance(other, PureArray):
            return PureArray([a / b for a, b in zip(self.data, other.data)], self.index)
        return PureArray([a / other for a in self.data], self.index)
    def __floordiv__(self, other):
        if isinstance(other, PureArray):
            return PureArray([a // b for a, b in zip(self.data, other.data)], self.index)
        return PureArray([a // other for a in self.data], self.index)
    def __mod__(self, other):
        if isinstance(other, PureArray):
            return PureArray([a % b for a, b in zip(self.data, other.data)], self.index)
        return PureArray([a % other for a in self.data], self.index)
    def __pow__(self, other):
        if isinstance(other, PureArray):
            return PureArray([a ** b for a, b in zip(self.data, other.data)], self.index)
        return PureArray([a ** other for a in self.data], self.index)
    def __neg__(self):
        return PureArray([-a for a in self.data], self.index)
    def astype(self, dtype):
        if dtype == str:
            return PureArray([str(a) for a in self.data], self.index)
        if dtype == bool:
            return PureArray([bool(a) for a in self.data], self.index)
        return self
    def copy(self):
        return PureArray(self.data[:], self.index[:], self.name)
    def set_by_index(self, index, value):
        new_data = self.data[:]
        for i, idx in enumerate(index):
            pos = self.index.index(idx)
            if isinstance(value, PureArray):
                new_data[pos] = value.data[i]
            else:
                new_data[pos] = value
        return PureArray(new_data, self.index, self.name)
    @classmethod
    def filled(cls, value, index):
        return cls([value] * len(index), index)
    def all(self):
        return all(self.data)
    def any(self):
        return any(self.data)
    def isin(self, values):
        return PureArray([v in values for v in self.data], self.index)
    def unique(self):
        return list(set(self.data))
    def __getitem__(self, idx):
        if isinstance(idx, PureArray):
            return PureArray([d for d, m in zip(self.data, idx.data) if m], [i for i, m in zip(self.index, idx.data) if m])
        if isinstance(idx, list):
            return PureArray([self.data[i] for i in idx], [self.index[i] for i in idx])
        return self.data[idx]
    def __repr__(self):
        return f"PureArray({self.data})"

class PureStructure:
    def __init__(self, df, index=None):
        self.df = df
        self.index = list(index) if index is not None else list(range(len(df['a'])))
        self.columns = list(df.keys())
    def get_property(self, key):
        if key == 'index':
            return PureArray(self.index, self.index, name='index')
        return PureArray(self.df[key], self.index)
    def select(self, mask):
        selected = {k: [v for v, m in zip(self.df[k], mask.data) if m] for k in self.df}
        new_index = [i for i, m in zip(self.index, mask.data) if m]
        return PureStructure(selected, index=new_index)
    def get_coordinates(self, columns):
        # Return a list of lists for spatial tests (no numpy)
        return [[self.df[c][i] for c in columns] for i in self.index]

    def minimum_pairwise_distances(self, target):
        # Pure Python version of minimum pairwise distances
        coords1 = self.get_coordinates(['x', 'y', 'z'])
        coords2 = target.get_coordinates(['x', 'y', 'z'])
        def euclidean(p1, p2):
            return sum((a - b) ** 2 for a, b in zip(p1, p2)) ** 0.5
        min_dists = []
        for p1 in coords1:
            min_dist = min(euclidean(p1, p2) for p2 in coords2)
            min_dists.append(min_dist)
        return PureArray(min_dists, index=self.index)
    def len(self):
        return len(self.index)
    def array_filled(self, value):
        return PureArray.filled(value, self.index)
    def array_values(self, values):
        return PureArray(values, index=self.index)
    def equals(self, other):
        return self.df == other.df
