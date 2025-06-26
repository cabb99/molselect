import pandas as pd
from typing import Union, Sequence, Iterable, Any, Type
from molselect.python.protocols import Mask, Array, Structure

PandasMask = pd.Series  # type: ignore

class PandasArray(pd.Series):
    def set_by_index(self, index: Any, value: Any) -> 'PandasArray':
        arr = self.copy()
        arr.loc[index] = value
        return arr
    def copy(self, deep=True):
        # Use pd.Series.copy and return as PandasArray
        s = super().copy(deep=deep)
        return PandasArray(s.values, index=s.index, name=s.name)
    def isin(self, values):
        return super().isin(pd.Series(values).unique())
    def unique(self):
        return super().unique()
    def str_contains(self, pattern: str, regex: bool = True):
        return self.astype(str).str.contains(pattern, regex=regex)

class PandasStructure:
    def __init__(self, df: pd.DataFrame):
        self.df = df
    def len(self) -> int:
        return len(self.df)
    def get_property(self, key: Union[str, Mask, Sequence[int]]):
        if key == 'index':
            return PandasArray(self.df.index, index=self.df.index, name='index')
        if isinstance(key, str):
            return PandasArray(self.df[key])
        elif isinstance(key, pd.Series) and key.dtype == bool:
            return PandasStructure(self.df[key])
        elif isinstance(key, Sequence) and not isinstance(key, str):
            return PandasStructure(self.df.iloc[list(key)])
        else:
            raise TypeError(f"Unsupported key type: {type(key)}")
    def select(self, mask: Mask) -> 'PandasStructure':
        return PandasStructure(self.df[mask])
    @property
    def index(self):
        return self.df.index
    @property
    def columns(self) -> Iterable[str]:
        return self.df.columns
    def get_coordinates(self, columns: Sequence[str]) -> Any:
        return self.df[list(columns)].values
    def array_filled(self, value: Any) -> PandasArray:
        return PandasArray([value] * len(self.index), index=self.index)
    def array_values(self, values: Iterable[Any]) -> PandasArray:
        return PandasArray(values, index=self.index)
    def minimum_pairwise_distances(self, target: 'PandasStructure') -> pd.DataFrame:
        coords1 = self.df[['x','y','z']].values
        coords2 = target.df[['x','y','z']].values
        d2 = ((coords1[:,None,:] - coords2[None,:,:])**2).sum(axis=2)
        return (d2 ** 0.5).min(axis=1)
    def get_positions(self, indices):
        return self.df.loc[indices][['x','y','z']].values
    def equals(self, other):
        if not isinstance(other, PandasStructure):
            return False
        return self.df.equals(other.df)
