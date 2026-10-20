import sys
import unittest
from pathlib import Path


ROOT=Path(__file__).parents[1]
sys.path.insert(0,str(ROOT/"05_src"))

from crane_plan.tieins import calculate_tie_in_plan, horizontal_intersections, required_pair_tie_length


class TieInAlgorithmTests(unittest.TestCase):
    def test_free_standing_crane_needs_no_ties(self):
        plan=calculate_tie_in_plan(40,44.4,61,20)
        self.assertEqual(plan.total_sections,0)
        self.assertEqual(plan.stages,[])

    def test_user_example_selects_four_five_metre_sections(self):
        plan=calculate_tie_in_plan(61,44.4,61,20,horizontal_distance_m=8)
        self.assertEqual(len(plan.stages),1)
        self.assertAlmostEqual(plan.stages[0].level_m,38.4)
        self.assertEqual(plan.stages[0].sections_this_stage,4)
        self.assertAlmostEqual(plan.accepted_height_m,64.4)

    def test_second_tie_starts_after_five_sections(self):
        plan=calculate_tie_in_plan(72,44.4,90,30,horizontal_distance_m=8)
        self.assertEqual([round(stage.level_m,1) for stage in plan.stages],[38.4,63.4])
        self.assertEqual([stage.sections_this_stage for stage in plan.stages],[5,1])
        self.assertAlmostEqual(plan.accepted_height_m,74.4)

    def test_pair_length_accounts_for_sixty_degree_angle(self):
        self.assertAlmostEqual(required_pair_tie_length(6,60),6.928203,places=5)

    def test_contour_is_checked_at_tie_level(self):
        contour=[(0,0),(20,0),(20,50),(0,50)]
        self.assertEqual(horizontal_intersections(contour,38.4),[0.0,20.0])
        plan=calculate_tie_in_plan(61,44.4,61,20,horizontal_distance_m=8,section_contour=contour)
        self.assertTrue(plan.geometry_ok)

    def test_short_tie_is_reported(self):
        plan=calculate_tie_in_plan(61,44.4,61,20,tie_length_m=8,tie_angle_deg=60,horizontal_distance_m=10)
        self.assertFalse(plan.geometry_ok)
        self.assertTrue(any("не достигают" in reason for reason in plan.reasons))


if __name__=="__main__":
    unittest.main()
