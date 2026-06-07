"""Generate selection-contract cases from the canonical data files.

The macro list (`macros.json`) and keyword list (`keywords.json`) are the source
of truth for what MolSelect supports, so the contract enumerates *every* macro
and keyword (plus their synonyms) automatically, rather than hand-listing them.
A per-area ``exceptions`` map in the jsonc then supplies only the cases that
diverge from the trivial default: reference-equivalent queries, xfails, or a
better probe value.

Each generated case carries an intent-standardized ``description`` of the form
``"<kind>: <subject>"`` — it states *what the case is meant to validate*
(e.g. ``macro: protein``, ``keyword: beta``, ``synonym: bb = backbone``), not
the mechanics of the query.

Divergence classes the generator knows about (so they are encoded once, in code,
not repeated per item):
  * Secondary-structure macros (definition references ``structure``): ProDy gets
    the equivalent ``secstr …`` query; VMD is excused (STRIDE vs DSSP); ProDy is
    excused on the CIF structures whose DSSP chain mapping differs.
  * MolSelect-computed keywords with no VMD/ProDy selection keyword
    (phi/psi/numbonds/pfrag/nfrag): both references are excused.
  * Keywords not populated from PDB/CIF or deferred past 0.1
    (velocities, forces, ANISOU, fragment, type, frame): excused everywhere.
"""

import os
import json

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "..", "data")

# CIF structures whose DSSP chain mapping (auth vs label asym id) differs from
# ProDy's, so secondary-structure macros are excused for ProDy there.
_SS_CIF_XFAIL = ("1atp.cif", "1zbl.cif", "3ay6.cif")

# Keywords MolSelect computes but VMD/ProDy have no selection keyword for (and
# whose molscene compute may be unavailable on some structures).
MOLSCENE_ONLY_KEYWORDS = {"phi", "psi", "pfrag", "nfrag"}

# Keywords not populated from PDB/CIF (or deferred past 0.1): excused everywhere.
OUT_OF_SCOPE_KEYWORDS = {
    "fragment", "frame", "type", "anisotropy",
    "vx", "vy", "vz", "fx", "fy", "fz", "ufx", "ufy", "ufz",
}

# Keywords that are MolSelect-internal CIF/aliasing fields, not contract surface.
SKIP_KEYWORDS = {
    "auth_asym_id", "auth_atom_id", "auth_comp_id", "auth_seq_id",
    "label_seq_id", "label_entity_id", "model", "recname",
}


def _load_json(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Macros
# ---------------------------------------------------------------------------

def _iter_macros():
    """Yield (name, synonyms, definition) for every public macro."""
    data = _load_json("macros.json")
    seen = []

    def walk(node):
        if isinstance(node, dict):
            if "definition" in node and "name" in node:
                seen.append(node)
            else:
                for v in node.values():
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    for m in seen:
        name = m.get("name", "")
        if not name or name.startswith("_"):
            continue
        yield name, m.get("synonyms", []) or [], m.get("definition", "") or ""


def _ss_defaults(definition):
    """Return (prody_query, xfail) for a secondary-structure macro, else None."""
    if "structure" not in definition.split():
        return None
    prody_query = definition.replace("structure", "secstr")
    xfail = {"*": {"vmd": "VMD uses STRIDE; MolSelect/ProDy use DSSP"}}
    for cif in _SS_CIF_XFAIL:
        xfail[cif] = {"prody": "DSSP chain mapping (auth vs label) differs on CIF"}
    return prody_query, xfail


def _is_pure_resname(definition: str) -> bool:
    """True if a macro is defined as a bare ``resname <values>`` list."""
    toks = definition.split()
    if not toks or toks[0] != "resname":
        return False
    return not any(
        t in ("or", "and", "not", "name", "structure") or "(" in t or ")" in t
        for t in toks[1:]
    )


def _is_element_def(definition: str) -> bool:
    """True if a macro is ``element <X>`` or ``not element <X>`` (no operators)."""
    toks = definition.split()
    if toks[:1] == ["element"]:
        rest = toks[1:]
    elif toks[:2] == ["not", "element"]:
        rest = toks[2:]
    else:
        return False
    return bool(rest) and not any(
        t in ("or", "and", "not") or "(" in t or ")" in t for t in rest
    )


def generate_macro_cases(exceptions: dict, extra: list) -> list:
    cases = []
    for name, synonyms, definition in _iter_macros():
        base = {"query": name, "description": f"macro: {name}", "area": "macros"}
        ss = _ss_defaults(definition)
        if ss:
            base["prody_query"], base["xfail"] = ss
        elif _is_pure_resname(definition) or _is_element_def(definition):
            # Compare via MolSelect's own definition: VMD/ProDy native macros may
            # use a different set, so we test that all engines count the SAME
            # resnames/elements identically and document the difference in the note.
            base["prody_query"] = definition
            base["vmd_query"] = definition
            base["note"] = f"MolSelect {name} = `{definition}` (compared via explicit definition)"
        _apply_exception(base, exceptions.get(name))
        cases.append(base)
        # one synonym-equivalence case per synonym (MolSelect-internal check)
        for syn in synonyms:
            cases.append({
                "query": syn, "equiv": name, "area": "macros",
                "description": f"synonym: {syn} = {name}",
            })
    cases.extend(_tag_area(extra, "macros"))
    return cases


# ---------------------------------------------------------------------------
# Keywords
# ---------------------------------------------------------------------------

def _iter_keywords():
    """Yield (name, synonyms, type, example) for every keyword."""
    data = _load_json("keywords.json")["keywords"]
    for category, kws in data.items():
        for name, meta in kws.items():
            yield (name, meta.get("synonyms", []) or [],
                   meta.get("type", "str"), str(meta.get("example", "")).strip())


def _keyword_defaults(name, ktype, example):
    """Default probe query + any divergence-class xfail for a keyword."""
    value = example if example and example != "(none)" else ("0" if ktype != "str" else "X")
    query = f"{name} {value}"
    xfail = None
    if name in MOLSCENE_ONLY_KEYWORDS:
        xfail = {"*": "MolSelect-computed property; no VMD/ProDy selection keyword "
                      "(and molscene compute is unavailable on some structures)"}
    elif name in OUT_OF_SCOPE_KEYWORDS:
        xfail = {"*": "not populated from PDB/CIF or deferred past 0.1"}
    return query, xfail


def generate_keyword_cases(exceptions: dict, extra: list) -> list:
    cases = []
    for name, synonyms, ktype, example in _iter_keywords():
        if name in SKIP_KEYWORDS:
            continue
        query, xfail = _keyword_defaults(name, ktype, example)
        base = {"query": query, "description": f"keyword: {name}", "area": "keywords"}
        if xfail:
            base["xfail"] = xfail
        _apply_exception(base, exceptions.get(name))
        cases.append(base)
        # Synonym-equivalence cases only make sense for keywords whose base case
        # actually evaluates (skip out-of-scope/computed-unavailable ones).
        if name in OUT_OF_SCOPE_KEYWORDS or name in MOLSCENE_ONLY_KEYWORDS:
            continue
        for syn in synonyms:
            if syn in SKIP_KEYWORDS:
                continue
            syn_query = base["query"].replace(name, syn, 1)
            cases.append({
                "query": syn_query, "equiv": base["query"], "area": "keywords",
                "description": f"synonym: {syn} = {name}",
            })
    cases.extend(_tag_area(extra, "keywords"))
    return cases


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _apply_exception(base: dict, exc: dict | None):
    """Merge an exception entry (query/vmd_query/prody_query/xfail/note) onto a base case."""
    if not exc:
        return
    for key in ("query", "vmd_query", "prody_query", "note", "description"):
        if key in exc:
            base[key] = exc[key]
    if "xfail" in exc:
        base["xfail"] = exc["xfail"]  # exception's xfail replaces the class default


def _tag_area(cases: list, area: str) -> list:
    out = []
    for c in cases:
        c = dict(c)
        c.setdefault("area", area)
        out.append(c)
    return out


GENERATORS = {
    "macros": generate_macro_cases,
    "keywords": generate_keyword_cases,
}
