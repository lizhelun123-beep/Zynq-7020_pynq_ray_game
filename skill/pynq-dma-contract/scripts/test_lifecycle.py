"""Positive/negative host lifecycle contracts, no device APIs."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "examples/lifecycle.py"
spec = importlib.util.spec_from_file_location("lifecycle_example", path)
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


class Clock:
    def __init__(self):
        self.now = 0.0

    def read(self):
        return self.now

    def sleep(self, duration):
        self.now += duration


class LifecycleTests(unittest.TestCase):
    def prepared(self, **kwargs):
        slot, engine = demo.Slot(192), demo.FakeEngine(**kwargs)
        demo.copy_rows(slot, bytearray(range(48)), 12, 3, 16, 64)
        engine.flush(slot)
        demo.submit(slot, engine)
        return slot, engine

    def test_distinct_row_strides_and_padding_preserved(self):
        source, slot = bytearray(range(48)), demo.Slot(192)
        demo.copy_rows(slot, source, 12, 3, 16, 64)
        for y in range(3):
            self.assertEqual(slot.data[y * 64:y * 64 + 12], source[y * 16:y * 16 + 12])
            self.assertEqual(slot.data[y * 64 + 12:(y + 1) * 64], bytearray([0xA5] * 52))

    def test_active_slot_and_invalid_layout_rejected(self):
        slot = demo.Slot(192)
        slot.owner = "device"
        with self.assertRaises(ValueError):
            demo.copy_rows(slot, bytearray(48), 12, 3, 16, 64)
        slot.owner = "cpu"
        for args in [(12, 3, 8, 64), (12, 3, 16, 8), (12, 3, 16, 128)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                demo.copy_rows(slot, bytearray(48), *args)

    def test_missing_sync_and_rewrite_after_sync_rejected(self):
        slot, engine = demo.Slot(192), demo.FakeEngine()
        with self.assertRaises(ValueError):
            demo.submit(slot, engine)
        engine.flush(slot)
        demo.copy_rows(slot, bytearray(48), 12, 3, 16, 64)
        with self.assertRaises(ValueError):
            demo.submit(slot, engine)

    def test_direct_source_destination_alias_rejected(self):
        slot = demo.Slot(192)
        with self.assertRaises(ValueError):
            demo.copy_rows(slot, slot.data, 12, 3, 16, 64)

    def test_success_has_explicit_stop_confirmation(self):
        slot, engine = self.prepared()
        clock = Clock()
        self.assertTrue(demo.release_after_stop(slot, engine, 0.03, clock.read, clock.sleep))
        self.assertEqual(slot.owner, "released")
        self.assertEqual(engine.events, ["flush", "start", "request_stop"])

    def test_timeout_retains_device_ownership(self):
        slot, engine = self.prepared(can_halt=False)
        clock = Clock()
        self.assertFalse(demo.release_after_stop(slot, engine, 0.003, clock.read, clock.sleep))
        self.assertEqual(slot.owner, "device")
        self.assertFalse(slot.released)

    def test_partial_start_exception_does_not_roll_back_ownership(self):
        slot, engine = demo.Slot(192), demo.FakeEngine(fail_start=True)
        engine.flush(slot)
        with self.assertRaises(RuntimeError):
            demo.submit(slot, engine)
        self.assertEqual(slot.owner, "device")
        self.assertFalse(slot.released)

    def test_stop_or_status_exception_retains_ownership(self):
        for method in ["request_stop", "read_status"]:
            slot, engine = self.prepared(can_halt=False)
            def fail():
                raise RuntimeError("fake adapter failed")
            setattr(engine, method, fail)
            clock = Clock()
            with self.subTest(method=method), self.assertRaises(RuntimeError):
                demo.release_after_stop(slot, engine, 0.003, clock.read, clock.sleep)
            self.assertEqual(slot.owner, "device")
            self.assertFalse(slot.released)

    def test_running_and_halted_together_not_release_proof(self):
        slot, engine = self.prepared(can_halt=False)
        engine.read_status = lambda: dict(running=True, halted=True, error=False)
        clock = Clock()
        self.assertFalse(demo.release_after_stop(slot, engine, 0.003, clock.read, clock.sleep))
        self.assertEqual(slot.owner, "device")

    def test_invalid_timeout_does_not_request_stop(self):
        for value in (True, 0, -1, float("nan"), float("inf"), "1", 10 ** 1000):
            slot, engine = self.prepared()
            with self.subTest(value=type(value).__name__), self.assertRaises(ValueError):
                demo.release_after_stop(slot, engine, value)
            self.assertNotIn("request_stop", engine.events)

    def test_late_status_or_error_never_releases(self):
        for late in (False, True):
            slot, engine = self.prepared()
            clock = Clock()
            def status():
                if late:
                    clock.now = 1.0
                return dict(running=False, halted=True, error=not late)
            engine.read_status = status
            self.assertFalse(demo.release_after_stop(slot, engine, .01, clock.read, clock.sleep))
            self.assertEqual(slot.owner, "device")


if __name__ == "__main__":
    unittest.main()
