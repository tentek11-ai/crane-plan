from __future__ import annotations

import unittest

from crane_plan.admissible_area import calculate_admissible_area, evaluate_candidate
from crane_plan.models import CraneConfiguration, Load, ProjectInput, SiteInput, WorkPoint


def make_config() -> CraneConfiguration:
    return CraneConfiguration(
        id="TEST-20",
        model="Test crane",
        priority=1,
        jib_length_m=20.0,
        max_capacity_kg=6000.0,
        max_free_standing_hook_height_m=50.0,
        capacity_curve=((5.0, 6000.0), (20.0, 3000.0)),
        source="test load chart, table 1",
    )


def make_project(*, load_kg=2800.0, rigging_kg=200.0, level_m=0.0, restricted=None) -> ProjectInput:
    return ProjectInput(
        name="article-boundary-test",
        city="test",
        year=2026,
        author="",
        email="",
        pit_bottom_m=0.0,
        parapet_m=50.0,
        site=SiteInput(
            boundary=[(-30.0, -30.0), (30.0, -30.0), (30.0, 30.0), (-30.0, 30.0)],
            building=[(19.0, -1.0), (21.0, -1.0), (21.0, 1.0), (19.0, 1.0)],
            restricted_zones=restricted or [],
            min_crane_to_building_m=1.0,
            max_crane_to_building_m=25.0,
        ),
        loads=[Load("critical", load_kg, rigging_kg, 1.0, 1.0, 1.0)],
        work_points=[WorkPoint(20.0, 0.0, level_m, 0, "WP-1")],
        protective_screen_possible=True,
        tie_ins_possible=False,
        restricted_zones_confirmed=True,
    )


class CandidateEvaluationTests(unittest.TestCase):
    def test_exact_reach_and_capacity_boundaries_pass(self):
        result = evaluate_candidate(make_project(), make_config(), (0.0, 0.0))
        self.assertTrue(result.passed)
        self.assertEqual(result.reason_codes, ())
        self.assertAlmostEqual(result.required_radius_m, 20.0)
        self.assertAlmostEqual(result.capacity_margin_kg, 0.0)

    def test_capacity_shortfall_by_one_kilogram_is_reported(self):
        result = evaluate_candidate(
            make_project(load_kg=2801.0), make_config(), (0.0, 0.0)
        )
        self.assertFalse(result.passed)
        self.assertIn("CAPACITY_INSUFFICIENT", result.reason_codes)
        self.assertAlmostEqual(result.capacity_margin_kg, -1.0)

    def test_unassigned_active_load_is_checked_at_existing_work_point(self):
        project = make_project(load_kg=500.0, rigging_kg=50.0)
        project.loads.append(Load("unassigned-heavy", 3001.0, 0.0, 1.0, 1.0, 1.0))

        result = evaluate_candidate(project, make_config(), (0.0, 0.0))

        self.assertFalse(result.passed)
        self.assertIn("CAPACITY_INSUFFICIENT", result.reason_codes)
        self.assertEqual(result.critical_operation_id, "WP-1:WP-1:unassigned-heavy")

    def test_missing_rigging_mass_blocks_input(self):
        project = make_project()
        project.loads[0].rigging_kg = None  # type: ignore[assignment]
        result = evaluate_candidate(project, make_config(), (0.0, 0.0))
        self.assertEqual(result.reason_codes, ("INPUT_BLOCKED",))

    def test_insufficient_free_standing_height_is_reported(self):
        result = evaluate_candidate(
            make_project(level_m=46.0), make_config(), (0.0, 0.0)
        )
        self.assertFalse(result.passed)
        self.assertIn("HEIGHT_INSUFFICIENT", result.reason_codes)
        self.assertLess(result.height_margin_m, 0.0)

    def test_base_and_restricted_zone_conflicts_are_distinguished(self):
        project = make_project(restricted=[[(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]])
        result = evaluate_candidate(project, make_config(), (0.0, 0.0))
        self.assertIn("RESTRICTED_ZONE_CONFLICT", result.reason_codes)

    def test_route_conflict_is_reported_separately(self):
        project = make_project(restricted=[[(9.0, -2.0), (11.0, -2.0), (11.0, 2.0), (9.0, 2.0)]])
        result = evaluate_candidate(project, make_config(), (0.0, 0.0))
        self.assertIn("ROUTE_CONFLICT", result.reason_codes)
        self.assertNotIn("RESTRICTED_ZONE_CONFLICT", result.reason_codes)

    def test_repeated_area_runs_are_deterministic(self):
        first = calculate_admissible_area(
            make_project(), make_config(), step_m=10.0, refinement_levels=1, run_id="R-1"
        )
        second = calculate_admissible_area(
            make_project(), make_config(), step_m=10.0, refinement_levels=1, run_id="R-1"
        )
        self.assertEqual(first.accepted_points, second.accepted_points)
        self.assertEqual(first.counts_by_reason, second.counts_by_reason)
        self.assertEqual(first.area_estimate_m2, second.area_estimate_m2)
        self.assertEqual(first.input_hashes, second.input_hashes)
        self.assertTrue(all(item.source_locators for item in first.candidate_evaluations))


if __name__ == "__main__":
    unittest.main()
