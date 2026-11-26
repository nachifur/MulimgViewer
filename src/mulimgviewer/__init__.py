r"""Provide ``__version__`` for
`importlib.metadata.version() <https://docs.python.org/3/library/importlib.metadata.html#distribution-versions>`_.
"""
import os

from .release_version import __version__

__version_tuple__ = tuple(map(int, __version__.split(".")))

__all__ = ["__version__", "__version_tuple__", "html_favicon"]

html_favicon = os.path.join(os.path.dirname(__file__), "mulimgviewer.png")
