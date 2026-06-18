from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vibewiki.capture import capture_session
from vibewiki.distill import distill_session
from vibewiki.import_markdown import import_markdown_session
from vibewiki.merge import merge_patches
from vibewiki.project import init_project
from vibewiki.review import review_patches
from vibewiki.validate import validate_skill_file, validate_skill_text


class VibeWikiFlowTest(unittest.TestCase):
    def test_local_memory_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            created = init_project(root)
            self.assertIn(root / ".vibewiki" / "config.yaml", created)
            self.assertTrue((root / "docs" / "wiki" / "index.md").exists())
            self.assertTrue((root / "AGENTS.md").exists())

            session = capture_session(
                root,
                goal="Fix simulator mismatch",
                outcome="Aligned output with the reference trace",
                commands=["make run-vemu"],
            )
            self.assertTrue(session.session_md.exists())
            self.assertTrue(session.diff_patch.exists())
            self.assertTrue(session.metadata_yaml.exists())

            patches = distill_session(root)
            self.assertTrue(patches.knowledge_patch.exists())
            self.assertTrue(patches.skill_patch.exists())
            self.assertTrue(patches.agent_rule_patch.exists())
            self.assertIn("Which test", patches.questions.read_text(encoding="utf-8"))
            skill_text = patches.skill_patch.read_text(encoding="utf-8")
            self.assertIn("## When Not To Use", skill_text)
            self.assertIn("## Probes", skill_text)
            self.assertIn("## Evolution Log", skill_text)
            report = validate_skill_file(patches.skill_patch)
            self.assertEqual(report.errors, [])
            self.assertTrue(report.warnings)
            self.assertTrue(report.ok())
            self.assertFalse(report.ok(strict=True))

            review = review_patches(root, patch_dir=patches.patch_dir, approve=True)
            self.assertIn("decision: approved", review.review_file.read_text(encoding="utf-8"))

            changed = merge_patches(root, patch_dir=patches.patch_dir)
            self.assertIn(root / "docs" / "wiki" / "development_notes.md", changed)
            self.assertIn(root / "AGENTS.md", changed)
            self.assertTrue((root / "skills" / f"{session.session_id}.md").exists())

    def test_skill_validation_requires_sections(self) -> None:
        report = validate_skill_text(
            """# Skill Patch

## Skill Name

Incomplete Skill
""",
        )

        self.assertFalse(report.ok())
        self.assertTrue(any(item.code == "missing-section" for item in report.errors))

    def test_import_markdown_creates_session_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "codex_session.md"
            source.write_text(
                """# Fix VEMU Output Mismatch

> Help me debug the simulator mismatch.

结论：VEMU output now matches the reference trace.

```bash
make -C /work/VEMU/dsl all
python3 compare_outputs.py
```

验证情况：
- resource check passed
- exit code 0
- RMSE 0
""",
                encoding="utf-8",
            )

            session = import_markdown_session(root, source)
            self.assertTrue((session.session_dir / "raw_session.md").exists())
            session_text = session.session_md.read_text(encoding="utf-8")
            self.assertIn("Fix VEMU Output Mismatch", session_text)
            self.assertIn("make -C /work/VEMU/dsl all", session_text)
            self.assertIn("exit code 0", session_text)
            self.assertIn("imported_from:", session.metadata_yaml.read_text(encoding="utf-8"))

            patches = distill_session(root, session_dir=session.session_dir)
            self.assertTrue(patches.skill_patch.exists())
            self.assertIn("make -C /work/VEMU/dsl all", patches.skill_patch.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
