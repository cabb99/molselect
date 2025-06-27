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

def test_add_and_remove_macro(parser):
    # Add a macro
    parser.set_macro(
        macro_name="testmacro",
        definition="resid 1",
        synonyms=["tm", "testm"],
        category="testcat",
    )
    # Should be available for parsing and expansion
    assert "testmacro" in parser.macros_dict
    assert parser.expand_macro("testmacro") == "resid 1"
    # Synonyms should also expand
    assert parser.expand_macro("tm") == "resid 1"
    assert parser.expand_macro("testm") == "resid 1"
    # Should parse using the new macro
    tree = parser.parse("testmacro")
    
    # Check that the tree is a bool_keyword  testmacro
    # The tree format should be like this:
    # Tree('start', [Tree(Token('RULE', 'bool_keyword'), [Token('TESTMACRO', 'testmacro')])])
    assert tree.data == 'start'
    assert tree.children[0].data == 'bool_keyword'
    assert tree.children[0].children[0].type == 'TESTMACRO'
    assert tree.children[0].children[0].value == 'testmacro'

    #Should also parse using synonyms
    tree_tm = parser.parse("tm")
    assert tree_tm.data == 'start'
    assert tree_tm.children[0].data == 'bool_keyword'
    assert tree_tm.children[0].children[0].type == 'TESTMACRO'
    assert tree_tm.children[0].children[0].value == 'tm'

    # Remove the macro
    parser.remove_macro("testmacro", category="testcat")
    # Macro and synonyms should be gone
    assert "testmacro" not in parser.macros_dict
    assert "tm" not in parser.macros_dict
    assert "testm" not in parser.macros_dict
    # Parsing should now fail
    import pytest
    with pytest.raises(Exception):
        parser.parse("testmacro")
