# molselect/python/errors.py

"""
Exception hierarchy for MolSelect.
"""

from typing import Optional, Any


class MolSelectError(Exception):
    """Base exception for all errors in MolSelect."""
    pass


class MolSelectParseError(MolSelectError):
    """
    Raised when parsing a selection string fails.

    Attributes:
        expression: the input string being parsed
        position: character index where the error was detected (if known)
    """
    def __init__(
        self,
        message: str,
        expression: Optional[str] = None,
        position: Optional[int] = None,
    ):
        self.expression = expression
        self.position = position
        # Build a standardized message
        parts = [message]
        if expression is not None:
            parts.append(f"in `{expression}`")
        if position is not None:
            parts.append(f"at pos {position}")
        super().__init__(" — ".join(parts))


class MolSelectMacroError(MolSelectParseError):
    """
    Raised when expansion of a user-defined or built-in macro fails.

    Attributes:
        macro_name: name of the macro that failed to expand
    """
    def __init__(self, macro_name: str, message: str):
        self.macro_name = macro_name
        super().__init__(f"Macro `{macro_name}` expansion error: {message}", expression=macro_name)


class MolSelectBuilderError(MolSelectError):
    """
    Raised when AST construction via ASTBuilder fails.

    Attributes:
        tree_or_token: the lark.Tree or Token that triggered the failure
    """
    def __init__(self, message: str, tree_or_token: Any):
        self.tree_or_token = tree_or_token
        super().__init__(f"ASTBuilder error on {type(tree_or_token).__name__}: {message}")


class MolSelectNodeError(MolSelectError):
    """
    Raised when a Node’s `evaluate` or `symbolic` method fails.

    Attributes:
        node: the AST Node instance where the error occurred
    """
    def __init__(self, message: str, node: Any):
        self.node = node
        super().__init__(f"{type(node).__name__} error: {message}")


class MolSelectEvaluationError(MolSelectError):
    """
    Raised when evaluating the AST against a backend Structure fails.

    Attributes:
        node: the AST Node being evaluated (if applicable)
        backend: the Structure instance or backend class in use
    """
    def __init__(
        self,
        message: str,
        node: Optional[Any] = None,
        backend: Optional[Any] = None,
    ):
        self.node = node
        self.backend = backend
        ctx = []
        if node is not None:
            ctx.append(f"node={type(node).__name__}")
        if backend is not None:
            ctx.append(f"backend={backend.__class__.__name__}")
        ctx_str = " ".join(ctx)
        super().__init__(f"Evaluation error{' (' + ctx_str + ')' if ctx_str else ''}: {message}")


class MolSelectConfigError(MolSelectError):
    """Raised when configuration loading or manipulation fails."""
    pass


class MolSelectConfigFileNotFound(MolSelectConfigError):
    """
    Raised when a required configuration file is missing.

    Attributes:
        path: the filesystem path that was not found
    """
    def __init__(self, path: str):
        self.path = path
        super().__init__(f"Configuration file not found: {path}")


class MolSelectBackendError(MolSelectError):
    """
    Raised when instantiating or using a user-defined backend fails.

    Attributes:
        backend_cls: the backend class that could not be used
    """
    def __init__(self, message: str, backend_cls: Any):
        self.backend_cls = backend_cls
        super().__init__(f"Backend `{backend_cls.__name__}` error: {message}")
