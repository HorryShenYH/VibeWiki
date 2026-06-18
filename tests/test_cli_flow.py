from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vibewiki.capture import capture_session
from vibewiki.distill import distill_session
from vibewiki.import_markdown import extract_hint_lines, import_markdown_session
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
            self.assertTrue((root / "skills" / "skilllets" / "index.md").exists())
            self.assertTrue((root / "skills" / "prompt_patterns" / "index.md").exists())
            self.assertTrue((root / "skills" / "workflows" / "index.md").exists())

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
            self.assertTrue((patches.skilllets_dir / "fix-simulator-mismatch.md").exists())
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
            self.assertTrue((root / "skills" / "skilllets" / "fix-simulator-mismatch.md").exists())

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

    def test_distill_splits_long_session_into_composable_units(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "matlab_vemu_session.md"
            source.write_text(
                """# Remote MATLAB Agent And NR Demod

We need a MATLAB Agent task package from `vemu_dag_summary.json`.
The remote worker must produce `run_vemu_gold.m` and `config_schema.json`.

Windows SSH note: the user is in Administrators, so OpenSSH reads
`C:\\ProgramData\\ssh\\administrators_authorized_keys` under the
`Match Group administrators` rule. `sshpass` is only for first login.

MATLAB reference: use `nrSymbolModulate` and `nrSymbolDemodulate`.
The QPSK run fixed `llr_scale = 0.35355339059327373`.
BAS `char` values are signed int8 byte patterns: `255 -> -1`.
The C build has `-fno-signed-char`, so convert explicitly.

Generated cases live in `generated_bas`, then materialize one
`TARGET_DAG` per case and compare `DAGRet_demod.log`.
For F5 set `VENUSROW=128` and `VENUSLANE=16` in `config.mk`.

Final vector implementation uses `vload`, `vseq`, `vbrdcst`,
`MASKREAD_ON`, and `vshuffle` to keep Venus registers bounded.

Verification:
QPSK:   max_abs_diff=0 bad_abs_gt_1=0
16QAM:  max_abs_diff=0 bad_abs_gt_1=0
64QAM:  max_abs_diff=0 bad_abs_gt_1=0
256QAM: max_abs_diff=1 bad_abs_gt_1=0
""",
                encoding="utf-8",
            )

            session = import_markdown_session(root, source)
            patches = distill_session(root, session_dir=session.session_dir)

            expected = [
                patches.prompt_patterns_dir / "remote-matlab-agent-task-package.md",
                patches.skilllets_dir / "windows-ssh-key-for-admin-worker.md",
                patches.skilllets_dir / "matlab-nr-demod-reference.md",
                patches.skilllets_dir / "bas-char-signed-int8.md",
                patches.skilllets_dir / "vemu-f5-venus-128x16.md",
                patches.skilllets_dir / "matlab-gold-vemu-compare.md",
                patches.skilllets_dir / "venus-vector-lut-mask-scatter.md",
                patches.workflows_dir / "materialize-vemu-replay-cases.md",
            ]
            for path in expected:
                self.assertTrue(path.exists(), path)

            index_text = (patches.patch_dir / "composable_units.md").read_text(encoding="utf-8")
            self.assertIn("Venus Vector LUT Mask Scatter", index_text)
            vector_text = (patches.skilllets_dir / "venus-vector-lut-mask-scatter.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("Evidence From Session", vector_text)
            self.assertIn("vshuffle", vector_text)

            review_patches(root, patch_dir=patches.patch_dir, approve=True)
            changed = merge_patches(root, patch_dir=patches.patch_dir)
            merged = root / "skills" / "skilllets" / "matlab-nr-demod-reference.md"
            self.assertIn(merged, changed)
            self.assertIn(
                "MATLAB NR Demod Reference",
                merged.read_text(encoding="utf-8"),
            )

    def test_import_markdown_does_not_treat_paths_as_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "paths_and_commands.md"
            source.write_text(
                """# Path Heavy Session

Useful files:
- `Debug/emulator_vins_result/task0/hart0`
- `./5g_lite/tasks/nrPDSCHDag1_v2/Task.c`

Useful commands:
```bash
cd /work/VEMU
rm -rf Debug/emulator_vins_result
./Emulator test.hex -w -j../dsl/final_output/dag1.json -b../dsl/bin/dag1.bin
Debug/Emulator test.hex -w -j../dsl/final_output/dag1.json -b../dsl/bin/dag1.bin
```
""",
                encoding="utf-8",
            )

            session = import_markdown_session(root, source)
            session_text = session.session_md.read_text(encoding="utf-8")
            self.assertIn("cd /work/VEMU", session_text)
            self.assertIn("rm -rf Debug/emulator_vins_result", session_text)
            self.assertIn("./Emulator test.hex", session_text)
            self.assertIn("Debug/Emulator test.hex", session_text)
            self.assertNotIn("- Debug/emulator_vins_result/task0/hart0", session_text)
            self.assertNotIn("- ./5g_lite/tasks/nrPDSCHDag1_v2/Task.c", session_text)

    def test_import_markdown_hint_matching_avoids_poweredge_prompt(self) -> None:
        lines = extract_hint_lines(
            """shenyihao@greatcsi-PowerEdge-R740:~/Project$ git status
relative RMSE: 12.3%
功耗结果有效
""",
            ("power", "relative rmse", "功耗"),
        )

        self.assertNotIn("shenyihao@greatcsi-PowerEdge-R740:~/Project$ git status", lines)
        self.assertIn("relative RMSE: 12.3%", lines)
        self.assertIn("功耗结果有效", lines)


if __name__ == "__main__":
    unittest.main()
