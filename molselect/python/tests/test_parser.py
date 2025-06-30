import pytest
from molselect.python.parser import SelectionParser
from molselect.python.errors import *

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
    with pytest.raises(MolSelectMacroError):
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
    assert parser.expand_macro("testmacro") == "(resid 1)"
    # Synonyms should also expand
    assert parser.expand_macro("tm") == "(resid 1)"
    assert parser.expand_macro("testm") == "(resid 1)"
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

def test_add_and_remove_keyword(parser):
    # Add a keyword
    parser.set_keyword(
        keyword_name="testkw",
        definition="1",
        synonyms=["tkw", "testk"],
        category="testcat",
    )
    # Should parse using the new keyword in a property selection context
    tree = parser.parse("testkw 1")
    assert tree.data == 'start'
    # Find property_selection in the tree
    prop_sel = tree.children[0]
    assert prop_sel.data == 'property_selection'
    sel_kw = prop_sel.children[0]
    assert sel_kw.data == 'selection_keyword'
    assert sel_kw.children[0].type == 'TESTKW'
    assert sel_kw.children[0].value == 'testkw'
    # Should also parse using synonyms
    tree_tkw = parser.parse("tkw 1")
    prop_sel_tkw = tree_tkw.children[0]
    sel_kw_tkw = prop_sel_tkw.children[0]
    assert sel_kw_tkw.data == 'selection_keyword'
    assert sel_kw_tkw.children[0].type == 'TESTKW'
    assert sel_kw_tkw.children[0].value == 'tkw'
    tree_testk = parser.parse("testk 1")
    prop_sel_testk = tree_testk.children[0]
    sel_kw_testk = prop_sel_testk.children[0]
    assert sel_kw_testk.data == 'selection_keyword'
    assert sel_kw_testk.children[0].type == 'TESTKW'
    assert sel_kw_testk.children[0].value == 'testk'
    # Remove the keyword
    parser.remove_keyword("testkw", category="testcat")
    import pytest
    with pytest.raises(Exception):
        parser.parse("testkw 1")
    with pytest.raises(Exception):
        parser.parse("tkw 1")
    with pytest.raises(Exception):
        parser.parse("testk 1")

def test_macro_circular_reference(parser):
    # Add three macros with circular references
    parser.set_macro("A", definition="B", category="circ")
    parser.set_macro("B", definition="C", category="circ")
    parser.set_macro("C", definition="A", category="circ")
    # Expanding any of them should raise a ValueError for circular reference
    import pytest
    with pytest.raises(MolSelectMacroError):
        parser.expand_macro("A")
        print("Expanded A:", parser.expand_macro("A"))
    with pytest.raises(MolSelectMacroError):
        parser.expand_macro("B")
        print("Expanded B:", parser.expand_macro("B"))
    with pytest.raises(MolSelectMacroError):
        parser.expand_macro("C")
        print("Expanded C:", parser.expand_macro("C"))

    parser.set_macro("A", definition="B or C", category="circ")
    parser.set_macro("B", definition="C", category="circ")
    parser.set_macro("C", definition="none", category="circ")

    # Expanding D should not raise an error, as it does not create a circular reference
    expanded_d = parser.expand_macro("A")
    assert expanded_d == "(((none)) or (none))"

    
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


