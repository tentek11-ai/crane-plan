import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.catalog import allowed_capacity_kg, load_catalog  # noqa: E402
from crane_plan.geometry import distance_to_polygon, point_in_polygon  # noqa: E402
from crane_plan.models import CraneConfiguration, Load, ProjectInput, SiteInput, WorkPoint  # noqa: E402
from crane_plan.optimizer import optimize  # noqa: E402


class GeometryTests(unittest.TestCase):
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]

    def test_point_inside_and_outside(self):
        self.assertTrue(point_in_polygon((5, 5), self.square))
        self.assertFalse(point_in_polygon((11, 5), self.square))

    def test_distance_to_boundary(self):
        self.assertEqual(distance_to_polygon((5, 5), self.square), 5)


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog(ROOT / "02_processed_data/cranes/crane_configurations.json")

    def test_priority_130_ecb_6_first(self):
        self.assertEqual(self.catalog[0].model, "130 EC-B 6")

    def test_verified_catalog_contains_ecb_and_ech_fallbacks(self):
        models = {item.model for item in self.catalog}
        self.assertIn("150 EC-B 8 Litronic", models)
        self.assertIn("280 EC-H 12 Litronic", models)

    def test_capacity_interpolates_conservatively(self):
        self.assertAlmostEqual(allowed_capacity_kg(self.catalog[0], 28.75), 5550)

    def test_outside_jib_is_zero(self):
        self.assertEqual(allowed_capacity_kg(self.catalog[0], 61), 0)


class OptimizerTests(unittest.TestCase):
    def test_finds_one_crane_for_simple_site(self):
        project = ProjectInput(
            name="Тест", city="Москва", year=2026, author="Автор", email="a@example.test",
            pit_bottom_m=0, parapet_m=20,
            site=SiteInput(
                boundary=[(-50,-50),(50,-50),(50,50),(-50,50)],
                building=[(-10,-10),(10,-10),(10,10),(-10,10)],
                min_crane_to_building_m=1, max_crane_to_building_m=25,
            ),
            loads=[Load("Груз", 1000, 100, 1, 1, 1, 100)],
            work_points=[WorkPoint(-8,-8,20,0), WorkPoint(8,8,20,0)],
            protective_screen_possible=True,
        )
        catalog = load_catalog(ROOT / "02_processed_data/cranes/crane_configurations.json")
        result = optimize(project, catalog, step_m=5)
        self.assertIn(result[0].status, {"PASS", "PASS_WITH_CONDITIONS"})
        self.assertEqual(len(result[0].placements), 1)
        self.assertTrue(any("130 EC-B 8" in warning for warning in result[0].warnings))

    def test_only_assigned_load_is_checked_at_work_point(self):
        project = ProjectInput(
            name="Тест", city="Москва", year=2026, author="Автор", email="a@example.test",
            pit_bottom_m=0, parapet_m=20,
            site=SiteInput([(-50,-50),(50,-50),(50,50),(-50,50)], [(-5,-5),(5,-5),(5,5),(-5,5)], min_crane_to_building_m=1, max_crane_to_building_m=25),
            loads=[Load("Лёгкий",100,10,1,1,1), Load("Сверх нормы",13000,100,1,1,1)],
            work_points=[WorkPoint(0,0,20,0)], protective_screen_possible=True,
        )
        catalog = load_catalog(ROOT / "02_processed_data/cranes/crane_configurations.json")
        result = optimize(project, catalog, step_m=5)
        self.assertIn(result[0].status, {"PASS", "PASS_WITH_CONDITIONS"})
        project.work_points[0].load_index = 1
        result = optimize(project, catalog, step_m=5)
        self.assertEqual(result[0].status, "BLOCKED")
        self.assertTrue(any("требует 13100 кг" in reason and "доступно" in reason for reason in result[0].reasons))

    def test_restricted_zone_blocks_boom_direction(self):
        project = ProjectInput(
            name="Тест", city="Москва", year=2026, author="", email="", pit_bottom_m=0, parapet_m=20,
            site=SiteInput([(-40,-40),(40,-40),(40,40),(-40,40)],[(-5,-5),(5,-5),(5,5),(-5,5)],restricted_zones=[[(-12,-12),(12,-12),(12,12),(-12,12)]],min_crane_to_building_m=13,max_crane_to_building_m=25),
            loads=[Load("Груз",500,50,1,1,1)],work_points=[WorkPoint(0,0,20,0)],protective_screen_possible=True,
        )
        crane=CraneConfiguration("test","130 EC-B 6 test",1,35,6000,60,((0,6000),(35,2000)),"test")
        self.assertEqual(optimize(project,[crane],step_m=5)[0].status,"BLOCKED")

    def test_self_intersecting_site_is_blocked(self):
        project=ProjectInput("x","x",2026,"","",0,10,SiteInput([(0,0),(20,20),(0,20),(20,0)],[(8,8),(12,8),(12,12),(8,12)]),[Load("x",1,0,1,1,1)],[WorkPoint(10,10,10,0)])
        crane=CraneConfiguration("test","130 EC-B 6 test",1,35,6000,60,((0,6000),(35,2000)),"test")
        result=optimize(project,[crane],step_m=5)[0]
        self.assertEqual(result.status,"BLOCKED")
        self.assertTrue(any("самопересечение" in reason for reason in result.reasons))

    def test_joint_levels_must_fit_free_standing_configuration(self):
        project = ProjectInput(
            name="Протяжённый корпус", city="Москва", year=2026, author="", email="", pit_bottom_m=0, parapet_m=20,
            site=SiteInput([(-65,-30),(65,-30),(65,30),(-65,30)],[(-50,-5),(50,-5),(50,5),(-50,5)],min_crane_to_building_m=1,max_crane_to_building_m=20),
            loads=[Load("Груз",500,50,1,1,1)],work_points=[WorkPoint(-25,0,20,0),WorkPoint(25,0,20,0)],protective_screen_possible=True,
        )
        crane=CraneConfiguration("test","130 EC-B 6 test",1,35,6000,27,((0,6000),(35,2000)),"test")
        self.assertEqual(optimize(project,[crane],step_m=5)[0].status,"BLOCKED")

    def test_explains_when_installation_area_is_empty(self):
        project = ProjectInput(
            name="Тест", city="Москва", year=2026, author="", email="",
            pit_bottom_m=0, parapet_m=20,
            site=SiteInput([(-10,-10),(10,-10),(10,10),(-10,10)], [(-9,-9),(9,-9),(9,9),(-9,9)], min_crane_to_building_m=20, max_crane_to_building_m=25),
            loads=[Load("Груз",1000,100,1,1,1)], work_points=[WorkPoint(0,0,20,0)], protective_screen_possible=True,
        )
        catalog = load_catalog(ROOT / "02_processed_data/cranes/crane_configurations.json")
        result = optimize(project, catalog, step_m=2)
        self.assertEqual(result[0].status, "BLOCKED")
        self.assertTrue(any("ни одной допустимой точки установки" in reason for reason in result[0].reasons))

    def test_uses_two_cranes_when_one_cannot_cover_building_contour(self):
        project = ProjectInput(
            name="Протяжённый корпус", city="Москва", year=2026, author="", email="",
            pit_bottom_m=0, parapet_m=20,
            site=SiteInput(
                [(-65,-30),(65,-30),(65,30),(-65,30)],
                [(-50,-5),(50,-5),(50,5),(-50,5)],
                min_crane_to_building_m=1, max_crane_to_building_m=20,
            ),
            loads=[Load("Груз",500,50,1,1,1)],
            work_points=[WorkPoint(-25,0,20,0),WorkPoint(25,0,20,0)],
            protective_screen_possible=True,
        )
        crane = CraneConfiguration("test","Тестовый башенный кран",1,35,6000,60,((0,6000),(35,2000)),"test")
        result = optimize(project,[crane],step_m=5)
        self.assertIn(result[0].status,{"PASS","PASS_WITH_CONDITIONS"})
        self.assertEqual(len(result[0].placements),2)
        self.assertTrue(any("Совместная работа" in warning for warning in result[0].warnings))
        self.assertIsNotNone(result[0].joint_plan)
        self.assertGreaterEqual(result[0].joint_plan.vertical_separation_m,3)
        self.assertEqual(result[0].joint_plan.jib_structural_height_m,2)
        self.assertEqual(result[0].joint_plan.combined_tower_envelope_m,4)
        self.assertEqual(len(result[0].joint_plan.schedule_stages),4)
        self.assertGreater(result[0].joint_plan.overlap_area_m2,0)
        self.assertEqual(result[0].joint_plan.priority_crane_index,2)
        self.assertTrue(all(p.allowed_sector_end_deg>p.allowed_sector_start_deg for p in result[0].placements))
        self.assertEqual(sum(len(p.assigned_contour_points) for p in result[0].placements),44)
        higher=result[0].joint_plan.higher_crane_index-1
        lower=1-higher
        self.assertLessEqual(result[0].placements[lower].jib_length_m,result[0].joint_plan.axis_distance_m-7.0+1e-6)
        self.assertTrue(all(abs((p.jib_length_m/5)-round(p.jib_length_m/5))<1e-9 for p in result[0].placements))
        self.assertTrue(all(p.max_radius_m<=p.jib_length_m+1e-6 for p in result[0].placements))


if __name__ == "__main__":
    unittest.main()
