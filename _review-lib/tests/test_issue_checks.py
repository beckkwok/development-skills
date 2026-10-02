from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent.parent / "debug-analysis"
sys.path.insert(0, str(SKILL_DIR.parent / "_review-lib"))

_spec = importlib.util.spec_from_file_location(
    "issue_checks", SKILL_DIR / "scripts" / "issue_checks.py"
)
issue_checks = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(issue_checks)


def _issue(title="", body="", labels=None):
    return {
        "number": 7,
        "title": title,
        "body": body,
        "url": "https://github.com/acme/demo/issues/7",
        "labels": [{"name": name} for name in (labels or [])],
    }


class KindTests(unittest.TestCase):
    def test_label_priority(self):
        self.assertEqual(issue_checks.detect_kind(_issue("Boom", "x", ["bug"])), "bug")
        self.assertEqual(issue_checks.detect_kind(_issue("Boom", "x", ["enhancement"])), "feature")
        self.assertEqual(issue_checks.detect_kind(_issue("Boom", "x", ["question"])), "question")

    def test_keyword_heuristics(self):
        self.assertEqual(
            issue_checks.detect_kind(_issue("Feature request: dark mode", "Please add support for themes")),
            "feature",
        )
        self.assertEqual(
            issue_checks.detect_kind(_issue("Crash on launch", "Traceback: TypeError")),
            "bug",
        )
        self.assertEqual(
            issue_checks.detect_kind(_issue("How do I configure this?", "Is there a way to...")),
            "question",
        )
        self.assertEqual(issue_checks.detect_kind(_issue("Hello", "Just saying hi")), "unclear")

    def test_extract_includes_kind(self):
        data = issue_checks.extract(_issue("Feature request: x", "Please add y"))
        self.assertEqual(data["kind"], "feature")


class RenderTests(unittest.TestCase):
    def test_feature_render_with_questions_and_sub_issues(self):
        issue = _issue("Feature request: dark mode", "Please add support", ["enhancement"])
        analysis = {
            "kind": "feature",
            "summary": "Add a dark theme toggle.",
            "confidence": "medium",
            "assessment": "Fits the existing settings screen.",
            "feasibility": "Needs a theme store; see app/lib/screens/settings_screen.dart:1.",
            "questions": ["Light or dark first?", "Persist per device?"],
            "sub_issues": [{"number": 12, "url": "https://github.com/acme/demo/issues/12", "title": "[Parent #7] theme store"}],
            "next_steps": ["Answer questions, then implement."],
        }
        body = issue_checks.render(issue, analysis, ["general"])
        self.assertIn("## Feature Analysis:", body)
        self.assertIn("### Questions for the author", body)
        self.assertIn("1. Light or dark first?", body)
        self.assertIn("[#12](https://github.com/acme/demo/issues/12)", body)
        self.assertTrue(body.rstrip().endswith("<!-- debug-analysis-agent -->"))

    def test_bug_render_unchanged(self):
        issue = _issue("Crash", "Traceback", ["bug"])
        analysis = {
            "kind": "bug",
            "summary": "s",
            "confidence": "high",
            "makes_sense": {"verdict": "yes", "reasoning": "r"},
            "reproducible": {"verdict": "unknown", "method": "m"},
        }
        body = issue_checks.render(issue, analysis, [])
        self.assertIn("## Debug Analysis:", body)
        self.assertIn("### 1. Does the bug make sense?", body)


if __name__ == "__main__":
    unittest.main()
