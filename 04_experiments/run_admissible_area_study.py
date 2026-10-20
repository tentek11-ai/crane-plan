"""Immutable command-line runner for the admissible-area article study."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from crane_plan.admissible_area import calculate_admissible_area
from crane_plan.models import CraneConfiguration, Load, ProjectInput, SiteInput, WorkPoint


REGISTRY_FIELDS = (
    "run_id", "case_id", "validation_status", "created_at_utc",
    "algorithm_version", "catalog_version", "step_m", "refinement_levels",
    "project_sha256", "crane_configuration_sha256", "result_file",
)


def _project_from_dict(data: dict) -> ProjectInput:
    site_data = data["site"]
    site = SiteInput(
        boundary=[tuple(point) for point in site_data["boundary"]],
        building=[tuple(point) for point in site_data["building"]],
        restricted_zones=[[tuple(point) for point in zone] for zone in site_data.get("restricted_zones", [])],
        unloading_zone=[tuple(point) for point in site_data.get("unloading_zone", [])],
        storage_zones=[[tuple(point) for point in zone] for zone in site_data.get("storage_zones", [])],
        min_crane_to_building_m=site_data.get("min_crane_to_building_m", 1.0),
        max_crane_to_building_m=site_data.get("max_crane_to_building_m", 25.0),
    )
    fields = {key: value for key, value in data.items() if key in ProjectInput.__dataclass_fields__}
    fields["site"] = site
    fields["loads"] = [Load(**item) for item in data["loads"]]
    fields["work_points"] = [WorkPoint(**item) for item in data["work_points"]]
    if "section_building_contour" in fields:
        fields["section_building_contour"] = [tuple(point) for point in fields["section_building_contour"]]
    for key in ("plan_crop_box", "section_crop_box"):
        if key in fields:
            fields[key] = tuple(fields[key])
    return ProjectInput(**fields)


def _configuration_from_dict(data: dict) -> CraneConfiguration:
    payload = dict(data)
    payload["capacity_curve"] = tuple(tuple(float(value) for value in pair) for pair in data["capacity_curve"])
    return CraneConfiguration(**payload)


def _registry_ids(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["run_id"] for row in csv.DictReader(handle)}


def run_study(
    manifest_path: str | Path,
    results_root: str | Path,
    run_id: str,
    step_m: float,
    refinement_levels: int,
) -> Path:
    manifest_path = Path(manifest_path)
    results_root = Path(results_root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if "research_input" not in manifest:
        raise ValueError(f"{manifest.get('case_id', manifest_path.stem)}: mandatory research_input is not confirmed")
    case_id = str(manifest["case_id"])
    validation_status = str(manifest["validation_status"])
    research_input = manifest["research_input"]
    catalog_version = str(research_input.get("catalog_version", ""))
    if not catalog_version:
        raise ValueError("catalog_version is required")

    registry_path = results_root / "run_registry.csv"
    output_path = results_root / "runs" / case_id / f"{run_id}.json"
    if run_id in _registry_ids(registry_path) or output_path.exists():
        raise ValueError(f"Run ID already exists: {run_id}")

    project = _project_from_dict(research_input["project"])
    config = _configuration_from_dict(research_input["crane_configuration"])
    result = calculate_admissible_area(project, config, step_m, refinement_levels, run_id)
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    input_hashes = dict(result.input_hashes)
    payload = {
        "run_id": run_id,
        "case_id": case_id,
        "validation_status": validation_status,
        "created_at_utc": created_at,
        "algorithm_version": result.algorithm_version,
        "catalog_version": catalog_version,
        "step_m": step_m,
        "refinement_levels": refinement_levels,
        "input_hashes": input_hashes,
        "result": asdict(result),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, output_path)

    registry_path.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not registry_path.exists()
    with registry_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REGISTRY_FIELDS)
        if needs_header:
            writer.writeheader()
        writer.writerow({
            "run_id": run_id,
            "case_id": case_id,
            "validation_status": validation_status,
            "created_at_utc": created_at,
            "algorithm_version": result.algorithm_version,
            "catalog_version": catalog_version,
            "step_m": step_m,
            "refinement_levels": refinement_levels,
            "project_sha256": input_hashes["project_sha256"],
            "crane_configuration_sha256": input_hashes["crane_configuration_sha256"],
            "result_file": output_path.relative_to(results_root).as_posix(),
        })
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--step", type=float, required=True)
    parser.add_argument("--refinement-levels", type=int, default=0)
    args = parser.parse_args()
    print(run_study(args.manifest, args.results_root, args.run_id, args.step, args.refinement_levels))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
