#!/usr/bin/env python3
"""Build grouped PDFs from Markdown docs in a VisualCron docs checkout."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

DEFAULT_REPO_URL = "https://github.com/smatechnologies/visualcron-docs.git"
ENGINE_PRIORITY = [
    "typst",
    "weasyprint",
    "wkhtmltopdf",
    "xelatex",
    "lualatex",
    "pdflatex",
]


@dataclass(frozen=True)
class Group:
    folder: Path
    files: List[Path]


def run(cmd: Sequence[str], *, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(cmd),
        cwd=str(cwd) if cwd else None,
        check=False,
        capture_output=True,
        text=True,
    )


def ensure_source_repo(
    source_path: Optional[Path],
    checkout_dir: Path,
    source_repo_url: str,
    branch: str,
    update: bool,
) -> Path:
    if source_path:
        resolved = source_path.resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"--source-path does not exist: {resolved}")
        return resolved

    checkout_dir = checkout_dir.resolve()
    if not checkout_dir.exists():
        checkout_dir.parent.mkdir(parents=True, exist_ok=True)
        clone_result = run(["git", "clone", "--branch", branch, "--single-branch", source_repo_url, str(checkout_dir)])
        if clone_result.returncode != 0:
            raise RuntimeError(
                "Failed to clone source repository. "
                "If you are running offline, supply --source-path to an existing checkout.\n"
                f"Command: git clone --branch {branch} --single-branch {source_repo_url} {checkout_dir}\n"
                f"stderr: {clone_result.stderr.strip()}"
            )
        return checkout_dir

    git_dir = checkout_dir / ".git"
    if update and git_dir.exists():
        fetch_result = run(["git", "fetch", "origin", branch], cwd=checkout_dir)
        if fetch_result.returncode == 0:
            run(["git", "checkout", branch], cwd=checkout_dir)
            run(["git", "reset", "--hard", f"origin/{branch}"], cwd=checkout_dir)
    return checkout_dir


def natural_sort_key(name: str) -> List[object]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def sort_markdown_files(paths: Iterable[Path]) -> List[Path]:
    def key(path: Path) -> tuple[int, List[object]]:
        lowered = path.name.lower()
        if lowered == "index.md":
            priority = 0
        elif lowered == "readme.md":
            priority = 1
        else:
            priority = 2
        return (priority, natural_sort_key(lowered))

    return sorted(paths, key=key)


def discover_groups(docs_dir: Path) -> List[Group]:
    groups: List[Group] = []
    for root, dirs, files in os.walk(docs_dir):
        dirs.sort(key=natural_sort_key)
        root_path = Path(root)
        markdown_files = [root_path / file for file in files if file.lower().endswith(".md")]
        if not markdown_files:
            continue
        groups.append(Group(folder=root_path, files=sort_markdown_files(markdown_files)))

    groups.sort(key=lambda group: natural_sort_key(str(group.folder.relative_to(docs_dir))))
    return groups


def format_title(path: Path) -> str:
    return path.stem.replace("-", " ").replace("_", " ").strip().title()


def build_combined_markdown(group: Group, docs_dir: Path) -> str:
    relative_folder = group.folder.relative_to(docs_dir)
    group_name = "docs" if str(relative_folder) == "." else str(relative_folder)
    lines: List[str] = [f"# {group_name}\n"]

    for source_file in group.files:
        lines.append(f"\n## {format_title(source_file)}\n")
        lines.append(source_file.read_text(encoding="utf-8"))
        lines.append("\n\n\\newpage\n")

    return "".join(lines)


def resolve_output_pdf(output_dir: Path, docs_dir: Path, group: Group) -> Path:
    relative_folder = group.folder.relative_to(docs_dir)
    if str(relative_folder) == ".":
        return output_dir / "docs.pdf"
    return output_dir / relative_folder.parent / f"{relative_folder.name}.pdf"


def available_engines() -> List[str]:
    return [engine for engine in ENGINE_PRIORITY if shutil.which(engine)]


def render_pdf_with_pandoc(markdown_path: Path, output_pdf: Path) -> str:
    if not shutil.which("pandoc"):
        raise RuntimeError(
            "pandoc is not available. Install pandoc, or run with --source-path on a machine where pandoc is installed."
        )

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    engines = available_engines()
    attempts: List[tuple[str, subprocess.CompletedProcess]] = []

    for engine in engines:
        cmd = ["pandoc", "--from", "gfm", "--pdf-engine", engine, str(markdown_path), "-o", str(output_pdf)]
        result = run(cmd)
        attempts.append((engine, result))
        if result.returncode == 0:
            return f"pandoc:{engine}"

    fallback_cmd = ["pandoc", "--from", "gfm", str(markdown_path), "-o", str(output_pdf)]
    fallback_result = run(fallback_cmd)
    attempts.append(("pandoc-default", fallback_result))
    if fallback_result.returncode == 0:
        return "pandoc:default"

    details = "\n\n".join(
        f"Attempt {name}:\n{attempt.stderr.strip() or '(no stderr)'}" for name, attempt in attempts
    )
    raise RuntimeError(
        "Unable to render PDF with detected local backends.\n"
        "Install one of: typst, weasyprint, wkhtmltopdf, or a LaTeX engine (xelatex/lualatex/pdflatex).\n"
        f"Details:\n{details}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-path", type=Path, help="Path to an existing visualcron-docs checkout.")
    parser.add_argument(
        "--checkout-dir",
        type=Path,
        default=Path(".cache") / "visualcron-docs",
        help="Where to clone visualcron-docs if --source-path is not provided.",
    )
    parser.add_argument(
        "--source-repo-url",
        default=DEFAULT_REPO_URL,
        help="Git URL used when cloning source documentation repository.",
    )
    parser.add_argument("--branch", default="main", help="Source repository branch when cloning/updating.")
    parser.add_argument("--update", action="store_true", help="Update existing checkout_dir via git fetch/reset.")
    parser.add_argument(
        "--docs-subdir",
        default="docs",
        help="Docs path inside source repository checkout.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output") / "pdfs",
        help="Directory where generated PDFs are written.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("output") / "pdfs" / "manifest.json",
        help="JSON manifest with generated groups and files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        source_root = ensure_source_repo(
            source_path=args.source_path,
            checkout_dir=args.checkout_dir,
            source_repo_url=args.source_repo_url,
            branch=args.branch,
            update=args.update,
        )
    except Exception as exc:  # pragma: no cover - CLI entry handling
        print(str(exc), file=sys.stderr)
        return 2

    docs_dir = source_root / args.docs_subdir
    if not docs_dir.is_dir():
        print(f"Docs directory not found: {docs_dir}", file=sys.stderr)
        return 2

    groups = discover_groups(docs_dir)
    if not groups:
        print(f"No markdown files found under {docs_dir}", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []

    with tempfile.TemporaryDirectory(prefix="build-doc-pdfs-") as temp_dir:
        temp_root = Path(temp_dir)
        for index, group in enumerate(groups, start=1):
            merged_path = temp_root / f"group-{index:04d}.md"
            merged_path.write_text(build_combined_markdown(group, docs_dir), encoding="utf-8")

            output_pdf = resolve_output_pdf(args.output_dir, docs_dir, group)
            try:
                backend = render_pdf_with_pandoc(merged_path, output_pdf)
            except Exception as exc:
                print(f"Failed generating {output_pdf}: {exc}", file=sys.stderr)
                return 1

            results.append(
                {
                    "group": str(group.folder.relative_to(docs_dir)),
                    "output_pdf": str(output_pdf),
                    "backend": backend,
                    "files": [str(path.relative_to(docs_dir)) for path in group.files],
                }
            )
            print(f"Generated {output_pdf}")

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote manifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
