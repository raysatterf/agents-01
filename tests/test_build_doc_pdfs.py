import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import build_doc_pdfs


class BuildDocPdfsTests(unittest.TestCase):
    def test_discover_groups_uses_immediate_children_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            (docs / "commands").mkdir(parents=True)
            (docs / "commands" / "scripts.md").write_text("# scripts", encoding="utf-8")
            (docs / "commands" / "readme.md").write_text("# readme", encoding="utf-8")
            (docs / "commands" / "nested").mkdir(parents=True)
            (docs / "commands" / "nested" / "child.md").write_text("# child", encoding="utf-8")

            groups = build_doc_pdfs.discover_groups(docs)
            by_folder = {
                str(group.folder.relative_to(docs)): [path.name for path in group.files]
                for group in groups
            }

            self.assertEqual(by_folder["commands"], ["readme.md", "scripts.md"])
            self.assertEqual(by_folder["commands/nested"], ["child.md"])

    def test_sort_markdown_files_prioritizes_index_and_readme_then_natural(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = [
                root / "chapter10.md",
                root / "README.md",
                root / "chapter2.md",
                root / "index.md",
            ]
            sorted_names = [path.name for path in build_doc_pdfs.sort_markdown_files(files)]
            self.assertEqual(sorted_names, ["index.md", "README.md", "chapter2.md", "chapter10.md"])

    def test_resolve_output_pdf_handles_spaces(self):
        docs_dir = Path("/tmp/docs")
        group = build_doc_pdfs.Group(
            folder=Path("/tmp/docs/get visualcron"),
            files=[Path("/tmp/docs/get visualcron/assembly-resolver.md")],
        )
        output = build_doc_pdfs.resolve_output_pdf(Path("/tmp/out"), docs_dir, group)
        self.assertEqual(output, Path("/tmp/out/get visualcron.pdf"))

    def test_resolve_output_pdf_handles_nested_groups(self):
        docs_dir = Path("/tmp/docs")
        group = build_doc_pdfs.Group(
            folder=Path("/tmp/docs/client-user-interface/toolbar"),
            files=[Path("/tmp/docs/client-user-interface/toolbar/add-job.md")],
        )
        output = build_doc_pdfs.resolve_output_pdf(Path("/tmp/out"), docs_dir, group)
        self.assertEqual(output, Path("/tmp/out/client-user-interface/toolbar.pdf"))

    def test_render_pdf_tries_detected_backends_then_fallback(self):
        markdown_path = Path("/tmp/input.md")
        output_pdf = Path("/tmp/output.pdf")

        with mock.patch("scripts.build_doc_pdfs.shutil.which") as which_mock, mock.patch(
            "scripts.build_doc_pdfs.run"
        ) as run_mock:
            def which_side_effect(name):
                if name == "pandoc":
                    return "/usr/bin/pandoc"
                if name in {"wkhtmltopdf", "pdflatex"}:
                    return f"/usr/bin/{name}"
                return None

            which_mock.side_effect = which_side_effect
            run_mock.side_effect = [
                mock.Mock(returncode=1, stderr="wk failed"),
                mock.Mock(returncode=0, stderr=""),
            ]

            backend = build_doc_pdfs.render_pdf_with_pandoc(markdown_path, output_pdf)

            self.assertEqual(backend, "pandoc:pdflatex")
            first_cmd = run_mock.call_args_list[0].args[0]
            second_cmd = run_mock.call_args_list[1].args[0]
            self.assertIn("wkhtmltopdf", first_cmd)
            self.assertIn("pdflatex", second_cmd)


if __name__ == "__main__":
    unittest.main()
