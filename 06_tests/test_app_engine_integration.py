import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.app import CranePlanApp  # noqa: E402
import crane_plan.app as app_module  # noqa: E402
from crane_plan.engine import IntegrationStatus  # noqa: E402
from crane_plan.models import Load, Placement, ProjectInput, ScenarioResult, SiteInput, WorkPoint  # noqa: E402


class FakeBooleanVar:
    def __init__(self, value=True, **_kwargs):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class FakeCombo:
    def __init__(self):
        self.values = ()

    def configure(self, **kwargs):
        self.values = tuple(kwargs["values"])


class FakeText:
    def __init__(self):
        self.content = ""

    def delete(self, *_args):
        self.content = ""

    def insert(self, _where, text):
        self.content += text


class AppEngineIntegrationTests(unittest.TestCase):
    def test_project_snapshot_detects_any_input_change_before_release(self):
        first = ProjectInput(
            "Дом", "Москва", 2026, "", "", -3, 27,
            SiteInput([(-10,-10),(10,-10),(10,10),(-10,10)], [(1,-1),(3,-1),(3,1),(1,1)]),
            [Load("Груз",1000,100,1,1,1)], [WorkPoint(2,0,20,0)], loads_verified=True,
        )
        changed = ProjectInput(**{**first.__dict__, "parapet_m": 28})
        app = object.__new__(CranePlanApp)
        app.calculation_input_snapshot = CranePlanApp._project_snapshot(first)
        self.assertTrue(app._calculation_is_current(first))
        self.assertFalse(app._calculation_is_current(changed))

    def test_preview_uses_selected_scenario_and_marks_expert_status(self):
        first = ScenarioResult("PASS", [], [], [])
        selected = ScenarioResult("PASS", [], [], [])
        verifications = [
            SimpleNamespace(status=IntegrationStatus.VERIFIED, release_allowed=True, messages=()),
            SimpleNamespace(status=IntegrationStatus.EXPERT_REVIEW_REQUIRED, release_allowed=False, messages=("проверить",)),
        ]
        app = object.__new__(CranePlanApp)
        app.scenarios = [first, selected]
        app.scenario_verifications = verifications
        app.selected_release_index = 1
        app.release_variant_var = FakeBooleanVar("Вариант 2 — EXPERT_REVIEW_REQUIRED")
        app._project = lambda: object()
        app._calculation_is_current = lambda _project: True
        app.status = FakeBooleanVar("")
        app.update_idletasks = lambda: None
        calls = []

        def stop_after_generation(path, project, scenarios, **kwargs):
            calls.append((path, project, scenarios, kwargs))
            raise RuntimeError("stop after report boundary")

        with (
            patch.object(app_module, "generate_report", side_effect=stop_after_generation),
            patch.object(app_module.messagebox, "showerror"),
        ):
            app.preview_report_pages()

        self.assertEqual(len(calls[0][2]), 1)
        self.assertEqual(calls[0][2][0].status, selected.status)
        self.assertIn("проверить", calls[0][2][0].warnings)
        self.assertIn("НЕ ДЛЯ ВЫПУСКА", calls[0][3]["document_status"])

    def test_save_is_blocked_before_files_for_expert_status(self):
        scenario = ScenarioResult("PASS", [], [], [], total_active_lifts=1, accounted_lifts=1)
        expert = SimpleNamespace(
            status=IntegrationStatus.EXPERT_REVIEW_REQUIRED,
            release_allowed=False,
            messages=("LOGISTICS_SOURCE_REQUIRED: нанесите склад.",),
        )
        app = object.__new__(CranePlanApp)
        app.scenarios = [scenario]
        app.scenario_verifications = [expert]
        app.selected_release_index = 0
        app.release_variant_var = FakeBooleanVar("Вариант 1 — EXPERT_REVIEW_REQUIRED")
        warnings = []
        with patch.object(app_module.messagebox, "showwarning", side_effect=lambda title, text: warnings.append((title, text))):
            app.save_and_report()
        self.assertEqual(len(warnings), 1)
        self.assertIn("эксперт", warnings[0][1].lower())

    def test_verified_save_uses_only_selected_scenario_and_persists_protocol(self):
        project = ProjectInput(
            "Дом", "Москва", 2026, "", "", -3, 27,
            SiteInput(
                [(-10,-10),(10,-10),(10,10),(-10,10)],
                [(1,-1),(3,-1),(3,1),(1,1)],
                unloading_zone=[(-8,-2),(-6,-2),(-6,2),(-8,2)],
                storage_zones=[[(-5,-2),(-3,-2),(-3,2),(-5,2)]],
            ),
            [Load("Груз",1000,100,1,1,1)], [WorkPoint(2,0,20,0)], loads_verified=True,
            restricted_zones_confirmed=True,
        )
        first = ScenarioResult("PASS", [Placement("c","130 EC-B 6",0,0,[0],20,25)], [], [], total_active_lifts=1, accounted_lifts=1)
        selected = ScenarioResult("PASS", [Placement("c","130 EC-B 6",0,0,[0],20,25)], [], [], total_active_lifts=1, accounted_lifts=1)
        protocol = object()
        summaries = [
            SimpleNamespace(status=IntegrationStatus.REJECTED, release_allowed=False, messages=("отказ",), protocol=None, to_dict=lambda: {"status":"REJECTED"}),
            SimpleNamespace(status=IntegrationStatus.VERIFIED, release_allowed=True, messages=(), protocol=protocol, to_dict=lambda: {"status":"VERIFIED"}),
        ]
        app = object.__new__(CranePlanApp)
        app.scenarios = [first, selected]
        app.scenario_verifications = summaries
        app.selected_release_index = 1
        app.release_variant_var = FakeBooleanVar("Вариант 2 — VERIFIED")
        app._project = lambda: project
        app.calculation_input_snapshot = CranePlanApp._project_snapshot(project)
        app.plan_pdf = ""
        app.section_pdf = ""
        app.report_page_order = None
        app.report_excluded_pages = set()
        app.report_path_var = FakeBooleanVar("")
        app.status = FakeBooleanVar("")
        events = []
        with __import__("tempfile").TemporaryDirectory() as tmp:
            app.project_root = Path(tmp)
            with (
                patch.object(app_module, "save_project") as save_project_mock,
                patch.object(app_module, "generate_report", side_effect=lambda path, *_args, **_kwargs: events.append("report") or path) as report_mock,
                patch.object(app_module, "save_protocol_atomic", side_effect=lambda *_args, **_kwargs: events.append("protocol")) as protocol_mock,
                patch.object(app_module.messagebox, "showinfo"),
            ):
                app.save_and_report()
        saved_scenarios = save_project_mock.call_args.args[2]
        self.assertEqual(len(saved_scenarios), 2)
        self.assertEqual(save_project_mock.call_args.kwargs["selected_scenario_index"], 1)
        self.assertEqual(len(save_project_mock.call_args.kwargs["scenario_verifications"]), 2)
        self.assertEqual(report_mock.call_args.args[2], [selected])
        protocol_mock.assert_called_once()
        self.assertLess(events.index("protocol"), events.index("report"))

    def test_run_calculation_verifies_every_legacy_scenario_and_selects_release_variant(self):
        app = object.__new__(CranePlanApp)
        scenario = SimpleNamespace(
            status="PASS",
            placements=[],
            joint_plan=None,
            calendar_days=None,
            accounted_lifts=0,
            total_active_lifts=0,
            crane_work_hours=[],
            warnings=[],
            reasons=[],
        )
        verification = SimpleNamespace(
            status=IntegrationStatus.VERIFIED,
            release_allowed=True,
            messages=(),
            engine_result=None,
            protocol=None,
        )
        app._input_issues = lambda: ([], [])
        app._project = lambda: SimpleNamespace(to_dict=lambda: {"project": "run"})
        app.catalog_path = Path("legacy.json")
        app.user_catalog_path = Path("user.json")
        app.catalog_v3_path = Path("v3.json")
        app.scenarios = [object()]
        app.scenario_verifications = [object()]
        app.selected_release_index = 0
        app.release_variant_var = FakeBooleanVar("")
        app.release_variant_combo = FakeCombo()
        app.report_page_order = [0]
        app.report_excluded_pages = {0}
        app.report_selection_var = FakeBooleanVar("")
        app.results = FakeText()
        app.status = FakeBooleanVar("")
        with (
            patch.object(app_module, "load_catalog", return_value=(object(),)) as load_catalog_mock,
            patch.object(app_module, "optimize", return_value=[scenario]),
            patch.object(app_module, "load_catalog_v3", return_value=(object(),)),
            patch.object(app_module, "verify_scenarios_v21", return_value=(verification,)) as verify_all,
        ):
            app.run_calculation()

        self.assertEqual(app.scenarios, [scenario])
        self.assertEqual(app.scenario_verifications, [verification])
        self.assertEqual(app.selected_release_index, 0)
        self.assertIn("НЕЗАВИСИМАЯ ПРОВЕРКА", app.results.content)
        load_catalog_mock.assert_called_once_with(app.catalog_path, app.user_catalog_path)
        verify_all.assert_called_once()

    def test_missing_v3_catalog_keeps_legacy_scenario_for_expert_review(self):
        app = object.__new__(CranePlanApp)
        scenario = SimpleNamespace(
            status="PASS", placements=[], joint_plan=None, calendar_days=None,
            accounted_lifts=0, total_active_lifts=0, crane_work_hours=[], warnings=[], reasons=[],
        )
        app._input_issues = lambda: ([], [])
        app._project = lambda: SimpleNamespace(to_dict=lambda: {"project": "missing-catalog"})
        app.catalog_path = Path("legacy.json")
        app.user_catalog_path = Path("user.json")
        app.catalog_v3_path = Path("missing-v3.json")
        app.scenarios = []
        app.scenario_verifications = []
        app.selected_release_index = None
        app.release_variant_var = FakeBooleanVar("")
        app.release_variant_combo = FakeCombo()
        app.report_page_order = None
        app.report_excluded_pages = set()
        app.report_selection_var = FakeBooleanVar("")
        app.results = FakeText()
        app.status = FakeBooleanVar("")
        with (
            patch.object(app_module, "load_catalog", return_value=(object(),)),
            patch.object(app_module, "optimize", return_value=[scenario]),
            patch.object(app_module, "load_catalog_v3", side_effect=FileNotFoundError("missing")),
        ):
            app.run_calculation()
        self.assertEqual(app.scenarios, [scenario])
        self.assertEqual(app.scenario_verifications[0].status, IntegrationStatus.EXPERT_REVIEW_REQUIRED)
        self.assertIn("V3_CATALOG_UNAVAILABLE", app.scenario_verifications[0].messages[0])

    def test_reset_calculation_results_clears_stale_selection_and_combo(self):
        app = object.__new__(CranePlanApp)
        app.scenarios = [object()]
        app.scenario_verifications = [object()]
        app.selected_release_index = 0
        app.release_variant_var = FakeBooleanVar("Вариант 1")
        app.release_variant_combo = FakeCombo()

        app._reset_calculation_results()

        self.assertEqual(app.scenarios, [])
        self.assertEqual(app.scenario_verifications, [])
        self.assertIsNone(app.selected_release_index)
        self.assertEqual(app.release_variant_var.get(), "")
        self.assertEqual(app.release_variant_combo.values, ())

    def test_refresh_release_choices_selects_first_releasable_variant(self):
        app = object.__new__(CranePlanApp)
        app.scenario_verifications = [
            SimpleNamespace(status=IntegrationStatus.EXPERT_REVIEW_REQUIRED, release_allowed=False),
            SimpleNamespace(status=IntegrationStatus.VERIFIED_WITH_CONDITIONS, release_allowed=True),
        ]
        app.release_variant_var = FakeBooleanVar("")
        app.release_variant_combo = FakeCombo()

        app._refresh_release_variant_choices()

        self.assertEqual(app.selected_release_index, 1)
        self.assertEqual(app._selected_release_index(), 1)
        self.assertEqual(len(app.release_variant_combo.values), 2)
        self.assertIn("Вариант 2", app.release_variant_var.get())

    def test_render_verification_includes_measured_values_and_protocol_identity(self):
        checks = (
            SimpleNamespace(code="REACH", measured_value=25.0, limit=60.0, units="m", operation_id="OP-W1-L1"),
            SimpleNamespace(code="CAPACITY_INSUFFICIENT", measured_value=1300.0, limit=6000.0, units="kg", operation_id="OP-W1-L1"),
            SimpleNamespace(code="HEIGHT", measured_value=24.4, limit=44.4, units="m", operation_id="OP-W1-L1"),
        )
        placement = SimpleNamespace(configuration_id="LIEBHERR-130-ECB-6-60-V3")
        solution = SimpleNamespace(stages=(SimpleNamespace(placements=(placement,)),))
        protocol = SimpleNamespace(input_sha256="a" * 64, result_sha256="b" * 64, run_id="RUN-1")
        verification = SimpleNamespace(
            status=IntegrationStatus.VERIFIED,
            messages=(),
            engine_result=SimpleNamespace(
                verification=SimpleNamespace(checks=checks),
                protocol=protocol,
                accepted_solution=solution,
            ),
            protocol=protocol,
        )

        text = CranePlanApp._render_scenario_verification(object.__new__(CranePlanApp), verification)

        self.assertIn("ПРОВЕРЕН", text)
        self.assertIn("LIEBHERR-130-ECB-6-60-V3", text)
        self.assertIn("OP-W1-L1", text)
        self.assertIn("25", text)
        self.assertIn("6000", text)
        self.assertIn("4700", text)
        self.assertIn("24.4", text)
        self.assertIn("20", text)
        self.assertIn("RUN-1", text)
        self.assertIn("a" * 64, text)
        self.assertIn("b" * 64, text)

    def test_invalidate_load_confirmation_clears_stale_results(self):
        app = object.__new__(CranePlanApp)
        app.loads_verified = FakeBooleanVar(True)
        app.scenarios = [object()]
        app.scenario_verifications = [object()]
        app.selected_release_index = 0

        app._invalidate_load_confirmation()

        self.assertFalse(app.loads_verified.get())
        self.assertEqual(app.scenarios, [])
        self.assertEqual(app.scenario_verifications, [])
        self.assertIsNone(app.selected_release_index)

    def test_delete_load_invalidates_confirmation_after_actual_delete(self):
        class Tree:
            def selection(self):
                return ("row",)

            def index(self, _item):
                return 0

            def delete(self, _item):
                return None

        app = object.__new__(CranePlanApp)
        app.load_tree = Tree()
        app.work_points = [SimpleNamespace(load_index=0)]
        app.status = SimpleNamespace(set=lambda _value: None)
        calls = []
        app._invalidate_load_confirmation = lambda: calls.append("invalidated")

        app.delete_load()

        self.assertEqual(calls, ["invalidated"])

    def test_edit_load_invalidates_confirmation_after_save(self):
        saved_commands = []

        class Widget:
            def __init__(self, *_args, **kwargs):
                if kwargs.get("text") == "Сохранить":
                    saved_commands.append(kwargs["command"])

            def grid(self, *_args, **_kwargs):
                return self

        class Dialog(Widget):
            def title(self, *_args):
                pass

            def configure(self, **_kwargs):
                pass

            def transient(self, *_args):
                pass

            def grab_set(self):
                pass

            def destroy(self):
                pass

        class Tree:
            def selection(self):
                return ("row",)

            def item(self, _item, option=None, **kwargs):
                if option == "values":
                    return ("Бадья", 2600, 100, 1.8, 1.8, 2.4, 10, "да")
                self.saved = kwargs["values"]

        app = object.__new__(CranePlanApp)
        app.load_tree = Tree()
        calls = []
        app._invalidate_load_confirmation = lambda: calls.append("invalidated")
        with (
            patch.object(app_module.tk, "Toplevel", Dialog),
            patch.object(app_module.tk, "StringVar", FakeBooleanVar),
            patch.object(app_module.tk, "BooleanVar", FakeBooleanVar),
            patch.object(app_module.ttk, "Label", Widget),
            patch.object(app_module.ttk, "Entry", Widget),
            patch.object(app_module.ttk, "Checkbutton", Widget),
            patch.object(app_module.ttk, "Button", Widget),
        ):
            app.edit_load()
            saved_commands[0]()

        self.assertEqual(calls, ["invalidated"])


if __name__ == "__main__":
    unittest.main()
