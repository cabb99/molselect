from lark import Transformer, v_args, Token, Tree
from typing import Optional, Dict
import logging
from molselect.python.abstract import *

logger = logging.getLogger(__name__)

@v_args(inline=True)
class ASTBuilder(Transformer):
    """Transforms parse trees into AST nodes, expanding macros immediately using the parser."""
    def __init__(self, parser=None):
        super().__init__()
        if parser is None:
            from molselect.python.parser import SelectionParser
            parser = SelectionParser()
        self.parser = parser

    def parse(self, sel, start_rule='start'):
        """Convenience method: parse a selection string and return the AST."""
        tree = self.parser.parse(sel, start_rule=start_rule)
        return self.transform(tree)

    def _expand_macro_ast(self, name):
        """Expand a macro by name using the parser and return the AST subtree."""
        expanded_expr = self.parser.expand_macro(name)
        tree = self.parser.parse(expanded_expr, start_rule='expr')
        return self.transform(tree)

    def _to_node(self, x):
        # Recursively transform Tree or Token to AST node
        if isinstance(x, Tree):
            return self.transform(x)
        return x

    def and_(self, left, right):
        return And(self._to_node(left), self._to_node(right))

    def or_(self, left, right):
        return Or(self._to_node(left), self._to_node(right))

    def xor_(self, left, right):
        return Xor(self._to_node(left), self._to_node(right))

    def not_(self, expr):
        return Not(self._to_node(expr))

    def comparison(self, name_tok, op_tok, value):
        left = self._to_node(name_tok)
        right = self._to_node(value)
        # If left is a SelectionKeyword node, use its name as string
        if isinstance(left, SelectionKeyword):
            left = left.name
        # Pass the raw operator text
        return Comparison(left, op_tok.value, right)

    def comparison_selection(self, *items):
        operands = [self._to_node(x) for x in items[0::2]]
        operators = items[1::2]
        mask = None
        for left, op, right in zip(operands, operators, operands[1:]):
            cmp = Comparison(left, str(op), right)
            mask = cmp if mask is None else And(mask, cmp)
        return mask

    def property_selection(self, name, *values):
        vals = []
        name = self._to_node(name)
        for v in values:
            node = self._to_node(v)
            vals.append(node)
        return PropertySelection(name, vals)

    def range_value(self, start, end, step=None):
        start = self._to_node(start)
        end = self._to_node(end)
        step = self._to_node(step) if step is not None else None
        return RangeValue(start, end, step)

    def regex_selection(self, operand, pattern):
        return Regex(self._to_node(operand), self._to_node(pattern))

    def regex_value(self, tok):
        return RegexValue(tok.value[1:-1])

    def quoted_string_value(self, tok):
        return QuotedStringValue(tok.value)

    def string_value(self, tok):
        return StringValue(tok.value)

    def number(self, tok):
        return Number(tok.value)

    def const(self, token):
        return Const(token.value)

    def func(self, fname:Token, arg):
        return Func(fname.type.lower(), self._to_node(arg))

    def add(self, left, right):
        return Add(self._to_node(left), self._to_node(right))
    def sub(self, left, right):
        return Sub(self._to_node(left), self._to_node(right))
    def mul(self, left, right):
        return Mul(self._to_node(left), self._to_node(right))
    def truediv(self, left, right):
        return Div(self._to_node(left), self._to_node(right))
    def floordiv(self, left, right):
        return FloorDiv(self._to_node(left), self._to_node(right))
    def mod(self, left, right):
        return Mod(self._to_node(left), self._to_node(right))
    def pow(self, left, right):
        return Pow(self._to_node(left), self._to_node(right))
    def neg(self, value):
        return Neg(self._to_node(value))
    def pos(self, value):
        return self._to_node(value)

    def within_selection(self, within_token, dist, target_mask):
        mode = str(within_token).lower()
        return Within(dist, self._to_node(target_mask), mode=mode)

    def bonded_selection(self, bonded_op, distance, selection):
        mode = str(bonded_op).lower()
        return Bonded(self._to_node(distance), self._to_node(selection), mode=mode)

    def same_selection(self, name, mask):
        name = self._to_node(name)
        return Same(name, self._to_node(mask))

    def macro(self, name):
        # Immediately expand macro using the parser
        return self._expand_macro_ast(str(name).lstrip('@'))

    def bool_keyword(self, tok):
        # Handle macros
        if tok.type == 'ALL':
            return All()
        if tok.type == 'NONE':
            return None_()
        # Use tok.type (canonical name in uppercase) to resolve synonyms
        canonical = tok.type.lower()
        # If it's a macro, expand it immediately
        if hasattr(self.parser, 'macros_dict') and canonical in self.parser.macros_dict:
            return self._expand_macro_ast(canonical)
        # Otherwise, treat as a column/flag
        return SelectionKeyword(canonical)

    def selection_keyword(self, token):
        if isinstance(token, Tree):
            return self._to_node(token)
        # Use token.type (canonical name in uppercase) to resolve synonyms
        return SelectionKeyword(token.type.lower())

    def var_sel(self, tok):
        return SelectionKeyword(str(tok))

    def macro_sel(self, tok):
        return self._expand_macro_ast(str(tok).lstrip('@'))

    def sequence_selection(self, sequence):
        return SequenceSelection(sequence)

    def start(self, expr):
        return Start(self._to_node(expr))
