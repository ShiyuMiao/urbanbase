from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SITE = "outputs_citylbm_voxel_china/dalian_dlut_west_library"


def existing_files_under(rel_dir: str, patterns: tuple[str, ...]) -> list[str]:
    root = PROJECT_ROOT / rel_dir
    if not root.exists():
        return []
    files: list[str] = []
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            if path.is_file() and "__pycache__" not in path.parts and ".ipynb_checkpoints" not in path.parts:
                files.append(path.relative_to(PROJECT_ROOT).as_posix())
    return files


ROOT_SOURCE_FILES = [
    ".gitignore",
    "README.md",
    "requirements.txt",
    "GITHUB_RELEASE_MANIFEST.md",
    "SOFTWARE_OPTIMIZATION_PLAN_VOXEL_CARVING.md",
    "CURRENT_PROGRESS_ZHONGSHAN_RELEASE_REPORT.md",
    "CityLBM_VoxCity_China_0p1m_RhinoVoxel_full_process.ipynb",
    "voxcity_demo (4).py",
]

SOURCE_FILES = sorted(
    set(
        ROOT_SOURCE_FILES
        + existing_files_under("src", ("**/*.py",))
        + existing_files_under("scripts", ("*.py",))
        + existing_files_under("config", ("**/*.json",))
        + existing_files_under("docs", ("**/*.md",))
        + existing_files_under("notebooks", ("**/*.ipynb",))
        + existing_files_under("templates", ("**/*",))
        + existing_files_under("10_figures_tables/versioned_screenshots", ("*.png",))
    )
)

SMALL_EXAMPLE_FILES = [
    "05_rhino/final_city_voxel_1m_metadata.json",
    "05_rhino/final_city_voxel_1m_layers.csv",
    "05_rhino/final_city_voxel_1m_object_mapping.csv",
    "06_tables/basic_site_statistics.json",
    "06_tables/basic_site_statistics.csv",
    "06_tables/layer_summary_statistics.csv",
    "06_tables/layer_element_statistics.csv",
    "06_tables/scene_classification_alcc_lcz.json",
    "06_tables/scene_classification_metrics.csv",
    "06_tables/scene_morphology_lcz_formula_notes.md",
    "06_tables/vegetation_layer_quality_summary.json",
    "06_tables/esa_worldcover_landcover_metadata.json",
    "08_morphology/grid_250m_index.csv",
    "08_morphology/grid_prepare_summary.json",
    "08_morphology/morphology_indicator_schema.json",
    "08_morphology/morphology_indicators_250m.csv",
    "09_lcz/lcz_classification_250m.csv",
    "09_lcz/lcz_classification_summary.json",
    "14_heat_wind_risk/heat_wind_compound_risk_250m.csv",
    "14_heat_wind_risk/heat_wind_compound_risk_summary.json",
    "15_typical_blocks/typical_blocks_for_citylbm.csv",
    "15_typical_blocks/typical_blocks_summary.json",
    "07_audit/real_data_source_check.json",
    "07_audit/data_quality_audit.csv",
    "07_audit/data_quality_audit.json",
    "10_figures/dalian_dlut_west_library_voxel_model_review.png",
    "12_logs/final_execution_report.json",
    "12_logs/site_output_qa.json",
    "12_logs/site_model_summary.json",
]

LARGE_ASSET_FILES = [
    "04_voxels/sparse_voxels.csv",
]

ROOT_LARGE_ASSET_FILES = [
    "outputs_citylbm_voxel_china/01_raw/ESA_WorldCover_10m_2021_v200_N36E120_Map.tif",
]


def rel(path: Path) -> str:
    return path.as_posix()


def copy_relative(src_rel: str, target_root: Path, required: bool, copied: list[dict[str, Any]], missing: list[str]) -> None:
    src = PROJECT_ROOT / src_rel
    if not src.exists():
        if required:
            missing.append(src_rel)
        return
    dst = target_root / src_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    copied.append({"path": rel(src_rel_path(dst, target_root)), "bytes": dst.stat().st_size})


def src_rel_path(path: Path, root: Path) -> Path:
    return path.relative_to(root)


def site_large_asset_files(site_root: str) -> list[str]:
    assets = list(LARGE_ASSET_FILES)
    metadata_path = PROJECT_ROOT / site_root / "05_rhino" / "final_city_voxel_1m_metadata.json"
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            rhino_file = Path(str(metadata.get("file", "")))
            if rhino_file.name:
                assets.insert(0, f"05_rhino/{rhino_file.name}")
        except (OSError, json.JSONDecodeError):
            assets.insert(0, "05_rhino/final_city_voxel_1m.3dm")
    else:
        assets.insert(0, "05_rhino/final_city_voxel_1m.3dm")
    deduped: list[str] = []
    for asset in assets:
        if asset not in deduped:
            deduped.append(asset)
    return deduped


def write_release_notes(target_root: Path, site_root: str, include_large_assets: bool, copied: list[dict[str, Any]]) -> None:
    total_mb = sum(item["bytes"] for item in copied) / 1024 / 1024
    notes = [
        "# VoxCity Open Streetview Facade - DUT Library Source Release",
        "",
        f"Generated at: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "This folder is a clean release staging copy generated from the working tree.",
        "It intentionally uses a whitelist so legacy outputs and runtime caches are not mixed into the GitHub source release.",
        "",
        "## Contents",
        "",
        "- Source code, command-line runners, QA tools, and stability tests.",
        "- Project README, requirements, optimization plan, progress report, and release manifest.",
        "- LCZ/morphology configuration, documentation, templates, and sequential notebooks.",
        "- DUT west-campus library QA/statistics files, morphology/LCZ/risk tables, and review screenshot.",
        "",
        "## Excluded From Normal Git",
        "",
        "Large model assets should be uploaded with Git LFS or GitHub Release assets:",
        "",
        "- Rhino `.3dm` model",
        "- Sparse voxel CSV",
        "- ESA WorldCover GeoTIFF",
        "",
        f"Large assets included in this staging folder: `{include_large_assets}`",
        f"Example site root: `{site_root}`",
        f"Copied files: `{len(copied)}`",
        f"Total copied size: `{total_mb:.2f} MB`",
        "",
        "## Minimum Verification",
        "",
        "Run these commands in the original repository before publishing:",
        "",
        "```powershell",
        "python scripts\\test_release_staging_integrity.py",
        "python scripts\\run_stability_checks.py --timeout-s 900 --strict-worldcover-coverage --include-tiny-e2e --include-multi-site-e2e --include-cross-china-e2e --strict-cross-china-real-data",
        "python scripts\\qa_site_output.py --output-root outputs_citylbm_voxel_china\\dalian_dlut_west_library --min-buildings 1 --min-green-features 1 --min-dem-relief-m 1.0 --expected-lat 38.8831553 --expected-lon 121.5120457 --expected-aoi-width-m 500 --expected-voxel-size-m 1.0 --require-real-data-sources",
        "```",
        "",
    ]
    (target_root / "RELEASE_NOTES.md").write_text("\n".join(notes), encoding="utf-8")


def prepare(target_root: Path, site_root: str, include_large_assets: bool) -> dict[str, Any]:
    if target_root.exists() and any(target_root.iterdir()):
        raise FileExistsError(f"target directory already exists and is not empty: {target_root}")

    copied: list[dict[str, Any]] = []
    missing: list[str] = []

    for src_rel in SOURCE_FILES:
        copy_relative(src_rel, target_root, required=True, copied=copied, missing=missing)

    for site_rel in SMALL_EXAMPLE_FILES:
        copy_relative(f"{site_root}/{site_rel}", target_root, required=True, copied=copied, missing=missing)

    if include_large_assets:
        for site_rel in site_large_asset_files(site_root):
            copy_relative(f"{site_root}/{site_rel}", target_root / "_large_assets", required=True, copied=copied, missing=missing)
        for src_rel in ROOT_LARGE_ASSET_FILES:
            copy_relative(src_rel, target_root / "_large_assets", required=True, copied=copied, missing=missing)

    if missing:
        raise FileNotFoundError("missing required release files: " + ", ".join(missing))

    write_release_notes(target_root, site_root, include_large_assets, copied)
    manifest = {
        "status": "prepared",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "target_root": str(target_root),
        "site_root": site_root,
        "include_large_assets": include_large_assets,
        "file_count": len(copied),
        "total_bytes": sum(item["bytes"] for item in copied),
        "copied": copied,
    }
    (target_root / "RELEASE_CONTENTS.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a clean GitHub release staging folder from the current working tree.")
    parser.add_argument(
        "--target",
        type=Path,
        default=PROJECT_ROOT / "_release" / "voxcity-open-streetview-facade-dut-library_source",
        help="Empty target directory.",
    )
    parser.add_argument("--site-root", default=DEFAULT_SITE, help="Example site output root to include.")
    parser.add_argument("--include-large-assets", action="store_true", help="Also copy large Rhino/voxel/GeoTIFF assets into _large_assets.")
    args = parser.parse_args()

    try:
        manifest = prepare(args.target, args.site_root.replace("\\", "/"), args.include_large_assets)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(1)

    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
