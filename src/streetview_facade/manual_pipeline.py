from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .coordinates import LocalOrigin, angular_difference_deg, bearing_between_xy, distance_xy, local_xy
from .facade import FacadePlane, extract_facades_from_buildings, write_facade_csv
from .metadata import StreetviewImageRecord, read_metadata_csv, validate_records, write_metadata_template


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _choose_origin(records: list[StreetviewImageRecord], center_lon: float | None, center_lat: float | None) -> LocalOrigin:
    if center_lon is not None and center_lat is not None:
        return LocalOrigin(lon=center_lon, lat=center_lat)
    if not records:
        raise ValueError("Cannot infer local origin without metadata records")
    return LocalOrigin(
        lon=sum(r.lon for r in records) / len(records),
        lat=sum(r.lat for r in records) / len(records),
    )


def _match_images_to_facades(records: list[StreetviewImageRecord], facades: list[FacadePlane], origin: LocalOrigin) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for record in records:
        image_xy = local_xy(record.lon, record.lat, origin)
        best: dict[str, Any] | None = None
        for facade in facades:
            facade_xy = facade.centroid_xy
            distance_m = distance_xy(image_xy, facade_xy)
            view_bearing = bearing_between_xy(image_xy, facade_xy)
            if record.heading_deg is None:
                angle_error = None
                score = distance_m
            else:
                angle_error = angular_difference_deg(record.heading_deg, view_bearing)
                # A heading-consistent image farther away is preferred to a nearby image facing the wrong direction.
                score = distance_m + angle_error * 2.0
            row = {
                "image_id": record.image_id,
                "facade_id": facade.facade_id,
                "building_id": facade.building_id,
                "image_x_m": round(image_xy[0], 3),
                "image_y_m": round(image_xy[1], 3),
                "facade_centroid_x_m": round(facade_xy[0], 3),
                "facade_centroid_y_m": round(facade_xy[1], 3),
                "distance_m": round(distance_m, 3),
                "image_heading_deg": record.heading_deg,
                "bearing_to_facade_deg": round(view_bearing, 3),
                "heading_error_deg": round(angle_error, 3) if angle_error is not None else "",
                "match_score": round(score, 3),
                "match_status": "candidate_for_manual_correspondence",
            }
            if best is None or score < float(best["match_score"]):
                best = row
        if best is not None:
            matches.append(best)
    return matches


def run_manual_phase1(
    metadata_csv: str | Path,
    building_path: str | Path,
    output_dir: str | Path,
    image_root: str | Path | None = None,
    center_lon: float | None = None,
    center_lat: float | None = None,
    id_column: str | None = None,
    min_facade_length_m: float = 2.0,
    require_images: bool = True,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    records = read_metadata_csv(metadata_csv, image_root=image_root)
    issues = validate_records(records, require_images=require_images)
    error_count = sum(1 for issue in issues if issue["severity"] == "error")
    _write_csv(output_dir / "metadata_audit.csv", issues, fieldnames=["image_id", "severity", "message"])
    if error_count:
        raise ValueError(f"Street-view metadata validation failed with {error_count} error(s); see metadata_audit.csv")

    origin = _choose_origin(records, center_lon=center_lon, center_lat=center_lat)
    facades = extract_facades_from_buildings(building_path, origin, id_column=id_column, min_length_m=min_facade_length_m)
    write_facade_csv(facades, output_dir / "facade_planes.csv")
    matches = _match_images_to_facades(records, facades, origin)
    _write_csv(output_dir / "image_facade_matches.csv", matches)

    summary = {
        "status": "success",
        "phase": "streetview_facade_manual_import_phase1",
        "metadata_csv": str(Path(metadata_csv)),
        "building_path": str(Path(building_path)),
        "output_dir": str(output_dir),
        "origin": asdict(origin),
        "image_count": len(records),
        "facade_count": len(facades),
        "match_count": len(matches),
        "metadata_warning_count": sum(1 for issue in issues if issue["severity"] == "warning"),
        "outputs": {
            "metadata_audit": str(output_dir / "metadata_audit.csv"),
            "facade_planes": str(output_dir / "facade_planes.csv"),
            "image_facade_matches": str(output_dir / "image_facade_matches.csv"),
            "summary": str(output_dir / "summary.json"),
        },
        "limitations": [
            "Phase 1 does not infer facade semantics or depth; it prepares auditable manual image-to-facade correspondences.",
            "Images must be self-captured, manually supplied, or obtained from licensed providers outside this runner.",
        ],
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 1 manual street-view facade metadata audit and facade matching.")
    parser.add_argument("--metadata-csv", required=True)
    parser.add_argument("--building-path", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--image-root", default=None)
    parser.add_argument("--center-lon", type=float, default=None)
    parser.add_argument("--center-lat", type=float, default=None)
    parser.add_argument("--id-column", default=None)
    parser.add_argument("--min-facade-length-m", type=float, default=2.0)
    parser.add_argument("--allow-missing-images-for-template-check", action="store_true")
    parser.add_argument("--write-template", default=None)
    args = parser.parse_args()

    if args.write_template:
        print(write_metadata_template(args.write_template))
        return

    summary = run_manual_phase1(
        metadata_csv=args.metadata_csv,
        building_path=args.building_path,
        output_dir=args.output_dir,
        image_root=args.image_root,
        center_lon=args.center_lon,
        center_lat=args.center_lat,
        id_column=args.id_column,
        min_facade_length_m=args.min_facade_length_m,
        require_images=not args.allow_missing_images_for_template_check,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
