"""Unit tests for the statemachine module."""

# pylint: disable=missing-class-docstring,missing-function-docstring,invalid-name,protected-access
# flake8: noqa

from unittest import main, TestCase

from batcave.statemachine import StateMachine, StateMachineError, StateStatus


class TestStateMachine(TestCase):
    STATES = ('state1', 'state2')

    def setUp(self):
        if StateMachine._DEFAULT_STATEFILE.exists():
            StateMachine._DEFAULT_STATEFILE.unlink()
        if StateMachine._DEFAULT_LOCKFILE.exists():
            StateMachine._DEFAULT_LOCKFILE.unlink()

    def tearDown(self):
        self.setUp()

    def test_statemachine_happypath(self):
        with StateMachine(self.STATES) as sm:
            self.assertEqual(sm.status, StateStatus.exited)
            self.assertEqual(sm.state, 'None')
            self.assertTrue(StateMachine._DEFAULT_STATEFILE.exists())
            self.assertTrue(StateMachine._DEFAULT_LOCKFILE.exists())
            for state in self.STATES:
                sm.enter_next_state()
                self.assertEqual(sm.status, StateStatus.entering)
                self.assertEqual(sm.state, state)
                sm.exit_state()
                self.assertEqual(sm.status, StateStatus.exited)
                self.assertEqual(sm.state, state)
            self.assertRaises(StateMachineError, sm.enter_next_state)
            try:
                sm.enter_next_state()
            except StateMachineError as err:
                self.assertEqual(StateMachineError.DONE.code, err.code)
        self.assertTrue(StateMachine._DEFAULT_STATEFILE.exists())
        self.assertFalse(StateMachine._DEFAULT_LOCKFILE.exists())

    def test_statemachine_savestate(self):
        for _unused_state in self.STATES:
            with StateMachine(self.STATES) as sm:
                sm.enter_next_state()
                sm.exit_state()

    def test_statemachine_badentry(self):
        with StateMachine(self.STATES) as sm:
            sm.enter_next_state()
            self.assertRaises(StateMachineError, sm.enter_next_state)
            try:
                sm.enter_next_state()
            except StateMachineError as err:
                self.assertEqual(StateMachineError.BAD_ENTRY.code, err.code)

    def test_statemachine_badexit(self):
        with StateMachine(self.STATES) as sm:
            sm.enter_next_state()
            sm.exit_state()
            self.assertRaises(StateMachineError, sm.exit_state)
            try:
                sm.exit_state()
            except StateMachineError as err:
                self.assertEqual(StateMachineError.BAD_EXIT.code, err.code)


if __name__ == '__main__':
    main()
