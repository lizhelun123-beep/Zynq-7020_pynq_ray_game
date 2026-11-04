"""One-owner control for this template's ap_ctrl_hs AXI-Lite IP."""
import asyncio
import math
import threading
import time

OFFSETS = {"ctrl": 0x00, "gie": 0x04, "ier": 0x08, "isr": 0x0c,
           "x": 0x10, "bias": 0x18, "y": 0x20}


class BusyError(RuntimeError):
    pass


def uint32(value):
    if type(value) is not int or not 0 <= value <= 0xffffffff:
        raise ValueError("expected unsigned32 Python int")
    return value


def budget(value):
    if type(value) not in (int, float):
        raise ValueError("timeout must be positive finite seconds")
    try:
        valid = math.isfinite(value) and value > 0
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("timeout must be positive finite seconds")
    return float(value)


class AddBiasSession:
    def __init__(self, io, interrupt=None, clock=time.monotonic, sleep=time.sleep):
        self.io = io
        self.interrupt = interrupt
        self.clock = clock
        self.sleep = sleep
        self.state = "idle"
        self.irq_usable = interrupt is not None
        self.irq_events = 0
        self._guard = threading.Lock()

    def _ack_irq(self):
        # This generated HLS ISR is toggle-on-write,not arbitrary W1C.
        pending = self.io.read(OFFSETS["isr"]) & 3
        if pending:
            self.io.write(OFFSETS["isr"], pending)

    def _prepare(self, x, bias, timeout, irq):
        x, bias, timeout = uint32(x), uint32(bias), budget(timeout)
        with self._guard:
            if self.state != "idle":
                raise BusyError("session is " + self.state)
            if irq and not self.irq_usable:
                raise RuntimeError("fresh valid interrupt object required")
            self.state = "busy"
        try:
            if not self.io.read(OFFSETS["ctrl"]) & 4:
                raise BusyError("hardware is not idle")
            self.io.write(OFFSETS["gie"], 0)
            self.io.write(OFFSETS["ier"], 0)
            self._ack_irq()
            self.io.write(OFFSETS["x"], x)
            self.io.write(OFFSETS["bias"], bias)
            if irq:
                self.io.write(OFFSETS["ier"], 1)
                self.io.write(OFFSETS["gie"], 1)
            return self.clock() + timeout
        except BaseException:
            self.state = "unknown"
            raise

    def _finish(self):
        value = self.io.read(OFFSETS["y"]) & 0xffffffff
        self._ack_irq()
        self.io.write(OFFSETS["gie"], 0)
        self.io.write(OFFSETS["ier"], 0)
        self.state = "idle"
        return value

    def add(self, x, bias, timeout=1.0):
        deadline = self._prepare(x, bias, timeout, False)
        try:
            self.io.write(OFFSETS["ctrl"], 1)
            while self.clock() < deadline:
                control = self.io.read(OFFSETS["ctrl"])
                if self.clock() >= deadline:
                    break
                if control & 2:
                    return self._finish()
                remaining = deadline - self.clock()
                if remaining > 0:
                    self.sleep(min(.001, remaining))
            raise TimeoutError("completion not confirmed before deadline")
        except BaseException:
            self.state = "unknown"
            raise

    async def add_async(self, x, bias, timeout=1.0):
        deadline = self._prepare(x, bias, timeout, True)
        waiter = None
        try:
            # Register the waiter before starting even a one-cycle IP.
            waiter = asyncio.ensure_future(self.interrupt.wait())
            await asyncio.sleep(0)
            self.io.write(OFFSETS["ctrl"], 1)
            while True:
                remaining = deadline - self.clock()
                if remaining <= 0:
                    raise TimeoutError("interrupt deadline expired")
                await asyncio.wait_for(waiter, remaining)
                self.irq_events += 1
                self._ack_irq()
                control = self.io.read(OFFSETS["ctrl"])
                if self.clock() >= deadline:
                    raise TimeoutError("late completion")
                if control & 2:
                    return self._finish()
                waiter = asyncio.ensure_future(self.interrupt.wait())
        except BaseException:
            if waiter is not None and not waiter.done():
                waiter.cancel()
            # PYNQ2.6 cancellation can leave controller registration pending.
            self.irq_usable = False
            self.state = "unknown"
            raise

    def recover_if_idle(self):
        """Only for this scalar/no-memory-master IP;not a DMA drain proof."""
        with self._guard:
            if self.state in ("busy", "closed"):
                raise BusyError("cannot recover " + self.state)
            if not self.io.read(OFFSETS["ctrl"]) & 4:
                return False
            self.io.write(OFFSETS["gie"], 0)
            self.io.write(OFFSETS["ier"], 0)
            self._ack_irq()
            self.state = "idle"
            return True

    def close(self):
        with self._guard:
            if self.state == "closed":
                return
            if self.state != "idle" or not self.io.read(OFFSETS["ctrl"]) & 4:
                raise BusyError("idle confirmation required before close")
            self.io.write(OFFSETS["gie"], 0)
            self.io.write(OFFSETS["ier"], 0)
            self._ack_irq()
            self.state = "closed"
