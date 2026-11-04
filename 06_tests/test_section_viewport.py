import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from PIL import Image  # noqa: E402
from crane_plan.app import CranePlanApp  # noqa: E402


class FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeCanvas:
    def __init__(self, scroll_x=0.0, scroll_y=0.0, width=200, height=200):
        self.scroll_x = scroll_x
        self.scroll_y = scroll_y
        self.width = width
        self.height = height
        self.ovals = []
        self.lines = []
        self.config = {}

    def canvasx(self, value):
        return value + self.scroll_x

    def canvasy(self, value):
        return value + self.scroll_y

    def create_oval(self, *coords, **_kwargs):
        self.ovals.append(coords)

    def create_line(self, *coords, **_kwargs):
        self.lines.append(coords)

    def create_image(self, *_args, **_kwargs):
        return 1

    def delete(self, *_args):
        return None

    def configure(self, **kwargs):
        self.config.update(kwargs)

    def update_idletasks(self):
        return None

    def winfo_width(self):
        return self.width

    def winfo_height(self):
        return self.height


def bare_app():
    app = CranePlanApp.__new__(CranePlanApp)
    app.section_pdf = "section.pdf"
    app.section_crop_box = (0.0, 0.0, 1.0, 1.0)
    app.section_crop_active = False
    app.section_background_intensity = FakeVar("35")
    app.section_zoom = 1.0
    app.section_image_scale = 1.0
    app.section_calibration_points = []
    app.section_m_per_pixel = None
    app.section_origin_px = None
    app.section_axis = (0.0, -1.0)
    app.section_mode = "calibration"
    app.section_building_points = []
    app.section_contour_pixels = []
    app.section_contour_closed = False
    app.section_distance_var = FakeVar("10")
    app.status = FakeVar("")
    return app


class SectionViewportTests(unittest.TestCase):
    def test_closing_contour_rebases_its_bottom_without_moving_pdf_overlay(self):
        app = bare_app()
        app.section_canvas = FakeCanvas()
        app.section_mode = "building"
        app.section_m_per_pixel = 0.1
        app.section_origin_px = (100.0, 200.0)
        app.section_axis = (0.0, -1.0)
        app.section_building_points = [
            (0.0, 2.95),
            (12.0, 2.95),
            (12.0, 33.95),
            (0.0, 33.95),
        ]
        app.scenarios = [object()]
        pixels_before = [app._section_world_to_pixel(point) for point in app.section_building_points]

        app.finish_section_building_contour()

        pixels_after = [app._section_world_to_pixel(point) for point in app.section_building_points]
        for actual, expected in zip(
            [height for _, height in app.section_building_points],
            [0.0, 0.0, 31.0, 31.0],
        ):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(app.section_origin_px, (100.0, 170.5))
        for before, after in zip(pixels_before, pixels_after):
            self.assertAlmostEqual(before[0], after[0])
            self.assertAlmostEqual(before[1], after[1])

    def test_redraw_preserves_the_two_selected_calibration_points(self):
        app = bare_app()
        app.section_canvas = FakeCanvas()
        app.section_image_scale = 2.0
        app.section_calibration_points = [(10.0, 10.0), (40.0, 50.0)]
        app.section_origin_px = (10.0, 10.0)
        app.section_m_per_pixel = 0.5
        app.section_axis = (0.6, 0.8)
        app.pit_bottom = FakeVar("-5")
        app.parapet = FakeVar("95")

        app._redraw_section_calibration()

        self.assertEqual(app.section_canvas.lines[0], (20.0, 20.0, 80.0, 100.0))

    def test_calibration_marker_uses_scrolled_canvas_coordinates(self):
        app = bare_app()
        app.section_canvas = FakeCanvas(scroll_x=100, scroll_y=200)
        app.section_image_scale = 2.0

        app.on_section_click(SimpleNamespace(x=10, y=20))

        self.assertEqual(app.section_calibration_points, [(55.0, 110.0)])
        self.assertEqual(app.section_canvas.ovals[0], (106.0, 216.0, 114.0, 224.0))

    def test_section_pdf_is_physically_enlarged_at_two_hundred_percent(self):
        app = bare_app()
        app.section_canvas = FakeCanvas(width=104, height=104)
        app.section_zoom = 2.0
        source = Image.new("RGB", (100, 100), "white")

        with patch("crane_plan.app.render_page", return_value=source), patch(
            "crane_plan.app.ImageTk.PhotoImage", side_effect=lambda image: image
        ):
            app._show_section()

        self.assertEqual(app.section_image_scale, 2.0)
        self.assertEqual(app.section_image.size, (200, 200))
        self.assertEqual(app.section_canvas.config["scrollregion"], (0, 0, 200, 200))


if __name__ == "__main__":
    unittest.main()
