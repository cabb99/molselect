import pytest
from molselect.python.parser import SelectionParser

@pytest.fixture
def parser():
    return SelectionParser()

def test_parse_valid_expression(parser):
    expr = "protein and (resid 10 to 20)"
    tree = parser.parse(expr)
    assert tree is not None
    assert tree.data in ('start', 'expr')

def test_parse_invalid_expression(parser):
    expr = "this is not valid syntax"
    with pytest.raises(Exception):
        parser.parse(expr)

def test_expand_macro_existing(parser):
    # Use a macro that is expected to exist, e.g., 'protein' or any from macros_dict
    macro_names = list(parser.macros_dict.keys())
    if macro_names:
        macro = macro_names[0]
        expanded = parser.expand_macro(macro)
        assert isinstance(expanded, str)
    else:
        pytest.skip("No macros available to test.")

def test_expand_macro_nonexistent(parser):
    with pytest.raises(ValueError):
        parser.expand_macro("nonexistent_macro")
