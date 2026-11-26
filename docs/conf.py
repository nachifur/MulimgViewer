r"""Configure the Sphinx documentation builder.

https://www.sphinx-doc.org/en/master/usage/configuration.html
"""
try:
    from mulimgviewer import __version__ as version  # type: ignore

except ImportError:
    version = "3.9.7"

__all__ = ["version", "author", "copyright", "project", "html_favicon"]

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.

# -- Project information -----------------------------------------------------
project = "MulimgViewer"
author = "Jiawei Liu"
copyright = "2026, Jiawei Liu"
release = version

language = "zh_CN"
locale_dirs = ["locale"]
gettext_compact = False

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.githubpages",
    "myst_parser",
    "sphinxcontrib.eval",
]

myst_heading_anchors = 3
myst_title_to_header = True

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]


# -- Options for HTML output -------------------------------------------------

html_theme = "furo"
html_title = project
html_logo = "../src/mulimgviewer/mulimgviewer.svg"
html_favicon = "../src/mulimgviewer/mulimgviewer.png"
html_static_path = ["_static"]
html_css_files = ["manual.css"]
sidebar_colors = {
    "color-sidebar-background": "#101a35",
    "color-sidebar-background-border": "#29395b",
    "color-sidebar-brand-text": "#f0f5ff",
    "color-sidebar-caption-text": "#8eaaff",
    "color-sidebar-link-text": "#d2def5",
    "color-sidebar-link-text--top-level": "#e4edff",
    "color-sidebar-item-background--hover": "#243659",
    "color-sidebar-item-background--current": "#253e69",
    "color-sidebar-search-background": "#182747",
    "color-sidebar-search-background--focus": "#23385d",
    "color-sidebar-search-border": "#485e84",
    "color-sidebar-search-foreground": "#f1f6ff",
    "color-sidebar-search-icon": "#9fcbff",
    "color-sidebar-search-text": "#e1edff",
}
html_theme_options = {
    "light_css_variables": {
        **sidebar_colors,
        "color-brand-primary": "#344ed0",
        "color-brand-content": "#254ac1",
        "color-background-primary": "#f7f9ff",
        "color-foreground-primary": "#172542",
        "color-background-border": "#cdd7ea",
    },
    "dark_css_variables": {
        **sidebar_colors,
        "color-brand-primary": "#72d6ff",
        "color-brand-content": "#9acfff",
        "color-background-primary": "#0c1325",
        "color-foreground-primary": "#e4edff",
        "color-background-border": "#344464",
    },
}
