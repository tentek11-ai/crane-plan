import sys
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.engine.domain import SourceKind, SourceLocator  # noqa: E402
from crane_plan.engine import load_catalog_v3, verify_scenario_v21  # noqa: E402
from crane_plan.engine.integration import IntegrationStatus, ScenarioVerificationV21  # noqa: E402
from crane_plan.engine.verification import VerificationCheck, VerificationReport, VerificationStatus  # noqa: E402
from crane_plan.models import (  # noqa: E402
    LiftRoute,
    Load,
    Placement,
    ProjectInput,
    RestrictedZone,
    RestrictedZoneKind,
    RouteAlternative,
    RouteWaypoint,
    SOZRPlan,
    SOZRPoint,
    SOZRRestrictionClass,
    ScenarioResult,
    SiteInput,
    WorkPoint,
)
from crane_plan.pprk_context import PPRKValueTrace, build_pprk_context, scenario_render_sha256  # noqa: E402


SOURCE = SourceLocator(SourceKind.PASSPORT, "LIEBHERR-130-ECB", "load chart p.12")


def _fixture():
    route = LiftRoute(
        "OP-W1-L1",
        (
            RouteWaypoint(-8.0, 0.0, 18.0, "hoist"),
            RouteWaypoint(8.0, 0.0, 34.0, "slew"),
        ),
        34.0,
        (RouteAlternative("direct", True, 3.5, 24.0),),
        "route-input-hash",
    )
    sozr = SOZRPlan(
        "CR-1",
        45.0,
        (),
        (),
        (
            SOZRPoint(
                "ОТ1",
                12.0,
                3.0,
                14.0,
                31.0,
                SOZRRestrictionClass.PERMANENT,
                "RZ-1",
                16.0,
                "запрет",
            ),
        ),
        (route,),
        "SOZR-1.0",
        crane_x=0.0,
        crane_y=0.0,
    )
    placement = Placement(
        "CR-1",
        "Liebherr 130 EC-B 6",
        0.0,
        -8.0,
        [0],
        31.0,
        36.0,
        jib_length_m=45.0,
        max_free_standing_height_m=44.4,
        accepted_crane_height_m=63.4,
        tie_in_levels_m=[38.4],
        tie_in_stage_sections=[4],
        total_additional_sections=4,
        required_tie_length_m=12.0,
        sozr_plan=sozr,
    )
    project = ProjectInput(
        "Жилой дом",
        "Москва",
        2026,
        "",
        "",
        -3.0,
        30.0,
        SiteInput(
            [(-30, -30), (30, -30), (30, 30), (-30, 30)],
            [(-5, -5), (5, -5), (5, 5), (-5, 5)],
            restricted_zones=[
                RestrictedZone(
                    "RZ-1",
                    "ЛЭП",
                    RestrictedZoneKind.HEIGHT_OBSTACLE,
                    [(10, -2), (14, -2), (14, 2), (10, 2)],
                    16.0,
                    source_refs=["План стройплощадки"],
                )
            ],
            unloading_zone=[(-20, -4), (-16, -4), (-16, 4), (-20, 4)],
            storage_zones=[[(-14, -4), (-10, -4), (-10, 4), (-14, 4)]],
        ),
        [Load("Щит опалубки", 1800.0, 120.0, 3.0, 1.2, 2.8, lifts=24)],
        [WorkPoint(8.0, 0.0, 30.0, 0)],
        organization="ООО Генподрядчик",
        project_code="ППРк-01",
        restricted_zones_confirmed=True,
        loads_verified=True,
    )
    project.pprk_release.object_address = "Москва, ул. Испытательная, д. 1"
    project.loads[0] = replace(project.loads[0], rigging_type="Канатный",
        rigging_branch_count=4, sling_identification="4СК-TEST", rigging_capacity_kg=2500,
        rigging_evidence="Испытательный паспорт 123", rigging_verified=True)
    scenario = ScenarioResult(
        "PASS",
        [placement],
        [],
        [],
        total_active_lifts=24,
        accounted_lifts=24,
        routes=[route],
    )
    checks = (
        VerificationCheck("REACH", True, 29.5, 45.0, "m", "OP-W1-L1", "CR-1", (SOURCE,)),
        VerificationCheck("CAPACITY_INSUFFICIENT", True, 1920.0, 2350.0, "kg", "OP-W1-L1", "CR-1", (SOURCE,)),
        VerificationCheck("HEIGHT", True, 34.3, 44.4, "m", "OP-W1-L1", "CR-1", (SOURCE,)),
    )
    solution_placement = SimpleNamespace(
        id="CR-1", stage_id="MAIN_STAGE", configuration_id="CFG-130", x_m=0.0, y_m=-8.0
    )
    assignment = SimpleNamespace(operation_id="OP-W1-L1", placement_id="CR-1")
    operation_evaluation = SimpleNamespace(
        operation_id="OP-W1-L1",
        radius_m=29.5,
        available_capacity_kg=2350.0,
        capacity_margin_kg=430.0,
        utilization=1920.0 / 2350.0,
        required_hook_height_m=34.3,
        height_margin_m=10.1,
    )
    protocol = SimpleNamespace(
        run_id="RUN-1",
        input_sha256="a" * 64,
        result_sha256="b" * 64,
        algorithm_version="3.0.1",
        verification=VerificationReport(VerificationStatus.VALID, checks),
        catalog=(SimpleNamespace(id="CFG-130", capacity_curve=(SimpleNamespace(radius_m=3.0, capacity_kg=6000.0), SimpleNamespace(radius_m=45.0, capacity_kg=1800.0)), source=SOURCE),),
        solution=SimpleNamespace(
            stages=(SimpleNamespace(stage_id="MAIN_STAGE", placements=(solution_placement,), assignments=(assignment,)),)
        ),
        project=SimpleNamespace(
            operations=(SimpleNamespace(id="OP-W1-L1", load=SimpleNamespace(id="LOAD-L1")),)
        ),
        placement_evaluations=(
            SimpleNamespace(
                stage_id="MAIN_STAGE",
                crane_point=(0.0, -8.0),
                configuration_id="CFG-130",
                operation_evaluations=(operation_evaluation,),
            ),
        ),
    )
    verification = ScenarioVerificationV21(
        0,
        IntegrationStatus.VERIFIED,
        True,
        (),
        SimpleNamespace(verification=protocol.verification, protocol=protocol),
        protocol,
    )
    return project, scenario, verification


class PPRKContextTests(unittest.TestCase):
    def test_load_confirmation_rejects_stale_project_mass(self):
        project, scenario, verification = _fixture()
        project.loads[0].load_kg = 9000
        context = build_pprk_context(project, scenario, verification)
        load, = context.active_loads
        self.assertFalse(load.confirmed)
        self.assertTrue(load.warnings)
        self.assertTrue(any(i.blocking and i.code == "PPRK_LOAD_EVIDENCE_REQUIRED" for i in context.completeness_issues))
        self.assertFalse(context.trace("load.mass_kg", "OP-W1-L1").verified)

    def test_load_confirmation_requires_protocol_capacity_check_in_kg(self):
        for mode in ("missing", "wrong_units", "failed", "wrong_crane", "nonfinite"):
            with self.subTest(mode=mode):
                project, scenario, verification = _fixture()
                checks = verification.protocol.verification.checks
                capacity = next(c for c in checks if c.code == "CAPACITY_INSUFFICIENT")
                changed = {
                    "wrong_units": replace(capacity, units="t"),
                    "failed": replace(capacity, passed=False),
                    "wrong_crane": replace(capacity, crane_id="OTHER"),
                    "nonfinite": replace(capacity, measured_value=float("inf")),
                }.get(mode)
                checks = tuple(c for c in checks if c.code != "CAPACITY_INSUFFICIENT") + ((changed,) if changed else ())
                report = replace(verification.protocol.verification, checks=checks)
                verification = replace(verification, protocol=SimpleNamespace(**{**verification.protocol.__dict__, "verification": report}))
                load, = build_pprk_context(project, scenario, verification).active_loads
                self.assertFalse(load.confirmed)

    def test_every_operation_must_match_mass_and_transfers_authoritative_trace(self):
        for second_mass, confirmed in ((1920, True), (2000, False)):
            with self.subTest(second_mass=second_mass):
                project, scenario, verification = _fixture()
                protocol = verification.protocol
                capacity = next(c for c in protocol.verification.checks if c.code == "CAPACITY_INSUFFICIENT")
                checks = protocol.verification.checks + (replace(capacity, operation_id="OP-W2-L1", measured_value=second_mass),)
                stage, = protocol.solution.stages
                stage = SimpleNamespace(**{**stage.__dict__, "assignments": (*stage.assignments, SimpleNamespace(operation_id="OP-W2-L1", placement_id="CR-1"))})
                protocol = SimpleNamespace(**{**protocol.__dict__, "project": SimpleNamespace(operations=(*protocol.project.operations, SimpleNamespace(id="OP-W2-L1", load=SimpleNamespace(id="LOAD-L1")))), "solution": SimpleNamespace(stages=(stage,)), "verification": replace(protocol.verification, checks=checks)})
                context = build_pprk_context(project, scenario, replace(verification, protocol=protocol))
                load, = context.active_loads
                self.assertEqual(load.confirmed, confirmed)
                if confirmed:
                    self.assertTrue(hasattr(load, "capacity_evidence"), "load payload needs authoritative capacity traces")
                    self.assertEqual([(t.operation_id, t.value, t.unit, t.verified) for t in load.capacity_evidence], [("OP-W1-L1", 1920, "kg", True), ("OP-W2-L1", 1920, "kg", True)])
                    self.assertEqual(load.verified_total_kg, 1920)

    def test_builds_object_identity_and_template_values(self):
        project, scenario, verification = _fixture()

        context = build_pprk_context(project, scenario, verification)

        self.assertEqual(context.object_name, "Жилой дом")
        self.assertEqual(context.object_address, "Москва, ул. Испытательная, д. 1")
        self.assertEqual(context.project_code, "ППРк-01")
        self.assertEqual(context.crane_ids, ("CR-1",))
        self.assertEqual(context.operation_ids, ("OP-W1-L1",))
        self.assertEqual(context.values["crane_count"], 1)
        self.assertEqual(context.values["crane_model"], "Liebherr 130 EC-B 6")
        self.assertEqual(context.values["building_height_m"], 33.0)
        self.assertEqual(context.values["storage_zone_count"], 1)

    def test_context_carries_authoritative_scenario_hash_and_verified_danger_offset(self):
        project, scenario, verification = _fixture()
        danger = VerificationCheck(
            "DANGER_ZONE_INSIDE_SITE", True, 9.4, 0.0, "m", "OP-W1-L1", "CR-1", (SOURCE,)
        )
        report = replace(verification.engine_result.verification, checks=verification.engine_result.verification.checks + (danger,))
        verification = replace(
            verification,
            engine_result=SimpleNamespace(verification=report),
            protocol=SimpleNamespace(**{**verification.protocol.__dict__, "verification": report}),
        )

        context = build_pprk_context(project, scenario, verification)

        self.assertEqual(context.scenario_render_sha256, scenario_render_sha256(scenario))
        self.assertEqual(context.values["verified_danger_zone_offset_m"], 9.4)

    def test_transfers_explicit_release_inputs_without_invented_defaults(self):
        project, scenario, verification = _fixture()
        release = project.pprk_release
        release.project_basis = "Задание заказчика"
        release.plan_sheet_refs = "ГЧ-01, ГЧ-02"
        release.responsible_fire_safety = "назначается приказом"
        release.max_wind_speed_m_s = 10.0
        release.fall_protection_system = "страховочная система"
        release.power_supply_scheme = "линия от ВРУ"
        release.waste_plan = "контейнерный вывоз"
        release.external_document_register = "по ведомости"
        release.receiving_platform_ids = ["ПП-1"]
        release.opening_ids = ["ПР-1"]
        release.bucket_volume_m3 = 1.0

        context = build_pprk_context(project, scenario, verification)

        for field_name in (
            "project_basis",
            "plan_sheet_refs",
            "responsible_fire_safety",
            "max_wind_speed_m_s",
            "fall_protection_system",
            "power_supply_scheme",
            "waste_plan",
            "external_document_register",
            "receiving_platform_ids",
            "opening_ids",
            "bucket_volume_m3",
        ):
            with self.subTest(field_name=field_name):
                expected = getattr(release, field_name)
                if field_name in ("receiving_platform_ids", "opening_ids"):
                    expected = tuple(expected)
                self.assertEqual(context.values[field_name], expected)

    def test_capacity_reach_and_height_come_from_verification_not_recalculation(self):
        project, scenario, verification = _fixture()
        scenario.placements[0].max_radius_m = 31.0

        context = build_pprk_context(project, scenario, verification)

        self.assertEqual(context.trace("reach.required_m", "OP-W1-L1", "CR-1").value, 29.5)
        self.assertEqual(context.trace("capacity.required_kg", "OP-W1-L1", "CR-1").value, 1920.0)
        self.assertEqual(context.trace("capacity.available_kg", "OP-W1-L1", "CR-1").value, 2350.0)
        self.assertEqual(context.trace("height.required_m", "OP-W1-L1", "CR-1").value, 34.3)
        self.assertEqual(context.trace("height.available_m", "OP-W1-L1", "CR-1").value, 44.4)
        self.assertEqual(context.values["work_radii_m"], (29.5,))
        self.assertEqual(context.values["max_capacity_t"], 6.0)
        self.assertEqual(context.trace("capacity.margin_kg", "OP-W1-L1", "CR-1").value, 430.0)
        self.assertEqual(context.trace("height.margin_m", "OP-W1-L1", "CR-1").value, 10.1)

    def test_traces_configuration_ties_zones_sozr_routes_and_lifts(self):
        project, scenario, verification = _fixture()

        context = build_pprk_context(project, scenario, verification)

        expected_fields = {
            "crane.jib_length_m",
            "crane.accepted_height_m",
            "crane.tie_level_m",
            "crane.tie_stage_sections",
            "load.mass_kg",
            "load.rigging_kg",
            "load.lift_count",
            "restricted_zone.height_m",
            "sozr.point.x_m",
            "sozr.point.y_m",
            "sozr.point.bearing_deg",
            "sozr.point.radius_m",
            "route.transport_hook_height_m",
            "route.waypoint.hook_height_m",
        }
        self.assertTrue(expected_fields.issubset({trace.field_id for trace in context.traces}))
        numeric_traces = [trace for trace in context.traces if isinstance(trace.value, (int, float)) and not isinstance(trace.value, bool)]
        self.assertTrue(numeric_traces)
        for trace in numeric_traces:
            with self.subTest(field_id=trace.field_id):
                self.assertTrue(trace.source)
                self.assertTrue(trace.rule)
                self.assertTrue(trace.algorithm_version)
        self.assertEqual(context.values["tie_levels_m"], (38.4,))
        self.assertEqual(context.values["tower_sections"], (4,))
        self.assertIn("ОТ1", context.values["sozr_points"])
        self.assertIn("OP-W1-L1", context.values["route_register"])

    def test_requires_every_check_for_every_assignment_and_blocks_rejected_result(self):
        project, scenario, verification = _fixture()
        scenario.placements[0].crane_id = "LIEBHERR-SHARED-CONFIG"
        second = Placement("LIEBHERR-SHARED-CONFIG", "Liebherr 130 EC-B 6", 10.0, -8.0, [0], 28.0, 36.0, jib_length_m=40.0)
        scenario.placements.append(second)
        second_solution = SimpleNamespace(
            id="CR-2", stage_id="MAIN_STAGE", configuration_id="CFG-130", x_m=10.0, y_m=-8.0
        )
        stage = verification.protocol.solution.stages[0]
        verification.protocol.solution = SimpleNamespace(
            stages=(
                SimpleNamespace(
                    stage_id="MAIN_STAGE",
                    placements=stage.placements + (second_solution,),
                    assignments=stage.assignments + (SimpleNamespace(operation_id="OP-W2-L1", placement_id="CR-2"),),
                ),
            )
        )
        # Only REACH exists for the second assignment; CAPACITY and HEIGHT are absent.
        extra_check = VerificationCheck("REACH", True, 20.0, 40.0, "m", "OP-W2-L1", "CR-2", (SOURCE,))
        verification.engine_result.verification = VerificationReport(
            VerificationStatus.INVALID,
            verification.engine_result.verification.checks + (extra_check,),
        )
        verification = replace(
            verification,
            status=IntegrationStatus.REJECTED,
            release_allowed=False,
        )

        context = build_pprk_context(project, scenario, verification)

        fields = {issue.field_id for issue in context.completeness_issues}
        self.assertEqual(context.crane_ids, ("CR-1", "CR-2"))
        self.assertEqual(context.values["crane_configuration_ids"], ("CFG-130", "CFG-130"))
        self.assertEqual(context.values["legacy_configuration_references"], ("LIEBHERR-SHARED-CONFIG", "LIEBHERR-SHARED-CONFIG"))
        self.assertFalse(any(trace.crane_id == "LIEBHERR-SHARED-CONFIG" for trace in context.traces))
        self.assertIn("verification.status", fields)
        self.assertIn("OP-W2-L1/CR-2/CAPACITY_INSUFFICIENT", fields)
        self.assertIn("OP-W2-L1/CR-2/HEIGHT", fields)

    def test_expands_geometry_schedule_joint_and_comparison_traces(self):
        project, scenario, verification = _fixture()
        placement = scenario.placements[0]
        placement.jib_level_m = 61.4
        placement.allowed_sector_start_deg = 15.0
        placement.allowed_sector_end_deg = 280.0
        placement.tower_exclusion_start_deg = 70.0
        placement.tower_exclusion_end_deg = 95.0
        placement.assigned_contour_points = [0, 2]
        placement.assigned_logistics_zones = [0]
        placement.radial_limits_m = [(20.0, 32.0)]
        placement.sozr_plan = SOZRPlan(
            placement.sozr_plan.crane_id,
            placement.sozr_plan.technical_radius_m,
            (
                SimpleNamespace(zone_id="RZ-1", points=((10.0, 1.0), (11.0, 2.0)), restriction_class=SOZRRestrictionClass.PERMANENT, zone_height_m=16.0, condition="запрет"),
            ),
            (
                SimpleNamespace(zone_id="RZ-2", points=((15.0, 1.0), (16.0, 2.0)), restriction_class=SOZRRestrictionClass.CONDITIONAL, zone_height_m=8.0, condition="выше"),
            ),
            placement.sozr_plan.points,
            placement.sozr_plan.critical_routes,
            "SOZR-1.0",
            admissible_contours=(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)),),
        )
        scenario.routes[0] = LiftRoute(
            scenario.routes[0].operation_id,
            scenario.routes[0].waypoints,
            scenario.routes[0].transport_hook_height_m,
            (RouteAlternative("direct", True, 3.5, 24.0), RouteAlternative("outer", False, 1.2, 31.0)),
            scenario.routes[0].input_sha256,
        )
        scenario.calendar_days = 120.0
        scenario.score = 14.5
        scenario.estimated_cost = 2_400_000.0
        scenario.crane_work_hours = [800.0]
        scenario.joint_plan = SimpleNamespace(
            axis_distance_m=30.0,
            working_horizontal_clearance_m=5.0,
            parking_horizontal_clearance_m=2.0,
            vertical_separation_m=3.0,
            higher_crane_index=1,
            priority_crane_index=1,
            overlap_exists=True,
            overlap_area_m2=120.0,
            overlap_polygon=[(0.0, 0.0), (2.0, 0.0), (1.0, 2.0)],
            jib_structural_height_m=2.0,
            tower_protection_radius_m=2.0,
            combined_tower_envelope_m=4.0,
            schedule_stages=["К1 работает, К2 ожидает"],
        )

        context = build_pprk_context(project, scenario, verification)
        fields = {trace.field_id for trace in context.traces}

        for required in (
            "crane.max_radius_m",
            "crane.jib_level_m",
            "crane.allowed_sector_start_deg",
            "crane.radial_limit_m",
            "coverage.work_point_index",
            "sozr.permanent_contour.x_m",
            "sozr.conditional_contour.y_m",
            "sozr.admissible_contour.x_m",
            "route.alternative.min_clearance_m",
            "route.alternative.path_length_m",
            "joint.axis_distance_m",
            "joint.overlap_polygon.x_m",
            "schedule.calendar_days",
            "comparison.estimated_cost",
        ):
            self.assertIn(required, fields)

    def test_preserves_original_active_load_index_and_real_operation_identity(self):
        project, scenario, verification = _fixture()
        project.loads.insert(0, Load("Неактивный", 100.0, 10.0, 1.0, 1.0, 1.0, active=False))
        project.work_points[0].load_index = 1
        verification.protocol.project.operations = (
            SimpleNamespace(id="OP-W1-L2", load=SimpleNamespace(id="LOAD-L2")),
        )
        stage = verification.protocol.solution.stages[0]
        verification.protocol.solution = SimpleNamespace(
            stages=(SimpleNamespace(stage_id=stage.stage_id, placements=stage.placements, assignments=(SimpleNamespace(operation_id="OP-W1-L2", placement_id="CR-1"),)),)
        )
        remapped = tuple(
            VerificationCheck(check.code, check.passed, check.measured_value, check.limit, check.units, "OP-W1-L2", check.crane_id, check.sources)
            for check in verification.engine_result.verification.checks
        )
        verification.engine_result.verification = VerificationReport(VerificationStatus.VALID, remapped)

        context = build_pprk_context(project, scenario, verification)
        mass_trace = next(trace for trace in context.traces if trace.field_id == "load.mass_kg")

        self.assertEqual(mass_trace.source, "ProjectInput.loads[1]")
        self.assertEqual(mass_trace.operation_id, "OP-W1-L2")
        self.assertFalse(any(trace.operation_id.startswith("LOAD-") for trace in context.traces))

    def test_missing_identity_and_required_datasets_are_not_silently_filled(self):
        project, scenario, verification = _fixture()
        project.pprk_release.object_address = ""
        project.organization = ""
        project.project_code = ""
        project.loads[0].active = False
        scenario.placements.clear()
        scenario.routes.clear()

        context = build_pprk_context(project, scenario, verification)

        self.assertEqual(context.object_address, "")
        codes = {issue.code for issue in context.completeness_issues}
        self.assertTrue(
            {"PPRK_ADDRESS_REQUIRED", "PPRK_ORGANIZATION_REQUIRED", "PPRK_CODE_REQUIRED", "PPRK_CRANES_REQUIRED", "PPRK_LOADS_REQUIRED", "PPRK_ROUTES_REQUIRED"}.issubset(codes)
        )

    def test_unverified_loads_and_zones_block_release(self):
        project, scenario, verification = _fixture()
        project.loads_verified = False
        project.site.restricted_zones[0].verified = False

        context = build_pprk_context(project, scenario, verification)

        codes = {issue.code for issue in context.completeness_issues}
        self.assertIn("PPRK_LOADS_UNVERIFIED", codes)
        self.assertIn("PPRK_ZONES_UNVERIFIED", codes)

    def test_real_engine_protocol_builds_context_and_transfers_all_numeric_checks(self):
        catalog = load_catalog_v3(ROOT / "02_processed_data/cranes/crane_configurations_v3.json")
        project = ProjectInput(
            "Дом",
            "Москва",
            2026,
            "",
            "",
            -3.0,
            27.0,
            SiteInput(
                [(-80, -80), (80, -80), (80, 80), (-80, 80)],
                [(20, -10), (40, -10), (40, 10), (20, 10)],
                unloading_zone=[(-20, -5), (-10, -5), (-10, 5), (-20, 5)],
                storage_zones=[[(-10, -5), (0, -5), (0, 5), (-10, 5)]],
                min_crane_to_building_m=1.0,
                max_crane_to_building_m=25.0,
            ),
            [Load("Бадья", 1200.0, 100.0, 1.8, 1.8, 2.4, 12)],
            [WorkPoint(25.0, 0.0, 20.0, 0, "Подача 1")],
            loads_verified=True,
            organization="ООО Проект",
            project_code="ППРк-REAL",
        )
        project.pprk_release.object_address = "Москва, реальный тестовый объект"
        scenario = ScenarioResult(
            "PASS",
            [
                Placement(
                    "LIEBHERR-130-ECB-6-60",
                    "130 EC-B 6",
                    0.0,
                    0.0,
                    [0],
                    25.0,
                    25.0,
                    60.0,
                    max_free_standing_height_m=44.4,
                    accepted_crane_height_m=44.4,
                )
            ],
            [],
            [],
        )
        verification = verify_scenario_v21(
            project,
            scenario,
            catalog,
            scenario_index=0,
            run_id="RUN-REAL",
            created_at="2026-11-04T12:00:00+03:00",
        )

        context = build_pprk_context(project, scenario, verification)

        self.assertEqual(context.crane_ids, ("SCENARIO-1-CRANE-1",))
        self.assertEqual(context.values["crane_configuration_ids"], ("LIEBHERR-130-ECB-6-60-V3",))
        self.assertEqual(context.values["legacy_configuration_references"], ("LIEBHERR-130-ECB-6-60",))
        self.assertEqual(context.trace("crane.configuration_id", "", "SCENARIO-1-CRANE-1").value, "LIEBHERR-130-ECB-6-60-V3")
        self.assertEqual(context.trace("crane.legacy_configuration_reference", "", "SCENARIO-1-CRANE-1").value, "LIEBHERR-130-ECB-6-60")
        self.assertEqual(context.values["max_capacity_t"], 6.0)
        self.assertEqual(context.trace("verification.base_clearance.measured", "", "SCENARIO-1-CRANE-1").value, 20.0)
        self.assertEqual(context.trace("verification.danger_zone_inside_site.measured", "OP-W1-L1", "SCENARIO-1-CRANE-1").value, 9.4)
        self.assertEqual(context.scenario_render_sha256, scenario_render_sha256(scenario))
        self.assertEqual(context.values["verified_danger_zone_offset_m"], 9.4)
        numeric_checks = [trace for trace in context.traces if trace.field_id.startswith("verification.") and isinstance(trace.value, (int, float))]
        self.assertTrue(numeric_checks)
        self.assertTrue(all(trace.source and trace.rule and trace.algorithm_version for trace in numeric_checks))

    def test_missing_protocol_is_explicit_and_never_invented(self):
        project, scenario, verification = _fixture()
        verification = ScenarioVerificationV21(
            0,
            IntegrationStatus.EXPERT_REVIEW_REQUIRED,
            False,
            ("нет протокола",),
            None,
            None,
        )

        context = build_pprk_context(project, scenario, verification)

        self.assertTrue(any(issue.code == "PPRK_PROTOCOL_REQUIRED" for issue in context.completeness_issues))
        missing = context.trace("verification.protocol", "", "")
        self.assertIsNone(missing.value)
        self.assertFalse(missing.verified)
        self.assertNotIn(0, context.values["work_radii_m"])

    def test_trace_rejects_untraceable_numeric_value(self):
        with self.assertRaises(ValueError):
            PPRKValueTrace("x", 1.0, "m", "", "", "")


if __name__ == "__main__":
    unittest.main()
