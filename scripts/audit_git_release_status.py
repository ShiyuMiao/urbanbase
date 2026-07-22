from __future__ import annotations

import argparse
import json
import locale
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PREFIX = "outputs_citylbm_voxel_china/"

ROOT_RELEASE_FILES = {
    ".gitignore",
    "README.md",
    "requirements.txt",
    "GITHUB_RELEASE_MANIFEST.md",
    "SOFTWARE_OPTIMIZATION_PLAN_VOXEL_CARVING.md",
    "CURRENT_PROGRESS_ZHONGSHAN_RELEASE_REPORT.md",
    "CityLBM_VoxCity_China_0p1m_RhinoVoxel_full_process.ipynb",
    "voxcity_demo (4).py",
}

RELEASE_SOURCE_PREFIXES = (
    "src/",
    "scripts/",
    "config/",
    "docs/",
    "notebooks/",
    "templates/",
)


def run_git(args: list[str]) -> str:
    proc = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        stderr = decode_git_output(proc.stderr).strip()
        stdout = decode_git_output(proc.stdout).strip()
        raise RuntimeError(stderr or stdout or f"git {' '.join(args)} failed")
    return decode_git_output(proc.stdout)


def decode_git_output(data: bytes) -> str:
    for encoding in ("utf-8", locale.getpreferredencoding(False)):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def parse_porcelain(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for raw_line in text.splitlines():
        if not raw_line:
            continue
        status = raw_line[:2]
        path = raw_line[3:] if len(raw_line) > 3 else ""
        entries.append({"status": status, "path": path})
    return entries


def is_release_source(path: str) -> bool:
    return path in ROOT_RELEASE_FILES or path.startswith(RELEASE_SOURCE_PREFIXES)


def path_starts_with(path: str, prefix: str) -> bool:
    return path.startswith(prefix) or path.startswith(f'"{prefix}')


def split_rename_path(path: str) -> tuple[str, str] | None:
    if " -> " not in path:
        return None
    before, after = path.split(" -> ", 1)
    return before, after


def classify(entries: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = {
        "release_source_changes": [],
        "tracked_output_changes": [],
        "ignored_runtime_outputs": [],
        "other_changes": [],
    }
    for entry in entries:
        path = entry["path"]
        status = entry["status"]
        if status == "!!":
            groups["ignored_runtime_outputs"].append(entry)
        elif path_starts_with(path, OUTPUT_PREFIX):
            groups["tracked_output_changes"].append(entry)
        elif is_release_source(path):
            groups["release_source_changes"].append(entry)
        else:
            groups["other_changes"].append(entry)
    return groups


def cleanup_plan(groups: dict[str, list[dict[str, str]]]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for entry in groups["tracked_output_changes"]:
        rename = split_rename_path(entry["path"])
        candidate: dict[str, Any] = {
            "status": entry["status"],
            "path": entry["path"],
            "action": "safe_to_untrack_candidate",
            "requires_manual_review": False,
        }
        if rename is not None:
            candidate["action"] = "manual_review_required"
            candidate["requires_manual_review"] = True
            candidate["renamed_from"] = rename[0]
            candidate["renamed_to"] = rename[1]
            candidate["note"] = "Rename entries need explicit review before removing either side from Git tracking."
        candidates.append(candidate)
    return {
        "candidate_count": len(candidates),
        "safety_note": "This is a dry-run cleanup plan. It does not delete files and does not run git rm --cached.",
        "candidates": candidates,
    }


def summarize(groups: dict[str, list[dict[str, str]]]) -> dict[str, Any]:
    tracked_outputs = groups["tracked_output_changes"]
    other_changes = groups["other_changes"]
    source_changes = groups["release_source_changes"]
    if tracked_outputs or other_changes:
        status = "attention_required"
    elif source_changes:
        status = "source_changes_only"
    else:
        status = "clean"
    return {
        "status": status,
        "counts": {name: len(items) for name, items in groups.items()},
        "recommendation": recommendation(status, groups),
    }


def recommendation(status: str, groups: dict[str, list[dict[str, str]]]) -> str:
    if status == "clean":
        return "Working tree has no visible release-relevant changes."
    if status == "source_changes_only":
        return "Review and commit release source changes after running the stability gate."
    if groups["tracked_output_changes"]:
        return (
            "Tracked generated outputs are mixed into git status. Decide separately whether to keep them, "
            "publish them as release assets, or remove them from tracking with an explicit cleanup commit."
        )
    return "Review uncategorized changes before preparing a release commit."


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Classify git status for a clean source release without modifying files.")
    parser.add_argument("--include-ignored", action="store_true", help="Also report ignored runtime-output entries.")
    parser.add_argument("--strict-clean-release", action="store_true", help="Exit non-zero when tracked output or uncategorized changes exist.")
    parser.add_argument("--cleanup-plan-json", type=Path, help="Write a dry-run JSON plan for tracked generated outputs.")
    args = parser.parse_args()

    status_args = ["status", "--porcelain"]
    if args.include_ignored:
        status_args.append("--ignored")
    entries = parse_porcelain(run_git(status_args))
    groups = classify(entries)
    summary = summarize(groups)
    result = {
        **summary,
        "project_root": str(PROJECT_ROOT),
        "groups": groups,
    }
    if args.cleanup_plan_json:
        plan = cleanup_plan(groups)
        args.cleanup_plan_json.parent.mkdir(parents=True, exist_ok=True)
        args.cleanup_plan_json.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        result["cleanup_plan_json"] = str(args.cleanup_plan_json)
        result["cleanup_plan_candidate_count"] = plan["candidate_count"]
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.strict_clean_release and summary["status"] == "attention_required":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
