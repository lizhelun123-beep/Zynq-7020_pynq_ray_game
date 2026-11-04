"""Host control-state tests;fake MMIO/IRQ,not hardware evidence."""
import asyncio
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "assets/scalar-demo/python"))
from pynq_scalar_demo.core import AddBiasSession, BusyError, OFFSETS


class Clock:
    now = 0.0

    def read(self):
        return self.now

    def sleep(self, delay):
        self.now += delay


class IRQ:
    def __init__(self):
        self.event = asyncio.Event()
        self.armed = False

    async def wait(self):
        self.armed = True
        await self.event.wait()
        self.event.clear()


class IO:
    def __init__(self, irq=None, complete=True, fail_start=False):
        self.regs = {offset: 0 for offset in OFFSETS.values()}
        self.regs[0] = 4
        self.events, self.irq = [], irq
        self.complete, self.fail_start = complete, fail_start

    def read(self, address):
        self.events.append(("read", address))
        value = self.regs[address]
        if address == 0:
            self.regs[0] &= ~2  # AP_DONE clear-on-read.
        return value

    def write(self, address, value):
        self.events.append(("write", address, value))
        if address == 12:
            self.regs[address] ^= value  # HLS ISR toggle-on-write.
        else:
            self.regs[address] = value
        if address == 0 and value == 1:
            if self.irq is not None and not self.irq.armed:
                raise AssertionError("start before interrupt registration")
            if self.fail_start:
                raise OSError("partial hardware start")
            if self.complete:
                self.regs[32] = (self.regs[16] + self.regs[24]) & 0xffffffff
                self.regs[0], self.regs[12] = 6, 1
                if self.irq is not None:
                    self.irq.event.set()


class CoreTests(unittest.TestCase):
    def test_arguments_fail_without_io(self):
        for args in ((True, 0, 1), (-1, 0, 1), (1 << 32, 0, 1), (0, 0, float("nan")),
                     (0, 0, float("inf")), (0, 0, 0), (0, 0, True), (0, 0, 10 ** 1000)):
            io = IO()
            with self.subTest(args=str(args)[:60]), self.assertRaises(ValueError):
                AddBiasSession(io).add(*args)
            self.assertEqual(io.events, [])

    def test_poll_vectors_and_pending_tow(self):
        io = IO()
        io.regs[12] = 1
        session = AddBiasSession(io)
        for x, b in ((0, 0), (3, 4), (0xffffffff, 1), (0x80000000, 0x80000000)):
            self.assertEqual(session.add(x, b), (x + b) & 0xffffffff)
            self.assertEqual(io.regs[12], 0)
        session.close()
        session.close()
        with self.assertRaises(BusyError):
            session.add(1, 2)

    def test_timeout_retains_unknown_until_idle_confirmed(self):
        io, clock = IO(complete=False), Clock()
        session = AddBiasSession(io, clock=clock.read, sleep=clock.sleep)
        with self.assertRaises(TimeoutError):
            session.add(1, 2, .003)
        self.assertEqual(session.state, "unknown")
        self.assertFalse(session.recover_if_idle())
        with self.assertRaises(BusyError):
            session.close()
        io.regs[0] = 4
        self.assertTrue(session.recover_if_idle())
        session.close()

    def test_partial_start_does_not_rollback(self):
        session = AddBiasSession(IO(fail_start=True))
        with self.assertRaises(OSError):
            session.add(1, 2)
        self.assertEqual(session.state, "unknown")
        with self.assertRaises(BusyError):
            session.add(1, 2)

    def test_done_read_after_deadline_rejected(self):
        io, clock = IO(), Clock()
        original = io.read
        def read(address):
            value = original(address)
            if address == 0 and value & 2:
                clock.now = 2
            return value
        io.read = read
        with self.assertRaises(TimeoutError):
            AddBiasSession(io, clock=clock.read).add(1, 2, 1)

    def run_async(self, coroutine):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coroutine)
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()

    def test_irq_armed_before_one_cycle_completion(self):
        async def scenario():
            irq = IRQ()
            io = IO(irq)
            session = AddBiasSession(io, irq)
            self.assertEqual(await session.add_async(0xffffffff, 1), 0)
            self.assertEqual(session.irq_events, 1)
            self.assertEqual(io.regs[12], 0)
            session.close()
        self.run_async(scenario())

    def test_async_cancel_rejects_reentry_and_irq_reuse(self):
        async def scenario():
            irq = IRQ()
            io = IO(irq, complete=False)
            session = AddBiasSession(io, irq)
            task = asyncio.ensure_future(session.add_async(1, 2))
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            with self.assertRaises(BusyError):
                session.add(1, 2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertEqual(session.state, "unknown")
            io.regs[0] = 4
            self.assertTrue(session.recover_if_idle())
            with self.assertRaises(RuntimeError):
                await session.add_async(1, 2)
            io.irq, io.complete = None, True
            self.assertEqual(session.add(2, 3), 5)
        self.run_async(scenario())

    def test_irq_timeout_never_succeeds_by_polling(self):
        async def scenario():
            irq = IRQ()
            io = IO(complete=True)  # finishes,but has no interrupt route
            session = AddBiasSession(io, irq)
            with self.assertRaises(asyncio.TimeoutError):
                await session.add_async(1, 2, .01)
            self.assertEqual(session.irq_events, 0)
            self.assertFalse(session.irq_usable)
            self.assertEqual(session.state, "unknown")
        self.run_async(scenario())

    def test_spurious_irq_rearms_until_done(self):
        async def scenario():
            class ScriptedIRQ:
                armed, calls = False, 0
                async def wait(inner):
                    inner.armed = True
                    inner.calls += 1
                    if inner.calls == 2:
                        io.regs[0], io.regs[12], io.regs[32] = 6, 1, 7
            irq = ScriptedIRQ()
            io = IO(irq, complete=False)
            session = AddBiasSession(io, irq)
            self.assertEqual(await session.add_async(3, 4), 7)
            self.assertEqual(session.irq_events, 2)
            self.assertEqual(io.regs[12], 0)
        self.run_async(scenario())


if __name__ == "__main__":
    unittest.main()
