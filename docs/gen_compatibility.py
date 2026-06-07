#!/usr/bin/env python3
"""Generate docs/Compatibility.md from the selection-contract test cases.

The compatibility table is derived directly from the ``xfail`` annotations in
``molselect/python/tests/cases/*.jsonc`` (and the divergence classes baked into
``case_gen.py``). Every documented divergence therefore corresponds to exactly
one expected-failure in the contract suite — the docs cannot promise a
difference that is not tested, and cannot hide one that is.

Run:  python docs/gen_compatibility.py
"""

import os
import sys
import glob
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.abspath(os.path.join(HERE, "..", "molselect", "python", "tests"))
sys.path.insert(0, TESTS)

import case_gen  # noqa: E402
from backends_ref import load_jsonc  # noqa: E402

OUT = os.path.join(HERE, "Compatibility.md")


def load_cases():
    cases = []
    for path in sorted(glob.glob(os.path.join(TESTS, "cases", "*.jsonc"))):
        data = load_jsonc(path)
        area = os.path.splitext(os.path.basename(path))[0]
        if isinstance(data, dict) and "generate" in data:
            cases.extend(case_gen.GENERATORS[data["generate"]](
                data.get("exceptions", {}), data.get("extra", [])))
        else:
            for entry in data:
                entry = dict(entry)
                entry.setdefault("area", area)
                cases.append(entry)
    return cases


def scope_label(pattern: str) -> str:
    return {"*": "all structures", "*.cif": "CIF files", "*.pdb": "PDB files"}.get(pattern, pattern)


# (engine, reason) -> set of (area, query, scope)
def collect(cases):
    vmd, prody, both, molselect = (defaultdict(set) for _ in range(4))
    for c in cases:
        xf = c.get("xfail")
        if not xf:
            continue
        q = c["query"]
        area = c.get("area", "")
        for pattern, val in xf.items():
            scope = scope_label(pattern)
            if isinstance(val, dict):
                for ref, reason in val.items():
                    target = {"vmd": vmd, "prody": prody, "molscene": molselect}.get(ref)
                    if target is not None:
                        target[reason].add((area, q, scope))
            else:  # bare string excuses all references / a MolSelect-side limit
                gap = any(k in val for k in (
                    "grammar", "mis-parse", "molscene", "computed", "compute",
                    "incomplete", "upstream", "limitation", "unavailable",
                    "populated", "deferred", "scope"))
                bucket = molselect if gap else both
                bucket[val].add((area, q, scope))
    return vmd, prody, both, molselect


def render_section(title, mapping, intro):
    lines = [f"## {title}", "", intro, ""]
    if not mapping:
        lines.append("_None._\n")
        return "\n".join(lines)
    for reason in sorted(mapping):
        rows = sorted(mapping[reason])
        lines.append(f"**{reason}**")
        lines.append("")
        lines.append("| Selection | Area | Scope |")
        lines.append("|---|---|---|")
        for area, q, scope in rows:
            qd = q.replace("|", "\\|")
            lines.append(f"| `{qd}` | {area} | {scope} |")
        lines.append("")
    return "\n".join(lines)


def main():
    cases = load_cases()
    vmd, prody, both, molselect = collect(cases)
    n_x = sum(len(v) for m in (vmd, prody, both, molselect) for v in m.values())

    header = f"""# Compatibility with VMD and ProDy

MolSelect's selection grammar is a superset of the common VMD/ProDy syntax, but
the three engines do **not** always select the same atoms — they disagree with
*each other* on some keywords and macros (connectivity vs. resname definitions,
STRIDE vs. DSSP, single- vs. double-precision coordinates, …). MolSelect picks a
single, documented behaviour and this page lists every place it differs from a
reference engine.

Each row below is backed by exactly one expected-failure (`xfail`) in
`molselect/python/tests/test_selection_contract.py`, generated from
`cases/*.jsonc`. This file is produced by `docs/gen_compatibility.py` — do not
edit it by hand; edit the test cases and regenerate.

> Scope `all structures` means the divergence is inherent to the selection;
> a specific structure (e.g. `1r70.pdb`) or `CIF files` means it only appears
> there, usually because of that structure's chemistry or file format.

{len(cases)} contract cases · {n_x} documented divergences.
"""

    sections = [
        header,
        render_section(
            "VMD differs", vmd,
            "MolSelect agrees with ProDy here; VMD selects a different set."),
        render_section(
            "ProDy differs", prody,
            "MolSelect agrees with VMD here; ProDy selects a different set or "
            "lacks the keyword."),
        render_section(
            "VMD and ProDy both differ", both,
            "A MolSelect definition choice that neither reference shares."),
        render_section(
            "MolSelect limitations", molselect,
            "Known gaps in MolSelect itself, or properties MolSelect computes "
            "that the reference engines have no selection keyword for."),
    ]
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(sections).rstrip() + "\n")
    print(f"Wrote {OUT}: {len(cases)} cases, {n_x} divergences")


if __name__ == "__main__":
    main()
