import sys
import unittest
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.app import CranePlanApp  # noqa: E402
import crane_plan.app as app_module  # noqa: E402
from crane_plan.engine import IntegrationStatus  # noqa: E402
from crane_plan.models import Load, Placement, ProjectInput, RestrictedZone, RestrictedZoneKind, ScenarioResult, SiteInput, WorkPoint  # noqa: E402
from crane_plan.zone_editor import ZoneEditorResult  # noqa: E402


from test_pprk_context import _fixture


def render_stub_pdf(path, *_args, **_kwargs):
    from reportlab.pdfgen.canvas import Canvas
    canvas = Canvas(str(path), invariant=1)
    canvas.drawString(50, 500, "Controlled publication test")
    canvas.showPage()
    canvas.save()
    return path


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


@dataclass(frozen=True)
class DummyProtocol:
    warning_acceptances: tuple = ()


@dataclass(frozen=True)
class DummyEngineResult:
    protocol: DummyProtocol


class AppEngineIntegrationTests(unittest.TestCase):
    def test_user_can_select_warning_and_acceptance_enters_protocol(self):
        app = object.__new__(CranePlanApp)
        app.scenarios = [ScenarioResult("PASS_WITH_CONDITIONS", [], [], ["первое", "второе"])]
        protocol = DummyProtocol()
        app.scenario_verifications = [
            app_module.ScenarioVerificationV21(
                0, IntegrationStatus.VERIFIED_WITH_CONDITIONS, True, (),
                DummyEngineResult(protocol), protocol,
            )
        ]
        app.selected_release_index = 0
        app.release_variant_var = FakeBooleanVar("Вариант 1 — VERIFIED_WITH_CONDITIONS")
        app.release_variant_combo = FakeCombo()
        app.calculation_input_snapshot = '{"project":"same"}'
        app.warning_acceptances = []
        app.status = FakeBooleanVar("")
        app._draw_selected_sozr = lambda: None
        with (
            patch.object(app_module.simpledialog, "askinteger", return_value=2),
            patch.object(app_module.simpledialog, "askstring", return_value=""),
        ):
            app.accept_selected_warning()
        self.assertEqual(len(app.warning_acceptances), 1)
        self.assertEqual(app.scenario_verifications[0].status, IntegrationStatus.EXPERT_REVIEW_REQUIRED)
        self.assertTrue(app.scenario_verifications[0].release_allowed)
        self.assertEqual(len(app.scenario_verifications[0].protocol.warning_acceptances), 1)
    def test_finishing_restricted_contour_adds_only_saved_typed_zone(self):
        class FakeCanvas:
            def create_line(self, *_args, **_kwargs):
                return 1

            def delete(self, *_args, **_kwargs):
                return None

        app = object.__new__(CranePlanApp)
        app.mode = "restricted"
        app.canvas = FakeCanvas()
        app.contour_pixels = {"restricted": [(0, 0), (4, 0), (4, 3)]}
        app.current_zone_points = [(0, 0), (4, 0), (4, 3)]
        app.restricted_zones = []
        app.origin_px = None
        app.m_per_pixel = None
        app.selected_restricted_zone_id = None
        app.status = FakeBooleanVar("")
        app._refresh_zone_table = lambda: None
        saved = RestrictedZone(
            "zone-1", "ЛЭП", RestrictedZoneKind.HEIGHT_OBSTACLE,
            [(0, 0), (4, 0), (4, 3)], 12.0,
        )

        with patch.object(app_module, "edit_restricted_zone", return_value=ZoneEditorResult(saved, False)):
            app.finish_contour()

        self.assertEqual(app.restricted_zones, [saved])
        self.assertEqual(app.current_zone_points, [])

        app.contour_pixels["restricted"] = [(0, 0), (1, 0), (1, 1)]
        app.current_zone_points = [(0, 0), (1, 0), (1, 1)]
        with patch.object(app_module, "edit_restricted_zone", return_value=ZoneEditorResult(None, True)):
            app.finish_contour()

        self.assertEqual(app.restricted_zones, [saved])
        self.assertEqual(app.current_zone_points, [])

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
        project, selected, verified = _fixture()
        first = ScenarioResult("PASS", [], [], [])
        verifications = [verified, app_module.ScenarioVerificationV21(
            1, IntegrationStatus.EXPERT_REVIEW_REQUIRED, False, ("проверить",), None, None
        )]
        app = object.__new__(CranePlanApp)
        app.scenarios = [first, selected]
        app.scenario_verifications = verifications
        app.selected_release_index = 1
        app.release_variant_var = FakeBooleanVar("Вариант 2 — EXPERT_REVIEW_REQUIRED")
        app._project = lambda: project
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
        self.assertEqual(calls[0][2], [selected])
        self.assertIsNotNone(calls[0][3].get("bundle"))
        self.assertIn("НЕ ДЛЯ ВЫПУСКА", calls[0][3]["document_status"])

    def test_save_is_blocked_before_files_for_expert_status(self):
        project, scenario, verified = _fixture()
        expert = replace(verified,
            status=IntegrationStatus.EXPERT_REVIEW_REQUIRED,
            release_allowed=False,
            messages=("LOGISTICS_SOURCE_REQUIRED: нанесите склад.",),
            protocol=None,
        )
        app = object.__new__(CranePlanApp)
        app.scenarios = [scenario]
        app.scenario_verifications = [expert]
        app.selected_release_index = 0
        app.release_variant_var = FakeBooleanVar("Вариант 1 — EXPERT_REVIEW_REQUIRED")
        app._project = lambda: project
        app.calculation_input_snapshot = app._project_snapshot(project)
        warnings = []
        with patch.object(app_module.messagebox, "showwarning", side_effect=lambda title, text: warnings.append((title, text))):
            app.save_and_report()
        self.assertEqual(len(warnings), 1)
        self.assertIn("эксперт", warnings[0][1].lower())

    def test_verified_save_uses_only_selected_scenario_and_persists_protocol(self):
        project, selected, verified = _fixture()
        first = ScenarioResult("PASS", [], [], [])
        protocol = verified.protocol
        summaries = [verified, app_module.ScenarioVerificationV21(
            1, verified.status, True, (), verified.engine_result, protocol
        )]
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
        save_errors = []
        test_temp_root = ROOT / "tmp" / "test-temp"
        test_temp_root.mkdir(parents=True, exist_ok=True)
        with __import__("tempfile").TemporaryDirectory(dir=test_temp_root) as tmp:
            app.project_root = Path(tmp)
            app.preview_fingerprint = "previous"
            project.pprk_release.title = "Изменено после предпросмотра"
            def render(path, _project, scenarios, *, bundle, **_kwargs):
                self.assertEqual(dict(bundle.sheet("service.title").fields)["title"], "Изменено после предпросмотра")
                events.append("report")
                render_stub_pdf(path)
                return path
            with (
                patch.object(app_module, "save_project") as save_project_mock,
                patch.object(app_module, "generate_report", side_effect=render) as report_mock,
                patch.object(app_module, "save_protocol_atomic", side_effect=lambda *_args, **_kwargs: events.append("protocol")) as protocol_mock,
                patch.object(app_module.messagebox, "showinfo"),
                patch.object(app_module.messagebox, "showerror", side_effect=lambda title, text: save_errors.append((title, text))),
            ):
                app.save_and_report()
        self.assertEqual(save_errors, [])
        saved_scenarios = save_project_mock.call_args.args[2]
        self.assertEqual(len(saved_scenarios), 2)
        self.assertEqual(save_project_mock.call_args.kwargs["selected_scenario_index"], 1)
        self.assertEqual(len(save_project_mock.call_args.kwargs["scenario_verifications"]), 2)
        self.assertEqual(report_mock.call_args.args[2], [selected])
        protocol_mock.assert_called_once()
        self.assertIn("report", events)

    def test_failed_protocol_save_preserves_previous_pdf(self):
        project, scenario, verification = _fixture()
        app = object.__new__(CranePlanApp)
        app.scenarios = [scenario]
        app.scenario_verifications = [verification]
        app.selected_release_index = 0
        app._project = lambda: project
        app.calculation_input_snapshot = app._project_snapshot(project)
        with __import__("tempfile").TemporaryDirectory() as tmp:
            app.project_root = Path(tmp)
            folder = app_module.create_project_folder(tmp, project)
            prior = folder / "reports" / "ППРк_предварительный.pdf"
            prior.write_bytes(b"previous")
            with (
                patch.object(app_module, "generate_report", side_effect=render_stub_pdf),
                patch.object(app_module, "save_protocol_atomic", side_effect=OSError("Ошибка записи протокола")),
                patch.object(app_module.messagebox, "showwarning"),
                patch.object(app_module.messagebox, "showerror"),
            ):
                app.save_and_report()
            self.assertEqual(prior.read_bytes(), b"previous")

    def test_variant_verification_index_mismatch_is_rejected(self):
        project, scenario, verification = _fixture()
        app = object.__new__(CranePlanApp)
        app.scenarios = [scenario, scenario]
        app.scenario_verifications = [verification, verification]
        app.selected_release_index = 1
        app._project = lambda: project
        app.calculation_input_snapshot = app._project_snapshot(project)
        with self.assertRaisesRegex(ValueError, "вариант"):
            app._current_release_inputs()

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

