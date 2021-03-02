"""This module provides a simplified interface to the standard argparse module."""

# Import standard modules
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter, HelpFormatter, Namespace, REMAINDER, _MutuallyExclusiveGroup
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Optional, Sequence, Type, Union

# Import internal modules
from .version import get_version_info, VersionStyle
from .lang import str_to_pythonval


class Argument:  # pylint: disable=too-few-public-methods
    """This is a simple container class to encapsulate an argument definition passed to ArgumentParser.add_argument()."""

    def __init__(self, *names, **options):
        """
        Args:
            *names: A list of the argument names.
            **options (optional): A dictionary of the argument options.

        Attributes:
            names: The value of the names argument.
            options: The value of the options argument.
        """
        self.names: Sequence[str] = names
        self.options: Dict = options


@dataclass(frozen=True)
class SubParser:
    """This is a simple container class to encapsulate a subparser definition.

        Attributes:
            subcommand: The subcommand name for the subparser.
            command_runner: The function which runs the commands for the subparser.
            arguments (optional, default=None): A list of arguments for the subparser.
    """
    subcommand: str
    command_runner: Callable
    arguments: Sequence[Argument] = field(default_factory=tuple)


class Commander:
    """This class provides a simplified interface to the argparse.ArgumentParser class."""

    def __init__(self, description: str, arguments: Sequence[Argument] = tuple(), subparsers: Iterable[SubParser] = tuple(),  # pylint: disable=too-many-locals,too-many-arguments
                 subparser_common_args: Sequence[Argument] = tuple(), default: Optional[Callable] = None, parents: Sequence[ArgumentParser] = tuple(),
                 parse_extra: bool = False, extra_var_sep: str = ':', convert_extra: bool = True, add_version: bool = True,
                 version_style: VersionStyle = VersionStyle.oneline, formatter_class: Type[HelpFormatter] = ArgumentDefaultsHelpFormatter):
        """
        Args:
            description: The subcommand name for the subparser.
            arguments (optional, default=None): A list of arguments for the command driver.
            subparsers (optional, default=None): A list of subparsers for the command driver.
            subparser_common_args (optional, default=None): A list of common arguments for all subparsers.
            default (optional, default=None): The default subparser.
            parents (optional, default=None): A list of parents to pass to the parser.
            parse_extra (optional, default=False): If True then all un-parsed arguments will be interpreted
                using the value of extra_var_sep as extra arguments of the form: argument:value.
            extra_var_sep (optional, default=:): The character used to separate the extra vars from the values.
            convert_extra (optional, default=True): If True then used str_to_pythonval on the values in the parse_extra arguments.
            add_version (optional, default=True): If True then add a version argument to the parser and use version.get_version_info.
            version_style (optional, default=oneline): The version.VERSION_STYLE to use for the version argument output.
            formatter_class (optional, default=ArgumentDefaultsHelpFormatter): The formatter class to pass to the parser.

        Attributes:
            parser: The command parser instance.
            subparser_common_parser: The parser for subparser common arguments.
            _convert_extra: The value of the convert_extra argument.
            _default: The value of the default argument.
            _extra_var_sep: The value of the extra_var_sep argument.
            _parse_extra: The value of the parse_extra argument.
            _pass_on: The list of arguments to pass to the subparsers when parsing.
            _subparsers: The value of the subparsers argument.
        """
        self._convert_extra = convert_extra
        self._default = default
        self._extra_var_sep = extra_var_sep
        self._parse_extra = parse_extra
        self._pass_on: Sequence[str] = tuple()
        self._subparsers = subparsers
        self.subparser_common_parser: Optional[ArgumentParser] = None

        self.parser = ArgumentParser(description=description, formatter_class=formatter_class, parents=parents)  # type: ignore[arg-type]
        _add_arguments_to_parser(self.parser, arguments)
        if add_version:
            self.parser.add_argument('-v', '--version', action='version', version=get_version_info(version_style))

        if subparsers:
            subparser_objects = self.parser.add_subparsers(dest='command')
            for subparser_def in subparsers:
                subparser: ArgumentParser = subparser_objects.add_parser(subparser_def.subcommand)
                _add_arguments_to_parser(subparser, subparser_def.arguments)
                subparser.set_defaults(command=subparser_def.command_runner)

        if subparser_common_args:
            self.subparser_common_parser = ArgumentParser(add_help=False)
            _add_arguments_to_parser(self.subparser_common_parser, subparser_common_args)

        if self._parse_extra:
            self.parser.add_argument('extra_parser_args', nargs=REMAINDER, metavar='[[var1:val1] ...]')

    def execute(self, argv: Optional[Sequence[str]] = None, use_args: Optional[Namespace] = None) -> Any:
        """Parse the command line and call the command_runner.

        Args:
            argv (optional, default=None): The arguments to pass to the parser if use_args is None, otherwise sys.argv will be used.
            use_args (optional, default=None): The arguments to pass to the parser, otherwise argv will be used.

        Returns:
            The result of the called command_runner.
        """
        args: Namespace = use_args if use_args else self.parse_args(argv)
        caller: Callable = self._default if (self._subparsers and not args.command and self._default) else args.command
        caller_args = (self.subparser_common_parser, self._pass_on) if self.subparser_common_parser else (args,)
        return caller(*caller_args)

    def parse_args(self, argv: Optional[Sequence[str]] = None, err_msg: str = 'No command specified', raise_on_error: Optional[BaseException] = None) -> Namespace:
        """Parse the command line.

        Args:
            argv (optional, default=None): The arguments to pass to the parser, otherwise sys.argv will be used.
            err_msg (optional, default='No command specified'): The error message to use if a bad subcommand is requested.
            raise_on_error (optional, default=None): If not None, use the value as the error to be raised on a failure.

        Returns:
            The parsed argument Namespace.

        Raises:
            The value of raise_on_error if not False.
        """
        (args, self._pass_on) = self.parser.parse_known_args(argv) if self.subparser_common_parser else (self.parser.parse_args(argv), tuple())
        if self._subparsers and not args.command and not self._default:
            if raise_on_error:
                raise raise_on_error
            self.parser.error(err_msg)
        if self._parse_extra:
            for arg in args.extra_parser_args:
                if self._extra_var_sep in arg:
                    (var, val) = arg.split(self._extra_var_sep, 1)
                    setattr(args, var, str_to_pythonval(val) if self._convert_extra else val)
        return args


def _add_arguments_to_parser(parser: Union[ArgumentParser, _MutuallyExclusiveGroup], arglist: Iterable[Union[dict, Argument]], /) -> None:
    """Add arguments to the specified parser.

    Args:
        parser: The parser to which to add the arguments.
        arglist: The arguments to add to the parser.

    Returns:
        Nothing.
    """
    for arg in arglist:
        if isinstance(arg, dict):
            group_parser = parser.add_mutually_exclusive_group(**arg['options'])
            _add_arguments_to_parser(group_parser, arg['args'])
        else:
            parser.add_argument(*arg.names, **arg.options)
