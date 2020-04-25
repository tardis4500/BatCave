"""This module implements a simple state machine."""

# Import standard modules
from enum import Enum
from pathlib import Path
from string import Template

# Import internal modules
from .logger import Logger
from .sysutil import LockFile
from .lang import is_debug, BatCaveError, BatCaveException


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
        STATE_STATUSES: The status of the current state.
        _DEFAULT_STATEFILE: The default file to use to store the current state information.
        _DEFAULT_LOGFILE: The default file to use to store the log information.
        _DEFAULT_LOCKFILE: The default file to use for file locking.
    """
    _DEFAULT_LOCKFILE = Path('lock')
    _DEFAULT_LOGFILE = Path('log')
    _DEFAULT_STATEFILE = Path('state')

    STATE_STATUSES = Enum('state_status', ('entering', 'exited'))

    def __init__(self, states, statefile=_DEFAULT_STATEFILE, logfile=_DEFAULT_LOGFILE, lockfile=_DEFAULT_LOCKFILE, logger_args=None, autostart=True):
        """
        Args:
            states: The list of states for the state machine.
            statefile (optional, default=_DEFAULT_STATEFILE): The value of the file in which to store the state machine state.
            logfile (optional, default=_DEFAULT_LOGFILE): The log file to use for logging.
            lockfile (optional, default=_DEFAULT_LOCKFILE): The file to use to lock the state machine.
            logger_args (optional, default=None): The arguments to pass to the Logger instance.
            autostart (optional, default=True): If True, start the state machine when the instance is created.

        Attributes:
            locker: The value of the lockfile argument.
            logger: The logging instance created from the logfile and logger_args arguments.
            started: Indicates if the state machine is running.
            state: Indicates the current state of the state machine.
            statefile: The value of the statefile argument.
            states: The value of the states argument prepended by 'None.'
            status: Indicates the current status of the state machine.

        Raises:
            StateMachineError.BAD_STATUS: if the value of self.status is not in STATE_STATUSES
        """
        self.statefile = Path(statefile)
        self.locker = LockFile(lockfile)
        self.logger = Logger(logfile, **(logger_args if logger_args else dict()))
        self.states = ('None',) + states
        self.started = False
        if self.statefile.exists():
            debug_msg = 'Found'
            with open(self.statefile) as filestream:
                (status, state) = filestream.read().split()
                self.status = self.STATE_STATUSES[status]
                self.state = state
                if self.status not in self.STATE_STATUSES:
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

    def _writestate(self):
        """Write the current state to the state file.

        Returns:
            Nothing.
        """
        if is_debug('STATEMACHINE'):
            print(f'Writing state file with {self.status.name} {self.state}')
        with open(self.statefile, 'w') as filestream:
            print(self.status.name, self.state, file=filestream)

    def done(self):
        """Shutdown the state machine.

        Returns:
            Nothing.
        """
        self.logger.shutdown()
        self.locker.close()

    def enter_next_state(self):
        """Enter the next state.

        Returns:
            Nothing.

        Raises:
            StateMachineError.BAD_ENTRY: If the state machine has not exitted from the previous start.
            StateMachineError.DONE: If the state machine has already completed.
            StateMachineError.NOT_STARTED: If the state machine has not been started.
        """
        if not self.started:
            raise StateMachineError(StateMachineError.NOT_STARTED)
        if self.status != self.STATE_STATUSES.exited:
            raise StateMachineError(StateMachineError.BAD_ENTRY)
        next_state_index = self.states.index(self.state) + 1
        if next_state_index >= len(self.states):
            raise StateMachineError(StateMachineError.DONE)
        self.status = self.STATE_STATUSES.entering
        self.state = self.states[next_state_index]
        self._writestate()

    def exit_state(self):
        """Exit the current state.

        Returns:
            Nothing.

        Raises:
            StateMachineError.BAD_EXIT: If the state machine has not entered a state.
            StateMachineError.NOT_STARTED: If the state machine has not been started.
        """
        if not self.started:
            raise StateMachineError(StateMachineError.NOT_STARTED)
        if self.status != self.STATE_STATUSES.entering:
            raise StateMachineError(StateMachineError.BAD_EXIT)
        self.status = self.STATE_STATUSES.exited
        self._writestate()

    def reset(self):
        """Reset the state machine.

        Returns:
            Nothing.
        """
        if self.statefile.exists():
            self.statefile.unlink()
        (self.status, self.state) = (self.STATE_STATUSES.exited, self.states[0])
        self._writestate()

    def rollback(self):
        """Rollback to the previous state.

        Returns:
            Nothing.

        Raises:
            StateMachineError.BAD_ROLLBACK: If the state machine has not entered a state.
        """
        if self.status != self.STATE_STATUSES.entering:
            raise StateMachineError(StateMachineError.BAD_ROLLBACK)
        self.status = self.STATE_STATUSES.exited
        self.state = self.states[self.states.index(self.state) - 1]
        self._writestate()

    def start(self):
        """Start the state machine.

        Returns:
            Nothing.

        Raises:
            StateMachineError.CRASHED: If the state machine crashed on the previous run.
            StateMachineError.ALREADY_STARTED: If the state machine has already been started.
        """
        if self.started:
            raise StateMachineError(StateMachineError.ALREADY_STARTED)
        if self.status == self.STATE_STATUSES.entering:
            raise StateMachineError(StateMachineError.CRASHED, state=self.state)
        self.started = True
