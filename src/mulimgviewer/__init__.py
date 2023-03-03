r"""Provide ``__version__`` for
`importlib.metadata.version() <https://docs.python.org/3/library/importlib.metadata.html#distribution-versions>`_.
"""
from ._version import __version__, __version_tuple__  # type: ignore

__all__ = ["__version__", "__version_tuple__"]
