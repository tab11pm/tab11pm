import tempfile
import unittest
from pathlib import Path

from scripts.update_profile import TEMPLATE_PATHS, count_source_lines, render_svg


class ProfileGeneratorTests(unittest.TestCase):
    def test_visible_identity_uses_tabek_without_changing_github_handle(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("dark.template.svg", "light.template.svg"):
            svg = (root / name).read_text(encoding="utf-8")
            self.assertIn("I'm Tabek", svg)
            self.assertIn(">Tabek</text>", svg)
            self.assertIn("github.com/tab11pm", svg)

    def test_readme_has_approved_clickable_links_and_sections(self):
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
        self.assertIn('href="https://github.com/tab11pm"', readme)
        self.assertIn('href="mailto:tabrez.frontend@gmail.com"', readme)
        self.assertIn("## About", readme)
        self.assertIn("## Tech Stack", readme)
        self.assertIn("Tabek", readme)

    def test_both_svg_templates_contain_each_stat_token_once(self):
        for template_path in TEMPLATE_PATHS:
            template = template_path.read_text(encoding="utf-8")
            for token in ("REPOS", "STARS", "COMMITS_YEAR", "FOLLOWERS", "LOC"):
                self.assertEqual(template.count("{{" + token + "}}"), 1, f"{template_path.name}: {token}")

    def test_count_source_lines_ignores_empty_lines_and_excluded_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "src" / "app.py").write_text("print('x')\n\n# note\n", encoding="utf-8")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "vendor.js").write_text("x\n", encoding="utf-8")
            self.assertEqual(count_source_lines(root), 2)

    def test_render_svg_replaces_every_stat_token(self):
        source = "{{REPOS}}/{{STARS}}/{{COMMITS_YEAR}}/{{FOLLOWERS}}/{{LOC}}"
        values = {
            "REPOS": "2",
            "STARS": "7",
            "COMMITS_YEAR": "14",
            "FOLLOWERS": "3",
            "LOC": "99",
        }
        self.assertEqual(render_svg(source, values), "2/7/14/3/99")


if __name__ == "__main__":
    unittest.main()
