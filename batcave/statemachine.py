"""This module implements a simple state machine."""

# Import standard modules
from enum import Enum
from pathlib import Path
from string import Template
from typing import Sequence

# Import internal modules
from .sysutil import LockFile
from .lang import is_debug, BatCaveError, BatCaveException, PathName

StateStatus = Enum('StateStatus', ('entering', 'exited'))


class StateMachineError(BatCaveException):
    """State Machine Exceptions.

    Attributes:
        ALREADY_STARTED: There was an attempt to start a state machine that is already in progress.
        BAD_ENTRY: There was an attempt to enter next state before exiting current one.
        BAD_EXIT: There was an attempt to exit the state before it was entered.
        BAD_ROLLBACK: There was an attempt to rollback a state before it entered.
        BAD_STATUS: An invalid status was requested.
        CRASHED: The state machine crashed in a state.
        DONE: There was an attempt to enter a state after the final state.
        NOT_STARTED: There was an attempt to continue a state machine that has not started.
    """
    ALREADY_STARTED = BatCaveError(1, 'State machine already started')
    BAD_ENTRY = BatCaveError(2, 'Attempt to enter next state before exiting current one')
    BAD_EXIT = BatCaveError(3, 'Attempt to exit state before entering')
    BAD_ROLLBACK = BatCaveError(4, 'Attempt to rollback state before entering')
    BAD_STATUS = BatCaveError(5, Template('Unknown status: $status'))
    CRASHED = BatCaveError(6, Template('State machine crashed in state: $state'))
    DONE = BatCaveError(7, 'Attempt to enter state after final state')
    NOT_STARTED = BatCaveError(8, 'State machine not started')


class StateMachine:
    """This class implements a classic state machine.

    Attributes:
        _DEFAULT_STATEFILE: The default file to use to store the current state information.
        _DEFAULT_LOGFILE: The default file to use to store the log information.
        _DEFAULT_LOCKFILE: The default file to use for file locking.
    """
    _DEFAULT_LOCKFILE = Path('lock')
    _DEFAULT_STATEFILE = Path('state')

    def __init__(self, states: Sequence, /, *, statefile: PathName = _DEFAULT_STATEFILE, lockfile: PathName = _DEFAULT_LOCKFILE, autostart: bool = True):
        """
        Args:
            states: The list of states for the state machine.
            statefile (optional, default=_DEFAULT_STATEFILE): The value of the file in which to store the state machine state.
            lockfile (optional, default=_DEFAULT_LOCKFILE): The file to use to lock the state machine.
            autostart (optional, default=True): If True, start the state machine when the instance is created.

        Attributes:
            state: Indicates the current state of the state machine.
            status: Indicates the current status of the state machine.
            _locker: The value of the lockfile argument.
            _started: Indicates if the state machine is running.
            _statefile: The value of the statefile argument.
            _states: The value of the states argument prepended by 'None.'

        Raises:
            StateMachineError.BAD_STATUS: if the value of self.status is not in StateStatus
        """
        self._statefile = Path(statefile)
        self._locker = LockFile(lockfile)
        self._states = ['None'] + list(states)
        self._started = False
        if self._statefile.exists():
            debug_msg = 'Found'
            with open(self._statefile) as filestream:
                (status, state) = filestream.read().split()
                self.status = StateStatus[status]
                self.state = state
                if self.status not in StateStatus:
                    raise StateMachineError(StateMachineError.BAD_STATUS, status=self.status)
        else:
            debug_msg = 'Initializing'
            self.reset()

        if autostart:
            self.start()

        if is_debug('STATEMACHINE'):
            print(f'{debug_msg} state file with {self.status.name} {self.state}')

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.done()
        return False

    def _writestate(self) -> None:
        """Write the current state to the state file.

        Returns:
            Nothing.
        """
        if is_debug('STATEMACHINE'):
            print(f'Writing state file with {self.status.name} {self.state}')
        with open(self._statefile, 'w') as filestream:
            print(self.status.name, self.state, file=filestream)

    def done(self) -> None:
        """Shutdown the state machine.

        Returns:
            Nothing.
        """
        self._locker.close()

    def enter_next_state(self) -> None:
        """Enter the next state.

        Returns:
            Nothing.

        Raises:
            StateMachineError.BAD_ENTRY: If the state machine has not exitted from the previous start.
            StateMachineError.DONE: If the state machine has already completed.
            StateMachineError.NOT_STARTED: If the state machine has not been started.
        """
        if not self._started:
            raise StateMachineError(StateMachineError.NOT_STARTED)
        if self.status != StateStatus.exited:
            raise StateMachineError(StateMachineError.BAD_ENTRY)
        if (next_state_index := self._states.index(self.state) + 1) >= len(self._states):
            raise StateMachineError(StateMachineError.DONE)
        self.status = StateStatus.entering
        self.state = self._states[next_state_index]
        self._writestate()

    def exit_state(self) -> None:
        """Exit the current state.

        Returns:
            Nothing.

        Raises:
            StateMachineError.BAD_EXIT: If the state machine has not entered a state.
            StateMachineError.NOT_STARTED: If the state machine has not been started.
        """
        if not self._started:
            raise StateMachineError(StateMachineError.NOT_STARTED)
        if self.status != StateStatus.entering:
            raise StateMachineError(StateMachineError.BAD_EXIT)
        self.status = StateStatus.exited
        self._writestate()

    def reset(self) -> None:
        """Reset the state machine.

        Returns:
            Nothing.
        """
        if self._statefile.exists():
            self._statefile.unlink()
        (self.status, self.state) = (StateStatus.exited, self._states[0])
        self._writestate()

    def rollback(self) -> None:
        """Rollback to the previous state.

        Returns:
            Nothing.

        Raises:
            StateMachineError.BAD_ROLLBACK: If the state machine has not entered a state.
        """
        if self.status != StateStatus.entering:
            raise StateMachineError(StateMachineError.BAD_ROLLBACK)
        self.status = StateStatus.exited
        self.state = self._states[self._states.index(self.state) - 1]
        self._writestate()

    def start(self) -> None:
        """Start the state machine.

        Returns:
            Nothing.

        Raises:
            StateMachineError.CRASHED: If the state machine crashed on the previous run.
            StateMachineError.ALREADY_STARTED: If the state machine has already been started.
        """
        if self._started:
            raise StateMachineError(StateMachineError.ALREADY_STARTED)
        if self.status == StateStatus.entering:
            raise StateMachineError(StateMachineError.CRASHED, state=self.state)
        self._started = True
