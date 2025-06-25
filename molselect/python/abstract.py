import math
import numpy as np
import pandas as pd
from dataclasses import dataclass, fields
from typing import Any, Optional,Union
from typing_extensions import Protocol, runtime_checkable
from molselect.python.protocols import Array, Structure, Mask

@runtime_checkable
class Structure(Protocol):
    """Protocol for objects that can be used like a pandas DataFrame."""
    def __getitem__(self, key: str) -> Array: ...
    def __setitem__(self, key: str, value: Array) -> None: ...
    @property
    def index(self) -> pd.Index: ...
    @property
    def columns(self) -> pd.Index: ...
    def loc(self, indexer) -> 'Structure': ...
    def copy(self) -> 'Structure': ...


class Node:
    """Base AST node; subclasses implement eager and symbolic evaluation."""
    short_circuit = True
    _symbol: str = None   # subclasses can override
    
    def evaluate(self, df: Structure) -> Any:
        raise NotImplementedError
    
    def symbolic(self) -> str:
        # 1) If this node has a custom symbol and exactly two fields, render infix
        if self._symbol and len(fields(self)) == 2:
            left, right = (getattr(self, f.name) for f in fields(self))
            return f"({left.symbolic()}) {self._symbol} ({right.symbolic()})"
        # 2) If it’s a 1-arg prefix operator
        if self._symbol and len(fields(self)) == 1:
            (inner,) = (getattr(self, f.name) for f in fields(self))
            return f"{self._symbol}({inner.symbolic()})"
        # 3) Fallback: list out all dataclass fields by name
        parts = []
        for f in fields(self):
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
    _symbol: str = None
    expr: Node
    def evaluate(self, df: Structure) -> Structure:
        """Evaluate the main expression and return a boolean mask."""
        return Structure.select(self.expr.evaluate)
# Logical Operators
@dataclass
class And(LogicNode):
    _symbol: str = "&"
    left: Node
    right: Node
    def evaluate(self, df: Structure) -> Array:
        left_mask = self.left.evaluate(df)
        # Short-circuit: if nothing matches left, return all False
        if not left_mask.any():
            return left_mask
        # Only evaluate right on the subset where left_mask is True unless short-circuiting is disabled
        right_mask = self.right.evaluate(df[left_mask] if self.right.short_circuit else df)
        # Reindex right_mask to match original df
        combined = Array(False, index=df.index)
        combined.loc[right_mask.index] = left_mask.loc[right_mask.index] & right_mask
        return combined

@dataclass
class Or(Node):
    _symbol: str = "|"
    left: Node
    right: Node
    def evaluate(self, df: Structure) -> Array:
        left_mask = self.left.evaluate(df)
        # Short-circuit: if everything matches left, return all True
        if left_mask.all():
            return left_mask
        # Only evaluate right on the subset where left_mask is False unless short-circuiting is disabled
        right_mask = self.right.evaluate(df[~left_mask] if self.right.short_circuit else df)
        # Start with left_mask, set True where right_mask is True
        combined = left_mask.copy()
        combined.loc[right_mask.index] = left_mask.loc[right_mask.index] | right_mask
        return combined

@dataclass
class Xor(Node):
    _symbol: str = "^"
    left: Node
    right: Node
    def evaluate(self, df: Structure) -> Array:
        left_mask = self.left.evaluate(df)
        # Short-circuit: if everything matches left, return ~right
        if left_mask.all():
            return ~self.right.evaluate(df)
        # Short-circuit: if nothing matches left, return right
        if not left_mask.any():
            return self.right.evaluate(df)
        # Evaluate right only on where left_mask is False unless short-circuiting is disabled
        right_mask = self.right.evaluate(df[~left_mask] if self.right.short_circuit else df)
        combined = left_mask.copy()
        combined.loc[right_mask.index] = left_mask.loc[right_mask.index] ^ right_mask
        return combined

@dataclass
class Not(Node):
    _symbol: str = "~"
    expr: Node
    def evaluate(self, df: Structure) -> Array:
        return ~self.expr.evaluate(df)
    
@dataclass
class All(Node):
    _symbol: str = None
    def evaluate(self, df):
        return Array(True, index=df.index)

@dataclass
class None_(Node):
    _symbol: str = None
    def evaluate(self, df):
        return Array(False, index=df.index)

# Selections
@dataclass
class Comparison(Node):
    _symbol: str = None
    field: Node  # always a Node now
    op: str
    value: Union[str, Node, float, int, None]
    def evaluate(self, df: Structure) -> Array:
        left = self.field.evaluate(df)
        right = self.value.evaluate(df) if isinstance(self.value, Node) else self.value

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
            # Return all False if comparison is invalid (e.g., str < int)
            if isinstance(left, Array):
                return Array(False, index=left.index)
            elif isinstance(right, Array):
                return Array(False, index=right.index)
            else:
                return False

## Data Values
class DataValue(Node):
    """Base class for data values that do not evaluate to a Series."""
    def evaluate(self, df: Structure) -> Any:
        raise NotImplementedError(f"{self.__class__.__name__} should not be evaluated directly.")

@dataclass
class RangeValue(DataValue):
    start: Union[Node]
    end: Union[Node]
    step: Union[Node, None] = None
    def evaluate(self, df: Structure):
        start = self.start.evaluate(df) if isinstance(self.start, Node) else self.start
        end = self.end.evaluate(df) if isinstance(self.end, Node) else self.end
        step = self.step.evaluate(df) if isinstance(self.step, Node) else self.step
        return start, end, step

   
@dataclass
class StringValue(DataValue):
    """Represents a string value in the AST."""
    value: str
    def evaluate(self, df: Structure) -> str:
        return self.value
    
@dataclass
class QuotedStringValue(DataValue):
    """Represents a quoted string value in the AST."""
    value: str
    def evaluate(self, df: Structure) -> str:
        return self.value[1:-1]  # Remove quotes
    
@dataclass
class RegexValue(DataValue):
    """Represents a regex value in the AST."""
    value: str
    def evaluate(self, df: Structure) -> str:
        return self.value    

@dataclass
class PropertySelection(Node):
    _symbol: str = None
    field: Node  # always a Node now
    values: list
    def evaluate(self, df):
        col = self.field.evaluate(df)
        mask = Array(False, index=col.index)
        for v in self.values:
            if isinstance(v, StringValue):
                value = v.evaluate(df)
                mask |= (col == value)
            elif isinstance(v, QuotedStringValue):
                value = v.evaluate(df)
                mask |= (col == value)
            elif isinstance(v, RegexValue):
                # Pass the string pattern, not the node
                mask |= Regex(self.field, v).evaluate(df)
            elif isinstance(v, RangeValue):
                start = v.start.evaluate(df) if isinstance(v.start, Node) else v.start
                end = v.end.evaluate(df) if isinstance(v.end, Node) else v.end
                step = v.step.evaluate(df) if (v.step is not None and isinstance(v.step, Node)) else v.step
                range_mask = (col >= start) & (col <= end)
                if step is not None:
                    range_mask &= ((col - start) % step == 0)
                mask |= range_mask
            else:
                mask |= (col == v.evaluate(df) if isinstance(v, Node) else col == v)
        return mask


@dataclass
class Regex(Node):
    _symbol: str = None
    field: Node  # always a Node now
    pattern: str
    def evaluate(self, df: Structure) -> Array:
        col = self.field.evaluate(df)
        pattern = self.pattern.evaluate(df)
        return col.astype(str).str.contains(pattern, regex=True)

@dataclass
class Within(Node):
    """Spatial selection within a distance of reference points."""
    short_circuit = False # Needs access to all points, so no short-circuiting
    distance: Node  # always a Node now
    target_mask: Node  # always a Node now
    mode: str = "within"  # "within" or "exwithin"
    def evaluate(self, df: Structure) -> Array:
        distance = self.distance.evaluate(df)
        mask = self.target_mask.evaluate(df)
        ref_pts = df.loc[mask, ['x','y','z']].values
        pts = df[['x','y','z']].values
        if ref_pts.size == 0:
            # “within” of an empty set → nobody matches
            result = np.zeros(len(df), dtype=bool)
            return Array(result, index=df.index)
        d2 = ((pts[:,None,:] - ref_pts[None,:,:])**2).sum(axis=2)
        if self.mode == "within":
            result = (d2.min(axis=1)**0.5) <= distance
        else:  # exwithin
            result = (d2.min(axis=1)**0.5) > distance
        return Array(result, index=df.index)

@dataclass
class Macro(Node):
    """User-defined macro that expands into another AST subtree."""
    _symbol: str = None
    name: str
    definition: Optional[Node] = None

    def evaluate(self, df):
        if self.definition is None:
            raise RuntimeError("Macro definition not expanded.")
        return self.definition.evaluate(df)

@dataclass
class Same(Node):
    _symbol: str = None
    short_circuit = False # Needs access to all points, so no short-circuiting
    field: Node  # always a Node now
    mask: Node
    def evaluate(self, df):
        col = self.field.evaluate(df)
        vals = col[df.index[self.mask.evaluate(df)]].unique()
        return col.isin(vals)
    
@dataclass
class SelectionKeyword(Node):
    _symbol: str = None
    name: str
    def evaluate(self, df):
        if self.name == 'index':
            return Array(df.index, name='index', index=df.index)
        if self.name not in df.columns:
            raise ValueError(f"Column '{self.name}' not found in DataFrame.")
        return df[self.name]

@dataclass
class Bonded(Node):
    _symbol: str = None
    short_circuit = False # Needs access to all points, so no short-circuiting
    distance: float
    selection: Node
    def evaluate(self, df):
        raise NotImplementedError("Bonded selection not implemented.")

@dataclass
class SequenceSelectionRegex(Node):
    _symbol: str = None
    pattern: str
    def evaluate(self, df):
        raise NotImplementedError("Sequence selection regex not implemented.")

@dataclass
class SequenceSelection(Node):
    _symbol: str = None
    sequence: str
    def evaluate(self, df):
        raise NotImplementedError("Sequence selection not implemented.")

# Mathematical Operations
@dataclass
class Add(Node):
    _symbol: str = "+"
    left: Node
    right: Node
    def evaluate(self, df):
        return self.left.evaluate(df) + self.right.evaluate(df)

@dataclass
class Sub(Node):
    _symbol: str = "-"
    left: Node
    right: Node
    def evaluate(self, df):
        return self.left.evaluate(df) - self.right.evaluate(df)

@dataclass
class Mul(Node):
    _symbol: str = "*"
    left: Node
    right: Node
    def evaluate(self, df):
        return self.left.evaluate(df) * self.right.evaluate(df)

@dataclass
class Div(Node):
    _symbol: str = "/"
    left: Node
    right: Node
    def evaluate(self, df):
        return self.left.evaluate(df) / self.right.evaluate(df)

@dataclass
class FloorDiv(Node):
    _symbol: str = "//"
    left: Node
    right: Node
    def evaluate(self, df):
        return self.left.evaluate(df) // self.right.evaluate(df)

@dataclass
class Mod(Node):
    _symbol: str = "%"
    left: Node
    right: Node
    def evaluate(self, df):
        return self.left.evaluate(df) % self.right.evaluate(df)

@dataclass
class Pow(Node):
    _symbol: str = "**"
    left: Node
    right: Node
    def evaluate(self, df):
        return self.left.evaluate(df) ** self.right.evaluate(df)

@dataclass
class Neg(Node):
    _symbol: str = "-"
    value: Node
    def evaluate(self, df):
        return -self.value.evaluate(df)

@dataclass
class Func(Node):
    _symbol: str = None
    name: str
    arg: Node
    def evaluate(self, df):
        v = self.arg.evaluate(df)
        if self.name == 'sq':
            return v ** 2
        if self.name == 'abs':
            return np.abs(v)
        return getattr(np, self.name)(v)

@dataclass
class Number(Node):
    _symbol: str = None
    value: Union[int, float, str]
    def evaluate(self, df):
        v = self.value
        if '.' in v or 'e' in v or 'E' in v:
            return float(v)
        return int(v)

@dataclass
class Const(Node):
    _symbol: str = None
    name: str
    def evaluate(self, df):
        if self.name.lower() == 'pi':
            return math.pi
        elif self.name.lower() == 'e':
            return math.e
        else:
            raise ValueError(f"Unknown constant: {self.name}")

