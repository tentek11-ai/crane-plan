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
from crane_plan.pdf_workspace import PdfViewportTransform, calibration_m_per_pixel, inspect_pdf, pixel_to_world, render_page, suggest_vector_bounds  # noqa: E402
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
            project.plan_crop_box=(.1,.2,.9,.8); project.plan_background_intensity=.42
            project.floors=24; project.tie_length_m=12; project.tie_angle_deg=60; project.section_building_contour=[(0,0),(20,0),(20,60),(0,60)]
            folder = create_project_folder(tmp, project)
            save_project(folder, project)
            loaded = load_project(folder)
            self.assertEqual(loaded.name, project.name)
            self.assertEqual(loaded.site.building, project.site.building)
            self.assertEqual(loaded.project_code, "TEST-PPRK-01")
            self.assertEqual(loaded.plan_crop_box, (.1,.2,.9,.8))
            self.assertEqual(loaded.plan_background_intensity, .42)
            self.assertEqual(loaded.floors,24)
            self.assertEqual(loaded.section_building_contour,[(0,0),(20,0),(20,60),(0,60)])

    def test_two_immediate_saves_create_two_revisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            project=sample_project(); folder=create_project_folder(tmp,project)
            save_project(folder,project); save_project(folder,project)
            self.assertEqual(len(list((folder/"revisions").glob("*.json"))),2)


class PdfWorkspaceTests(unittest.TestCase):
    def test_viewport_zoom_keeps_document_point_under_cursor(self):
        viewport=PdfViewportTransform(scale=1.0,offset_x=15,offset_y=-8)
        cursor=(320,240); before=viewport.view_to_document(cursor)
        viewport.zoom_at(cursor,2.0)
        self.assertAlmostEqual(viewport.view_to_document(cursor)[0],before[0])
        self.assertAlmostEqual(viewport.view_to_document(cursor)[1],before[1])
        viewport.pan_by(30,-12)
        self.assertEqual(viewport.document_to_view(before),(350,228))

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

    def test_render_page_crops_and_fades_background(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"crop.pdf"; c=Canvas(str(path),pagesize=(400,200))
            c.setFillColorRGB(0,0,0); c.rect(0,0,200,200,stroke=0,fill=1); c.save()
            cropped=render_page(path,0,1.0,(0,0,.5,1),.35)
            self.assertEqual(cropped.size,(200,200))
            self.assertGreater(sum(cropped.getpixel((100,100)))/3,150)
            right=render_page(path,0,1.0,(.5,0,1,1),.35)
            self.assertGreater(sum(right.getpixel((100,100)))/3,245)


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
            project.plan_background_intensity=1.0; project.section_background_intensity=1.0
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

    def test_report_contains_tie_in_schedule(self):
        project=sample_project(); project.parapet_m=90; project.floors=30; project.tie_length_m=12; project.tie_angle_deg=60
        project.section_building_contour=[(0,0),(22,0),(22,90),(0,90)]
        placement=Placement(
            "c","130 EC-B 6",-10,0,[0],25,87.8,25,
            max_free_standing_height_m=44.4,accepted_crane_height_m=89.4,
            tie_in_levels_m=[38.4,63.4],tie_in_stage_sections=[5,4],total_additional_sections=9,
            required_tie_length_m=5.8,tie_geometry_ok=True,tie_nearest_floors=[13,21],
        )
        scenario=ScenarioResult("PASS_WITH_CONDITIONS",[placement],[],[],3.5,1)
        with tempfile.TemporaryDirectory() as tmp:
            path=generate_report(Path(tmp)/"ties.pdf",project,[scenario])
            text="\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
            self.assertIn("К1/П1",text)
            self.assertIn("38.4",text)
            self.assertIn("проектом пристёжек",text)


if __name__ == "__main__":
    unittest.main()
