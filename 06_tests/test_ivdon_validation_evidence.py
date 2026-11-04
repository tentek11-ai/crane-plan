from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "04_experiments" / "import_ivdon_validation_evidence.py"


def load_importer():
    spec = importlib.util.spec_from_file_location("ivdon_evidence", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load evidence importer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IvDonValidationEvidenceTests(unittest.TestCase):
    def test_normalizes_novatorov_project_and_author_confirmed_evidence(self):
        module = load_importer()
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            temp = Path(temporary)
            project = temp / "project"
            project.mkdir()
            payload = {
                "work_points": [{} for _ in range(16)],
                "loads": [{"active": True, "lifts": 160}],
                "hours_per_day": 24,
                "utilization": 0.7,
                "scenarios": [{
                    "status": "PASS_WITH_CONDITIONS",
                    "placements": [{
                        "model": "130 EC-B 6", "x": 1.0, "y": 2.0,
                        "assigned_work_points": list(range(16)),
                        "max_radius_m": 16.826473, "required_hook_height_m": 37.2,
                        "jib_length_m": 20.0, "accepted_crane_height_m": 44.4,
                    }],
                    "accounted_lifts": 160, "total_active_lifts": 160,
                    "calendar_days": 1.773805,
                    "warnings": ["требуется проект защитного ограждения"],
                }],
            }
            (project / "project.json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            reports = project / "reports"
            reports.mkdir()
            (reports / "ППРк_предварительный.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
            result = module.load_validation_evidence(temp / "article", project)

        novatorov = result["novatorov"]
        retrospective = result["retrospective"]
        self.assertEqual(novatorov["software_version"], "2.2.2")
        self.assertEqual(novatorov["recommended_model"], "130 EC-B 6")
        self.assertEqual(novatorov["covered_points"], 16)
        self.assertEqual(novatorov["accounted_lifts"], 160)
        self.assertEqual(
            novatorov["status_ru"],
            "решение допустимо при выполнении установленных условий безопасности",
        )
        self.assertEqual(
            novatorov["expert_evidence_status"],
            "AUTHOR_CONFIRMED_WRITTEN_SIGNED_STAMPED",
        )
        self.assertEqual(
            retrospective["evidence_status"], "AUTHOR_CONFIRMED_HELD_BY_AUTHOR"
        )
        self.assertNotIn(str(project), json.dumps(result, ensure_ascii=False))

    def test_missing_external_archives_do_not_invent_numeric_metrics(self):
        module = load_importer()
        record = module.build_retrospective_attestation()
        self.assertEqual(record["evidence_status"], "AUTHOR_CONFIRMED_HELD_BY_AUTHOR")
        self.assertEqual(record["workspace_inspection"], False)
        self.assertNotIn("coverage_percent", record)
        self.assertNotIn("calculation_time", record)


if __name__ == "__main__":
    unittest.main()
