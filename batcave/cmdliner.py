"""This module provides a utility for building command line runners."""

# Import standard modules
from typing import Any, Dict, List, Optional, Union

# Import internal modules
from .sysutil import SysCmdRunner


class CommandLineRunner(SysCmdRunner):
    """Class to wrap SysCmdRunner for simple usage with auto-logging."""

    def __init__(self, command: str, /, *args, syscmd_args: Optional[Dict] = None, **kwargs: Any):
        """
        Args:
            command: The command passed to SysCmdRunner.
            syscmd_args (optional, default={'show_cmd': True, 'show_stdout': True}): The list of default args passed to syscmd.
            *args (optional, default=[]): The list of default args for the command.
            **kwargs (optional, default={}): The list of default options for the command.

        Attributes:
            _default_args: The default arguments for any command.
        """
        if syscmd_args is None:
            default_syscmd_args = {'show_cmd': True, 'show_stdout': True}
        elif syscmd_args is False:
            default_syscmd_args = dict()
        else:
            default_syscmd_args = syscmd_args
        super().__init__(command, *args, logger=None, **default_syscmd_args)
        self._default_args = kwargs

    def run(self, *args: Any, post_option_args: Optional[Dict] = None, syscmd_args: Optional[Dict] = None, **kwargs: Any) -> Union[str, List[str]]:
        """Run the action.

        Args:
            post_option_args (optional, default=[]): The list of args to pass after the options.
            syscmd_args (optional, default={}): The list of default args passed to syscmd.
            *args (optional, default=[]): The list of args passed to the command.
            **kwargs (optional, default={}): The list of named args passed to the command.

        Returns:
            Returns whatever is returned by SysCmdRunner.
        """
        command_args = list(args)
        option_args = self._default_args
        option_args.update(kwargs)
        for (arg, value) in option_args.items():
            arg_name = arg.replace('_', '-')
            if value is True:
                command_args.append(f'--{arg_name}')
            else:
                command_args.append(f'--{arg_name}={value}')
        if post_option_args:
            command_args += post_option_args
        return super().run('', *command_args, **(syscmd_args if syscmd_args else dict()))
