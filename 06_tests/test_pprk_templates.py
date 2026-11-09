import json
import csv
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.pprk_models import TemplateOverride  # noqa: E402
from crane_plan.pprk_templates import (  # noqa: E402
    ALLOWED_ORIGIN_STATUSES,
    TemplateCatalogError,
    load_template_catalog,
    load_regulation_ids,
    render_template_text,
    validate_catalog_regulations,
)


EXPECTED_SECTION_IDS = (
    "general",
    "basis_and_regulations",
    "object_characteristics",
    "crane_characteristics",
    "preparatory_measures",
    "work_procedure",
    "construction_stages",
    "safe_crane_operations",
    "lifting_accessories",
    "loading_operations",
    "long_loads",
    "storage",
    "concrete_bucket",
    "receiving_platforms",
    "opening_delivery",
    "joint_operations",
    "fire_safety",
    "storm_and_weather",
    "work_at_height",
    "electrical_safety",
    "environmental_protection",
    "external_documents",
)


class PPRKTemplateCatalogTests(unittest.TestCase):
    def test_catalog_contains_all_spec_sections_and_unique_stable_ids(self):
        catalog = load_template_catalog()

        self.assertEqual(tuple(section.section_id for section in catalog), EXPECTED_SECTION_IDS)
        paragraph_ids = [paragraph.paragraph_id for section in catalog for paragraph in section.paragraphs]
        self.assertEqual(len(paragraph_ids), len(set(paragraph_ids)))
        self.assertTrue(all(paragraph.version for section in catalog for paragraph in section.paragraphs))
        self.assertTrue(all(paragraph.origin_status for section in catalog for paragraph in section.paragraphs))
        self.assertTrue(all(section.source_pages for section in catalog))
        for section in catalog:
            for paragraph in section.paragraphs:
                self.assertIn(paragraph.origin_status, ALLOWED_ORIGIN_STATUSES)
                self.assertRegex(paragraph.review_date, r"^\d{4}-\d{2}-\d{2}$")
                self.assertIn(paragraph.source_page, section.source_pages)
                self.assertIsInstance(paragraph.sheet_links, tuple)
                self.assertIsInstance(paragraph.appendix_links, tuple)

    def test_every_section_declares_condition_variables_and_normative_keys(self):
        catalog = load_template_catalog()

        self.assertTrue(all(section.inclusion_condition for section in catalog))
        self.assertTrue(all(isinstance(section.required_variables, tuple) for section in catalog))
        self.assertTrue(all(isinstance(section.normative_keys, tuple) for section in catalog))
        self.assertGreater(sum(len(section.normative_keys) for section in catalog), 15)
        for section in catalog:
            declared = set(section.required_variables)
            used = {name for paragraph in section.paragraphs for name in paragraph.placeholders}
            self.assertLessEqual(used, declared, section.section_id)

    def test_all_normative_keys_resolve_to_actual_registry_rows(self):
        catalog = load_template_catalog()
        registry_ids = load_regulation_ids(ROOT / "02_processed_data/regulations/regulation_registry.csv")

        self.assertTrue({f"REG-{index:03d}" for index in range(1, 10)}.issubset(registry_ids))
        self.assertEqual(validate_catalog_regulations(catalog, registry_ids), ())

    def test_specialized_sections_reference_semantically_matching_registry_documents(self):
        registry_path = ROOT / "02_processed_data/regulations/regulation_registry.csv"
        with registry_path.open("r", encoding="utf-8-sig", newline="") as stream:
            rows = {row["rule_id"]: row for row in csv.DictReader(stream)}
        catalog = {section.section_id: section for section in load_template_catalog()}

        self.assertIn("REG-010", catalog["fire_safety"].normative_keys)
        self.assertIn("пожар", (rows["REG-010"]["topic"] + rows["REG-010"]["document"]).lower())
        self.assertIn("1479", rows["REG-010"]["document"])
        self.assertIn("REG-011", catalog["work_at_height"].normative_keys)
        self.assertIn("высот", (rows["REG-011"]["topic"] + rows["REG-011"]["document"]).lower())
        self.assertIn("782н", rows["REG-011"]["document"])
        self.assertIn("REG-012", catalog["electrical_safety"].normative_keys)
        self.assertIn("электроустанов", (rows["REG-012"]["topic"] + rows["REG-012"]["document"]).lower())
        self.assertIn("903н", rows["REG-012"]["document"])
        self.assertIn("REG-013", catalog["electrical_safety"].normative_keys)
        self.assertIn("811", rows["REG-013"]["document"])

    def test_full_note_preserves_operational_depth_and_accurate_provenance(self):
        catalog = {section.section_id: section for section in load_template_catalog()}

        self.assertGreaterEqual(len(catalog["safe_crane_operations"].paragraphs), 18)
        self.assertGreaterEqual(len(catalog["fire_safety"].paragraphs), 8)
        self.assertGreaterEqual(len(catalog["environmental_protection"].paragraphs), 5)
        fire_page_40 = " ".join(
            paragraph.text for paragraph in catalog["fire_safety"].paragraphs if paragraph.source_page == 40
        ).lower()
        self.assertIn("эвакуац", fire_page_40)
        self.assertIn("встреч", fire_page_40)
        environment = " ".join(paragraph.text for paragraph in catalog["environmental_protection"].paragraphs).lower()
        self.assertNotIn("шумные работы", environment)
        self.assertNotIn("слепящего", environment)

    def test_master_numeric_clearances_prohibitions_and_fire_inventory_are_preserved(self):
        catalog = {section.section_id: section for section in load_template_catalog()}
        safe = {paragraph.paragraph_id: paragraph.text.lower() for paragraph in catalog["safe_crane_operations"].paragraphs}
        movement = safe["safe.load_movement"]
        self.assertRegex(movement, r"1(?:[,.]0)?\s*м[^.]{0,80}горизонт")
        self.assertRegex(movement, r"0[,.]5\s*м[^.]{0,80}вертикал")
        page_23 = " ".join(
            paragraph.text.lower()
            for paragraph in catalog["safe_crane_operations"].paragraphs
            if paragraph.source_page == 23
        )
        for required in (
            "находящимися на нем людьми",
            "примерзшего",
            "наклонном положении",
            "защемленных ветвей",
            "поправка стропов на весу",
            "концевыми выключателями",
            "выведенных из строя прибор",
            "нахождении людей на кране вне его кабины",
            "под которыми размещены помещения",
            "в кузове или кабине",
            "между поднимаемым",
            "поврежденными строповочными узлами",
            "на вилы погрузчика",
            "без стропальщика",
            "оставлять груз на крюке",
        ):
            with self.subTest(required=required):
                self.assertIn(required, page_23)
        fire = " ".join(paragraph.text.lower() for paragraph in catalog["fire_safety"].paragraphs)
        for required in (
            "лом — 1 шт",
            "багор — 1 шт",
            "ведро — 2 шт",
            "лопата штыковая — 1 шт",
            "лопата совковая — 1 шт",
            "0,2 м³",
            "0,5 м³",
            "огнетушитель — 2 шт",
        ):
            with self.subTest(required=required):
                self.assertIn(required, fire)

    def test_calculated_object_text_uses_structured_variables_not_opaque_blobs(self):
        catalog = {section.section_id: section for section in load_template_catalog()}
        declared = {name for section in catalog.values() for name in section.required_variables}
        required = {
            "crane_count",
            "crane_configurations",
            "work_radii_m",
            "tower_sections",
            "tie_levels_m",
            "active_loads",
            "load_masses_kg",
            "rigging_masses_kg",
            "lift_counts",
            "sozr_points",
            "route_register",
        }

        self.assertLessEqual(required, declared)
        for opaque in ("stage_description", "active_lifting_devices", "joint_work_description"):
            self.assertNotIn(opaque, declared)

    def test_catalog_contains_no_reference_project_identifiers(self):
        raw = (ROOT / "05_src/crane_plan/assets/pprk/sections.json").read_text(encoding="utf-8").lower()

        for forbidden in ("тружеников", "хамовник", "ac-trz", "архиком", "вл.12", "27.06-23"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, raw)

    def test_loader_rejects_placeholder_not_declared_by_section(self):
        payload = {
            "schema_version": 1,
            "sections": [
                {
                    "id": "bad",
                    "title": "Bad",
                    "condition": "always",
                    "origin_status": "typical",
                    "review_date": "2026-11-04",
                    "sheet_links": [],
                    "appendix_links": [],
                    "required_variables": ["object_name"],
                    "normative_keys": [],
                    "source_pages": [5],
                    "paragraphs": [
                        {"id": "bad.p1", "version": "1.0", "source_page": 5, "text": "{object_name}: {undeclared}"}
                    ],
                }
            ],
        }
        temp_root = ROOT / "tmp" / "test-temp"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as tmp:
            path = Path(tmp) / "sections.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(TemplateCatalogError, "undeclared"):
                load_template_catalog(path)

    def test_loader_rejects_invalid_review_date_and_out_of_range_source_page(self):
        def payload(review_date="2026-99-99", source_page=5):
            return {
                "schema_version": 1,
                "sections": [
                    {
                        "id": "bad_metadata",
                        "title": "Bad metadata",
                        "condition": "always",
                        "origin_status": "typical",
                        "review_date": review_date,
                        "sheet_links": [],
                        "appendix_links": [],
                        "required_variables": [],
                        "normative_keys": [],
                        "source_pages": [5],
                        "paragraphs": [
                            {"id": "bad_metadata.p1", "version": "1.0", "source_page": source_page, "text": "Текст"}
                        ],
                    }
                ],
            }

        temp_root = ROOT / "tmp" / "test-temp"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as tmp:
            path = Path(tmp) / "sections.json"
            path.write_text(json.dumps(payload()), encoding="utf-8")
            with self.assertRaisesRegex(TemplateCatalogError, "review_date"):
                load_template_catalog(path)
            path.write_text(json.dumps(payload("2026-11-04", 999)), encoding="utf-8")
            with self.assertRaisesRegex(TemplateCatalogError, "source_page"):
                load_template_catalog(path)

    def test_missing_required_value_is_visible_and_reported(self):
        rendered = render_template_text("general", {"crane_model": "Liebherr 130 EC-B 6"}, [])

        self.assertIn("object_name", rendered.missing_variables)
        self.assertIn("⟦НЕ ЗАПОЛНЕНО: object_name⟧", rendered.text)
        self.assertIn("Liebherr 130 EC-B 6", rendered.text)

    def test_matching_override_survives_context_changes(self):
        catalog = load_template_catalog()
        paragraph = next(item for item in catalog[0].paragraphs if item.paragraph_id == "general.purpose")
        override = TemplateOverride(paragraph.paragraph_id, paragraph.version, "Согласованный пользователем текст.")

        first = render_template_text("general", {"object_name": "Корпус 1", "crane_model": "Кран 1"}, [override])
        second = render_template_text("general", {"object_name": "Корпус 2", "crane_model": "Кран 2"}, [override])

        self.assertIn("Согласованный пользователем текст.", first.text)
        self.assertIn("Согласованный пользователем текст.", second.text)
        self.assertEqual(first.override_conflicts, ())
        self.assertEqual(second.override_conflicts, ())

    def test_changed_base_version_reports_conflict_and_keeps_base_text(self):
        stale = TemplateOverride("general.purpose", "0.1", "Устаревшая ручная редакция")

        rendered = render_template_text(
            "general",
            {"object_name": "Корпус", "crane_model": "Liebherr 130 EC-B 6"},
            [stale],
        )

        self.assertEqual(len(rendered.override_conflicts), 1)
        self.assertEqual(rendered.override_conflicts[0].paragraph_id, "general.purpose")
        self.assertNotIn("Устаревшая ручная редакция", rendered.text)
        self.assertIn("Корпус", rendered.text)

    def test_duplicate_and_orphan_overrides_are_reported_not_silently_ignored(self):
        catalog = load_template_catalog()
        paragraph = next(item for item in catalog[0].paragraphs if item.paragraph_id == "general.purpose")
        overrides = [
            TemplateOverride(paragraph.paragraph_id, paragraph.version, "Первая редакция"),
            TemplateOverride(paragraph.paragraph_id, paragraph.version, "Вторая редакция"),
            TemplateOverride("removed.paragraph", "1.0", "Сирота"),
        ]

        rendered = render_template_text(
            "general",
            {"object_name": "Корпус", "crane_model": "Кран"},
            overrides,
            catalog=catalog,
        )

        reasons = {(item.paragraph_id, item.reason) for item in rendered.override_conflicts}
        self.assertIn((paragraph.paragraph_id, "duplicate_override"), reasons)
        self.assertIn(("removed.paragraph", "orphan_override"), reasons)
        self.assertNotIn("Первая редакция", rendered.text)
        self.assertNotIn("Вторая редакция", rendered.text)


if __name__ == "__main__":
    unittest.main()
