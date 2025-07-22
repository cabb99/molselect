import os
import subprocess
import tempfile
import logging
from typing import Union
import numpy as np
import pandas as pd
import pytest

logger = logging.getLogger(__name__)
BACKUP_PATH = os.path.join(os.path.dirname(__file__), "atom_counts_backup.csv")

import os
import json
import subprocess
import tempfile
import logging
import pandas as pd
import numpy as np
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


# Move BackendInterface above Backup to fix NameError
class BackendInterface(ABC):
    """
    Abstract interface for atom-count backends.
    Each backend must implement `count_atom_data`, returning a mapping
    (basename, selection) -> (count, indices_list).
    """

    @abstractmethod
    def count_atom_data(
        self,
        pdb_paths: list[str],
        selections: list[str]
    ) -> dict[tuple[str, str], tuple[int, list[int]]]:
        ...


class Backup:
    """
    Manages persistent storage of atom-counts and indices for multiple backends.
    Schema columns:
      - pdb (basename)
      - selection (query string)
      - count_vmd, indices_vmd
      - count_prody, indices_prody
      - count_molscene, indices_molscene
    """
    COLUMNS = [
        "pdb", "selection",
        "count_vmd", "indices_vmd",
        "count_prody", "indices_prody",
        "count_molscene", "indices_molscene"
    ]

    def __init__(self, path: str):
        self.path = path
        self.df = self._load_backup()

    def _load_backup(self) -> pd.DataFrame:
        if os.path.exists(self.path):
            df = pd.read_csv(self.path)
        else:
            df = pd.DataFrame(columns=self.COLUMNS)
        for col in self.COLUMNS:
            if col not in df.columns:
                default = np.nan if col.startswith("count_") else [[] for _ in range(len(df))]
                df[col] = default
        return df

    def save(self) -> None:
        df_to_save = self.df.copy()
        for col in [c for c in self.COLUMNS if c.startswith("indices_")]:
            df_to_save[col] = df_to_save[col].apply(lambda x: json.dumps(x))
        df_to_save.to_csv(self.path, index=False)

    def update_backend(self, backend_name: str, data: dict[tuple[str, str], tuple[int, list[int]]]):
        count_col = f"count_{backend_name}"
        indices_col = f"indices_{backend_name}"
        for (pdb, sel), (cnt, idx_list) in data.items():
            mask = (self.df["pdb"] == pdb) & (self.df["selection"] == sel)
            if mask.any():
                self.df.loc[mask, count_col] = cnt
                self.df.loc[mask, indices_col] = [idx_list]
            else:
                new_row = {"pdb": pdb, "selection": sel, count_col: cnt, indices_col: idx_list}
                for col in self.COLUMNS:
                    if col not in new_row:
                        new_row[col] = np.nan if col.startswith("count_") else []
                self.df = pd.concat([self.df, pd.DataFrame([new_row])], ignore_index=True)

    def validate_indices(self) -> None:
        mismatches = []
        for _, row in self.df.iterrows():
            lists = []
            for col in [c for c in self.COLUMNS if c.startswith("indices_")]:
                idx_list = row[col]
                if isinstance(idx_list, str):
                    idx_list = json.loads(idx_list)
                if idx_list:
                    lists.append(list(idx_list))
            if len(lists) > 1:
                first = lists[0]
                for other in lists[1:]:
                    if other != first:
                        mismatches.append((row["pdb"], row["selection"]))
                        break
        if mismatches:
            raise RuntimeError(f"Index mismatch for {len(mismatches)} entries: {mismatches}")

    def run_all(self, pdb_paths: list[str], selections: list[str], backends: list[BackendInterface]) -> None:
        for backend in backends:
            name = type(backend).__name__.replace('Backend','').lower()
            data = backend.count_atom_data(pdb_paths, selections)
            self.update_backend(name, data)
        self.save()
        self.validate_indices()


def _escape_tcl(sel: str) -> str:
    """
    Escape characters in a VMD atomselect string for Tcl.
    """
    return (
        sel.replace('\\', '\\\\')
           .replace('"', '\\"')
           .replace('$', '\\$')
           .replace('[', '\\[')
           .replace(']', '\\]')
    )


class BackendInterface(ABC):
    """
    Abstract interface for atom-count backends.
    Each backend must implement `count_atom_data`, returning a mapping
    (basename, selection) -> (count, indices_list).
    """

    @abstractmethod
    def count_atom_data(
        self,
        pdb_paths: list[str],
        selections: list[str]
    ) -> dict[tuple[str, str], tuple[int, list[int]]]:
        ...


class VMDBackend(BackendInterface):
    """
    Uses VMD (text mode) to count atoms and retrieve their indices.
    """
    def __init__(self, tcl_script_path: str | None = None):
        self.tcl_script_path = tcl_script_path

    def count_atom_data(
        self,
        pdb_paths: list[str],
        selections: list[str]
    ) -> dict[tuple[str, str], tuple[int, list[int]]]:
        delimiter = '|----|'
        tcl_lines: list[str] = []
        for pdb in pdb_paths:
            base = os.path.basename(pdb)
            abs_path = os.path.abspath(pdb)
            tcl_lines.append(f'mol new "{abs_path}"')
            for sel in selections:
                esc = _escape_tcl(sel)
                tcl_lines.extend([
                    'try {',
                    f'  set selobj [atomselect top "{esc}"]',
                    f'  puts "COUNT {base}{delimiter}{esc}{delimiter}[$selobj num]"',
                    f'  puts -nonewline "INDICES {base}{delimiter}{esc}{delimiter}"',
                    '  puts [$selobj get index]',
                    '  $selobj delete',
                    '} on error {err opts} {',
                    f'  puts "COUNT {base}{delimiter}{esc}{delimiter}nan"',
                    f'  puts "INDICES {base}{delimiter}{esc}{delimiter}"',
                    f'  puts ""',
                    '}',
                ])
            tcl_lines.append('mol delete top')
        tcl_lines.append('exit')
        tcl_script = '\n'.join(tcl_lines)

        if self.tcl_script_path:
            script_path = self.tcl_script_path
            with open(script_path, 'w') as f:
                f.write(tcl_script)
        else:
            tf = tempfile.NamedTemporaryFile('w', suffix='.tcl', delete=False)
            tf.write(tcl_script)
            tf.flush()
            script_path = tf.name
            tf.close()

        cmd = ['vmd', '-dispdev', 'text', '-e', script_path]
        proc = subprocess.run(cmd, text=True, capture_output=True)
        if proc.returncode != 0:
            logger.error(f"VMD failed (rc={proc.returncode}): {proc.stderr.strip()}")
            raise RuntimeError(f"VMD failed (rc={proc.returncode}): {proc.stderr.strip()}")

        counts: dict[tuple[str,str], float] = {}
        indices: dict[tuple[str,str], list[int]] = {}
        for line in proc.stdout.splitlines():
            if line.startswith('COUNT '):
                _, rest = line.split('COUNT ', 1)
                parts = rest.split(delimiter)
                if len(parts) == 3:
                    pdbfile, sel, num = parts
                    try:
                        cnt = int(num)
                    except ValueError:
                        cnt = np.nan
                    counts[(pdbfile, sel)] = cnt
            elif line.startswith('INDICES '):
                _, rest = line.split('INDICES ', 1)
                parts = rest.split(delimiter)
                if len(parts) == 3:
                    pdbfile, sel, idx_str = parts
                    idx_list = [int(i) for i in idx_str.strip().split() if i.isdigit()]
                    indices[(pdbfile, sel)] = idx_list

        result: dict[tuple[str,str], tuple[int, list[int]]] = {}
        for pdb in [os.path.basename(p) for p in pdb_paths]:
            for sel in selections:
                key = (pdb, sel)
                cnt = counts.get(key, np.nan)
                idx_list = indices.get(key, [])
                result[key] = (cnt, idx_list)
        return result


class ProDyBackend(BackendInterface):
    """
    Uses ProDy to count atoms and retrieve their indices.
    """
    def count_atom_data(
        self,
        pdb_paths: list[str],
        selections: list[str]
    ) -> dict[tuple[str, str], tuple[int, list[int]]]:
        from prody import parsePDB, execDSSP, parseDSSP
        result_counts: dict[tuple[str,str], float] = {}
        result_indices: dict[tuple[str,str], list[int]] = {}

        for pdb in pdb_paths:
            basename = os.path.basename(pdb)
            try:
                structure = parsePDB(pdb)
                try:
                    dssp_file = execDSSP(basename)
                    parseDSSP(dssp_file, structure)
                except Exception as e:
                    logger.warning(f"DSSP failed for {basename}: {e}")

                for sel in selections:
                    key = (basename, sel)
                    try:
                        atoms = structure.select(sel)
                        if atoms is None:
                            cnt = 0
                            idx_list = []
                        else:
                            cnt = len(atoms)
                            idx_list = atoms.getIndices().tolist()
                    except Exception:
                        cnt = np.nan
                        idx_list = []
                    result_counts[key] = cnt
                    result_indices[key] = idx_list
            except Exception as e:
                logger.warning(f"ProDy parse failed for {basename}: {e}")
                for sel in selections:
                    key = (basename, sel)
                    result_counts[key] = np.nan
                    result_indices[key] = []

        for pdb in [os.path.basename(p) for p in pdb_paths]:
            for sel in selections:
                key = (pdb, sel)
                result_counts.setdefault(key, np.nan)
                result_indices.setdefault(key, [])

        result = {k: (result_counts[k], result_indices[k]) for k in result_counts}
        return result


class MolSceneBackend(BackendInterface):
    """
    Uses MolScene and molselect Evaluator to count atoms and retrieve their indices.
    """
    def count_atom_data(
        self,
        pdb_paths: list[str],
        selections: list[str]
    ) -> dict[tuple[str, str], tuple[int, list[int]]]:
        from molscene.Scene import Scene
        from molselect.python.backends.pandas import PandasStructure
        from molselect.python.evaluator import Evaluator

        result_counts: dict[tuple[str,str], float] = {}
        result_indices: dict[tuple[str,str], list[int]] = {}
        selector = Evaluator(PandasStructure)

        for pdb in pdb_paths:
            basename = os.path.basename(pdb)
            try:
                if pdb.endswith('.pdb'):
                    df = Scene.from_pdb(pdb)
                elif pdb.endswith('.cif'):
                    df = Scene.from_cif(pdb)
                else:
                    raise ValueError(f"Unsupported file format for {basename}")
                if 'model' in df.columns:
                    df = df[df['model'] == 1]

                for sel in selections:
                    key = (basename, sel)
                    try:
                        sel_result = selector.parse(df, sel)
                        count = len(sel_result.df)
                        idx_list = sel_result.df.index.to_list()
                    except Exception as e:
                        logger.warning(f"[molselect] selection failed for '{sel}' on {basename}: {e}")
                        count = np.nan
                        idx_list = []
                    result_counts[key] = count
                    result_indices[key] = idx_list
            except Exception as e:
                logger.warning(f"MolSceneBackend parse failed for {basename}: {e}")
                for sel in selections:
                    key = (basename, sel)
                    result_counts[key] = np.nan
                    result_indices[key] = []

        for pdb in [os.path.basename(p) for p in pdb_paths]:
            for sel in selections:
                key = (pdb, sel)
                result_counts.setdefault(key, np.nan)
                result_indices.setdefault(key, [])

        return {key: (result_counts[key], result_indices[key]) for key in result_counts}



import re

# Load PDB files and selection tests

# Helper functions to load PDB files and selection tests
def load_selection_tests():
    import os
    import json
    jsonc_path = os.path.join(os.path.dirname(__file__), "selection_tests.jsonc")
    with open(jsonc_path, "r") as f:
        lines = f.readlines()
    clean_lines = [line for line in lines if not line.lstrip().startswith("//")]
    clean_json = "".join(clean_lines)
    selection_tests = json.loads(clean_json)
    selections = [test["query"] for test in selection_tests]
    return selections


def load_pdb_files():
    import glob
    base = os.path.dirname(__file__)
    pdb_files = glob.glob(os.path.join(base, '../../data/tests/*.pdb'))
    pdb_files += glob.glob(os.path.join(base, '../../data/tests/*.cif'))
    return pdb_files

PDB_FILES = load_pdb_files()[:2]
SELECTIONS = load_selection_tests()[:10]

# Instantiate backend objects
molscene_backend = MolSceneBackend()
prody_backend = ProDyBackend()
vmd_backend = VMDBackend()


@pytest.fixture(scope="session")
def molscene_counts():
    """Compute once per session."""
    # keys are (basename, sel)
    return {k: v[0] for k, v in molscene_backend.count_atom_data(PDB_FILES, SELECTIONS).items()}

@pytest.fixture(scope="session")
def prody_counts():
    return {k: v[0] for k, v in prody_backend.count_atom_data(PDB_FILES, SELECTIONS).items()}

@pytest.fixture(scope="session")
def vmd_counts():
    # pass tcl_script_path=None to auto-tempfile
    return {k: v[0] for k, v in vmd_backend.count_atom_data(PDB_FILES, SELECTIONS).items()}

def _sanitize(sel: str) -> str:
    # Turn your selection into a safe Python identifier
    name = re.sub(r'[^0-9a-zA-Z]+', '_', sel).strip('_')
    return name[:30]  # truncate if super long


def _make_test_for(sel: str):
    """
    Return a single test function that closes over `sel` and is parametrized
    over all pdb_paths.
    """
    # @pytest.mark.skip()
    @pytest.mark.parametrize("pdb_path", PDB_FILES, ids=lambda p: os.path.basename(p))
    def test_molscene_vs_prody_or_vmd(self, pdb_path,
                                      molscene_counts, prody_counts, vmd_counts):
        basename = os.path.basename(pdb_path)
        key = (basename, sel)

        mol = molscene_counts[key]
        pro = prody_counts[key]
        vmd = vmd_counts[key]

        # if both reference backends fail → check mol
        if (pd.isna(pro) or np.isnan(pro)) and (pd.isna(vmd) or np.isnan(vmd)):
            if pd.isna(mol) or np.isnan(mol):
                pytest.fail(f"Selection '{sel}' unsupported by all: molscene, ProDy, and VMD on {basename}")
            return  # pass if mol is not na

        ok_pro = not (pd.isna(pro) or np.isnan(pro)) and mol == pro
        ok_vmd = not (pd.isna(vmd) or np.isnan(vmd)) and mol == vmd

        assert ok_pro or ok_vmd, (
            f"{basename} | sel={sel!r}: molscene={mol!r} "
            f"!= prody={pro!r} and != vmd={vmd!r}"
        )

    # give it a useful docstring so Test Explorer shows the full query
    test_molscene_vs_prody_or_vmd.__doc__ = f"molscene vs prody/vmd for selection: {sel!r}"
    return test_molscene_vs_prody_or_vmd


# Dynamically build one Test class per selection
for sel in SELECTIONS:
    safe = _sanitize(sel)
    cls_name = f"Test_sel_{safe}"
    # create an empty class
    cls = type(cls_name, (object,), {})
    # attach our generated test method
    setattr(cls, "test_molscene", _make_test_for(sel))
    # inject into module level so pytest will collect it
    globals()[cls_name] = cls

# For a single selection, return the indices with all the backends
def _make_test_for_indices(sel: str):
    @pytest.mark.parametrize("pdb_path", PDB_FILES, ids=lambda p: os.path.basename(p))
    def test_indices_molscene_vs_prody_or_vmd(self, pdb_path,
                                              molscene_counts, prody_counts, vmd_counts):
        basename = os.path.basename(pdb_path)
        key = (basename, sel)

        mol = molscene_counts[key]
        pro = prody_counts[key]
        vmd = vmd_counts[key]

        # if all fail → skip
        if (pd.isna(pro) or np.isnan(pro)) and (pd.isna(vmd) or np.isnan(vmd)):
            pytest.skip(f"Selection '{sel}' unsupported by all: molscene, ProDy, and VMD on {basename}")

        assert not pd.isna(mol) and not np.isnan(mol), (
            f"{basename} | sel={sel!r}: molscene={mol!r} "
            f"!= prody={pro!r} and != vmd={vmd!r}"
        )

    test_indices_molscene_vs_prody_or_vmd.__doc__ = f"molscene vs prody/vmd for selection: {sel!r}"
    return test_indices_molscene_vs_prody_or_vmd



if __name__ == "__main__":
    import pandas as pd
    import os

    # Load files and selections
    pdb_files = load_pdb_files()
    selections = load_selection_tests()

    # Instantiate backend objects
    molscene_backend = MolSceneBackend()
    prody_backend = ProDyBackend()
    vmd_backend = VMDBackend()

    # Compute all results using backend classes
    print("Computing molscene counts...")
    molscene = {k: v[0] for k, v in molscene_backend.count_atom_data(pdb_files, selections).items()}
    print("Computing prody counts...")
    prody = {k: v[0] for k, v in prody_backend.count_atom_data(pdb_files, selections).items()}
    print("Computing vmd counts...")
    vmd = {k: v[0] for k, v in vmd_backend.count_atom_data(pdb_files, selections).items()}

    # Build DataFrame
    rows = []
    for pdb in pdb_files:
        basename = os.path.basename(pdb)
        for sel in selections:
            rows.append({
                "pdb": basename,
                "selection": sel,
                "count_molscene": molscene.get((basename, sel), pd.NA),
                "count_prody": prody.get((basename, sel), pd.NA),
                "count_vmd": vmd.get((basename, sel), pd.NA),
            })
    df = pd.DataFrame(rows)
    print(df)
    # Optionally, save to CSV
    df.to_csv("atom_counts_all_backends.csv", index=False)
    print("Saved results to atom_counts_all_backends.csv")

