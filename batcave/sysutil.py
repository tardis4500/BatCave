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

# Import internal modules
from .lang import flatten_string_list, is_debug, BatCaveError, BatCaveException, WIN32

if WIN32:
    import msvcrt
    PROG_FILES = {'32': Path(getenv('ProgramFiles(x86)', '')), '64': Path(getenv('ProgramFiles', ''))}
else:
    from fcntl import lockf, LOCK_EX, LOCK_NB, LOCK_UN  # pylint: disable=E0401
    from grp import getgrnam  # pylint: disable=E0401
    from os import geteuid  # pylint: disable=E0611,C0412
    from pwd import getpwnam  # pylint: disable=E0401
    PROG_FILES = {'32': Path('/usr/local')}
    PROG_FILES['64'] = PROG_FILES['32']

S_660 = S_IRUSR | S_IWUSR | S_IRGRP | S_IWGRP
S_664 = S_660 | S_IROTH
S_770 = S_IRWXU | S_IRWXG
S_775 = S_770 | S_IROTH | S_IXOTH


class CMDError(BatCaveException):
    'Exceptions which can be raised when running system commands'
    CMDTYPE_NOT_FOUND = BatCaveError(1, Template('Invalid Command type: $cmdtype'))
    CMD_NOT_FOUND = BatCaveError(2, Template('Command not found when running: $cmd'))
    CMD_ERROR = BatCaveError(3, '')
    UNSUPPORTED = BatCaveError(4, Template('$func is not supported for $context'))

    def __str__(self):
        if self._errobj.code == CMDError.CMD_ERROR.code:
            errlines = self.vars['errlines'] if self.vars['errlines'] else self.vars['outlines']
            return f"Error {self.vars['returncode']} when running: {self.vars['cmd']}\nError output:\n" + ''.join(errlines)
        return BatCaveException.__str__(self)


class LockError(BatCaveException):
    'Used to indicate an unsupported platform'
    NO_LOCK = BatCaveError(1, Template('unable to get lock'))


class OSUtilError(BatCaveException):
    """Exceptions when performing OS level tasks."""
    GROUP_EXISTS = BatCaveError(1, Template('The group already exists: $group'))
    USER_EXISTS = BatCaveError(2, Template('The user already exists: $user'))


class PlatformError(BatCaveException):
    'Used to indicate an unsupported platform'
    UNSUPPORTED = BatCaveError(1, Template('platform unsupported: $platform'))


LOCK_MODES = Enum('lock_modes', ('lock', 'unlock'))


class LockFile:
    'Lockfile interface'
    def __init__(self, filename, handle=None, cleanup=True):
        self._filename = Path(filename)
        self._cleanup = cleanup
        self._fh = handle if handle else open(filename, 'w')
        self._fd = self._fh.fileno()
        if WIN32:
            self._locker = msvcrt.locking
            self._lock = msvcrt.LK_NBLCK
            self._unlock = msvcrt.LK_UNLCK
        else:
            self._locker = lockf
            self._lock = LOCK_EX | LOCK_NB
            self._unlock = LOCK_UN
        self.action(LOCK_MODES.lock)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False

    def action(self, mode):
        'Performs the requested action on the loc file'
        lock_mode = self._lock if (mode == LOCK_MODES.lock) else self._unlock
        fail = False
        try:
            self._locker(self._fd, lock_mode, 1)
        except IOError as err:
            fail = True
            if err.errno not in (EACCES, EAGAIN):
                raise
        if fail:
            raise LockError(LockError.NO_LOCK)

    def close(self):
        'Close the lock file'
        self.action(LOCK_MODES.unlock)
        self._fh.close()
        if self._cleanup:
            self._filename.unlink()


class SysCmdRunner:
    'Improved interface to sysutil.syscmd()'
    def __init__(self, command, *default_args, logger=None, **default_keys):
        self.command = command
        self.writer = logger.loginfo if logger else print
        self.default_args = list(default_args)
        self.default_keys = default_keys

    def run(self, message, *args, **keys):
        'Run the defined command with the additional specified args and keys'
        use_args = self.default_args + list(args)
        use_keys = copy_object(self.default_keys)
        use_keys.update(keys)
        if message:
            self.writer(message)
        return syscmd(self.command, *use_args, **use_keys)


def create_group(group_name, exists_ok=True):
    """Create the system group at the OS level.

    Arguments:
        group_name: The group to create.
        exists_ok (optional, default=True): Do not raise an error if the group exists.

    Returns:
        Nothing.

    Raises:
        OSUtilError.GROUP_EXISTS: If the group exists and exists_ok is False.
        PlatformError.UNSUPPORTED: If this is a Windows platform.

    Todo:
        Implement for the Windows platform.
    """
    if WIN32:
        raise PlatformError(PlatformError.UNSUPPORTED, platform='Windows')
    try:
        getgrnam(group_name)
        if not exists_ok:
            raise OSUtilError(OSUtilError.GROUP_EXISTS, group=group_name)
    except KeyError:
        syscmd('groupadd', group_name)


def create_user(username, groups=tuple(), exists_ok=True):
    """Create the user account at the OS level.

    Arguments:
        username: The user account to create.
        exists_ok (optional, default=True): Do not raise an error if the user exists.

    Returns:
        Nothing.

    Raises:
        OSUtilError.USER_EXISTS: If the user exists and exists_ok is False.
        PlatformError.UNSUPPORTED: If this is a Windows platform.

    Todo:
        Implement for the Windows platform.
    """
    if WIN32:
        raise PlatformError(PlatformError.UNSUPPORTED, platform='Windows')
    create_group(username, exists_ok)
    try:
        getpwnam(username)
        if not exists_ok:
            raise OSUtilError(OSUtilError.USER_EXISTS, group=username)
    except KeyError:
        groups_args = (('-G',) + groups) if groups else tuple()
        syscmd('useradd', username, '-g', username, *groups_args)


def is_user_administrator():
    """Determines if the current user is an OS administrator.

    Arguments:
        None

    Returns:
        True if the user is an administrator, False otherwise.
    """
    if WIN32:
        try:
            syscmd('net', 'file')
        except CMDError as err:
            if 'Access is denied' in str(err):
                return False
            raise
    elif geteuid() != 0:
        return False
    return True


def chown(pathname, user=None, group=None, recursive=False):
    """Perform chown and chgrp together, recursively if requested.

    Arguments:
        user (optional, default=None): The user to set as the owner, if specified.
        group (optional, default=None): The group to set as the owner, if specified.
        recursive (optional, default=False): Also perform the user/owner settings recursively on all children.

    Returns:
        Nothing.
    """
    pathname = Path(pathname)
    os_chown(pathname, user, group)
    if recursive:
        for (root, dirs, files) in walk(pathname):
            for pathname in dirs + files:
                os_chown(Path(root, pathname), user, group)


def chmod(dirname, mode, recursive=False, files_only=False):
    """Perform chmod recursively if requested.

    Arguments:
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


def rmpath(path_name):
    """Remove the specified path object. If a directory, remove recursively.

    Arguments:
        path_name: The name of the path object to remove.

    Returns:
        The value returned by unlink() for a file object or rmtree_hard() for a path object.
    """
    path_name = Path(path_name)
    if path_name.is_dir():
        return rmtree_hard(path_name)
    else:
        return path_name.unlink()


def rmtree_hard(tree):
    """Recursively, remove a directory and try to avoid non-fatal errors.

    Arguments:
        tree: The directory tree to remove.

    Returns:
        The value returned by shutil.rmtree().
    """
    return rmtree(tree, onerror=_rmtree_onerror)


def _rmtree_onerror(caller, pathstr, excinfo):
    """The exception handler used by rmtree_hard to try to remove read-only attributes.

    Arguments:
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


# Implement standard directory stack on chdir
_DIRECTORY_STACK = list()


def pushd(dirname):
    """Implements the push function for a directory stack.

    Arguments:
        dirname: The directory to which to change.

    Returns:
        The value of the directory pushed to the stack.
    """
    global _DIRECTORY_STACK  # pylint: disable=global-statement
    cwd = Path.cwd()
    chdir(dirname)
    _DIRECTORY_STACK.append(cwd)
    return cwd


def popd():
    """Implements the pop function for a directory stack.

    Arguments:
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


def syscmd(command, *cmd_args, input_lines=None, show_stdout=False, ignore_stderr=False, append_stderr=False, fail_on_error=True, show_cmd=False, use_shell=False,
           flatten_output=False, remote=False, remote_is_windows=None, copy_for_remote=False, remote_auth=None, remote_powershell=False):
    """Wrapper to provide a better interface to subprocess.Popen().

    Arguments:
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
        CMDError.UNSUPPORTED:
            If PowerShell remoting is requested while trying to pass remote credentials,
            If remote execution requires the executable to be copied before execution and the local or remote system is Linux.
            If remote execution requires the executable to be copied before execution and PowerShell remoting is requested.
            If any remote options are provided but remote is False.
        CMDError.CMD_NOT_FOUND: If the requested command is not found.
        CMDError.CMD_ERROR: If fail_on_error is True, and the return code is non-zero, or there is output on stderr if ignore_stderr is True.
    """
    cmd_spec = [str(command)] + [str(c) for c in cmd_args]
    if remote:
        remote_is_windows = WIN32 if (remote_is_windows is None) else remote_is_windows
        if WIN32:
            if remote_is_windows:
                if remote_powershell:
                    if remote_auth or copy_for_remote:
                        raise CMDError(CMDError.UNSUPPORTED, func='remote_auth' if remote_auth else 'copy_for_remote', context='PowerShell')
                    remote_driver = ['powershell', '-NoLogo', '-NonInteractive', '-Command', 'Invoke-Command', '-ComputerName', remote, '-ScriptBlock']
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
                    raise CMDError(CMDError.UNSUPPORTED, func='copy_for_remote', context='Linux')
                remote_driver = ['plink', '-batch', '-v']
                if remote_auth:
                    remote_driver += ['-l', remote_auth[0], '-pw', remote_auth[1]]
                remote_driver += [remote]
        else:
            if copy_for_remote:
                raise CMDError(CMDError.UNSUPPORTED, func='copy_for_remote', context='Linux')
            remote_driver = ['ssh', '-t', '-t']
            if remote_auth:
                remote_driver += ['-u', remote_auth[0], '-p', remote_auth[1]]
            remote_driver += [remote]

        remote_cmd = cmd_spec
        if use_shell and remote_is_windows:
            remote_cmd = ['cmd', '/c'] + cmd_spec
        use_shell = False
        if remote_powershell:
            remote_cmd = ['{'] + remote_cmd + ['}']
        cmd_spec = remote_driver + remote_cmd
    elif remote_auth or copy_for_remote or remote_powershell or remote_is_windows:
        raise CMDError(CMDError.UNSUPPORTED, func='remote options', context='local servers')

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
        proc.stdin.writelines(input_lines)
        proc.stdin.close()

    if is_debug('SYSCMD'):
        print('Getting output lines')
    outlines = list()
    for line in iter(proc.stdout.readline, ''):
        if is_debug('SYSCMD'):
            print('Received output line:', line)
        outlines.append(line)
        if show_stdout:
            sys.stdout.write(line)

    if is_debug('SYSCMD'):
        print('Getting error lines')
    errlines = proc.stderr.readlines()
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

# cSpell:ignore chgrp geteuid getpwnam IRGRP IROTH IRWXG IXOTH lockf NBLCK nobanner psexec syscmd UNLCK
