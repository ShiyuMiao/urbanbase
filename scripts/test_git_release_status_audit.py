from __future__ import annotations

import json

from audit_git_release_status import classify, cleanup_plan, decode_git_output, parse_porcelain, summarize


def main() -> None:
    porcelain = "\n".join(
        [
            " M README.md",
            "?? scripts/audit_git_release_status.py",
            "R  outputs_citylbm_voxel_china/01_raw/osm_overpass_combined_raw.json -> outputs_citylbm_voxel_china/01_raw/legacy_osm_overpass_combined_raw.json",
            " M outputs_citylbm_voxel_china/02_gis/aoi_boundary.gpkg",
            " M outputs_citylbm_voxel_china/11_docs/完整流程详细介绍.md",
            ' M "outputs_citylbm_voxel_china/11_docs/\\345\\256\\214\\346\\225\\264.md"',
            "!! outputs_citylbm_voxel_china/_smoke_tiny_e2e_20260713/",
            "?? experimental_notes.tmp",
        ]
    )
    entries = parse_porcelain(porcelain)
    groups = classify(entries)
    summary = summarize(groups)
    assert decode_git_output("完整流程详细介绍.md".encode("utf-8")) == "完整流程详细介绍.md"
    assert decode_git_output("完整流程详细介绍.md".encode("gbk")) == "完整流程详细介绍.md"

    expected_counts = {
        "release_source_changes": 2,
        "tracked_output_changes": 4,
        "ignored_runtime_outputs": 1,
        "other_changes": 1,
    }
    plan = cleanup_plan(groups)
    assert summary["counts"] == expected_counts, summary
    assert summary["status"] == "attention_required", summary
    tracked_paths = [item["path"] for item in groups["tracked_output_changes"]]
    assert any(path.startswith('"outputs_citylbm_voxel_china/') for path in tracked_paths), groups
    assert any(path.endswith("完整流程详细介绍.md") for path in tracked_paths), groups
    assert "Tracked generated outputs" in summary["recommendation"], summary
    assert plan["candidate_count"] == 4, plan
    assert "git rm --cached" in plan["safety_note"], plan
    assert plan["candidates"][0]["action"] == "manual_review_required", plan
    assert plan["candidates"][0]["requires_manual_review"] is True, plan
    assert plan["candidates"][0]["renamed_from"].endswith("osm_overpass_combined_raw.json"), plan
    assert plan["candidates"][0]["renamed_to"].endswith("legacy_osm_overpass_combined_raw.json"), plan
    assert plan["candidates"][1]["action"] == "safe_to_untrack_candidate", plan
    assert plan["candidates"][1]["requires_manual_review"] is False, plan
    assert any(candidate["path"].endswith("完整流程详细介绍.md") for candidate in plan["candidates"]), plan

    print(
        json.dumps(
            {
                "status": "success",
                "counts": summary["counts"],
                "classification_status": summary["status"],
                "cleanup_candidate_count": plan["candidate_count"],
            },
            ensure_ascii=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
