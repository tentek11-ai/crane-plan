from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from crane_plan.models import CraneConfiguration, Load, ProjectInput, SiteInput, WorkPoint


ROOT = Path(__file__).resolve().parents[1]
ARTICLE_ROOT = ROOT / "08_dissertation" / "04_article_1_crane_placement"
RUNNER_PATH = ROOT / "04_experiments" / "run_admissible_area_study.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("run_admissible_area_study", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load study runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_manifest(path: Path) -> dict:
    project = ProjectInput(
        name="fixture",
        city="test",
        year=2026,
        author="",
        email="",
        pit_bottom_m=0.0,
        parapet_m=30.0,
        site=SiteInput(
            boundary=[(-20.0, -20.0), (30.0, -20.0), (30.0, 20.0), (-20.0, 20.0)],
            building=[(9.0, -1.0), (11.0, -1.0), (11.0, 1.0), (9.0, 1.0)],
            min_crane_to_building_m=1.0,
            max_crane_to_building_m=20.0,
        ),
        loads=[Load("load", 1000.0, 100.0, 1.0, 1.0, 1.0)],
        work_points=[WorkPoint(10.0, 0.0, 5.0, 0, "WP")],
        protective_screen_possible=True,
        tie_ins_possible=False,
        restricted_zones_confirmed=True,
    )
    config = CraneConfiguration(
        "TEST", "Test", 1, 20.0, 5000.0, 40.0,
        ((5.0, 5000.0), (20.0, 2000.0)), "fixture chart",
    )
    payload = {
        "case_id": "PPRK-TEST",
        "validation_status": "retrospective",
        "research_input": {
            "project": project.to_dict(),
            "crane_configuration": {
                **config.__dict__,
                "capacity_curve": [list(pair) for pair in config.capacity_curve],
            },
            "catalog_version": "fixture-1",
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


class StudyProtocolTests(unittest.TestCase):
    def test_protocol_and_csv_schemas_are_frozen(self):
        protocol = (ARTICLE_ROOT / "protocol" / "EXPERIMENT_PROTOCOL.md").read_text(encoding="utf-8")
        for token in ("4 m", "2 m", "1 m", "≤ 1 m", "≤ 5%", "2026-10-20"):
            self.assertIn(token, protocol)

        expected = {
            "run_registry.csv": {
                "run_id", "case_id", "validation_status", "created_at_utc",
                "algorithm_version", "catalog_version", "step_m", "refinement_levels",
                "project_sha256", "crane_configuration_sha256", "result_file",
            },
            "results_summary.csv": {
                "case_id", "run_id", "metric", "value", "unit", "json_locator",
            },
            "sensitivity.csv": {
                "case_id", "run_id", "step_m", "area_m2", "recommended_x_m",
                "recommended_y_m", "accepted_count", "runtime_s", "stability_status",
            },
        }
        for filename, required in expected.items():
            with (ARTICLE_ROOT / "results" / filename).open(encoding="utf-8", newline="") as handle:
                header = set(next(csv.reader(handle)))
            self.assertTrue(required.issubset(header), filename)

    def test_runner_refuses_duplicate_run_id_without_mutating_first_result(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = root / "manifest.json"
            fixture_manifest(manifest_path)
            manifest_bytes = manifest_path.read_bytes()
            output = runner.run_study(manifest_path, root / "results", "RUN-001", 5.0, 1)
            first_bytes = output.read_bytes()
            with self.assertRaisesRegex(ValueError, "RUN-001"):
                runner.run_study(manifest_path, root / "results", "RUN-001", 2.0, 2)
            self.assertEqual(output.read_bytes(), first_bytes)
            self.assertEqual(manifest_path.read_bytes(), manifest_bytes)

    def test_export_contains_mandatory_provenance_and_preserves_case_status(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = root / "manifest.json"
            fixture_manifest(manifest_path)
            output = runner.run_study(manifest_path, root / "results", "RUN-002", 5.0, 1)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["validation_status"], "retrospective")
            for key in (
                "run_id", "case_id", "created_at_utc", "algorithm_version",
                "catalog_version", "step_m", "refinement_levels", "input_hashes", "result",
            ):
                self.assertIn(key, payload)

    def test_real_case_manifests_block_until_research_inputs_are_confirmed(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as temporary:
            for case_id in ("PPRK-005", "PPRK-006", "PPRK-007"):
                manifest = ARTICLE_ROOT / "cases" / case_id / "case_manifest.json"
                with self.assertRaisesRegex(ValueError, "research_input"):
                    runner.run_study(manifest, Path(temporary), f"BLOCK-{case_id}", 2.0, 2)


if __name__ == "__main__":
    unittest.main()
