from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.engine import (  # noqa: E402
    IntegrationStatus,
    default_release_index,
    load_catalog_v3,
    release_blockers,
    scenario_for_report,
    verify_scenario_v21,
    verify_scenarios_v21,
)
from crane_plan.models import Load, Placement, ProjectInput, ScenarioResult, SiteInput, WorkPoint  # noqa: E402


CATALOG = load_catalog_v3(ROOT / "02_processed_data/cranes/crane_configurations_v3.json")


def make_project(*, verified: bool = True, load_kg: float = 1200, level_m: float = 20) -> ProjectInput:
    return ProjectInput(
        "Дом",
        "Москва",
        2026,
        "",
        "",
        -3,
        27,
        SiteInput(
            [(-80, -80), (80, -80), (80, 80), (-80, 80)],
            [(20, -10), (40, -10), (40, 10), (20, 10)],
            unloading_zone=[(-20, -5), (-10, -5), (-10, 5), (-20, 5)],
            storage_zones=[[(-10, -5), (0, -5), (0, 5), (-10, 5)]],
            min_crane_to_building_m=1,
            max_crane_to_building_m=25,
        ),
        [Load("Бадья", load_kg, 100, 1.8, 1.8, 2.4, 12)],
        [WorkPoint(25, 0, level_m, 0, "Подача 1")],
        loads_verified=verified,
    )


def make_scenario(*, jib: float = 60, crane_id: str = "LIEBHERR-130-ECB-6-60") -> ScenarioResult:
    return ScenarioResult(
        "PASS",
        [
            Placement(
                crane_id,
                "130 EC-B 6",
                0,
                0,
                [0],
                25,
                25,
                jib,
                max_free_standing_height_m=44.4,
                accepted_crane_height_m=44.4,
            )
        ],
        [],
        [],
    )


def verify(project=None, scenario=None, *, run_id="RUN-1", created_at="2026-10-20T10:00:00+03:00"):
    return verify_scenario_v21(
        project or make_project(),
        scenario or make_scenario(),
        CATALOG,
        scenario_index=0,
        run_id=run_id,
        created_at=created_at,
    )


class EngineIntegrationTests(unittest.TestCase):
    def test_valid_confirmed_scenario_is_verified(self):
        result = verify()
        self.assertEqual(result.status, IntegrationStatus.VERIFIED)
        self.assertTrue(result.release_allowed)
        self.assertIsNotNone(result.protocol)

    def test_unconfirmed_load_requires_expert_review(self):
        result = verify(make_project(verified=False))
        self.assertEqual(result.status, IntegrationStatus.EXPERT_REVIEW_REQUIRED)
        self.assertFalse(result.release_allowed)

    def test_short_jib_is_verified_with_conditions(self):
        result = verify(scenario=make_scenario(jib=50))
        self.assertEqual(result.status, IntegrationStatus.VERIFIED_WITH_CONDITIONS)
        self.assertTrue(result.release_allowed)
        self.assertTrue(any("консерватив" in message.lower() for message in result.messages))

    def test_insufficient_capacity_is_rejected_with_measured_values(self):
        result = verify(make_project(load_kg=7000))
        self.assertEqual(result.status, IntegrationStatus.REJECTED)
        self.assertFalse(result.release_allowed)
        self.assertTrue(any("7100" in message and "6000" in message for message in result.messages))

    def test_insufficient_height_is_rejected_with_measured_values(self):
        result = verify(make_project(level_m=50))
        self.assertEqual(result.status, IntegrationStatus.REJECTED)
        self.assertTrue(any("54.4" in message and "44.4" in message for message in result.messages))

    def test_tie_ins_remain_expert_case(self):
        scenario = make_scenario()
        scenario.placements[0].tie_in_levels_m = [38.4]
        result = verify(scenario=scenario)
        self.assertEqual(result.status, IntegrationStatus.EXPERT_REVIEW_REQUIRED)
        self.assertTrue(any("TIE_INS_NOT_VERIFIED" in message for message in result.messages))

    def test_protective_screen_condition_is_preserved(self):
        project = make_project()
        project.protective_screen_possible = True
        project.site.boundary = [(-20, -20), (30, -20), (30, 20), (-20, 20)]
        result = verify(project)
        self.assertEqual(result.status, IntegrationStatus.VERIFIED_WITH_CONDITIONS)
        self.assertTrue(any("DANGER_ZONE_PROTECTED" in message for message in result.messages))

    def test_unknown_crane_is_expert_case_with_code(self):
        result = verify(scenario=make_scenario(crane_id="OTHER"))
        self.assertEqual(result.status, IntegrationStatus.EXPERT_REVIEW_REQUIRED)
        self.assertTrue(any("CONFIGURATION_NOT_IN_V3_CATALOG" in message for message in result.messages))

    def test_multiple_storage_zones_are_expert_case(self):
        project = make_project()
        project.site.storage_zones.append([(1, 1), (2, 1), (2, 2), (1, 2)])
        result = verify(project)
        self.assertEqual(result.status, IntegrationStatus.EXPERT_REVIEW_REQUIRED)
        self.assertTrue(any("LOGISTICS_SOURCE_AMBIGUOUS" in message for message in result.messages))

    def test_batch_isolates_exception_in_one_scenario(self):
        real = verify(make_project(), make_scenario())
        with patch("crane_plan.engine.integration.verify_scenario_v21", side_effect=[RuntimeError("boom"), real]):
            results = verify_scenarios_v21(
                make_project(),
                [make_scenario(), make_scenario()],
                CATALOG,
                run_id="RUN",
                created_at="2026-10-20T10:00:00+03:00",
            )
        self.assertEqual(results[0].status, IntegrationStatus.EXPERT_REVIEW_REQUIRED)
        self.assertEqual(results[1].status, IntegrationStatus.VERIFIED)

    def test_protocol_content_hashes_are_repeatable(self):
        first = verify(run_id="RUN-A", created_at="2026-10-20T10:00:00+03:00")
        second = verify(run_id="RUN-B", created_at="2026-10-21T10:00:00+03:00")
        self.assertEqual(first.protocol.input_sha256, second.protocol.input_sha256)
        self.assertEqual(first.protocol.result_sha256, second.protocol.result_sha256)

    def test_serialized_summary_contains_status_messages_and_hashes(self):
        payload = verify().to_dict()
        self.assertEqual(payload["status"], "VERIFIED")
        self.assertEqual(len(payload["input_sha256"]), 64)
        self.assertEqual(len(payload["result_sha256"]), 64)
        self.assertEqual(payload["run_id"], "RUN-1")
        self.assertIsInstance(payload["messages"], list)

    def test_default_selection_and_release_blockers(self):
        expert = verify(make_project(verified=False))
        rejected = verify(make_project(load_kg=7000))
        verified = verify()
        self.assertEqual(default_release_index((expert, verified)), 1)
        self.assertEqual(default_release_index((expert, rejected)), 0)
        self.assertIsNone(default_release_index(()))
        self.assertTrue(release_blockers((expert,), None))
        self.assertTrue(release_blockers((expert,), 0))
        self.assertTrue(release_blockers((expert,), 4))
        self.assertEqual(release_blockers((verified,), 0), ())

    def test_report_scenario_is_copy_with_conditions(self):
        scenario = make_scenario(jib=50)
        verification = verify(scenario=scenario)
        report_scenario = scenario_for_report(scenario, verification)
        self.assertIsNot(report_scenario, scenario)
        self.assertEqual(scenario.warnings, [])
        self.assertTrue(any("консерватив" in warning.lower() for warning in report_scenario.warnings))


if __name__ == "__main__":
    unittest.main()
