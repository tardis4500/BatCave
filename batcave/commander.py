"""This module provides a simplified interface to the standard argparse module."""

# Import standard modules
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter, REMAINDER

# Import internal modules
from .version import get_version_info, VERSION_STYLES
from .lang import str_to_pythonval


class Argument:
    """This is a simple container class to encapsulate an argument definition passed to ArgumentParser.add_argument()."""

    def __init__(self, *names, **options):
        """
        Args:
            *names: A list of the argument names.
            **options (optional, default={}): A dictionary of the argument options.

        Attributes:
            names: The value of the names argument.
            options: The value of the options argument.
        """
        self.names = names
        self.options = options


class SubParser:
    """This is a simple container class to encapsulate a subparser definition."""

    def __init__(self, subcommand, command_runner, arguments=tuple()):
        """
        Args:
            subcommand: The subcommand name for the subparser.
            command_runner: The function which runs the commands for the subparser.
            arguments (optional, default=None): A list of arguments for the subparser.

        Attributes:
            arguments: The value of the arguments argument.
            command_runner: The value of the command_runner argument.
            subcommand: The value of the subcommand argument.
        """
        self.subcommand = subcommand
        self.command_runner = command_runner
        self.arguments = arguments


class Commander:
    """This class provides a simplified interface to the argparse.ArgumentParser class."""

    def __init__(self, description, arguments=tuple(), subparsers=tuple(), subparser_common_args=tuple(), default=None, parents=tuple(),
                 parse_extra=False, extra_var_sep=':', convert_extra=True,
                 add_version=True, version_style=VERSION_STYLES.oneline, formatter_class=ArgumentDefaultsHelpFormatter):
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
        self._pass_on = None
        self._subparsers = subparsers

        self.parser = ArgumentParser(description=description, formatter_class=formatter_class, parents=parents)
        _add_arguments_to_parser(self.parser, arguments)
        if add_version:
            self.parser.add_argument('-v', '--version', action='version', version=get_version_info(version_style))

        if subparsers:
            subparser_objects = self.parser.add_subparsers(dest='command')
        for subparser_def in subparsers:
            subparser = subparser_objects.add_parser(subparser_def.subcommand)
            _add_arguments_to_parser(subparser, subparser_def.arguments)
            subparser.set_defaults(command=subparser_def.command_runner)

        self.subparser_common_parser = ArgumentParser(add_help=False) if subparser_common_args else None
        _add_arguments_to_parser(self.subparser_common_parser, subparser_common_args)

        if self._parse_extra:
            self.parser.add_argument('extra_parser_args', nargs=REMAINDER, metavar='[[var1:val1] ...]')

    def execute(self, argv=None, use_args=None):
        """Parse the command line and call the command_runner.

        Args:
            argv (optional, default=None): The arguments to pass to the parser if use_args is None, otherwise sys.argv will be used.
            use_args (optional, default=None): The arguments to pass to the parser, otherwise argv will be used.

        Returns:
            The result of the called command_runner.
        """
        args = use_args if use_args else self.parse_args(argv)
        caller = self._default if (self._subparsers and not args.command and self._default) else args.command
        caller_args = (self.subparser_common_parser, self._pass_on) if self.subparser_common_parser else (args,)
        return caller(*caller_args)

    def parse_args(self, argv=None, err_msg='No command specified', raise_on_error=False):
        """Parse the command line.

        Args:
            argv (optional, default=None): The arguments to pass to the parser, otherwise sys.argv will be used.
            err_msg (optional, default='No command specified'): The error message to use if a bad subcommand is requested.
            raise_on_error (optional, default=False): If not False, use the value as the error to be raised on a failure.

        Returns:
            The parsed argument Namespace.

        Raises:
            The value of raise_on_error if not False.
        """
        (args, self._pass_on) = self.parser.parse_known_args(argv) if self.subparser_common_parser else (self.parser.parse_args(argv), None)
        if self._subparsers and not args.command and not self._default:
            if raise_on_error:
                raise raise_on_error  # pylint: disable=E0702
            self.parser.error(err_msg)
        if self._parse_extra:
            for arg in args.extra_parser_args:
                if self._extra_var_sep in arg:
                    (var, val) = arg.split(self._extra_var_sep, 1)
                    setattr(args, var, str_to_pythonval(val) if self._convert_extra else val)
        return args


def _add_arguments_to_parser(parser, arglist):
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
