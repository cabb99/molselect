import os
import subprocess
import tempfile
import logging
from typing import Union
import numpy as np
import pandas as pd
import pytest

logger = logging.getLogger(__name__)

def count_atoms_with_vmd(pdb_paths: list[str], selections: list[str], tcl_script_path: str | None = None) -> dict[tuple[str, str], int]:
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
    logger.info(f"Calling VMD to count atoms in {pdb_paths} with selections {selections}")
    logger.debug(f"Preparing Tcl script for VMD selections.")

    delimiter = '|----|' # Use a unique delimiter unlikely to appear in filenames or selections
    # Build Tcl script to load each PDB and count atoms for each selection
    tcl_lines = []
    for pdb in pdb_paths:
        tcl_lines.append(f"mol new \"{os.path.abspath(pdb)}\"")
        for sel in selections:
            escaped_sel = (
                sel
                .replace('\\', '\\\\')   # escape backslashes first
                .replace('"', '\\"')     # escape double-quotes
                .replace('$', '\\$')     # escape dollar signs (no $VAR substitution)
                .replace('[', '\\[')     # escape open brackets (no [cmd] substitution)
                .replace(']', '\\]')     # (optional) escape closing brackets for symmetry
            )
            # Use try to catch errors in atomselect and puts
            tcl_lines.append(f"try {{")
            tcl_lines.append(f'    set sel [atomselect top "{escaped_sel}"]')
            tcl_lines.append(f'    puts "COUNT {os.path.basename(pdb)}{delimiter}{escaped_sel}{delimiter}[$sel num]"')
            tcl_lines.append(f"    $sel delete")
            tcl_lines.append(f"}} on error {{err opts}} {{")
            tcl_lines.append(f'    puts "COUNT {os.path.basename(pdb)}{delimiter}{escaped_sel}{delimiter}nan"')
            tcl_lines.append(f"}}")
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

    # Parse output lines like: COUNT filename<<<DELIM>>>selection<<<DELIM>>>N
    result = {}
    found_keys = set()
    for line in proc.stdout.splitlines():
        s = line.strip()
        if s.startswith("COUNT "):
            try:
                _, rest = s.split("COUNT ", 1)
                parts = rest.split(delimiter)
                if len(parts) != 3:
                    logger.warning(f"Unexpected output format: {s}")
                    continue
                pdbfile, sel, n = [x.strip() for x in parts]
                found_keys.add((pdbfile, sel))
                if n.isdigit():
                    result[(pdbfile, sel)] = int(n)
                    logger.info(f"Found atom count: {pdbfile} | {sel} = {n}")
                else:
                    result[(pdbfile, sel)] = np.nan
                    logger.info(f"Invalid selection or count for: {pdbfile} | {sel}, returning np.nan")
            except Exception as e:
                logger.warning(f"Failed to parse line: {s} ({e})")
    # Fill missing (pdb, sel) pairs with np.nan
    for pdb in pdb_paths:
        for sel in selections:
            key = (os.path.basename(pdb), sel)
            if key not in result:
                logger.warning(f"Missing count for {key}, setting to np.nan")
                result[key] = np.nan
    if not result:
        logger.error("Could not parse VMD output for atom counts.")
        raise RuntimeError(
            "Could not parse VMD output for atom counts.\n"
            f"Full stdout:\n{proc.stdout}\n"
            f"Full stderr:\n{proc.stderr}"
        )
    return result


def count_atoms_with_prody(pdb_paths: list[str], selections: list[str]) -> dict[tuple[str, str], int]:
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
    logger = logging.getLogger(__name__)
    result = {}
    backup_path = os.path.join(os.path.dirname(__file__), "atom_counts_backup.csv")
    if os.path.exists(backup_path):
        backup_df = pd.read_csv(backup_path)
        # Build a lookup for (pdb, selection) -> count
        backup_lookup = {(row["pdb"], row["selection"]): row["count_prody"] for _, row in backup_df.iterrows()}
        # Determine which need to be calculated
        to_calculate = []
        for pdb in pdb_paths:
            pdb_basename = os.path.basename(pdb)
            for sel in selections:
                key = (pdb_basename, sel)
                count = backup_lookup.get(key, None)
                if count is not None and not pd.isna(count):
                    result[key] = int(count)
                else:
                    to_calculate.append((pdb, pdb_basename, sel))
    else:
        # If backup does not exist, calculate all
        to_calculate = [(pdb, os.path.basename(pdb), sel) for pdb in pdb_paths for sel in selections]
    # Calculate only missing/nan
    # Group selections to calculate by pdb
    from collections import defaultdict
    pdb_to_sels = defaultdict(list)
    for pdb, pdb_basename, sel in to_calculate:
        pdb_to_sels[(pdb, pdb_basename)].append(sel)
    idx = 0
    for (pdb, pdb_basename), sels in pdb_to_sels.items():
        try:
            structure = parsePDB(pdb)
            try:
                from prody import execDSSP, parseDSSP
                dssp_file = execDSSP(pdb_basename)
                parseDSSP(dssp_file, structure)
            except Exception as e:
                logger.warning(f"calcDSSP failed for {pdb_basename}: {e}")
            for sel in sels:
                try:
                    atoms = structure.select(sel)
                    count = len(atoms) if atoms is not None else 0
                    result[(pdb_basename, sel)] = count
                except Exception as e:
                    logger.warning(f"Failed to select for {pdb_basename}, {sel}: {e}")
                    result[(pdb_basename, sel)] = np.nan
                idx += 1
                if idx % 20 == 0:
                    logger.info(f"[ProDy] Processed {idx} selections")
        except Exception as e:
            logger.warning(f"Failed to parse for {pdb_basename}: {e}")
            for sel in sels:
                result[(pdb_basename, sel)] = np.nan
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
    @pytest.mark.skip()
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