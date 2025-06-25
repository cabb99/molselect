"""
MolSelect Configuration Management
==================================

This module provides centralized configuration management for the MolSelect package, following the MolSSI documentation style.

Overview
--------
This module defines classes for handling file-based configuration, supporting both single-file and multi-file (with plugin) scenarios. It is designed to allow user overrides, packaged defaults, and plugin-based extensions for configuration files such as grammars, macros, and keywords.

Classes
-------

BaseConfig
~~~~~~~~~~
.. autoclass:: molselect.python.config.BaseConfig
   :members:
   :undoc-members:
   :show-inheritance:

    Single-file configuration with layered overrides.

    **Layers (in order of precedence):**
      1. A user-supplied path (via constructor or setter)
      2. A packaged default resource (from importlib.resources)

    **Attributes:**
        - name (str): Identifier used in logging.
        - _path (Path): Resolved file path.

    **Methods:**
        - path: Property getter/setter for the active file path.

MultiConfig
~~~~~~~~~~~
.. autoclass:: molselect.python.config.MultiConfig
   :members:
   :undoc-members:
   :show-inheritance:

    Multi-file configuration with plugin support.

    Manages a prioritized list of configuration files:
      - User-specified paths (added via constructor or add())
      - Packaged default resource
      - Entry-point plugins (via importlib.metadata)

    **Methods:**
        - paths -> List[Path]: Full resolution list in precedence order.
        - add(p) -> None: Prepend a new path.
        - remove(p) -> None: Remove a path (raises ValueError if missing).
        - replace(paths) -> None: Replace all user paths at once.
        - remove_default_path() -> None: Drop the packaged default entry.
        - get(index) -> Path: Fetch the path at given priority index.

ConfigManager
~~~~~~~~~~~~~
.. autoclass:: molselect.python.config.ConfigManager
   :members:
   :undoc-members:
   :show-inheritance:

    Aggregates BaseConfig and MultiConfig for molselect.

    Provides easy access to:
      - grammar: BaseConfig
      - macros: MultiConfig
      - keywords: MultiConfig

Usage Example
-------------
.. code-block:: python

    from molselect.python.config import ConfigManager

    cfg = ConfigManager(
        grammar='/path/to/custom.grammar.lark',
        macros=['/custom/macros1.json', '/custom/macros2.json'],
    )

    # Access single-file config
    print(cfg.grammar.path)
    # Add a new macro file at highest precedence
    cfg.macros.add('/new/more_macros.json')
    # Replace all macro files at once
    cfg.macros.replace(['/macros/A.json', '/macros/B.json'])
    # Remove the default packaged macro file
    cfg.macros.remove_default_path()
    # Fetch the next priority path
    first_path = cfg.macros.get(0)

"""
from pathlib import Path
import logging
import importlib.resources
from importlib import metadata
from typing import List, Optional, Union
import molselect.data as data_pkg

# A path-like type accepted by the configuration classes
PathLike = Union[str, Path]
logger = logging.getLogger(__name__)

class BaseConfig:
    """
    Single-file configuration with layered overrides.

    Layers (in order of precedence):
      1. A user-supplied path (via constructor or setter)
      2. A packaged default resource (from importlib.resources)

    Attributes:
        name (str): Identifier used in logging.
        _path (Path): Resolved file path.

    Methods:
        path: Property getter/setter for the active file path.
    """

    def __init__(
        self,
        name: str,
        default_pkg,
        default_file: str,
        user_path: Optional[PathLike] = None,
    ):
        self.name = name
        if user_path:
            # Use provided path
            self._path = Path(user_path)
            logger.debug(f"{name}: using user path {self._path}")
        else:
            # Always use importlib.resources to locate packaged data
            pkg_root = importlib.resources.files(default_pkg)
            self._path = pkg_root / default_file
            logger.debug(f"{name}: using default resource at {self._path}")

    @property
    def path(self) -> Path:
        """
        The active configuration file path.

        Returns:
            Path: Current file path in use.
        """
        return self._path

    @path.setter
    def path(self, p: PathLike) -> None:
        """
        Override the active configuration file.

        Args:
            p (PathLike): New file path to use.
        """
        self._path = Path(p)
        logger.debug(f"{self.name}: path overridden to {self._path}")


class MultiConfig(BaseConfig):
    """
    Multi-file configuration with plugin support.

    Manages a prioritized list of configuration files:
      - User-specified paths (added via constructor or add())
      - Packaged default resource
      - Entry-point plugins (via importlib.metadata)

    Methods:
        paths -> List[Path]: Full resolution list in precedence order.
        add(p) -> None: Prepend a new path.
        remove(p) -> None: Remove a path (raises ValueError if missing).
        replace(paths) -> None: Replace all user paths at once.
        remove_default_path() -> None: Drop the packaged default entry.
        get(index) -> Path: Fetch the path at given priority index.
    """

    def __init__(
        self,
        name: str,
        default_pkg,
        default_file: str,
        user_paths: Optional[List[PathLike]] = None,
        entry_point_group: Optional[str] = None,
    ):
        # Store for later rebuild operations
        self._default_pkg = default_pkg
        self._default_file = default_file
        self._entry_point_group = entry_point_group

        # Initialize the default packaged path
        super().__init__(
            name=name,
            default_pkg=default_pkg,
            default_file=default_file,
            user_path=None,
        )

        # Build the initial resolution list
        self._paths: List[Path] = []
        if user_paths:
            for p in user_paths:
                self._paths.append(Path(p))
                logger.debug(f"{name}: added user path {p}")

        # Always include the packaged default
        self._paths.append(self._path)
        logger.debug(f"{name}: added default path {self._path}")

        # Append any plugin-provided resources
        if entry_point_group:
            for ep in metadata.entry_points(group=entry_point_group):
                plugin_path = Path(ep.load())
                self._paths.append(plugin_path)
                logger.debug(f"{name}: added plugin path {plugin_path} from entry point {ep.name}")

    @property
    def paths(self) -> List[Path]:
        """
        Get the full list of resolved paths (highest precedence first).

        Returns:
            List[Path]: Current resolution order of config files.
        """
        return list(self._paths)

    def add(self, p: PathLike) -> None:
        """
        Prepend a new configuration file to the resolution order.

        Args:
            p (PathLike): File path to add.
        """
        new_path = Path(p)
        self._paths.insert(0, new_path)
        logger.debug(f"{self.name}: prepended path {new_path}")

    def remove(self, p: PathLike) -> None:
        """
        Remove a configuration file from the resolution list.

        Args:
            p (PathLike): File path to remove.

        Raises:
            ValueError: If the path is not found.
        """
        path = Path(p)
        self._paths.remove(path)
        logger.debug(f"{self.name}: removed path {path}")

    def replace(self, user_paths: List[PathLike]) -> None:
        """
        Atomically replace all user-supplied paths.

        Args:
            user_paths (List[PathLike]): New list of user paths.
        """
        # Only use the explicit user paths, drop default and plugins
        self._paths = [Path(p) for p in user_paths]
        logger.debug(f"{self.name}: replaced user paths with {user_paths}")

    def remove_default_path(self) -> None:
        """
        Remove the packaged default resource from the list.
        """
        try:
            self._paths.remove(self._path)
            logger.debug(f"{self.name}: removed default path {self._path}")
        except ValueError:
            logger.debug(f"{self.name}: default path not present, nothing to do")

    def get(self, index: int) -> Path:
        """
        Fetch the configuration path at the specified index.

        Args:
            index (int): 0-based priority index.

        Returns:
            Path: the path at that position.

        Raises:
            IndexError: If index is out of range.
        """
        return self._paths[index]
    
class ConfigManager:
    """
    Aggregates BaseConfig and MultiConfig for molselect.

    Provides easy access to:
      - grammar: BaseConfig
      - macros: MultiConfig
      - keywords: MultiConfig
    """

    def __init__(
        self,
        grammar: Optional[PathLike] = None,
        macros: Optional[List[PathLike]] = None,
        keywords: Optional[List[PathLike]] = None,
    ):
        pkg = data_pkg
        self.grammar = BaseConfig(
            name="grammar",
            default_pkg=pkg,
            default_file="grammar_template.lark",
            user_path=grammar,
        )
        # Always build MultiConfig with default+plugins, then replace if user provided paths
        self.macros = MultiConfig(
            name="macros",
            default_pkg=pkg,
            default_file="macros.json",
            user_paths=None,
            entry_point_group="molselect.macros",
        )
        if macros is not None:
            self.macros.replace(macros)
        self.keywords = MultiConfig(
            name="keywords",
            default_pkg=pkg,
            default_file="keywords.json",
            user_paths=None,
            entry_point_group="molselect.keywords",
        )
        if keywords is not None:
            self.keywords.replace(keywords)

    def __repr__(self):
        return (
            f"<ConfigManager grammar={self.grammar.path!r}, "
            f"macros={self.macros.paths!r}, "
            f"keywords={self.keywords.paths!r}>"
        )

if __name__ == "__main__":
    # Demo: Instantiate ConfigManager and print resolved paths
    cfg = ConfigManager()
    print("Grammar path:", cfg.grammar.path)
    if not cfg.grammar.path.exists():
        raise FileNotFoundError(f"Grammar file not found at {cfg.grammar.path}")

    print("Macros paths:", cfg.macros.paths)
    for p in cfg.macros.paths:
        if not p.exists():
            raise FileNotFoundError(f"Macro file not found at {p}")

    print("Keywords paths:", cfg.keywords.paths)
    for p in cfg.keywords.paths:
        if not p.exists():
            raise FileNotFoundError(f"Keyword file not found at {p}")

