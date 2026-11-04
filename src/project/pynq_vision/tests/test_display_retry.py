"""Host fault injection for retry bounds and stop-before-release ordering."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pynq_vision.beam_runtime import DisplayFault, run


class RetryTests(unittest.TestCase):
    def exercise(self, stage, stop_after=None, faults=100, error=None, drain_delays=0):
        events = []
        state = dict(now=0., sleeps=0, calls=0, stopped=False, drains=0)

        def sleep(seconds):
            state['now'] += .1
            state['sleeps'] += 1
            if state['sleeps'] > 20:
                raise AssertionError('retry escaped its original deadline')

        def operation(name):
            events.append(name)
            if name == stage:
                state['calls'] += 1
                if stop_after and state['calls'] >= stop_after:
                    state['stopped'] = True
                if state['calls'] <= faults:
                    raise DisplayFault('injected ' + name)

        class Owner:
            first_fault = None
            def prepare(inner): events.append('prepare')
            def capture_cpu(inner): events.append('capture'); return object()
            def check_capture(inner): pass
            def submit_cpu(inner, canvas, result): operation('submit')
            def display_retired(inner, ticket):
                operation('retire')
                state['stopped'] = True
                return True
            def stop(inner):
                state['drains'] += 1
                events.append('stop')
            def can_exit(inner):
                safe = state['drains'] > drain_delays
                if safe: events.append('halt_confirmed')
                return safe

        class Beam:
            def receive(inner, packet): return []
            def frame(inner, captured):
                events.append('compose')
                return SimpleNamespace(ticket=17), b'canvas', b'pose'
            def submitted(inner, ticket): events.append('submitted')
            def retired(inner, ticket): events.append('retired'); return b'ready'
            def close(inner):
                self.assertIn('halt_confirmed', events)
                events.append('beam_close')

        class Uart:
            def read(inner): return b''
            def write_packet(inner, packet): events.append('write_' + packet.decode())
            def close(inner):
                self.assertIn('halt_confirmed', events)
                events.append('uart_close')

        owner = Owner()
        with patch('pynq_vision.beam_runtime.time.monotonic', lambda: state['now']), \
                patch('pynq_vision.beam_runtime.time.sleep', sleep):
            if error:
                with self.assertRaisesRegex(RuntimeError, error):
                    run(owner, Beam(), Uart(), lambda: state['stopped'])
                self.assertIsNotNone(owner.first_fault)
            else:
                run(owner, Beam(), Uart(), lambda: state['stopped'])
                self.assertIsNone(owner.first_fault)
        self.assertEqual(events.count('capture'), 1)
        self.assertEqual(events.count('compose'), 1)
        self.assertEqual(events[-3:], ['halt_confirmed', 'uart_close', 'beam_close'])
        return events, state

    def test_persistent_submit_faults_reach_deadline(self):
        events, state = self.exercise('submit', error='submission exceeded 500ms')
        self.assertNotIn('submitted', events)
        self.assertNotIn('retired', events)
        self.assertLessEqual(state['calls'], 7)

    def test_persistent_retirement_faults_reach_deadline(self):
        events, state = self.exercise('retire', error='retirement exceeded original 500ms')
        self.assertEqual(events.count('submitted'), 1)
        self.assertNotIn('retired', events)
        self.assertLessEqual(state['calls'], 7)

    def test_stop_during_submission_never_fakes_submission(self):
        events, state = self.exercise('submit', stop_after=2)
        self.assertEqual(state['calls'], 2)
        self.assertNotIn('submitted', events)
        self.assertNotIn('retired', events)

    def test_stop_during_retirement_never_fakes_retirement(self):
        events, state = self.exercise('retire', stop_after=2)
        self.assertEqual(state['calls'], 2)
        self.assertIn('submitted', events)
        self.assertNotIn('retired', events)
        self.assertNotIn('write_ready', events)

    def test_transient_submit_failure_reuses_same_frame(self):
        events, _ = self.exercise('submit', faults=1)
        self.assertEqual(events.count('submit'), 2)
        self.assertEqual(events.count('submitted'), 1)
        self.assertEqual(events.count('retired'), 1)

    def test_transient_retirement_failure_reuses_same_ticket(self):
        events, _ = self.exercise('retire', faults=1)
        self.assertEqual(events.count('submit'), 1)
        self.assertEqual(events.count('retire'), 2)
        self.assertEqual(events.count('retired'), 1)

    def test_stop_keeps_resources_until_actual_halt_confirmation(self):
        events, state = self.exercise('submit', stop_after=1, drain_delays=2)
        self.assertEqual(state['drains'], 3)
        self.assertEqual(events.count('stop'), 3)
        self.assertLess(events.index('halt_confirmed'), events.index('uart_close'))


if __name__ == '__main__':
    unittest.main()
