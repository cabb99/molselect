import math
import numpy as np
from dataclasses import dataclass, fields
from typing import Any, Optional, Union
from typing_extensions import Protocol, runtime_checkable
from molselect.python.protocols import Array, Structure, Mask

class Node:
    """Base AST node; subclasses implement eager and symbolic evaluation."""
    short_circuit = True
    _symbol: str = None   # subclasses can override
    
    def evaluate(self, s: Structure) -> Any:
        raise NotImplementedError
    
    def symbolic(self) -> str:
        # Exclude _symbol from field list for symbolic rendering
        data_fields = [f for f in fields(self) if f.name != '_symbol']
        # 1) If this node has a custom symbol and exactly two data fields, render infix
        if self._symbol and len(data_fields) == 2:
            left, right = (getattr(self, f.name) for f in data_fields)
            return f"({left.symbolic()}) {self._symbol} ({right.symbolic()})"

        # 2) If it’s a 1-arg prefix operator
        if self._symbol and len(data_fields) == 1:
            (inner,) = (getattr(self, f.name) for f in data_fields)
            return f"{self._symbol}({inner.symbolic()})"
        # 3) Fallback: list out all dataclass fields by name (excluding _symbol)
        parts = []
        for f in data_fields:
            v = getattr(self, f.name)
            if isinstance(v, Node):
                parts.append(v.symbolic())
            elif isinstance(v, list):
                parts.append("[" + ", ".join(x.symbolic() if isinstance(x, Node) else repr(x) for x in v) + "]")
            else:
                parts.append(repr(v))
        name = type(self).__name__
        return f"{name}(" + ", ".join(parts) + ")"

class LogicNode(Node):
    """Base class for logical nodes that can short-circuit evaluation."""
    @property
    def evaluate_global(self) -> Mask:
        return getattr(self.left,  'evaluate_global', True) and getattr(self.right, 'evaluate_global', True)

@dataclass
class Start(Node):
    """Root node of the AST, contains the main expression."""
    expr: Node
    def evaluate(self, s: Structure) -> Structure:
        """Evaluate the main expression and return a boolean mask."""
        return s.select(self.expr.evaluate(s))

@dataclass
class And(LogicNode):
    left: Node
    right: Node
    _symbol: str = "&"
    def evaluate(self, s: Structure) -> Array:
        left_mask = self.left.evaluate(s)
        # Short-circuit: if nothing matches left, return all False
        if not left_mask.any():
            return left_mask
        # Only evaluate right on the subset where left_mask is True unless short-circuiting is disabled
        if self.right.short_circuit:
            # Evaluate right only on the subset where left_mask is True
            right_mask = self.right.evaluate(s.select(left_mask))
            # Expand right_mask
            combined = s.array_filled(False)
            return combined.set_by_index(right_mask.index, right_mask)
        else:
            # Evaluate right on the full structure
            return left_mask & self.right.evaluate(s) 

@dataclass
class Or(Node):
    left: Node
    right: Node
    _symbol: str = "|"
    def evaluate(self, s: Structure) -> Array:
        left_mask = self.left.evaluate(s)
        # Short-circuit: if everything matches left, return all True
        if left_mask.all():
            return left_mask
        if self.right.short_circuit:
            # Evaluate right only on the subset where left_mask is False
            right_mask = self.right.evaluate(s.select(~left_mask))
            combined = s.array_filled(True)
            return combined.set_by_index(right_mask.index, right_mask)
        else:
            # Evaluate right on the full structure
            return left_mask | self.right.evaluate(s)


@dataclass
class Xor(Node):
    left: Node
    right: Node
    _symbol: str = "^"

    def evaluate(self, s: Structure) -> Array:
        return self.left.evaluate(s) ^ self.right.evaluate(s)

@dataclass
class Not(Node):
    expr: Node
    _symbol: str = "~"
    def evaluate(self, s: Structure) -> Array:
        return ~self.expr.evaluate(s)
    
@dataclass
class All(Node):
    def evaluate(self, s):
        return s.array_filled(True)

@dataclass
class None_(Node):
    def evaluate(self, s):
        return s.array_filled(False)

# Selections
@dataclass
class Comparison(Node):
    field: Node  # always a Node now
    op: str
    value: Union[str, Node, float, int, None]
    def evaluate(self, s: Structure) -> Array:
        left = self.field.evaluate(s)
        right = self.value.evaluate(s) if isinstance(self.value, Node) else self.value

        op = self.op
        if not isinstance(left, Array) and isinstance(right, Array):
            left, right = right, left
            flip = {'<': '>', '>': '<', '<=': '>=', '>=': '<=', '==': '==', '!=': '!=',
                    'eq': 'eq', 'ne': 'ne', 'lt': 'gt', 'gt': 'lt', 'le': 'ge', 'ge': 'le'}
            op = flip.get(op, op)

        if right is None:
            return left.astype(bool)

        ops = {
            '==': lambda l, r: l == r,
            '!=': lambda l, r: l != r,
            '<':  lambda l, r: l < r,
            '>':  lambda l, r: l > r,
            '<=': lambda l, r: l <= r,
            '>=': lambda l, r: l >= r,
            'eq': lambda l, r: l == r,
            'ne': lambda l, r: l != r,
            'lt': lambda l, r: l < r,
            'gt': lambda l, r: l > r,
            'le': lambda l, r: l <= r,
            'ge': lambda l, r: l >= r,
        }
        try:
            return ops[op](left, right)
        except TypeError:
            return s.array_filled(False)

    def symbolic(self) -> str:
        # Custom symbolic for Comparison: always show as infix
        left = self.field.symbolic() if isinstance(self.field, Node) else repr(self.field)
        right = self.value.symbolic() if isinstance(self.value, Node) else repr(self.value)
        return f"({left}) {self.op} ({right})"

## Data Values
class DataValue(Node):
    """Base class for data values that do not evaluate to a Series."""
    def evaluate(self, s: Structure) -> Any:
        raise NotImplementedError(f"{self.__class__.__name__} should not be evaluated directly.")

@dataclass
class RangeValue(DataValue):
    start: Union[Node]
    end: Union[Node]
    step: Union[Node, None] = None
    def evaluate(self, s: Structure):
        start = self.start.evaluate(s) if isinstance(self.start, Node) else self.start
        end = self.end.evaluate(s) if isinstance(self.end, Node) else self.end
        step = self.step.evaluate(s) if isinstance(self.step, Node) else self.step
        return start, end, step

   
@dataclass
class StringValue(DataValue):
    """Represents a string value in the AST."""
    value: str
    def evaluate(self, s: Structure) -> str:
        return self.value
    
@dataclass
class QuotedStringValue(DataValue):
    """Represents a quoted string value in the AST."""
    value: str
    def evaluate(self, s: Structure) -> str:
        return self.value[1:-1]  # Remove quotes
    
@dataclass
class RegexValue(DataValue):
    """Represents a regex value in the AST."""
    value: str
    def evaluate(self, s: Structure) -> str:
        return self.value    

@dataclass
class PropertySelection(Node):
    field: Node  # always a Node now
    values: list
    def evaluate(self, s):
        col = self.field.evaluate(s)
        mask = s.array_filled(False)
        for v in self.values:
            if isinstance(v, StringValue):
                value = v.evaluate(s)
                mask |= (col == value)
            elif isinstance(v, QuotedStringValue):
                value = v.evaluate(s)
                mask |= (col == value)
            elif isinstance(v, RegexValue):
                mask |= Regex(self.field, v).evaluate(s)
            elif isinstance(v, RangeValue):
                start = v.start.evaluate(s) if isinstance(v.start, Node) else v.start
                end = v.end.evaluate(s) if isinstance(v.end, Node) else v.end
                step = v.step.evaluate(s) if (v.step is not None and isinstance(v.step, Node)) else v.step
                range_mask = (col >= start) & (col <= end)
                if step is not None:
                    range_mask &= ((col - start) % step == 0)
                mask |= range_mask
            else:
                mask |= (col == v.evaluate(s) if isinstance(v, Node) else col == v)
        return mask


@dataclass
class Regex(Node):
    field: Node  # always a Node now
    pattern: str
    def evaluate(self, s: Structure) -> Array:
        col = self.field.evaluate(s)
        pattern = self.pattern.evaluate(s)
        # Use protocol method if available
        if hasattr(col, 'str_contains'):
            return col.str_contains(pattern, regex=True)
        # Fallback: elementwise regex
        import re
        regex = re.compile(pattern)
        found = s.array_values([bool(regex.search(str(x))) for x in col.data])
        return found


@dataclass
class Within(Node):
    """Spatial selection within a distance of reference points."""
    distance: Node  # always a Node now
    target_mask: Node  # always a Node now
    mode: str = "within"  # "within" or "exwithin"
    short_circuit = False # Needs access to all points, so no short-circuiting
    def evaluate(self, s: Structure) -> Array:
        distance = self.distance.evaluate(s)
        mask = self.target_mask.evaluate(s)
        dists = s.minimum_pairwise_distances(s.select(mask))
        if not mask.any():
            return s.array_filled(False)
        if self.mode == "within":
            result = (dists <= distance)
        else:
            result = (dists > distance)
        return s.array_values(result)

@dataclass
class Same(Node):
    field: Node  # always a Node now
    mask: Node
    short_circuit = False # Needs access to all points, so no short-circuiting
    def evaluate(self, s):
        col = self.field.evaluate(s)
        mask = self.mask.evaluate(s)
        return col.isin(col[mask])

@dataclass
class SelectionKeyword(Node):
    name: str
    def evaluate(self, s):
        if self.name == 'index':
            # Return a flat array of the index, not a nested list
            return s.get_property('index')
        if self.name not in s.columns:
            raise ValueError(f"Column '{self.name}' not found in Structure.")
        return s.get_property(self.name)

@dataclass
class Bonded(Node):
    distance: float
    selection: Node
    short_circuit = False # Needs access to all points, so no short-circuiting
    def evaluate(self, s):
        raise NotImplementedError("Bonded selection not implemented.")

@dataclass
class SequenceSelectionRegex(Node):
    pattern: str
    def evaluate(self, s):
        raise NotImplementedError("Sequence selection regex not implemented.")

@dataclass
class SequenceSelection(Node):
    sequence: str
    def evaluate(self, s):
        raise NotImplementedError("Sequence selection not implemented.")

# Mathematical Operations
@dataclass
class Add(Node):
    left: Node
    right: Node
    _symbol: str = "+"
    def evaluate(self, s):
        return self.left.evaluate(s) + self.right.evaluate(s)

@dataclass
class Sub(Node):
    left: Node
    right: Node
    _symbol: str = "-"
    def evaluate(self, s):
        return self.left.evaluate(s) - self.right.evaluate(s)

@dataclass
class Mul(Node):
    left: Node
    right: Node
    _symbol: str = "*"
    def evaluate(self, s):
        return self.left.evaluate(s) * self.right.evaluate(s)

@dataclass
class Div(Node):
    left: Node
    right: Node
    _symbol: str = "/"
    def evaluate(self, s):
        return self.left.evaluate(s) / self.right.evaluate(s)

@dataclass
class FloorDiv(Node):
    left: Node
    right: Node
    _symbol: str = "//"
    def evaluate(self, s):
        return self.left.evaluate(s) // self.right.evaluate(s)

@dataclass
class Mod(Node):
    left: Node
    right: Node
    _symbol: str = "%"
    def evaluate(self, s):
        return self.left.evaluate(s) % self.right.evaluate(s)

@dataclass
class Pow(Node):
    left: Node
    right: Node
    _symbol: str = "**"
    def evaluate(self, s):
        return self.left.evaluate(s) ** self.right.evaluate(s)

@dataclass
class Neg(Node):
    value: Node
    _symbol: str = "-"
    def evaluate(self, s):
        return -self.value.evaluate(s)

@dataclass
class Func(Node):
    name: str
    arg: Node
    _symbol: str = None
    def evaluate(self, s):
        v = self.arg.evaluate(s)
        if self.name == 'sq':
            return v ** 2
        if self.name == 'abs':
            return np.abs(v)
        return getattr(np, self.name)(v)

@dataclass
class Number(Node):
    value: Union[int, float, str]
    _symbol: str = None
    def evaluate(self, s):
        v = self.value
        if '.' in v or 'e' in v or 'E' in v:
            return float(v)
        return int(v)

@dataclass
class Const(Node):
    name: str
    _symbol: str = None
    def evaluate(self, s):
        if self.name.lower() == 'pi':
            return math.pi
        elif self.name.lower() == 'e':
            return math.e
        else:
            raise ValueError(f"Unknown constant: {self.name}")

