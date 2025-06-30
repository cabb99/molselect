from lark import Lark, Tree
import logging
from molselect.python.config import config
from molselect.python.grammar import load_json, make_token_block, compute_last_token_pattern
from molselect.python.errors import MolSelectMacroError

logger = logging.getLogger(__name__)

class SelectionParser:
    """Parses selection strings to parse trees using Lark."""
    MAX_MACRO_DEPTH = 10

    def __init__(self, parser_kwargs=None):
        self._build_parser_and_macros(**parser_kwargs if parser_kwargs else {})

    def _build_parser_and_macros(self, macros_dict=None, keywords_dict=None, **parser_kwargs):
        """
        Internal method to build the grammar, initialize Lark, and update macro/keyword dicts.
        If macros_dict or keywords_dict is None, reload from config; otherwise, use the provided dicts.
        """
        # Load grammar template
        grammar_template_path = config.grammar.path
        grammar_template = grammar_template_path.read_text(encoding='utf-8')

        # Load macros
        if macros_dict is None:
            macros_dict = {}
            for macro_path in config.macros.paths:
                if not macro_path.exists():
                    logger.warning(f"Macros JSON file {macro_path} does not exist, skipping.")
                    continue
                logger.info(f"Loading macros from {macro_path}")
                macros_dict.update(load_json(macro_path)["macros"])
        self._macros_dict_full = macros_dict

        # Load keywords
        if keywords_dict is None:
            keywords_dict = {}
            for keyword_path in config.keywords.paths:
                if not keyword_path.exists():
                    logger.warning(f"Keywords JSON file {keyword_path} does not exist, skipping.")
                    continue
                logger.info(f"Loading keywords from {keyword_path}")
                keywords_dict.update(load_json(keyword_path)["keywords"])
        self._keywords_dict_full = keywords_dict

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
        self.grammar = grammar_interim.replace("<<LAST_TOKEN>>", last_token_pattern)
        # Pass grammar text to Lark
        self.lark = Lark(self.grammar, propagate_positions=True, start=['start', 'expr'], **parser_kwargs)

        # Flatten macros for expansion (after grammar construction)
        flat_macros_dict = {}
        for category in macros_dict:
            for macro_name, macro_obj in macros_dict[category].items():
                definition = macro_obj.get("definition", "")
                flat_macros_dict[macro_name] = definition
                for syn in macro_obj.get("synonyms", []):
                    flat_macros_dict[syn] = definition
        self.macros_dict = flat_macros_dict

    def parse(self, text: str, start_rule: str = 'start') -> Tree:
        return self.lark.parse(text, start=start_rule)
    
    def expand_macro(self, name: str, depth: int = 0) -> str:
        if depth > self.MAX_MACRO_DEPTH:
            raise MolSelectMacroError(
                name,
                f"Macro expansion exceeded maximum depth of {self.MAX_MACRO_DEPTH}"
            )
        if name not in self.macros_dict:
            raise MolSelectMacroError(name, f"Macro {name!r} not defined")

        tokens = self.macros_dict[name].split()
        expanded = []
        for tok in tokens:
            if tok.startswith('@'):
                sub = tok[1:]
                expanded.append(self.expand_macro(sub, depth + 1))
            elif tok in self.macros_dict:
                expanded.append(self.expand_macro(tok, depth + 1))
            else:
                expanded.append(tok)
        return f"({' '.join(expanded)})"

    def remove_macro(self, macro_name: str, category: str = 'Custom'):
        """
        Remove a macro from the parser by name and category, rebuild the grammar, and re-initialize Lark.
        If the macro or category does not exist, this is a no-op.
        """
        macros_dict = getattr(self, '_macros_dict_full', None)
        if macros_dict is None:
            self._build_parser_and_macros()
            macros_dict = self._macros_dict_full
        if category in macros_dict and macro_name in macros_dict[category]:
            del macros_dict[category][macro_name]
            # Remove category if empty
            if not macros_dict[category]:
                del macros_dict[category]
            self._build_parser_and_macros(macros_dict)

    def set_macro(self, macro_name: str, definition: str, synonyms: list = None, category: str = 'Custom', regex_substitution: dict = None):
        """
        Add or edit a macro to the parser, rebuild the grammar, and re-initialize Lark.
        category: The macro category (e.g., 'biomolecule').
        macro_name: The name of the macro (e.g., 'protein').
        definition: The macro definition string.
        synonyms: Optional list of synonyms for the macro.
        regex_substitution: Optional dict mapping macro_name and synonyms to regex patterns.
        
        Note: If the macro name starts with '_', it will be treated as a hidden macro and not included in the grammar.
        This allows for internal macros that can be used for recursion or other purposes without being exposed in the grammar.
        """
        if synonyms is None:
            synonyms = []
        if regex_substitution is None:
            regex_substitution = {}
        macros_dict = getattr(self, '_macros_dict_full', None)
        if macros_dict is None:
            self._build_parser_and_macros()
            macros_dict = self._macros_dict_full
        if category not in macros_dict:
            macros_dict[category] = {}
        macros_dict[category][macro_name] = {
            'definition': definition,
            'synonyms': synonyms,
            'regex_substitution': regex_substitution
        }
        self._build_parser_and_macros(macros_dict)

    def set_keyword(self, keyword_name: str, definition: str, synonyms: list = None, category: str = 'Custom', regex_substitution: dict = None):
        """
        Add or edit a keyword to the parser, rebuild the grammar, and re-initialize Lark.
        category: The keyword category (e.g., 'residue').
        keyword_name: The name of the keyword (e.g., 'ALA').
        definition: The keyword definition string.
        synonyms: Optional list of synonyms for the keyword.
        regex_substitution: Optional dict mapping keyword_name and synonyms to regex patterns.
        """
        if synonyms is None:
            synonyms = []
        if regex_substitution is None:
            regex_substitution = {}
        macros_dict = getattr(self, '_macros_dict_full', None)
        if macros_dict is None:
            self._build_parser_and_macros()
            macros_dict = self._macros_dict_full
        keywords_dict = getattr(self, '_keywords_dict_full', None)
        if keywords_dict is None:
            keywords_dict = {}
            for keyword_path in config.keywords.paths:
                if not keyword_path.exists():
                    continue
                keywords_dict.update(load_json(keyword_path)["keywords"])
        if category not in keywords_dict:
            keywords_dict[category] = {}
        keywords_dict[category][keyword_name] = {
            'definition': definition,
            'synonyms': synonyms,
            'regex_substitution': regex_substitution
        }
        self._keywords_dict_full = keywords_dict
        self._build_parser_and_macros(macros_dict, keywords_dict)

    def remove_keyword(self, keyword_name: str, category: str = 'Custom'):
        """
        Remove a keyword from the parser by name and category, rebuild the grammar, and re-initialize Lark.
        If the keyword or category does not exist, this is a no-op.
        """
        macros_dict = getattr(self, '_macros_dict_full', None)
        if macros_dict is None:
            self._build_parser_and_macros()
            macros_dict = self._macros_dict_full
        keywords_dict = getattr(self, '_keywords_dict_full', None)
        if keywords_dict is None:
            keywords_dict = {}
            for keyword_path in config.keywords.paths:
                if not keyword_path.exists():
                    continue
                keywords_dict.update(load_json(keyword_path)["keywords"])
        if category in keywords_dict and keyword_name in keywords_dict[category]:
            del keywords_dict[category][keyword_name]
            if not keywords_dict[category]:
                del keywords_dict[category]
            self._keywords_dict_full = keywords_dict
            self._build_parser_and_macros(macros_dict, keywords_dict)