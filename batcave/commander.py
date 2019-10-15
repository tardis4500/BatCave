'Simplified interface to argparse'

# Import standard modules
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter, REMAINDER
from string import Template

# Import internal modules
from .version import get_version_info, VERSION_STYLES
from .lang import str_to_pythonval, HALError, HALException


class CommandParseError(HALException):
    'Class for LoadBalancer realted errors'
    NO_COMMAND = HALError(1, 'No command specified')
    BAD_COMMAND = HALError(2, Template('Invalid command: $cmd'))
    BAD_ARGUMENTS = HALError(3, Template('incorrect number of arguments for command $cmd'))


class Argument:
    'This is a simple container class to encapsulate and argument definition passed to ArgumentParser.add_argument()'
    def __init__(self, *names, **options):
        self.names = names
        self.options = options


class SubParser:
    'This is a simple container class to encapsulate a subparser definition'
    def __init__(self, subcommand, command_runner, arguments=tuple()):
        self.subcommand = subcommand
        self.command_runner = command_runner
        self.arguments = arguments


class Commander:
    'This provides a simplified interface to argparse.ArgumentParser'
    def __init__(self, description, arguments=tuple(), subparsers=tuple(), subparser_common_args=tuple(), default=None, parents=tuple(),
                 parse_extra=False, extra_var_sep=':', convert_extra=True,
                 add_version=True, version_style=VERSION_STYLES.oneline, formatter_class=ArgumentDefaultsHelpFormatter):
        self.subparsers = subparsers
        self.default = default
        self.pass_on = None
        self.parse_extra = parse_extra
        self.extra_var_sep = extra_var_sep
        self.convert_extra = convert_extra

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

        if self.parse_extra:
            self.parser.add_argument('extra_parser_args', nargs=REMAINDER, metavar='[[var1:val1] ...]')

    def parse_args(self, argv=None, err_msg='No command specified', raise_on_error=False):
        'Parse the command line'
        (args, self.pass_on) = self.parser.parse_known_args(argv) if self.subparser_common_parser else (self.parser.parse_args(argv), None)
        if self.subparsers and not args.command and not self.default:
            if raise_on_error:
                raise raise_on_error  # pylint: disable=E0702
            self.parser.error(err_msg)
        if self.parse_extra:
            for arg in args.extra_parser_args:
                if self.extra_var_sep in arg:
                    (var, val) = arg.split(self.extra_var_sep, 1)
                    setattr(args, var, str_to_pythonval(val) if self.convert_extra else val)
        return args

    def execute(self, argv=None, use_args=None):
        'Parse the command line and call the command_runner'
        args = use_args if use_args else self.parse_args(argv)
        caller = self.default if (self.subparsers and not args.command and self.default) else args.command
        caller_args = (self.subparser_common_parser, self.pass_on) if self.subparser_common_parser else (args,)
        return caller(*caller_args)


def _add_arguments_to_parser(parser, arglist):
    for arg in arglist:
        if isinstance(arg, dict):
            group_parser = parser.add_mutually_exclusive_group(**arg['options'])
            _add_arguments_to_parser(group_parser, arg['args'])
        else:
            parser.add_argument(*arg.names, **arg.options)
