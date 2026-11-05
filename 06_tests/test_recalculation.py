import sys
import unittest
from concurrent.futures import Future
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "05_src"))

from crane_plan.recalculation import CalculationState, RecalculationCoordinator  # noqa: E402


class FakeRuntime:
    def __init__(self):
        self.scheduled = []
        self.cancelled = []
        self.futures = []

    def schedule(self, delay, callback):
        handle = [delay, callback, False]
        self.scheduled.append(handle)
        return handle

    def cancel(self, handle):
        handle[2] = True
        self.cancelled.append(handle)

    def submit(self, job):
        future = Future()
        future.job = job
        self.futures.append(future)
        return future

    def run_last_scheduled(self):
        handle = self.scheduled[-1]
        self.assert_not_cancelled(handle)
        handle[1]()

    @staticmethod
    def assert_not_cancelled(handle):
        if handle[2]:
            raise AssertionError("scheduled callback was cancelled")


class RecalculationCoordinatorTests(unittest.TestCase):
    def make_coordinator(self):
        runtime = FakeRuntime()
        source = {"hash": "h1", "payload": 1}
        states = []
        results = []
        coordinator = RecalculationCoordinator(
            snapshot_factory=lambda: (source["hash"], source["payload"]),
            calculate=lambda payload: payload * 10,
            schedule=runtime.schedule,
            cancel_schedule=runtime.cancel,
            submit=runtime.submit,
            on_state=states.append,
            on_result=results.append,
            delay_ms=600,
        )
        return coordinator, runtime, source, states, results

    def test_change_is_debounced_and_button_runs_immediately(self):
        coordinator, runtime, _source, states, _results = self.make_coordinator()
        coordinator.mark_changed()
        first = runtime.scheduled[-1]
        coordinator.mark_changed()
        self.assertTrue(first[2])
        self.assertEqual(runtime.scheduled[-1][0], 600)
        coordinator.recalculate_now()
        self.assertTrue(runtime.scheduled[-1][2])
        self.assertEqual(states[-1], CalculationState.RUNNING)
        self.assertEqual(len(runtime.futures), 1)

    def test_late_result_from_old_revision_cannot_replace_new_result(self):
        coordinator, runtime, source, states, results = self.make_coordinator()
        coordinator.recalculate_now()
        old_future = runtime.futures[-1]
        source.update(hash="h2", payload=2)
        coordinator.mark_changed()
        coordinator.recalculate_now()
        new_future = runtime.futures[-1]

        old_future.set_result(10)
        runtime.run_last_scheduled()
        self.assertEqual(results, [])

        new_future.set_result(20)
        runtime.run_last_scheduled()
        self.assertEqual(results, [20])
        self.assertEqual(states[-1], CalculationState.CURRENT)

    def test_changed_hash_rejects_completion_even_without_extra_result(self):
        coordinator, runtime, source, _states, results = self.make_coordinator()
        coordinator.recalculate_now()
        future = runtime.futures[-1]
        source["hash"] = "changed-without-mark"
        future.set_result(10)
        runtime.run_last_scheduled()
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
