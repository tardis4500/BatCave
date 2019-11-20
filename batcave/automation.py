"""This module provides utilities for building automation."""

# Import standard modules
import sys
from pathlib import Path

# Import internal modules
from .sysutil import popd, SysCmdRunner


class ActionCommandRunner(SysCmdRunner):
    """Class to wrap SysCmdRunner for simple usage with auto-logging."""

    def __init__(self, command: str, guard: str = '', default_args: tuple = tuple(), **kwargs):
        """
        Args:
            command: The command passed to SysCmdRunner.
            guard (optional, default=''): A line to be printed before the command is run.
                If an empty string, nothing is printed.
            default_args (optional, default=()): The list of default args passed to SysCmdRunner.
            **kwargs (optional, default={}): The list of default named args passed to SysCmdRunner.
        """
        super().__init__(command, *default_args, show_cmd=True, show_stdout=True, **kwargs)
        self.guard = guard

    def run(self, message: str, *args, **kwargs):
        """Runs the action.

        Args:
            message: The message passed to SysCmdRunner.
            *args: The list of args passed to SysCmdRunner.
            **kwargs: The list of named args passed to SysCmdRunner.

        Returns:
            Returns whatever is returned by SysCmdRunner
        """
        if self.guard:
            self.writer(self.guard)
        return super().run(message, *args, **kwargs)


class Action:
    """The common base class for all actions.

    This is a virtual class and the inheriting class must at least include a _execute() method
    The action is invoked by calling the execute() method which will run the following methods:
        pre()
        _execute()
        post()
    These are run in a try to catch any exceptions after which
        always_post()
    is run.

    Attributes:
        MESSAGE_GUARD: This string is printed by logger if the value of guard passed to logger is true.
    """
    MESSAGE_GUARD: str = f"{'*'*70}"

    def __init__(self, **_unused_kwargs):
        """
        Args:
            **_unused_kwargs: All arguments passed are ignored by the time they reach this initializer
        """
        self.project_root = Path.cwd().parent

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def pre(self):
        """Executed before _execute()."""

    def post(self):
        """Executed after _execute()."""

    def always_post(self):
        """Executed after _execute() like finally in try/catch/finally."""
        popd()

    def execute(self):
        """Runs the _execute() method from the child class."""
        try:
            self.pre()
            self._execute()  # pylint: disable=E1101
            self.post()
        finally:
            self.always_post()

    def log_message(self, message: str, guard: bool = False, leader: str = 'INFO'):
        """Logs a message to stdout and flushes the stream.

        Args:
            message: The message to be printed.
            guard (optional, default=False): If True, MESSAGE_GUARD will be printed on a line before the message.
            leader (optional, default='INFO'): If it does not evaluate to False, it will be prepended to every printed
                line, including the guard.

        Returns:
            Nothing
        """
        guard = self.MESSAGE_GUARD if (guard is True) else ''
        leader = f'{leader} ' if leader else ''
        if guard:
            print(f'{leader}{guard}')
        print(f'{leader}{message}')
        sys.stdout.flush()
