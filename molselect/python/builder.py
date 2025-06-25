from lark import Transformer, v_args, Token, Tree
from typing import Optional, Dict
import logging
from molselect.python.abstract import *

logger = logging.getLogger(__name__)

@v_args(inline=True)
class ASTBuilder(Transformer):
    """Transforms parse trees into AST nodes."""
    def __init__(self, macros: Optional[Dict[str, str]] = None):
        super().__init__()
        self.macros = macros or {}
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
        if step is not None:
            step = self._to_node(step)
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

    def within_selection(self, within_token, dist, target_mask):
        mode = str(within_token).lower()
        return Within(dist, self._to_node(target_mask), mode=mode)

    def bonded_selection(self, distance, selection):
        return Bonded(distance, self._to_node(selection))

    def same_selection(self, name, mask):
        name = self._to_node(name)
        return Same(name, self._to_node(mask))

    def macro(self, name):
        # Macro expansion will be handled in Evaluator
        return Macro(str(name).lstrip('@'), None)

    def bool_keyword(self, tok):
        # Handle macros
        if tok.type == 'ALL':
            return All()
        if tok.type == 'NONE':
            return None_()
        # If it's a macro, return Macro node
        if hasattr(self, 'macros') and tok.value in self.macros:
            return Macro(str(tok.value), None)
        # Otherwise, treat as a column/flag
        return SelectionKeyword(str(tok.value))

    def selection_keyword(self, token):
        if isinstance(token, Tree):
            return self._to_node(token)
        return SelectionKeyword(str(token))

    def var_sel(self, tok):
        return SelectionKeyword(str(tok))

    def macro_sel(self, tok):
        return Macro(str(tok).lstrip('@'), None)

    def sequence_selection_regex(self, pattern):
        return SequenceSelectionRegex(str(pattern))

    def sequence_selection(self, sequence):
        return SequenceSelection(str(sequence))

    def start(self, expr):
        return Start(self._to_node(expr))
