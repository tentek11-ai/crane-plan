import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.models import (  # noqa: E402
    LiftRoute,
    RouteAlternative,
    RouteWaypoint,
    SOZRContour,
    SOZRPlan,
    SOZRPoint,
    SOZRRestrictionClass,
)
from crane_plan.sozr_canvas import SOZRCanvasStyle, build_sozr_canvas_primitives  # noqa: E402


def plan(crane_id="K1", x=10.0, y=20.0):
    permanent = SOZRContour(
        "zone-red", ((12, 21), (14, 21), (14, 23)),
        SOZRRestrictionClass.PERMANENT, 0, "запрет",
    )
    conditional = SOZRContour(
        "zone-orange", ((7, 18), (8, 18), (8, 19)),
        SOZRRestrictionClass.CONDITIONAL, 8, "выше 11 м",
    )
    point = SOZRPoint(
        f"{crane_id}-1", 12, 21, 63.4, 2.2,
        SOZRRestrictionClass.PERMANENT, "zone-red", 0, "запрет",
    )
    route = LiftRoute(
        "OP-1",
        (RouteWaypoint(5, 20, 12, "RADIAL"), RouteWaypoint(10, 25, 12, "ANGULAR")),
        12,
        (RouteAlternative("direct", True, 3, 8),),
        "a" * 64,
    )
    return SOZRPlan(
        crane_id, 30, (permanent,), (conditional,), (point,), (route,), "SOZR-1.0", x, y,
    )


class SOZRCanvasPrimitiveTests(unittest.TestCase):
    def test_snapshot_contains_base_circle_cutouts_route_points_and_labels(self):
        style = SOZRCanvasStyle()
        primitives = build_sozr_canvas_primitives(plan(), lambda p: (p[0] * 2, p[1] * 3), style)
        snapshot = [(item.kind, item.layer, item.color, item.label, item.dash) for item in primitives]

        self.assertIn(("ellipse", "admissible", style.admissible_color, "", ()), snapshot)
        self.assertIn(("ellipse", "technical_circle", style.technical_color, "K1 R=30 м", style.technical_dash), snapshot)
        self.assertIn(("polygon", "permanent", style.permanent_color, "", ()), snapshot)
        self.assertIn(("polygon", "conditional", style.conditional_color, "H=8 м", ()), snapshot)
        self.assertIn(("polyline", "route", style.route_color, "OP-1", ()), snapshot)
        self.assertIn(("point", "restriction_point", style.point_color, "K1-1", ()), snapshot)

        technical = next(item for item in primitives if item.layer == "technical_circle")
        self.assertEqual(technical.coords, (-40.0, -30.0, 80.0, 150.0))

    def test_two_cranes_keep_independent_labels_and_complete_dashed_circles(self):
        primitives = []
        for item in (plan("K1", 0, 0), plan("K2", 40, 0)):
            primitives.extend(build_sozr_canvas_primitives(item, lambda p: p))
        circles = [item for item in primitives if item.layer == "technical_circle"]
        self.assertEqual([item.label for item in circles], ["K1 R=30 м", "K2 R=30 м"])
        self.assertTrue(all(item.dash for item in circles))
        self.assertEqual(len([item for item in primitives if item.layer == "permanent"]), 2)


if __name__ == "__main__":
    unittest.main()
