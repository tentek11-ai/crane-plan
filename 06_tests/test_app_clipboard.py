import sys
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.app import CranePlanApp  # noqa: E402


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class ClipboardEditingTests(unittest.TestCase):
    def test_ctrl_v_uses_physical_v_key_and_pastes_word_text_into_project_field(self):
        app = CranePlanApp(resource_root=ROOT)
        app.withdraw()
        try:
            app.update_idletasks()
            project_name_entry = next(
                child
                for child in descendants(app)
                if child.winfo_class() == "TEntry"
                and child.cget("textvariable") == str(app.project_name)
            )
            app.clipboard_clear()
            app.clipboard_append("Жилой комплекс\r\nКорпус 1")
            app.update()

            result = app._handle_text_shortcut(
                SimpleNamespace(
                    widget=project_name_entry,
                    state=0x0004,
                    keycode=86,
                    keysym="Cyrillic_em",
                )
            )

            self.assertEqual(result, "break")
            self.assertEqual(app.project_name.get(), "Жилой комплекс Корпус 1")
        finally:
            app.destroy()

    def test_edit_commands_support_select_copy_cut_and_paste(self):
        app = CranePlanApp(resource_root=ROOT)
        app.withdraw()
        try:
            app.update_idletasks()
            project_name_entry = next(
                child
                for child in descendants(app)
                if child.winfo_class() == "TEntry"
                and child.cget("textvariable") == str(app.project_name)
            )
            app.project_name.set("Башня 1")

            self.assertEqual(app._text_edit_action(project_name_entry, "select_all"), "break")
            self.assertEqual(app._text_edit_action(project_name_entry, "copy"), "break")
            self.assertEqual(app.clipboard_get(), "Башня 1")
            self.assertEqual(app._text_edit_action(project_name_entry, "cut"), "break")
            self.assertEqual(app.project_name.get(), "")
            self.assertEqual(app._text_edit_action(project_name_entry, "paste"), "break")
            self.assertEqual(app.project_name.get(), "Башня 1")
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()
