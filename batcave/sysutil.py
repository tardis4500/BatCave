"""This module provides a Pythonic interface to work with system utilities.

Attributes:
    PROG_FILES (dict): The default software installation location
        For 32-bit Windows systems this is the value of the ProgramFiles(x86) environment variable.
        For 64-bit Windows systems this is the value of the ProgramFiles environment variable.
        For all other systems it is /usr/local.
    S_660: A quick version of the UNIX 0660 mode.
    S_664: A quick version of the UNIX 0664 mode.
    S_770: A quick version of the UNIX 0770 mode.
    S_775: A quick version of the UNIX 0775 mode.
"""

# Import standard modules
import sys
from copy import copy as copy_object
from enum import Enum
from errno import EACCES, EAGAIN, ECHILD
from os import chdir, getenv, remove, unlink, walk
from pathlib import Path
from shutil import rmtree, chown as os_chown
from stat import S_IRUSR, S_IWUSR, S_IRGRP, S_IWGRP, S_IROTH, S_IRWXU, S_IRWXG, S_IXOTH
from string import Template
from subprocess import Popen, PIPE
from typing import cast, Any, Dict, Callable, IO, Iterable, List, Optional, Tuple, TextIO, Union

# Import internal modules
from .lang import flatten_string_list, is_debug, BatCaveError, BatCaveException, CommandResult, PathName, WIN32

if sys.platform == 'win32':
    from msvcrt import locking, LK_NBLCK, LK_UNLCK  # pylint: disable=import-error
    PROG_FILES = {'32': Path(getenv('ProgramFiles(x86)', '')), '64': Path(getenv('ProgramFiles', ''))}
    geteuid = getgrnam = getpwnam = None  # Fix Pylance and mypy linting errors  # pylint: disable=invalid-name
else:
    from fcntl import lockf, LOCK_EX, LOCK_NB, LOCK_UN  # pylint: disable=import-error
    from grp import getgrnam  # pylint: disable=import-error
    from os import geteuid  # pylint: disable=no-name-in-module,ungrouped-imports
    from pwd import getpwnam  # pylint: disable=import-error
    PROG_FILES = {'32': Path('/usr/local')}
    PROG_FILES['64'] = PROG_FILES['32']

LockMode = Enum('LockMode', ('lock', 'unlock'))
S_660 = S_IRUSR | S_IWUSR | S_IRGRP | S_IWGRP
S_664 = S_660 | S_IROTH
S_770 = S_IRWXU | S_IRWXG
S_775 = S_770 | S_IROTH | S_IXOTH


class CMDError(BatCaveException):
    """System Command Exceptions.

    Attributes:
        CMD_ERROR: Generic command error.
        CMD_NOT_FOUND: The command was not found.
        INVALID_OPERATION: The requested operation is not supported in the current context.
    """
    CMD_ERROR = BatCaveError(1, '')
    CMD_NOT_FOUND = BatCaveError(2, Template('Command not found when running: $cmd'))
    INVALID_OPERATION = BatCaveError(3, Template('$func is not supported for $context'))

    def __str__(self):
        if self._errobj.code == CMDError.CMD_ERROR.code:
            errlines = self.vars['errlines'] if self.vars['errlines'] else self.vars['outlines']
            return f"Error {self.vars['returncode']} when running: {self.vars['cmd']}\nError output:\n" + ''.join(errlines)
        return BatCaveException.__str__(self)


class LockError(BatCaveException):
    """Lock File Exceptions.

    Attributes:
        NO_LOCK: There was a failure attempting to get a lock on the lock file.
    """
    NO_LOCK = BatCaveError(1, Template('Unable to get lock'))


class OSUtilError(BatCaveException):
    """Operating System Exceptions.

    Attributes:
        GROUP_EXISTS: The specified group already exists.
        INVALID_OPERATION: The requested operation is not supported on the current platform.
        USER_EXISTS: The specified user already exists.
    """
    GROUP_EXISTS = BatCaveError(1, Template('The group already exists: $group'))
    INVALID_OPERATION = BatCaveError(2, Template('Platform unsupported: $platform'))
    USER_EXISTS = BatCaveError(3, Template('The user already exists: $user'))


class LockFile:
    """Class to create a universal abstract interface for an OS lock file."""

    def __init__(self, filename: PathName, /, handle: Optional[TextIO] = None, *, cleanup: bool = True):
        """
        Args:
            filename: The file name for the lock file.
            handle (optional, default=None): The value of the file handle if the file is already open, otherwise the file specified in the filename will be opened.
            cleanup (optional, default=True): If True, the lock file will be removed when the lock is released.

        Attributes:
            _cleanup: The value of the cleanup argument.
            _fd: The fileno for the _fh attribute.
            _fh: The value of the handle argument if not None, otherwise the value of the handle for the opened filename argument.
            _filename: The value of the filename argument.
            _lock: The value to pass to the _locker method to lock the file.
            _locker: The method used to lock the file.
            _unlock: The value to pass to the _locker method to unlock the file.
        """
        self._filename = Path(filename)
        self._cleanup = cleanup
        self._fh = handle if handle else open(filename, 'w')
        self._fd = self._fh.fileno()
        if sys.platform == 'win32':
            self._locker = locking
            self._lock = LK_NBLCK
            self._unlock = LK_UNLCK
        else:
            self._locker = lockf
            self._lock = LOCK_EX | LOCK_NB
            self._unlock = LOCK_UN
        self.action(LockMode.lock)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False

    def action(self, mode: LockMode, /) -> None:
        """Perform the requested action on the lock file.

        Args:
            mode: The action to perform on the lock file.

        Returns:
            Nothing.

        Raises:
            LockError.NO_LOCK: If it was not possible to obtain a system level lock on the lock file.
        """
        lock_mode = self._lock if (mode == LockMode.lock) else self._unlock
        try:
            self._locker(self._fd, lock_mode, 1)
        except IOError as err:
            if err.errno not in (EACCES, EAGAIN):
                raise
            raise LockError(LockError.NO_LOCK) from err

    def close(self) -> None:
        """Close the lock file.

        Returns:
            Nothing.
        """
        self.action(LockMode.unlock)
        self._fh.close()
        if self._cleanup:
            self._filename.unlink()


class SysCmdRunner:  # pylint: disable=too-few-public-methods
    """This class provides a simplified interface to sysutil.syscmd()."""

    def __init__(self, command: str, /, *args, show_cmd: bool = True, show_stdout: bool = True, syscmd_args: Optional[Dict[Any, Any]] = None, **kwargs: Any):
        """
        Args:
            command: The command to run.
            show_cmd (optional, default=True): The default value of the show_cmd value passed to syscmd.
            show_stdout (optional, default=True): The default value of the show_stdout value passed to syscmd.
            syscmd_args (optional, default={}): The dictionary of other arguments passed to syscmd.
            *args (optional): A list of default arguments to use each time the command is run.
            **kwargs (optional): A list of default keys to use each time the command is run.

        Attributes:
            _command: The value of the command argument.
            _default_args: The value of the args argument.
            _default_kwargs: The value of the kwargs argument.
            _default_syscmd_kwargs: The value of the syscmd_args argument.
        """
        self._command = command
        self._default_args = list(args)
        self._default_kwargs = kwargs
        self._default_syscmd_args: Dict[Any, Any] = {'show_cmd': show_cmd, 'show_stdout': show_stdout}
        if syscmd_args:
            self._default_syscmd_args.update(syscmd_args)

    def run(self, *args, post_option_args: Optional[Dict] = None, syscmd_args: Optional[Dict[Any, Any]] = None, **kwargs) -> CommandResult:
        """Run the defined command with the additional specified arguments.

        Args:
            post_option_args (optional, default=[]): The list of args to pass after the options.
            syscmd_args (optional, default={}): The list of default args passed to syscmd.
            *args (optional, default=[]): Any extra arguments to pass to the command.
            **kwargs (optional, default={}): Any extra keyword arguments to pass to the command.

        Returns:
            The result of the syscmd call.
        """
        command_args = self._default_args + list(args)
        option_args = copy_object(self._default_kwargs)
        option_args.update(kwargs)
        for (arg, value) in option_args.items():
            arg_name = arg.replace('_', '-')
            if value is True:
                command_args.append(f'--{arg_name}')
            else:
                command_args.append(f'--{arg_name}={value}')
        if post_option_args:
            command_args += post_option_args
        all_syscmd_args = copy_object(self._default_syscmd_args)
        if syscmd_args:
            all_syscmd_args.update(syscmd_args)
        return syscmd(self._command, *command_args, **all_syscmd_args)


def chmod(dirname: PathName, mode: int, *, recursive: bool = False, files_only: bool = False) -> None:
    """Perform chmod recursively if requested.

    Args:
        dirname: The directory for which to set the mode.
        mode: The mode to set as would be specified for os.chmod().
        recursive (optional, default=False): Also perform setting recursively on all children.
        files_only (optional, default=False): Only affect files.

    Returns:
        Nothing.
    """
    dirname = Path(dirname)
    if not files_only:
        dirname.chmod(mode)
    if recursive:
        for (root, dirs, files) in walk(dirname):
            for pathname in (files if files_only else (dirs + files)):  # pylint: disable=superfluous-parens
                Path(root, pathname).chmod(mode)


def chown(pathname: PathName, user: Optional[str] = None, group: Optional[str] = None, *, recursive: bool = False) -> None:
    """Perform chown and chgrp together, recursively if requested.

    Args:
        user (optional, default=None): The user to set as the owner, if specified.
        group (optional, default=None): The group to set as the owner, if specified.
        recursive (optional, default=False): Also perform the user/owner settings recursively on all children.

    Returns:
        Nothing.
    """
    os_chown(path := Path(pathname), user, group)
    if recursive:
        for (root, dirs, files) in walk(path):
            for sub_path in dirs + files:
                os_chown(Path(root, sub_path), user, group)


def create_group(group_name: str, /, *, exists_ok: bool = True) -> None:
    """Create the system group at the OS level.

    Args:
        group_name: The group to create.
        exists_ok (optional, default=True): Do not raise an error if the group exists.

    Returns:
        Nothing.

    Raises:
        OSUtilError.GROUP_EXISTS: If the group exists and exists_ok is False.
        OSUtilError.INVALID_OPERATION: If this is a Windows platform.

    Todo:
        Implement for the Windows platform.
    """
    if sys.platform == 'win32':
        raise OSUtilError(OSUtilError.INVALID_OPERATION, platform='Windows')
    try:
        getgrnam(group_name)
        if not exists_ok:
            raise OSUtilError(OSUtilError.GROUP_EXISTS, group=group_name)
    except KeyError:
        syscmd('groupadd', group_name)


def create_user(username: str, /, groups: Tuple = tuple(), *, exists_ok: bool = True) -> None:
    """Create the user account at the OS level.

    Args:
        username: The user account to create.
        exists_ok (optional, default=True): Do not raise an error if the user exists.

    Returns:
        Nothing.

    Raises:
        OSUtilError.USER_EXISTS: If the user exists and exists_ok is False.
        OSUtilError.INVALID_OPERATION: If this is a Windows platform.

    Todo:
        Implement for the Windows platform.
    """
    if sys.platform == 'win32':
        raise OSUtilError(OSUtilError.INVALID_OPERATION, platform='Windows')
    create_group(username, exists_ok=exists_ok)
    try:
        getpwnam(username)
        if not exists_ok:
            raise OSUtilError(OSUtilError.USER_EXISTS, group=username)
    except KeyError:
        groups_args = (('-G',) + groups) if groups else tuple()
        syscmd('useradd', username, '-g', username, *groups_args)


def is_user_administrator() -> bool:
    """Determines if the current user is an OS administrator.

    Args:
        None

    Returns:
        True if the user is an administrator, False otherwise.
    """
    if sys.platform == 'win32':
        try:
            syscmd('net', 'file')
        except CMDError as err:
            if 'Access is denied' in str(err):
                return False
            raise
    elif geteuid() != 0:
        return False
    return True


def rmpath(path_name: PathName, /) -> None:
    """Remove the specified path object. If a directory, remove recursively.

    Args:
        path_name: The name of the path object to remove.

    Returns:
        Nothing.
    """
    if (path_name := Path(path_name)).is_dir():
        rmtree_hard(path_name)
    else:
        path_name.unlink()


def rmtree_hard(tree: PathName, /) -> None:
    """Recursively, remove a directory and try to avoid non-fatal errors.

    Args:
        tree: The directory tree to remove.

    Returns:
        Nothing.
    """
    rmtree(tree, onerror=_rmtree_onerror)


def _rmtree_onerror(caller: Callable, pathstr: PathName, excinfo: Any) -> None:
    """The exception handler used by rmtree_hard to try to remove read-only attributes.

    Args:
        caller: The calling function.
        pathstr: The path to change.
        excinfo: The run stack to use if the caller is not remove or unlink.

    Returns:
        Nothing.

    Raises:
        The exception in excinfo if the caller is not remove or unlink.
    """
    pathstr = Path(pathstr)
    if caller not in (remove, unlink):
        raise excinfo[0](excinfo[1])
    pathstr.chmod(S_IRWXU)
    pathstr.unlink()


def syscmd(command: str, /, *cmd_args, input_lines: Optional[Iterable] = None, show_stdout: bool = False,  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
           ignore_stderr: bool = False, append_stderr: bool = False, fail_on_error: bool = True, show_cmd: bool = False,
           use_shell: bool = False, flatten_output: bool = False, remote: Optional[Union[bool, str]] = False,
           remote_is_windows: Optional[bool] = None, copy_for_remote: bool = False, remote_auth: Optional[Tuple[str, str]] = None,
           remote_powershell: bool = False) -> CommandResult:
    """Wrapper to provide a better interface to subprocess.Popen().

    Args:
        command
        *cmd_args
        input_lines=None
        show_stdout=False
        ignore_stderr=False
        append_stderr=False
        fail_on_error=True
        show_cmd=False
        use_shell=False
        flatten_output=False
        remote=False
        remote_is_windows=None
        copy_for_remote=False
        remote_auth=Noneremote_powershell=False

    Returns:
        The string (or string-list) output of the command.

    Raises:
        CMDError.INVALID_OPERATION:
            If PowerShell remoting is requested while trying to pass remote credentials,
            If remote execution requires the executable to be copied before execution and the local or remote system is Linux.
            If remote execution requires the executable to be copied before execution and PowerShell remoting is requested.
            If any remote options are provided but remote is False.
        CMDError.CMD_NOT_FOUND: If the requested command is not found.
        CMDError.CMD_ERROR: If fail_on_error is True, and the return code is non-zero, or there is output on stderr if ignore_stderr is True.
    """
    cmd_spec = [str(command)] + [str(c) for c in cmd_args]
    remote_driver: List[str] = list()
    if remote:
        remote_is_windows = WIN32 if (remote_is_windows is None) else remote_is_windows
        if WIN32:
            if remote_is_windows:
                if remote_powershell:
                    if remote_auth or copy_for_remote:
                        raise CMDError(CMDError.INVALID_OPERATION, func='remote_auth' if remote_auth else 'copy_for_remote', context='PowerShell')
                    remote_driver = ['powershell', '-NoLogo', '-NonInteractive', '-Command', 'Invoke-Command', '-ComputerName', str(remote), '-ScriptBlock']
                else:
                    ignore_stderr = True  # psexec puts status info on stderr
                    remote_driver = ['psexec', rf'\\{remote}', '-accepteula', '-nobanner', '-h']
                    if remote_auth:
                        remote_driver += ['-u', remote_auth[0], '-p', remote_auth[1]]
                    if copy_for_remote:
                        remote_driver.append('-c')
                        copy_for_remote = False
            else:
                if copy_for_remote:
                    raise CMDError(CMDError.INVALID_OPERATION, func='copy_for_remote', context='Linux')
                remote_driver = ['plink', '-batch', '-v']
                if remote_auth:
                    remote_driver += ['-l', remote_auth[0], '-pw', remote_auth[1]]
                remote_driver += [str(remote)]
        else:
            if copy_for_remote:
                raise CMDError(CMDError.INVALID_OPERATION, func='copy_for_remote', context='Linux')
            remote_driver = ['ssh', '-t', '-t']
            if remote_auth:
                remote_driver += ['-u', remote_auth[0], '-p', remote_auth[1]]
            remote_driver += [str(remote)]

        remote_cmd = cmd_spec
        if use_shell and remote_is_windows:
            remote_cmd = ['cmd', '/c'] + cmd_spec
        use_shell = False
        if remote_powershell:
            remote_cmd = ['{'] + remote_cmd + ['}']
        cmd_spec = remote_driver + remote_cmd
    elif remote_auth or copy_for_remote or remote_powershell or remote_is_windows:
        raise CMDError(CMDError.INVALID_OPERATION, func='remote options', context='local servers')

    cmd_str = ' '.join([f'"{c}"' for c in cmd_spec])
    if show_cmd or is_debug('SYSCMD'):
        print('Executing system command:', cmd_str)
    cmd_to_pass = cmd_str if use_shell else cmd_spec

    proc = Popen(cmd_to_pass, shell=use_shell, universal_newlines=True, stdout=PIPE, stderr=PIPE,
                 bufsize=0 if show_stdout else -1,
                 stdin=PIPE if input_lines else None)

    if input_lines:
        if is_debug('SYSCMD'):
            print('Sending input lines:', input_lines)
        cast(IO, proc.stdin).writelines(input_lines)
        cast(IO, proc.stdin).close()

    if is_debug('SYSCMD'):
        print('Getting output lines')
    outlines = list()
    for line in iter(cast(IO, proc.stdout).readline, ''):
        if is_debug('SYSCMD'):
            print('Received output line:', line)
        outlines.append(line)
        if show_stdout:
            sys.stdout.write(line)

    if is_debug('SYSCMD'):
        print('Getting error lines')
    errlines = cast(IO, proc.stderr).readlines()
    if is_debug('SYSCMD'):
        print('Received error lines:', errlines)

    if is_debug('SYSCMD'):
        print('Getting return code')
    try:
        returncode = proc.wait()
    except OSError as err:
        if err.errno == ECHILD:
            returncode = proc.returncode
        else:
            raise
    if is_debug('SYSCMD'):
        print('Received return code:', returncode)

    if remote and WIN32 and (not remote_is_windows) and (not returncode) and (errlines[-1] == 'Disconnected: All channels closed\n'):
        errlines = list()

    if is_debug('SYSCMD'):
        print('Checking for' if fail_on_error else 'Ignoring', 'errors')
    if fail_on_error and (returncode or (not ignore_stderr and errlines)):
        bad_cmd_str = 'not recognized as an internal or external command' if WIN32 else 'command not found'
        err_type = CMDError.CMD_NOT_FOUND if (bad_cmd_str in ''.join(errlines)) else CMDError.CMD_ERROR
        raise CMDError(err_type, cmd=cmd_str, returncode=returncode, errlines=errlines, outlines=outlines)

    if errlines and append_stderr:
        outlines += errlines
    return flatten_string_list(outlines) if flatten_output else outlines


# Implement standard directory stack on chdir
_DIRECTORY_STACK = list()


def pushd(dirname: PathName, /) -> PathName:
    """Implements the push function for a directory stack.

    Args:
        dirname: The directory to which to change.

    Returns:
        The value of the directory pushed to the stack.
    """
    global _DIRECTORY_STACK  # pylint: disable=global-statement
    cwd = Path.cwd()
    chdir(dirname)
    _DIRECTORY_STACK.append(cwd)
    return cwd


def popd() -> Union[int, PathName]:
    """Implements the pop function for a directory stack.

    Args:
        None.

    Returns:
        The value of the directory removed from the stack.

    Raises:
        IndexError: If the stack is empty.
    """
    global _DIRECTORY_STACK  # pylint: disable=global-statement
    try:
        dirname = _DIRECTORY_STACK.pop()
    except IndexError:
        return 0
    chdir(dirname)
    return dirname

# cSpell:ignore chgrp geteuid getpwnam IRGRP IROTH IRWXG IXOTH lockf NBLCK nobanner psexec pylance syscmd unlck ungrouped
