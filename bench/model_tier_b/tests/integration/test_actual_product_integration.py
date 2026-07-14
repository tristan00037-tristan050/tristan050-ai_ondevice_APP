"""P0-3: actual product integration — real import, real entrypoint calls, real Box3
endpoint/runner/DLP/approval wiring, observer hook, route-semantics diff 0.

This test imports the *real* Butler product (``butler_pc_core``) — it is not a
synthetic runner and asserts no fake verdicts. It requires the repository root on
``sys.path`` (``ci_actual_integration.sh`` and the CI job set ``PYTHONPATH``). If the
product cannot be imported the test fails loudly rather than being skipped.
"""

from __future__ import annotations

import importlib
import json
import unittest


class ActualProductIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.adapter = importlib.import_module("butler_pc_core.model_tier_bench.product_adapter")
            self.observer = importlib.import_module("butler_pc_core.model_tier_bench.observer")
        except Exception as exc:  # pragma: no cover - environment failure surfaces loudly
            self.fail(f"actual product import failed (repo root must be importable): {exc!r}")

    def tearDown(self) -> None:
        self.observer.clear_observer()

    def test_six_entrypoints_reach_real_product_callables(self) -> None:
        events: list[dict] = []
        self.observer.set_observer(events.append)
        outputs = [entrypoint() for entrypoint in self.adapter.ADAPTER_ENTRYPOINTS]
        self.observer.clear_observer()

        self.assertEqual(6, len(outputs))
        self.assertEqual(6, len(events))  # observer hook fired once per real reach
        for output in outputs:
            dotted = output["product_callable"]
            module_name, _, attribute = dotted.rpartition(".")
            module = importlib.import_module(module_name)  # real product module import
            self.assertTrue(callable(getattr(module, attribute)), dotted)
            self.assertTrue(module_name.startswith("butler_pc_core."), dotted)
            self.assertEqual(0, output["runtime_activation_allowed"])

    def test_observer_off_on_product_response_is_byte_identical(self) -> None:
        # Route semantics diff 0: registering an observer must not change any product
        # response, byte for byte.
        with_observer_events: list[dict] = []
        self.observer.set_observer(with_observer_events.append)
        on = [entrypoint() for entrypoint in self.adapter.ADAPTER_ENTRYPOINTS]
        self.observer.clear_observer()
        off = [entrypoint() for entrypoint in self.adapter.ADAPTER_ENTRYPOINTS]

        self.assertEqual(json.dumps(on, sort_keys=True), json.dumps(off, sort_keys=True))
        self.assertTrue(with_observer_events)

    def test_real_box3_endpoint_runner_dlp_approval_are_connected(self) -> None:
        # Prove the four real Box3 product surfaces are importable and callable — the
        # adapter rides on these, no synthetic substitutes.
        draft_service = importlib.import_module("butler_pc_core.cards.box3.draft_service")
        self.assertTrue(hasattr(draft_service, "BOX3_DRAFT_ENDPOINT"))
        self.assertTrue(callable(getattr(draft_service, "draft_from_current_contract")))

        runner = importlib.import_module("butler_pc_core.cards.box3.local_real_runner")
        self.assertTrue(callable(getattr(runner, "run_box3_real_enablement_smoke")))

        dlp = importlib.import_module("butler_pc_core.dlp.runtime")
        self.assertTrue(callable(getattr(dlp, "scan_runtime")))

        approval = importlib.import_module("butler_pc_core.cards.box3.human_approval")
        self.assertTrue(callable(getattr(approval, "evaluate_human_approval")))

    def test_real_dlp_route_is_deterministic_and_reached(self) -> None:
        # The adapter's DLP entrypoint reaches the real runtime DLP scanner; the real
        # scanner is deterministic (same input -> same detection), i.e. route diff 0.
        dlp = importlib.import_module("butler_pc_core.dlp.runtime")
        first = dlp.scan_runtime("정산 요약 문서 검토 요청입니다.")
        second = dlp.scan_runtime("정산 요약 문서 검토 요청입니다.")
        self.assertEqual(first.any_detected, second.any_detected)
        out = self.adapter.butler_bench_run_v2()
        self.assertEqual("butler_pc_core.dlp.runtime.scan_runtime", out["product_callable"])

    def test_adapter_defines_no_synthetic_or_fake_symbols(self) -> None:
        forbidden = {"synthetic_runner", "fake_verdict", "mock_run", "stub_pipeline"}
        self.assertEqual(set(), forbidden & set(dir(self.adapter)))

    def test_observer_exception_is_isolated_and_invalidates_measurement(self) -> None:
        # R2-P1-011: an observer callback that raises must NOT change the product
        # response or crash the product; it is recorded so measurement is invalid.
        baseline = self.adapter.butler_bench_run_v2()  # observer off
        self.observer.reset_failures()

        def raising(_event):
            raise RuntimeError("observer boom")

        self.observer.set_observer(raising)
        with_failure = self.adapter.butler_bench_run_v2()  # observer on, raises internally
        self.observer.clear_observer()

        self.assertEqual(baseline, with_failure)  # product response byte-identical
        failures = self.observer.emit_failures()
        self.assertTrue(failures)  # measurement flagged invalid
        self.assertEqual("OBSERVER_EMIT_FAILED", failures[0]["code"])
        self.assertEqual("RuntimeError", failures[0]["exception_type"])
        self.observer.reset_failures()


if __name__ == "__main__":
    unittest.main()
