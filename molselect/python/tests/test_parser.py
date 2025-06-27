import pytest
from molselect.python.parser import SelectionParser

@pytest.fixture(scope="module")
def module_parser():
    return SelectionParser()

@pytest.fixture(scope="function")
def parser(module_parser):
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

def load_selection_queries():
    import os
    import json
    jsonc_path = os.path.join(os.path.dirname(__file__), "selection_tests.jsonc")
    with open(jsonc_path, "r") as f:
        lines = f.readlines()
    clean_lines = [line for line in lines if not line.lstrip().startswith("//")]
    clean_json = "".join(clean_lines)
    selection_tests = json.loads(clean_json)
    return [test["query"] for test in selection_tests]

@pytest.mark.parametrize("selection", load_selection_queries())
def test_parse_single_selection(module_parser, selection):
    """Test parsing a single selection query."""
    module_parser.parse(selection)

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])


