import pytest
from lark import Tree, Token
from molselect.python.builder import ASTBuilder
from molselect.python.abstract import (
    And, Or, Not, Xor,
    Comparison, RangeValue as Range, Regex, PropertySelection,
    Number, Const, SelectionKeyword
)

def test_number_builder():
    tok = Token('NUMBER', '42')
    node = ASTBuilder().number(tok)
    assert isinstance(node, Number)
    assert node.value == '42'

def test_const_builder():
    tok = Token('CONST', 'pi')
    node = ASTBuilder().const(tok)
    assert isinstance(node, Const)
    assert node.name == 'pi'

def test_selection_keyword_builder():
    tok = Token('NAME', 'mass')
    node = ASTBuilder().selection_keyword(tok)
    assert isinstance(node, SelectionKeyword)
    assert node.name == 'mass'

def test_and_builder():
    left = SelectionKeyword('a')
    right = SelectionKeyword('b')
    node = ASTBuilder().and_(left, right)
    assert isinstance(node, And)
    assert node.left is left and node.right is right

def test_or_builder():
    L, R = SelectionKeyword('x'), SelectionKeyword('y')
    node = ASTBuilder().or_(L, R)
    assert isinstance(node, Or)
    assert node.left is L and node.right is R

def test_not_builder():
    expr = SelectionKeyword('flag')
    node = ASTBuilder().not_(expr)
    assert isinstance(node, Not)
    assert node.expr is expr

def test_xor_builder():
    A, B = SelectionKeyword('p'), SelectionKeyword('q')
    node = ASTBuilder().xor_(A, B)
    assert isinstance(node, Xor)
    assert node.left is A and node.right is B

def test_comparison_builder():
    field_node = SelectionKeyword('mass')
    op_tok     = Token('GT','>')
    value_node = Number('5')
    cmp = ASTBuilder().comparison(field_node, op_tok, value_node)
    assert isinstance(cmp, Comparison)
    assert cmp.op == '>' and cmp.value is value_node
    assert cmp.field == 'mass'

def test_range_builder():
    name, st, en, sp = SelectionKeyword('i'), Number('1'), Number('10'), Number('2')
    rng = ASTBuilder().range_value(st, en, sp)
    assert isinstance(rng, Range)
    assert rng.start is st and rng.end is en and rng.step is sp

def test_number_range_builder():
    st, en = Number('0'), Number('4')
    rng = ASTBuilder().range_value(st, en)
    assert isinstance(rng, Range)
    assert rng.start is st and rng.end is en and rng.step is None

def test_property_selection_builder():
    name = SelectionKeyword('name')
    v1, v2 = Number('1'), Number('2')
    prop = ASTBuilder().property_selection(name, v1, v2)
    assert isinstance(prop, PropertySelection)
    assert prop.field is name
    assert prop.values == [v1, v2]

def test_macro_builder():
    # This test now checks that macro expansion returns the correct AST, not a Macro node
    builder = ASTBuilder()  # Uses default parser with macros loaded
    tok = Token('NAME', 'heme')
    node = builder.macro(tok)
    # The 'heme' macro expands to 'resname HEM HEME', which should be a PropertySelection node
    from molselect.python.abstract import PropertySelection
    assert isinstance(node, PropertySelection)
    # Optionally, check the field and values
    assert getattr(node.field, 'name', None) == 'resname'
    values = [getattr(v, 'value', None) for v in node.values]
    assert 'HEM' in values and 'HEME' in values

def test_to_node_with_tree():
    subtree = Tree('number', [Token('NUMBER','7')])
    builder = ASTBuilder()
    node = builder._to_node(subtree)
    assert isinstance(node, Number)
    assert node.value == '7'
