"""Selection-contract test suite.

Per-feature, per-structure comparison of MolSelect against the reference engines
(ProDy, VMD). Test cases live in ``cases/*.jsonc``; each file owns one grammar
area and isolates a single feature per entry using operands all three engines
agree on, so a failure points at the feature under test rather than at a
diverging operand.

Contract semantics:
  * MolSelect must select the same atoms as every *available* reference, using
    that reference's equivalent query (``vmd_query`` / ``prody_query``).
  * There are no SKIPs. A genuinely irreconcilable single structure is recorded
    as ``"xfail": {"<pdb>": "<reason>"}`` on the case and fails *expectedly*
    there only.
  * The suite runs without VMD/ProDy installed: an absent backend is simply not
    compared (the run degrades to "MolSelect must not error").
"""

import os
import sys
import glob
import fnmatch

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import case_gen  # noqa: E402
from backends_ref import (  # noqa: E402
    MolSceneBackend, ProDyBackend, VMDBackend,
    load_jsonc, load_pdb_files, is_nan,
)

CASES_DIR = os.path.join(HERE, "cases")


def _load_cases() -> list[dict]:
    """Load every cases/*.jsonc. A file is either an explicit list of cases, or a
    generate-spec ``{"generate": <area>, "exceptions": {...}, "extra": [...]}``
    whose cases are enumerated from the data files by case_gen."""
    cases = []
    for path in sorted(glob.glob(os.path.join(CASES_DIR, "*.jsonc"))):
        area = os.path.splitext(os.path.basename(path))[0]
        data = load_jsonc(path)
        if isinstance(data, dict) and "generate" in data:
            gen = case_gen.GENERATORS[data["generate"]]
            cases.extend(gen(data.get("exceptions", {}), data.get("extra", [])))
        else:
            for entry in data:
                entry = dict(entry)
                entry["area"] = area
                cases.append(entry)
    return cases


CASES = _load_cases()
PDB_FILES = load_pdb_files()


def _molscene_selections() -> list[dict]:
    """Every distinct query MolScene must evaluate (case queries + equiv targets)."""
    seen, out = set(), []
    for c in CASES:
        for q in [c["query"]] + ([c["equiv"]] if "equiv" in c else []):
            if q not in seen:
                seen.add(q)
                out.append({"query": q})
    return out


def _ref_cases() -> list[dict]:
    """Cases compared against VMD/ProDy (synonym-equivalence cases are excluded)."""
    return [c for c in CASES if "equiv" not in c]

_HAVE_VMD = VMDBackend.available()
_HAVE_PRODY = ProDyBackend.available()
_HAVE_MOLSCENE = MolSceneBackend.available()

molscene_backend = MolSceneBackend()
prody_backend = ProDyBackend()
vmd_backend = VMDBackend()  # writes its Tcl to a throwaway temp file


# ---------------------------------------------------------------------------
# Session-scoped backend computation (each engine runs once over all cases)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def molscene_data():
    if not _HAVE_MOLSCENE:
        pytest.skip("molscene not installed")
    return molscene_backend.count_atom_data(PDB_FILES, _molscene_selections())


@pytest.fixture(scope="session")
def prody_data():
    if not _HAVE_PRODY:
        return {}
    return prody_backend.count_atom_data(PDB_FILES, _ref_cases())


@pytest.fixture(scope="session")
def vmd_data():
    if not _HAVE_VMD:
        return {}
    return vmd_backend.count_atom_data(PDB_FILES, _ref_cases())


# ---------------------------------------------------------------------------
# The contract test
# ---------------------------------------------------------------------------

def _case_id(case: dict) -> str:
    return f"{case['area']}::{case['query']}"


def _diff(ms_set: set, ref_set: set, limit: int = 8) -> str:
    missing = sorted(ref_set - ms_set)
    extra = sorted(ms_set - ref_set)
    return f"missing={missing[:limit]} extra={extra[:limit]}"


def _xfail_for(case: dict, base: str) -> dict:
    """Resolve a case's ``xfail`` spec for one structure into ``{ref: reason}``.

    Spec form:  {"<pdb-or-glob>": "<reason>" | {"<ref>": "<reason>", ...}}
    A glob key (e.g. ``"*.cif"``) matches the basename; a bare-string value
    excuses *all* references (stored under ``"*"``); a dict value excuses only
    the named references (``"vmd"`` / ``"prody"``). ``"molscene"`` excuses a
    MolSelect-side error (feature not supported on that structure).
    """
    out = {}
    for pat, val in case.get("xfail", {}).items():
        if base == pat or fnmatch.fnmatch(base, pat):
            if isinstance(val, dict):
                out.update(val)
            else:
                out["*"] = val
    return out


@pytest.mark.parametrize("pdb_path", PDB_FILES, ids=[os.path.basename(p) for p in PDB_FILES])
@pytest.mark.parametrize("case", CASES, ids=[_case_id(c) for c in CASES])
def test_selection_contract(case, pdb_path, molscene_data, prody_data, vmd_data):
    base = os.path.basename(pdb_path)
    key = (base, case["query"])
    xmap = _xfail_for(case, base)

    ms_cnt, ms_idx = molscene_data[key]

    # MolSelect itself must produce a result (unless this structure is excused).
    if is_nan(ms_cnt):
        reason = xmap.get("molscene") or xmap.get("*")
        if reason:
            pytest.xfail(f"{base} (molscene): {reason}")
        pytest.fail(f"MolSelect errored on {case['query']!r} for {base}")
    ms_set = set(ms_idx)

    # Synonym-equivalence cases: MolSelect(query) must equal MolSelect(equiv),
    # an internal-consistency check that needs no reference engine.
    if "equiv" in case:
        eq_cnt, eq_idx = molscene_data[(base, case["equiv"])]
        assert not is_nan(eq_cnt), f"{base}: canonical {case['equiv']!r} errored in MolSelect"
        assert ms_set == set(eq_idx), (
            f"{base} | [{case['area']}] synonym {case['query']!r} != {case['equiv']!r} "
            f"({ms_cnt} vs {eq_cnt})"
        )
        return

    refs = []
    if _HAVE_PRODY:
        refs.append(("prody", prody_data.get(key, (float('nan'), []))))
    if _HAVE_VMD:
        refs.append(("vmd", vmd_data.get(key, (float('nan'), []))))

    failures = []   # uncovered disagreements -> hard fail
    xfailed = []    # disagreements excused by an xfail entry
    for name, (cnt, idx) in refs:
        if not is_nan(cnt) and set(idx) == ms_set:
            continue
        reason = xmap.get(name) or xmap.get("*")
        if is_nan(cnt):
            msg = f"{name}: equivalent query produced no result (errored)"
        else:
            msg = f"{name}: count={cnt} vs molselect={ms_cnt}  {_diff(ms_set, set(idx))}"
        (xfailed if reason else failures).append((name, reason, msg))

    assert not failures, (
        f"{base} | [{case['area']}] {case['query']!r}\n  "
        + "\n  ".join(m for _, _, m in failures)
    )
    if xfailed:
        pytest.xfail(
            f"{base}: " + "; ".join(f"{n}: {why}" for n, why, _ in xfailed)
        )
