import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.models import RestrictedZone, RestrictedZoneKind  # noqa: E402
from crane_plan.zone_editor import ZoneEditorResult, zone_from_form  # noqa: E402


POLYGON = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]


class ZoneEditorFormTests(unittest.TestCase):
    def test_form_builds_typed_zone_and_accepts_decimal_comma(self):
        zone = zone_from_form(
            POLYGON,
            name="  ЛЭП  ",
            kind_value=RestrictedZoneKind.HEIGHT_OBSTACLE.value,
            height_text="12,5",
            clearance_text="1,25",
            note="  охранная зона  ",
        )

        self.assertEqual(zone.name, "ЛЭП")
        self.assertEqual(zone.kind, RestrictedZoneKind.HEIGHT_OBSTACLE)
        self.assertEqual(zone.height_m, 12.5)
        self.assertEqual(zone.horizontal_clearance_m, 1.25)
        self.assertEqual(zone.note, "охранная зона")
        self.assertEqual(zone.polygon, POLYGON)
        self.assertTrue(zone.id.startswith("zone-"))

    def test_edit_preserves_identity_and_verification_metadata(self):
        initial = RestrictedZone(
            id="zone-existing",
            name="Старое имя",
            kind=RestrictedZoneKind.FULL_EXCLUSION,
            polygon=POLYGON,
            height_m=0.0,
            verified=False,
            source_refs=["source.pdf"],
        )

        edited = zone_from_form(
            POLYGON,
            name="Новое имя",
            kind_value=RestrictedZoneKind.LOAD_PROHIBITED.value,
            height_text="8",
            clearance_text="0",
            note="",
            initial=initial,
        )

        self.assertEqual(edited.id, initial.id)
        self.assertFalse(edited.verified)
        self.assertEqual(edited.source_refs, ["source.pdf"])

    def test_migrated_zone_can_be_explicitly_confirmed(self):
        initial = RestrictedZone(
            id="zone-migrated",
            name="Старая зона",
            kind=RestrictedZoneKind.FULL_EXCLUSION,
            polygon=POLYGON,
            height_m=0.0,
            verified=False,
        )
        confirmed = zone_from_form(
            POLYGON,
            name="Проверенная зона",
            kind_value=RestrictedZoneKind.FULL_EXCLUSION.value,
            height_text="6",
            clearance_text="1",
            note="",
            initial=initial,
            verified=True,
        )
        self.assertTrue(confirmed.verified)

    def test_required_and_numeric_fields_are_validated(self):
        cases = (
            ({"name": "", "kind_value": "FULL_EXCLUSION", "height_text": "0", "clearance_text": "0"}, "назван"),
            ({"name": "Зона", "kind_value": "UNKNOWN", "height_text": "0", "clearance_text": "0"}, "тип"),
            ({"name": "Зона", "kind_value": "FULL_EXCLUSION", "height_text": "", "clearance_text": "0"}, "высот"),
            ({"name": "Зона", "kind_value": "FULL_EXCLUSION", "height_text": "-1", "clearance_text": "0"}, "высот"),
            ({"name": "Зона", "kind_value": "FULL_EXCLUSION", "height_text": "0", "clearance_text": "-0,1"}, "запас"),
        )
        for fields, expected in cases:
            with self.subTest(fields=fields):
                with self.assertRaisesRegex(ValueError, f"(?i){expected}"):
                    zone_from_form(POLYGON, note="", **fields)

    def test_result_explicitly_distinguishes_cancel_from_save(self):
        cancelled = ZoneEditorResult(zone=None, cancelled=True)
        self.assertTrue(cancelled.cancelled)
        self.assertIsNone(cancelled.zone)


if __name__ == "__main__":
    unittest.main()
