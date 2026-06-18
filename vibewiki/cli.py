from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .capture import capture_session
from .distill import distill_session
from .merge import merge_patches
from .project import init_project
from .review import patch_summary, review_patches
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

    review = subparsers.add_parser("review", help="Inspect or approve candidate patches.")
    review.add_argument("--patch-dir", default=None, help="Specific patch directory to review.")
    review.add_argument("--approve", action="store_true", help="Mark the patch as human-approved.")
    review.add_argument("--notes", default="", help="Review notes.")

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
