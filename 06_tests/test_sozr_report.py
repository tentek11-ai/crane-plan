import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from pypdf import PdfReader  # noqa: E402
from reportlab.lib.pagesizes import A3, landscape  # noqa: E402
from reportlab.pdfgen.canvas import Canvas  # noqa: E402
from crane_plan.models import (  # noqa: E402
    LiftRoute, Placement, ProjectInput, RouteAlternative, RouteFailure,
    RouteFailureCode, RouteWaypoint, SOZRPlan, SOZRPoint,
    SOZRRestrictionClass, SiteInput, WarningAcceptance,
)
from crane_plan.sozr_report import build_route_explanation, build_sozr_table_rows, draw_sozr_sheet  # noqa: E402


def sample_plan():
    point = SOZRPoint("K1-1", 12, 15, 38.7, 19.2, SOZRRestrictionClass.CONDITIONAL, "zone-1", 8, "низ груза выше 11 м")
    route = LiftRoute(
        "OP-1", (RouteWaypoint(0, 0, 15, "START"), RouteWaypoint(12, 15, 15, "RADIAL")), 15,
        (
            RouteAlternative("direct", False, -1.5, 19.2, (RouteFailure(RouteFailureCode.HEIGHT_EXCEEDED, "не хватает высоты", "zone-1", 11.0, 9.5),)),
            RouteAlternative("over", True, 4.0, 22.0),
        ),
        "a" * 64,
    )
    return SOZRPlan("K1", 30, (), (), (point,), (route,), "SOZR-1.0", 0, 0)


class SOZRReportTests(unittest.TestCase):
    def test_table_has_required_columns_and_numeric_point_values(self):
        rows = build_sozr_table_rows(sample_plan())
        self.assertEqual(rows[0], ["Точка", "X, м", "Y, м", "Угол, °", "Вылет, м", "Тип", "H зоны, м", "Условие"])
        self.assertEqual(rows[1][:5], ["K1-1", "12.00", "15.00", "38.70", "19.20"])

    def test_explanation_contains_selected_chain_numeric_rejection_and_only_nonempty_comments(self):
        result = SimpleNamespace(
            routes=list(sample_plan().critical_routes),
            route_failures=[],
            warning_acceptances=[
                WarningAcceptance("WARN-EMPTY", "a" * 64, ""),
                WarningAcceptance("WARN-COMMENT", "a" * 64, "согласовано с крановщиком"),
            ],
        )
        text = "\n".join(build_route_explanation(result))
        self.assertIn("OP-1", text)
        self.assertIn("over", text)
        self.assertIn("11", text)
        self.assertIn("9.5", text)
        self.assertIn("WARN-EMPTY", text)
        self.assertNotIn("WARN-EMPTY: ", text)
        self.assertIn("согласовано с крановщиком", text)

    def test_sheet_pdf_contains_expert_transfer_caveat(self):
        project = ProjectInput("Дом", "Москва", 2026, "", "", 0, 30, SiteInput([(-40,-40),(40,-40),(40,40),(-40,40)], [(-5,-5),(5,-5),(5,5),(-5,5)]), [], [])
        placement = Placement("c1", "130 EC-B 6", 0, 0, [], 30, 40, 30, sozr_plan=sample_plan())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sozr.pdf"
            canvas = Canvas(str(path), pagesize=landscape(A3))
            draw_sozr_sheet(canvas, project, placement, sample_plan(), 1)
            canvas.save()
            text = PdfReader(str(path)).pages[0].extract_text()
        self.assertIn("СОЗР", text)
        self.assertIn("эксперт", text.lower())
        self.assertIn("прибор", text.lower())


if __name__ == "__main__":
    unittest.main()
