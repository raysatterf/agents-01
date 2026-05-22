"""
Unit tests for scripts/build_doc_pdfs.py

Run with:
    python -m unittest discover -v
or:
    python -m unittest tests.test_build_doc_pdfs -v
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure the repo root is on sys.path so the script can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_doc_pdfs import (
    collect_md_groups,
    detect_pdf_backend,
    load_config,
    merge_markdown_files,
    output_name_from_group,
    rewrite_image_paths,
    run_pandoc,
    section_title_from_file,
    sort_files,
    title_from_path,
)


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------

class TestLoadConfig(unittest.TestCase):
    def test_returns_defaults_when_no_file(self):
        config = load_config(None)
        self.assertEqual(config["output_root"], "output-pdf")
        self.assertIn("pandoc", config["pdf_backend_preference"])

    def test_merges_user_values(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as fh:
            json.dump({"output_root": "my-pdfs"}, fh)
            tmp = fh.name
        try:
            config = load_config(tmp)
            self.assertEqual(config["output_root"], "my-pdfs")
            # Default keys not overridden should still be present
            self.assertIn("file_order", config)
        finally:
            os.unlink(tmp)

    def test_ignores_missing_path(self):
        config = load_config("/does/not/exist.json")
        self.assertEqual(config["output_root"], "output-pdf")


# ---------------------------------------------------------------------------
# collect_md_groups
# ---------------------------------------------------------------------------

class TestCollectMdGroups(unittest.TestCase):
    def _make_tree(self, base: Path, structure: dict) -> None:
        """Recursively create files/dirs described by *structure*."""
        for name, value in structure.items():
            path = base / name
            if isinstance(value, dict):
                path.mkdir(parents=True, exist_ok=True)
                self._make_tree(path, value)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value or "", encoding="utf-8")

    def test_groups_by_immediate_parent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            self._make_tree(
                base,
                {
                    "commands": {
                        "scripts.md": "# Scripts",
                        "batch.md": "# Batch",
                    },
                    "setup": {
                        "install.md": "# Install",
                    },
                },
            )
            groups = collect_md_groups(base, ignore_dirs=[], ignore_files=[])
            self.assertIn("commands", groups)
            self.assertIn("setup", groups)
            self.assertEqual(len(groups["commands"]), 2)
            self.assertEqual(len(groups["setup"]), 1)

    def test_root_level_files_keyed_empty_string(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "overview.md").write_text("# Overview", encoding="utf-8")
            groups = collect_md_groups(base, ignore_dirs=[], ignore_files=[])
            self.assertIn("", groups)
            self.assertEqual(len(groups[""]), 1)

    def test_ignores_listed_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            self._make_tree(
                base,
                {
                    "docs": {"page.md": "# Page"},
                    ".git": {"COMMIT_EDITMSG": "commit"},
                    "node_modules": {"lib.md": "# Lib"},
                },
            )
            groups = collect_md_groups(
                base,
                ignore_dirs=[".git", "node_modules"],
                ignore_files=[],
            )
            self.assertIn("docs", groups)
            self.assertNotIn(".git", groups)
            self.assertNotIn("node_modules", groups)

    def test_ignores_listed_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            self._make_tree(
                base,
                {
                    "docs": {
                        "page.md": "# Page",
                        "skip-me.md": "# Skip",
                    }
                },
            )
            groups = collect_md_groups(
                base,
                ignore_dirs=[],
                ignore_files=["skip-me.md"],
            )
            names = [f.name for f in groups.get("docs", [])]
            self.assertIn("page.md", names)
            self.assertNotIn("skip-me.md", names)

    def test_empty_directory_returns_no_groups(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            groups = collect_md_groups(Path(tmpdir), ignore_dirs=[], ignore_files=[])
            self.assertEqual(groups, {})

    def test_nested_subfolders_are_separate_groups(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            self._make_tree(
                base,
                {
                    "ui": {
                        "overview.md": "# Overview",
                        "toolbar": {
                            "add-job.md": "# Add Job",
                        },
                    }
                },
            )
            groups = collect_md_groups(base, ignore_dirs=[], ignore_files=[])
            # The parent folder and the nested subfolder must be separate groups
            ui_key = "ui"
            toolbar_key = os.path.join("ui", "toolbar")
            self.assertIn(ui_key, groups)
            self.assertIn(toolbar_key, groups)
            # Each group should contain only its direct children
            ui_names = [f.name for f in groups[ui_key]]
            self.assertIn("overview.md", ui_names)
            self.assertNotIn("add-job.md", ui_names)
            toolbar_names = [f.name for f in groups[toolbar_key]]
            self.assertIn("add-job.md", toolbar_names)


# ---------------------------------------------------------------------------
# sort_files
# ---------------------------------------------------------------------------

class TestSortFiles(unittest.TestCase):
    def _paths(self, *names: str) -> list:
        return [Path(n) for n in names]

    def test_priority_names_come_first(self):
        files = self._paths("zebra.md", "readme.md", "alpha.md", "index.md")
        result = sort_files(files, ["index.md", "readme.md"])
        self.assertEqual(result[0].name, "index.md")
        self.assertEqual(result[1].name, "readme.md")

    def test_numeric_prefix_sorted_numerically(self):
        files = self._paths("10-chapter.md", "2-chapter.md", "1-chapter.md")
        result = sort_files(files, [])
        self.assertEqual(result[0].name, "1-chapter.md")
        self.assertEqual(result[1].name, "2-chapter.md")
        self.assertEqual(result[2].name, "10-chapter.md")

    def test_alphabetical_fallback(self):
        files = self._paths("zebra.md", "alpha.md", "mango.md")
        result = sort_files(files, [])
        names = [f.name for f in result]
        self.assertEqual(names, sorted(names, key=str.lower))

    def test_empty_list(self):
        self.assertEqual(sort_files([], []), [])


# ---------------------------------------------------------------------------
# title_from_path / section_title_from_file / output_name_from_group
# ---------------------------------------------------------------------------

class TestNamingHelpers(unittest.TestCase):
    def test_title_from_empty_path(self):
        self.assertEqual(title_from_path(""), "Documentation")

    def test_title_from_single_folder(self):
        self.assertEqual(title_from_path("commands"), "Commands")

    def test_title_from_nested_path(self):
        result = title_from_path("client-user-interface/toolbar")
        self.assertIn("Client User Interface", result)
        self.assertIn("Toolbar", result)

    def test_section_title_strips_dashes(self):
        p = Path("add-job.md")
        self.assertEqual(section_title_from_file(p), "Add Job")

    def test_section_title_strips_underscores(self):
        p = Path("assembly_resolver.md")
        self.assertEqual(section_title_from_file(p), "Assembly Resolver")

    def test_output_name_empty_group_key(self):
        self.assertEqual(output_name_from_group(""), "documentation")

    def test_output_name_nested_path(self):
        result = output_name_from_group("client-user-interface/toolbar")
        self.assertEqual(result, "client-user-interface--toolbar")

    def test_output_name_spaces_replaced(self):
        result = output_name_from_group("get visualcron")
        self.assertNotIn(" ", result)


# ---------------------------------------------------------------------------
# rewrite_image_paths
# ---------------------------------------------------------------------------

class TestRewriteImagePaths(unittest.TestCase):
    def test_relative_path_rewritten_when_file_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            img = Path(tmpdir) / "screenshot.png"
            img.write_bytes(b"\x89PNG")

            content = "![Alt text](screenshot.png)"
            result = rewrite_image_paths(content, Path(tmpdir))

            # Should now contain the absolute POSIX path
            self.assertIn(img.as_posix(), result)

    def test_absolute_path_left_unchanged(self):
        content = "![Logo](/absolute/path/logo.png)"
        result = rewrite_image_paths(content, Path("/some/dir"))
        self.assertEqual(result, content)

    def test_http_url_left_unchanged(self):
        content = "![Remote](https://example.com/img.png)"
        result = rewrite_image_paths(content, Path("/some/dir"))
        self.assertEqual(result, content)

    def test_missing_file_leaves_original(self):
        content = "![Alt](nonexistent.png)"
        result = rewrite_image_paths(content, Path("/tmp"))
        self.assertEqual(result, content)


# ---------------------------------------------------------------------------
# merge_markdown_files
# ---------------------------------------------------------------------------

class TestMergeMarkdownFiles(unittest.TestCase):
    def test_single_file_included(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            md = Path(tmpdir) / "page.md"
            md.write_text("Hello world", encoding="utf-8")

            result = merge_markdown_files([md], "My Group")
            self.assertIn("My Group", result)
            self.assertIn("Hello world", result)

    def test_multiple_files_separated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            a = Path(tmpdir) / "a.md"
            b = Path(tmpdir) / "b.md"
            a.write_text("Content A", encoding="utf-8")
            b.write_text("Content B", encoding="utf-8")

            result = merge_markdown_files([a, b], "Group")
            self.assertIn("Content A", result)
            self.assertIn("Content B", result)
            # Separator between files
            self.assertIn("---", result)

    def test_section_heading_added_when_file_has_no_h1(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            md = Path(tmpdir) / "no-heading.md"
            md.write_text("Just plain text here.", encoding="utf-8")

            result = merge_markdown_files([md], "Group")
            self.assertIn("## No Heading", result)

    def test_missing_file_produces_error_message(self):
        result = merge_markdown_files([Path("/nonexistent/file.md")], "Group")
        self.assertIn("Error reading file", result)


# ---------------------------------------------------------------------------
# run_pandoc
# ---------------------------------------------------------------------------

class TestRunPandoc(unittest.TestCase):
    @patch("scripts.build_doc_pdfs.subprocess.run")
    def test_success(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
        ok, err = run_pandoc("in.md", "out.pdf", "")
        self.assertTrue(ok)
        self.assertEqual(err, "")

    @patch("scripts.build_doc_pdfs.subprocess.run")
    def test_failure_returns_stderr(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(returncode=1, stderr="some error", stdout="")
        ok, err = run_pandoc("in.md", "out.pdf", "--pdf-engine=xelatex")
        self.assertFalse(ok)
        self.assertEqual(err, "some error")

    @patch("scripts.build_doc_pdfs.subprocess.run", side_effect=FileNotFoundError)
    def test_pandoc_not_found(self, _mock: MagicMock):
        ok, err = run_pandoc("in.md", "out.pdf", "")
        self.assertFalse(ok)
        self.assertIn("not found", err)


# ---------------------------------------------------------------------------
# detect_pdf_backend
# ---------------------------------------------------------------------------

class TestDetectPdfBackend(unittest.TestCase):
    @patch("scripts.build_doc_pdfs.shutil.which")
    def test_pandoc_with_wkhtmltopdf(self, mock_which: MagicMock):
        def which_side(name):
            return f"/usr/bin/{name}" if name in ("pandoc", "wkhtmltopdf") else None

        mock_which.side_effect = which_side
        backend, arg = detect_pdf_backend(
            ["pandoc-wkhtmltopdf", "pandoc-xelatex", "pandoc"]
        )
        self.assertEqual(backend, "pandoc-engine")
        self.assertIn("wkhtmltopdf", arg)

    @patch("scripts.build_doc_pdfs.shutil.which")
    def test_falls_back_to_pandoc_default(self, mock_which: MagicMock):
        def which_side(name):
            return "/usr/bin/pandoc" if name == "pandoc" else None

        mock_which.side_effect = which_side
        backend, arg = detect_pdf_backend(
            ["pandoc-wkhtmltopdf", "pandoc-xelatex", "pandoc"]
        )
        self.assertEqual(backend, "pandoc-engine")
        self.assertEqual(arg, "")

    @patch("scripts.build_doc_pdfs.shutil.which", return_value=None)
    def test_no_tools_returns_none(self, _mock: MagicMock):
        backend, arg = detect_pdf_backend(
            ["pandoc-wkhtmltopdf", "pandoc-xelatex", "pandoc", "html-edge", "html-chrome"]
        )
        self.assertIsNone(backend)


# ---------------------------------------------------------------------------
# Integration: main() dry-run
# ---------------------------------------------------------------------------

class TestMainDryRun(unittest.TestCase):
    def test_dry_run_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "commands").mkdir()
            (base / "commands" / "scripts.md").write_text(
                "# Scripts\nSome content.", encoding="utf-8"
            )

            from scripts.build_doc_pdfs import main

            exit_code = main(["--source-path", str(base), "--dry-run"])
            self.assertEqual(exit_code, 0)

    def test_missing_source_path_exits_one(self):
        from scripts.build_doc_pdfs import main

        exit_code = main(["--source-path", "/this/does/not/exist", "--dry-run"])
        self.assertEqual(exit_code, 1)

    def test_empty_source_directory_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            from scripts.build_doc_pdfs import main

            exit_code = main(["--source-path", tmpdir, "--dry-run"])
            self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
