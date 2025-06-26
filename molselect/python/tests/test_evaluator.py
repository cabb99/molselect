import pytest
import pandas as pd
from molselect.python.evaluator import Evaluator
from molselect.python.builder import ASTBuilder
from molselect.python.parser import SelectionParser
from molselect.python.backends.pandas import PandasStructure

@pytest.fixture
def example_dataframe():
    data = {
        'x': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        'y': [4, 5, 6, 7, 8, 9, 10, 11, 12, 13],
        'z': [7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
        'name': ['CA', 'CB', 'N', 'O', 'FE', 'CA', 'CB', 'O', 'N', 'H'],
        'mass': [12.0, 13.0, 14.0, 16.0, 55.8, 12.0, 13.0, 16.0, 14.0, 1.0],
        'resid': [1, 1, 2, 2, 3, 4, 4, 5, 5, 6],
        'resname': ['ALA', 'ALA', 'GLY', 'GLY', 'HEM', 'PHE', 'PHE', 'HOH', 'HOH', 'GLU'],
        'element': ['C', 'C', 'N', 'O', 'Fe', 'C', 'C', 'O', 'N', 'H'],
    }
    return pd.DataFrame(data)

@pytest.fixture
def evaluator(example_dataframe):
    parser = SelectionParser()
    builder = ASTBuilder(parser)
    backend = PandasStructure(example_dataframe)
    return Evaluator(backend, parser=parser, builder=builder)

@pytest.mark.parametrize("description, sel", [
    ("Simple flag: protein", "protein"),
    ("Simple field: name CA", "name CA"),
    ("Multiple names", "name CA CB"),
    ("Residue id", "resid 4"),
    ("AND logic", "protein and water"),
    ("OR logic", "protein or water"),
    ("NOT logic", "not water"),
    ("Numeric comparison", "mass>12"),
    ("Range selection", "resid 1 to 4"),
    ("Python-style range", "resid 1:4"),
    ("Quotes test 1", "name CA and resname ALA"),
    ("Quotes test 2", 'name "CA" and resname ALA'),
    ("Regex on name", 'name =~ "C.*"'),
    ("Within distance", "within 5 of water"),
    ("Same residue as", "same resid as exwithin 4 of water"),
    ("Complex selection", "protein and (resname ALA or resname GLY) and not water"),
])
def test_evaluator_cases(evaluator, description, sel):
    parser = evaluator.parser
    builder = evaluator.builder
    tree = parser.parse(sel, start_rule='start')
    ast = builder.transform(tree)
    symbolic = evaluator.symbolic(ast)
    result = evaluator.evaluate(ast)
    assert symbolic is not None
    assert result is not None
    
