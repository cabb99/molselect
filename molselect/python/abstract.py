import json
import math
import os
import re
import warnings
from decimal import Decimal
import numpy as np
from dataclasses import dataclass, fields
from typing import Any, Optional, Union
from typing_extensions import Protocol, runtime_checkable
from molselect.python.protocols import Array, Structure, Mask

import logging
logger = logging.getLogger(__name__)

# Load residue-name → 1-letter-code mappings from data file
_data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
with open(os.path.join(_data_dir, 'sequence_mappings.json')) as _f:
    _seq_maps = json.load(_f)

# Build a combined mapping: protein > DNA > RNA (no priority conflict for selection — all matches returned)
SEQUENCE_MAP = {}
SEQUENCE_MAP.update(_seq_maps['RNA'])
SEQUENCE_MAP.update(_seq_maps['DNA'])
SEQUENCE_MAP.update(_seq_maps['protein'])

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
        selection = self.expr.evaluate(s)
        return s.select(selection)

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
            '=':  lambda l, r: l == r,
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

def numeric_tolerance_from_literal(text: str) -> float:
    """Return half-unit tolerance implied by the decimal precision of a numeric literal.

    Tolerance is derived from the **token text**, not the parsed float value, so
    that ``12``, ``12.0``, and ``12.00`` can imply different precisions.

    Examples::

        "12"      -> 0.5        (integer: nearest whole unit)
        "12.0"    -> 0.05       (1 decimal place)
        "12.011"  -> 0.0005     (3 decimal places)
        ".5"      -> 0.05       (1 decimal place, no integer part)
        "12."     -> 0.5        (trailing dot = 0 fractional digits)
        "1e1"     -> 5.0        (integer × 10^1: nearest 10)
        "1.20e1"  -> 0.05       (2 decimal places × 10^1 → step 0.1)

    This is documented as *decimal precision matching*, not significant-digit
    matching — simpler and matches common expectations for atomic masses.
    """
    s = text.strip().lower()
    m = re.fullmatch(r'([+-]?)(\d*)(?:\.(\d*))?(?:e([+-]?\d+))?', s)
    if not m:
        raise ValueError(f"Invalid numeric literal: {text!r}")
    frac_part = m.group(3)            # None if no '.'; '' if trailing '.'
    exp_part = int(m.group(4) or 0)
    decimal_places = len(frac_part) if frac_part is not None else 0
    step = Decimal(10) ** Decimal(exp_part - decimal_places)
    return float(step / 2)


def _mass_tolerance(val: Any, node: Any) -> float:
    """Return match tolerance for a mass value literal (VMD decimal-precision convention).

    Delegates to :func:`numeric_tolerance_from_literal` when *node* is a
    :class:`Number` AST node (i.e. the user typed a literal).  All other nodes
    (expressions, variables, etc.) fall back to exact matching (0.0).

    Only applied to the ``mass`` column; other float columns use exact equality.
    """
    return numeric_tolerance_from_literal(str(node.value)) if isinstance(node, Number) else 0.0


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
                if value == '_':
                    # ProDy convention: _ matches empty string, space, and NaN/missing.
                    # CIF uses '.' for missing values and '?' for unknown values.
                    empty_mask = (col == '') | (col == ' ') | (col == '.') | (col == '?')
                    if hasattr(col, 'isna'):
                        empty_mask |= col.isna()
                    mask |= empty_mask
                else:
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
                    # Integer data is sometimes stored as float (e.g. resid with a missing value)
                    try:
                        # if all values are integers, step filtering is valid
                        arr = np.asarray(col, dtype=float)
                        finite = arr[np.isfinite(arr)]
                        integer_valued = finite.size == 0 or bool(np.all(np.mod(finite, 1) == 0)) 
                    except (TypeError, ValueError):
                        integer_valued = True  # if unsure, keep the step (safe for integer data)
                    if integer_valued:
                        range_mask &= ((col - start) % step == 0)
                    else:
                        warnings.warn(
                            f"molselect: step in range {start}:{end}:{step} ignored."
                            f" column has non-integer values or modulo operation is not supported for column type {col.dtype}",
                            RuntimeWarning,
                            stacklevel=2,
                        )
                mask |= range_mask
            else:
                val = v.evaluate(s) if isinstance(v, Node) else v
                # Mass literals match with a decimal-precision tolerance (VMD convention):
                # `mass 12` matches C (12.011) via ±0.5, `mass 12.0` uses the tighter ±0.05.
                # Other float columns keep exact equality.
                is_mass = isinstance(self.field, SelectionKeyword) and self.field.name == 'mass'
                tol = _mass_tolerance(val, v) if is_mass else 0.0
                if tol > 0.0:
                    try:
                        col_is_float = hasattr(col, 'dtype') and col.dtype.kind == 'f'
                    except (AttributeError, TypeError):
                        col_is_float = False
                    mask |= (col >= val - tol) & (col < val + tol) if col_is_float else (col == val)
                else:
                    mask |= (col == val)
        return mask


@dataclass
class Regex(Node):
    field: Node  # always a Node now
    pattern: str
    def evaluate(self, s: Structure) -> Array:
        col = self.field.evaluate(s)
        pattern = self.pattern.evaluate(s)
        # Use protocol method if available
        if hasattr(col, 'str'):
            return col.str.fullmatch(pattern)
        # Fallback: elementwise regex
        import re
        regex = re.compile(pattern)
        found = s.array_values([bool(regex.fullmatch(str(x))) for x in col])
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
        if not mask.any():
            return s.array_filled(False)
        dists = s.minimum_pairwise_distances(s.select(mask))
        result = (dists <= distance)
        if self.mode == "exwithin":
            result[mask] = False
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
class SequenceSelection(Node):
    """Select atoms by matching a 1-letter sequence pattern against residue names.

    The query node is a StringValue (literal match), QuotedStringValue (literal),
    or RegexValue (regex match). Literal strings are treated as exact substrings;
    quoted and regex strings are compiled as regex patterns.

    The selection is chain-aware: sequences are built and matched per-chain independently.
    All residues matching anywhere in any chain are selected.
    """
    query: Node  # StringValue, QuotedStringValue, or RegexValue
    short_circuit = False  # Needs full structure to build sequence

    def evaluate(self, s: Structure) -> Any:
        # 1. Determine the pattern string and whether it's regex
        if isinstance(self.query, RegexValue):
            pattern_str = self.query.value
            is_regex = True
        elif isinstance(self.query, QuotedStringValue):
            pattern_str = self.query.value[1:-1]  # strip quotes
            is_regex = True  # quoted = regex in ProDy convention
        elif isinstance(self.query, StringValue):
            pattern_str = self.query.value
            is_regex = False  # plain string = literal substring
        else:
            # Fallback: treat as literal string
            pattern_str = str(self.query.evaluate(s)) if isinstance(self.query, Node) else str(self.query)
            is_regex = False

        # 2. Compile the regex pattern
        if is_regex:
            regex = re.compile(pattern_str)
        else:
            regex = re.compile(re.escape(pattern_str))

        # 3. Get residue names and residue indices from the structure
        resname_arr = s.get_property('resname')
        residue_arr = s.get_property('residue')

        # Also get chain if available, for chain-aware matching
        has_chain = 'chain' in s.columns
        if has_chain:
            chain_arr = s.get_property('chain')

        # 4. Build per-chain sequences and collect matching residue indices
        #    We iterate atoms in order, grouping by (chain, residue) to preserve order.
        matched_residues = set()

        # Build ordered list of (chain, residue_index, resname) — one per unique residue
        seen = set()
        residue_info = []  # list of (chain, residue_idx, 1-letter code)

        for i in range(s.len()):
            chain_val = str(chain_arr[i]) if has_chain else ''
            res_idx = residue_arr[i]

            # Handle potential NaN or missing residue index
            try:
                res_key = (chain_val, int(res_idx))
            except (ValueError, TypeError):
                continue

            if res_key not in seen:
                seen.add(res_key)
                rn = str(resname_arr[i]).strip()
                code = SEQUENCE_MAP.get(rn)
                if code is None:
                    # Unknown residue (water, ions, ligands) — skip, not part of sequence
                    continue
                residue_info.append((chain_val, int(res_idx), code))

        # 5. Group by chain, build sequence per chain, match
        # Collect chains in order of appearance
        chain_order = []
        chain_residues = {}  # chain -> list of (residue_idx, 1-letter code)
        for chain_val, res_idx, code in residue_info:
            if chain_val not in chain_residues:
                chain_order.append(chain_val)
                chain_residues[chain_val] = []
            chain_residues[chain_val].append((res_idx, code))

        for chain_val in chain_order:
            residues = chain_residues[chain_val]
            seq_str = ''.join(code for _, code in residues)
            res_indices = [idx for idx, _ in residues]

            # Find all matches in this chain's sequence
            for m in regex.finditer(seq_str):
                start, end = m.start(), m.end()
                matched_residues.update(res_indices[start:end])

        # 6. Build the result mask: all atoms whose residue index is in matched set
        if not matched_residues:
            return s.array_filled(False)

        return residue_arr.isin(list(matched_residues))

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

