"""This module provides utilities for building automation."""

# Import standard modules
import sys
from abc import abstractmethod
from pathlib import Path
from typing import Any, List, Union

# Import internal modules
from .sysutil import popd, SysCmdRunner


class ActionCommandRunner(SysCmdRunner):  # pylint: disable=too-few-public-methods
    """Class to wrap SysCmdRunner for simple usage with auto-logging."""

    def __init__(self, command: str, guard: str = '', default_args: tuple = tuple(), **kwargs: Any):
        """
        Args:
            command: The command passed to SysCmdRunner.
            guard (optional, default=''): A line to be printed before the command is run.
                If an empty string, nothing is printed.
            default_args (optional, default=()): The list of default args passed to SysCmdRunner.
            **kwargs (optional, default={}): The list of default named args passed to SysCmdRunner.

        Attributes:
            guard: The value of the guard argument.
        """
        super().__init__(command, *default_args, show_cmd=True, show_stdout=True, **kwargs)
        self.guard = guard

    def run(self, message: str, *args: Any, **kwargs: Any) -> Union[str, List[str]]:
        """Run the action.

        Args:
            message: The message passed to SysCmdRunner.
            *args (optional, default=[]): The list of args passed to SysCmdRunner.
            **kwargs (optional, default={}): The list of named args passed to SysCmdRunner.

        Returns:
            Returns whatever is returned by SysCmdRunner.
        """
        if self.guard:
            self.writer(self.guard)  # type: ignore
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
    MESSAGE_GUARD = f"{'*'*70}"

    def __init__(self, **_unused_kwargs: Any):
        """
        Args:
            **_unused_kwargs: All arguments passed are ignored by the time they reach this initializer.

        Attributes:
            _project_root: The parent directory from where the current action is run.
        """
        self._project_root = Path.cwd().parent

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    @abstractmethod
    def _execute(self) -> None:
        pass

    project_root = property(lambda s: s._project_root, doc='A read-only property which returns the root of the automation.')

    def pre(self) -> None:
        """Executed before _execute().

        Returns:
            Nothing.
        """

    def post(self) -> None:
        """Executed after _execute().

        Returns:
            Nothing.
        """

    def always_post(self) -> None:  # pylint: disable=no-self-use
        """Always executed after _execute() as in finally in try/catch/finally.

        Returns:
            Nothing.
        """
        popd()

    def execute(self) -> None:
        """Run the _execute() method from the child class.

        Returns:
            Nothing.
        """
        try:
            self.pre()
            self._execute()
            self.post()
        finally:
            self.always_post()

    def log_message(self, message: str, guard: bool = False, leader: str = 'INFO') -> None:
        """Log a message to stdout and flushes the stream.

        Args:
            message: The message to be printed.
            guard (optional, default=False): If True, MESSAGE_GUARD will be printed on a line before the message.
            leader (optional, default='INFO'): If it does not evaluate to False, it will be prepended to every printed
                line, including the guard.

        Returns:
            Nothing.
        """
        the_guard: str = self.MESSAGE_GUARD if (guard is True) else ''
        the_leader: str = f'{leader} ' if leader else ''
        if the_guard:
            print(f'{the_leader}{the_guard}')
        print(f'{the_leader}{message}')
        sys.stdout.flush()
