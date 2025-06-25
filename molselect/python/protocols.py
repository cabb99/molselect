import abc
from typing import Protocol, runtime_checkable, Union, Sequence, Any

@runtime_checkable
class Mask(Protocol):
    """Boolean array of length N."""
    def __and__(self,  other: 'Mask') -> 'Mask': ...
    def __or__(self,   other: 'Mask') -> 'Mask': ...
    def __xor__(self,  other: 'Mask') -> 'Mask': ...
    def __invert__(self)           -> 'Mask': ...
    def any(self)                  -> bool: ...
    def all(self)                  -> bool: ...
    def __getitem__(self, idx: Any) -> 'Mask': ...  # e.g. submask

class MaskABC(abc.ABC):
    @abc.abstractmethod
    def __iter__(self):
        pass
    def __and__(self, other: 'Mask') -> 'Mask':
        return type(self)([a and b for a, b in zip(self, other)])
    def __or__(self, other: 'Mask') -> 'Mask':
        return type(self)([a or b for a, b in zip(self, other)])
    def __xor__(self, other: 'Mask') -> 'Mask':
        return type(self)([bool(a) ^ bool(b) for a, b in zip(self, other)])
    def __invert__(self) -> 'Mask':
        return type(self)([not a for a in self])
    def any(self) -> bool:
        return any(self)
    def all(self) -> bool:
        return all(self)
    def __getitem__(self, idx: Any) -> 'Mask':
        # Default: assume self is indexable and returns same type
        return type(self)(list(self)[idx])

@runtime_checkable
class Array(Protocol):
    """Supports comparisons, arithmetic, and casting to bool masks."""
    # comparisons → Mask
    def __eq__(self,  other: 'Array') -> Mask: ...
    def __ne__(self,  other: 'Array') -> Mask: ...
    def __lt__(self,  other: 'Array') -> Mask: ...
    def __le__(self,  other: 'Array') -> Mask: ...
    def __gt__(self,  other: 'Array') -> Mask: ...
    def __ge__(self,  other: 'Array') -> Mask: ...

    # arithmetic → ArrayLike
    def __add__(self,  other: 'Array') -> Any: ...
    def __sub__(self,  other: 'Array') -> Any: ...
    def __mul__(self,  other: 'Array') -> Any: ...
    def __truediv__(self, other: 'Array') -> Any: ...
    def __floordiv__(self, other: 'Array') -> Any: ...
    def __mod__(self,  other: 'Array') -> Any: ...
    def __pow__(self,  other: 'Array') -> Any: ...
    def __neg__(self)              -> Any: ...

    # to support regex / Comparison(None)
    def astype(self, dtype: Any)  -> Any: ...  

    # short-circuit checks
    def any(self) -> bool: ...
    def all(self) -> bool: ...
    def __getitem__(self, idx: Any) -> Any: ...  # e.g. for sub-arrays

class ArrayABC(abc.ABC):
    @abc.abstractmethod
    def __iter__(self):
        pass
    def __eq__(self, other: 'Array') -> Mask:
        return type(self)([a == b for a, b in zip(self, other)])
    def __ne__(self, other: 'Array') -> Mask:
        return type(self)([a != b for a, b in zip(self, other)])
    def __lt__(self, other: 'Array') -> Mask:
        return type(self)([a < b for a, b in zip(self, other)])
    def __le__(self, other: 'Array') -> Mask:
        return type(self)([a <= b for a, b in zip(self, other)])
    def __gt__(self, other: 'Array') -> Mask:
        return type(self)([a > b for a, b in zip(self, other)])
    def __ge__(self, other: 'Array') -> Mask:
        return type(self)([a >= b for a, b in zip(self, other)])
    # Arithmetic methods can be similarly implemented if needed.
    @abc.abstractmethod
    def any(self) -> bool:
        pass
    @abc.abstractmethod
    def all(self) -> bool:
        pass
    @abc.abstractmethod
    def __getitem__(self, idx: Any) -> Any:
        pass
    @abc.abstractmethod
    def astype(self, dtype: Any) -> Any:
        pass

# The container of atoms/residues/etc.:
@runtime_checkable
class Structure(Protocol):
    """Any per-atom container, indexed either by name or by mask/indices."""
    def len(self) -> int: ...
    def get_property( 
        self, 
        key: Union[str, Mask, Sequence[int]] 
    ) -> Union[Array]:
        """
        - If key is a str → return a 1-D data array of length N (ArrayLike)  
        - If key is a boolean Mask or list of ints → return a new StructureLike
        """
    
    def select(self, mask:Mask) -> 'Structure':
        """Return a new StructureLike with the same properties, but no selection."""
