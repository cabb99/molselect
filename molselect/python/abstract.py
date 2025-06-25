import math
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Any, Optional,Union

class Node:
    """Base AST node; subclasses implement eager and symbolic evaluation."""
    short_circuit = True
    def evaluate(self, df: DataFrameLike) -> Any:
        raise NotImplementedError
    def symbolic(self) -> str:
        raise NotImplementedError

class LogicNode(Node):
    """Base class for logical nodes that can short-circuit evaluation."""
    @property
    def evaluate_global(self) -> bool:
        return getattr(self.left,  'evaluate_global', True) and getattr(self.right, 'evaluate_global', True)

@dataclass
class Start(Node):
    """Root node of the AST, contains the main expression."""
    expr: Node
    def evaluate(self, df: DataFrameLike) -> pd.Series:
        """Evaluate the main expression and return a boolean mask."""
        return df[self.expr.evaluate(df)]
    def symbolic(self) -> str:
        """Return the symbolic representation of the main expression."""
        return self.expr.symbolic() if self.expr else "Start"
# Logical Operators
@dataclass
class And(LogicNode):
    left: Node
    right: Node
    def evaluate(self, df: DataFrameLike) -> pd.Series:
        left_mask = self.left.evaluate(df)
        # Short-circuit: if nothing matches left, return all False
        if not left_mask.any():
            return left_mask
        # Only evaluate right on the subset where left_mask is True unless short-circuiting is disabled
        right_mask = self.right.evaluate(df[left_mask] if self.right.short_circuit else df)
        # Reindex right_mask to match original df
        combined = pd.Series(False, index=df.index)
        combined.loc[right_mask.index] = left_mask.loc[right_mask.index] & right_mask
        return combined
    def symbolic(self) -> str:
        return f"({self.left.symbolic()}) & ({self.right.symbolic()})"

@dataclass
class Or(Node):
    left: Node
    right: Node
    def evaluate(self, df: DataFrameLike) -> pd.Series:
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
    def symbolic(self) -> str:
        return f"({self.left.symbolic()}) | ({self.right.symbolic()})"

@dataclass
class Xor(Node):
    left: Node
    right: Node
    def evaluate(self, df: DataFrameLike) -> pd.Series:
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
    def symbolic(self) -> str:
        return f"({self.left.symbolic()}) ^ ({self.right.symbolic()})"

@dataclass
class Not(Node):
    expr: Node
    def evaluate(self, df: DataFrameLike) -> pd.Series:
        return ~self.expr.evaluate(df)
    def symbolic(self) -> str:
        return f"~({self.expr.symbolic()})"
    
@dataclass
class All(Node):
    def evaluate(self, df):
        return pd.Series(True, index=df.index)
    def symbolic(self):
        return "All"

@dataclass
class None_(Node):
    def evaluate(self, df):
        return pd.Series(False, index=df.index)
    def symbolic(self):
        return "None"

# Selections
@dataclass
class Comparison(Node):
    field: Node  # always a Node now
    op: str
    value: Union[str, Node, float, int, None]
    def evaluate(self, df: DataFrameLike) -> pd.Series:
        left = self.field.evaluate(df)
        right = self.value.evaluate(df) if isinstance(self.value, Node) else self.value

        op = self.op
        if not isinstance(left, pd.Series) and isinstance(right, pd.Series):
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
            if isinstance(left, pd.Series):
                return pd.Series(False, index=left.index)
            elif isinstance(right, pd.Series):
                return pd.Series(False, index=right.index)
            else:
                return False
    def symbolic(self) -> str:
        return f"{self.field.symbolic()} {self.op} {self.value.symbolic() if isinstance(self.value, Node) else self.value}"

## Data Values
class DataValue(Node):
    """Base class for data values that do not evaluate to a Series."""
    def evaluate(self, df: DataFrameLike) -> Any:
        raise NotImplementedError(f"{self.__class__.__name__} should not be evaluated directly.")
    def symbolic(self) -> str:
        """ Write the name of the class and their values as a string representation. """
        return f"{self.__class__.__name__}({' '.join(f'{k}={v!r}' for k, v in self.__dict__.items() if v is not None)})"

@dataclass
class RangeValue(DataValue):
    start: Union[Node]
    end: Union[Node]
    step: Union[Node, None] = None
    def evaluate(self, df: DataFrameLike):
        start = self.start.evaluate(df) if isinstance(self.start, Node) else self.start
        end = self.end.evaluate(df) if isinstance(self.end, Node) else self.end
        step = self.step.evaluate(df) if isinstance(self.step, Node) else self.step
        return start, end, step

   
@dataclass
class StringValue(DataValue):
    """Represents a string value in the AST."""
    value: str
    def evaluate(self, df: DataFrameLike) -> str:
        return self.value
    
    def symbolic(self) -> str:
        return repr(self.value)
    
@dataclass
class QuotedStringValue(DataValue):
    """Represents a quoted string value in the AST."""
    value: str
    def evaluate(self, df: DataFrameLike) -> str:
        return self.value[1:-1]  # Remove quotes
    
    def symbolic(self) -> str:
        return repr(self.value)

@dataclass
class RegexValue(DataValue):
    """Represents a regex value in the AST."""
    value: str
    def evaluate(self, df: DataFrameLike) -> str:
        return self.value    
    
    def symbolic(self) -> str:
        return f"RegexValue(value={self.value!r})"

@dataclass
class PropertySelection(Node):
    field: Node  # always a Node now
    values: list
    def evaluate(self, df):
        col = self.field.evaluate(df)
        mask = pd.Series(False, index=col.index)
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
    def symbolic(self):
        return f"PropertySelection({self.field.symbolic()}, {self.values})"


@dataclass
class Regex(Node):
    field: Node  # always a Node now
    pattern: str
    def evaluate(self, df: DataFrameLike) -> pd.Series:
        col = self.field.evaluate(df)
        pattern = self.pattern.evaluate(df)
        return col.astype(str).str.contains(pattern, regex=True)
    def symbolic(self) -> str:
        return f"Regex({self.field.symbolic()}, {self.pattern!r})"

@dataclass
class Within(Node):
    """Spatial selection within a distance of reference points."""
    short_circuit = False # Needs access to all points, so no short-circuiting
    distance: Node  # always a Node now
    target_mask: Node  # always a Node now
    mode: str = "within"  # "within" or "exwithin"
    def evaluate(self, df: DataFrameLike) -> pd.Series:
        distance = self.distance.evaluate(df)
        mask = self.target_mask.evaluate(df)
        ref_pts = df.loc[mask, ['x','y','z']].values
        pts = df[['x','y','z']].values
        if ref_pts.size == 0:
            # “within” of an empty set → nobody matches
            result = np.zeros(len(df), dtype=bool)
            return pd.Series(result, index=df.index)
        d2 = ((pts[:,None,:] - ref_pts[None,:,:])**2).sum(axis=2)
        if self.mode == "within":
            result = (d2.min(axis=1)**0.5) <= distance
        else:  # exwithin
            result = (d2.min(axis=1)**0.5) > distance
        return pd.Series(result, index=df.index)
    def symbolic(self) -> str:
        return f"{self.mode}({self.distance.symbolic()}, {self.target_mask.symbolic()})"

@dataclass
class Macro(Node):
    """User-defined macro that expands into another AST subtree."""
    name: str
    definition: Optional[Node] = None

    def evaluate(self, df):
        if self.definition is None:
            raise RuntimeError("Macro definition not expanded.")
        return self.definition.evaluate(df)

    def symbolic(self):
        # Always expand macros before symbolic, for correct output
        if self.definition is None:
            raise RuntimeError("Macro definition not expanded for symbolic(). Expand macros before calling symbolic().")
        return self.definition.symbolic()

@dataclass
class Same(Node):
    short_circuit = False # Needs access to all points, so no short-circuiting
    field: Node  # always a Node now
    mask: Node
    def evaluate(self, df):
        col = self.field.evaluate(df)
        vals = col[df.index[self.mask.evaluate(df)]].unique()
        return col.isin(vals)
    def symbolic(self):
        return f"Same({self.field.symbolic()}, {self.mask.symbolic()})"
    
@dataclass
class SelectionKeyword(Node):
    name: str
    def evaluate(self, df):
        if self.name == 'index':
            return pd.Series(df.index, name='index', index=df.index)
        if self.name not in df.columns:
            raise ValueError(f"Column '{self.name}' not found in DataFrame.")
        return df[self.name]
    def symbolic(self):
        return self.name

@dataclass
class Bonded(Node):
    short_circuit = False # Needs access to all points, so no short-circuiting
    distance: float
    selection: Node
    def evaluate(self, df):
        raise NotImplementedError("Bonded selection not implemented.")
    def symbolic(self):
        return f"Bonded({self.distance!r}, {self.selection!r})"

@dataclass
class SequenceSelectionRegex(Node):
    pattern: str
    def evaluate(self, df):
        raise NotImplementedError("Sequence selection regex not implemented.")
    def symbolic(self):
        return f"SequenceSelectionRegex({self.pattern!r})"

@dataclass
class SequenceSelection(Node):
    sequence: str
    def evaluate(self, df):
        raise NotImplementedError("Sequence selection not implemented.")
    def symbolic(self):
        return f"SequenceSelection({self.sequence!r})"

# Mathematical Operations
@dataclass
class Add(Node):
    left: Node
    right: Node
    def evaluate(self, df):
        return self.left.evaluate(df) + self.right.evaluate(df)
    def symbolic(self):
        return f"({self.left.symbolic()}) + ({self.right.symbolic()})"

@dataclass
class Sub(Node):
    left: Node
    right: Node
    def evaluate(self, df):
        return self.left.evaluate(df) - self.right.evaluate(df)
    def symbolic(self):
        return f"({self.left.symbolic()}) - ({self.right.symbolic()})"

@dataclass
class Mul(Node):
    left: Node
    right: Node
    def evaluate(self, df):
        return self.left.evaluate(df) * self.right.evaluate(df)
    def symbolic(self):
        return f"({self.left.symbolic()}) * ({self.right.symbolic()})"

@dataclass
class Div(Node):
    left: Node
    right: Node
    def evaluate(self, df):
        return self.left.evaluate(df) / self.right.evaluate(df)
    def symbolic(self):
        return f"({self.left.symbolic()}) / ({self.right.symbolic()})"

@dataclass
class FloorDiv(Node):
    left: Node
    right: Node
    def evaluate(self, df):
        return self.left.evaluate(df) // self.right.evaluate(df)
    def symbolic(self):
        return f"({self.left.symbolic()}) // ({self.right.symbolic()})"

@dataclass
class Mod(Node):
    left: Node
    right: Node
    def evaluate(self, df):
        return self.left.evaluate(df) % self.right.evaluate(df)
    def symbolic(self):
        return f"({self.left.symbolic()}) % ({self.right.symbolic()})"

@dataclass
class Pow(Node):
    left: Node
    right: Node
    def evaluate(self, df):
        return self.left.evaluate(df) ** self.right.evaluate(df)
    def symbolic(self):
        return f"({self.left.symbolic()}) ** ({self.right.symbolic()})"

@dataclass
class Neg(Node):
    value: Node
    def evaluate(self, df):
        return -self.value.evaluate(df)
    def symbolic(self):
        return f"-({self.value.symbolic()})"

@dataclass
class Func(Node):
    name: str
    arg: Node
    def evaluate(self, df):
        v = self.arg.evaluate(df)
        if self.name == 'sq':
            return v ** 2
        if self.name == 'abs':
            return np.abs(v)
        return getattr(np, self.name)(v)
    def symbolic(self):
        return f"{self.name}({self.arg.symbolic()})"

@dataclass
class Number(Node):
    value: Union[int, float]
    def evaluate(self, df):
        v = self.value
        if '.' in v or 'e' in v or 'E' in v:
            return float(v)
        return int(v)
    def symbolic(self):
        return str(self.value)

@dataclass
class Const(Node):
    name: str
    def evaluate(self, df):
        if self.name.lower() == 'pi':
            return math.pi
        elif self.name.lower() == 'e':
            return math.e
        else:
            raise ValueError(f"Unknown constant: {self.name}")
    def symbolic(self):
        return self.name