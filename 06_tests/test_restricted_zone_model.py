import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan import models  # noqa: E402
from crane_plan.project_io import load_project, save_project  # noqa: E402


class RestrictedZoneModelTests(unittest.TestCase):
    def test_site_input_normalizes_legacy_polygon_for_runtime_compatibility(self):
        site = models.SiteInput(
            boundary=[(0, 0), (10, 0), (10, 10), (0, 10)],
            building=[(3, 3), (7, 3), (7, 7), (3, 7)],
            restricted_zones=[[(1, 1), (2, 1), (2, 2), (1, 2)]],
        )
        self.assertIsInstance(site.restricted_zones[0], models.RestrictedZone)
        self.assertEqual(site.restricted_zones[0].kind, models.RestrictedZoneKind.FULL_EXCLUSION)
        self.assertFalse(site.restricted_zones[0].verified)

    def test_zone_model_exposes_typed_validated_fields(self):
        self.assertTrue(hasattr(models, "RestrictedZoneKind"))
        self.assertTrue(hasattr(models, "RestrictedZone"))

        zone = models.RestrictedZone(
            id="zone-1",
            name="ЛЭП",
            kind=models.RestrictedZoneKind.HEIGHT_OBSTACLE,
            polygon=[(0, 0), (4, 0), (4, 3), (0, 3)],
            height_m=12.5,
            horizontal_clearance_m=1.0,
            note="Проверить по исполнительной съёмке",
            source_refs=["ГП-1"],
        )

        self.assertEqual(zone.kind.value, "HEIGHT_OBSTACLE")
        self.assertEqual(zone.height_m, 12.5)
        self.assertEqual(zone.horizontal_clearance_m, 1.0)
        self.assertTrue(zone.verified)
        self.assertEqual(zone.source_refs, ["ГП-1"])

    def test_zone_rejects_invalid_geometry_and_dimensions(self):
        cases = (
            ([(0, 0), (1, 0), (0, 0)], 1.0, 0.0, "трёх уникальных"),
            ([(0, 0), (1, 0), (0, 1)], -0.1, 0.0, "Высота"),
            ([(0, 0), (1, 0), (0, 1)], 1.0, -0.1, "запас"),
        )
        for polygon, height, clearance, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    models.RestrictedZone(
                        id="zone-invalid",
                        name="Неверная зона",
                        kind=models.RestrictedZoneKind.FULL_EXCLUSION,
                        polygon=polygon,
                        height_m=height,
                        horizontal_clearance_m=clearance,
                    )

    def test_project_defaults_include_route_settings_and_warning_acceptance(self):
        site = models.SiteInput(
            boundary=[(0, 0), (10, 0), (10, 10), (0, 10)],
            building=[(3, 3), (7, 3), (7, 7), (3, 7)],
        )
        project = models.ProjectInput(
            "Дом", "Москва", 2026, "", "", 0, 30, site, [], []
        )
        self.assertEqual(project.schema_version, 4)
        self.assertEqual(project.route_angle_step_deg, 1.0)
        self.assertEqual(project.route_radius_step_m, 0.5)
        self.assertEqual(project.vertical_clearance_m, 3.0)
        self.assertEqual(project.warning_acceptances, [])

        acceptance = models.WarningAcceptance("warning-1", "a" * 64, "Принято")
        project.warning_acceptances.append(acceptance)
        self.assertEqual(
            project.to_dict()["warning_acceptances"][0],
            {"warning_id": "warning-1", "input_sha256": "a" * 64, "comment": "Принято"},
        )

    def test_schema_three_round_trip_preserves_typed_zones_and_acceptances(self):
        zone = models.RestrictedZone(
            id="zone-1",
            name="Существующее здание",
            kind=models.RestrictedZoneKind.HEIGHT_OBSTACLE,
            polygon=[(1, 1), (2, 1), (2, 2), (1, 2)],
            height_m=18.0,
            horizontal_clearance_m=0.5,
            note="Обмерить",
            source_refs=["СПОЗУ"],
        )
        project = models.ProjectInput(
            "Дом",
            "Москва",
            2026,
            "",
            "",
            0,
            30,
            models.SiteInput(
                boundary=[(0, 0), (10, 0), (10, 10), (0, 10)],
                building=[(3, 3), (7, 3), (7, 7), (3, 7)],
                restricted_zones=[zone],
            ),
            [],
            [],
            warning_acceptances=[models.WarningAcceptance("warn-1", "b" * 64)],
        )

        with tempfile.TemporaryDirectory() as temporary:
            path = save_project(temporary, project)
            payload = json.loads(path.read_text(encoding="utf-8"))
            loaded = load_project(path)

        self.assertEqual(payload["schema_version"], 4)
        self.assertEqual(payload["site"]["restricted_zones"][0]["kind"], "HEIGHT_OBSTACLE")
        self.assertIsInstance(loaded.site.restricted_zones[0], models.RestrictedZone)
        self.assertEqual(loaded.site.restricted_zones[0].height_m, 18.0)
        self.assertEqual(loaded.warning_acceptances[0].warning_id, "warn-1")

    def test_loading_schema_two_migrates_zone_without_overwriting_source(self):
        project = models.ProjectInput(
            "Дом",
            "Москва",
            2026,
            "",
            "",
            0,
            30,
            models.SiteInput(
                boundary=[(0, 0), (10, 0), (10, 10), (0, 10)],
                building=[(3, 3), (7, 3), (7, 7), (3, 7)],
            ),
            [],
            [],
        )
        payload = project.to_dict()
        payload["schema_version"] = 2
        payload["site"]["restricted_zones"] = [
            [[1, 1], [2, 1], [2, 2], [1, 2]]
        ]

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "project.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            before = path.read_bytes()
            loaded = load_project(path)
            after = path.read_bytes()

        migrated = loaded.site.restricted_zones[0]
        self.assertEqual(before, after)
        self.assertEqual(loaded.schema_version, 4)
        self.assertEqual(migrated.kind, models.RestrictedZoneKind.FULL_EXCLUSION)
        self.assertEqual(migrated.height_m, 0.0)
        self.assertFalse(migrated.verified)
        self.assertEqual(migrated.name, "Опасная зона 1")


if __name__ == "__main__":
    unittest.main()

