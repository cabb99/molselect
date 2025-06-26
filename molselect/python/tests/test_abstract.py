import pytest
import math
import numpy as np
import pandas as pd
from molselect.python import abstract
from molselect.python.backends.pandas import PandasStructure, PandasArray

# Minimal mock Array/Mask implementation
class MockArray:
    def __init__(self, data, index=None, name=None):
        self.data = list(data)
        self.index = list(index) if index is not None else list(range(len(data)))
        self.name = name
    def __and__(self, other):
        return MockArray([a and b for a, b in zip(self.data, other.data)], self.index)
    def __or__(self, other):
        return MockArray([a or b for a, b in zip(self.data, other.data)], self.index)
    def __xor__(self, other):
        return MockArray([bool(a) ^ bool(b) for a, b in zip(self.data, other.data)], self.index)
    def __invert__(self):
        return MockArray([not a for a in self.data], self.index)
    def __eq__(self, other):
        if isinstance(other, MockArray):
            return MockArray([a == b for a, b in zip(self.data, other.data)], self.index)
        return MockArray([a == other for a in self.data], self.index)
    def __ne__(self, other):
        if isinstance(other, MockArray):
            return MockArray([a != b for a, b in zip(self.data, other.data)], self.index)
        return MockArray([a != other for a in self.data], self.index)
    def __lt__(self, other):
        if isinstance(other, MockArray):
            return MockArray([a < b for a, b in zip(self.data, other.data)], self.index)
        return MockArray([a < other for a in self.data], self.index)
    def __le__(self, other):
        if isinstance(other, MockArray):
            return MockArray([a <= b for a, b in zip(self.data, other.data)], self.index)
        return MockArray([a <= other for a in self.data], self.index)
    def __gt__(self, other):
        if isinstance(other, MockArray):
            return MockArray([a > b for a, b in zip(self.data, other.data)], self.index)
        return MockArray([a > other for a in self.data], self.index)
    def __ge__(self, other):
        if isinstance(other, MockArray):
            return MockArray([a >= b for a, b in zip(self.data, other.data)], self.index)
        return MockArray([a >= other for a in self.data], self.index)
    def __add__(self, other):
        if isinstance(other, MockArray):
            return MockArray([a + b for a, b in zip(self.data, other.data)], self.index)
        return MockArray([a + other for a in self.data], self.index)
    def __sub__(self, other):
        if isinstance(other, MockArray):
            return MockArray([a - b for a, b in zip(self.data, other.data)], self.index)
        return MockArray([a - other for a in self.data], self.index)
    def __mul__(self, other):
        if isinstance(other, MockArray):
            return MockArray([a * b for a, b in zip(self.data, other.data)], self.index)
        return MockArray([a * other for a in self.data], self.index)
    def __truediv__(self, other):
        if isinstance(other, MockArray):
            return MockArray([a / b for a, b in zip(self.data, other.data)], self.index)
        return MockArray([a / other for a in self.data], self.index)
    def __floordiv__(self, other):
        if isinstance(other, MockArray):
            return MockArray([a // b for a, b in zip(self.data, other.data)], self.index)
        return MockArray([a // other for a in self.data], self.index)
    def __mod__(self, other):
        if isinstance(other, MockArray):
            return MockArray([a % b for a, b in zip(self.data, other.data)], self.index)
        return MockArray([a % other for a in self.data], self.index)
    def __pow__(self, other):
        if isinstance(other, MockArray):
            return MockArray([a ** b for a, b in zip(self.data, other.data)], self.index)
        return MockArray([a ** other for a in self.data], self.index)
    def __neg__(self):
        return MockArray([-a for a in self.data], self.index)
    def astype(self, dtype):
        if dtype == str:
            return MockArray([str(a) for a in self.data], self.index)
        if dtype == bool:
            return MockArray([bool(a) for a in self.data], self.index)
        return self
    def copy(self):
        return MockArray(self.data[:], self.index[:], self.name)
    def set_by_index(self, index, value):
        # Return a new MockArray with updated values
        new_data = self.data[:]
        for i, idx in enumerate(index):
            pos = self.index.index(idx)
            if isinstance(value, MockArray):
                new_data[pos] = value.data[i]
            else:
                new_data[pos] = value
        return MockArray(new_data, self.index, self.name)
    @classmethod
    def filled(cls, value, index):
        return cls([value] * len(index), index)
    def all(self):
        return all(self.data)
    def any(self):
        return any(self.data)
    def isin(self, values):
        return MockArray([v in values for v in self.data], self.index)
    def unique(self):
        return list(set(self.data))
    # def str_contains(self, pattern, regex=True):
    #     import re
    #     regex_obj = re.compile(pattern) if regex else None
    #     if regex:
    #         return MockArray([bool(regex_obj.search(str(x))) for x in self.data], self.index)
    #     else:
    #         return MockArray([pattern in str(x) for x in self.data], self.index)
    def __getitem__(self, idx):
        if isinstance(idx, MockArray):
            return MockArray([d for d, m in zip(self.data, idx.data) if m], [i for i, m in zip(self.index, idx.data) if m])
        if isinstance(idx, list):
            return MockArray([self.data[i] for i in idx], [self.index[i] for i in idx])
        return self.data[idx]
    def __repr__(self):
        return f"MockArray({self.data})"

# Minimal mock Structure
class MockStructure:
    def __init__(self, df, index=None):
        self.df = df
        self.index = list(index) if index is not None else list(range(len(df['a'])))
        self.columns = list(df.keys())
    def get_property(self, key):
        if key == 'index':
            return MockArray(self.index, self.index, name='index')
        return MockArray(self.df[key], self.index)
    def select(self, mask):
        # mask is a MockArray of bools
        selected = {k: [v for v, m in zip(self.df[k], mask.data) if m] for k in self.df}
        new_index = [i for i, m in zip(self.index, mask.data) if m]
        # 3) construct a new MockStructure with the same indices
        return MockStructure(selected, index=new_index)
    def get_coordinates(self, columns):
        # Return a numpy-like array for spatial tests
        import numpy as np
        arr = np.array([[self.df[c][i] for c in columns] for i in self.index])
        return arr
    def len(self):
        return len(self.index)
    def array_filled(self, value):
        return MockArray.filled(value, self.index)
    def array_values(self, values):
        return MockArray(values, index=self.index)
    def equals(self, other):
        # Helper for test: compare .df dicts
        return self.df == other.df
    def minimum_pairwise_distances(self, target):
        import numpy as np
        coords1 = self.get_coordinates(['x', 'y', 'z'])
        coords2 = target.get_coordinates(['x', 'y', 'z'])
        d2 = ((coords1[:, None, :] - coords2[None, :, :]) ** 2).sum(axis=2)
        return MockArray((d2 ** 0.5).min(axis=1), index=self.index)

@pytest.fixture(params=["mock", "pandas"])
def structure(request):
    df = {
        'a': [1, 2, 3, 4],
        'b': [4, 3, 2, 1],
        'x': [0.0, 1.0, 0.0, 1.0],
        'y': [0.0, 0.0, 1.0, 1.0],
        'z': [0.0, 0.0, 0.0, 0.0],
        's': ['foo', 'bar', 'foo', 'baz'],
    }
    if request.param == "mock":
        return MockStructure(df)
    else:
        return PandasStructure(pd.DataFrame(df))

@pytest.fixture
def LiteralMask(request, structure):
    if isinstance(structure, PandasStructure):
        class _LiteralMask(abstract.Node):
            def __init__(self, mask):
                self.mask = mask
            def evaluate(self, s):
                return PandasArray(self.mask, index=s.index)
        return _LiteralMask
    else:
        class _LiteralMask(abstract.Node):
            def __init__(self, mask):
                self.mask = mask
            def evaluate(self, s):
                # Return the mask on the same index as the structure
                return MockArray([d for i,d in zip(self.mask.index,self.mask.data) if i in s.index], index=s.index)
        return _LiteralMask

@pytest.fixture
def Field():
    class _Field(abstract.Node):
        def __init__(self, name):
            self.name = name
        def evaluate(self, s):
            return s.get_property(self.name)
    return _Field

@pytest.fixture
def LiteralValue():
    class _LiteralValue(abstract.Node):
        def __init__(self, value):
            self.value = value
        def evaluate(self, s):
            return self.value
    return _LiteralValue

@pytest.fixture
def array_type(structure):
    if isinstance(structure, PandasStructure):
        return PandasArray
    else:
        return MockArray

# 1. Logical nodes
def test_logical_nodes(structure, LiteralMask, array_type):
    s = structure
    mask1 = array_type([True, False, True, False], index=s.index)
    mask2 = array_type([False, True, True, False], index=s.index)
    result_and = abstract.And(LiteralMask(mask1), LiteralMask(mask2)).evaluate(s)
    result_or = abstract.Or(LiteralMask(mask1), LiteralMask(mask2)).evaluate(s)
    result_xor = abstract.Xor(LiteralMask(mask1), LiteralMask(mask2)).evaluate(s)
    result_not = abstract.Not(LiteralMask(mask1)).evaluate(s)
    expected_and = (mask1 & mask2)
    expected_or = (mask1 | mask2)
    expected_xor = (mask1 ^ mask2)
    expected_not = (~mask1)
    assert (result_and == expected_and).all()
    assert (result_or == expected_or).all()
    assert (result_xor == expected_xor).all()
    assert (result_not == expected_not).all()
    assert abstract.All().evaluate(s).all()
    assert not abstract.None_().evaluate(s).any()

# 2. Selections
def test_comparison(structure, Field):
    s = structure
    node = abstract.Comparison(field=Field('a'), op='>', value=2)
    result = node.evaluate(s)
    expected = s.get_property('a') > 2
    assert (result == expected).all()

def test_property_selection(structure, Field):
    s = structure
    node = abstract.PropertySelection(
        field=Field('s'),
        values=[abstract.StringValue('foo'), abstract.StringValue('baz')]
    )
    result = node.evaluate(s)
    expected = s.get_property('s').isin(['foo', 'baz'])
    assert (result == expected).all()

def test_regex(structure, Field, LiteralValue, array_type):
    s = structure
    node = abstract.Regex(field=Field('s'), pattern=LiteralValue('ba.'))
    result = node.evaluate(s)
    col = s.get_property('s').astype(str)
    if hasattr(col, 'str_contains'):
        expected = col.str_contains('ba.', regex=True)
    elif hasattr(col, 'str'):
        expected = col.str.contains('ba.', regex=True)
    else:
        import re
        regex = re.compile('ba.')
        values = getattr(col, 'data', None) or getattr(col, 'values', None) or list(col)
        expected = type(col)([bool(regex.search(x)) for x in values], col.index)
    assert (result == expected).all()

def test_within(structure, LiteralMask, LiteralValue, array_type):
    s = structure
    mask_node = LiteralMask(array_type([True, False, False, False], index=s.index))
    node = abstract.Within(distance=LiteralValue(1.0), target_mask=mask_node)
    result = node.evaluate(s)
    if isinstance(result, PandasArray):
        assert result.iloc[0] == True
        assert result.iloc[1] == True
        assert result.iloc[2] == True
        assert result.iloc[3] == False
    else:
        assert result[0] == True
        assert result[1] == True
        assert result[2] == True
        assert result[3] == False

def test_same(structure, Field, LiteralMask, array_type):
    s = structure
    node = abstract.Same(field=Field('s'), mask=LiteralMask(array_type([True, False, False, True], index=s.index)))
    result = node.evaluate(s)
    expected = s.get_property('s').isin(['foo', 'baz'])
    assert (result == expected).all()

def test_selection_keyword(structure, array_type):
    s = structure
    node = abstract.SelectionKeyword(name='a')
    result = node.evaluate(s)
    expected = s.get_property('a')
    assert (result == expected).all()
    node_index = abstract.SelectionKeyword(name='index')
    result_index = node_index.evaluate(s)
    if isinstance(result_index, PandasArray):
        expected_index = PandasArray(s.index, index=s.index, name='index')
    else:
        expected_index = MockArray(s.index, name='index', index=s.index)
    assert (result_index == expected_index).all()

def test_range_value(structure, LiteralValue):
    s = structure
    node = abstract.RangeValue(start=LiteralValue(1), end=LiteralValue(3), step=LiteralValue(1))
    assert node.evaluate(s) == (1, 3, 1)

def test_string_values(structure):
    s = structure
    assert abstract.StringValue('foo').evaluate(s) == 'foo'
    assert abstract.QuotedStringValue('"foo"').evaluate(s) == 'foo'
    assert abstract.RegexValue('ba.').evaluate(s) == 'ba.'

# 3. Math nodes
def test_math_nodes(structure, Field):
    s = structure
    node_add = abstract.Add(left=Field('a'), right=Field('b'))
    node_sub = abstract.Sub(left=Field('a'), right=Field('b'))
    node_mul = abstract.Mul(left=Field('a'), right=Field('b'))
    node_div = abstract.Div(left=Field('a'), right=Field('b'))
    node_floordiv = abstract.FloorDiv(left=Field('a'), right=Field('b'))
    node_mod = abstract.Mod(left=Field('a'), right=Field('b'))
    node_pow = abstract.Pow(left=Field('a'), right=Field('b'))
    node_neg = abstract.Neg(value=Field('a'))
    assert (node_add.evaluate(s) == (s.get_property('a') + s.get_property('b'))).all()
    assert (node_sub.evaluate(s) == (s.get_property('a') - s.get_property('b'))).all()
    assert (node_mul.evaluate(s) == (s.get_property('a') * s.get_property('b'))).all()
    assert (node_div.evaluate(s) == (s.get_property('a') / s.get_property('b'))).all()
    assert (node_floordiv.evaluate(s) == (s.get_property('a') // s.get_property('b'))).all()
    assert (node_mod.evaluate(s) == (s.get_property('a') % s.get_property('b'))).all()
    assert (node_pow.evaluate(s) == (s.get_property('a') ** s.get_property('b'))).all()
    assert (node_neg.evaluate(s) == (-s.get_property('a'))).all()

def test_func_number_const(structure, LiteralValue):
    s = structure
    node_func = abstract.Func(name='abs', arg=LiteralValue(-5))
    assert node_func.evaluate(s) == 5
    node_sq = abstract.Func(name='sq', arg=LiteralValue(3))
    assert node_sq.evaluate(s) == 9
    node_number = abstract.Number(value='3.14')
    assert node_number.evaluate(s) == 3.14
    node_const_pi = abstract.Const(name='pi')
    assert math.isclose(node_const_pi.evaluate(s), math.pi)
    node_const_e = abstract.Const(name='e')
    assert math.isclose(node_const_e.evaluate(s), math.e)
    with pytest.raises(ValueError):
        abstract.Const(name='unknown').evaluate(s)

# 4. Macro, Start, NotImplemented nodes
def test_macro_start(structure):
    s = structure
    start = abstract.Start(expr=abstract.All())
    assert start.evaluate(s).len() == s.len()

def test_notimplemented_nodes(structure):
    s = structure
    with pytest.raises(NotImplementedError):
        abstract.Bonded(distance=1.0, selection=abstract.All()).evaluate(s)
    with pytest.raises(NotImplementedError):
        abstract.SequenceSelectionRegex(pattern='A').evaluate(s)
    with pytest.raises(NotImplementedError):
        abstract.SequenceSelection(sequence='A').evaluate(s)
