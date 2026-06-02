import os
import json
import re
import subprocess
import tempfile
import logging
from abc import ABC, abstractmethod

import numpy as np
import pandas as pd
import pytest

logger = logging.getLogger(__name__)
BACKUP_PATH = os.path.join(os.path.dirname(__file__), "atom_counts_backup.csv")


class BackendInterface(ABC):
    """
    Abstract interface for atom-count backends.
    Each backend must implement `count_atom_data`, returning a mapping
    (basename, selection_query) -> (count, indices_list).
    """

    @abstractmethod
    def count_atom_data(
        self,
        pdb_paths: list[str],
        selections: list[dict[str, str]]
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


class VMDBackend(BackendInterface):
    """
    Uses VMD (text mode) to count atoms and retrieve their indices.
    Supports a vmd_query override per selection.
    """
    def __init__(self, tcl_script_path: str | None = None):
        self.tcl_script_path = tcl_script_path

    def _get_vmd_query(self, sel: dict) -> str:
        """Resolve which query string VMD should use for this selection."""
        return sel['vmd_query'] if 'vmd_query' in sel else sel['query']

    def count_atom_data(
        self,
        pdb_paths: list[str],
        selections: list[dict[str, str]]
    ) -> dict[tuple[str, str], tuple[int, list[int]]]:
        delimiter = '|----|'
        tcl_lines: list[str] = []
        for pdb in pdb_paths:
            base = os.path.basename(pdb)
            abs_path = os.path.abspath(pdb)
            tcl_lines.append(f'mol new "{abs_path}"')
            for sel in selections:
                esc_for_comparison = _escape_tcl(sel['query'])
                vmd_sel = self._get_vmd_query(sel)
                esc = _escape_tcl(vmd_sel)
                tcl_lines.extend([
                    'try {',
                    f'  set selobj [atomselect top "{esc}" frame 0]',
                    f'  puts "COUNT {base}{delimiter}{esc_for_comparison}{delimiter}[$selobj num]"',
                    f'  puts -nonewline "INDICES {base}{delimiter}{esc_for_comparison}{delimiter}"',
                    '  puts [$selobj get index]',
                    '  $selobj delete',
                    '} on error {err opts} {',
                    f'  puts "COUNT {base}{delimiter}{esc_for_comparison}{delimiter}nan"',
                    f'  puts "INDICES {base}{delimiter}{esc_for_comparison}{delimiter}"',
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

        counts: dict[tuple[str, str], float] = {}
        indices: dict[tuple[str, str], list[int]] = {}
        with open("vmd_output.txt", "w+") as f:
            for line in proc.stdout.splitlines():
                f.write(line + "\n")
                if line.startswith('COUNT '):
                    _, rest = line.split('COUNT ', 1)
                    parts = rest.split(delimiter)
                    if len(parts) == 3:
                        pdbfile, sel_str, num = parts
                        try:
                            cnt = int(num)
                        except ValueError:
                            cnt = np.nan
                        if (pdbfile, sel_str) in counts:
                            f.write(f'REPEATED COUNTKEY: {(pdbfile, sel_str)}\n')
                        counts[(pdbfile, sel_str)] = cnt
                        
                elif line.startswith('INDICES '):
                    _, rest = line.split('INDICES ', 1)
                    parts = rest.split(delimiter)
                    if len(parts) == 3:
                        pdbfile, sel_str, idx_str = parts
                        idx_list = [int(i) for i in idx_str.strip().split() if i.isdigit()]
                        if (pdbfile, sel_str) in indices:
                            f.write(f'REPEATED INDICES KEY: {(pdbfile, sel_str)}\n')
                        indices[(pdbfile, sel_str)] = idx_list

        

            result: dict[tuple[str, str], tuple[int, list[int]]] = {}
            for pdb in [os.path.basename(p) for p in pdb_paths]:
                for sel in selections:
                    key = (pdb, sel['query'])
                    cnt = counts.get(key, np.nan)
                    idx_list = indices.get(key, [])
                    result[key] = (cnt, idx_list)
                    f.write(f'RESULT KEY: {key} -> count={cnt}, indices={idx_list}\n')
            return result


class ProDyBackend(BackendInterface):
    """
    Uses ProDy to count atoms and retrieve their indices.
    """
    @staticmethod
    def _exec_dssp_legacy(pdb_path: str) -> str:
        """Run mkdssp with --output-format dssp to produce legacy format that ProDy can parse."""
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
        dssp_cache_dir = os.path.join(project_root, 'molselect', 'data', 'tests')
        basename = os.path.splitext(os.path.basename(pdb_path))[0]
        cached = os.path.join(dssp_cache_dir, basename + '.dssp')
        if os.path.exists(cached):
            return cached

        from prody.utilities import which
        mkdssp = which('mkdssp') or which('dssp')
        if mkdssp is None:
            raise EnvironmentError('mkdssp/dssp executable not found')
        abs_pdb = os.path.abspath(pdb_path)
        os.makedirs(dssp_cache_dir, exist_ok=True)
        out = os.path.join(dssp_cache_dir, basename + '.dssp')
        status = os.system(f'{mkdssp} --output-format dssp {abs_pdb} > {out} 2>/dev/null')
        if status != 0:
            raise RuntimeError(f'mkdssp failed with status {status} for {abs_pdb}')
        return out

    def count_atom_data(
        self,
        pdb_paths: list[str],
        selections: list[dict[str, str]]
    ) -> dict[tuple[str, str], tuple[int, list[int]]]:
        from prody import parsePDB, parseDSSP
        result_counts: dict[tuple[str, str], float] = {}
        result_indices: dict[tuple[str, str], list[int]] = {}

        for pdb in pdb_paths:
            basename = os.path.basename(pdb)
            try:
                structure = parsePDB(pdb, altloc='all')
                try:
                    dssp_file = self._exec_dssp_legacy(pdb)
                    parseDSSP(dssp_file, structure)
                except Exception as e:
                    logger.warning(f"DSSP failed for {basename}: {e}")

                for sel in selections:
                    key = (basename, sel['query'])
                    prody_sel = sel.get('prody_query', sel['query'])
                    try:
                        atoms = structure.select(prody_sel)
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
                    key = (basename, sel['query'])
                    result_counts[key] = np.nan
                    result_indices[key] = []

        for pdb in [os.path.basename(p) for p in pdb_paths]:
            for sel in selections:
                key = (pdb, sel['query'])
                result_counts.setdefault(key, np.nan)
                result_indices.setdefault(key, [])

        return {k: (result_counts[k], result_indices[k]) for k in result_counts}


class MolSceneBackend(BackendInterface):
    from molscene.Scene import Scene
    """
    Uses MolScene and molselect Evaluator to count atoms and retrieve their indices.
    """

    # Directories to search for pre-computed .dssp files
    DSSP_SEARCH_DIRS = [
        os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'tests'),  # canonical cache dir
        os.path.join(os.path.dirname(__file__), '..', '..', '..'),  # project root
        os.path.dirname(__file__),  # tests dir
    ]

    @staticmethod
    def _parse_dssp_file(dssp_path: str) -> dict[tuple[str, int], str]:
        """
        Parse a legacy-format DSSP file and return a mapping of (chain, resid) -> SS letter.
        SS letter is one of H, E, T, S, G, B, I, P, or 'C' for coil (space in DSSP).
        """
        result = {}
        in_data = False
        with open(dssp_path) as f:
            for line in f:
                if line.startswith('  #  RESIDUE'):
                    in_data = True
                    continue
                if not in_data:
                    continue
                if len(line) < 17:
                    continue
                # Skip chain-break lines (marked with '!' in the amino acid column)
                if line[13] == '!':
                    continue
                try:
                    resid = int(line[5:10].strip())
                except ValueError:
                    continue
                chain = line[11].strip()
                ss = line[16]
                if ss == ' ':
                    ss = 'C'
                result[(chain, resid)] = ss
        return result

    @staticmethod
    def _apply_dssp_to_df(df, dssp_map: dict[tuple[str, int], str]):
        """Apply DSSP assignments from a parsed DSSP map onto a DataFrame.

        For CIF files, DSSP chain IDs correspond to auth_asym_id (author chain),
        not label_asym_id (which MolScene stores as 'chain'). If auth_asym_id is
        available and produces better overlap, use it for matching.
        """
        # Determine which chain column to use for DSSP key matching.
        # For CIF files, label_asym_id (chain) may differ from auth_asym_id.
        # DSSP uses author chain IDs, so compare actual (chain, resid) overlap.
        chain_col = 'chain'
        if 'auth_asym_id' in df.columns:
            dssp_keys = set(dssp_map.keys())
            resids = df['resid'].dropna()
            try:
                resid_ints = resids.astype(int)
            except (ValueError, TypeError):
                resid_ints = pd.Series(dtype=int)
            valid = resid_ints.index
            label_keys = set(zip(df.loc[valid, 'chain'], resid_ints))
            auth_keys = set(zip(df.loc[valid, 'auth_asym_id'], resid_ints))
            label_overlap = len(label_keys & dssp_keys)
            auth_overlap = len(auth_keys & dssp_keys)
            if auth_overlap > label_overlap:
                chain_col = 'auth_asym_id'

        ss_series = pd.Series('C', index=df.index)
        for idx, row in df.iterrows():
            chain = row.get(chain_col, '')
            resid = row.get('resid', None)
            if resid is not None:
                try:
                    resid_int = int(resid)
                except (ValueError, TypeError):
                    continue
                key = (chain, resid_int)
                if key in dssp_map:
                    ss_series.at[idx] = dssp_map[key]
        df['secondary'] = ss_series
        return df

    def _find_dssp_file(self, pdb_path: str) -> str | None:
        """Find a pre-computed .dssp file for the given PDB/CIF file."""
        stem = os.path.splitext(os.path.basename(pdb_path))[0]
        for d in self.DSSP_SEARCH_DIRS:
            candidate = os.path.join(os.path.abspath(d), stem + '.dssp')
            if os.path.exists(candidate):
                return candidate
        return None

    def load_pdb_or_cif(self, path: str):
        """
        Load a PDB or CIF file into a Pandas DataFrame.
        """
        basename = os.path.basename(path)
        if path.endswith('.pdb'):
            df = self.Scene.from_pdb(path)
        elif path.endswith('.cif'):
            df = self.Scene.from_cif(path)
        else:
            raise ValueError(f"Unsupported file format for {basename}")
        df = df.compute_mass()
        try:
            df = df.compute_secondary_structure()
            df['secondary'] = df['secondary_structure'].fillna('C').replace({'.': 'C'})
        except Exception as e:
            logger.warning(f"compute_secondary_structure failed for {path}: {e}")
            # Fallback: try loading pre-computed DSSP file
            dssp_path = self._find_dssp_file(path)
            if dssp_path:
                logger.info(f"Using pre-computed DSSP file: {dssp_path}")
                dssp_map = self._parse_dssp_file(dssp_path)
                df = self._apply_dssp_to_df(df, dssp_map)
            else:
                df['secondary'] = 'C'
        if 'model' in df.columns:
            df = df[df['model'] == 1]
        return df

    def count_atom_data(
        self,
        pdb_paths: list[str],
        selections: list[dict[str, str]],
        query_key: str = 'query'
    ) -> dict[tuple[str, str], tuple[int, list[int]]]:
        from molselect.python.backends.pandas import PandasStructure
        from molselect.python.evaluator import Evaluator

        result_counts: dict[tuple[str, str], float] = {}
        result_indices: dict[tuple[str, str], list[int]] = {}
        selector = Evaluator(PandasStructure)

        for pdb in pdb_paths:
            basename = os.path.basename(pdb)
            try:
                df = self.load_pdb_or_cif(pdb)
                for sel in selections:
                    query_str = sel.get(query_key, sel['query']) if query_key != 'query' else sel['query']
                    key = (basename, sel['query'])
                    try:
                        sel_result = selector.parse(df, query_str)
                        count = len(sel_result.df)
                        idx_list = sel_result.df.index.to_list()
                    except Exception as e:
                        logger.warning(f"[molselect] selection failed for '{query_str}' on {basename}: {e}")
                        count = np.nan
                        idx_list = []
                    result_counts[key] = count
                    result_indices[key] = idx_list
            except Exception as e:
                logger.warning(f"MolSceneBackend parse failed for {basename}: {e}")
                for sel in selections:
                    key = (basename, sel['query'])
                    result_counts[key] = np.nan
                    result_indices[key] = []

        for pdb in [os.path.basename(p) for p in pdb_paths]:
            for sel in selections:
                key = (pdb, sel['query'])
                result_counts.setdefault(key, np.nan)
                result_indices.setdefault(key, [])

        return {key: (result_counts[key], result_indices[key]) for key in result_counts}



# ---------------------------------------------------------------------------
# Load PDB files and selection tests
# ---------------------------------------------------------------------------

def load_selection_tests():
    jsonc_path = os.path.join(os.path.dirname(__file__), "selection_tests.jsonc")
    with open(jsonc_path, "r") as f:
        lines = f.readlines()
    clean_lines = [line for line in lines if not line.lstrip().startswith("//")]
    clean_json = "".join(clean_lines)
    return json.loads(clean_json)


def load_pdb_files():
    import glob
    base = os.path.dirname(__file__)
    pdb_files = glob.glob(os.path.join(base, '../../data/tests/*.pdb'))
    pdb_files += glob.glob(os.path.join(base, '../../data/tests/*.cif'))
    return pdb_files


PDB_FILES = load_pdb_files()
_ALL_SELECTIONS = load_selection_tests()

# ---------------------------------------------------------------------------
# Optional filtering via environment variable
# ---------------------------------------------------------------------------
# Usage:  MOLSELECT_SEL=3,37,68  pytest test_functional.py
#         MOLSELECT_PDB=1zir.pdb  pytest test_functional.py
# Dramatically speeds up targeted testing by skipping irrelevant backends work.

_sel_filter = os.environ.get("MOLSELECT_SEL", "")
if _sel_filter:
    _sel_indices = [int(i) for i in _sel_filter.split(",") if i.strip()]
    SELECTIONS = [_ALL_SELECTIONS[i] for i in _sel_indices if i < len(_ALL_SELECTIONS)]
    logger.info("MOLSELECT_SEL: running %d/%d selections: %s", len(SELECTIONS), len(_ALL_SELECTIONS), _sel_indices)
else:
    SELECTIONS = _ALL_SELECTIONS

_pdb_filter = os.environ.get("MOLSELECT_PDB", "")
if _pdb_filter:
    _pdb_names = {n.strip() for n in _pdb_filter.split(",") if n.strip()}
    PDB_FILES = [p for p in PDB_FILES if os.path.basename(p) in _pdb_names]
    logger.info("MOLSELECT_PDB: running %d PDB files: %s", len(PDB_FILES), _pdb_names)

# Check whether any selections define a fallback query
_HAS_FALLBACK = any('fallback_query' in s for s in SELECTIONS)

# Instantiate backend objects
molscene_backend = MolSceneBackend()
prody_backend = ProDyBackend()
vmd_backend = VMDBackend('temporary_script.tcl')


# ---------------------------------------------------------------------------
# Session-scoped fixtures — each backend computed once
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def molscene_data():
    """Compute MolScene counts and indices once per session."""
    return molscene_backend.count_atom_data(PDB_FILES, SELECTIONS)

@pytest.fixture(scope="session")
def molscene_counts(molscene_data):
    return {k: v[0] for k, v in molscene_data.items()}

@pytest.fixture(scope="session")
def molscene_indices(molscene_data):
    return {k: v[1] for k, v in molscene_data.items()}

@pytest.fixture(scope="session")
def molscene_fallback_data():
    """Compute MolScene results for fallback_query. Only computed if any selection has one."""
    if not _HAS_FALLBACK:
        return {}
    return molscene_backend.count_atom_data(PDB_FILES, SELECTIONS, query_key='fallback_query')

@pytest.fixture(scope="session")
def molscene_fallback_counts(molscene_fallback_data):
    return {k: v[0] for k, v in molscene_fallback_data.items()}

@pytest.fixture(scope="session")
def molscene_fallback_indices(molscene_fallback_data):
    return {k: v[1] for k, v in molscene_fallback_data.items()}

@pytest.fixture(scope="session")
def prody_data():
    """Compute ProDy counts and indices once per session."""
    return prody_backend.count_atom_data(PDB_FILES, SELECTIONS)

@pytest.fixture(scope="session")
def prody_counts(prody_data):
    return {k: v[0] for k, v in prody_data.items()}

@pytest.fixture(scope="session")
def prody_indices(prody_data):
    return {k: v[1] for k, v in prody_data.items()}

@pytest.fixture(scope="session")
def vmd_data():
    """Compute VMD counts and indices once per session."""
    return vmd_backend.count_atom_data(PDB_FILES, SELECTIONS)

@pytest.fixture(scope="session")
def vmd_counts(vmd_data):
    return {k: v[0] for k, v in vmd_data.items()}

@pytest.fixture(scope="session")
def vmd_indices(vmd_data):
    return {k: v[1] for k, v in vmd_data.items()}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize(sel: str) -> str:
    name = re.sub(r'[^0-9a-zA-Z]+', '_', sel).strip('_')
    return name[:30]


def _is_nan(val) -> bool:
    try:
        return pd.isna(val) or np.isnan(val)
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Test generators
# ---------------------------------------------------------------------------

def _make_test_for(sel: dict):
    """
    Generate a count-comparison test for one selection, parametrized over PDB files.
    Supports fallback_query: if primary query diverges from a backend,
    re-evaluate MolSelect with fallback_query and compare.
    """
    has_fallback = 'fallback_query' in sel

    @pytest.mark.parametrize("pdb_path", PDB_FILES, ids=lambda p: os.path.basename(p))
    def test_molscene_vs_prody_or_vmd(self, pdb_path,
                                      molscene_counts, prody_counts, vmd_counts,
                                      molscene_fallback_counts):
        basename = os.path.basename(pdb_path)
        key = (basename, sel['query'])

        mol = molscene_counts[key]
        pro = prody_counts[key]
        vmd_val = vmd_counts[key]

        # If both reference backends fail → check mol
        if _is_nan(pro) and _is_nan(vmd_val):
            if _is_nan(mol):
                pytest.skip(f"Selection '{sel['query']}' unsupported by all backends on {basename}")
            return  # MolSelect produced a result with no reference — pass

        ok_pro = not _is_nan(pro) and mol == pro
        ok_vmd = not _is_nan(vmd_val) and mol == vmd_val

        # Fallback: if primary query diverges, try fallback_query on MolSelect
        if not (ok_pro or ok_vmd) and has_fallback and molscene_fallback_counts:
            mol_fb = molscene_fallback_counts.get(key, np.nan)
            if not _is_nan(mol_fb):
                if not ok_pro and not _is_nan(pro) and mol_fb == pro:
                    ok_pro = True
                if not ok_vmd and not _is_nan(vmd_val) and mol_fb == vmd_val:
                    ok_vmd = True

        assert ok_pro or ok_vmd, (
            f"{basename} | sel={sel!r}: molscene={mol!r} "
            f"!= prody={pro!r} and != vmd={vmd_val!r}"
        )

    test_molscene_vs_prody_or_vmd.__doc__ = f"molscene vs prody/vmd for selection: {sel!r}"
    return test_molscene_vs_prody_or_vmd


def _make_test_for_indices(sel: dict):
    """
    Generate an index-comparison test for one selection, parametrized over PDB files.
    Supports fallback_query for cases where primary query diverges.
    """
    has_fallback = 'fallback_query' in sel

    @pytest.mark.parametrize("pdb_path", PDB_FILES, ids=lambda p: os.path.basename(p))
    def test_indices(self, pdb_path,
                     molscene_indices, prody_indices, vmd_indices,
                     molscene_counts, prody_counts, vmd_counts,
                     molscene_fallback_indices, molscene_fallback_counts):
        basename = os.path.basename(pdb_path)
        key = (basename, sel['query'])

        mol_idx = molscene_indices[key]
        pro_idx = prody_indices[key]
        vmd_idx = vmd_indices[key]

        mol_count = molscene_counts[key]
        pro_count = prody_counts[key]
        vmd_count = vmd_counts[key]

        # If all fail → skip
        if _is_nan(pro_count) and _is_nan(vmd_count):
            pytest.skip(f"Selection '{sel['query']}' unsupported by all backends on {basename}")

        # MolSelect must not fail
        assert not _is_nan(mol_count), (
            f"{basename} | sel={sel!r}: molscene failed "
            f"(prody={pro_count!r}, vmd={vmd_count!r})"
        )

        pro_ok = not _is_nan(pro_count) and mol_idx == pro_idx
        vmd_ok = not _is_nan(vmd_count) and mol_idx == vmd_idx

        if sel.get('prody_query', '') == 'SKIP':
            pro_ok = True
        if sel.get('vmd_query', '') == 'SKIP':
            vmd_ok = True

        # If a reference backend returned nan, don't count it as a failure
        if _is_nan(pro_count):
            pro_ok = True
        if _is_nan(vmd_count):
            vmd_ok = True

        # Fallback: if primary query diverges, try fallback_query on MolSelect
        if not (pro_ok and vmd_ok) and has_fallback and molscene_fallback_indices:
            mol_fb_idx = molscene_fallback_indices.get(key, [])
            mol_fb_count = molscene_fallback_counts.get(key, np.nan)
            if not _is_nan(mol_fb_count):
                if not pro_ok and not _is_nan(pro_count) and mol_fb_idx == pro_idx:
                    pro_ok = True
                if not vmd_ok and not _is_nan(vmd_count) and mol_fb_idx == vmd_idx:
                    vmd_ok = True

        if not (pro_ok and vmd_ok):
            scene = molscene_backend.load_pdb_or_cif(pdb_path)
            msg = f"{basename} | sel={sel!r}:\n"

            def _diff_msg(ref_name, ref_count, ref_idx):
                nonlocal msg
                msg += f"  molscene count={mol_count!r} != {ref_name} count={ref_count!r}\n"
                if _is_nan(ref_count):
                    return
                ref_set = set(ref_idx)
                mol_set = set(mol_idx)
                missing = sorted(ref_set - mol_set)
                extra = sorted(mol_set - ref_set)
                with pd.option_context("display.max_columns", None, "display.width", None):
                    if missing and all(a in scene.index for a in missing):
                        msg += f"  Missing in {ref_name} selection:\n{scene.loc[missing]}\n"
                    if extra and all(a in scene.index for a in extra):
                        msg += f"  Extra in MolScene selection:\n{scene.loc[extra]}\n"

            if not pro_ok:
                _diff_msg("prody", pro_count, pro_idx)
            if not vmd_ok:
                _diff_msg("vmd", vmd_count, vmd_idx)
            assert False, msg

    test_indices.__doc__ = f"molscene vs prody/vmd indices for selection: {sel!r}"
    return test_indices


# ---------------------------------------------------------------------------
# Dynamically build one Test class per selection
# ---------------------------------------------------------------------------

for _i, _sel in enumerate(SELECTIONS):
    _safe = _sanitize(_sel['query'])
    _cls_name = f"Test_{_i:03d}_{_safe}"
    _cls = type(_cls_name, (object,), {})
    setattr(_cls, "test_molscene", _make_test_for(_sel))
    setattr(_cls, "test_indices", _make_test_for_indices(_sel))
    globals()[_cls_name] = _cls


# ---------------------------------------------------------------------------
# Standalone analysis script (python -m or python test_functional.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pdb_files = PDB_FILES
    selections = SELECTIONS

    ms_backend = MolSceneBackend()
    pr_backend = ProDyBackend()
    vm_backend = VMDBackend()

    print("Computing molscene counts...")
    molscene = {k: v[0] for k, v in ms_backend.count_atom_data(pdb_files, selections).items()}
    print("Computing prody counts...")
    prody = {k: v[0] for k, v in pr_backend.count_atom_data(pdb_files, selections).items()}
    print("Computing vmd counts...")
    vmd = {k: v[0] for k, v in vm_backend.count_atom_data(pdb_files, selections).items()}

    rows = []
    for pdb in pdb_files:
        basename = os.path.basename(pdb)
        for sel in selections:
            q = sel['query']
            rows.append({
                "pdb": basename,
                "selection": q,
                "count_molscene": molscene.get((basename, q), pd.NA),
                "count_prody": prody.get((basename, q), pd.NA),
                "count_vmd": vmd.get((basename, q), pd.NA),
            })
    df = pd.DataFrame(rows)
    print(df)
    df.to_csv("atom_counts_all_backends.csv", index=False)
    print("Saved results to atom_counts_all_backends.csv")

