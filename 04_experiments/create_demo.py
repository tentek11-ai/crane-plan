from pathlib import Path
import sys


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.catalog import load_catalog
from crane_plan.models import Load, ProjectInput, SiteInput, WorkPoint
from crane_plan.optimizer import optimize
from crane_plan.report import generate_report


project = ProjectInput(
    name="Демонстрационный протяжённый монолитный жилой дом",
    city="Москва",
    year=2026,
    author="",
    email="",
    pit_bottom_m=-3.0,
    parapet_m=42.0,
    site=SiteInput(
        boundary=[(-95,-45),(95,-45),(95,45),(-95,45)],
        building=[(-70,-12),(70,-12),(70,12),(-70,12)],
        restricted_zones=[[(-90,25),(-65,25),(-65,40),(-90,40)]],
        unloading_zone=[(-88,-38),(-62,-38),(-62,-26),(-88,-26)],
        storage_zones=[[(-50,-38),(-28,-38),(-28,-26),(-50,-26)]],
        min_crane_to_building_m=1.0,
        max_crane_to_building_m=25.0,
    ),
    loads=[
        Load("Пакет арматуры",1200,120,11.7,0.6,0.6,180),
        Load("Бадья с бетоном 0,5 м³",1400,100,1.4,1.4,2.0,420),
        Load("Поддон газобетона",1200,80,1.2,1.0,1.5,160),
    ],
    work_points=[
        WorkPoint(-66,-10,45,0,"Секция А"), WorkPoint(-32,10,45,1,"Секция Б"),
        WorkPoint(0,-10,45,2,"Секция В"), WorkPoint(32,10,45,1,"Секция Г"),
        WorkPoint(66,-10,45,2,"Секция Д"),
    ],
    priority="cost",
    hours_per_day=24,
    utilization=0.7,
    protective_screen_possible=True,
)

catalog = load_catalog(ROOT / "02_processed_data/cranes/crane_configurations.json")
scenarios = optimize(project, catalog, max_variants=3, step_m=2.0)
output = ROOT.parent / "outputs" / "CranePlan_demo_joint_cranes_1.5.1.pdf"
generate_report(output, project, scenarios)
print(output)
print([scenario.to_dict() for scenario in scenarios])
