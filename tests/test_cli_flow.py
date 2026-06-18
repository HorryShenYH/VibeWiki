from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from vibewiki.capture import capture_session
from vibewiki.distill import distill_session
from vibewiki.import_markdown import extract_hint_lines, import_markdown_session
from vibewiki.import_url import chatgpt_share_to_markdown, html_to_markdown, import_url_session
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
            self.assertTrue((root / "docs" / "wiki" / "knowledge.md").exists())
            self.assertTrue((root / "docs" / "wiki" / "todos.md").exists())
            self.assertTrue((root / "docs" / "wiki" / "ideas.md").exists())
            self.assertTrue((root / "docs" / "wiki" / "research_notes.md").exists())
            self.assertTrue((root / "docs" / "wiki" / "directions.md").exists())
            self.assertTrue((root / ".vibewiki" / "skill_registry.yaml").exists())

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
            self.assertTrue(patches.findings_index.exists())
            self.assertTrue(patches.merge_suggestions.exists())
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
            self.assertIn(
                "fix-simulator-mismatch",
                (root / ".vibewiki" / "skill_registry.yaml").read_text(encoding="utf-8"),
            )

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

    def test_findings_keep_non_procedural_memory_out_of_skilllets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "vcmxmul_session.md"
            source.write_text(
                """# VCMXMUL OFDM Notes

VCMXMUL uses the Gauss form `C*(A-B) + B*(C-D)`.
It is algebraically valid, but not bit-exact in fixed-point because 截断 and 饱和
happen at different points. The OFDM FFT output had relative RMSE about 140%,
so the error is 不可忽略.

The default path should stay `CMUL_WN_EXPLICIT_V1_STYLE` with no `vns_cmxmul`.
Future direction: consider raw product, wide post_adder, final shift, and
VCMXMUL_ACC for 8bit precision.

For evaluation, compute MAE, RMSE, relative RMSE, correlation, and mismatch.
""",
                encoding="utf-8",
            )

            session = import_markdown_session(root, source)
            patches = distill_session(root, session_dir=session.session_dir)

            self.assertTrue(
                (patches.findings_dir / "knowledge__vcmxmul-fixed-point-gauss-caveat.md").exists()
            )
            self.assertTrue(
                (patches.findings_dir / "direction__cau-vcmxmul-raw-product-wide-accumulate.md").exists()
            )
            self.assertFalse(
                (patches.skilllets_dir / "vcmxmul-fixed-point-gauss-caveat.md").exists()
            )
            self.assertTrue(
                (patches.skilllets_dir / "quantized-output-error-analysis.md").exists()
            )

            review_patches(root, patch_dir=patches.patch_dir, approve=True)
            changed = merge_patches(root, patch_dir=patches.patch_dir)
            self.assertIn(root / "docs" / "wiki" / "knowledge.md", changed)
            self.assertIn(root / "docs" / "wiki" / "directions.md", changed)
            self.assertTrue(
                (root / "skills" / "skilllets" / "quantized-output-error-analysis.md").exists()
            )

    def test_registry_reuses_existing_skilllet_slug(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            first = capture_session(
                root,
                goal="First VEMU compare",
                outcome="Compared VEMU output against MATLAB gold",
                tests="max_abs_diff=0\nbad_abs_gt_1=0\nMATLAB gold matched VEMU output log",
            )
            first_patches = distill_session(root, session_dir=first.session_dir)
            review_patches(root, patch_dir=first_patches.patch_dir, approve=True)
            merge_patches(root, patch_dir=first_patches.patch_dir)

            source = root / "second_session.md"
            source.write_text(
                """# Second VEMU Error Check

Another task compared a VEMU output log against reference data.
It reports `max_abs_diff=1` and `bad_abs_gt_1=0`, so it should update
the existing comparison skilllet instead of creating a session-specific clone.
""",
                encoding="utf-8",
            )

            second = import_markdown_session(root, source)
            second_patches = distill_session(root, session_dir=second.session_dir)
            self.assertTrue(
                (second_patches.skilllets_dir / "matlab-gold-vemu-compare.md").exists()
            )
            suggestions = second_patches.merge_suggestions.read_text(encoding="utf-8")
            self.assertIn("will update existing `matlab-gold-vemu-compare`", suggestions)

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

    def test_chatgpt_share_html_to_markdown_from_next_data(self) -> None:
        payload = {
            "props": {
                "pageProps": {
                    "serverResponse": {
                        "data": {
                            "mapping": {
                                "a": {
                                    "message": {
                                        "author": {"role": "user"},
                                        "content": {"parts": ["今天突然想到一个小工具。"]},
                                    }
                                },
                                "b": {
                                    "message": {
                                        "author": {"role": "assistant"},
                                        "content": {"parts": ["可以先把它记成 idea，而不是 skill。"]},
                                    }
                                },
                            }
                        }
                    }
                }
            }
        }
        source = (
            "<html><head><title>Shared Chat</title></head><body>"
            f"<script id=\"__NEXT_DATA__\" type=\"application/json\">{json.dumps(payload)}</script>"
            "</body></html>"
        )

        markdown = chatgpt_share_to_markdown("https://chatgpt.com/share/example", source)
        self.assertIn("# Shared Chat", markdown)
        self.assertIn("## User", markdown)
        self.assertIn("今天突然想到一个小工具。", markdown)
        self.assertIn("## Assistant", markdown)
        self.assertIn("不是 skill", markdown)

    def test_chatgpt_share_html_to_markdown_from_react_router_stream(self) -> None:
        devalue_table = [
            {"_1": 2},
            "messages",
            [3, 14],
            {"_4": 5, "_9": 10},
            "author",
            {"_6": 7},
            "role",
            "user",
            "assistant",
            "content",
            {"_11": 12, "_13": 16},
            "content_type",
            "text",
            "parts",
            {"_4": 15, "_9": 17},
            {"_6": 8},
            [18],
            {"_11": 12, "_13": 20},
            "CloudRIC 这种对话应该能从分享链接里提取出来。",
            "code",
            [21],
            "可以沉淀成 research_note，而不是强行做成 skill。",
        ]
        source = (
            "<html><head><title>ChatGPT - CloudRIC能效提升分析</title></head><body>"
            "<script>"
            "window.__reactRouterContext.streamController.enqueue("
            f"{json.dumps(json.dumps(devalue_table, ensure_ascii=False), ensure_ascii=False)}"
            ");"
            "</script>"
            "</body></html>"
        )

        markdown = chatgpt_share_to_markdown(
            "https://chatgpt.com/share/stream-example",
            source,
        )
        self.assertIn("# ChatGPT - CloudRIC能效提升分析", markdown)
        self.assertIn("## User", markdown)
        self.assertIn("分享链接里提取出来", markdown)
        self.assertIn("## Assistant", markdown)
        self.assertIn("research_note", markdown)
        self.assertNotIn("code", markdown)

    def test_import_url_session_supports_file_url_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            html_file = Path(tmp) / "share.html"
            html_file.write_text(
                """<html><head><title>Daily Chat</title></head>
<body><main><p>灵感：把日常聊天里的想法留下来。</p>
<p>下一步：试试 VibeWiki import-url。</p></main></body></html>""",
                encoding="utf-8",
            )

            session = import_url_session(root, html_file.as_uri(), session_name="daily-chat")
            session_text = session.session_md.read_text(encoding="utf-8")
            raw_text = (session.session_dir / "raw_session.md").read_text(encoding="utf-8")
            self.assertIn("Daily Chat", session_text)
            self.assertIn("import-url", raw_text)
            self.assertTrue((session.session_dir / "raw_source.html").exists())
            self.assertIn("imported_url:", session.metadata_yaml.read_text(encoding="utf-8"))

            patches = distill_session(root, session_dir=session.session_dir)
            findings = patches.findings_index.read_text(encoding="utf-8")
            self.assertIn("Ideas", findings)
            skilllets = [
                path
                for path in patches.skilllets_dir.glob("*.md")
                if path.name != "index.md"
            ]
            self.assertEqual(skilllets, [])

    def test_html_to_markdown_fallback_keeps_readable_text(self) -> None:
        markdown = html_to_markdown(
            "https://example.com/chat",
            "<html><head><title>Plain Page</title></head><body><p>一个普通网页。</p></body></html>",
        )
        self.assertIn("# Plain Page", markdown)
        self.assertIn("一个普通网页。", markdown)

    def test_chatgpt_share_without_conversation_does_not_import_login_shell(self) -> None:
        markdown = html_to_markdown(
            "https://chatgpt.com/share/example",
            "<html><head><title>ChatGPT</title></head><body>Skip to content Log in</body></html>",
        )
        self.assertIn("No readable ChatGPT conversation text was found", markdown)
        self.assertNotIn("Skip to content", markdown)


if __name__ == "__main__":
    unittest.main()
