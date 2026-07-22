from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from streetview_facade.manual_pipeline import run_manual_phase1


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        image_dir = tmp / "images"
        image_dir.mkdir()
        image_path = image_dir / "sample.jpg"
        image_path.write_bytes(b"placeholder image bytes for metadata existence validation")
        metadata = tmp / "metadata.csv"
        metadata.write_text(
            "image_id,image_path,lon,lat,provider,captured_at,heading_deg,pitch_deg,roll_deg,horizontal_fov_deg,camera_height_m,coordinate_crs,license,photographer,building_id,notes\n"
            "img_001,images/sample.jpg,121.5120,38.8830,manual,2026-01-01T10:00:00+08:00,90,0,0,70,1.6,EPSG:4326,user-supplied,,bldg_001,validation sample\n",
            encoding="utf-8-sig",
        )
        building = tmp / "building.geojson"
        building.write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"osm_id": "bldg_001"},
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [
                                    [
                                        [121.51205, 38.88295],
                                        [121.51218, 38.88295],
                                        [121.51218, 38.88308],
                                        [121.51205, 38.88308],
                                        [121.51205, 38.88295],
                                    ]
                                ],
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        out = tmp / "out"
        summary = run_manual_phase1(
            metadata_csv=metadata,
            building_path=building,
            output_dir=out,
            image_root=tmp,
            center_lon=121.5120,
            center_lat=38.8830,
        )
        assert summary["image_count"] == 1
        assert summary["facade_count"] >= 4
        assert summary["match_count"] == 1
        for name in ["metadata_audit.csv", "facade_planes.csv", "image_facade_matches.csv", "summary.json"]:
            assert (out / name).exists(), name
        print(json.dumps({"status": "success", "summary": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
