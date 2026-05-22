#!/usr/bin/env python3
"""
build_doc_pdfs.py - Generate grouped PDFs from a Markdown documentation tree.

Groups .md files by their immediate parent directory and converts each group
into a single PDF. Designed to work offline with locally installed tools.

Usage:
    python scripts/build_doc_pdfs.py --source-path <path_to_docs>
    python scripts/build_doc_pdfs.py --source-path <path_to_docs> --output-path output-pdf/
    python scripts/build_doc_pdfs.py --source-path <path_to_docs> --config scripts/config.json
    python scripts/build_doc_pdfs.py --source-path <path_to_docs> --dry-run

PDF backend priority (first available wins):
    1. pandoc + wkhtmltopdf
    2. pandoc + xelatex
    3. pandoc + pdflatex
    4. pandoc (default engine)
    5. headless Microsoft Edge  → HTML → PDF
    6. headless Google Chrome/Chromium → HTML → PDF
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict = {
    "docs_root": "docs",
    "output_root": "output-pdf",
    "grouping": "per-folder-direct-files",
    "merge_single_file_folders": True,
    "file_order": ["index.md", "readme.md"],
    "ignore_dirs": [".git", ".github", "node_modules", "__pycache__"],
    "ignore_files": [],
    "pdf_backend_preference": [
        "pandoc-wkhtmltopdf",
        "pandoc-xelatex",
        "pandoc-pdflatex",
        "pandoc",
        "html-edge",
        "html-chrome",
    ],
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_config(config_path: Optional[str]) -> dict:
    """Load configuration from a JSON file, merged on top of defaults."""
    config = DEFAULT_CONFIG.copy()
    if config_path and os.path.isfile(config_path):
        with open(config_path, "r", encoding="utf-8") as fh:
            user_config = json.load(fh)
        config.update(user_config)
    return config


# ---------------------------------------------------------------------------
# Tool / backend detection
# ---------------------------------------------------------------------------

def _find_tool(names: List[str]) -> Optional[str]:
    """Return the path to the first tool found on PATH, or None."""
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


def detect_pdf_backend(
    preferences: List[str],
) -> Tuple[Optional[str], str]:
    """
    Probe the local system for a working PDF backend.

    Returns a tuple of (backend_type, engine_arg) where:
      - backend_type is one of: "pandoc-engine", "html-browser", or None
      - engine_arg is the --pdf-engine argument for pandoc, the path for a
        browser, or an empty string when the default pandoc engine is used.
    """
    pandoc = shutil.which("pandoc")

    for pref in preferences:
        if pref == "pandoc-wkhtmltopdf" and pandoc:
            if shutil.which("wkhtmltopdf"):
                return ("pandoc-engine", "--pdf-engine=wkhtmltopdf")

        elif pref == "pandoc-xelatex" and pandoc:
            if shutil.which("xelatex"):
                return ("pandoc-engine", "--pdf-engine=xelatex")

        elif pref == "pandoc-pdflatex" and pandoc:
            if shutil.which("pdflatex"):
                return ("pandoc-engine", "--pdf-engine=pdflatex")

        elif pref == "pandoc" and pandoc:
            return ("pandoc-engine", "")

        elif pref == "html-edge":
            edge = _find_tool(
                ["msedge", "microsoft-edge", "microsoft-edge-stable"]
            )
            if edge:
                return ("html-browser", edge)

        elif pref == "html-chrome":
            chrome = _find_tool(
                [
                    "google-chrome",
                    "google-chrome-stable",
                    "chromium",
                    "chromium-browser",
                    "chrome",
                ]
            )
            if chrome:
                return ("html-browser", chrome)

    return (None, "")


# ---------------------------------------------------------------------------
# File discovery and grouping
# ---------------------------------------------------------------------------

def collect_md_groups(
    source_path: Path,
    ignore_dirs: List[str],
    ignore_files: List[str],
) -> Dict[str, List[Path]]:
    """
    Walk *source_path* and group .md files by their immediate parent folder.

    Returns a dict mapping relative folder key -> list of absolute Paths.
    The root folder is represented by an empty string key "".

    Directories whose names appear in *ignore_dirs* are skipped entirely.
    Directories whose names begin with "." (hidden directories) are also
    always skipped, regardless of the *ignore_dirs* list.
    """
    groups: Dict[str, List[Path]] = defaultdict(list)
    ignore_set = set(ignore_dirs)

    for root, dirs, files in os.walk(source_path):
        root_path = Path(root)

        # Prune ignored and hidden directories in-place so os.walk skips them
        dirs[:] = [
            d for d in dirs
            if d not in ignore_set and not d.startswith(".")
        ]

        rel_folder = root_path.relative_to(source_path)
        folder_key = "" if str(rel_folder) == "." else str(rel_folder)

        md_files = [
            root_path / fname
            for fname in files
            if fname.lower().endswith(".md") and fname not in ignore_files
        ]

        if md_files:
            groups[folder_key].extend(md_files)

    return dict(groups)


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------

def sort_files(files: List[Path], priority_names: List[str]) -> List[Path]:
    """
    Sort a list of Markdown file paths deterministically:
      1. Priority names (e.g. index.md, readme.md) in declared order.
      2. Files with a leading numeric prefix, sorted numerically.
      3. All remaining files, sorted alphabetically (case-insensitive).
    """
    priority_lower = [n.lower() for n in priority_names]

    def sort_key(p: Path) -> Tuple:
        name_lower = p.name.lower()

        # Check priority list first
        try:
            idx = priority_lower.index(name_lower)
            return (0, idx, 0, name_lower)
        except ValueError:
            pass

        # Natural sort on leading digits
        match = re.match(r"^(\d+)", p.name)
        if match:
            return (1, 0, int(match.group(1)), name_lower)

        return (2, 0, 0, name_lower)

    return sorted(files, key=sort_key)


# ---------------------------------------------------------------------------
# Naming helpers
# ---------------------------------------------------------------------------

def title_from_path(rel_path: str) -> str:
    """
    Convert a relative folder path to a human-readable title.

    "client-user-interface/toolbar" → "Client User Interface > Toolbar"
    """
    if not rel_path:
        return "Documentation"
    parts = Path(rel_path).parts
    return " > ".join(
        part.replace("-", " ").replace("_", " ").title() for part in parts
    )


def section_title_from_file(md_file: Path) -> str:
    """Convert a filename stem to a human-readable section heading."""
    return md_file.stem.replace("-", " ").replace("_", " ").title()


def output_name_from_group(group_key: str) -> str:
    """
    Convert a group key to a safe, flat output filename (without extension).

    "client-user-interface/toolbar" → "client-user-interface--toolbar"
    """
    if not group_key:
        return "documentation"
    return (
        group_key
        .replace("\\", "/")
        .replace("/", "--")
        .replace(" ", "-")
    )


# ---------------------------------------------------------------------------
# Content processing
# ---------------------------------------------------------------------------

def rewrite_image_paths(content: str, md_file_dir: Path) -> str:
    """
    Rewrite relative Markdown image references to absolute POSIX paths so
    that pandoc can locate them after the files are merged into a temp file.
    """
    def _replace(match: re.Match) -> str:
        alt = match.group(1)
        path = match.group(2)

        # Leave absolute paths and URLs untouched
        if path.startswith(("http://", "https://", "/", "data:")):
            return match.group(0)

        abs_path = (md_file_dir / path).resolve()
        if abs_path.exists():
            return f"![{alt}]({abs_path.as_posix()})"

        # Image not found — keep original so caller can warn
        return match.group(0)

    return re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", _replace, content)


def merge_markdown_files(files: List[Path], group_title: str) -> str:
    """
    Concatenate multiple Markdown files into a single string.

    Each file is preceded by a section heading (H2) and separated from the
    next by a horizontal rule.  The overall document begins with an H1 title.
    """
    parts: List[str] = [f"# {group_title}\n"]
    missing_images: List[str] = []

    for i, md_file in enumerate(files):
        section_title = section_title_from_file(md_file)
        try:
            with open(md_file, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read().strip()
        except OSError as exc:
            content = f"*Error reading file `{md_file.name}`: {exc}*"

        content = rewrite_image_paths(content, md_file.parent)

        # Check for unresolved relative image refs after rewriting
        for m in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", content):
            img = m.group(1)
            if not img.startswith(("http://", "https://", "/", "data:")):
                missing_images.append(f"{md_file.name}: {img}")

        # Prepend section heading if file doesn't already open with H1/H2
        if not re.match(r"^#{1,2} ", content):
            parts.append(f"\n## {section_title}\n")

        parts.append(f"\n{content}\n")

        if i < len(files) - 1:
            parts.append("\n---\n")

    if missing_images:
        warnings = "\n".join(f"  - {w}" for w in missing_images)
        print(f"  ⚠  Image(s) not resolved (will render as broken):\n{warnings}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# PDF conversion
# ---------------------------------------------------------------------------

def run_pandoc(
    input_file: str,
    output_file: str,
    engine_arg: str,
) -> Tuple[bool, str]:
    """Invoke pandoc to convert *input_file* (Markdown) to *output_file* (PDF)."""
    cmd = [
        "pandoc",
        input_file,
        "-o", output_file,
        "--from", "gfm",
        "--standalone",
    ]
    if engine_arg:
        cmd.append(engine_arg)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return (True, "")
        return (False, (result.stderr or result.stdout).strip())
    except subprocess.TimeoutExpired:
        return (False, "pandoc timed out after 120 s")
    except FileNotFoundError:
        return (False, "pandoc executable not found on PATH")
    except (OSError, subprocess.SubprocessError) as exc:
        return (False, str(exc))


def _markdown_to_html(content: str, title: str) -> str:
    """
    Minimal Markdown → HTML conversion used only for the browser-print fallback.
    Handles headings, horizontal rules, and wraps other lines in <p> tags.
    """
    lines = content.splitlines()
    body_parts: List[str] = []

    for line in lines:
        if line.startswith("#### "):
            body_parts.append(f"<h4>{line[5:]}</h4>")
        elif line.startswith("### "):
            body_parts.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            body_parts.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            body_parts.append(f"<h1>{line[2:]}</h1>")
        elif line.strip() == "---":
            body_parts.append("<hr>")
        elif line.strip():
            body_parts.append(f"<p>{line}</p>")

    body = "\n".join(body_parts)
    return (
        f"<!DOCTYPE html><html><head>"
        f"<meta charset='utf-8'><title>{title}</title>"
        f"<style>body{{font-family:sans-serif;max-width:900px;margin:2em auto}}"
        f"h1,h2,h3{{page-break-after:avoid}}hr{{page-break-after:always}}</style>"
        f"</head><body>{body}</body></html>"
    )


def run_html_browser(
    input_html: str,
    output_pdf: str,
    browser_path: str,
) -> Tuple[bool, str]:
    """Use a headless browser to print an HTML file to PDF."""
    abs_html = os.path.abspath(input_html)
    cmd = [
        browser_path,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        f"--print-to-pdf={os.path.abspath(output_pdf)}",
        f"file://{abs_html}",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0 and os.path.isfile(output_pdf):
            return (True, "")
        return (False, (result.stderr or result.stdout or "Browser produced no output").strip())
    except subprocess.TimeoutExpired:
        return (False, "browser timed out after 60 s")
    except (OSError, subprocess.SubprocessError) as exc:
        return (False, str(exc))


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------

def _build_report_entry(
    group_key: str,
    files: List[Path],
    output_pdf: str,
    success: bool,
    error: str,
    backend: str,
) -> dict:
    return {
        "group": group_key or "(root)",
        "title": title_from_path(group_key),
        "files": [str(f) for f in files],
        "output_pdf": output_pdf,
        "success": success,
        "error": error,
        "backend": backend,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:  # returns exit code
    parser = argparse.ArgumentParser(
        description=(
            "Generate grouped PDFs from a Markdown documentation tree. "
            "Each immediate sub-folder in the source path becomes one PDF."
        )
    )
    parser.add_argument(
        "--source-path",
        required=True,
        metavar="PATH",
        help="Root directory that contains the Markdown documentation files.",
    )
    parser.add_argument(
        "--output-path",
        default=None,
        metavar="PATH",
        help="Directory where PDFs will be written (default: output-pdf/).",
    )
    parser.add_argument(
        "--config",
        default=None,
        metavar="FILE",
        help="Path to a JSON config file (default: scripts/config.json if present).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and list groups without generating PDFs.",
    )
    args = parser.parse_args(argv)

    # --- Config ---------------------------------------------------------------
    config_path = args.config
    if not config_path:
        default_cfg = Path(__file__).parent / "config.json"
        if default_cfg.exists():
            config_path = str(default_cfg)
    config = load_config(config_path)

    # --- Resolve paths --------------------------------------------------------
    source_path = Path(args.source_path).resolve()
    if not source_path.is_dir():
        print(
            f"ERROR: source path is not an accessible directory: {source_path}",
            file=sys.stderr,
        )
        return 1

    output_root = (
        Path(args.output_path).resolve()
        if args.output_path
        else Path(config["output_root"]).resolve()
    )
    output_root.mkdir(parents=True, exist_ok=True)

    print(f"Source : {source_path}")
    print(f"Output : {output_root}")

    # --- Backend detection ----------------------------------------------------
    backend_type, backend_arg = detect_pdf_backend(config["pdf_backend_preference"])

    if not args.dry_run:
        if backend_type is None:
            print(
                "\nWARNING: No PDF conversion tool was found on this system.\n"
                "  Install one of the following and re-run:\n"
                "    • pandoc          https://pandoc.org/installing.html\n"
                "    • wkhtmltopdf     https://wkhtmltopdf.org/downloads.html\n"
                "    • xelatex / pdflatex (part of a TeX distribution)\n"
                "    • Google Chrome or Microsoft Edge (headless fallback)\n"
                "\n  Switching to --dry-run mode.",
                file=sys.stderr,
            )
            args.dry_run = True
        else:
            label = backend_arg or "(pandoc default engine)"
            print(f"Backend: {backend_type}  {label}")

    # --- Discover groups ------------------------------------------------------
    groups = collect_md_groups(
        source_path,
        config["ignore_dirs"],
        config["ignore_files"],
    )

    if not groups:
        print(
            f"\nNo Markdown files found under: {source_path}",
            file=sys.stderr,
        )
        return 0

    sorted_keys = sorted(groups.keys())
    print(f"\nFound {len(groups)} folder group(s) with Markdown files:")
    for gk in sorted_keys:
        print(f"  [{gk or '(root)'}]  —  {len(groups[gk])} file(s)")

    if args.dry_run:
        print("\nDry-run mode: no PDFs generated.")
        return 0

    # --- Generate PDFs --------------------------------------------------------
    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source_path),
        "output_path": str(output_root),
        "backend": f"{backend_type} {backend_arg}".strip(),
        "groups": [],
        "summary": {"total": 0, "success": 0, "failed": 0},
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        for group_key in sorted_keys:
            files = sort_files(groups[group_key], config["file_order"])
            group_title = title_from_path(group_key)
            out_stem = output_name_from_group(group_key)
            output_pdf = str(output_root / f"{out_stem}.pdf")

            print(f"\nProcessing [{group_key or '(root)'}] → {out_stem}.pdf")
            for fpath in files:
                print(f"  + {fpath.name}")

            merged = merge_markdown_files(files, group_title)

            if backend_type == "pandoc-engine":
                tmp_md = os.path.join(tmpdir, f"{out_stem}.md")
                with open(tmp_md, "w", encoding="utf-8") as wf:
                    wf.write(merged)
                success, error = run_pandoc(tmp_md, output_pdf, backend_arg)

            elif backend_type == "html-browser":
                tmp_html = os.path.join(tmpdir, f"{out_stem}.html")
                html = _markdown_to_html(merged, group_title)
                with open(tmp_html, "w", encoding="utf-8") as wf:
                    wf.write(html)
                success, error = run_html_browser(tmp_html, output_pdf, backend_arg)

            else:
                success, error = False, "No backend available"

            status_icon = "✓" if success else "✗"
            print(f"  {status_icon}  {'OK' if success else f'FAILED — {error}'}")

            report["groups"].append(
                _build_report_entry(
                    group_key,
                    files,
                    output_pdf,
                    success,
                    error,
                    f"{backend_type} {backend_arg}".strip(),
                )
            )
            report["summary"]["total"] += 1
            if success:
                report["summary"]["success"] += 1
            else:
                report["summary"]["failed"] += 1

    # --- Write report ---------------------------------------------------------
    report_path = output_root / "build-report.json"
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    print(f"\n{'=' * 60}")
    s = report["summary"]
    print(f"Summary : {s['success']}/{s['total']} PDF(s) generated successfully")
    print(f"Report  : {report_path}")

    if s["failed"] > 0:
        print(
            f"\nWARNING: {s['failed']} group(s) failed. "
            f"See {report_path} for details."
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
