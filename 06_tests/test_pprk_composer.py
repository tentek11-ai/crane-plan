import sys
import unittest
import importlib
from unittest.mock import patch
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.pprk_assets import load_asset_manifest  # noqa: E402
from crane_plan.pprk_composer import (  # noqa: E402
    compose_pprk,
    check_completeness,
)
from crane_plan.pprk_context import PPRKContext, build_pprk_context  # noqa: E402
from crane_plan.pprk_models import (  # noqa: E402
    ApprovalSlot,
    ExternalDocument,
    PPRKReleaseConfig,
    ReleaseStatus,
    TemplateOverride,
)
from crane_plan.pprk_templates import MISSING_VALUE_TEMPLATE, load_template_catalog  # noqa: E402


def complete_values(**changes):
    values = {
        "object_name": "Жилой дом",
        "object_address": "г. Москва, ул. Проектная, д. 1",
        "crane_model": "Liebherr 130 EC-B 6",
        "crane_count": 1,
        "crane_configurations": ("Liebherr 130 EC-B 6; стрела 60 м",),
        "building_height_m": 61.0,
        "floors": 20,
        "jib_length_m": (60.0,),
        "hook_height_m": (63.4,),
        "max_capacity_t": 6.0,
        "work_radii_m": (42.0,),
        "tower_sections": (4,),
        "tie_levels_m": (),
        "active_loads": ("Опалубка",),
        "load_masses_kg": (1800.0,),
        "rigging_masses_kg": (120.0,),
        "lift_counts": (120,),
        "max_load_length_m": 2.5,
        "storage_zone_count": 1,
        "unloading_zone": ((0.0, 0.0), (3.0, 0.0), (3.0, 5.0)),
        "sozr_points": ("Т1", "Т2"),
        "route_register": ("OP-W1-L1",),
        "project_basis": "Задание заказчика",
        "plan_sheet_refs": "ГЧ-01, ГЧ-02",
        "responsible_fire_safety": "назначается приказом",
        "max_wind_speed_m_s": 10.0,
        "fall_protection_system": "страховочная система с анкерной линией",
        "power_supply_scheme": "от ВРУ по самостоятельной линии",
        "waste_plan": "контейнерный вывоз по графику",
        "external_document_register": "паспорта и акты по ведомости",
    }
    values.update(changes)
    return values


def make_context(**value_changes):
    values = complete_values(**value_changes)
    return PPRKContext(
        object_name=str(values["object_name"]),
        object_address=str(values["object_address"]),
        organization="ООО Проект",
        project_code="ППРК-01",
        verification_status="VERIFIED",
        protocol_run_id="RUN-1",
        protocol_input_sha256="a" * 64,
        protocol_result_sha256="b" * 64,
        crane_ids=tuple(f"CRANE-{index + 1}" for index in range(int(values["crane_count"]))),
        operation_ids=("OP-W1-L1",),
        values=values,
        traces=(),
        completeness_issues=(),
    )


def compose(context=None, config=None):
    return compose_pprk(
        context or make_context(),
        load_template_catalog(),
        load_asset_manifest(),
        config or PPRKReleaseConfig(),
    )


def complete_release(*, status=ReleaseStatus.PRELIMINARY, approvals=None, **changes):
    values = dict(
        title="ППРк на возведение монолитного здания",
        object_address="г. Москва, ул. Проектная, д. 1",
        developer_organization="ООО Проект",
        project_code="ППРК-01",
        developer_position="Главный инженер проекта",
        developer_name="Иванов И.И.",
        developer_date="2026-11-04",
        manager_position="Технический директор",
        manager_name="Петров П.П.",
        manager_date="2026-11-04",
        issue_city="Москва",
        issue_year=2026,
        issue_date="2026-11-04",
        lifting_equipment_type="Башенный кран",
        project_basis="Задание заказчика",
        plan_sheet_refs="ГЧ-01, ГЧ-02",
        responsible_fire_safety="назначается приказом",
        max_wind_speed_m_s=10.0,
        fall_protection_system="анкерная линия и страховочная привязь",
        power_supply_scheme="самостоятельная линия от ВРУ",
        waste_plan="контейнерный вывоз",
        external_document_register="по ведомости приложений",
        status=status,
    )
    values.update(changes)
    supplied = list(values.get("external_documents", ()))
    supplied_ids = {d.document_id for d in supplied}
    values["external_documents"] = [*verified_required_documents(), *supplied]
    values["external_documents"] = [d for d in values["external_documents"]
        if d in supplied or d.document_id not in supplied_ids]
    if approvals is not None:
        values["approvals"] = approvals
    return PPRKReleaseConfig(**values)


def verified_required_documents():
    from crane_plan.pprk_merge import verify_external_revision
    from reportlab.pdfgen.canvas import Canvas
    directory = ROOT / "tmp/test-temp/mandatory-documents"
    directory.mkdir(parents=True, exist_ok=True)
    documents = []
    for document_id in ("crane_passport", "foundation_project", "erection_project"):
        path = directory / f"{document_id}.pdf"
        if not path.exists():
            canvas = Canvas(str(path), invariant=1)
            canvas.drawString(50, 500, f"CONTROLLED TEST {document_id}")
            canvas.showPage(); canvas.save()
        documents.append(verify_external_revision(ExternalDocument(document_id, f"Испытательный {document_id}",
            present=True, attachment_path=str(path))))
    return documents


def complete_approvals():
    return [
        ApprovalSlot("Организация", {1: "Проверил", 2: "Утвердил"}.get(index, "Должность"), f"Фамилия {index}", "Подпись", "2026-11-04")
        for index in range(1, 9)
    ]


class PPRKComposerTests(unittest.TestCase):
    def setUp(self):
        # Controlled verified normative evidence isolates the approval/external
        # matrix; the real unresolved registry is tested by final hardening.
        from crane_plan.pprk_regulations import load_release_regulations
        records = tuple(replace(r, verification_status="VERIFIED_SOURCE") for r in load_release_regulations())
        self.registry_patch = patch("crane_plan.pprk_composer.load_release_regulations", return_value=records)
        self.registry_patch.start()
        self.addCleanup(self.registry_patch.stop)
    def test_calculated_drawings_aggregate_resolves_to_concrete_physical_targets(self):
        bundle = compose()
        target_ids = {sheet.sheet_id for part in bundle.parts for sheet in part.sheets}
        self.assertNotIn("drawing.CALCULATED_DRAWINGS", target_ids)
        for part in bundle.parts:
            for sheet in part.sheets:
                self.assertNotIn("drawing.CALCULATED_DRAWINGS", sheet.reference_keys)
                self.assertTrue(all(key in target_ids for key in sheet.reference_keys if key.startswith("drawing.")))

    def test_first_four_service_pages_and_numbering_are_exact(self):
        bundle = compose()

        self.assertEqual(
            tuple(part.part_id for part in bundle.parts[:4]),
            ("service.title", "service.approvals", "service.familiarization", "service.contents"),
        )
        approvals = bundle.sheet("service.approvals")
        self.assertEqual(len(approvals.approval_slots), 8)
        note_sheets = [sheet for part in bundle.parts if part.kind != "graphical" for sheet in part.sheets]
        self.assertEqual([sheet.page_number for sheet in note_sheets], list(range(1, len(note_sheets) + 1)))
        graphical = [sheet for part in bundle.parts if part.kind == "graphical" for sheet in part.sheets]
        self.assertEqual(
            [sheet.designation for sheet in graphical],
            [f"ГЧ-{index:02d}" for index in range(1, len(graphical) + 1)],
        )
        self.assertTrue(graphical)
        self.assertTrue(all(sheet.page_number is None for sheet in graphical))
        target_ids = {sheet.sheet_id for part in bundle.parts for sheet in part.sheets}
        self.assertEqual({entry.target_id for entry in bundle.contents}, target_ids)
        referenced_ids = {
            reference
            for part in bundle.parts
            for sheet in part.sheets
            for reference in sheet.reference_keys
        }
        self.assertTrue(referenced_ids)
        self.assertTrue(referenced_ids <= target_ids)

    def test_conditional_sections_and_cards_follow_project_values(self):
        baseline = compose()
        extended = compose(
            make_context(
                crane_count=2,
                crane_configurations=("130 EC-B 6", "130 EC-B 6"),
                max_load_length_m=6.0,
                bucket_volume_m3=1.0,
                receiving_platform_ids=("ПП-1",),
                opening_ids=("ПР-1",),
                joint_work_schedule=("Этап 1",),
            )
        )

        self.assertNotIn("concrete_bucket", baseline.included_section_ids)
        self.assertNotIn("long_loads", baseline.included_section_ids)
        self.assertIn("concrete_bucket", extended.included_section_ids)
        self.assertIn("long_loads", extended.included_section_ids)
        self.assertIn("joint_operations", extended.included_section_ids)
        self.assertIn("receiving_platforms", extended.included_section_ids)
        self.assertIn("opening_delivery", extended.included_section_ids)
        bucket_part = extended.part("section.concrete_bucket")
        self.assertIn("slinging", {asset for sheet in bucket_part.sheets for asset in sheet.asset_ids})
        self.assertIn(("long_loads", "condition:has_load_longer_than_3m"), extended.inclusion_reasons)
        self.assertIn(("concrete_bucket", "condition:has_concrete_bucket"), extended.inclusion_reasons)

    def test_recomposition_has_no_stale_or_gapped_references(self):
        with_optional = compose(make_context(bucket_volume_m3=1.0, max_load_length_m=4.0))
        rebuilt = compose(make_context(bucket_volume_m3=None, max_load_length_m=2.0))

        self.assertIn("concrete_bucket", with_optional.included_section_ids)
        self.assertNotIn("concrete_bucket", rebuilt.included_section_ids)
        self.assertNotIn("long_loads", rebuilt.included_section_ids)
        rebuilt_ids = {sheet.sheet_id for part in rebuilt.parts for sheet in part.sheets}
        self.assertTrue(all(entry.target_id in rebuilt_ids for entry in rebuilt.contents))
        note_pages = [
            sheet.page_number
            for part in rebuilt.parts
            if part.kind != "graphical"
            for sheet in part.sheets
        ]
        self.assertEqual(note_pages, list(range(1, len(note_pages) + 1)))

    def test_missing_address_is_visible_and_prevents_production_status(self):
        config = PPRKReleaseConfig(status=ReleaseStatus.PRODUCTION)
        bundle = compose(make_context(object_address=""), config)

        title = bundle.sheet("service.title")
        self.assertEqual(dict(title.fields)["object_address"], MISSING_VALUE_TEMPLATE.format(name="object_address"))
        self.assertFalse(bundle.production_allowed)
        self.assertTrue(bundle.preliminary_available)
        self.assertEqual(bundle.effective_status, ReleaseStatus.REVIEW)
        self.assertIn("PPRK_ADDRESS_REQUIRED", {issue.code for issue in check_completeness(bundle)})

    def test_missing_tie_project_blocks_advanced_release(self):
        context = make_context(tie_levels_m=(38.4,))
        preliminary = compose(
            context,
            complete_release(status=ReleaseStatus.PRELIMINARY, approvals=complete_approvals()),
        )
        final = compose(
            context,
            complete_release(status=ReleaseStatus.PRODUCTION, approvals=complete_approvals()),
        )
        supplied = compose(
            context,
            complete_release(
                status=ReleaseStatus.PRODUCTION,
                approvals=complete_approvals(),
                external_documents=[
                    ExternalDocument(
                        "tie_in_project",
                        "Проект крепления крана к зданию",
                        required=True,
                        present=True,
                        verification_status="VERIFIED",
                        verified_sha256="a" * 64,
                    )
                ],
            ),
        )

        self.assertTrue(preliminary.preliminary_available)
        self.assertEqual(preliminary.effective_status, ReleaseStatus.PRELIMINARY)
        self.assertIn("PPRK_TIE_PROJECT_REQUIRED", {issue.code for issue in check_completeness(preliminary)})
        self.assertFalse(final.production_allowed)
        self.assertEqual(final.effective_status, ReleaseStatus.REVIEW)
        self.assertNotIn("PPRK_TIE_PROJECT_REQUIRED", {issue.code for issue in check_completeness(supplied)})
        self.assertTrue(supplied.production_allowed)
        self.assertEqual(supplied.effective_status, ReleaseStatus.PRODUCTION)

    def test_required_section_cannot_be_silently_excluded(self):
        config = PPRKReleaseConfig(excluded_section_ids=["general"])
        bundle = compose(config=config)

        self.assertIn("general", bundle.included_section_ids)
        self.assertIn("PPRK_REQUIRED_SECTION_EXCLUSION", {issue.code for issue in check_completeness(bundle)})
        self.assertIn(("general", "required:no_expert_decision"), bundle.inclusion_reasons)

    def test_user_override_is_preserved_in_composed_section(self):
        replacement = "Пользовательский текст для {object_name}; кран {crane_model}."
        config = PPRKReleaseConfig(
            overrides=[TemplateOverride("general.purpose", "1.0", replacement)]
        )
        bundle = compose(config=config)

        part = bundle.part("section.general")
        self.assertIn("Пользовательский текст для Жилой дом", part.rendered_text)
        self.assertFalse(any(issue.code == "PPRK_OVERRIDE_CONFLICT" for issue in check_completeness(bundle)))

    def test_real_verified_pipeline_fills_explicit_template_inputs(self):
        engine_fixtures = importlib.import_module("06_tests.test_engine_integration")
        project = engine_fixtures.make_project()
        project.organization = "ООО Проект"
        project.project_code = "ППРК-01"
        release = complete_release(bucket_volume_m3=1.0)
        project.pprk_release = release
        scenario = engine_fixtures.make_scenario()
        verification = engine_fixtures.verify(project, scenario)

        context = build_pprk_context(project, scenario, verification)
        bundle = compose_pprk(
            context,
            load_template_catalog(),
            load_asset_manifest(),
            release,
        )

        self.assertFalse(
            [issue for issue in check_completeness(bundle) if issue.code == "PPRK_TEMPLATE_VALUE_REQUIRED"]
        )
        self.assertIn("concrete_bucket", bundle.included_section_ids)

    def test_required_assets_fail_closed_and_preserve_verified_identity(self):
        missing = compose_pprk(make_context(), load_template_catalog(), (), complete_release())
        self.assertIn("PPRK_ASSET_REQUIRED", {issue.code for issue in check_completeness(missing)})

        records = load_asset_manifest()
        slinging = next(record for record in records if record.asset_id == "slinging")
        for corrupt in (
            replace(slinging, sha256="0" * 64),
            replace(slinging, quality_status="unverified"),
            replace(slinging, category="storage"),
        ):
            with self.subTest(corrupt=corrupt):
                assets = tuple(corrupt if item.asset_id == "slinging" else item for item in records)
                bundle = compose_pprk(make_context(), load_template_catalog(), assets, complete_release())
                self.assertIn("PPRK_ASSET_INVALID", {issue.code for issue in check_completeness(bundle)})

        accepted = compose_pprk(make_context(), load_template_catalog(), records, complete_release())
        sheet = accepted.sheet("appendix.SLINGING_CARDS")
        identity = next(item for item in sheet.asset_identities if item.asset_id == "slinging")
        self.assertEqual(identity.sha256, slinging.sha256)
        self.assertEqual(identity.category, "slinging")
        self.assertEqual(identity.quality_status, "verified")

    def test_asset_id_cannot_be_rebound_to_another_verified_clip(self):
        records = load_asset_manifest()
        slinging = next(record for record in records if record.asset_id == "slinging")
        storage = next(record for record in records if record.asset_id == "storage")
        rebound = replace(
            slinging,
            file_name=storage.file_name,
            sha256=storage.sha256,
            pixel_width=storage.pixel_width,
            pixel_height=storage.pixel_height,
        )
        supplied = tuple(rebound if item.asset_id == "slinging" else item for item in records)

        bundle = compose_pprk(
            make_context(),
            load_template_catalog(),
            supplied,
            complete_release(
                status=ReleaseStatus.PRODUCTION,
                approvals=complete_approvals(),
            ),
        )

        self.assertIn("PPRK_ASSET_INVALID", {issue.code for issue in check_completeness(bundle)})
        self.assertFalse(bundle.production_allowed)
        self.assertFalse(bundle.sheet("appendix.SLINGING_CARDS").asset_identities)

    def test_asset_binding_rejects_any_canonical_record_metadata_mutation(self):
        records = load_asset_manifest()
        slinging = next(record for record in records if record.asset_id == "slinging")
        mutations = (
            replace(slinging, title="Подмененное название"),
            replace(slinging, source_page=slinging.source_page + 1),
            replace(
                slinging,
                crop_box=(
                    slinging.crop_box[0] + 1,
                    *slinging.crop_box[1:],
                ),
            ),
            replace(slinging, source_kind="generated"),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                supplied = tuple(
                    mutation if item.asset_id == "slinging" else item for item in records
                )
                bundle = compose_pprk(
                    make_context(),
                    load_template_catalog(),
                    supplied,
                    complete_release(
                        status=ReleaseStatus.PRODUCTION,
                        approvals=complete_approvals(),
                    ),
                )
                self.assertIn(
                    "PPRK_ASSET_INVALID",
                    {issue.code for issue in check_completeness(bundle)},
                )
                self.assertFalse(bundle.production_allowed)

    def test_tie_project_reference_resolves_to_verified_external_document(self):
        config = complete_release(
            external_documents=[
                ExternalDocument(
                    "tie_in_project",
                    "Проект крепления крана",
                    required=True,
                    present=True,
                    verification_status="VERIFIED",
                    attachment_path="attachments/tie.pdf",
                    verified_sha256="a" * 64,
                )
            ]
        )
        bundle = compose(make_context(tie_levels_m=(38.4,)), config)

        construction = bundle.sheet("section.construction_stages")
        self.assertIn("external.tie_in_project", construction.reference_keys)
        self.assertNotIn("appendix.TIE_IN_PROJECT", {sheet.sheet_id for part in bundle.parts for sheet in part.sheets})
        self.assertEqual(
            len([part for part in bundle.parts if part.part_id == "external.tie_in_project"]),
            1,
        )

    def test_approval_sheet_always_has_eight_blocks_and_guards_final_status(self):
        for count in (0, 1, 10):
            with self.subTest(count=count):
                approvals = [ApprovalSlot(organization=f"Организация {index}") for index in range(count)]
                bundle = compose(config=complete_release(status=ReleaseStatus.PRELIMINARY, approvals=approvals))
                self.assertEqual(len(bundle.sheet("service.approvals").approval_slots), 8)

        incomplete = compose(
            config=complete_release(status=ReleaseStatus.APPROVED, approvals=[ApprovalSlot()])
        )
        complete = compose(
            config=complete_release(status=ReleaseStatus.APPROVED, approvals=complete_approvals())
        )
        self.assertIn("PPRK_APPROVALS_INCOMPLETE", {issue.code for issue in check_completeness(incomplete)})
        self.assertNotEqual(incomplete.effective_status, ReleaseStatus.APPROVED)
        self.assertEqual(complete.effective_status, ReleaseStatus.APPROVED)

    def test_whitespace_only_approval_slots_do_not_unlock_final_status(self):
        whitespace = [ApprovalSlot(" ", "\t", "  ", "\n", " ") for _ in range(8)]
        for status in (ReleaseStatus.APPROVED, ReleaseStatus.PRODUCTION):
            with self.subTest(status=status):
                bundle = compose(config=complete_release(status=status, approvals=whitespace))
                self.assertIn(
                    "PPRK_APPROVALS_INCOMPLETE",
                    {issue.code for issue in check_completeness(bundle)},
                )
                self.assertNotEqual(bundle.effective_status, status)

    def test_deserialized_null_and_zero_width_approvals_cannot_unlock_release(self):
        base = complete_release(
            status=ReleaseStatus.PRODUCTION,
            approvals=complete_approvals(),
        ).to_dict()
        bad_rows = (
            [
                {
                    "organization": None,
                    "position": None,
                    "full_name": None,
                    "signature": None,
                    "date": None,
                }
                for _ in range(8)
            ],
            [
                {
                    "organization": "\u200b",
                    "position": "\u200b\u00a0",
                    "full_name": "\u200b",
                    "signature": "\u200b",
                    "date": "\u200b",
                }
                for _ in range(8)
            ],
        )
        for approvals in bad_rows:
            with self.subTest(approvals=approvals[0]):
                payload = dict(base)
                payload["approvals"] = approvals
                config = PPRKReleaseConfig.from_dict(payload)
                bundle = compose(config=config)
                self.assertIn(
                    "PPRK_APPROVALS_INCOMPLETE",
                    {issue.code for issue in check_completeness(bundle)},
                )
                self.assertFalse(bundle.production_allowed)
                self.assertNotEqual(bundle.effective_status, ReleaseStatus.PRODUCTION)

    def test_status_matrix_separates_technical_approval_and_external_guards(self):
        expected_technical = {
            ReleaseStatus.PRELIMINARY: ReleaseStatus.PRELIMINARY,
            ReleaseStatus.REVIEW: ReleaseStatus.REVIEW,
            ReleaseStatus.COORDINATION: ReleaseStatus.REVIEW,
            ReleaseStatus.APPROVED: ReleaseStatus.REVIEW,
            ReleaseStatus.PRODUCTION: ReleaseStatus.REVIEW,
        }
        for requested, effective in expected_technical.items():
            with self.subTest(kind="technical", requested=requested):
                bundle = compose(
                    make_context(object_address=""),
                    complete_release(status=requested, object_address=""),
                )
                self.assertEqual(bundle.effective_status, effective)

        for requested in ReleaseStatus:
            with self.subTest(kind="external", requested=requested):
                bundle = compose(
                    make_context(tie_levels_m=(38.4,)),
                    complete_release(status=requested, approvals=complete_approvals()),
                )
                expected = ReleaseStatus.REVIEW if requested in (ReleaseStatus.COORDINATION, ReleaseStatus.APPROVED, ReleaseStatus.PRODUCTION) else requested
                self.assertEqual(bundle.effective_status, expected)

        approval_blocked = compose(
            config=complete_release(status=ReleaseStatus.PRODUCTION, approvals=[ApprovalSlot()])
        )
        self.assertEqual(approval_blocked.effective_status, ReleaseStatus.COORDINATION)

    def test_title_has_full_service_payload_and_guards_missing_fields(self):
        config = complete_release(approvals=complete_approvals())
        bundle = compose(config=config)
        fields = dict(bundle.sheet("service.title").fields)
        expected = {
            "title",
            "lifting_equipment_type",
            "crane_model",
            "crane_configurations",
            "approval_marks",
            "object_name",
            "object_address",
            "organization",
            "project_code",
            "developer_position",
            "developer_name",
            "developer_date",
            "manager_position",
            "manager_name",
            "manager_date",
            "issue_city",
            "issue_year",
            "issue_date",
        }
        self.assertEqual(set(fields), expected)
        self.assertTrue(all(fields[name] for name in expected))

        missing = compose(config=complete_release(status=ReleaseStatus.APPROVED, developer_name=""))
        self.assertIn("PPRK_TITLE_FIELD_REQUIRED", {issue.code for issue in check_completeness(missing)})
        self.assertNotEqual(missing.effective_status, ReleaseStatus.APPROVED)

    def test_unknown_manual_section_ids_are_explicit_configuration_errors(self):
        config = complete_release(
            status=ReleaseStatus.APPROVED,
            included_section_ids=["removed.section"],
            excluded_section_ids=["unknown.section"],
        )
        bundle = compose(config=config)

        self.assertIn("PPRK_UNKNOWN_SECTION_ID", {issue.code for issue in check_completeness(bundle)})
        self.assertNotEqual(bundle.effective_status, ReleaseStatus.APPROVED)


if __name__ == "__main__":
    unittest.main()

