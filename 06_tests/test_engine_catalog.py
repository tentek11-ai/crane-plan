from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from crane_plan.engine.catalog import (
    CapacityPoint,
    CraneConfigurationV3,
    conservative_capacity_kg,
    load_catalog_v3,
    validate_capacity_curve,
)
from crane_plan.engine.domain import SourceKind, SourceLocator


def make_config() -> CraneConfigurationV3:
    return CraneConfigurationV3(
        id="CFG-1",
        manufacturer="Liebherr",
        model="Test crane",
        priority=1,
        jib_length_m=30.0,
        max_free_standing_hook_height_m=44.4,
        capacity_curve=(CapacityPoint(25.0, 5900.0), CapacityPoint(30.0, 5200.0)),
        allowed_jib_lengths_m=(25.0, 30.0),
        allowed_tower_section_heights_m=(5.0,),
        source=SourceLocator(
            SourceKind.PASSPORT,
            "CRANE-CAT-TEST",
            "p. 2",
            sha256="a" * 64,
        ),
    )


class EngineCatalogTests(unittest.TestCase):
    def test_capacity_at_exact_chart_radius_uses_exact_value(self):
        self.assertEqual(conservative_capacity_kg(make_config(), 25.0), 5900.0)

    def test_capacity_between_points_uses_next_larger_radius_value(self):
        self.assertEqual(conservative_capacity_kg(make_config(), 28.75), 5200.0)

    def test_capacity_outside_terminal_radius_is_zero(self):
        self.assertEqual(conservative_capacity_kg(make_config(), 30.001), 0.0)

    def test_empty_unsorted_duplicate_and_increasing_curves_are_rejected(self):
        cases = (
            ((), "CURVE_EMPTY"),
            ((CapacityPoint(30, 5200), CapacityPoint(25, 5000)), "RADIUS_ORDER_INVALID"),
            ((CapacityPoint(25, 5900), CapacityPoint(25, 5200)), "RADIUS_DUPLICATE"),
            ((CapacityPoint(25, 5200), CapacityPoint(30, 5900)), "CAPACITY_NOT_MONOTONE"),
        )
        for curve, expected_code in cases:
            with self.subTest(expected_code):
                issues = validate_capacity_curve(replace(make_config(), capacity_curve=curve))
                self.assertIn(expected_code, {issue.code for issue in issues})

    def test_catalog_requires_document_page_and_sha256(self):
        payload = {
            "schema_version": 3,
            "catalog_version": "test",
            "configurations": [
                {
                    "id": "BAD",
                    "manufacturer": "Liebherr",
                    "model": "Bad source",
                    "priority": 1,
                    "jib_length_m": 30,
                    "max_free_standing_hook_height_m": 40,
                    "capacity_curve": [[25, 5900], [30, 5200]],
                    "allowed_jib_lengths_m": [25, 30],
                    "allowed_tower_section_heights_m": [5],
                    "source": {
                        "kind": "PASSPORT",
                        "document_id": "",
                        "locator": "",
                        "sha256": "",
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SOURCE_INCOMPLETE"):
                load_catalog_v3(path)


if __name__ == "__main__":
    unittest.main()
