"""Prepare release-facing files and verify a release candidate before tagging."""
import argparse
import os
import re
import subprocess
import sys
from email.parser import BytesParser
from pathlib import Path
from runpy import run_path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def verify_wheel(wheel, version):
    with ZipFile(wheel) as archive:
        metadata = BytesParser().parsebytes(
            archive.read(f"mulimgviewer-{version}.dist-info/METADATA"))
        package = ROOT / "src/mulimgviewer"
        # Confirm the wheel carries the same offline catalogs tested from source.
        for source in (package / "src/locales").glob("*.json"):
            name = "mulimgviewer/" + source.relative_to(package).as_posix()
            if archive.read(name).splitlines() != source.read_bytes().splitlines():
                raise ValueError(f"Wheel translation differs: {name}")
        version_file = "src/mulimgviewer/release_version.py"
        if (metadata["Version"] != version or
                archive.read("mulimgviewer/release_version.py").splitlines() !=
                (ROOT / version_file).read_bytes().splitlines()):
            raise ValueError(f"Wheel metadata or packaged application version differs: {wheel}")


def release_version():
    version = run_path(str(ROOT / "src/mulimgviewer/release_version.py"))["__version__"]
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version):
        raise ValueError("Use a release number such as 4.0.0")
    return version


def check_release(prepare=False, full=False, tag=None):
    version = release_version()
    if tag and tag != f"v{version}":
        raise ValueError(f"Tag {tag} does not match v{version}")

    languages = run_path(str(ROOT / "src/mulimgviewer/src/languages.py"))["LANGUAGE_INFO"]
    links = []
    for name, target in languages.values():
        if not target.startswith("https://") and not (ROOT / "docs" / target).is_file():
            raise ValueError(f"Missing manual: {target}")
        links.append(f"[{name}]({target})")
    directory = ROOT / "docs/languages.md"
    expected = "# Documentation · 语言\n\n" + "\n\n".join(links) + "\n"
    if not directory.exists() or directory.read_text(encoding="utf-8") != expected:
        if not prepare:
            raise ValueError("Documentation language links are stale. Run tools/release.py --prepare")
        directory.write_text(expected, encoding="utf-8")

    template_path = ROOT / "README-v4.md"
    template = template_path.read_text(encoding="utf-8")
    begin, end = "<!-- manual-links -->", "<!-- /manual-links -->"
    if template.count(begin) != 1 or template.count(end) != 1 or template.index(begin) >= template.index(end):
        raise ValueError("README-v4.md needs one marked block for manual links")
    before, block = template.split(begin)
    _, after = block.split(end)
    direct_links = [
        f"[{name}]({target if target.startswith('https://') else 'docs/' + target})"
        for name, target in languages.values()
    ]
    updated = before + begin + "\n\n" + " · ".join(direct_links) + "\n\n" + end + after
    if template != updated:
        if not prepare:
            raise ValueError("README language links are stale. Run tools/release.py --prepare")
        template_path.write_text(updated, encoding="utf-8")
        template = updated
    targets = re.findall(r"\]\(([^ )]+)\)", template)
    targets += re.findall(r'(?:src|href)="([^"]+)"', template)
    for target in targets:
        if "://" in target:
            if "mulimgviewer.readthedocs.io/" in target and target not in {url for _, url in languages.values()}:
                raise ValueError(f"Link to the matching document in docs/ instead: {target}")
            continue
        path, _, anchor = target.partition("#")
        document = ROOT / path
        if not document.exists() or (anchor and not document.is_file()):
            raise ValueError(f"Missing README target: {target}")
        if anchor and f'<a name="{anchor}"></a>' not in document.read_text(encoding="utf-8"):
            raise ValueError(f"Missing README section: {target}")
    if int(version.split(".")[0]) >= 4:
        readme = ROOT / "README.md"
        expected = template.replace("{{version}}", version)
        for _, url in languages.values():
            expected = expected.replace(url, url.replace("/latest/", f"/v{version}/"))
        if readme.read_text(encoding="utf-8") != expected:
            if not prepare:
                raise ValueError("README.md is stale. Run python tools/release.py --prepare")
            readme.write_bytes(expected.encode("utf-8"))
            print("Updated README.md. Include it in the release commit.")

    changes = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    section = re.search(rf"^## {re.escape(version)}[ \t]*\n(.*?)(?=^## |\Z)",
                        changes, re.M | re.S)
    if prepare and not section:
        pending = re.search(r"^## 未发布[ \t]*\n(.*?)(?=^## |\Z)", changes, re.M | re.S)
        if pending and pending[1].strip():
            changes = changes[:pending.start(1)] + f"\n## {version}\n" + changes[pending.start(1):]
            (ROOT / "CHANGELOG.md").write_bytes(changes.encode("utf-8"))
            section = re.search(rf"^## {re.escape(version)}\n(.*?)(?=^## |\Z)", changes, re.M | re.S)
    if not section or not section[1].strip():
        raise ValueError("Add release notes under '## 未发布' in CHANGELOG.md and run --prepare")
    if tag:
        notes = ROOT / "build/CHANGELOG.md"
        notes.parent.mkdir(exist_ok=True)
        notes.write_bytes(section[1].strip().encode("utf-8") + b"\n")
    if full:
        if subprocess.check_output(["git", "tag", "--list", f"v{version}"], cwd=ROOT).strip():
            raise ValueError(f"v{version} already exists locally. Choose a new release version.")
        subprocess.run([os.environ.get("SPHINX_PYTHON", sys.executable),
                        "tools/build_translations.py", "--check-only"], cwd=ROOT, check=True)
        for language in languages:
            subprocess.run([os.environ.get("SPHINX_PYTHON", sys.executable), "-m",
                            "sphinx", "-E", "-W", "-b", "html", "-D",
                            f"language={language}", "docs", f"docs/_build/release-{language}"],
                           cwd=ROOT, check=True)
        subprocess.run([sys.executable, "auto_test_scripts/run_tests.py", "--strict-skips"],
                       cwd=ROOT, check=True)
        dist = ROOT / "build" / f"release-{version}" / "dist"
        subprocess.run([sys.executable, "-m", "build", "--outdir", str(dist)],
                       cwd=ROOT, check=True, env={**os.environ, "PYTHONUTF8": "1"})
        wheels = list(dist.glob(f"mulimgviewer-{version}-*.whl"))
        if len(wheels) != 1 or not (dist / f"mulimgviewer-{version}.tar.gz").is_file():
            raise ValueError(f"Expected one v{version} wheel and its source archive under {dist}")
        verify_wheel(wheels[0], version)
        print(f"Local checks passed for v{version}. Commit the reviewed files and verify CI before tagging.")
    else:
        print(f"Release metadata verified: {version}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true", help="Update the root README for v4 and later")
    parser.add_argument("--full", action="store_true", help="Check local tag availability, docs, tests and distributions")
    parser.add_argument("--tag", help="Verify a release tag and write GitHub release notes")
    parser.add_argument("--print-tag", action="store_true", help="Print the tag for the configured version")
    args = parser.parse_args()
    try:
        if args.print_tag:
            print(f"v{release_version()}")
        else:
            check_release(args.prepare, args.full, args.tag)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
