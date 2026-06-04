import json
import math
import os
import re
import sys
import warnings
from decimal import Decimal
import numpy as np
from dataclasses import dataclass
from typing import Any, Optional, Union
from typing_extensions import Protocol, runtime_checkable
from molselect.python.protocols import Array, Structure
from molselect.python.errors import MolSelectEvaluationError

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

# ---------------------------------------------------------------------------
# Domain sanitization for math functions
# ---------------------------------------------------------------------------
_DOMAIN_TOLERANCE = 1e-6

# Each entry: (lower_bound, upper_bound, clamp_low, clamp_high)
# None means unbounded on that side; clamp values are what near-boundary values get clamped to.
_FUNC_DOMAINS = {
    'arcsin': (-1.0, 1.0, -1.0, 1.0),
    'arccos': (-1.0, 1.0, -1.0, 1.0),
    'sqrt':   (0.0, None, 0.0, None),
    'log':    (0.0, None, sys.float_info.min, None),    # 0 itself → -inf (numpy default), keep
    'log10':  (0.0, None, sys.float_info.min, None),
}


def _sanitize_domain(name, v, tol=_DOMAIN_TOLERANCE):
    """Clamp near-boundary floating-point artifacts and count far-out-of-domain values.

    Returns (sanitized_value, n_far_violations, n_total_elements).
    Near-boundary values (within *tol* of a domain edge) are silently clamped.
    Far out-of-domain values are left unchanged (numpy will produce NaN).
    """
    if name not in _FUNC_DOMAINS:
        return v, 0, 0

    lo, hi, clamp_lo, clamp_hi = _FUNC_DOMAINS[name]

    # Operate on a numpy array for uniform handling; reconstruct original type at the end.
    is_scalar = np.ndim(v) == 0
    arr = np.asarray(v, dtype=float)
    n_total = arr.size
    n_far = 0

    if lo is not None:
        below = arr < lo
        if below.any():
            near_mask = below & (arr >= lo - tol)
            far_mask = below & ~near_mask
            n_far += int(far_mask.sum())
            arr = np.where(near_mask, clamp_lo, arr)

    if hi is not None:
        above = arr > hi
        if above.any():
            near_mask = above & (arr <= hi + tol)
            far_mask = above & ~near_mask
            n_far += int(far_mask.sum())
            arr = np.where(near_mask, clamp_hi, arr)

    # Reconstruct original container type
    if is_scalar:
        result = float(arr)
    else:
        try:
            import pandas as pd
            if isinstance(v, pd.Series):
                result = pd.Series(arr, index=v.index, name=v.name)
            else:
                result = arr
        except ImportError:
            result = arr

    return result, n_far, n_total


# Binding strength for addind parentheses in symbolic rendering: higher means tighter binding, fewer parentheses.
_PREC_ATOM = 100


class Node:
    """Base AST node; subclasses implement eager and symbolic evaluation."""
    short_circuit = True
    _symbol: Optional[str] = None       
    _precedence = _PREC_ATOM  # binding strength for adding parens in symbolic rendering

    def evaluate(self, s: Structure) -> Any:
        raise NotImplementedError

    @staticmethod
    def _sym(x: Any) -> str:
        """Render *x* as selection syntax: a Node via ``symbolic()``, else ``str(x)``."""
        return x.symbolic() if isinstance(x, Node) else str(x)

    @staticmethod
    def _operand(child: Any, parent_prec: int, is_right: bool) -> str:
        """Render *child* of a binary op, adding parens only when precedence requires.

        A child is wrapped when it binds looser than the parent, or binds equally
        and sits on the right (since operators are left-associative).
        """
        inner = Node._sym(child)
        if isinstance(child, Node):
            cp = getattr(child, '_precedence', _PREC_ATOM)
            if cp < parent_prec or (cp == parent_prec and is_right):
                return f"({inner})"
        return inner

    @staticmethod
    def _prefix(child: Any, parent_prec: int) -> str:
        """Render the operand of a prefix op (not/neg), wrapping only if it binds looser."""
        inner = Node._sym(child)
        if isinstance(child, Node) and getattr(child, '_precedence', _PREC_ATOM) < parent_prec:
            return f"({inner})"
        return inner

    def symbolic(self) -> str:
        try:
            names = [n for n in getattr(self, '__dataclass_fields__', {}) if n != '_symbol']
            parts = [self._sym(getattr(self, n)) for n in names]
            return f"{type(self).__name__}(" + ", ".join(parts) + ")"
        except Exception:
            return type(self).__name__

class BinaryOp(Node):
    """Infix binary operator: renders as ``left <symbol> right``, parenthesizing
    operands only where precedence/associativity require it."""
    left: Node
    right: Node
    def symbolic(self) -> str:
        left = self._operand(self.left, self._precedence, is_right=False)
        right = self._operand(self.right, self._precedence, is_right=True)
        return f"{left} {self._symbol} {right}"


@dataclass
class Start(Node):
    """Root node of the AST, contains the main expression."""
    expr: Node
    def evaluate(self, s: Structure) -> Structure:
        """Evaluate the main expression and return a boolean mask."""
        selection = self.expr.evaluate(s)
        return s.select(selection)
    def symbolic(self) -> str:
        return self.expr.symbolic()

@dataclass
class And(BinaryOp):
    left: Node
    right: Node
    _symbol: str = "and"
    _precedence = 3
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
class Or(BinaryOp):
    left: Node
    right: Node
    _symbol: str = "or"
    _precedence = 1
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
class Xor(BinaryOp):
    left: Node
    right: Node
    _symbol: str = "xor"
    _precedence = 2

    def evaluate(self, s: Structure) -> Array:
        return self.left.evaluate(s) ^ self.right.evaluate(s)

@dataclass
class Not(Node):
    expr: Node
    _symbol: str = "~"
    _precedence = 4
    def evaluate(self, s: Structure) -> Array:
        return ~self.expr.evaluate(s)
    def symbolic(self) -> str:
        return f"not {self._prefix(self.expr, self._precedence)}"
    
@dataclass
class All(Node):
    def evaluate(self, s):
        return s.array_filled(True)
    def symbolic(self) -> str:
        return "all"

@dataclass
class None_(Node):
    def evaluate(self, s):
        return s.array_filled(False)
    def symbolic(self) -> str:
        return "none"

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
        # A comparison's operands are complete math expressions / atoms, so they
        # never need parentheses. A None value means "truthiness of field" only.
        if self.value is None:
            return self._sym(self.field)
        return f"{self._sym(self.field)} {self.op} {self._sym(self.value)}"

## Data Values
class DataValue(Node):
    """Base class for data values that do not evaluate to a Series."""
    def evaluate(self, s: Structure) -> Any:
        raise NotImplementedError(f"{self.__class__.__name__} should not be evaluated directly.")

@dataclass
class RangeValue(DataValue):
    start: Node
    end: Node
    step: Optional[Node] = None
    def evaluate(self, s: Structure):
        start = self.start.evaluate(s) if isinstance(self.start, Node) else self.start
        end = self.end.evaluate(s) if isinstance(self.end, Node) else self.end
        step = self.step.evaluate(s) if isinstance(self.step, Node) else self.step
        return start, end, step
    def symbolic(self) -> str:
        if self.step is None:
            return f"{self._sym(self.start)} to {self._sym(self.end)}"
        return f"{self._sym(self.start)}:{self._sym(self.end)}:{self._sym(self.step)}"

   
@dataclass
class StringValue(DataValue):
    """Represents a string value in the AST."""
    value: str
    def evaluate(self, s: Structure) -> str:
        return self.value
    def symbolic(self) -> str:
        return self.value

@dataclass
class QuotedStringValue(DataValue):
    """Represents a quoted string value in the AST."""
    value: str
    def evaluate(self, s: Structure) -> str:
        return self.value[1:-1]  # Remove quotes
    def symbolic(self) -> str:
        return self.value  # already includes the surrounding quotes

@dataclass
class RegexValue(DataValue):
    """Represents a regex value in the AST."""
    value: str
    def evaluate(self, s: Structure) -> str:
        return self.value
    def symbolic(self) -> str:
        return f'"{self.value}"'  # value is stored without the quotes; re-wrap

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

    def symbolic(self) -> str:
        values = " ".join(self._sym(v) for v in self.values)
        return f"{self.field.symbolic()} {values}"


@dataclass
class Regex(Node):
    field: Node  # always a Node now
    pattern: Node
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

    def symbolic(self) -> str:
        return f"{self.field.symbolic()} =~ {self._sym(self.pattern)}"


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

    # `... of <expr>` is greedy to the end of the expression, so a Within binds
    # looser than any logical operator and must be wrapped when used as an operand.
    _precedence = 0
    def symbolic(self) -> str:
        return f"{self.mode} {self._sym(self.distance)} of {self.target_mask.symbolic()}"

@dataclass
class Same(Node):
    field: Node  # always a Node now
    mask: Node
    short_circuit = False # Needs access to all points, so no short-circuiting
    def evaluate(self, s):
        col = self.field.evaluate(s)
        mask = self.mask.evaluate(s)
        return col.isin(col[mask])

    _precedence = 0  # `... as <expr>` is greedy; must be wrapped as a logical operand
    def symbolic(self) -> str:
        return f"same {self.field.symbolic()} as {self.mask.symbolic()}"

@dataclass
class SelectionKeyword(Node):
    name: str
    def evaluate(self, s):
        if self.name == 'index':
            # Return a flat array of the index, not a nested list
            return s.get_property('index')
        if self.name not in s.columns:
            raise MolSelectEvaluationError(
                f"Column '{self.name}' not found in structure", node=self, backend=s)
        return s.get_property(self.name)

    def symbolic(self) -> str:
        return self.name

@dataclass
class Bonded(Node):
    distance: float
    selection: Node
    mode: str = "bonded"  # "bonded" or "exbonded"
    short_circuit = False # Needs access to all points, so no short-circuiting
    def evaluate(self, s):
        raise NotImplementedError("Bonded selection not implemented.")

    _precedence = 0  # `... to <expr>` is greedy; must be wrapped as a logical operand
    def symbolic(self) -> str:
        return f"{self.mode} {self._sym(self.distance)} to {self.selection.symbolic()}"

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

        # 3. Get residue indices for the mask
        residue_arr = s.get_property('residue')

        # Fast path: if the backend provides get_sequence(), use it to avoid the Python loop.
        # get_sequence(sequence_map) returns dict: chain -> (sequence_str, residue_indices_list)
        get_sequence = getattr(s, 'get_sequence', None)
        if get_sequence is not None:
            chain_sequences = get_sequence(SEQUENCE_MAP)
        else:
            chain_sequences = self._build_sequences(s)

        # 4. Match regex against each chain's sequence
        matched_residues = set()
        for chain_val, (seq_str, res_indices) in chain_sequences.items():
            for m in regex.finditer(seq_str):
                matched_residues.update(res_indices[m.start():m.end()])

        # 5. Build the result mask: all atoms whose residue index is in matched set
        if not matched_residues:
            return s.array_filled(False)

        return residue_arr.isin(list(matched_residues))

    def symbolic(self) -> str:
        return f"sequence {self._sym(self.query)}"

    @staticmethod
    def _build_sequences(s: Structure) -> dict:
        """Generic fallback: build per-chain 1-letter sequences by iterating atoms.

        Returns:
            dict mapping chain_id -> (sequence_str, list_of_residue_indices)
        """
        resname_arr = s.get_property('resname')
        residue_arr = s.get_property('residue')
        has_chain = 'chain' in s.columns
        if has_chain:
            chain_arr = s.get_property('chain')

        seen = set()
        residue_info = []
        for i in range(s.len()):
            chain_val = str(chain_arr[i]) if has_chain else ''
            res_idx = residue_arr[i]
            try:
                res_key = (chain_val, int(res_idx))
            except (ValueError, TypeError):
                continue
            if res_key not in seen:
                seen.add(res_key)
                rn = str(resname_arr[i]).strip()
                code = SEQUENCE_MAP.get(rn)
                if code is None:
                    continue
                residue_info.append((chain_val, int(res_idx), code))

        chain_order = []
        chain_residues = {}
        for chain_val, res_idx, code in residue_info:
            if chain_val not in chain_residues:
                chain_order.append(chain_val)
                chain_residues[chain_val] = []
            chain_residues[chain_val].append((res_idx, code))

        result = {}
        for chain_val in chain_order:
            residues = chain_residues[chain_val]
            seq_str = ''.join(code for _, code in residues)
            res_indices = [idx for idx, _ in residues]
            result[chain_val] = (seq_str, res_indices)
        return result

# Mathematical Operations
@dataclass
class Add(BinaryOp):
    left: Node
    right: Node
    _symbol: str = "+"
    _precedence = 5
    def evaluate(self, s):
        return self.left.evaluate(s) + self.right.evaluate(s)

@dataclass
class Sub(BinaryOp):
    left: Node
    right: Node
    _symbol: str = "-"
    _precedence = 5
    def evaluate(self, s):
        return self.left.evaluate(s) - self.right.evaluate(s)

@dataclass
class Mul(BinaryOp):
    left: Node
    right: Node
    _symbol: str = "*"
    _precedence = 6
    def evaluate(self, s):
        return self.left.evaluate(s) * self.right.evaluate(s)

@dataclass
class Div(BinaryOp):
    left: Node
    right: Node
    _symbol: str = "/"
    _precedence = 6
    def evaluate(self, s):
        return self.left.evaluate(s) / self.right.evaluate(s)

@dataclass
class FloorDiv(BinaryOp):
    left: Node
    right: Node
    _symbol: str = "//"
    _precedence = 6
    def evaluate(self, s):
        return self.left.evaluate(s) // self.right.evaluate(s)

@dataclass
class Mod(BinaryOp):
    left: Node
    right: Node
    _symbol: str = "%"
    _precedence = 6
    def evaluate(self, s):
        return self.left.evaluate(s) % self.right.evaluate(s)

@dataclass
class Pow(BinaryOp):
    left: Node
    right: Node
    _symbol: str = "**"
    _precedence = 7
    def evaluate(self, s):
        return self.left.evaluate(s) ** self.right.evaluate(s)

@dataclass
class Neg(Node):
    value: Node
    _symbol: str = "-"
    _precedence = 8
    def evaluate(self, s):
        return -self.value.evaluate(s)
    def symbolic(self) -> str:
        return f"-{self._prefix(self.value, self._precedence)}"

@dataclass
class Func(Node):
    name: str
    arg: Node
    _symbol: Optional[str] = None
    def evaluate(self, s):
        v = self.arg.evaluate(s)
        if self.name == 'sq':
            return v ** 2
        if self.name == 'abs':
            return np.abs(v)
        v, n_far, n_total = _sanitize_domain(self.name, v)
        if n_far > 0:
            # Render the offending sub-expression so the user can pinpoint the
            # failing part of the selection. Keep this purely diagnostic: never
            # let a symbolic-rendering failure break evaluation.
            try:
                where = f" in `{self.symbolic()}`"
            except Exception:
                where = ""
            warnings.warn(
                f"molselect: {self.name}(): {n_far} of {n_total} values outside domain"
                f"{where}, returned as NaN",
                RuntimeWarning,
                stacklevel=2,
            )
        with np.errstate(invalid='ignore', divide='ignore'):
            return getattr(np, self.name)(v)

    def symbolic(self) -> str:
        return f"{self.name}({self._sym(self.arg)})"

@dataclass
class Number(Node):
    value: str
    _symbol: Optional[str] = None
    def evaluate(self, s):
        v = self.value
        if '.' in v or 'e' in v or 'E' in v:
            return float(v)
        return int(v)
    def symbolic(self) -> str:
        return str(self.value)

@dataclass
class Const(Node):
    name: str
    _symbol: Optional[str] = None
    def evaluate(self, s):
        if self.name.lower() == 'pi':
            return math.pi
        elif self.name.lower() == 'e':
            return math.e
        else:
            raise MolSelectEvaluationError(f"Unknown constant '{self.name}'", node=self)
    def symbolic(self) -> str:
        return self.name

