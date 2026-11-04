import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.user_cranes import (  # noqa: E402
    add_user_crane,
    build_user_crane_payload,
    delete_user_crane,
    load_user_cranes,
    parse_capacity_curve,
    validate_user_crane,
)


def valid_payload(**overrides):
    payload = {
        "manufacturer": "Liebherr",
        "model": "Test 100",
        "jib_length_m": 50,
        "max_capacity_kg": 6000,
        "max_free_standing_hook_height_m": 44.4,
        "capacity_curve": ((15.0, 6000.0), (30.0, 3500.0), (50.0, 1500.0)),
        "notes": "Введено по локальной брошюре",
    }
    payload.update(overrides)
    return payload


class UserCraneCatalogTests(unittest.TestCase):
    def test_form_payload_converts_decimal_commas_and_curve_text(self):
        payload = build_user_crane_payload(
            {
                "manufacturer": " Liebherr ",
                "model": " 130 EC-B manual ",
                "jib_length_m": "60,0",
                "max_capacity_kg": "6000",
                "max_free_standing_hook_height_m": "44,4",
                "capacity_curve": "20;6000\n60;1350",
                "notes": "Проверить по паспорту",
            }
        )
        self.assertEqual(payload["manufacturer"], "Liebherr")
        self.assertEqual(payload["jib_length_m"], 60.0)
        self.assertEqual(payload["capacity_curve"], [[20.0, 6000.0], [60.0, 1350.0]])
        self.assertEqual(payload["status"], "USER_INPUT_EXPERT_REVIEW")

    def test_parse_capacity_curve_accepts_russian_decimal_separator(self):
        curve = parse_capacity_curve("15; 6000\n30,5; 3400\n50; 1500")
        self.assertEqual(curve, ((15.0, 6000.0), (30.5, 3400.0), (50.0, 1500.0)))

    def test_curve_requires_increasing_radius_and_non_increasing_capacity(self):
        with self.assertRaisesRegex(ValueError, "возрастать"):
            validate_user_crane(valid_payload(capacity_curve=((15, 6000), (15, 5000), (50, 1500))))
        with self.assertRaisesRegex(ValueError, "уменьшаться"):
            validate_user_crane(valid_payload(capacity_curve=((15, 5000), (30, 5500), (50, 1500))))

    def test_curve_must_reach_jib_and_not_exceed_maximum_capacity(self):
        with self.assertRaisesRegex(ValueError, "длины стрелы"):
            validate_user_crane(valid_payload(capacity_curve=((15, 6000), (40, 2000))))
        with self.assertRaisesRegex(ValueError, "максимальную"):
            validate_user_crane(valid_payload(capacity_curve=((15, 6500), (50, 1500))))

    def test_add_round_trip_uses_unique_ids_and_expert_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "user_cranes.json"
            first = add_user_crane(path, valid_payload())
            second = add_user_crane(path, valid_payload(notes="Вторая конфигурация"))

            loaded = load_user_cranes(path)
            self.assertEqual([item["id"] for item in loaded], [first["id"], second["id"]])
            self.assertNotEqual(first["id"], second["id"])
            self.assertTrue(all(item["status"] == "USER_INPUT_EXPERT_REVIEW" for item in loaded))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["schema_version"], 1)
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_delete_removes_only_requested_user_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "user_cranes.json"
            first = add_user_crane(path, valid_payload())
            second = add_user_crane(path, valid_payload(model="Test 200"))

            self.assertTrue(delete_user_crane(path, first["id"]))
            self.assertEqual([item["id"] for item in load_user_cranes(path)], [second["id"]])
            self.assertFalse(delete_user_crane(path, "missing"))


if __name__ == "__main__":
    unittest.main()
