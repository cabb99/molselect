import sys, os

print("⏱ [TEST DEBUG] running", __file__)
print("  cwd      =", os.getcwd())
print("  __package__ =", __package__)
print("  sys.path:")
for p in sys.path:
    print("    ", p)
# now try to locate molselect/data in each entry
for p in sys.path:
    pkg_dir = os.path.join(p, "molselect", "data")
    mod_file = os.path.join(p, "molselect.py")
    if os.path.isdir(pkg_dir):
        print("    → found molselect/data at", pkg_dir)
    if os.path.isfile(mod_file):
        print("    → found file molselect.py at", mod_file)

# now the broken import
import molselect.data as data_pkg
from molselect.python.config import BaseConfig, MultiConfig, ConfigManager


import pytest
from pathlib import Path
import importlib.resources
from importlib import metadata
import molselect.data as data_pkg
from molselect.python.config import BaseConfig, MultiConfig, ConfigManager


def test_baseconfig_user_override(tmp_path):
    # User-specified path should take priority
    custom = tmp_path / "custom.lark"
    custom.write_text("grammar content")
    bc = BaseConfig(
        name="grammar",
        default_pkg=data_pkg,
        default_file="grammar.lark",
        user_path=str(custom),
    )
    assert bc.path == custom


def test_baseconfig_default(tmp_path):
    # Default packaged resource should exist
    bc = BaseConfig(
        name="grammar",
        default_pkg=data_pkg,
        default_file="grammar_template.lark",
    )
    p = bc.path
    assert isinstance(p, Path)
    assert p.exists(), f"Expected default grammar at {p}"
    assert p.suffix == ".lark"


def test_multiconfig_default():
    # No user overrides or plugins => only packaged default
    mc = MultiConfig(
        name="macros",
        default_pkg=data_pkg,
        default_file="macros.json",
    )
    paths = mc.paths
    assert len(paths) == 1
    assert paths[0].name == "macros.json"


def test_multiconfig_user_paths(tmp_path):
    # User paths should precede default
    u1 = tmp_path / "m1.json"
    u2 = tmp_path / "m2.json"
    u1.write_text("{}")
    u2.write_text("{}")
    mc = MultiConfig(
        name="macros",
        default_pkg=data_pkg,
        default_file="macros.json",
        user_paths=[str(u1), str(u2)],
    )
    paths = mc.paths
    assert paths[0] == u1
    assert paths[1] == u2
    assert paths[2].name == "macros.json"


def test_multiconfig_plugins(monkeypatch, tmp_path):
    # Simulate entry-point plugins
    plugin_file = tmp_path / "plugin.json"
    plugin_file.write_text("{}")

    class DummyEP:
        def __init__(self, name, load_val):
            self.name = name
            self._val = load_val
        def load(self):
            return str(self._val)

    # Monkeypatch metadata.entry_points to return our dummy
    monkeypatch.setattr(
        metadata, "entry_points", lambda group: [DummyEP("p1", plugin_file)]
    )

    mc = MultiConfig(
        name="macros",
        default_pkg=data_pkg,
        default_file="macros.json",
        entry_point_group="molselect.macros",
    )
    paths = mc.paths
    # Default + plugin
    assert paths[-1] == plugin_file


def test_configmanager_defaults():
    # ConfigManager should expose valid defaults
    cm = ConfigManager()
    # Grammar default exists
    assert cm.grammar.path.exists()
    # Macros and keywords include their default files
    assert any(p.name == "macros.json" for p in cm.macros.paths)
    assert any(p.name == "keywords.json" for p in cm.keywords.paths)


def test_configmanager_override(tmp_path):
    # Overrides should propagate correctly
    g = tmp_path / "g.lark"
    m = tmp_path / "m.json"
    k = tmp_path / "k.json"
    g.write_text("g")
    m.write_text("{}")
    k.write_text("[]")

    cm = ConfigManager(
        grammar=str(g),
        macros=[str(m)],
        keywords=[str(k)],
    )
    assert cm.grammar.path == g
    assert cm.macros.paths[0] == m
    assert cm.keywords.paths[0] == k

def test_grammar_replacement_via_setter(tmp_path):
    # Dynamically replace the BaseConfig.path after init
    new_grammar = tmp_path / "new_grammar.lark"
    new_grammar.write_text("dummy")
    cm = ConfigManager()
    # originally it points at the packaged default
    assert cm.grammar.path != new_grammar
    # now replace
    cm.grammar.path = new_grammar
    assert cm.grammar.path == new_grammar


def test_macros_add_and_precedence(tmp_path):
    # Adding a new user path should come first in the list
    cm = ConfigManager()
    default_macro = Path(importlib.resources.files(data_pkg) / "macros.json")
    assert default_macro in cm.macros.paths

    custom = tmp_path / "extra_macro.json"
    custom.write_text("{}")
    cm.macros.add(str(custom))

    # custom was prepended
    assert cm.macros.paths[0] == custom
    # the old default is still present (just shifted)
    assert default_macro in cm.macros.paths


def test_macros_remove(tmp_path):
    # Remove the default macro via the new public API
    cm = ConfigManager()
    default_macro = Path(importlib.resources.files(data_pkg) / "macros.json")
    assert default_macro in cm.macros.paths

    cm.macros.remove(default_macro)
    assert default_macro not in cm.macros.paths


def test_macros_replace_via_constructor(tmp_path):
    m1 = tmp_path / "m1.json"
    m2 = tmp_path / "m2.json"
    m1.write_text("{}")
    m2.write_text("{}")

    cm = ConfigManager(macros=[str(m1), str(m2)])
    # When you pass user_paths into the constructor, the default is omitted
    assert cm.macros.paths == [m1, m2]


def test_keywords_replace_and_add(tmp_path):
    cm = ConfigManager()
    default_kw = Path(importlib.resources.files(data_pkg) / "keywords.json")
    assert default_kw in cm.keywords.paths

    # Replace the entire list via the new replace() method
    new_kw = tmp_path / "new_keywords.json"
    new_kw.write_text("[]")
    cm.keywords.replace([str(new_kw)])
    assert cm.keywords.paths == [new_kw]

    # And you can still prepend additional files
    extra = tmp_path / "extra_kw.json"
    extra.write_text("[]")
    cm.keywords.add(str(extra))
    assert cm.keywords.paths[0] == extra
    assert new_kw in cm.keywords.paths
