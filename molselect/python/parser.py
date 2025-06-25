from lark import Lark, Tree
import logging
from molselect.python.config import config
from molselect.python.grammar import load_json, make_token_block, compute_last_token_pattern

logger = logging.getLogger(__name__)

class SelectionParser:
    """Parses selection strings to parse trees using Lark."""
    def __init__(self):
        # Load configuration
        grammar_template_path = config.grammar.path
        macros_paths = config.macros.paths
        keywords_paths = config.keywords.paths

        # Load template and JSON
        grammar_template = grammar_template_path.read_text(encoding='utf-8')

        macros_dict = {}
        for macro_path in macros_paths:
            if not macro_path.exists():
                logger.warning(f"Macros JSON file {macro_path} does not exist, skipping.")
                continue
            logger.info(f"Loading macros from {macro_path}")
            macros_dict.update(load_json(macro_path)["macros"])

        keywords_dict = {}
        for keyword_path in keywords_paths:
            if not keyword_path.exists():
                logger.warning(f"Keywords JSON file {keyword_path} does not exist, skipping.")
                continue
            logger.info(f"Loading keywords from {keyword_path}")
            keywords_dict.update(load_json(keyword_path)["keywords"])

        # Build macro & keyword sections
        macros_block, macros_names = make_token_block(macros_dict, prefix='bool')
        keywords_block, keywords_names = make_token_block(keywords_dict, prefix='select')

        # First round of replacements
        grammar_interim = (
            grammar_template
            .replace("<<MACROS>>", macros_block)
            .replace("<<MACROS_NAMES>>", macros_names)
            .replace("<<KEYWORDS>>", keywords_block)
            .replace("<<KEYWORDS_NAMES>>", keywords_names)
        )

        # Compute last‐token pattern
        last_token_pattern = compute_last_token_pattern(grammar_interim)

        # Final injection
        grammar_final = grammar_interim.replace("<<LAST_TOKEN>>", last_token_pattern)

        # Flatten macros for expansion (after grammar construction)
        flat_macros_dict = {}
        for category in macros_dict:
            for macro_name, macro_obj in macros_dict[category].items():
                definition = macro_obj.get("definition", "")
                flat_macros_dict[macro_name] = definition
                for syn in macro_obj.get("synonyms", []):
                    flat_macros_dict[syn] = definition
        self.macros_dict = flat_macros_dict

        # Pass grammar text to Lark
        self.lark = Lark(grammar_final, parser='lalr', propagate_positions=True, start=['start', 'expr'])

    def parse(self, text: str, start_rule: str = 'start') -> Tree:
        return self.lark.parse(text, start=start_rule)

    def expand_macro(self, name: str, seen=None) -> str:
        """Expand a macro by name, recursively expanding any referenced macros."""
        if seen is None:
            seen = set()
        if name not in self.macros_dict:
            raise ValueError(f"Macro {name!r} not defined")
        expr = self.macros_dict[name]
        tokens = expr.split()
        expanded = []
        for token in tokens:
            macro_key = token[1:] if token.startswith('@') else token
            if macro_key in self.macros_dict and macro_key not in seen:
                seen.add(macro_key)
                expanded_sub = self.expand_macro(macro_key, seen)
                expanded.append(expanded_sub)
                seen.remove(macro_key)
            else:
                expanded.append(token)
        return ' '.join(expanded)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = SelectionParser()
    example = "protein and (resid 10 to 20)"
    print(f"Parsing example: {example!r}")
    try:
        tree = parser.parse(example)
        print("Parse tree:")
        print(tree.pretty())
    except Exception as e:
        print(f"Failed to parse: {e}")

    print("Available macros:")
    for macro_name in parser.macros_dict.keys():
        print(f" - {macro_name}")

    print("Expanding macro 'protein':")
    print(parser.expand_macro('protein'))