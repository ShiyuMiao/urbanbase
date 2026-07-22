from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from plan_worldcover_tiles import ManifestSite, plan_worldcover_tiles  # noqa: E402


def assert_manifest() -> dict[str, Any]:
    output_root = PROJECT_ROOT / "outputs_citylbm_voxel_china" / "_worldcover_manifest_tests"
    raw_dir = output_root / "01_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    fake_missing_tile = raw_dir / "ESA_WorldCover_10m_2021_v200_N24E102_Map.tif"
    fake_missing_tile.write_bytes(b"incomplete worldcover tile")
    dalian_tile = PROJECT_ROOT / "outputs_citylbm_voxel_china" / "01_raw" / "ESA_WorldCover_10m_2021_v200_N36E120_Map.tif"
    expected_sizes = {
        "ESA_WorldCover_10m_2021_v200_N36E120_Map.tif": dalian_tile.stat().st_size if dalian_tile.exists() else None,
        "ESA_WorldCover_10m_2021_v200_N24E102_Map.tif": 123456,
    }
    sites = [
        ManifestSite("dalian_dlut_west_library", 38.8831553, 121.5120457, 250.0),
        ManifestSite("kunming_missing_probe", 25.0389, 102.7183, 250.0),
    ]
    report = plan_worldcover_tiles(sites, "", str(output_root), remote_size_lookup=lambda tile: expected_sizes.get(tile))
    errors: list[str] = []

    site_by_name = {site["site_name"]: site for site in report.get("sites", [])}
    dalian = site_by_name.get("dalian_dlut_west_library", {})
    missing_site = site_by_name.get("kunming_missing_probe", {})
    dalian_tiles = {tile["tile_name"]: tile for tile in dalian.get("tiles", [])}
    missing_tiles = {tile["tile_name"]: tile for tile in missing_site.get("tiles", [])}

    if report.get("status") != "completed_with_missing_tiles":
        errors.append(f"manifest should expose missing cross-China WorldCover tiles: {report.get('status')}")
    if dalian.get("coverage_status") != "covered":
        errors.append(f"Dalian should be covered by local N36E120 tile: {dalian}")
    if dalian_tiles.get("ESA_WorldCover_10m_2021_v200_N36E120_Map.tif", {}).get("status") != "selected_local":
        errors.append(f"Dalian N36E120 tile should be selected_local: {dalian_tiles}")
    if missing_site.get("coverage_status") != "missing_coverage":
        errors.append(f"Missing probe should be explicit missing coverage: {missing_site}")
    missing_tile = missing_tiles.get("ESA_WorldCover_10m_2021_v200_N24E102_Map.tif", {})
    if missing_tile.get("status") != "present_incomplete_or_wrong_size":
        errors.append(f"N24E102 tile should be incomplete, not covered: {missing_tiles}")
    if str(fake_missing_tile) not in missing_tile.get("incomplete_local_paths", []):
        errors.append(f"Incomplete tile path should be recorded: {missing_tile}")
    if missing_tile.get("expected_download_bytes") != 123456:
        errors.append(f"Expected download size should be recorded: {missing_tile}")
    expected_url = (
        "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
        "ESA_WorldCover_10m_2021_v200_N24E102_Map.tif"
    )
    if missing_tile.get("download_url") != expected_url:
        errors.append(f"N24E102 tile should include official download_url: {missing_tile}")
    if "ESA_WorldCover_10m_2021_v200_N24E102_Map.tif" not in report.get("missing_expected_tiles", []):
        errors.append(f"manifest missing tile list is incomplete: {report.get('missing_expected_tiles')}")
    if not Path(report.get("output_json", "")).exists():
        errors.append(f"manifest JSON was not written: {report.get('output_json')}")
    if not Path(report.get("output_csv", "")).exists():
        errors.append(f"manifest CSV was not written: {report.get('output_csv')}")
    else:
        csv_text = Path(report["output_csv"]).read_text(encoding="utf-8-sig")
        if "download_url" not in csv_text or expected_url not in csv_text:
            errors.append("manifest CSV should include official WorldCover download_url values")
    gee_js_path = Path(report.get("output_gee_js", ""))
    if not gee_js_path.exists():
        errors.append(f"GEE export script was not written: {report.get('output_gee_js')}")
    else:
        gee_js = gee_js_path.read_text(encoding="utf-8")
        if "ESA/WorldCover/v200" not in gee_js:
            errors.append("GEE export script should reference ESA/WorldCover/v200")
        if "ESA_WorldCover_10m_2021_v200_N24E102_Map" not in gee_js:
            errors.append("GEE export script should include the missing N24E102 tile export")
        if "ESA_WorldCover_10m_2021_v200_N36E120_Map" in gee_js:
            errors.append("GEE export script should not export the already available Dalian N36E120 tile")
    download_ps1_path = Path(report.get("output_download_ps1", ""))
    if not download_ps1_path.exists():
        errors.append(f"WorldCover download script was not written: {report.get('output_download_ps1')}")
    else:
        download_ps1 = download_ps1_path.read_text(encoding="utf-8")
        if expected_url not in download_ps1:
            errors.append("WorldCover download script should include the missing N24E102 URL")
        if "ESA_WorldCover_10m_2021_v200_N36E120_Map" in download_ps1:
            errors.append("WorldCover download script should not download the already available Dalian N36E120 tile")
        if ".part" not in download_ps1 or "Content-Length" not in download_ps1 or "curl.exe -L -C -" not in download_ps1:
            errors.append("WorldCover download script should use .part files, Content-Length checks, and resumable curl.")

    return {
        "status": "success" if not errors else "failed",
        "errors": errors,
        "output_json": report.get("output_json"),
        "output_csv": report.get("output_csv"),
        "output_gee_js": report.get("output_gee_js"),
        "output_download_ps1": report.get("output_download_ps1"),
        "site_count": report.get("site_count"),
        "covered_site_count": report.get("covered_site_count"),
        "missing_site_count": report.get("missing_site_count"),
        "missing_expected_tiles": report.get("missing_expected_tiles"),
    }


def main() -> None:
    result = assert_manifest()
    print(json.dumps(result, ensure_ascii=True, indent=2))
    raise SystemExit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
