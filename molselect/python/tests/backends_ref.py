"""Shared reference backends for the selection-contract tests.

Each backend turns a list of structures and a list of selection dicts into a
mapping ``(basename, query) -> (count, indices)``. A selection dict carries the
canonical MolSelect ``query`` plus optional ``vmd_query`` / ``prody_query``
*equivalent* forms (the alternative spelling a backend needs to express the same
intent). There is intentionally no ``SKIP`` mechanism: when a reference tool
genuinely cannot agree on a particular structure, the test marks that single
``(pdb, query)`` as an expected failure instead.

Heavy third-party imports (molscene, prody) are deferred into the methods so
this module can be imported for environment probing even when a backend is
absent.
"""

import os
import glob
import json
import logging
import subprocess
import tempfile

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DATA_TESTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "tests")


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------

def load_jsonc(path: str) -> list:
    """Load a JSONC file (// line comments stripped)."""
    with open(path, encoding="utf-8") as f:
        lines = [line for line in f if not line.lstrip().startswith("//")]
    return json.loads("".join(lines))


def load_pdb_files(data_dir: str = DATA_TESTS_DIR) -> list[str]:
    """Return sorted absolute paths of all test PDB/CIF structures."""
    base = os.path.abspath(data_dir)
    files = glob.glob(os.path.join(base, "*.pdb")) + glob.glob(os.path.join(base, "*.cif"))
    return sorted(files)


def is_nan(val) -> bool:
    try:
        return bool(pd.isna(val))
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# VMD
# ---------------------------------------------------------------------------

def _escape_tcl(sel: str) -> str:
    """Escape a VMD atomselect string for Tcl."""
    return (
        sel.replace("\\", "\\\\")
           .replace('"', '\\"')
           .replace("$", "\\$")
           .replace("[", "\\[")
           .replace("]", "\\]")
    )


class VMDBackend:
    """Count atoms via VMD text mode, honouring a per-selection ``vmd_query``."""

    name = "vmd"

    def __init__(self, tcl_script_path: str | None = None):
        self.tcl_script_path = tcl_script_path

    @staticmethod
    def available() -> bool:
        from shutil import which
        return which("vmd") is not None

    @staticmethod
    def _query_for(sel: dict) -> str:
        return sel.get("vmd_query", sel["query"])

    def count_atom_data(self, pdb_paths, selections):
        delimiter = "|----|"
        tcl_lines: list[str] = []
        for pdb in pdb_paths:
            base = os.path.basename(pdb)
            abs_path = os.path.abspath(pdb)
            tcl_lines.append(f'mol new "{abs_path}"')
            for sel in selections:
                esc_key = _escape_tcl(sel["query"])
                esc_sel = _escape_tcl(self._query_for(sel))
                tcl_lines.extend([
                    "try {",
                    f'  set selobj [atomselect top "{esc_sel}" frame 0]',
                    f'  puts "COUNT {base}{delimiter}{esc_key}{delimiter}[$selobj num]"',
                    f'  puts -nonewline "INDICES {base}{delimiter}{esc_key}{delimiter}"',
                    "  puts [$selobj get index]",
                    "  $selobj delete",
                    "} on error {err opts} {",
                    f'  puts "COUNT {base}{delimiter}{esc_key}{delimiter}nan"',
                    f'  puts "INDICES {base}{delimiter}{esc_key}{delimiter}"',
                    '  puts ""',
                    "}",
                ])
            tcl_lines.append("mol delete top")
        tcl_lines.append("exit")
        tcl_script = "\n".join(tcl_lines)

        if self.tcl_script_path:
            script_path = self.tcl_script_path
            with open(script_path, "w") as f:
                f.write(tcl_script)
        else:
            tf = tempfile.NamedTemporaryFile("w", suffix=".tcl", delete=False)
            tf.write(tcl_script)
            tf.flush()
            script_path = tf.name
            tf.close()

        proc = subprocess.run(
            ["vmd", "-dispdev", "text", "-e", script_path],
            text=True, capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"VMD failed (rc={proc.returncode}): {proc.stderr.strip()}")

        counts: dict[tuple[str, str], float] = {}
        indices: dict[tuple[str, str], list[int]] = {}
        for line in proc.stdout.splitlines():
            if line.startswith("COUNT "):
                parts = line.split("COUNT ", 1)[1].split(delimiter)
                if len(parts) == 3:
                    pdbfile, sel_str, num = parts
                    try:
                        cnt = int(num)
                    except ValueError:
                        cnt = np.nan
                    counts[(pdbfile, sel_str)] = cnt
            elif line.startswith("INDICES "):
                parts = line.split("INDICES ", 1)[1].split(delimiter)
                if len(parts) == 3:
                    pdbfile, sel_str, idx_str = parts
                    indices[(pdbfile, sel_str)] = [int(i) for i in idx_str.split() if i.isdigit()]

        result: dict[tuple[str, str], tuple] = {}
        for pdb in [os.path.basename(p) for p in pdb_paths]:
            for sel in selections:
                key = (pdb, sel["query"])
                result[key] = (counts.get(key, np.nan), indices.get(key, []))
        return result


# ---------------------------------------------------------------------------
# ProDy
# ---------------------------------------------------------------------------

class ProDyBackend:
    """Count atoms via ProDy, honouring a per-selection ``prody_query``."""

    name = "prody"

    @staticmethod
    def available() -> bool:
        try:
            import prody  # noqa: F401
            return True
        except Exception:
            return False

    @staticmethod
    def _exec_dssp_legacy(pdb_path: str) -> str:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        dssp_cache_dir = os.path.join(project_root, "molselect", "data", "tests")
        basename = os.path.splitext(os.path.basename(pdb_path))[0]
        cached = os.path.join(dssp_cache_dir, basename + ".dssp")
        if os.path.exists(cached):
            return cached
        from prody.utilities import which
        mkdssp = which("mkdssp") or which("dssp")
        if mkdssp is None:
            raise EnvironmentError("mkdssp/dssp executable not found")
        abs_pdb = os.path.abspath(pdb_path)
        os.makedirs(dssp_cache_dir, exist_ok=True)
        out = os.path.join(dssp_cache_dir, basename + ".dssp")
        status = os.system(f"{mkdssp} --output-format dssp {abs_pdb} > {out} 2>/dev/null")
        if status != 0:
            raise RuntimeError(f"mkdssp failed with status {status} for {abs_pdb}")
        return out

    def count_atom_data(self, pdb_paths, selections):
        from prody import parsePDB, parseDSSP
        counts: dict[tuple[str, str], float] = {}
        indices: dict[tuple[str, str], list[int]] = {}

        for pdb in pdb_paths:
            basename = os.path.basename(pdb)
            try:
                structure = parsePDB(pdb, altloc="all")
                try:
                    parseDSSP(self._exec_dssp_legacy(pdb), structure)
                except Exception as e:
                    logger.warning(f"DSSP failed for {basename}: {e}")
                for sel in selections:
                    key = (basename, sel["query"])
                    prody_sel = sel.get("prody_query", sel["query"])
                    try:
                        atoms = structure.select(prody_sel)
                        if atoms is None:
                            counts[key], indices[key] = 0, []
                        else:
                            counts[key], indices[key] = len(atoms), atoms.getIndices().tolist()
                    except Exception:
                        counts[key], indices[key] = np.nan, []
            except Exception as e:
                logger.warning(f"ProDy parse failed for {basename}: {e}")
                for sel in selections:
                    counts[(basename, sel["query"])] = np.nan
                    indices[(basename, sel["query"])] = []

        return {k: (counts[k], indices[k]) for k in counts}


# ---------------------------------------------------------------------------
# MolScene (the system under test)
# ---------------------------------------------------------------------------

class MolSceneBackend:
    """Count atoms via molscene + the molselect Evaluator."""

    name = "molscene"

    DSSP_SEARCH_DIRS = [
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "tests"),
        os.path.join(os.path.dirname(__file__), "..", "..", ".."),
        os.path.dirname(__file__),
    ]

    @staticmethod
    def available() -> bool:
        try:
            import molscene  # noqa: F401
            return True
        except Exception:
            return False

    # -- DSSP fallback (used only when molscene's own SS computation is absent) --
    @staticmethod
    def _parse_dssp_file(dssp_path: str) -> dict[tuple[str, int], str]:
        result = {}
        in_data = False
        with open(dssp_path) as f:
            for line in f:
                if line.startswith("  #  RESIDUE"):
                    in_data = True
                    continue
                if not in_data or len(line) < 17:
                    continue
                if line[13] == "!":
                    continue
                try:
                    resid = int(line[5:10].strip())
                except ValueError:
                    continue
                chain = line[11].strip()
                ss = line[16]
                result[(chain, resid)] = "C" if ss == " " else ss
        return result

    @staticmethod
    def _apply_dssp_to_df(df, dssp_map):
        chain_col = "chain"
        if "auth_asym_id" in df.columns:
            dssp_keys = set(dssp_map.keys())
            resids = df["resid"].dropna()
            try:
                resid_ints = resids.astype(int)
            except (ValueError, TypeError):
                resid_ints = pd.Series(dtype=int)
            valid = resid_ints.index
            label_keys = set(zip(df.loc[valid, "chain"], resid_ints))
            auth_keys = set(zip(df.loc[valid, "auth_asym_id"], resid_ints))
            if len(auth_keys & dssp_keys) > len(label_keys & dssp_keys):
                chain_col = "auth_asym_id"
        ss_series = pd.Series("C", index=df.index)
        for idx, row in df.iterrows():
            resid = row.get("resid", None)
            if resid is None:
                continue
            try:
                key = (row.get(chain_col, ""), int(resid))
            except (ValueError, TypeError):
                continue
            if key in dssp_map:
                ss_series.at[idx] = dssp_map[key]
        df["secondary"] = ss_series
        return df

    def _find_dssp_file(self, pdb_path: str) -> str | None:
        stem = os.path.splitext(os.path.basename(pdb_path))[0]
        for d in self.DSSP_SEARCH_DIRS:
            candidate = os.path.join(os.path.abspath(d), stem + ".dssp")
            if os.path.exists(candidate):
                return candidate
        return None

    def load_pdb_or_cif(self, path: str):
        from molscene.Scene import Scene
        basename = os.path.basename(path)
        if path.endswith(".pdb"):
            df = Scene.from_pdb(path)
        elif path.endswith(".cif"):
            df = Scene.from_cif(path)
        else:
            raise ValueError(f"Unsupported file format for {basename}")
        df = df.compute_mass()
        for comp in ("compute_phi_psi", "compute_bonds", "compute_anisou"):
            try:
                df = getattr(df, comp)()
            except Exception as e:
                logger.warning(f"{comp} failed for {path}: {e}")
        try:
            df = df.compute_secondary_structure()
            df["secondary"] = df["secondary_structure"].fillna("C").replace({".": "C"})
        except Exception as e:
            logger.warning(f"compute_secondary_structure failed for {path}: {e}")
            dssp_path = self._find_dssp_file(path)
            if dssp_path:
                df = self._apply_dssp_to_df(df, self._parse_dssp_file(dssp_path))
            else:
                df["secondary"] = "C"
        if "model" in df.columns:
            df = df[df["model"] == 1]
        return df

    def count_atom_data(self, pdb_paths, selections, query_key: str = "query"):
        from molselect.python.backends.pandas import PandasStructure
        from molselect.python.evaluator import Evaluator

        counts: dict[tuple[str, str], float] = {}
        indices: dict[tuple[str, str], list[int]] = {}
        selector = Evaluator(PandasStructure)

        for pdb in pdb_paths:
            basename = os.path.basename(pdb)
            try:
                df = self.load_pdb_or_cif(pdb)
                for sel in selections:
                    key = (basename, sel["query"])
                    query_str = sel.get(query_key, sel["query"])
                    try:
                        result = selector.parse(df, query_str)
                        counts[key] = len(result.df)
                        indices[key] = result.df.index.to_list()
                    except Exception as e:
                        logger.warning(f"[molselect] selection failed for '{query_str}' on {basename}: {e}")
                        counts[key], indices[key] = np.nan, []
            except Exception as e:
                logger.warning(f"MolSceneBackend parse failed for {basename}: {e}")
                for sel in selections:
                    counts[(basename, sel["query"])] = np.nan
                    indices[(basename, sel["query"])] = []

        return {k: (counts[k], indices[k]) for k in counts}
