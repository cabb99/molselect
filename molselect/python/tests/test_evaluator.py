import pytest
import pandas as pd
from molselect.python.evaluator import Evaluator
from molselect.python.builder import ASTBuilder
from molselect.python.parser import SelectionParser
from molselect.python.backends.pandas import PandasStructure
from molselect.python.errors import MolSelectEvaluationError

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
def evaluator():
    parser = SelectionParser()
    builder = ASTBuilder(parser)
    backend = PandasStructure
    return Evaluator(backend, parser=parser, builder=builder)

def _render(builder, sel):
    """Parse *sel* and return its symbolic() rendering."""
    return builder.parse(sel).symbolic()


def assert_round_trip(builder, sel):
    """symbolic() must emit valid syntax that re-parses to the *same AST*.

    This is the faithfulness invariant: rendering then re-parsing preserves the
    tree exactly (macros/synonyms already normalized by the first parse). It is
    strictly stronger than string idempotence and catches any precedence /
    grouping regression introduced when parentheses are removed.
    Returns the canonical rendering for further assertions.
    """
    ast = builder.parse(sel)
    r1 = ast.symbolic()
    ast2 = builder.parse(r1)  # also asserts r1 re-parses without error
    assert ast2 == ast, f"symbolic() not faithful for {sel!r}:\n  rendered: {r1!r}"
    assert ast2.symbolic() == r1, f"rendering not idempotent for {sel!r}:\n  {r1!r}"
    return r1


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
def test_evaluator_cases(evaluator, description, sel, example_dataframe):
    parser = evaluator.parser
    builder = evaluator.builder
    tree = parser.parse(sel, start_rule='start')
    ast = builder.transform(tree)
    symbolic = evaluator.symbolic(ast)
    result = evaluator.evaluate(ast,structure=evaluator.backend(example_dataframe))
    assert symbolic is not None
    assert result is not None
    # symbolic() must be valid, re-parseable, stable selection syntax.
    assert_round_trip(builder, sel)


@pytest.mark.parametrize("sel", [
    # boolean keywords / macros
    "all",
    "none",
    "protein",
    # fields, lists, ranges
    "name CA",
    "name CA CB",
    "resid 1 to 4",
    "resid 1:10:2",
    "resid 1 2 3 5 to 9",
    "mass 12.0 to 16.5",
    # comparisons & math
    "mass > 12",
    "charge*2 + 1 > mass",
    "sqrt(charge) <= 2",
    "arcsin(x) > 0",
    "-charge > 5",
    # strings / regex
    'name "CA"',
    'name =~ "C.*"',
    'resname "AL."',
    # logical operators
    "not water",
    "name CA and resname ALA",
    "protein or water",
    "name CA xor name CB",
    "protein and (resname ALA or resname GLY) and not water",
    # spatial / structural / sequence
    "within 5 of water",
    "exwithin 4 of protein",
    "same resid as exwithin 4 of water",
    "sequence ALA",
    # precedence / associativity / grouping stress cases
    "protein and water and name CA",          # left-assoc and chain
    "protein or water or name CA",            # left-assoc or chain
    "(protein or water) and name CA",         # explicit grouping must survive
    "protein and (water or name CA)",
    "protein or water and name CA",           # or binds looser than and
    "not (protein and water)",
    "not not protein",
    "name CA and not water",
    "charge - 1 - 2 > mass",                  # left-assoc subtraction
    "charge ** 2 ** 3 > mass",                # left-assoc power (this grammar)
    "(charge + 1) * 2 > mass",                # grouping changes math precedence
    "charge * (mass + 1) > 5",
    "-(charge + 1) > 5",                      # neg wraps a looser child
    "1 < charge and charge < 5",              # chained-style comparison via and
    "within 5 of water and protein",          # greedy `of` — single Within
    "within 5 of protein or name CA",
    "name CA and within 5 of water",          # Within as right operand
    "same resid as protein and water",        # greedy `as`
])
def test_symbolic_round_trip(evaluator, sel):
    """Every node type renders as valid, idempotent (re-parseable) selection syntax."""
    assert_round_trip(evaluator.builder, sel)


def test_evaluation_error_localizes_failing_subexpression(evaluator, example_dataframe):
    """A missing column raises MolSelectEvaluationError naming the failing part."""
    # `charge` is a valid keyword but absent from the example structure.
    with pytest.raises(MolSelectEvaluationError) as exc:
        evaluator.parse(example_dataframe, "charge > 5 and name CA")
    msg = str(exc.value)
    assert "charge" in msg and "not found" in msg
    assert "`charge`" in msg  # points at the offending sub-expression

