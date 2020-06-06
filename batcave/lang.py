"""This module provides Python language utilities.

Attributes:
    BATCAVE_HOME: The home directory of the module.
    FROZEN (bool): Is this module running in a frozen application. Quick version of sys.frozen
    VALIDATE_PYTHON (bool, default=True): Whether this module should validate the minimum version of Python when loaded.
    WIN32 (bool): Is this module running on a Windows system. Quick version of (sys.platform == 'win32')
"""

# Import standard modules
from os import getenv
from pathlib import Path
from string import Template
import sys
from sys import executable, platform, version_info, path as sys_path
from typing import Union

# Useful contants
FROZEN = getattr(sys, 'frozen', False)
BATCAVE_HOME = Path(executable).parent if FROZEN else Path(sys_path[0])
VALIDATE_PYTHON = True
WIN32 = (platform == 'win32')

PathName = Union[str, Path]


class MsgStr:
    """Class to create a universal abstract interface for message strings.

    This class is only useful when subclassed where the subclass simply defines the _messages.

    Example:
        class MyMsg(MsgStr):
            _messages = {'Message1': 'This is just a string',
                            'Message2': Template('This is a $what template)}

        where messages are retrieved with
            MyMsg().Message1
            MyMsg(what='this').Message2
    """
    def __init__(self, instr='', transform=None, **variables):
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

    def __getattr__(self, attr):
        if attr in list(self._messages.keys()):
            return self._self_to_str(self._messages[attr])
        raise AttributeError(f"'{type(self)}' object has no attribute '{attr}'")

    def __str__(self):
        return self._self_to_str(self._str)

    def _self_to_str(self, _str):
        """Convert this message to a string and apply any transforms.

        Returns:
            The string message.
        """
        if isinstance(_str, Template):
            _str = _str.substitute(self._vars)
        if self._transform:
            _str = getattr(_str, self._transform)()
        return _str


class BatCaveException(Exception, MsgStr):
    """A base class to provide easier Exception management.

    Attributes:
        _message: A dictionary of messages provided by subclasses.
    """
    _messages = dict()

    def __init__(self, errobj, **variables):
        """
        Args:
            errobj: The input message string.
            variables (optional): A dictionary of variables to pass to the string.Template.substitute method.

        Attributes:
            vars: The value of the variables argument.
            _errobj: The value of the errobj argument.
        """
        Exception.__init__(self, errobj, variables)
        MsgStr.__init__(self, errobj.msg, **variables)
        self._errobj = errobj
        self.vars = variables

    def __str__(self):
        return MsgStr.__str__(self)

    code = property(lambda s: s._errobj.code, doc='A read-only property which returns the error code from the error object.')


class BatCaveError:
    """A class to provide an interface for inspecting exceptions."""
    def __init__(self, code, msg):
        """
        Args:
            code: A unique error code for this error.
            msg: A user-facing message for this error.

        Attributes:
            code: The value of the code argument.
            msg: The value of the msg argument.
        """
        self.code = code
        self.msg = msg


class PythonVersionError(BatCaveException):
    """Invalid Python Version Exception.

    Attributes:
        BAD_VERSION: The version of Python is too low.
    """
    BAD_VERSION = BatCaveError(1, Template('Python $needed required but $used used'))


class switch:  # pylint: disable=C0103
    """Class to implement a Pythonic switch statement.

    Taken verbatim from: http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/410692

    Title: Readable switch construction without lambdas or dictionaries
    Submitter: Brian Beck (other recipes)
    Last Updated: 2005/04/26
    Version no: 1.7

    Description:
        Python's lack of a 'switch' statement has garnered much discussion and even a PEP.
        The most popular substitute uses dictionaries to map cases to functions, which requires lots of defs or lambdas.
        While the approach shown here may be O(n) for cases, it aims to duplicate C's original 'switch' functionality and
        structure with reasonable accuracy.
    """

    def __init__(self, value):
        self.value = value
        self.fall = False
        self.first = True

    def __iter__(self):
        if self.first:
            self.first = False
            yield self.match
        else:
            return

    def match(self, *args):
        """Indicate whether or not to enter a case suite."""
        if self.fall or not args:
            return True
        elif self.value in args:
            self.fall = True
            return True
        else:
            return False


def bool_to_str(expr):
    """Converts an expression to a lowercase boolean string value.

    Args:
        expr: The expression to convert.

    Returns:
        'true' if the expression evaluates to True, 'false' otherwise.
    """
    return str(bool(expr)).lower()


def flatten(thing, recursive=True):
    """Flatten an iterable of iterables.

    Args:
        thing: The thing to be flattened.
        recursive (optional, default=True): Whether or not to recursively flatten the item.

    Returns:
        The final single depth item as the same type as thing.
    """
    flattened = False
    result = list()
    for item in thing:
        try:
            result += [i for i in iter(item)]
            flattened = True
        except TypeError:
            result.append(item)

    if recursive and flattened:
        return flatten(result)

    return type(thing)(result)


def flatten_string_list(iter_of_string, remove_newlines=True):
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


def is_debug(test_value=None):
    """Determine if the BATCAVE_DEBUG environment variable is set.

    Args:
        test_value (optional, default=None): If set, only return true if the value of test_value is in BATCAVE_DEBUG.

    Return:
        True if the OS environment variable BATCAVE_DEBUG is set, False otherwise.
    """
    debug_value = getenv('BATCAVE_DEBUG')
    if not debug_value:
        return False
    if not test_value:
        return True
    if test_value in debug_value:
        return True
    return False


def str_to_pythonval(the_string, parse_python=False):
    """Converts a string to the closest Python object.

    Args:
        the_string: The string to evaluate.
        parse_python (optional, default=False): If the string contains a '~' character, try to convert it to a more complex python object.

    Returns:
        1. If the string represents an integer, return the value as an int.
        2. If the string represents an non-integer number, return the value as a float.
        3. If the string evaluates to 'None' (case-insensitive), return None.
        4. If the string evaluates to 'True' or 'False' (case-insensitive), return True/False.
        3. If parse_python is True and the_string contains '~':
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
        the_string = eval(f'{data_type}({val})')  # pylint: disable=W0123

    return the_string


def validate_python(test_against=(3, 6)):
    """Checks to make sure that a minimum version of Python is used.

    Args:
        test_against (optional, default=(3,7)): The value of Python to check.

    Raises:
        PythonVersionError.BAD_VERSION: If the version is too low.
    """
    used = version_info[:2]
    needed = test_against if test_against else (3, 6)
    if used != needed:
        raise PythonVersionError(PythonVersionError.BAD_VERSION, used=used, needed=needed)


def xor(value1, value2):
    """Perform a logical exclusive-or evaluation.

    Args:
        value1, value2: The values on which to perform the operation.

    Returns:
        The logical exclusive-or of the values.
    """
    return bool(value1) ^ bool(value2)
