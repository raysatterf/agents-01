from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from scripts import build_doc_pdfs


REPO_ROOT = Path(__file__).resolve().parent.parent
CLI_PATH = REPO_ROOT / "scripts" / "build-doc-pdfs.py"


class BuildDocPdfsTests(unittest.TestCase):
    def test_discover_groups_and_ordering(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            docs_root = Path(temp_dir) / "docs"
            (docs_root / "commands").mkdir(parents=True)
            (docs_root / "client area" / "toolbar").mkdir(parents=True)

            for relative_path in [
                "readme.md",
                "10-overview.md",
                "2-intro.md",
                "commands/readme.md",
                "commands/20-run.md",
                "commands/3-setup.md",
                "client area/notes.md",
                "client area/toolbar/add-job.md",
            ]:
                path = docs_root / relative_path
                path.write_text(f"# {path.stem}\n", encoding="utf-8")

            groups = build_doc_pdfs.discover_groups(docs_root)

            self.assertEqual(
                ["docs-root", "client area", "client area/toolbar", "commands"],
                [build_doc_pdfs.group_label(group.relative_dir) for group in groups],
            )
            self.assertEqual(
                ["readme.md", "2-intro.md", "10-overview.md"],
                [path.name for path in groups[0].source_files],
            )
            self.assertEqual(
                ["readme.md", "3-setup.md", "20-run.md"],
                [path.name for path in groups[-1].source_files],
            )

    def test_cli_builds_outputs_and_manifest_with_fake_pandoc(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            docs_root = temp_path / "docs"
            output_root = temp_path / "output-pdf"
            fake_bin = temp_path / "bin"
            fake_bin.mkdir()
            self._write_fake_pandoc(fake_bin / "pandoc")

            (docs_root / "commands").mkdir(parents=True)
            (docs_root / "get visualcron").mkdir(parents=True)
            (docs_root / "client-user-interface" / "toolbar").mkdir(parents=True)

            for relative_path, content in {
                "readme.md": "# Root Readme\n",
                "commands/index.md": "# Commands\n",
                "commands/10-run.md": "# Run\n",
                "get visualcron/quick start.md": "# Quick Start\n",
                "client-user-interface/client-events.md": "# Client Events\n",
                "client-user-interface/toolbar/add-job.md": "# Add Job\n",
            }.items():
                path = docs_root / relative_path
                path.write_text(content, encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(CLI_PATH), "--docs-root", str(docs_root), "--output-root", str(output_root)],
                cwd=REPO_ROOT,
                env=self._build_env(fake_bin),
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, msg=result.stderr)
            self.assertTrue((output_root / "docs-root.pdf").exists())
            self.assertTrue((output_root / "commands.pdf").exists())
            self.assertTrue((output_root / "get visualcron.pdf").exists())
            self.assertTrue((output_root / "client-user-interface" / "toolbar.pdf").exists())
            self.assertTrue((output_root / "merged-markdown" / "commands.md").exists())

            manifest = json.loads((output_root / "build-report.json").read_text(encoding="utf-8"))
            self.assertEqual("pandoc-default", manifest["backend"])
            self.assertEqual(5, manifest["group_count"])
            self.assertEqual([], manifest["failures"])

            built_groups = {group["group"]: group["status"] for group in manifest["groups"]}
            self.assertEqual("built", built_groups["commands"])
            self.assertEqual("built", built_groups["get visualcron"])

    def test_cli_fails_gracefully_without_backend(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            docs_root = temp_path / "docs"
            output_root = temp_path / "output-pdf"
            empty_bin = temp_path / "empty-bin"
            empty_bin.mkdir()
            docs_root.mkdir()
            (docs_root / "readme.md").write_text("# Root\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(CLI_PATH), "--docs-root", str(docs_root), "--output-root", str(output_root)],
                cwd=REPO_ROOT,
                env=self._build_env(empty_bin, include_system_path=False),
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("Completed with failures", result.stderr)

            manifest = json.loads((output_root / "build-report.json").read_text(encoding="utf-8"))
            self.assertEqual(1, manifest["group_count"])
            self.assertEqual(None, manifest["backend"])
            self.assertTrue(manifest["failures"])
            self.assertTrue((output_root / "merged-markdown" / "docs-root.md").exists())

    def _write_fake_pandoc(self, path: Path) -> None:
        path.write_text(
            textwrap.dedent(
                f"""\
                #!{sys.executable}
                import pathlib
                import sys

                args = sys.argv[1:]
                input_path = pathlib.Path(args[args.index("--from=gfm") + 1])
                output_path = pathlib.Path(args[args.index("-o") + 1])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text("PDF\\n" + input_path.read_text(encoding="utf-8"), encoding="utf-8")
                """
            ),
            encoding="utf-8",
        )
        path.chmod(path.stat().st_mode | stat.S_IEXEC)

    def _build_env(self, fake_bin: Path | None, include_system_path: bool = True) -> dict[str, str]:
        env = os.environ.copy()
        path_parts = [str(fake_bin)] if fake_bin else []
        if include_system_path or not path_parts:
            path_parts.append(env["PATH"])
        env["PATH"] = os.pathsep.join(path_parts)
        return env


if __name__ == "__main__":
    unittest.main()
