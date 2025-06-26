import pytest
import math
import numpy as np
import pandas as pd
from molselect.python import abstract
from molselect.python.backends.pandas import PandasStructure, PandasArray
from molselect.python.backends.pure import PureArray, PureStructure
from molselect.python.backends.biopython import BiopythonArray, BiopythonStructure

@pytest.fixture(params=["pure", "pandas", "biopython"])
def structure(request):
    df = {
        'a': [1, 2, 3, 4],
        'b': [4, 3, 2, 1],
        'x': [0.0, 1.0, 0.0, 1.0],
        'y': [0.0, 0.0, 1.0, 1.0],
        'z': [0.0, 0.0, 0.0, 0.0],
        's': ['foo', 'bar', 'foo', 'baz'],
    }
    if request.param == "pure":
        return PureStructure(df)
    elif request.param == "biopython":
        # Create a mock Biopython Structure for testing
        from Bio.PDB import Structure, Model, Chain, Residue, Atom
        struct = Structure.Structure("test")
        model = Model.Model(0)
        chain = Chain.Chain("A")
        for i in range(4):
            res = Residue.Residue((" ", i+1, " "), "GLY", " ")
            atom = Atom.Atom("CA", [df['x'][i], df['y'][i], df['z'][i]], 1.0, 1.0, " ", "CA", i, "C")  # serial number = i
            # Add extra test fields as attributes for extraction
            atom.a = df['a'][i]
            atom.b = df['b'][i]
            atom.s = df['s'][i]
            res.add(atom)
            chain.add(res)
        model.add(chain)
        struct.add(model)
        return BiopythonStructure(struct)
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
    elif isinstance(structure, BiopythonStructure):
        class _LiteralMask(abstract.Node):
            def __init__(self, mask):
                self.mask = mask
            def evaluate(self, s):
                return BiopythonArray(self.mask, index=s.index)
        return _LiteralMask
    else:
        class _LiteralMask(abstract.Node):
            def __init__(self, mask):
                self.mask = mask
            def evaluate(self, s):
                return PureArray([d for i,d in zip(self.mask.index,self.mask.data) if i in s.index], index=s.index)
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
    elif isinstance(structure, BiopythonStructure):
        return BiopythonArray
    else:
        return PureArray

# 1. Logical nodes
def test_logical_nodes(structure, LiteralMask, array_type):
    s = structure
    # Test several mask scenarios
    mask_cases = [
        ([True, False, True, False], [False, True, True, False]),
        ([True, True, True, True], [False, False, False, False]),
        ([False, False, False, False], [True, True, True, True]),
        ([False, False, False, False], [False, False, False, False]),
        ([True, True, False, False], [False, True, True, False]),
    ]
    for mask1_vals, mask2_vals in mask_cases:
        mask1 = array_type(mask1_vals, index=s.index)
        mask2 = array_type(mask2_vals, index=s.index)
        result_and = abstract.And(LiteralMask(mask1), LiteralMask(mask2)).evaluate(s)
        result_or = abstract.Or(LiteralMask(mask1), LiteralMask(mask2)).evaluate(s)
        result_xor = abstract.Xor(LiteralMask(mask1), LiteralMask(mask2)).evaluate(s)
        result_not = abstract.Not(LiteralMask(mask1)).evaluate(s)
        # Use numpy for expected logic
        mask1_np = np.array(mask1_vals)
        mask2_np = np.array(mask2_vals)
        expected_and = mask1_np & mask2_np
        expected_xor = mask1_np ^ mask2_np
        expected_not = ~mask1_np
        # AST short-circuit logic for OR
        expected_or = np.ones_like(mask1_np, dtype=bool)
        expected_or[~mask1_np] = mask2_np[~mask1_np]
        # Get result arrays
        def get_arr(x):
            if hasattr(x, 'data'):
                return np.array(x.data)
            elif hasattr(x, 'values'):
                return np.array(x.values)
            else:
                return np.array(x)
        assert np.all(get_arr(result_and) == expected_and)
        assert np.all(get_arr(result_or) == expected_or)
        assert np.all(get_arr(result_xor) == expected_xor)
        assert np.all(get_arr(result_not) == expected_not)
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
        expected_index = PureArray(s.index, name='index', index=s.index)
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
