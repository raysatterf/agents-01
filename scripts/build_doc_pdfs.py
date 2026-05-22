#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

PRIORITY_FILENAMES = {"index.md": 0, "readme.md": 1}
LINK_PATTERN = re.compile(r"(!?\[[^\]]*]\(([^)]+)\))")


@dataclass(frozen=True)
class Backend:
    name: str
    command: list[str]


@dataclass(frozen=True)
class Group:
    relative_dir: Path
    source_files: list[Path]


def natural_sort_key(value: str) -> list[object]:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", value.casefold())]


def sort_markdown_files(files: Iterable[Path]) -> list[Path]:
    def file_key(path: Path) -> tuple[int, list[object], list[object]]:
        return (
            PRIORITY_FILENAMES.get(path.name.casefold(), 2),
            natural_sort_key(path.stem),
            natural_sort_key(path.name),
        )

    return sorted(files, key=file_key)


def group_sort_key(group: Group) -> tuple[list[object], ...]:
    if group.relative_dir == Path("."):
        return ()
    return tuple(natural_sort_key(part) for part in group.relative_dir.parts)


def discover_groups(docs_root: Path) -> list[Group]:
    groups: list[Group] = []
    for current_dir, dirnames, filenames in os.walk(docs_root):
        dirnames.sort(key=natural_sort_key)
        markdown_files = [
            Path(current_dir, filename)
            for filename in filenames
            if Path(filename).suffix.casefold() == ".md"
        ]
        if not markdown_files:
            continue

        relative_dir = Path(current_dir).relative_to(docs_root)
        groups.append(Group(relative_dir=relative_dir, source_files=sort_markdown_files(markdown_files)))

    return sorted(groups, key=group_sort_key)


def group_label(relative_dir: Path) -> str:
    return "docs-root" if relative_dir == Path(".") else relative_dir.as_posix()


def title_from_name(value: str) -> str:
    cleaned = re.sub(r"[-_]+", " ", value).strip()
    return cleaned.title() if cleaned else "Untitled"


def group_title(relative_dir: Path) -> str:
    if relative_dir == Path("."):
        return "Docs Root"
    return " / ".join(title_from_name(part) for part in relative_dir.parts)


def merged_markdown_path(output_root: Path, relative_dir: Path) -> Path:
    base_dir = output_root / "merged-markdown"
    if relative_dir == Path("."):
        return base_dir / "docs-root.md"
    return (base_dir / relative_dir).with_suffix(".md")


def pdf_output_path(output_root: Path, relative_dir: Path) -> Path:
    if relative_dir == Path("."):
        return output_root / "docs-root.pdf"
    return (output_root / relative_dir).with_suffix(".pdf")


def split_markdown_target(raw_target: str) -> str:
    target = raw_target.strip().strip("<>").split()[0]
    return target.split("#", 1)[0]


def is_local_relative_target(target: str) -> bool:
    if not target or target.startswith("#"):
        return False
    lowered = target.casefold()
    return not (
        "://" in lowered
        or lowered.startswith("mailto:")
        or lowered.startswith("file:")
        or os.path.isabs(target)
    )


def collect_missing_target_warnings(source_file: Path) -> list[str]:
    warnings: list[str] = []
    content = source_file.read_text(encoding="utf-8")
    for _, raw_target in LINK_PATTERN.findall(content):
        target = split_markdown_target(raw_target)
        if not is_local_relative_target(target):
            continue
        candidate = (source_file.parent / target).resolve()
        if not candidate.exists():
            warnings.append(f"{source_file.as_posix()}: missing referenced asset '{target}'")
    return warnings


def build_merged_markdown(group: Group, output_root: Path) -> tuple[Path, list[str]]:
    merged_path = merged_markdown_path(output_root, group.relative_dir)
    merged_path.parent.mkdir(parents=True, exist_ok=True)
    title = group_title(group.relative_dir)
    lines = [f"# {title}", ""]
    warnings: list[str] = []

    multiple_files = len(group.source_files) > 1
    for index, source_file in enumerate(group.source_files):
        warnings.extend(collect_missing_target_warnings(source_file))
        if multiple_files:
            lines.extend(
                [
                    f"## {title_from_name(source_file.stem)}",
                    "",
                    f"_Source: {source_file.as_posix()}_",
                    "",
                ]
            )

        lines.append(source_file.read_text(encoding="utf-8").rstrip())
        lines.append("")
        if multiple_files and index != len(group.source_files) - 1:
            lines.extend(["\\newpage", ""])

    merged_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return merged_path, warnings


def probe_backend() -> tuple[Backend | None, list[dict[str, object]]]:
    executables = {
        "pandoc": shutil.which("pandoc"),
        "wkhtmltopdf": shutil.which("wkhtmltopdf"),
        "xelatex": shutil.which("xelatex"),
        "pdflatex": shutil.which("pdflatex"),
    }

    probes = [
        ("pandoc-wkhtmltopdf", executables["pandoc"] and executables["wkhtmltopdf"], ["pandoc", "--pdf-engine=wkhtmltopdf"]),
        ("pandoc-xelatex", executables["pandoc"] and executables["xelatex"], ["pandoc", "--pdf-engine=xelatex"]),
        ("pandoc-pdflatex", executables["pandoc"] and executables["pdflatex"], ["pandoc", "--pdf-engine=pdflatex"]),
        ("pandoc-default", executables["pandoc"], ["pandoc"]),
    ]

    manifest_probes: list[dict[str, object]] = []
    selected_backend: Backend | None = None

    for name, available, command in probes:
        manifest_probes.append({"name": name, "available": bool(available)})
        if available and selected_backend is None:
            selected_backend = Backend(name=name, command=command)

    return selected_backend, manifest_probes


def render_group_to_pdf(backend: Backend, merged_markdown: Path, pdf_output: Path, resource_paths: list[Path]) -> None:
    pdf_output.parent.mkdir(parents=True, exist_ok=True)
    command = list(backend.command)
    command.extend(
        [
            "--from=gfm",
            str(merged_markdown),
            "-o",
            str(pdf_output),
            f"--resource-path={os.pathsep.join(str(path) for path in resource_paths)}",
        ]
    )
    subprocess.run(command, check=True, capture_output=True, text=True)


def write_manifest(manifest_path: Path, payload: dict[str, object]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def build_docs(docs_root: Path, output_root: Path, manifest_path: Path) -> int:
    output_root.mkdir(parents=True, exist_ok=True)
    groups = discover_groups(docs_root) if docs_root.exists() else []
    backend, backend_probes = probe_backend()
    utc_timestamp = datetime.now(timezone.utc).isoformat()

    manifest: dict[str, object] = {
        "generated_at": utc_timestamp,
        "docs_root": str(docs_root),
        "output_root": str(output_root),
        "manifest_path": str(manifest_path),
        "backend": backend.name if backend else None,
        "backend_probes": backend_probes,
        "group_count": len(groups),
        "groups": [],
        "warnings": [],
        "failures": [],
    }

    if not docs_root.exists():
        message = f"Docs root not found: {docs_root}"
        manifest["failures"].append(message)
        write_manifest(manifest_path, manifest)
        print(message, file=sys.stderr)
        return 1

    if not groups:
        manifest["warnings"].append(f"No markdown groups found under {docs_root}")
        write_manifest(manifest_path, manifest)
        print(f"No markdown files found under {docs_root}")
        return 0

    for group in groups:
        merged_path, group_warnings = build_merged_markdown(group, output_root)
        group_record: dict[str, object] = {
            "group": group_label(group.relative_dir),
            "relative_dir": "." if group.relative_dir == Path(".") else group.relative_dir.as_posix(),
            "source_files": [str(path) for path in group.source_files],
            "merged_markdown": str(merged_path),
            "pdf_output": str(pdf_output_path(output_root, group.relative_dir)),
            "backend": backend.name if backend else None,
            "warnings": group_warnings,
            "status": "merged",
        }
        manifest["warnings"].extend(group_warnings)
        manifest["groups"].append(group_record)

        if backend is None:
            error = (
                "No supported local PDF backend was found. Install pandoc "
                "(plus wkhtmltopdf, xelatex, or pdflatex if needed) and see "
                "README.md: 'Build grouped documentation PDFs' for setup details."
            )
            group_record["status"] = "failed"
            group_record["error"] = error
            manifest["failures"].append(f"{group_label(group.relative_dir)}: {error}")
            continue

        try:
            render_group_to_pdf(
                backend=backend,
                merged_markdown=merged_path,
                pdf_output=pdf_output_path(output_root, group.relative_dir),
                resource_paths=[docs_root / group.relative_dir, docs_root],
            )
            group_record["status"] = "built"
        except subprocess.CalledProcessError as error:
            error_message = error.stderr.strip() or error.stdout.strip() or str(error)
            group_record["status"] = "failed"
            group_record["error"] = error_message
            manifest["failures"].append(f"{group_label(group.relative_dir)}: {error_message}")

    write_manifest(manifest_path, manifest)

    if manifest["failures"]:
        print(f"Completed with failures. See manifest: {manifest_path}", file=sys.stderr)
        return 1

    print(f"Built {len(groups)} PDF group(s) using {backend.name}. Manifest: {manifest_path}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build grouped PDFs from docs markdown folders.")
    parser.add_argument("--docs-root", default="docs", help="Root docs directory to scan. Defaults to ./docs")
    parser.add_argument("--output-root", default="output-pdf", help="Directory for generated PDFs and merged markdown.")
    parser.add_argument("--manifest", default=None, help="Optional manifest path. Defaults to <output-root>/build-report.json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    docs_root = Path(args.docs_root).resolve()
    output_root = Path(args.output_root).resolve()
    manifest_path = Path(args.manifest).resolve() if args.manifest else output_root / "build-report.json"
    return build_docs(docs_root=docs_root, output_root=output_root, manifest_path=manifest_path)


if __name__ == "__main__":
    raise SystemExit(main())
