from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .capture import capture_session
from .distill import distill_session
from .import_markdown import import_markdown_session
from .import_url import import_url_session
from .merge import merge_patches
from .project import init_project
from .review import patch_summary, record_item_decision, review_patches
from .review_board import generate_review_board
from .review_plan import build_review_plan, format_review_plan_summary
from .review_ui import serve_review_ui
from .retrieval import answer_question, build_context_pack, format_search_results, search_memory
from .validate import default_skill_path, validate_skill_file


def _path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _read_text(value: str = "", file_path: str | None = None) -> str:
    if file_path:
        return Path(file_path).expanduser().read_text(encoding="utf-8")
    return value or ""


def _prompt(label: str, current: str = "") -> str:
    if current or not sys.stdin.isatty():
        return current
    print(f"{label}: ", end="", flush=True)
    return sys.stdin.readline().strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vibewiki",
        description="Turn AI coding sessions into reviewed project memory.",
    )
    parser.add_argument(
        "--project",
        default=".",
        help="Project root to operate on. Defaults to the current directory.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    init = subparsers.add_parser("init", help="Create VibeWiki memory structure.")
    init.add_argument("--force", action="store_true", help="Overwrite existing seed files.")

    capture = subparsers.add_parser("capture", help="Capture one coding session.")
    capture.add_argument("--session-name", default=None, help="Short name used in the session id.")
    capture.add_argument("--goal", default="", help="Session goal.")
    capture.add_argument("--outcome", default="", help="Final outcome.")
    capture.add_argument(
        "--command",
        dest="commands",
        action="append",
        default=[],
        help="Key command. Can be repeated.",
    )
    capture.add_argument("--tests", default="", help="Verification or test output.")
    capture.add_argument("--tests-file", default=None, help="Read verification output from a file.")
    capture.add_argument("--benchmark", default="", help="Benchmark output or summary.")
    capture.add_argument("--benchmark-file", default=None, help="Read benchmark output from a file.")
    capture.add_argument("--notes", default="", help="User notes.")
    capture.add_argument("--notes-file", default=None, help="Read user notes from a file.")
    capture.add_argument("--summary", default="", help="AI conversation summary.")
    capture.add_argument("--summary-file", default=None, help="Read AI summary from a file.")
    capture.add_argument(
        "--things-not-to-record",
        default="",
        help="Failed paths or sensitive details that should not enter project memory.",
    )
    capture.add_argument(
        "--things-not-to-record-file",
        default=None,
        help="Read things-not-to-record from a file.",
    )
    capture.add_argument(
        "--non-interactive",
        action="store_true",
        help="Do not ask follow-up questions in a TTY.",
    )

    distill = subparsers.add_parser("distill", help="Generate candidate memory patches.")
    distill.add_argument("--session-dir", default=None, help="Specific session directory to distill.")

    import_markdown = subparsers.add_parser(
        "import-markdown",
        help="Import an exported AI coding session Markdown file.",
    )
    import_markdown.add_argument("source", help="Markdown file to import.")
    import_markdown.add_argument("--session-name", default=None, help="Short name used in the session id.")
    import_markdown.add_argument("--goal", default="", help="Override detected session goal.")
    import_markdown.add_argument("--outcome", default="", help="Override detected final outcome.")
    import_markdown.add_argument(
        "--command",
        dest="commands",
        action="append",
        default=[],
        help="Add a key command. Can be repeated.",
    )
    import_markdown.add_argument("--tests", default="", help="Override detected verification notes.")
    import_markdown.add_argument("--benchmark", default="", help="Override detected benchmark notes.")
    import_markdown.add_argument("--notes", default="", help="User notes to attach to the import.")
    import_markdown.add_argument(
        "--things-not-to-record",
        default="",
        help="Failed paths or sensitive details that should not enter project memory.",
    )

    import_url = subparsers.add_parser(
        "import-url",
        help="Import a shared AI conversation URL, such as a ChatGPT share link.",
    )
    import_url.add_argument("url", help="Shared conversation URL to import.")
    import_url.add_argument("--session-name", default=None, help="Short name used in the session id.")
    import_url.add_argument("--goal", default="", help="Override detected session goal.")
    import_url.add_argument("--outcome", default="", help="Override detected final outcome.")
    import_url.add_argument(
        "--command",
        dest="commands",
        action="append",
        default=[],
        help="Add a key command. Can be repeated.",
    )
    import_url.add_argument("--tests", default="", help="Override detected verification notes.")
    import_url.add_argument("--benchmark", default="", help="Override detected benchmark notes.")
    import_url.add_argument("--notes", default="", help="User notes to attach to the import.")
    import_url.add_argument(
        "--things-not-to-record",
        default="",
        help="Failed paths or sensitive details that should not enter project memory.",
    )

    review = subparsers.add_parser("review", help="Inspect or approve candidate patches.")
    review.add_argument("--patch-dir", default=None, help="Specific patch directory to review.")
    review.add_argument("--approve", action="store_true", help="Mark the patch as human-approved.")
    review.add_argument("--notes", default="", help="Review notes.")

    review_item = subparsers.add_parser(
        "review-item",
        help="Record an item-level decision for a candidate finding or reusable unit.",
    )
    review_item.add_argument("--patch-dir", default=None, help="Specific patch directory to review.")
    review_item.add_argument("--item", required=True, help="Item path relative to the patch directory.")
    review_item.add_argument(
        "--decision",
        required=True,
        choices=["approve", "reject", "defer", "downgrade", "merge", "edit"],
        help="Decision for this candidate item.",
    )
    review_item.add_argument(
        "--target",
        default="",
        help="Target type or existing unit slug/path for downgrade or merge decisions.",
    )
    review_item.add_argument("--title", default="", help="Edited title to apply during merge.")
    review_item.add_argument("--summary", default="", help="Edited summary to apply during merge.")
    review_item.add_argument("--tags", default="", help="Comma-separated tags to record.")
    review_item.add_argument("--note", default="", help="Reviewer note for this item.")

    review_board = subparsers.add_parser(
        "review-board",
        help="Generate a local HTML review board for candidate patches.",
    )
    review_board.add_argument("--patch-dir", default=None, help="Specific patch directory to render.")
    review_board.add_argument("--output", default=None, help="HTML file to write.")

    review_plan = subparsers.add_parser(
        "review-plan",
        help="Generate a compact pre-review triage plan for candidate items.",
    )
    review_plan.add_argument("--patch-dir", default=None, help="Specific patch directory to triage.")
    review_plan.add_argument("--force", action="store_true", help="Rebuild even if the plan is current.")
    review_plan.add_argument(
        "--review-limit",
        type=int,
        default=8,
        help="Maximum unreviewed items shown by default. Defaults to 8.",
    )

    review_ui = subparsers.add_parser(
        "review-ui",
        help="Serve a clickable local review UI for candidate patches.",
    )
    review_ui.add_argument("--patch-dir", default=None, help="Specific patch directory to review.")
    review_ui.add_argument("--host", default="127.0.0.1", help="Host to bind. Defaults to 127.0.0.1.")
    review_ui.add_argument("--port", type=int, default=8765, help="Port to bind. Defaults to 8765.")

    merge = subparsers.add_parser("merge", help="Merge approved patches into project memory.")
    merge.add_argument("--patch-dir", default=None, help="Specific patch directory to merge.")
    merge.add_argument(
        "--force",
        action="store_true",
        help="Merge without requiring an approved review record.",
    )

    validate_skill = subparsers.add_parser(
        "validate-skill",
        help="Validate a Skill Patch quality gate.",
    )
    validate_skill.add_argument(
        "--path",
        default=None,
        help="Skill file to validate. Defaults to the latest patch skill_patch.md.",
    )
    validate_skill.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as failures.",
    )

    search = subparsers.add_parser("search", help="Search approved and candidate VibeWiki memory.")
    search.add_argument("query", help="Search query.")
    search.add_argument("--scope", choices=["approved", "candidate", "all"], default=None)
    search.add_argument("--max-items", type=int, default=None, help="Maximum results.")
    search.add_argument("--snippet-chars", type=int, default=None, help="Snippet size per result.")
    search.add_argument("--verbose", action="store_true", help="Show full matched chunk text.")
    search.add_argument(
        "--no-embeddings",
        action="store_true",
        help="Disable embedding retrieval even if configured.",
    )

    ask = subparsers.add_parser("ask", help="Ask a question against VibeWiki memory.")
    ask.add_argument("query", help="Question to answer.")
    ask.add_argument("--scope", choices=["approved", "candidate", "all"], default=None)
    ask.add_argument("--max-items", type=int, default=None, help="Maximum evidence items.")
    ask.add_argument("--verbose", action="store_true", help="Show longer evidence in draft mode.")
    ask.add_argument(
        "--no-embeddings",
        action="store_true",
        help="Disable embedding retrieval even if configured.",
    )

    context = subparsers.add_parser("context", help="Build a compact context pack for an AI agent.")
    context.add_argument("--for", dest="query", required=True, help="Task or question to retrieve for.")
    context.add_argument("--scope", choices=["approved", "candidate", "all"], default=None)
    context.add_argument("--max-items", type=int, default=None, help="Maximum context items.")
    context.add_argument("--max-chars", type=int, default=None, help="Maximum characters per item.")
    context.add_argument("--format", choices=["yaml", "json"], default="yaml")
    context.add_argument(
        "--no-embeddings",
        action="store_true",
        help="Disable embedding retrieval even if configured.",
    )

    return parser


def run(args: argparse.Namespace) -> int:
    project = _path(args.project)

    if args.subcommand == "init":
        created = init_project(project, force=args.force)
        if created:
            print("Created or refreshed:")
            for path in created:
                print(f"- {path}")
        else:
            print("VibeWiki workspace already exists. Use --force to refresh seed files.")
        return 0

    if args.subcommand == "capture":
        goal = args.goal
        outcome = args.outcome
        if not args.non_interactive:
            goal = _prompt("Session goal", goal)
            outcome = _prompt("Final outcome", outcome)
        paths = capture_session(
            project,
            goal=goal,
            outcome=outcome,
            commands=args.commands or [],
            tests=_read_text(args.tests, args.tests_file),
            benchmark=_read_text(args.benchmark, args.benchmark_file),
            notes=_read_text(args.notes, args.notes_file),
            ai_summary=_read_text(args.summary, args.summary_file),
            things_not_to_record=_read_text(
                args.things_not_to_record,
                args.things_not_to_record_file,
            ),
            session_name=args.session_name,
        )
        print(f"Captured session: {paths.session_dir}")
        print(f"- {paths.session_md}")
        print(f"- {paths.diff_patch}")
        print(f"- {paths.metadata_yaml}")
        return 0

    if args.subcommand == "distill":
        session_dir = _path(args.session_dir) if args.session_dir else None
        paths = distill_session(project, session_dir=session_dir)
        print(f"Generated patches: {paths.patch_dir}")
        print(f"- {paths.knowledge_patch}")
        print(f"- {paths.skill_patch}")
        print(f"- {paths.agent_rule_patch}")
        print(f"- {paths.questions}")
        print(f"- {paths.findings_index}")
        print(f"- {paths.merge_suggestions}")
        print(f"- {paths.skilllets_dir}")
        print(f"- {paths.prompt_patterns_dir}")
        print(f"- {paths.workflows_dir}")
        return 0

    if args.subcommand == "import-markdown":
        paths = import_markdown_session(
            project,
            _path(args.source),
            goal=args.goal,
            outcome=args.outcome,
            commands=args.commands or [],
            tests=args.tests,
            benchmark=args.benchmark,
            notes=args.notes,
            things_not_to_record=args.things_not_to_record,
            session_name=args.session_name,
        )
        print(f"Imported markdown session: {paths.session_dir}")
        print(f"- {paths.session_md}")
        print(f"- {paths.session_dir / 'raw_session.md'}")
        print(f"- {paths.diff_patch}")
        print(f"- {paths.metadata_yaml}")
        return 0

    if args.subcommand == "import-url":
        paths = import_url_session(
            project,
            args.url,
            goal=args.goal,
            outcome=args.outcome,
            commands=args.commands or [],
            tests=args.tests,
            benchmark=args.benchmark,
            notes=args.notes,
            things_not_to_record=args.things_not_to_record,
            session_name=args.session_name,
        )
        print(f"Imported URL session: {paths.session_dir}")
        print(f"- {paths.session_md}")
        print(f"- {paths.session_dir / 'raw_session.md'}")
        print(f"- {paths.session_dir / 'raw_source.html'}")
        print(f"- {paths.diff_patch}")
        print(f"- {paths.metadata_yaml}")
        return 0

    if args.subcommand == "review":
        patch_dir = _path(args.patch_dir) if args.patch_dir else None
        print(patch_summary(project, patch_dir))
        review_paths = review_patches(
            project,
            patch_dir=patch_dir,
            approve=args.approve,
            notes=args.notes,
        )
        decision = "approved" if args.approve else "needs_review"
        print(f"Review recorded ({decision}): {review_paths.review_file}")
        return 0

    if args.subcommand == "review-item":
        patch_dir = _path(args.patch_dir) if args.patch_dir else None
        decisions_file = record_item_decision(
            project,
            patch_dir=patch_dir,
            item=args.item,
            decision=args.decision,
            target=args.target,
            title=args.title,
            summary=args.summary,
            tags=args.tags,
            note=args.note,
        )
        print(f"Item review recorded: {decisions_file}")
        print(f"- item: {args.item}")
        print(f"- decision: {args.decision}")
        if args.target:
            print(f"- target: {args.target}")
        return 0

    if args.subcommand == "review-board":
        patch_dir = _path(args.patch_dir) if args.patch_dir else None
        output = _path(args.output) if args.output else None
        board = generate_review_board(project, patch_dir=patch_dir, output=output)
        print(f"Generated review board: {board}")
        return 0

    if args.subcommand == "review-plan":
        patch_dir = _path(args.patch_dir) if args.patch_dir else None
        plan = build_review_plan(
            project,
            patch_dir=patch_dir,
            force=args.force,
            review_limit=args.review_limit,
        )
        print(format_review_plan_summary(plan))
        return 0

    if args.subcommand == "review-ui":
        patch_dir = _path(args.patch_dir) if args.patch_dir else None
        serve_review_ui(project, patch_dir=patch_dir, host=args.host, port=args.port)
        return 0

    if args.subcommand == "merge":
        patch_dir = _path(args.patch_dir) if args.patch_dir else None
        changed = merge_patches(
            project,
            patch_dir=patch_dir,
            require_approved=not args.force,
        )
        if changed:
            print("Merged into:")
            for path in changed:
                print(f"- {path}")
        else:
            print("Nothing changed; these patches may already be merged.")
        return 0

    if args.subcommand == "validate-skill":
        skill_path = _path(args.path) if args.path else default_skill_path(project)
        report = validate_skill_file(skill_path)
        print(report.render())
        return 0 if report.ok(strict=args.strict) else 1

    if args.subcommand == "search":
        results = search_memory(
            project,
            args.query,
            scope=args.scope,
            max_items=args.max_items,
            snippet_chars=args.snippet_chars,
            use_embeddings=not args.no_embeddings,
        )
        print(format_search_results(results, verbose=args.verbose), end="")
        return 0

    if args.subcommand == "ask":
        print(
            answer_question(
                project,
                args.query,
                scope=args.scope,
                max_items=args.max_items,
                verbose=args.verbose,
                use_embeddings=not args.no_embeddings,
            ),
            end="",
        )
        return 0

    if args.subcommand == "context":
        print(
            build_context_pack(
                project,
                args.query,
                scope=args.scope,
                max_items=args.max_items,
                max_chars_per_item=args.max_chars,
                output_format=args.format,
                use_embeddings=not args.no_embeddings,
            ),
            end="",
        )
        return 0

    raise AssertionError(f"Unhandled command: {args.subcommand}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
