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

def _load_backup() -> pd.DataFrame:
    """Load the atom count backup, or return an empty one."""
    if os.path.exists(BACKUP_PATH):
        df = pd.read_csv(BACKUP_PATH)
        # ensure all columns exist
        for col in ("count_vmd", "count_prody"):
            if col not in df.columns:
                df[col] = np.nan
        return df
    else:
        return pd.DataFrame(columns=["pdb", "selection", "count_vmd", "count_prody"])
    
def _save_backup(df: pd.DataFrame) -> None:
    """Write the backup DataFrame back to CSV."""
    df.to_csv(BACKUP_PATH, index=False)

def count_atoms_with_vmd(
    pdb_paths: list[str],
    selections: list[str],
    tcl_script_path: str | None = None
) -> dict[tuple[str, str], int]:
    """
    Count atoms for multiple PDB files and multiple selections in a single VMD call.

    Parameters
    ----------
    pdb_paths : list of str
        List of paths to PDB files.
    selections : list of str
        List of VMD atom-selection strings.
    tcl_script_path : str or None, optional
        If provided, write the generated Tcl script to this file instead of a temporary file.

    Returns
    -------
    dict
        Mapping from (pdb_path, selection) to atom count.

    Raises
    ------
    RuntimeError
        If VMD fails or output cannot be parsed.
    """
    # 1) load existing cache
    backup_df   = _load_backup()
    backup_lookup = {
        (row["pdb"], row["selection"]): row["count_vmd"]
        for _, row in backup_df.iterrows()
    }
    # seed result with cached entries
    result = {
        (pdbfile, sel): int(cnt)
        for (pdbfile, sel), cnt in backup_lookup.items()
        if not pd.isna(cnt)
    }
    # 2) determine which (pdb,sel) are still missing
    missing = [
        (pdb, os.path.basename(pdb), sel)
        for pdb in pdb_paths
        for sel in selections
        if (os.path.basename(pdb), sel) not in result
    ]
    # if nothing left to do, return immediately
    if not missing:
        return result
    # 3) build Tcl script *only* for those missing
    logger.info(f"Calling VMD to count atoms in {pdb_paths} with selections {selections}")
    logger.debug(f"Preparing Tcl script for VMD selections.")
    delimiter = '|----|'
    tcl_lines = []
    for pdb, basename, sel in missing:
        tcl_lines.append(f'mol new "{os.path.abspath(pdb)}"')
        escaped_sel = (
            sel.replace('\\', '\\\\')
               .replace('"', '\"')
               .replace('$', '\$')
               .replace('[', '\[')
               .replace(']', '\]')
        )
        tcl_lines.extend([
            "try {",
            f'  set sel [atomselect top "{escaped_sel}"]',
            f'  puts "COUNT {basename}{delimiter}{escaped_sel}{delimiter}[$sel num]"',
            "  $sel delete",
            "} on error {err opts} {",
            f'  puts "COUNT {basename}{delimiter}{escaped_sel}{delimiter}nan"',
            "}",
        ])
        tcl_lines.append("mol delete top")
    tcl_lines.append("exit")
    tcl = "\n".join(tcl_lines)
    if tcl_script_path is not None:
        with open(tcl_script_path, "w") as script:
            script.write(tcl)
        script_path = tcl_script_path
        logger.debug(f"Tcl script written to user-specified file: {script_path}")
    else:
        with tempfile.NamedTemporaryFile("w", suffix=".tcl", delete=False) as script:
            script.write(tcl)
            script_path = script.name
        logger.debug(f"Temporary Tcl script written to: {script_path}")
    logger.debug(f"Tcl script contents:\n{tcl}")
    cmd = [
        "vmd",
        "-dispdev", "text",
        "-e", script_path
    ]
    logger.info(f"Calling VMD with command: {' '.join(cmd)}")
    proc = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
    )
    logger.debug(f"VMD return code: {proc.returncode}")
    logger.debug(f"VMD stdout:\n{proc.stdout}")
    logger.debug(f"VMD stderr:\n{proc.stderr}")
    if proc.returncode != 0:
        logger.error(f"VMD failed (rc={proc.returncode}):\n{proc.stderr.strip()}")
        raise RuntimeError(f"VMD failed (rc={proc.returncode}):\n{proc.stderr.strip()}")
    # 4) parse *only* the new lines and add into result
    for line in proc.stdout.splitlines():
        if not line.startswith("COUNT "):
            continue
        _, rest = line.split("COUNT ", 1)
        parts = rest.split(delimiter)
        if len(parts) != 3:
            continue
        pdbfile, sel, n = [x.strip() for x in parts]
        key = (pdbfile, sel)
        if key in result:
            continue
        result[key] = int(n) if n.isdigit() else np.nan
    for pdb in pdb_paths:
        basename = os.path.basename(pdb)
        for sel in selections:
            result.setdefault((basename, sel), np.nan)
    for (pdbfile, sel), cnt in result.items():
        mask = (backup_df["pdb"] == pdbfile) & (backup_df["selection"] == sel)
        if mask.any():
            backup_df.loc[mask, "count_vmd"] = cnt
        else:
            backup_df = pd.concat([
                backup_df,
                pd.DataFrame([{
                    "pdb":        pdbfile,
                    "selection":  sel,
                    "count_vmd":  cnt,
                    "count_prody": np.nan
                }])
            ], ignore_index=True)
    _save_backup(backup_df)
    return result


def count_atoms_with_prody(
    pdb_paths: list[str],
    selections: list[str]
) -> dict[tuple[str, str], int]:
    """
    Count atoms for multiple PDB files and multiple selections using ProDy.

    Parameters
    ----------
    pdb_paths : list of str
        List of paths to PDB files.
    selections : list of str
        List of ProDy atom-selection strings.

    Returns
    -------
    dict
        Mapping from (pdb_path, selection) to atom count (np.nan if selection fails).
    """
    from prody import parsePDB
    # 1) load cache
    backup_df     = _load_backup()
    backup_lookup = {
        (row["pdb"], row["selection"]): row["count_prody"]
        for _, row in backup_df.iterrows()
    }
    # seed result with cached entries
    result = {
        (pdbfile, sel): int(cnt)
        for (pdbfile, sel), cnt in backup_lookup.items()
        if not pd.isna(cnt)
    }
    # 2) figure out which to calculate
    to_calculate = [
        (pdb, os.path.basename(pdb), sel)
        for pdb in pdb_paths
        for sel in selections
        if (os.path.basename(pdb), sel) not in result
    ]
    # if nothing left, return immediately
    if not to_calculate:
        return result
    from collections import defaultdict
    pdb_to_sels = defaultdict(list)
    for pdb, basename, sel in to_calculate:
        pdb_to_sels[(pdb, basename)].append(sel)
    idx = 0
    for (pdb, basename), sels in pdb_to_sels.items():
        try:
            structure = parsePDB(pdb)
            try:
                from prody import execDSSP, parseDSSP
                dssp_file = execDSSP(basename)
                parseDSSP(dssp_file, structure)
            except Exception as e:
                logger.warning(f"DSSP failed for {basename}: {e}")
            for sel in sels:
                try:
                    atoms = structure.select(sel)
                    cnt   = len(atoms) if atoms is not None else 0
                except Exception:
                    cnt = np.nan
                result[(basename, sel)] = cnt
                idx += 1
                if idx % 20 == 0:
                    logger.info(f"[ProDy] Processed {idx} selections")
        except Exception:
            for sel in sels:
                result[(basename, sel)] = np.nan
    for pdb in pdb_paths:
        basename = os.path.basename(pdb)
        for sel in selections:
            result.setdefault((basename, sel), np.nan)
    for (pdbfile, sel), cnt in result.items():
        mask = (backup_df["pdb"] == pdbfile) & (backup_df["selection"] == sel)
        if mask.any():
            backup_df.loc[mask, "count_prody"] = cnt
        else:
            backup_df = pd.concat([
                backup_df,
                pd.DataFrame([{
                    "pdb":         pdbfile,
                    "selection":   sel,
                    "count_vmd":   np.nan,
                    "count_prody": cnt
                }])
            ], ignore_index=True)
    _save_backup(backup_df)
    return result

def count_atoms_with_molscene(pdb_paths: list[str], selections: list[str]) -> dict[tuple[str, str], int]:
    """
    Count atoms for multiple PDB files and multiple selections using the molselect Python API (new Evaluator interface).

    Parameters
    ----------
    pdb_paths : list of str
        List of paths to PDB files.
    selections : list of str
        List of selection queries.

    Returns
    -------
    dict
        Mapping from (pdb_path, selection) to atom count (np.nan if selection fails).
    """
    import numpy as np
    import os
    import logging
    from molscene.Scene import Scene
    from molselect.python.backends.pandas import PandasStructure
    from molselect.python.evaluator import Evaluator

    logger = logging.getLogger(__name__)
    result = {}
    selector = Evaluator(PandasStructure)
    for pdb in pdb_paths:
        pdb_basename = os.path.basename(pdb)
        logger.info(f"Processing PDB with molselect: {pdb_basename} with {len(selections)} selections")
        try:
            # Load structure as DataFrame
            if pdb.endswith('.pdb'):
                df = Scene.from_pdb(pdb)
            elif pdb.endswith('.cif'):
                df = Scene.from_cif(pdb)
            else:
                logger.warning(f"Unsupported file format for {pdb}")
                for sel in selections:
                    result[(pdb_basename, sel)] = np.nan
                continue
            
            df = df[df['model']==1]           
            
            # Add mass column if not present
            # The element is the first letter of the atom name, e.g. 'C' for 'CA'
            if 'element' not in df.columns:
                df['element'] = df['atom_name'].str[0].str.upper()
            # Mass dictionary for common elements
            mass_dict = {
                'H': 1.008, 'C': 12.011, 'N': 14.007, 'O': 15.999,
                'P': 30.974, 'S': 32.06, 'F': 18.998, 'Cl': 35.45,
                'Br': 79.904, 'I': 126.904
            }
            # Map elements to masses, default to 0 if not found
            df['mass'] = df['element'].map(mass_dict).fillna(0)
            
            for sel in selections:
                try:
                    selection_result = selector.parse(df, sel)
                    count = len(selection_result.df)
                    result[(pdb_basename, sel)] = count
                except Exception as e:
                    logger.info(f"[molselect] Selection failed for '{sel}': {e}")
                    result[(pdb_basename, sel)] = np.nan
        except Exception as e:
            logger.warning(f"molselect failed for {pdb}: {e}")
            for sel in selections:
                result[(pdb_basename, sel)] = np.nan
    return result



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


# @pytest.mark.parametrize("backend", ["molscene", "vmd", "prody"])
# def test_count_atoms_backends(backend):
#     import pandas as pd
#     selections = load_selection_tests()
#     print(selections)
#     pdb_files = load_pdb_files()
#     if not pdb_files:
#         pytest.skip("No PDB or CIF files found for testing.")
#     if backend == "molscene":
#         result = count_atoms_with_molscene(pdb_files, selections)
#     elif backend == "vmd":
#         result = count_atoms_with_vmd(pdb_files, selections, tcl_script_path=None)
#     elif backend == "prody":
#         result = count_atoms_with_prody(pdb_files, selections)
#     else:
#         raise ValueError(f"Unknown backend: {backend}")
#     # Check that at least some results are not all NaN
#     counts = list(result.values())
#     assert any(pd.notna(c) and c != 0 for c in counts), f"All counts are NaN or zero for backend {backend}"
#     # Optionally: print a summary for debugging
#     print(f"Backend: {backend}, non-NaN counts: {sum(pd.notna(c) for c in counts)} / {len(counts)}")


import re
PDB_FILES = load_pdb_files()
SELECTIONS = load_selection_tests()

@pytest.fixture(scope="session")
def molscene_counts():
    """Compute once per session."""
    # keys are (basename, sel)
    return count_atoms_with_molscene(PDB_FILES, SELECTIONS)

@pytest.fixture(scope="session")
def prody_counts():
    return count_atoms_with_prody(PDB_FILES, SELECTIONS)

@pytest.fixture(scope="session")
def vmd_counts():
    # pass tcl_script_path=None to auto-tempfile
    return count_atoms_with_vmd(PDB_FILES, SELECTIONS, tcl_script_path=None)

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

if __name__ == "__main__":
    import pandas as pd
    import os
    # Load files and selections
    pdb_files = load_pdb_files()
    selections = load_selection_tests()
    # Compute all results
    print("Computing molscene counts...")
    molscene = count_atoms_with_molscene(pdb_files, selections)
    print("Computing prody counts...")
    prody = count_atoms_with_prody(pdb_files, selections)
    print("Computing vmd counts...")
    vmd = count_atoms_with_vmd(pdb_files, selections, tcl_script_path=None)
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