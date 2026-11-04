import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.app import CranePlanApp  # noqa: E402


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class WorkPointDialogTests(unittest.TestCase):
    def test_height_entry_is_shown_when_project_elevation_is_temporarily_empty(self):
        app = CranePlanApp(resource_root=ROOT)
        app.withdraw()
        try:
            app.parapet.set("")
            app._add_work_point_dialog((10.0, 15.0), (100.0, 150.0))
            app.update_idletasks()

            dialog = next(
                child
                for child in app.winfo_children()
                if isinstance(child, tk.Toplevel) and child.title() == "Точка подачи груза"
            )
            height_entries = [
                child
                for child in descendants(dialog)
                if child.winfo_class() in {"TEntry", "Entry"}
                and int(child.grid_info().get("row", -1)) == 1
            ]

            self.assertEqual(len(height_entries), 1)
            self.assertEqual(height_entries[0].get(), "")
            height_entries[0].insert(0, "37,5")
            add_button = next(
                child
                for child in descendants(dialog)
                if child.winfo_class() == "TButton" and child.cget("text") == "Добавить"
            )
            with patch("crane_plan.app.messagebox.showerror", side_effect=AssertionError("unexpected dialog error")):
                add_button.invoke()

            self.assertEqual(len(app.work_points), 1)
            self.assertEqual(app.work_points[0].level_m, 37.5)
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()
