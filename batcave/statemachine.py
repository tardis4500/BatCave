'Module to implements a simple state machine.'

# Import standard modules
from enum import Enum
from pathlib import Path
from string import Template

# Import internal modules
from .hallog import Logger
from .sysutil import LockFile
from .lang import is_debug, HALError, HALException


class StateMachineError(HALException):
    'State machine exception class.'
    CRASHED = HALError(1, Template('State machine crashed in state: $state'))
    BAD_STATUS = HALError(2, Template('Unknown status: $status'))
    BAD_ENTRY = HALError(3, 'Attempt to enter next state before exiting current one')
    BAD_EXIT = HALError(4, 'Attempt to exit state before entering')
    BAD_ROLLBACK = HALError(5, 'Attempt to rollback state before entering')
    DONE = HALError(6, 'Attempt to enter state after final state')
    ALREADY_STARTED = HALError(7, 'State machine already started')
    NOT_STARTED = HALError(8, 'State machine not started')


class StateMachine:
    'Implements a state machine.'
    STATE_STATUSES = Enum('state_status', ('entering', 'exited'))
    _DEFAULT_STATEFILE = Path('state')
    _DEFAULT_LOGFILE = Path('log')
    _DEFAULT_LOCKFILE = Path('lock')

    def __init__(self, states, statefile=_DEFAULT_STATEFILE, logfile=_DEFAULT_LOGFILE, lockfile=_DEFAULT_LOCKFILE, logger_args=None, autostart=True):
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

    def start(self):
        'Start the state machine.'
        if self.started:
            raise StateMachineError(StateMachineError.ALREADY_STARTED)
        if self.status == self.STATE_STATUSES.entering:
            raise StateMachineError(StateMachineError.CRASHED, state=self.state)
        self.started = True

    def enter_next_state(self):
        'Enter the next state.'
        if not self.started:
            raise StateMachineError(StateMachineError.NOT_STARTED)
        if self.status != self.STATE_STATUSES.exited:
            raise StateMachineError(StateMachineError.BAD_ENTRY)
        next_state_index = self.states.index(self.state) + 1
        if next_state_index >= len(self.states):
            raise StateMachineError(StateMachineError.DONE)
        self.status = self.STATE_STATUSES.entering
        self.state = self.states[next_state_index]
        self.writestate()

    def rollback(self):
        'Rollback to the previous state.'
        if self.status != self.STATE_STATUSES.entering:
            raise StateMachineError(StateMachineError.BAD_ROLLBACK)
        self.status = self.STATE_STATUSES.exited
        self.state = self.states[self.states.index(self.state) - 1]
        self.writestate()

    def exit_state(self):
        'Exit the current state.'
        if not self.started:
            raise StateMachineError(StateMachineError.NOT_STARTED)
        if self.status != self.STATE_STATUSES.entering:
            raise StateMachineError(StateMachineError.BAD_EXIT)
        self.status = self.STATE_STATUSES.exited
        self.writestate()

    def reset(self):
        'Reset the state machine.'
        if self.statefile.exists():
            self.statefile.unlink()
        (self.status, self.state) = (self.STATE_STATUSES.exited, self.states[0])
        self.writestate()

    def writestate(self):
        'Write the current state to a file.'
        if is_debug('STATEMACHINE'):
            print(f'Writing state file with {self.status.name} {self.state}')
        with open(self.statefile, 'w') as filestream:
            print(self.status.name, self.state, file=filestream)

    def done(self):
        'Close down the state machine.'
        self.logger.shutdown()
        self.locker.close()
