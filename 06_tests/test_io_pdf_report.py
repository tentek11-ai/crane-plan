import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from pypdf import PdfReader  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.pdfgen.canvas import Canvas  # noqa: E402
from crane_plan.models import JointCranePlan, Load, Placement, ProjectInput, ScenarioResult, SiteInput, WorkPoint  # noqa: E402
from crane_plan.pdf_workspace import calibration_m_per_pixel, inspect_pdf, pixel_to_world, suggest_vector_bounds  # noqa: E402
from crane_plan.project_io import create_project_folder, load_project, save_project  # noqa: E402
from crane_plan.report import generate_report  # noqa: E402


def sample_project():
    project = ProjectInput(
        "Жилой дом", "Москва", 2026, "", "", -3, 45,
        SiteInput([(-50,-50),(50,-50),(50,50),(-50,50)], [(-10,-10),(10,-10),(10,10),(-10,10)]),
        [Load("Бадья",2600,100,1.8,1.8,2.4,100)], [WorkPoint(0,0,48,0)], protective_screen_possible=True,
    )
    project.organization="Тестовая организация"; project.project_code="TEST-PPRK-01"
    project.checked_by="Проверяющий"; project.approved_by="Утверждающий"
    return project


class ProjectIOTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = sample_project()
            folder = create_project_folder(tmp, project)
            save_project(folder, project)
            loaded = load_project(folder)
            self.assertEqual(loaded.name, project.name)
            self.assertEqual(loaded.site.building, project.site.building)
            self.assertEqual(loaded.project_code, "TEST-PPRK-01")

    def test_two_immediate_saves_create_two_revisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=sample_project(); folder=create_project_folder(tmp,project)
            save_project(folder,project); save_project(folder,project)
            self.assertEqual(len(list((folder/"revisions").glob("*.json"))),2)


class PdfWorkspaceTests(unittest.TestCase):
    def test_calibration(self):
        scale = calibration_m_per_pixel((10,10),(110,10),20)
        self.assertEqual(scale,0.2)
        self.assertEqual(pixel_to_world((20,0),(10,10),scale),(2,2))

    def test_vector_pdf_inspection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"vector.pdf"; c=Canvas(str(path))
            for i in range(12): c.line(10,i*10+10,200,i*10+10)
            c.drawString(20,200,"Vector plan"); c.save()
            result=inspect_pdf(path)
            self.assertTrue(result.likely_vector)
            self.assertEqual(result.pages,1)
            bounds=suggest_vector_bounds(path)
            self.assertLess(bounds[0],bounds[2])


class ReportTests(unittest.TestCase):
    def test_report_is_readable_and_multipage(self):
        project=sample_project()
        scenario=ScenarioResult("PASS",[Placement("c","130 EC-B 6",-20,0,[0],25,55)],[],[],3.5,1)
        with tempfile.TemporaryDirectory() as tmp:
            path=generate_report(Path(tmp)/"report.pdf",project,[scenario])
            reader=PdfReader(path)
            self.assertGreaterEqual(len(reader.pages),4)
            text="\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn("130 EC-B 6",text)
            self.assertIn("Жилой дом",text)
            self.assertIn("ТИПОВЫЕ СХЕМЫ СТРОПОВКИ",text)
            self.assertIn("ТЕХНОЛОГИЧЕСКАЯ СХЕМА ПОДЪЁМА",text)
            self.assertIn("TEST-PPRK-01",text)

    def test_report_can_select_and_reorder_pages(self):
        project=sample_project()
        scenario=ScenarioResult("PASS",[Placement("c","130 EC-B 6",-20,0,[0],25,55)],[],[],3.5,1)
        with tempfile.TemporaryDirectory() as tmp:
            full=generate_report(Path(tmp)/"full.pdf",project,[scenario])
            full_reader=PdfReader(full); last=len(full_reader.pages)-1
            selected=generate_report(Path(tmp)/"selected.pdf",project,[scenario],selected_pages=[last,0])
            reader=PdfReader(selected)
            self.assertEqual(len(reader.pages),2)
            self.assertIn("СХЕМА СОВМЕСТНОЙ РАБОТЫ",reader.pages[0].extract_text())
            self.assertIn("ПРОЕКТ ПРОИЗВОДСТВА РАБОТ КРАНАМИ",reader.pages[1].extract_text())

    def test_report_projects_markup_onto_source_plan_and_allows_blank_author(self):
        project=sample_project(); project.author=""; project.email=""
        scenario=ScenarioResult("PASS",[Placement("c","130 EC-B 6",0,0,[0],25,55)],[],[],3.5,1)
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/"plan.pdf"; c=Canvas(str(source),pagesize=A4)
            c.setFont("Helvetica",12); c.drawString(50,780,"SOURCE PLAN"); c.rect(80,120,430,550); c.save()
            section=Path(tmp)/"section.pdf"; c=Canvas(str(section),pagesize=A4)
            c.drawString(50,780,"SOURCE SECTION"); c.rect(220,120,170,520); c.save()
            project.source_plan_pdf=str(source); project.plan_m_per_pixel=.2
            project.plan_origin_x_px=300; project.plan_origin_y_px=400
            project.source_section_pdf=str(section); project.section_m_per_pixel=.1
            project.section_origin_x_px=300; project.section_origin_y_px=900
            project.section_axis_dx=0; project.section_axis_dy=-1
            path=generate_report(Path(tmp)/"report.pdf",project,[scenario])
            reader=PdfReader(path); text="\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn("Эскиз спроецирован",text)
            self.assertIn("Привязка выполнена",text)
            self.assertIn("____________________________",text)
            self.assertIn("SOURCE PLAN",text)
            self.assertIn("SOURCE SECTION",text)

    def test_joint_crane_sheet_contains_calculated_sectors(self):
        project=sample_project()
        p1=Placement("c1","130 EC-B 6",-25,0,[0],25,55,60,[0,1],58,320,410,345,375)
        p2=Placement("c2","130 EC-B 6",25,0,[],25,55,60,[2,3],59,130,220,165,195)
        joint=JointCranePlan(50,5,2,3,2,2,True,2200,[(-10,-20),(10,-20),(10,20),(-10,20)],[],2,2,4,["Этап 1","Этап 2","Этап 3","Этап 4"])
        scenario=ScenarioResult("PASS_WITH_CONDITIONS",[p1,p2],[],[],3.5,1,joint)
        with tempfile.TemporaryDirectory() as tmp:
            path=generate_report(Path(tmp)/"joint.pdf",project,[scenario])
            reader=PdfReader(path); coordination=reader.pages[-2]; schedule=reader.pages[-1]
            text=(coordination.extract_text() or "")+(schedule.extract_text() or "")
            self.assertGreater(float(coordination.mediabox.width),1100)
            self.assertGreater(float(schedule.mediabox.width),1100)
            self.assertIn("130 EC-B 6",text)
            self.assertIn("5.0",text)
            self.assertIn("320.0",text)
            self.assertIn("3.0",text)
            self.assertIn("4.0",text)


if __name__ == "__main__":
    unittest.main()
