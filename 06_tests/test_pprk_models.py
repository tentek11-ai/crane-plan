import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.pprk_models import (  # noqa: E402
    ApprovalSlot,
    CompletenessIssue,
    ExternalDocument,
    PPRKReleaseConfig,
    ReleaseStatus,
    TemplateOverride,
)


class PPRKReleaseModelTests(unittest.TestCase):
    def test_new_release_is_preliminary_with_eight_blank_approval_slots(self):
        release = PPRKReleaseConfig()

        self.assertEqual(release.status, ReleaseStatus.PRELIMINARY)
        self.assertEqual(len(release.approvals), 8)
        self.assertTrue(all(slot.organization == "" for slot in release.approvals))
        self.assertIsNot(release.approvals[0], release.approvals[1])

    def test_release_round_trip_preserves_title_external_documents_and_overrides(self):
        release = PPRKReleaseConfig(
            title="ППРк на возведение монолитного здания",
            object_address="г. Москва, 1-й Тружеников пер.",
            developer_organization="ООО Проект",
            project_code="ППРк-01",
            issue_city="Москва",
            issue_year=2026,
            approvals=[ApprovalSlot(organization="Генподрядчик", position="ГИП", full_name="Иванов И.И.")],
            included_section_ids=["general", "safety"],
            excluded_section_ids=["bucket"],
            overrides=[TemplateOverride("safety.p1", "2.0", "Согласованный текст")],
            external_documents=[
                ExternalDocument(
                    "foundation",
                    "Проект фундамента крана",
                    required=True,
                    present=True,
                    number="КР-12",
                    organization="ООО Конструктор",
                    attachment_path="attachments/foundation.pdf",
                )
            ],
            status=ReleaseStatus.REVIEW,
        )

        restored = PPRKReleaseConfig.from_dict(release.to_dict())

        self.assertEqual(restored, release)
        self.assertEqual(restored.status, ReleaseStatus.REVIEW)
        self.assertEqual(restored.external_documents[0].number, "КР-12")
        self.assertEqual(restored.overrides[0].replacement_text, "Согласованный текст")

    def test_release_loader_ignores_unknown_forward_fields(self):
        restored = PPRKReleaseConfig.from_dict(
            {
                "title": "Проект",
                "status": "PRELIMINARY",
                "future_release_field": {"enabled": True},
                "approvals": [{"organization": "Заказчик", "future_slot_field": 7}],
                "external_documents": [
                    {"document_id": "passport", "title": "Паспорт крана", "future_document_field": "x"}
                ],
                "overrides": [
                    {
                        "paragraph_id": "general.p1",
                        "base_version": "1.0",
                        "replacement_text": "Текст",
                        "future_override_field": False,
                    }
                ],
            }
        )

        self.assertEqual(restored.title, "Проект")
        self.assertEqual(restored.approvals[0].organization, "Заказчик")
        self.assertEqual(restored.external_documents[0].document_id, "passport")
        self.assertEqual(restored.overrides[0].paragraph_id, "general.p1")

    def test_invalid_status_falls_back_to_preliminary_without_claiming_approval(self):
        restored = PPRKReleaseConfig.from_dict({"status": "FUTURE_AUTO_APPROVED"})

        self.assertEqual(restored.status, ReleaseStatus.PRELIMINARY)

    def test_release_round_trip_preserves_full_template_and_title_inputs(self):
        release = PPRKReleaseConfig(
            lifting_equipment_type="Башенный кран",
            project_basis="Задание заказчика",
            plan_sheet_refs="ГЧ-01, ГЧ-02",
            responsible_fire_safety="назначается приказом",
            max_wind_speed_m_s=10.0,
            fall_protection_system="анкерная линия и страховочная привязь",
            power_supply_scheme="самостоятельная линия от ВРУ",
            waste_plan="контейнерный вывоз",
            external_document_register="по ведомости приложений",
            receiving_platform_ids=["ПП-1"],
            opening_ids=["ПР-1"],
            bucket_volume_m3=1.0,
            developer_date="2026-11-04",
            manager_date="2026-11-04",
        )

        restored = PPRKReleaseConfig.from_dict(release.to_dict())

        self.assertEqual(restored, release)
        self.assertEqual(restored.receiving_platform_ids, ["ПП-1"])
        self.assertEqual(restored.opening_ids, ["ПР-1"])

    def test_completeness_issue_records_blocking_scope(self):
        issue = CompletenessIssue("ADDRESS_REQUIRED", "Не заполнен адрес", True, "object_address")

        self.assertTrue(issue.blocking)
        self.assertEqual(issue.field_id, "object_address")


if __name__ == "__main__":
    unittest.main()
