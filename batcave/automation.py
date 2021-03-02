"""This module provides utilities for building automation."""

# Import standard modules
import sys
from abc import abstractmethod
from logging import Logger
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

# Import internal modules
from .lang import CommandResult
from .sysutil import popd, SysCmdRunner


class ActionCommandRunner(SysCmdRunner):  # pylint: disable=too-few-public-methods
    """Class to wrap SysCmdRunner for simple usage with auto-logging."""

    def __init__(self, command: str, /, *args, logger: Optional[Union[Callable, Logger]] = print, guard: str = '', syscmd_args: Optional[Dict[Any, Any]] = None, **kwargs: Any):
        """
        Args:
            command: The command passed to SysCmdRunner.
            logger (optional, default=print): A logging instance to use when the command is run.
            guard (optional, default=''): A line to be printed before the command is run.
                If an empty string, nothing is printed.
            syscmd_args (optional, default={}): Any arguments passed to syscmd.
            *args (optional, default=()): The list of default args passed to SysCmdRunner.
            **kwargs (optional, default={}): The list of default named args passed to SysCmdRunner.

        Attributes:
            logger: The value of the logger argument.
            guard: The value of the guard argument.
        """
        super().__init__(command, *args, syscmd_args=syscmd_args, **kwargs)
        self.logger = logger.info if isinstance(logger, Logger) else logger
        self.guard = guard

    def run(self, message: str, *args, post_option_args: Optional[Dict] = None,  # type: ignore[override]  # pylint: disable=arguments-differ
            syscmd_args: Optional[Dict[Any, Any]] = None, **kwargs) -> CommandResult:
        """Run the action.

        Args:
            message: The message to log if a logger has been set.
            post_option_args (optional, default=[]): The list of post_option_args passed to SysCmdRunner.
            syscmd_args (optional, default={}): The syscmd_args passed to SysCmdRunner.
            *args (optional, default=[]): The list of args passed to SysCmdRunner.
            **kwargs (optional, default={}): The list of named args passed to SysCmdRunner.

        Returns:
            Returns whatever is returned by SysCmdRunner.
        """
        if self.logger and message:
            if self.guard:
                self.logger(self.guard)
            self.logger(message)
        return super().run(*args, post_option_args=post_option_args, syscmd_args=syscmd_args, **kwargs)


class Action:
    """The common base class for all actions.

    This is a virtual class and the inheriting class must at least include a _execute() method.

    The action is invoked by calling the execute() method which will run the following methods::

        pre()
        _execute()
        post()

    These are run in a try to catch any exceptions with the always_post() method run in the finally block.

    Attributes:
        message_guard: This string is printed by logger if the value of guard passed to logger is true.
    """
    message_guard = f"{'*'*70}"

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

    def log_message(self, message: str, /, guard: bool = False, leader: str = 'INFO') -> None:
        """Log a message to stdout and flushes the stream.

        Args:
            message: The message to be printed.
            guard (optional, default=False): If True, message_guard will be printed on a line before the message.
            leader (optional, default='INFO'): If it does not evaluate to False, it will be prepended to every printed
                line, including the guard.

        Returns:
            Nothing.
        """
        the_leader: str = f'{leader} ' if leader else ''
        if the_guard := (self.message_guard if (guard is True) else ''):
            print(f'{the_leader}{the_guard}')
        print(f'{the_leader}{message}')
        sys.stdout.flush()
