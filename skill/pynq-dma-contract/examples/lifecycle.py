"""Complete host-only lifecycle example; no PYNQ, MMIO, allocator or device."""
import json
import math
import time


class Slot:
    def __init__(self, size):
        self.data = bytearray([0xA5] * size)
        self.owner = "cpu"
        self.synced = False
        self.released = False


def copy_rows(slot, source, row_bytes, height, source_stride, stride):
    if slot.owner != "cpu" or slot.released:
        raise ValueError("CPU does not own this slot")
    if any(type(n) is not int or n <= 0 for n in (row_bytes, height, source_stride, stride)):
        raise ValueError("positive integer layout required")
    if min(source_stride, stride) < row_bytes:
        raise ValueError("stride smaller than active row")
    view = memoryview(source)
    if view.ndim != 1 or view.itemsize != 1 or not view.c_contiguous:
        raise ValueError("source must be a contiguous one-dimensional byte buffer")
    if view.obj is slot.data:
        raise ValueError("source/destination alias not supported")
    if len(view) < (height - 1) * source_stride + row_bytes or len(slot.data) < height * stride:
        raise ValueError("source or destination span too small")
    slot.synced = False
    for y in range(height):
        slot.data[y * stride:y * stride + row_bytes] = view[y * source_stride:y * source_stride + row_bytes]


class FakeEngine:
    """Only this fake API promises nonblocking status/stop; not PYNQ DMA API."""
    def __init__(self, can_halt=True, fail_start=False):
        self.can_halt = can_halt
        self.fail_start = fail_start
        self.running = False
        self.halted = True
        self.stop_requested = False
        self.events = []

    def flush(self, slot):
        if slot.owner != "cpu" or slot.released:
            raise ValueError("cannot synchronize a device-owned slot")
        self.events.append("flush")
        slot.synced = True

    def start(self, slot):
        self.events.append("start")
        self.running, self.halted = True, False
        if self.fail_start:
            raise RuntimeError("simulated failure after start request")
        self.device_snapshot = bytes(slot.data)

    def request_stop(self):
        self.events.append("request_stop")
        self.stop_requested = True
        if self.can_halt:
            self.running, self.halted = False, True

    def read_status(self):
        return dict(running=self.running, halted=self.halted, error=False)


def submit(slot, engine):
    if slot.owner != "cpu" or slot.released or not slot.synced:
        raise ValueError("CPU ownership and synchronization required")
    # A failed submission may already have touched hardware: do not roll back ownership.
    slot.owner = "device"
    engine.start(slot)


def release_after_stop(slot, engine, timeout, clock=time.monotonic, sleep=time.sleep):
    if type(timeout) not in (int, float):
        raise ValueError("finite positive timeout required")
    try:
        valid = math.isfinite(timeout) and timeout > 0
    except OverflowError:
        valid = False
    if slot.owner != "device" or not valid:
        raise ValueError("device-owned slot and positive timeout required")
    deadline = clock() + timeout
    engine.request_stop()
    while clock() < deadline:
        status = engine.read_status()
        if clock() >= deadline:
            return False
        if status["halted"] and not status["running"] and not status["error"]:
            slot.owner, slot.released = "released", True
            return True
        if status["error"]:
            return False
        remaining = deadline - clock()
        if remaining > 0:
            sleep(min(0.001, remaining))
    return False  # Still device-owned; caller keeps its reference and allocation.


def main():
    slot, engine = Slot(192), FakeEngine()
    source = bytearray(range(48))
    copy_rows(slot, source, row_bytes=12, height=3, source_stride=16, stride=64)
    engine.flush(slot)
    submit(slot, engine)
    assert release_after_stop(slot, engine, timeout=0.1)
    assert engine.events == ["flush", "start", "request_stop"]
    print(json.dumps(dict(scope="MOCK_LIFECYCLE_ONLY", rows=3, events=engine.events,
                          owner=slot.owner, released=slot.released)))


if __name__ == "__main__":
    main()
