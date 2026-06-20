from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vibewiki.capture import capture_session
from vibewiki.distill import distill_session
from vibewiki.import_markdown import extract_hint_lines, import_markdown_session
from vibewiki.import_url import chatgpt_share_to_markdown, html_to_markdown, import_url_session
from vibewiki.merge import merge_patches
from vibewiki.project import init_project
from vibewiki.review import (
    read_item_decisions,
    record_item_decision,
    review_patches,
    update_item_body,
)
from vibewiki.review_board import generate_review_board
from vibewiki.review_plan import build_review_plan
from vibewiki.review_ui import (
    _markdown_to_html,
    render_review_ui,
    revise_candidate_markdown,
    translate_candidate_markdown,
)
from vibewiki.retrieval import answer_question, build_context_pack, search_memory
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
            self.assertIn(".vibewiki/cache/", (root / ".gitignore").read_text(encoding="utf-8"))
            config_text = (root / ".vibewiki" / "config.yaml").read_text(encoding="utf-8")
            self.assertIn("mode: bilingual", config_text)
            self.assertIn("primary: zh", config_text)
            self.assertIn("translation:", config_text)
            self.assertIn("provider_env: VIBEWIKI_TRANSLATION_PROVIDER", config_text)

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

    def test_distill_product_design_discussion_into_typed_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "vibewiki_design_session.md"
            source.write_text(
                """# VibeWiki Product Design Discussion

## Current Assessment

VibeWiki is a usable MVP, but product-design conversations are under-distilled.

## Key Innovation

- Review-first promotion keeps generated memory candidate until a human approves it.

## High Priority Improvements

- Add product/research conversation extraction for decisions, assumptions, tradeoffs, todos, issues, ideas, open questions, and roadmap directions.
- Add item-level review decisions before merge.

## Known Issues

- Product-design conversations are under-distilled and miss roadmap tradeoffs.

## Ideas

- Keep memory units smaller than a session-sized skill.

## Directions

- Position VibeWiki as a trusted memory compiler for AI conversations.

Example command mention: `vibewiki ask "what changed?"`
""",
                encoding="utf-8",
            )

            session = import_markdown_session(root, source)
            patches = distill_session(root, session_dir=session.session_dir)
            findings_index = patches.findings_index.read_text(encoding="utf-8")

            self.assertIn("Add product/research conversation extraction", findings_index)
            self.assertIn("Add item-level review decisions before merge", findings_index)
            self.assertIn(
                "Product-design conversations are under-distilled and miss roadmap tradeoffs",
                findings_index,
            )
            self.assertIn("Keep memory units smaller than a session-sized skill", findings_index)
            self.assertIn(
                "Position VibeWiki as a trusted memory compiler for AI conversations",
                findings_index,
            )
            self.assertNotIn("Imported from Markdown source", findings_index)
            self.assertTrue(any(patches.findings_dir.glob("todo__add-product-research*.md")))
            self.assertTrue(any(patches.findings_dir.glob("issue__product-design*.md")))
            self.assertTrue(any(patches.findings_dir.glob("idea__keep-memory*.md")))
            self.assertTrue(any(patches.findings_dir.glob("direction__position-vibewiki*.md")))
            generated_skilllets = [
                path for path in patches.skilllets_dir.glob("*.md") if path.name != "index.md"
            ]
            self.assertEqual(generated_skilllets, [])

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

    def test_review_board_renders_patch_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "review_session.md"
            source.write_text(
                """# MATLAB VEMU Compare Review

We compared a VEMU output log against MATLAB gold.
The check reported `max_abs_diff=0` and `bad_abs_gt_1=0`.

```bash
python3 compare_outputs.py
```
""",
                encoding="utf-8",
            )

            session = import_markdown_session(root, source)
            patches = distill_session(root, session_dir=session.session_dir)
            board = generate_review_board(root, patch_dir=patches.patch_dir)

            self.assertTrue(board.exists())
            html = board.read_text(encoding="utf-8")
            self.assertIn("Review Board", html)
            self.assertIn("MATLAB VEMU Compare Review", html)
            self.assertIn("Findings", html)
            self.assertIn("Composable Units", html)
            self.assertIn("matlab-gold-vemu-compare", html)
            self.assertIn("vibewiki --project", html)
            self.assertIn("review --patch-dir", html)
            self.assertIn("review-item", html)
            self.assertIn("merge --patch-dir", html)

            ui_html = render_review_ui(root, patch_dir=patches.patch_dir)
            self.assertIn("VibeWiki 审核", ui_html)
            self.assertIn('data-en="VibeWiki Review"', ui_html)
            self.assertIn('data-lang-choice="zh"', ui_html)
            self.assertIn('data-lang-choice="en"', ui_html)
            self.assertIn(">提交<", ui_html)
            self.assertIn(">不提交<", ui_html)
            self.assertIn("预审整理", ui_html)
            self.assertIn("显示低优先级", ui_html)
            self.assertIn("显示建议不提交", ui_html)
            self.assertIn('data-plan-group="review_now"', ui_html)
            self.assertIn('action="/item-action"', ui_html)
            self.assertIn('name="action" value="approve"', ui_html)
            self.assertIn('name="action" value="reject"', ui_html)
            self.assertIn('name="action" value="revise"', ui_html)
            self.assertIn('name="action" value="translate"', ui_html)
            self.assertIn('name="target_language"', ui_html)
            self.assertIn("生成翻译预览", ui_html)
            self.assertIn("隐藏已审", ui_html)
            self.assertIn("编辑 Markdown 或让 LLM 修改", ui_html)
            self.assertIn("让 LLM 生成修订稿", ui_html)
            self.assertIn('class="preview"', ui_html)
            self.assertIn("<h1>", ui_html)
            self.assertIn('textarea name="body"', ui_html)
            self.assertIn('textarea name="instruction"', ui_html)
            self.assertIn("setTimeout", ui_html)
            self.assertIn("matlab-gold-vemu-compare", ui_html)
            self.assertNotIn("Approve / 批准", ui_html)
            self.assertNotIn("目标：knowledge", ui_html)
            self.assertNotIn("批量备注", ui_html)

    def test_review_plan_triages_raw_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)
            patch_dir = root / ".vibewiki" / "patches" / "triage-session"
            findings = patch_dir / "findings"
            skilllets = patch_dir / "skilllets"
            findings.mkdir(parents=True)
            skilllets.mkdir(parents=True)
            (findings / "issue__outcome.md").write_text(
                """# Issue: Outcome

Status: candidate
Type: issue
Session: triage-session

## Summary

Candidate issue extracted from a product, research, or daily discussion: Outcome:
VibeWiki is now a usable MVP but not yet a mature open-source product.

## Follow Up

Review whether this discussion section should be promoted, edited, merged, or discarded.
""",
                encoding="utf-8",
            )
            (findings / "todo__add-review-plan.md").write_text(
                """# Todo: Add Review Plan

Status: candidate
Type: todo
Session: triage-session

## Summary

Add pre-review triage so humans review fewer candidates by default.
""",
                encoding="utf-8",
            )
            (skilllets / "review-queue-triage.md").write_text(
                """# Review Queue Triage

Status: candidate
Kind: skilllet

## Summary

Use a review plan before showing raw candidates to humans.
""",
                encoding="utf-8",
            )

            plan = build_review_plan(root, patch_dir=patch_dir, force=True)

            self.assertTrue(plan.path.exists())
            self.assertEqual(plan.payload["summary"]["raw_items"], 3)
            self.assertEqual(plan.items["findings/issue__outcome.md"].group, "suggested_discard")
            self.assertEqual(plan.items["findings/todo__add-review-plan.md"].group, "review_now")
            self.assertEqual(plan.items["skilllets/review-queue-triage.md"].risk, "high")

    def test_review_ui_markdown_preview_is_rendered_and_escaped(self) -> None:
        rendered = _markdown_to_html(
            """# Candidate Title

Status: candidate

- keep `inline code`
- escape <script>alert(1)</script>

```bash
echo "# this stays code"
```
""",
        )

        self.assertIn("<h1>Candidate Title</h1>", rendered)
        self.assertIn("<ul>", rendered)
        self.assertIn("<code>inline code</code>", rendered)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered)
        self.assertIn("echo &quot;# this stays code&quot;", rendered)
        self.assertNotIn("<script>", rendered)

    def test_review_ui_llm_revision_uses_configured_chat_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)
            with patch.dict(os.environ, {"VIBEWIKI_LLM_API_KEY": "token"}, clear=True):
                with patch(
                    "vibewiki.review_ui.chat_completion",
                    return_value="```markdown\n# Revised Candidate\n\nStatus: candidate\n```",
                ) as mocked:
                    revised = revise_candidate_markdown(
                        root,
                        body="# Candidate\n\nStatus: candidate\n",
                        instruction="Make it shorter.",
                    )

            self.assertEqual(revised, "# Revised Candidate\n\nStatus: candidate\n")
            self.assertTrue(mocked.called)

    def test_review_ui_translation_uses_libretranslate_and_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)
            body = "# Candidate\n\nKeep `VEMU` and `TARGET_DAG` unchanged.\n"
            env = {
                "VIBEWIKI_TRANSLATION_PROVIDER": "libretranslate",
                "VIBEWIKI_TRANSLATION_BASE_URL": "http://translate.local",
            }
            with patch.dict(os.environ, env, clear=True):
                with patch(
                    "vibewiki.translation._post_libretranslate",
                    return_value="# 候选\n\n保持 VIBEWIKI_PLACEHOLDER_0 和 VIBEWIKI_PLACEHOLDER_1 不变。",
                ) as mocked:
                    translated = translate_candidate_markdown(root, body=body, target_language="zh")

                with patch(
                    "vibewiki.translation._post_libretranslate",
                    side_effect=AssertionError("translation should come from cache"),
                ):
                    cached = translate_candidate_markdown(root, body=body, target_language="zh")

            self.assertEqual(translated, "# 候选\n\n保持 `VEMU` 和 `TARGET_DAG` 不变。\n")
            self.assertEqual(cached, translated)
            self.assertEqual(mocked.call_count, 1)
            self.assertEqual(mocked.call_args.kwargs["target_language"], "zh")
            cache_dir = root / ".vibewiki" / "cache" / "translations"
            self.assertTrue(any(cache_dir.glob("*.md")))
            self.assertTrue(any(cache_dir.glob("*.json")))

    def test_review_ui_translation_does_not_use_llm_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)
            with patch.dict(os.environ, {"VIBEWIKI_LLM_API_KEY": "token"}, clear=True):
                with patch("importlib.util.find_spec", return_value=None):
                    with patch(
                        "vibewiki.translation.chat_completion",
                        side_effect=AssertionError("LLM should be explicit for translation"),
                    ):
                        with self.assertRaisesRegex(RuntimeError, "No free translation provider"):
                            translate_candidate_markdown(
                                root,
                                body="# Candidate\n\nTranslate me.\n",
                                target_language="zh",
                            )

    def test_item_level_review_decisions_affect_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "item_review_session.md"
            source.write_text(
                """# Item Level Review

We need a MATLAB Agent task package from `vemu_dag_summary.json`.
The remote worker must produce `run_vemu_gold.m` and `config_schema.json`.

Windows SSH note: the user is in Administrators, so OpenSSH reads
`administrators_authorized_keys` under the `Match Group administrators` rule.
`sshpass` is only for first login.

MATLAB reference: use `nrSymbolModulate` and `nrSymbolDemodulate`.
BAS `char` values are signed int8 byte patterns: `255 -> -1`.
The C build has `-fno-signed-char`, so convert explicitly.

Generated cases live in `generated_bas`, then materialize one `TARGET_DAG`
per case and compare `DAGRet_demod.log`.
For F5 set `VENUSROW=128` and `VENUSLANE=16` in `config.mk`.

Verification reports `max_abs_diff=0`, `bad_abs_gt_1=0`, and MATLAB gold matched.
""",
                encoding="utf-8",
            )

            session = import_markdown_session(root, source)
            patches = distill_session(root, session_dir=session.session_dir)
            editable_item = "skilllets/matlab-gold-vemu-compare.md"
            edited_body = """# MATLAB Gold VEMU Compare

Status: candidate
Kind: skilllet

## Summary

Reviewer edited this candidate directly in the review UI.
"""
            edited_path = update_item_body(
                root,
                patch_dir=patches.patch_dir,
                item=editable_item,
                body=edited_body,
            )
            self.assertEqual(edited_path, patches.patch_dir / editable_item)
            self.assertIn("Reviewer edited", edited_path.read_text(encoding="utf-8"))

            with self.assertRaises(ValueError):
                update_item_body(
                    root,
                    patch_dir=patches.patch_dir,
                    item="../escape.md",
                    body="nope",
                )

            record_item_decision(
                root,
                patch_dir=patches.patch_dir,
                item="prompt_patterns/remote-matlab-agent-task-package.md",
                decision="approve",
                note="Good reusable prompt pattern.",
            )
            record_item_decision(
                root,
                patch_dir=patches.patch_dir,
                item="skilllets/windows-ssh-key-for-admin-worker.md",
                decision="reject",
                note="Do not keep Windows SSH guidance for this project.",
            )
            record_item_decision(
                root,
                patch_dir=patches.patch_dir,
                item="workflows/materialize-vemu-replay-cases.md",
                decision="defer",
                note="Needs a better example before merge.",
            )
            record_item_decision(
                root,
                patch_dir=patches.patch_dir,
                item="skilllets/bas-char-signed-int8.md",
                decision="downgrade",
                target="knowledge",
                title="BAS Signed Int8 Knowledge",
                summary="Keep this as knowledge until it becomes a reusable skilllet.",
            )
            record_item_decision(
                root,
                patch_dir=patches.patch_dir,
                item="skilllets/matlab-gold-vemu-compare.md",
                decision="merge",
                target="existing-compare",
                title="Existing Compare Skill",
                summary="Use this edited comparison summary.",
            )
            record_item_decision(
                root,
                patch_dir=patches.patch_dir,
                item="skilllets/vemu-f5-venus-128x16.md",
                decision="edit",
                title="Reviewed VEMU F5 Flow",
                summary="Edited F5 summary.",
            )

            decisions = read_item_decisions(root, patches.session_id)
            self.assertEqual(len(decisions), 6)

            board = generate_review_board(root, patch_dir=patches.patch_dir)
            board_html = board.read_text(encoding="utf-8")
            self.assertIn("decision: merge", board_html)
            self.assertIn("existing-compare", board_html)

            review_patches(root, patch_dir=patches.patch_dir, approve=True)
            merge_patches(root, patch_dir=patches.patch_dir)

            self.assertFalse(
                (root / "skills" / "skilllets" / "windows-ssh-key-for-admin-worker.md").exists()
            )
            self.assertFalse(
                (root / "skills" / "workflows" / "materialize-vemu-replay-cases.md").exists()
            )
            self.assertFalse((root / "skills" / "skilllets" / "bas-char-signed-int8.md").exists())
            self.assertIn(
                "BAS Signed Int8 Knowledge",
                (root / "docs" / "wiki" / "knowledge.md").read_text(encoding="utf-8"),
            )
            existing = root / "skills" / "skilllets" / "existing-compare.md"
            self.assertTrue(existing.exists())
            self.assertIn("Existing Compare Skill", existing.read_text(encoding="utf-8"))
            self.assertIn("Use this edited comparison summary.", existing.read_text(encoding="utf-8"))
            reviewed = root / "skills" / "skilllets" / "vemu-f5-venus-128x16.md"
            self.assertTrue(reviewed.exists())
            self.assertIn("Reviewed VEMU F5 Flow", reviewed.read_text(encoding="utf-8"))
            self.assertIn("Edited F5 summary.", reviewed.read_text(encoding="utf-8"))

    def test_search_reads_approved_and_candidate_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)
            (root / "docs" / "wiki" / "research_notes.md").write_text(
                """# Research Notes

## CloudRIC Baseline

CloudRIC is not an apples-to-apples comparison against traditional RAN base stations.
""",
                encoding="utf-8",
            )
            finding_dir = root / ".vibewiki" / "patches" / "draft-session" / "findings"
            finding_dir.mkdir(parents=True)
            (finding_dir / "research_note__cloudric-energy.md").write_text(
                """# Research Note: CloudRIC Energy Caveat

Status: candidate
Type: research_note
Session: draft-session

## Summary

CloudRIC energy efficiency evidence is useful, but its baseline is an internal vRAN deployment.
""",
                encoding="utf-8",
            )

            results = search_memory(root, "CloudRIC traditional RAN", use_embeddings=False)

            self.assertTrue(any(result.chunk.status == "approved" for result in results))
            self.assertTrue(any(result.chunk.status == "candidate" for result in results))
            self.assertIn("CloudRIC", results[0].snippet)

    def test_context_pack_outputs_json_for_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)
            (root / "skills" / "skilllets" / "vemu-f5.md").write_text(
                """# Skilllet: VEMU F5

Status: approved
Kind: skilllet

## Steps

Set `TARGET_DAG`, build DSL, then run the emulator.
""",
                encoding="utf-8",
            )

            rendered = build_context_pack(
                root,
                "how to run VEMU F5 TARGET_DAG",
                output_format="json",
                use_embeddings=False,
            )
            payload = json.loads(rendered)

            self.assertEqual(payload["query"], "how to run VEMU F5 TARGET_DAG")
            self.assertTrue(payload["items"])
            self.assertEqual(payload["items"][0]["status"], "approved")
            self.assertIn("TARGET_DAG", payload["items"][0]["text"])

    def test_ask_without_llm_returns_retrieval_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)
            (root / "docs" / "wiki" / "knowledge.md").write_text(
                """# Knowledge

## VCMXMUL

VCMXMUL Gauss form is not bit-exact for fixed-point OFDM.
""",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                answer = answer_question(root, "VCMXMUL OFDM bit exact?", use_embeddings=False)

            self.assertIn("Answer Draft", answer)
            self.assertIn("VCMXMUL", answer)
            self.assertIn("docs/wiki/knowledge.md", answer)

    def test_embedding_search_writes_local_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)
            (root / "docs" / "wiki" / "knowledge.md").write_text(
                """# Knowledge

## Resource Pooling

Heterogeneous accelerator pooling improves baseband scheduling.
""",
                encoding="utf-8",
            )

            def fake_embeddings(_base_url: str, _api_key: str, _model: str, inputs: list[str]) -> list[list[float]]:
                vectors: list[list[float]] = []
                for value in inputs:
                    if "semantic query" in value or "Heterogeneous accelerator" in value:
                        vectors.append([1.0, 0.0])
                    else:
                        vectors.append([0.0, 1.0])
                return vectors

            env = {
                "VIBEWIKI_EMBEDDING_BASE_URL": "http://embedding.local/v1",
                "VIBEWIKI_EMBEDDING_MODEL": "fake-embedding",
            }
            with patch.dict(os.environ, env, clear=True):
                with patch("vibewiki.retrieval._post_embeddings", side_effect=fake_embeddings):
                    results = search_memory(root, "semantic query", use_embeddings=True)

            self.assertTrue(results)
            self.assertGreater(results[0].embedding_score or 0, 0.9)
            cache = root / ".vibewiki" / "cache" / "embeddings" / "index.jsonl"
            self.assertTrue(cache.exists())
            self.assertIn("fake-embedding", cache.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
