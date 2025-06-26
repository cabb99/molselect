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
    """
    def __init__(self, backend, parser: Optional[SelectionParser] = None, builder: Optional[ASTBuilder] = None):
        self.backend = backend
        self.parser = parser or SelectionParser()
        self.builder = builder or ASTBuilder(self.parser)

    def evaluate(self, root: Node):
        return root.evaluate(self.backend)

    def symbolic(self, root: Node) -> str:
        return root.symbolic()