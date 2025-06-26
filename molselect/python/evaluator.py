import logging
from molselect.python.builder import ASTBuilder
from molselect.python.abstract import Node
from molselect.python.parser import SelectionParser
from typing import Optional

logger = logging.getLogger(__name__)

class Evaluator:
    """
    Evaluates AST nodes on a Structure (e.g., DataFrame), with backend selection.
    The parser and builder are fixed for the lifetime of the evaluator; only the backend (structure) changes.
    Now supports a simple parse method for direct selection from a DataFrame.
    """
    def __init__(self, backend_cls, parser: Optional[SelectionParser] = None, builder: Optional[ASTBuilder] = None):
        self.backend = backend_cls
        self.parser = parser or SelectionParser()
        self.builder = builder or ASTBuilder(self.parser)

    def evaluate(self, root: Node, structure=None):
        if structure is not None:
            return root.evaluate(structure)
        raise ValueError("Backend instance must be provided for evaluation or use the parse() method.")

    def symbolic(self, root: Node) -> str:
        return root.symbolic()

    def parse(self, df, selection: str):
        """
        Parse and evaluate a selection string on a DataFrame in one call.
        """
        structure = self.backend(df)
        tree = self.parser.parse(selection)
        ast = self.builder.transform(tree)
        return self.evaluate(ast, structure=structure)