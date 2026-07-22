from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

ALLOWED_PROVIDERS = {"manual", "self_capture", "mapillary", "kartaview"}
REQUIRED_COLUMNS = ["image_id", "image_path", "lon", "lat", "provider"]
OPTIONAL_COLUMNS = [
    "captured_at",
    "heading_deg",
    "pitch_deg",
    "roll_deg",
    "horizontal_fov_deg",
    "camera_height_m",
    "coordinate_crs",
    "license",
    "photographer",
    "building_id",
    "notes",
]
TEMPLATE_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS


@dataclass(frozen=True)
class StreetviewImageRecord:
    image_id: str
    image_path: Path
    lon: float
    lat: float
    provider: str
    captured_at: str = ""
    heading_deg: float | None = None
    pitch_deg: float = 0.0
    roll_deg: float = 0.0
    horizontal_fov_deg: float = 70.0
    camera_height_m: float = 1.6
    coordinate_crs: str = "EPSG:4326"
    license: str = ""
    photographer: str = ""
    building_id: str = ""
    notes: str = ""

    def to_row(self) -> dict[str, str | float | None]:
        row = asdict(self)
        row["image_path"] = str(self.image_path)
        return row


def _parse_optional_float(value: str | None, default: float | None = None) -> float | None:
    if value is None or str(value).strip() == "":
        return default
    return float(value)


def _normalize_provider(value: str) -> str:
    provider = value.strip().lower()
    if provider not in ALLOWED_PROVIDERS:
        allowed = ", ".join(sorted(ALLOWED_PROVIDERS))
        raise ValueError(f"Unsupported street-view provider '{value}'. Allowed providers: {allowed}")
    return provider


def read_metadata_csv(csv_path: str | Path, image_root: str | Path | None = None) -> list[StreetviewImageRecord]:
    csv_path = Path(csv_path)
    if image_root is None:
        image_root = csv_path.parent
    image_root = Path(image_root)

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"Metadata CSV is empty: {csv_path}")
        missing = [col for col in REQUIRED_COLUMNS if col not in reader.fieldnames]
        if missing:
            raise ValueError(f"Metadata CSV missing required columns: {missing}")

        records: list[StreetviewImageRecord] = []
        for line_no, row in enumerate(reader, start=2):
            image_id = (row.get("image_id") or "").strip()
            if not image_id:
                raise ValueError(f"Line {line_no}: image_id is required")
            raw_path = (row.get("image_path") or "").strip()
            if not raw_path:
                raise ValueError(f"Line {line_no}: image_path is required")
            image_path = Path(raw_path)
            if not image_path.is_absolute():
                image_path = image_root / image_path
            provider = _normalize_provider(row.get("provider") or "")
            records.append(
                StreetviewImageRecord(
                    image_id=image_id,
                    image_path=image_path,
                    lon=float(row.get("lon") or "nan"),
                    lat=float(row.get("lat") or "nan"),
                    provider=provider,
                    captured_at=(row.get("captured_at") or "").strip(),
                    heading_deg=_parse_optional_float(row.get("heading_deg")),
                    pitch_deg=float(_parse_optional_float(row.get("pitch_deg"), 0.0) or 0.0),
                    roll_deg=float(_parse_optional_float(row.get("roll_deg"), 0.0) or 0.0),
                    horizontal_fov_deg=float(_parse_optional_float(row.get("horizontal_fov_deg"), 70.0) or 70.0),
                    camera_height_m=float(_parse_optional_float(row.get("camera_height_m"), 1.6) or 1.6),
                    coordinate_crs=(row.get("coordinate_crs") or "EPSG:4326").strip(),
                    license=(row.get("license") or "").strip(),
                    photographer=(row.get("photographer") or "").strip(),
                    building_id=(row.get("building_id") or "").strip(),
                    notes=(row.get("notes") or "").strip(),
                )
            )
    return records


def validate_records(records: Iterable[StreetviewImageRecord], require_images: bool = True) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    seen: set[str] = set()
    for record in records:
        if record.image_id in seen:
            issues.append({"image_id": record.image_id, "severity": "error", "message": "duplicate image_id"})
        seen.add(record.image_id)
        if record.coordinate_crs.upper() != "EPSG:4326":
            issues.append({"image_id": record.image_id, "severity": "error", "message": "Phase 1 metadata requires lon/lat in EPSG:4326"})
        if not (-180.0 <= record.lon <= 180.0 and -90.0 <= record.lat <= 90.0):
            issues.append({"image_id": record.image_id, "severity": "error", "message": "invalid lon/lat range"})
        if record.heading_deg is not None and not (0.0 <= record.heading_deg < 360.0):
            issues.append({"image_id": record.image_id, "severity": "error", "message": "heading_deg must be in [0, 360)"})
        if record.horizontal_fov_deg <= 0.0 or record.horizontal_fov_deg > 180.0:
            issues.append({"image_id": record.image_id, "severity": "error", "message": "horizontal_fov_deg must be in (0, 180]"})
        if require_images and not record.image_path.exists():
            issues.append({"image_id": record.image_id, "severity": "error", "message": f"image file not found: {record.image_path}"})
        if not record.license:
            issues.append({"image_id": record.image_id, "severity": "warning", "message": "license is empty; publication use must document image rights"})
    return issues


def write_metadata_template(path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sample = {
        "image_id": "sample_001",
        "image_path": "images/sample_001.jpg",
        "lon": "121.512000",
        "lat": "38.883000",
        "provider": "manual",
        "captured_at": "2026-01-01T10:00:00+08:00",
        "heading_deg": "90",
        "pitch_deg": "0",
        "roll_deg": "0",
        "horizontal_fov_deg": "70",
        "camera_height_m": "1.6",
        "coordinate_crs": "EPSG:4326",
        "license": "user-supplied, document before publication",
        "photographer": "",
        "building_id": "",
        "notes": "replace this sample row with real authorized images",
    }
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TEMPLATE_COLUMNS)
        writer.writeheader()
        writer.writerow(sample)
    return path
