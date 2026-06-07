# Differences from VMD and ProDy

MolSelect's selection language follows the same family of atom-selection syntax
used by VMD and ProDy, and for most selections all three programs return the
same atoms. In a number of cases they do not, often because VMD and ProDy
themselves define a keyword in incompatible ways. This page describes the known
differences and, where MolSelect can reproduce a particular program's result,
the selection to use.

## Protein and amino-acid selections

MolSelect identifies protein by residue name, the same way ProDy does: any
standard or non-standard amino acid counts. VMD instead identifies protein from
connectivity, requiring each residue's atoms to form a connected C, CA, N and O
backbone. The two approaches disagree on structures whose backbone is incomplete
or unusual. A C-alpha trace such as 1r70 has no connected backbone, so VMD
reports no protein at all while MolSelect still recognises the residues;
conversely a cofactor that carries an amino-acid moiety, such as SAH in pdb3mht,
is counted as protein by VMD but not by MolSelect. MolSelect's `protein`
therefore follows ProDy. To obtain VMD's connectivity-based result instead, use
the `vmd_protein` macro (also available as `aminoacid`). The same difference
carries into `calpha`, `sidechain` and `is_protein`.

The `backbone` macro covers both the protein backbone and the nucleic-acid
backbone. ProDy's `backbone` is protein only; to match it, use `protein_backbone`
in MolSelect, or `nucleic_backbone` for the nucleic portion alone. VMD's backbone
atom set is connectivity-derived and differs again, and there is no exact
MolSelect equivalent for it.

The `hetero` and `hetatm` macros select anything that is neither protein nor
nucleic, which is the ProDy definition. VMD ties `hetero` more closely to the
HETATM records and to its connectivity-based protein detection, so the two
diverge whenever modified residues are present, and on the 1r70 C-alpha trace
where VMD treats every atom as heteroatom.

A few residue-class macros use a different residue list in each program. The
`acidic` macro, and therefore `charged`, includes the phosphorylated residues
SEP, TPO, PTR and PHD, which the built-in VMD and ProDy flags exclude. The
`neutral` macro uses the ProDy residue set rather than the VMD one, and
`aliphatic` follows VMD (ALA, GLY, ILE, LEU, VAL) where ProDy additionally
includes PRO. When you need a precise set in any program, name the residues
explicitly with `resname`.

## Residue numbering in mmCIF files

On mmCIF files, `resid` and `resnum` use the author numbering (`auth_seq_id`),
matching ProDy and the numbering printed in the original PDB record. VMD uses the
internal sequential numbering (`label_seq_id`) instead, so a selection such as
`resid 4` can pick different residues in the two programs. PDB files carry only
one numbering, so all three agree there. To reproduce VMD's numbering in
MolSelect, select on `label_seq_id` directly.

## Secondary structure

MolSelect assigns secondary structure with DSSP, as ProDy does, while VMD uses
STRIDE. The two algorithms label residues differently, so any selection on
`helix`, `sheet`, `coil`, `turn` or `secondary` can differ from VMD, and there is
no MolSelect selection that reproduces a STRIDE assignment. The class definitions
also differ between MolSelect and ProDy: MolSelect's `helix` covers the DSSP
codes H, G and I (alpha, 3-10 and pi helices), whereas ProDy's `helix` is the H
code alone. To match ProDy's narrower definition, select `secondary H` or use
`alpha_helix`. ProDy also represents coil as an empty code rather than C. On
mmCIF files the DSSP assignment is keyed by author chain, and the chain mapping
can shift a few residues relative to ProDy on some structures.

## Numeric selections

Ranges written as `N:M` include the upper bound M, the same as `N to M`, while
ProDy treats `N:M` as exclusive of M. The stepped form `N:M:S` is specific to
MolSelect. For portable behaviour, prefer the `N to M` form. Ranges must be
written with spaces; the glued form `10to15` is not yet recognised as a range,
so write `resid 10 to 15`.

An exact match on a coordinate, such as `x 6.665`, can select one atom more or
fewer in VMD than in MolSelect, because VMD stores coordinates in single
precision while MolSelect keeps the file's full precision. A small range such as
`x 6.664 to 6.666` avoids the discrepancy.

The `mass` keyword matches within a tolerance, so `mass 12` selects carbon. VMD
stores integer masses and behaves the same way, but ProDy compares the exact
floating-point mass, where 12 does not equal 12.011 and the selection is empty;
give a range such as `mass 11.5 to 12.5` when an exact match is needed. The
`charge` keyword has no effect in ProDy, which does not read partial charges from
PDB files, and `radius` is not a ProDy keyword at all; both work in MolSelect.

## Strings, quoting and regular expressions

A value in double quotes, such as `name "C.*"`, is treated as a regular
expression. A value in single quotes, such as `resname 'DG'`, is a literal
string; ProDy does not accept single-quoted values, so use the unquoted form
`resname DG` for results that agree with ProDy. ProDy also anchors regular
expressions differently on a few atom names, allows only one regular expression
per selection term, and cannot mix a regular expression with literal values in
the same term, so split such selections into separate terms when comparing with
ProDy.

## Set selections

The `same <field> as <selection>` form works for any field in MolSelect, for
example `same name as ...` or `same resname as ...`. ProDy supports only `chain`,
`residue`, `segment` and `fragment` in this position, so restrict the field to
those when ProDy compatibility matters.

## Keywords specific to one program

The `segment` and `icode` keywords are not available in VMD, which uses `segname`
in place of `segment` and has no insertion-code keyword; both work in MolSelect
and ProDy, and `_` matches the blank value. The `radius` keyword is unavailable
in ProDy. The `numbonds` keyword is available in VMD, but VMD's bond detection
differs from MolSelect's, so the counts need not agree.

## Operators and function names

MolSelect accepts a wider range of spellings than the reference programs.
Exponentiation may be written `**` or `^`; ProDy accepts only `^`, and VMD only
`**`. Floor division `//`, chained comparisons such as `0 < x < 10`, and the
exclusive-or operator `xor` are MolSelect features that neither VMD nor ProDy
provides. Among the mathematical functions, MolSelect accepts `arcsin`, `arccos`
and `arctan` alongside `asin`, `acos` and `atan`; `ln` alongside `log`; and `sq`,
`sqr` and `square` for the squaring function. ProDy uses `asin`, `log` and `sq`,
VMD uses `asin`, `log` and `sqr`, and ProDy's `tanh` is unavailable. MolSelect
maps each spelling to the appropriate function, so selections written in either
program's style are accepted.

## Properties computed by MolSelect

The `phi`, `psi`, `numbonds`, `pfrag` and `nfrag` keywords are computed by
MolSelect from the structure. VMD and ProDy mostly have no equivalent selection
keyword for them, so there is nothing to compare against; these are MolSelect
features rather than points of disagreement.

## Current limitations

The `vmd_nucleic` macro is not yet fully implemented and currently selects no
atoms. The velocity (`vx`, `vy`, `vz`), force (`fx`, `fy`, `fz`) and ANISOU
(`ufx`, `ufy`, `ufz`, `anisotropy`) fields, along with `fragment`, `type` and
`frame`, are not populated from PDB or mmCIF input in this release.
