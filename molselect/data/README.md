# MolSelect Data Directory

This directory contains the core data files that define the **protected words** for the MolSelect selection grammar. These protected words are essential for parsing and interpreting selection queries in molecular modeling and analysis. The files here provide the **base keywords**, **base macros**, and the **Lark grammar template** used by the parser. Other packages can extend these definitions by adding their own keywords and macros.

---

## Contents

- **`keywords.json`**: Defines the base set of selection keywords (properties, names, indices, etc.) and their synonyms, types, and descriptions.
- **`macros.json`**: Contains reusable macro definitions for common molecular groups (e.g., `protein`, `water`, `ion`) and their logical combinations.
- **`grammar_template.lark`**: The Lark grammar template for the selection language, with placeholders for keywords and macros.

---

## Keywords

The `keywords.json` file provides a structured list of all **base keywords** recognized by the grammar. Each keyword entry includes:

- **Name**: The canonical name of the keyword (e.g., `resname`, `chain`, `element`).
- **Synonyms**: Alternative names or aliases for the keyword.
- **Type**: The expected data type (`int`, `str`, `float`).
- **Short**: A brief description.
- **Description**: A detailed explanation of the keyword's meaning and usage.

**Example:**
```json
"resname": {
  "synonyms": ["label_comp_id", "resName"],
  "type": "str",
  "short": "Residue name.",
  "description": [
    "Residue name. Three-letter code (e.g., 'GLY' for glycine)."
  ]
}
```

---

## Macros

The `macros.json` file defines **base macros**, which are named logical groups or patterns that can be used in selection queries. Macros can represent sets of residues, atom types, or logical groupings (e.g., `protein`, `nucleic`, `water`, `ion`). Each macro includes:

- **Name**: The macro's identifier.
- **Synonyms**: Alternative names.
- **Short**: A brief description.
- **Description**: A detailed explanation of the macros meaning and usage.
- **Definition**: The selection expression or logic the macro expands to.

Macros can reference other macros, allowing for composable and extensible selection logic.

**Example:**
```json
"protein": {
  "name": "protein",
  "synonyms": ["is_protein"],
  "short": "all amino acids",
  "description": "All standard and non-standard amino acids (must have a CA atom).",
  "definition": "_std_aa or _nonstd_aa"
}
```

---

## Grammar Template

The `grammar_template.lark` file is a Lark parser grammar for the selection language. It includes placeholders (`<<KEYWORDS>>`, `<<MACROS>>`, etc.) that are dynamically filled with the current set of keywords and macros at runtime. This ensures that all protected words are reserved and recognized by the parser.

**Key features:**
- Logical operations (`and`, `or`, `not`, etc.)
- Selection expressions using keywords and macros
- Arithmetic and comparison operators
- Support for string, numeric, and regex values
- Extensible: other packages can inject additional keywords/macros

**Placeholders:**
- `<<KEYWORDS>>` and `<<KEYWORDS_NAMES>>`: Insert all base and extended keywords.
- `<<MACROS>>` and `<<MACROS_NAMES>>`: Insert all base and extended macros.
- `<<LAST_TOKEN>>`: Insert the fallback token for string values (used as a last resort for unmatched input at the end of the grammar).

---

## Extending the Grammar

Other packages can add their own keywords and macros by providing additional JSON files or by programmatically injecting new entries. The grammar template will automatically include these new protected words, ensuring they are reserved and parsed correctly. Users can also copy the grammar file and use a modified version of this grammar file with the same placeholders in place.