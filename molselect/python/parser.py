from lark import Lark, Tree
import logging

logger = logging.getLogger(__name__)

class SelectionParser:
    """Parses selection strings to parse trees using Lark."""
    def __init__(self, grammar_path: str):
        with open(grammar_path) as f:
            grammar_text = f.read()
        self.lark = Lark(grammar_text, parser='lalr', propagate_positions=True, start=['start', 'expr'])
    def parse(self, text: str, start_rule: str = 'start') -> Tree:
        return self.lark.parse(text, start=start_rule)