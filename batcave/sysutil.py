'OS-independent interface to system utilities'
# cSpell:ignore IRGRP, IROTH, IRWXG, IXOTH, lockf, NBLCK, nobanner, UNLCK

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
from .lang import flatten_string_list, is_debug, HALError, HALException, WIN32

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

S_664 = S_IRUSR | S_IWUSR | S_IRGRP | S_IWGRP | S_IROTH
S_775 = S_IRWXU | S_IRWXG | S_IROTH | S_IXOTH
S_660 = S_IRUSR | S_IWUSR | S_IRGRP | S_IWGRP
S_770 = S_IRWXU | S_IRWXG


class CMDError(HALException):
    'Exceptions which can be raised when running system commands'
    CMDTYPE_NOT_FOUND = HALError(1, Template('Invalid Command type: $cmdtype'))
    CMD_NOT_FOUND = HALError(2, Template('Command not found when running: $cmd'))
    CMD_ERROR = HALError(3, '')
    UNSUPPORTED = HALError(4, Template('$func is not supported for $context'))

    def __str__(self):
        if self._errobj.code == CMDError.CMD_ERROR.code:
            errlines = self.vars['errlines'] if self.vars['errlines'] else self.vars['outlines']
            return f"Error {self.vars['returncode']} when running: {self.vars['cmd']}\nError output:\n" + ''.join(errlines)
        return HALException.__str__(self)


class LockError(HALException):
    'Used to indicate an unsupported platform'
    NO_LOCK = HALError(1, Template('unable to get lock'))


class PlatformError(HALException):
    'Used to indicate an unsupported platform'
    UNSUPPORTED = HALError(1, Template('platform unsupported: $platform'))


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


def create_group(groupname):
    'Create a user group at the OS level'
    try:
        getgrnam(groupname)
    except KeyError:
        syscmd('groupadd', groupname)


def create_user(username, groups=tuple()):
    'Create a user at the OS level'
    create_group(username)
    try:
        getpwnam(username)
    except KeyError:
        groups_args = (('-G',) + groups) if groups else tuple()
        syscmd('useradd', username, '-g', username, *groups_args)


def is_user_administrator():
    'Determines if the current user is an OS administrator'
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
    'Recursive version of chown'
    pathname = Path(pathname)
    os_chown(pathname, user, group)
    if recursive:
        for (root, dirs, files) in walk(pathname):
            for pathname in dirs + files:
                os_chown(Path(root, pathname), user, group)


def chmod(dirname, mode, recursive=False, files_only=False):
    'Recursive version of chmod'
    dirname = Path(dirname)
    if not files_only:
        dirname.chmod(mode)
    if recursive:
        for (root, dirs, files) in walk(dirname):
            for pathname in (files if files_only else (dirs + files)):  # pylint: disable=C0325
                Path(root, pathname).chmod(mode)


# Remove a directory tree without failing on a write error
def rmpath(pathstr):
    'Recursively remove a directory'
    pathstr = Path(pathstr)
    if pathstr.is_dir():
        return rmtree_hard(pathstr)
    else:
        return pathstr.unlink()


def rmtree_hard(tree):
    'Handle errors when recursively removing a directory'
    return rmtree(tree, onerror=_rmtree_onerror)


def _rmtree_onerror(caller, pathstr, excinfo):
    pathstr = Path(pathstr)
    if caller not in (remove, unlink):
        print('Caller:', caller, file=sys.stderr)
        raise excinfo[0](excinfo[1])
    pathstr.chmod(S_IRWXU)
    pathstr.unlink()


# Implement standard directory stack on chdir
dirstack = list()  # pylint: disable=C0103


def pushd(dirname):
    'Add a directory to the global stack and cd to that directory'
    global dirstack  # pylint: disable=W0603,C0103
    cwd = Path.cwd()
    chdir(dirname)
    dirstack.append(cwd)
    return cwd


def popd():
    'Return to the top directory on the stack and remove it'
    global dirstack  # pylint: disable=W0603,C0103
    try:
        dirname = dirstack.pop()
    except IndexError:
        return 0
    chdir(dirname)
    return dirname


def syscmd(command, *cmd_args, input_lines=None, show_stdout=False, ignore_stderr=False, append_stderr=False, fail_on_error=True, show_cmd=False, use_shell=False,
           flatten_output=False, remote=False, remote_is_windows=None, copy_for_remote=False, remote_auth=None, remote_powershell=False):
    'Run a system command'
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
