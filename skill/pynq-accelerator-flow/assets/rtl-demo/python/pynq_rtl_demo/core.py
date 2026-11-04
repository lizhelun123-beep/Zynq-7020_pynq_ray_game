"""Own add32 ABI,not HLS ap_ctrl_hs;no PYNQ/device import."""
import asyncio
import math
import threading
import time

CTRL, STATUS, IRQ_ENABLE, VERSION, A, B, RESULT, COUNT = range(0, 32, 4)


def arguments(a, b, timeout):
    for value in (a, b):
        if type(value) is not int or not 0 <= value <= 0xffffffff:
            raise ValueError('expected uint32 Python int')
    if type(timeout) not in (int, float):
        raise ValueError('expected finite positive timeout')
    try:
        valid = math.isfinite(timeout) and timeout > 0
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError('expected finite positive timeout')
    return float(timeout)


class Session:
    def __init__(self, io, interrupt=None):
        self.io, self.interrupt = io, interrupt
        self.state, self.irq_usable = 'idle', interrupt is not None
        self.irq_events = 0
        self._guard = threading.Lock()

    def _ack(self):
        pending = self.io.read(STATUS) & 1
        if pending:
            self.io.write(STATUS, pending)

    def _prepare(self, a, b, timeout, irq):
        timeout = arguments(a, b, timeout)
        with self._guard:
            if self.state != 'idle':
                raise RuntimeError('session is ' + self.state)
            if irq and not self.irq_usable:
                raise RuntimeError('fresh interrupt object required')
            self.state = 'busy'
        try:
            if self.io.read(CTRL) & 2:
                raise RuntimeError('hardware busy')
            self.io.write(IRQ_ENABLE, 0)
            self._ack()
            self.io.write(A, a)
            self.io.write(B, b)
            if irq:
                self.io.write(IRQ_ENABLE, 1)
            return time.monotonic() + timeout
        except BaseException:
            self.state = 'unknown'
            raise

    def _finish(self):
        value = self.io.read(RESULT) & 0xffffffff
        self._ack()
        self.io.write(IRQ_ENABLE, 0)
        self.state = 'idle'
        return value

    def add(self, a, b, timeout=.1):
        deadline = self._prepare(a, b, timeout, False)
        try:
            self.io.write(CTRL, 1)
            while time.monotonic() < deadline:
                status = self.io.read(STATUS)
                if time.monotonic() >= deadline:
                    break
                if status & 1:
                    return self._finish()
                time.sleep(min(.0001, max(0, deadline - time.monotonic())))
            raise TimeoutError('completion not confirmed')
        except BaseException:
            self.state = 'unknown'
            raise

    async def add_async(self, a, b, timeout=.1):
        deadline = self._prepare(a, b, timeout, True)
        waiter = None
        try:
            waiter = asyncio.ensure_future(self.interrupt.wait())
            await asyncio.sleep(0)
            self.io.write(CTRL, 1)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('late IRQ')
                await asyncio.wait_for(waiter, remaining)
                self.irq_events += 1
                # DONE mirrors STATUS in THIS ABI:read before W1C acknowledgment.
                status = self.io.read(STATUS)
                if time.monotonic() >= deadline:
                    raise TimeoutError('late completion')
                if status & 1:
                    return self._finish()
                waiter = asyncio.ensure_future(self.interrupt.wait())
        except BaseException:
            if waiter is not None and not waiter.done():
                waiter.cancel()
            self.irq_usable = False
            self.state = 'unknown'
            raise

    def recover_if_idle(self):
        """Only this scalar no-memory-master IP;not a DMA drain proof."""
        with self._guard:
            if self.state in ('busy', 'closed'):
                raise RuntimeError('cannot recover ' + self.state)
            if self.io.read(CTRL) & 2:
                return False
            self.io.write(IRQ_ENABLE, 0)
            self._ack()
            self.state = 'idle'
            return True

    def close(self):
        with self._guard:
            if self.state == 'closed':
                return
            if self.state != 'idle' or self.io.read(CTRL) & 2:
                raise RuntimeError('idle confirmation required')
            self.io.write(IRQ_ENABLE, 0)
            self._ack()
            self.state = 'closed'
