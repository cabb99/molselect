#!/usr/bin/env python3
"""
scripts/generate_grammar.py

Reads:
  - molscene/selection/grammar_template.lark
  - macros.json
  - keywords.json

Writes:
  - molscene/selection/grammar.lark

Usage:
  python scripts/generate_grammar.py
"""

import re
from pathlib import Path

import json   # pip install json5
import logging

logger = logging.getLogger(__name__)

def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def make_token_block(tokens: dict, prefix='token') -> tuple[str, str, str]:
    """
    Returns (block_text, names_alternation, category_rules)
    - block_text: all token rules, grouped by category, with comments
    - names_alternation: all token names (for | alternation)
    - category_rules: one rule per category, e.g. ?bool_biomolecule: PROTEIN | NUCLEIC | ...
    """
    lines = []
    names = []
    categories = []
    for category in tokens.keys():
        
        cat_tokens = []
        # Add a comment for the category
        lines.append(f"")
        lines.append(f"// {category}")
        for token in tokens[category]:
            if token.startswith("_"):
                continue
            name = token
            token_data = tokens[category][token]
            macro_token = f"{name.upper()}"
            macro_rule = f'{macro_token} : "{name}"'
            if "synonyms" in token_data and len(token_data["synonyms"]) > 0:
                macro_rule += " | " + " | ".join(f'"{syn}"' for syn in token_data["synonyms"])
            lines.append(macro_rule)
            names.append(macro_token)
            cat_tokens.append(macro_token)
        # Add a category rule if there are tokens
        if cat_tokens:
            # Use category name for rule, e.g. bool_biomolecule
            rule_name = f"{prefix}_{category.lower()}"
            category_rule = f"?{rule_name}: " + " | ".join(cat_tokens)
            lines.append(category_rule)
            categories.append(rule_name)
        else:
            for i in range(2):
                lines.pop()
    return "\n".join(lines), " | ".join(categories)


def compute_last_token_pattern(grammar_text: str) -> str:
    """
    Scans all lines of the (already-injected) grammar for
    UPPERCASE_TOKEN : "lit" and collects every lit,
    then builds the negative-lookahead regex.
    """
    # Remove comments
    no_comments = re.sub(r'//.*', '', grammar_text)
    reserved = []
    for line in no_comments.splitlines():
        m = re.match(r'^\s*([A-Z_][A-Z0-9_]*)\s*:\s*(.+)$', line)
        if not m:
            continue
        for lit in re.findall(r'"([^"]+)"', m.group(2)):
            reserved.append(lit)
    # Build alternation pattern for reserved words
    kw_pat = "|".join(map(re.escape, reserved))
    # Compose the last-token regex pattern (no ^/$ anchors, use \b after reserved alternation)
    last_token_pattern = (
        r"""(?![-'"()])"""  # not starting with these punctuations
        rf"""(?!(?:{kw_pat})\b)"""  # not a reserved word
        r"""(?!\d+(?:\.\d*)?(?:[eE][+-]?\d+)?\b)"""  # not a number
        r"(?=[A-Za-z])"  # must start with a letter
        r"""[^()'"\s]+"""  # match token
    )

    last_token_pattern = last_token_pattern.replace('/', r'\/')
    return f"/{last_token_pattern}/"


def main(file_out: Path | None = None):
    from molselect.python.config import ConfigManager
    from tempfile import NamedTemporaryFile
    """
    Generate the grammar.lark file from the template and JSON files.
    This script reads the grammar template, macros, and keywords,
    processes them to create the final grammar file, and writes it out.
    """

    # Load configuration
    cfg = ConfigManager()
    TEMPLATE = cfg.grammar.path
    MACROS_JSON = cfg.macros.paths
    KEYWORDS_JSON = cfg.keywords.paths

    # load template + JSON

    tpl_text  = TEMPLATE.read_text()
    
    macros={}
    for json_path in MACROS_JSON:
        if not json_path.exists():
            logger.warning(f"Macros JSON file {json_path} does not exist, skipping.")
            continue
        logger.info(f"Loading macros from {json_path}")
        macros.update(load_json(json_path)["macros"])

    keywords = {}
    for json_path in KEYWORDS_JSON:
        if not json_path.exists():
            logger.warning(f"Keywords JSON file {json_path} does not exist, skipping.")
            continue
        logger.info(f"Loading keywords from {json_path}")
        keywords.update(load_json(json_path)["keywords"])

    # build macro & keyword sections
    macros_block, macros_names = make_token_block(macros, prefix='bool')
    kw_block,    kw_names      = make_token_block(keywords, prefix='select')

    # first round of replacements
    interim = (
        tpl_text
        .replace("<<MACROS>>", macros_block)
        .replace("<<MACROS_NAMES>>", macros_names)
        .replace("<<KEYWORDS>>", kw_block)
        .replace("<<KEYWORDS_NAMES>>", kw_names)
    )

    # compute last‐token pattern
    last_tok = compute_last_token_pattern(interim)

    # final injection
    final = interim.replace("<<LAST_TOKEN>>", last_tok)

    #Write to a temporary file or the specified output file
    if file_out is None:
        with NamedTemporaryFile(delete=False, suffix='.lark') as tempo:
            tempo.write_text(final)
            file_out = Path(tempo.name)
    else:
        file_out = Path(file_out)
        if not file_out.suffix:
            file_out = file_out.with_suffix('.lark')
        tempo = file_out.parent / f"{file_out.name}"
        if tempo.exists():
            logger.warning(f"Temporary file {tempo} already exists, overwriting.")
        tempo.write_text(final)


if __name__ == "__main__":
    main('temp_grammar.lark')
