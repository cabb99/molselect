import logging
from molselect.python.builder import ASTBuilder
from molselect.python.abstract import Node, Macro
from molselect.python.parser import SelectionParser
from typing import Dict

logger = logging.getLogger(__name__)

class Evaluator:
    """Evaluates AST nodes on a DataFrame, with macro expansion."""
    def __init__(self, df, macros: Dict[str, str], parser: SelectionParser, builder: ASTBuilder):
        self.df = df
        self.macros = macros
        self.parser = parser
        self.builder = builder
    def expand_macros_in_ast(self, node):
        """Recursively expand Macro nodes in the AST using string-based expansion for full macro resolution."""
        if isinstance(node, Macro):
            # Use string-based recursive expansion from MacrosLoader
            expanded_expr = self._expand_macro_string(node.name)
            tree = self.parser.parse(expanded_expr, start_rule='expr')
            ast = self.builder.transform(tree)
            return self.expand_macros_in_ast(ast)
        # Recursively expand for all dataclass fields that are Node(s)
        if hasattr(node, '__dataclass_fields__'):
            for field in node.__dataclass_fields__:
                value = getattr(node, field)
                if isinstance(value, Node):
                    setattr(node, field, self.expand_macros_in_ast(value))
                elif isinstance(value, list):
                    new_list = [self.expand_macros_in_ast(v) if isinstance(v, Node) else v for v in value]
                    setattr(node, field, new_list)
        return node

    def _expand_macro_string(self, name, seen=None):
        """Recursively expand macro references in a string, including hidden/underscore macros."""
        if seen is None:
            seen = set()
        if name not in self.macros:
            raise ValueError(f"Macro {name!r} not defined")
        expr = self.macros[name]
        tokens = expr.split()
        expanded = []
        for token in tokens:
            macro_key = token[1:] if token.startswith('@') else token
            if macro_key in self.macros and macro_key not in seen:
                seen.add(macro_key)
                expanded_sub = self._expand_macro_string(macro_key, seen)
                expanded.append(expanded_sub)
                seen.remove(macro_key)
            else:
                expanded.append(token)
        return ' '.join(expanded)

    def evaluate(self, root: Node):
        root = self.expand_macros_in_ast(root)
        return root.evaluate(self.df)
    def symbolic(self, root: Node) -> str:
        root = self.expand_macros_in_ast(root)
        return root.symbolic()