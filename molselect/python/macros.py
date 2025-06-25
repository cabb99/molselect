import os
import json
from typing import Dict
import logging

logger = logging.getLogger(__name__)

class MacrosLoader:
    """Loads and expands macros from a JSON file."""
    def __init__(self, macros_path: str):
        self.macros = self._load_macros(macros_path)
    def _load_macros(self, macros_path: str) -> Dict[str, str]:
        macros_flat = {}
        if os.path.exists(macros_path):
            with open(macros_path, 'r') as f:
                try:
                    macros_json = json.load(f)
                    for category in macros_json.get('macros', {}):
                        for macro_name, macro_obj in macros_json['macros'][category].items():
                            definition = macro_obj.get('definition', '')
                            macros_flat[macro_name] = definition
                            for syn in macro_obj.get('synonyms', []):
                                macros_flat[syn] = definition
                except Exception as e:
                    logger.warning(f"Failed to load macros from {macros_path}: {e}")
        return macros_flat
    def expand_macro(self, name: str, seen=None) -> str:
        if seen is None:
            seen = set()
        if name not in self.macros:
            raise ValueError(f"Macro {name!r} not defined")
        expr = self.macros[name]
        tokens = expr.split()
        expanded = []
        for token in tokens:
            macro_key = token[1:] if token.startswith('@') else token
            if macro_key in self.macros and macro_key not in seen:
                seen.add(macro_key)
                expanded_sub = self.expand_macro(macro_key, seen)
                expanded.append(expanded_sub)
                seen.remove(macro_key)
            else:
                expanded.append(token)
        return ' '.join(expanded)
