'Basic language support'

# Import standard modules
from os import getenv
from pathlib import Path
from string import Template
import sys
from sys import executable, platform, version_info, path as sys_path

# Useful contants
VALIDATE_PYTHON = True
WIN32 = (platform == 'win32')
FROZEN = getattr(sys, 'frozen', False)
BATCAVE_HOME = Path(executable).parent if FROZEN else Path(sys_path[0])

# Application information
COPYRIGHT = 'Copyright 2019 Jeff Smith'


class MsgStr:
    ''' Generic Class for message strings
        This class is only useful when subclassed where the subclass simply defines the _messages.
        For example:
            class MyMsg(MsgStr):
                _messages = {'Message1': 'This is just a string',
                             'Message2': Template('This is a $what template)}

        Then the messages are retrieved as
            MyMsg().Message1
            MyMsg(what='this').Message2 '''

    def __init__(self, instr='', transform=None, **variables):
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
        if not isinstance(_str, str):
            _str = _str.substitute(self._vars)
        if self._transform:
            _str = getattr(_str, self._transform)()
        return _str


class HALException(Exception, MsgStr):
    'Generic Class for HAL exceptions'
    _messages = dict()

    def __init__(self, errobj, **variables):
        Exception.__init__(self, errobj, variables)
        MsgStr.__init__(self, errobj.msg, **variables)
        self._errobj = errobj
        self.vars = variables
        self.code = errobj.code

    def __str__(self):
        return MsgStr.__str__(self)


class HALError:
    'Provides interface for inspecting exceptions'
    def __init__(self, code, msg):
        self.code = code
        self.msg = msg


class PythonVersionError(HALException):
    'Used to indicate the wrong version of Python'
    WRONG_VERSION = HALError(1, Template('Python $needed required but $used used'))


class switch:  # pylint: disable=C0103
    ''' Taken verbatim from: http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/410692

        Title: Readable switch construction without lambdas or dictionaries
        Submitter: Brian Beck (other recipes)
        Last Updated: 2005/04/26
        Version no: 1.7

        Description:
        Python's lack of a 'switch' statement has garnered much discussion and even a PEP.
        The most popular substitute uses dictionaries to map cases to functions, which requires lots of defs or lambdas.
        While the approach shown here may be O(n) for cases, it aims to duplicate C's original 'switch' functionality and
        structure with reasonable accuracy. '''

    def __init__(self, value):
        self.value = value
        self.fall = False
        self.first = True

    def __iter__(self):
        'Return the match method once, then stop'
        if self.first:
            self.first = False
            yield self.match
        else:
            return

    def match(self, *args):
        'Indicate whether or not to enter a case suite'
        if self.fall or not args:
            return True
        elif self.value in args:
            self.fall = True
            return True
        else:
            return False


def bool_to_str(val):
    'Convert a boolean value to a string'
    return 'true' if val else 'false'


def flatten(thing):
    'Flatten a list of lists'
    flattened = False
    result = list()
    for item in thing:
        if isinstance(item, list):
            result += [i for i in item]
            flattened = True
        else:
            result.append(item)

    if flattened:
        return flatten(result)

    return result


def flatten_string_list(thing, remove_newlines=True):
    'Flatten a list of lists of strings to a single string'
    result = ''.join(flatten(thing))
    if remove_newlines:
        return result.replace('\n', '')
    return result


def is_debug(testvalue=None):
    'boolean is_debug(string testvalue)'
    debugvalue = getenv('BATCAVE_DEBUG')
    if not debugvalue:
        return False
    if not testvalue:
        return True
    if testvalue in debugvalue:
        return True
    return False


def str_to_pythonval(the_string, parse_python=False):
    'Converts a string to the closest interpretable Python type'
    if not isinstance(the_string, str):
        raise ValueError

    if the_string.isdecimal():
        return int(the_string)

    if the_string.isdigit():
        return float(the_string)

    if the_string.lower() == 'none':
        return None

    if the_string.lower() == 'true':
        return True

    if the_string.lower() == 'false':
        return False

    if parse_python and '~' in the_string:
        (data_type, val) = the_string.split('~')
        the_string = eval(f'{data_type}({val})')  # pylint: disable=W0123

    return the_string


def validate_python(test_against=None):
    'Checks to make sure that the minimum version of Python is used'
    used = version_info[:2]
    needed = test_against if test_against else (3, 6)
    if used != needed:
        raise PythonVersionError(PythonVersionError.WRONG_VERSION, used=used, needed=needed)


def xor(value1, value2):
    'exclusive-or evaluation'
    return bool(value1) ^ bool(value2)
