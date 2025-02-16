"""This module provides Python language utilities.

Attributes:
    DEFAULT_ENCODING: The default encoding used for text file operations.
    BATCAVE_HOME: The home directory of the module.
    FROZEN (bool): Is this module running in a frozen application. Quick version of sys.frozen
    VALIDATE_PYTHON (bool, default=True): Whether this module should validate the minimum version of Python when loaded.
    WIN32 (bool): Is this module running on a Windows system. Quick version of (sys.platform == 'win32')
"""

# Import standard modules
from dataclasses import dataclass
from os import getenv
from pathlib import Path, PurePath
from string import Template
import sys
from sys import executable, platform, version_info, path as sys_path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Import third-party modules
from dotmap import DotMap
from yaml import safe_dump as yaml_dump, safe_load as yaml_load

# Useful constants
DEFAULT_ENCODING = 'UTF-8'
FROZEN = getattr(sys, 'frozen', False)
BATCAVE_HOME = Path(executable).parent if FROZEN else Path(sys_path[0])
VALIDATE_PYTHON = True
WIN32 = platform == 'win32'

type CommandResult = str | List[str]
type MessageString = str | Template
type PathName = str | Path | PurePath


class MsgStr:
    """Class to create a universal abstract interface for message strings.

    This class is only useful when subclassed where the subclass simply defines the _messages.

    Attributes:
        _message: A dictionary of messages provided by subclasses.

    Example:
        class MyMsg(MsgStr):
            _messages = {'Message1': 'This is just a string',
                            'Message2': Template('This is a $what template)}

        where messages are retrieved with
            MyMsg().Message1
            MyMsg(what='this').Message2
    """
    _messages: Dict[str, str | Template] = {}

    def __init__(self, instr: str | Template = '', transform: str = '', **variables):
        """
        Args:
            instr (optional, default=''): The input message string.
            transform (optional, default=None): A string method used to transform the input message string on output.
            variables (optional): A dictionary of variables to pass to the string.Template.substitute method.

        Attributes:
            _str: The value of the instr argument.
            _transform: The value of the transform argument.
            _vars: The value of the variables argument.
        """
        self._str = instr
        self._transform = transform
        self._vars = variables

    def __getattr__(self, attr: str) -> str:
        if attr in self._messages:
            return self._self_to_str(self._messages[attr])
        raise AttributeError(f"'{type(self)}' object has no attribute '{attr}'")

    def __str__(self):
        return self._self_to_str(self._str)

    def _self_to_str(self, _str: MessageString, /) -> str:
        """Convert this message to a string and apply any transforms.

        Returns:
            The string message.
        """
        return_str: str = _str.substitute(self._vars) if isinstance(_str, Template) else _str
        if self._transform:
            return_str = getattr(return_str, self._transform)()
        return return_str


class BatCaveException(Exception, MsgStr):
    """A base class to provide easier Exception management."""
    def __init__(self, err_obj: 'BatCaveError', /, **variables):
        """
        Args:
            err_obj: The input message string.
            variables (optional): A dictionary of variables to pass to the string.Template.substitute method.

        Attributes:
            vars: The value of the variables argument.
            _err_obj: The value of the err_obj argument.
        """
        Exception.__init__(self, err_obj, variables)
        MsgStr.__init__(self, err_obj.msg, **variables)
        self._err_obj = err_obj
        self.vars = variables

    def __str__(self):
        return MsgStr.__str__(self)

    code = property(lambda s: s._err_obj.code, doc='A read-only property which returns the error code from the error object.')


@dataclass(frozen=True)
class BatCaveError:
    """A class to provide an interface for inspecting exceptions.

        Attributes:
            code: A unique error code for this error.
            msg: A user-facing message for this error.
    """
    code: int
    msg: MessageString


class PythonVersionError(BatCaveException):
    """Invalid Python Version Exception.

    Attributes:
        BAD_VERSION: The version of Python is too low.
    """
    BAD_VERSION = BatCaveError(1, Template('Python $needed required but $used used'))


def bool_to_str(expr: bool | str, /) -> str:
    """Converts an expression to a lowercase boolean string value.

    Args:
        expr: The expression to convert.

    Returns:
        'true' if the expression evaluates to True, 'false' otherwise.
    """
    return str(bool(expr)).lower()


def dotmap_to_yaml(dotmap_thing: DotMap, yaml_file: PathName, /) -> None:
    """Convert a DotMap to a YAML file.

    Args:
        dotmap_thing: The DotMap to convert.
        yaml_file: The YAML file to which to write the DotMap.

    Returns:
        Nothing.
    """
    with open(yaml_file, 'w', encoding=DEFAULT_ENCODING) as yaml_stream:
        return yaml_dump(dotmap_thing.toDict(), yaml_stream)


def yaml_to_dotmap(yaml_info: str | PathName, /) -> DotMap:
    """Converts a YAML file to a DotMap.

    Args:
        yaml_info: The YAML to which to read into a DotMap. If this is a string it is presumed to be raw YAML
                    otherwise it is expected to be a Path object which can be open and read.

    Returns:
        A DotMap representing the YAML content.
    """
    if isinstance(yaml_info, str):
        return DotMap(yaml_load(yaml_info))
    with open(yaml_info, encoding=DEFAULT_ENCODING) as yaml_stream:
        return DotMap(yaml_load(yaml_stream))


def flatten(thing: Iterable[Iterable], /, *, recursive: bool = True) -> Iterable:
    """Flatten an iterable of iterables.

    Args:
        thing: The thing to be flattened.
        recursive (optional, default=True): Whether or not to recursively flatten the item.

    Returns:
        The final single depth item as the same type as thing.
    """
    flattened = False
    result = []
    for item in thing:
        try:
            result += [i for i in iter(item)]  # pylint: disable=unnecessary-comprehension
            flattened = True
        except TypeError:
            result.append(item)

    if recursive and flattened:
        return flatten(result)

    return type(thing)(result)  # type: ignore[call-arg]


def flatten_string_list(iter_of_string: Iterable[str], /, *, remove_newlines: bool = True) -> str:
    """Flatten an iterable of strings to a single string.

    Args:
        iter_of_string: The list of strings to be flattened to be flattened.
        remove_newlines (optional, default=True): Whether or not to remove newlines from the final list.

    Returns:
        The final string.
    """
    result = ''.join(flatten(iter_of_string))
    if remove_newlines:
        return result.replace('\n', '')
    return result


def is_debug(test_value: Optional[str] = None, /) -> bool:
    """Determine if the BATCAVE_DEBUG environment variable is set.

    Args:
        test_value (optional, default=False): If set, only return true if the value of test_value is in BATCAVE_DEBUG.

    Return:
        True if the OS environment variable BATCAVE_DEBUG is set, False otherwise.
    """
    return bool(debug_value := getenv('BATCAVE_DEBUG', '')) and ((not test_value) or (test_value in debug_value))


def str_to_pythonval(the_string: str, /, *, parse_python: bool = False) -> Any:
    """Converts a string to the closest Python object.

    Args:
        the_string: The string to evaluate.
        parse_python (optional, default=False): If the string contains a '~' character, try to convert it to a more complex python object.

    Returns:
        #. If the string represents an integer, return the value as an int.
        #. If the string represents an non-integer number, return the value as a float.
        #. If the string evaluates to 'None' (case-insensitive), return None.
        #. If the string evaluates to 'True' or 'False' (case-insensitive), return True/False.
        #. If parse_python is True and the_string contains '~':
            Split the_string on the first '~' and return the second part as the value of a type specified by the first part.

    Raises:
        ValueError: If the_string is not a string.
    """
    if not isinstance(the_string, str):
        raise ValueError

    if the_string.isdecimal():
        return int(the_string)

    if the_string.isdigit():
        return float(the_string)

    for (test, value) in (('none', None), ('true', True), ('false', False)):
        if the_string.lower() == test:
            return value

    if parse_python and '~' in the_string:
        (data_type, val) = the_string.split('~', 1)
        the_string = eval(f'{data_type}({val})')  # pylint: disable=eval-used

    if parse_python and '~' in the_string:
        (data_type, val) = the_string.split('~', 1)
        the_string = eval(f'{data_type}({val})')  # pylint: disable=eval-used

    return the_string


def validate_python(test_against: Tuple[int, int] = (3, 6), /) -> None:
    """Checks to make sure that a minimum version of Python is used.

    Args:
        test_against (optional, default=(3,7)): The value of Python to check.

    Returns:
        Nothing.

    Raises:
        PythonVersionError.BAD_VERSION: If the version is too low.
    """
    used = version_info[:2]
    needed = test_against if test_against else (3, 6)
    if used != needed:
        raise PythonVersionError(PythonVersionError.BAD_VERSION, used=used, needed=needed)


def xor(value1: Any, value2: Any, /) -> bool:
    """Perform a logical exclusive-or evaluation.

    Args:
        value1, value2: The values on which to perform the operation.

    Returns:
        The logical exclusive-or of the values.
    """
    return bool(value1) ^ bool(value2)

# cSpell:ignore batcave dotmap pythonval
