from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reviewlib import classify, config as config_mod, files, gh, guidelines, render  # noqa: E402


class FilesTests(unittest.TestCase):
    def test_reads_utf8_utf8bom_and_utf16(self):
        text = '{"repo": "acme/demo", "pr": 1, "note": "caf\u00e9 \u4e2d\u6587"}'
        with tempfile.TemporaryDirectory() as tmp:
            cases = {
                "utf8.json": text.encode("utf-8"),
                "bom.json": text.encode("utf-8-sig"),
                "utf16.json": text.encode("utf-16"),  # what PowerShell `>` writes
            }
            for name, data in cases.items():
                path = Path(tmp) / name
                path.write_bytes(data)
                self.assertEqual(json.loads(files.read_text(path))["pr"], 1, name)


class ClassifyTests(unittest.TestCase):
    def test_db_files(self):
        cases = [
            "db/migrate/20240101_create_users.rb",
            "app/migrations/0001_initial.py",
            "prisma/schema.prisma",
            "migrations/001_add_index.sql",
            "src/main/resources/db/migration/V1__init.sql",
            "src/models/user.py",
            "liquibase/changelog.xml",
        ]
        for path in cases:
            self.assertEqual(classify.classify_path(path), "db", path)

    def test_test_files(self):
        for path in ["tests/test_app.py", "src/foo_test.go", "web/app.spec.ts", "spec/models/user_spec.rb"]:
            self.assertEqual(classify.classify_path(path), "test", path)

    def test_docs_and_code(self):
        self.assertEqual(classify.classify_path("docs/guide.md"), "doc")
        self.assertEqual(classify.classify_path("src/index.ts"), "code")
        self.assertEqual(classify.classify_path("Makefile"), "other")

    def test_classify_files_groups(self):
        files = [
            {"filename": "db/migrate/1_x.sql"},
            {"filename": "src/app.py"},
            {"filename": "tests/test_app.py"},
        ]
        grouped = classify.classify_files(files)
        self.assertEqual([classify.path_of(f) for f in grouped["db"]], ["db/migrate/1_x.sql"])
        self.assertEqual(len(grouped["code"]), 1)
        self.assertEqual(len(grouped["test"]), 1)


class RenderTests(unittest.TestCase):
    def test_fail_comment(self):
        body = render.render_comment(
            skill="DB Review",
            verdict="fail",
            summary="Rollback missing.",
            findings=[
                {"severity": "blocker", "file": "db/migrate/1.sql", "line": 3, "message": "DROP TABLE", "rule": "destructive"},
                {"severity": "warning", "file": "db/migrate/2.sql", "message": "No index on FK"},
            ],
            guidelines=["general", "repo-specific"],
            marker="<!-- db-review-agent -->",
        )
        self.assertIn("## DB Review: FAILED", body)
        self.assertIn("Blockers", body)
        self.assertIn("`db/migrate/1.sql:3`", body)
        self.assertIn("Guidelines applied: `general`, `repo-specific`", body)
        self.assertTrue(body.rstrip().endswith("<!-- db-review-agent -->"))

    def test_pass_comment_no_findings(self):
        body = render.render_comment(skill="Code Review", verdict=True)
        self.assertIn("## Code Review: PASS", body)
        self.assertIn("_No issues found._", body)


class ConfigTests(unittest.TestCase):
    def test_deep_merge(self):
        merged = config_mod.deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"b": 9}})
        self.assertEqual(merged, {"a": {"b": 9, "c": 2}})

    def test_resolve_local_repo_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            review = Path(tmp) / ".review"
            review.mkdir()
            (review / "config.json").write_text(
                json.dumps({"registry": "custom/reg.md", "commands": {"test": "pytest"}}),
                encoding="utf-8",
            )
            cfg = config_mod.resolve(repo_root=tmp)
            self.assertEqual(cfg["registry"], "custom/reg.md")
            self.assertEqual(cfg["commands"]["test"], "pytest")
            self.assertIsNone(cfg["commands"]["lint"])


class GuidelinesTests(unittest.TestCase):
    def test_merge_general_and_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "db-review"
            (skill_dir / "references").mkdir(parents=True)
            (skill_dir / "references" / "general-guidelines.md").write_text(
                "# General\nAlways provide rollback.", encoding="utf-8"
            )
            repo = Path(tmp) / "repo"
            (repo / ".review").mkdir(parents=True)
            (repo / ".review" / "db-guidelines.md").write_text(
                "# Repo\nNo DROP on prod.", encoding="utf-8"
            )
            data = guidelines.load_merged(skill_dir=skill_dir, key="db", repo_root=str(repo))
            self.assertEqual(data["sources"], ["general", "repo-specific"])
            self.assertIn("Always provide rollback.", data["combined"])
            self.assertIn("No DROP on prod.", data["combined"])

    def test_general_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "db-review"
            (skill_dir / "references").mkdir(parents=True)
            (skill_dir / "references" / "general-guidelines.md").write_text("# General", encoding="utf-8")
            data = guidelines.load_merged(skill_dir=skill_dir, key="db")
            self.assertEqual(data["sources"], ["general"])


class GhEditTests(unittest.TestCase):
    def _fake(self, stdout: str = "") -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")

    def test_issue_edit_builds_args(self):
        with mock.patch.object(gh, "_gh", return_value=self._fake("https://x/7\n")) as m:
            url = gh.issue_edit("owner/repo", 7, add_assignees=["alice"], add_labels=["issue-analysed", "bug"])
        self.assertEqual(url, "https://x/7")
        args = m.call_args.args[0]
        self.assertEqual(args[:4], ["issue", "edit", "7", "--repo"])
        self.assertIn("owner/repo", args)
        self.assertIn("--add-assignee", args)
        self.assertIn("alice", args)
        self.assertEqual(args.count("--add-label"), 2)

    def test_issue_edit_requires_change(self):
        with self.assertRaises(ValueError):
            gh.issue_edit("owner/repo", 7)

    def test_label_ensure_uses_force(self):
        with mock.patch.object(gh, "_gh", return_value=self._fake()) as m:
            ensured = gh.label_ensure("owner/repo", ["issue-analysed", "bug"])
        self.assertEqual(ensured, ["issue-analysed", "bug"])
        self.assertEqual(m.call_count, 2)
        for call in m.call_args_list:
            args = call.args[0]
            self.assertEqual(args[:2], ["label", "create"])
            self.assertIn("--force", args)


if __name__ == "__main__":
    unittest.main()
