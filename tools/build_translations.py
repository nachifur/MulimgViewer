"""Build complete translated manuals alongside the Chinese Read the Docs site."""
import argparse
import os
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import tempfile

from babel.messages.pofile import read_po

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
LANGUAGES = run_path(str(ROOT / "src/mulimgviewer/src/languages.py"))["LANGUAGE_INFO"]


def sphinx(builder, output, doctrees, *options):
    subprocess.run(
        [sys.executable, "-m", "sphinx", "-q", "-E", "-W", "-b", builder,
         "-d", str(doctrees), *options, str(DOCS), str(output)],
        cwd=ROOT, check=True,
    )


def check_catalogs(templates):
    """Sphinx accepts absent translations. Fail before publishing a partial manual."""
    failures = []
    for pot in sorted(templates.rglob("*.pot")):
        relative = pot.relative_to(templates).with_suffix(".po")
        with pot.open("rb") as stream:
            messages = [msg.id for msg in read_po(stream) if msg.id]
        for code in LANGUAGES:
            if code == "zh_CN":
                continue
            po = DOCS / "locale" / code / "LC_MESSAGES" / relative
            if not po.is_file():
                failures.append(str(po))
                continue
            with po.open("rb") as stream:
                catalog = read_po(stream)
            for key in messages:
                # Release numbers and raw HTML anchors carry no language.
                if key.replace(".", "").isdigit() or key.startswith('<a name="'):
                    continue
                entry = catalog.get(key)
                if entry is None or not entry.string or entry.fuzzy:
                    failures.append(f"{code}/{relative}: {key[:100]}")
    if failures:
        raise ValueError("Missing or unreviewed catalog entries:\n" + "\n".join(failures))


def build(output, check_only=False):
    with tempfile.TemporaryDirectory(prefix="mulimgviewer-manual-") as temp:
        work = Path(temp)
        sphinx("gettext", work / "pot", work / "gettext-trees")
        check_catalogs(work / "pot")
        if check_only:
            return
        if not os.environ.get("READTHEDOCS_OUTPUT"):
            sphinx("html", output, work / "zh_CN", "-D", "language=zh_CN")
        elif not (output / "index.html").is_file():
            raise ValueError(f"Read the Docs did not produce its primary HTML output: {output}")
        pages = [p.relative_to(DOCS).with_suffix(".html")
                 for section in ("dev", "resources", "misc") for p in (DOCS / section).glob("*.md")]
        for code in LANGUAGES:
            if code == "zh_CN":
                continue
            destination = output / "i18n" / code
            sphinx("html", destination, work / code, "-D", f"language={code}")
            for page in [Path("index.html"), Path("languages.html"), *pages]:
                if not (destination / page).is_file():
                    raise ValueError(f"Missing page in {code}: {page}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Local output directory for the multilingual site")
    parser.add_argument("--check-only", action="store_true", help="Check every catalog against the current sources")
    args = parser.parse_args()
    if not args.output and not args.check_only:
        # Only the Chinese project publishes the multilingual bundle.
        if os.environ.get("READTHEDOCS_LANGUAGE", "").lower().replace("_", "-") != "zh-cn":
            if "READTHEDOCS_OUTPUT" in os.environ:
                sys.exit(0)
            parser.error("For a local build, specify --output or --check-only")
        args.output = Path(os.environ["READTHEDOCS_OUTPUT"]) / "html"
    os.environ["MULIMGVIEWER_BUNDLE"] = "1"
    build(args.output, args.check_only)
