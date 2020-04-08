"""This module provides a generic interface for local and remote server paths."""

# Import standard modules
from os import walk
from pathlib import Path, PurePosixPath, PureWindowsPath, WindowsPath
from string import Template
from shutil import copy

# Import internal modules
from .servermgr import Server
from .sysutil import rmpath, syscmd, CMDError
from .lang import is_debug, BatCaveError, BatCaveException, WIN32


class ServerPathError(BatCaveException):
    """ServerPath Exceptions.

    Attributes:
        INVALID_OPERATION: The specified server type does not support the requested operation.
        REMOTE_COPY_SPACE_ERROR: The remote server did not have enough disk space for the copy.
    """
    INVALID_OPERATION = BatCaveError(1, 'This function is only supported for remote Windows servers from Windows servers')
    REMOTE_COPY_SPACE_ERROR = BatCaveError(2, Template('Error during robocopy, possible lack of disk space on $dest'))


class ServerPath:
    """Class to create a universal abstract interface for an OS directory such that remote and local paths can be managed with the same code.

    Attributes:
        DEFAULT_REMOTE_COPY_COMMAND: The default command to perform a remote copy based on the OS of the source.
        DEFAULT_REMOTE_COPY_ARGS: The default arguments used to perform a remote copy based on the OS of the source.
    """
    DEFAULT_REMOTE_COPY_COMMAND = {Server.OS_TYPES.windows: 'robocopy', Server.OS_TYPES.linux: 'pscp' if WIN32 else 'scp'}
    DEFAULT_REMOTE_COPY_ARGS = {Server.OS_TYPES.windows: ['/MIR', '/MT', '/R:0', '/NFL', '/NDL', '/NP', '/NJH', '/NJS'],
                                Server.OS_TYPES.linux: ['-r', '-batch']}

    def __init__(self, server, the_path):
        """
        Args:
            server: The server for with the file path is a reference.
            the_path: The file path on the server.

        Attributes:
            is_win: True if the server is a Windows server.
            local: The value of the the_path argument when referenced locally on the server.
            server: The value of the server argument.
            win_to_win: True if the both the local and remote systems are Windows servers.
        """
        self.server = server
        self.is_win = (self.server.os_type == Server.OS_TYPES.windows)
        path_type = PureWindowsPath if self.is_win else PurePosixPath
        self.local = path_type(the_path)
        self.win_to_win = WIN32 and self.is_win

    def __str__(self):
        return str(self.remote)

    def __truediv__(self, other):
        return ServerPath(self.server, self.local / other)

    @property
    def remote(self):
        """A read-only property which returns the name of this remote server which hosts the path."""
        if self.server.is_local:
            return self.local
        if self.win_to_win:
            return WindowsPath(f'//{self.server.fqdn}/{self.local}'.replace(':', '$'))
        return f'{self.server.fqdn}:{self.local}'
    parent = property(lambda s: ServerPath(s.server, s.local.parent), doc='A read-only property which returns the parent of the path.')

    def exists(self):
        'Implementation of pathlib.Path.exists() adding remote server support'
        if self.server.is_local:
            if is_debug('SERVERPATH'):
                print(f'Testing local path: {self.local}')
            return Path(self.local).exists()
        if self.win_to_win:
            if is_debug('SERVERPATH'):
                print(f'Testing remote path: {self.remote}')
            return self.remote.exists()
        try:
            if is_debug('SERVERPATH'):
                print(f'Testing {self.server} remote path: {self.remote}')
            self.server.run_command('dir' if self.is_win else 'ls', self.local)
            return True
        except CMDError as err:
            if err.vars['errlines'][0].startswith('ls: cannot access'):
                return False
            raise

    def iterdir(self):
        'Implementation of pathlib.Path.iterdir() adding remote server support'
        if self.server.is_local:
            return [i for i in Path(self.local).iterdir()]
        if self.win_to_win:
            return [i for i in self.remote.iterdir()]
        return self.server.run_command('dir' if self.is_win else 'ls', self.local)

    def mkdir(self, mode=0o777, parents=False, exist_ok=False):
        'Implementation of pathlib.Path.mkdir() adding remote server support'
        if self.server.is_local:
            return Path(self.local).mkdir(mode, parents, exist_ok)
        if self.win_to_win:
            return self.remote.mkdir(mode, parents, exist_ok)
        cmd = ['mkdir']
        if parents and not self.is_win:
            cmd.append('-p')
        cmd.append(self.local)
        return self.server.run_command(*cmd)

    def rename(self, new):
        'Implementation of pathlib.Path.rename() adding remote server support'
        if self.server.is_local:
            return Path(self.local).rename(new)
        if self.win_to_win:
            return self.remote.rename(new)
        return self.server.run_command('ren' if self.is_win else 'mv', self.local, new)

    def rmdir(self, remote_rm_command=None, recursive=False):
        'Implementation of pathlib.Path.rmdir() adding remote server support'
        if remote_rm_command is None:
            remote_rm_command = ['RD', '/Q'] if self.is_win else ['rm', '-f']

        if not recursive:
            if self.server.is_local:
                return Path(self.local).rmdir()
            if self.win_to_win:
                return self.remote.rmdir()
            remote_rm_command.append(self.local)
            return self.server.run_command(*remote_rm_command, use_shell=True)

        if self.server.is_local:
            return rmpath(self.local)
        if self.win_to_win:
            return rmpath(self.remote)
        remote_rm_command += ['/S' if self.is_win else '-r', self.local]
        return self.server.run_command(*remote_rm_command, use_shell=True)

    def copy(self, sp_dest, remote_cp_command=None, remote_cp_args=None):
        'Copy this server path to another, possibly remote, location'
        if self.win_to_win and WindowsPath(self.remote).is_dir():
            remote_cp_command = self.DEFAULT_REMOTE_COPY_COMMAND[Server.OS_TYPES.windows] if (remote_cp_command is None) else remote_cp_command
            remote_cp_args = self.DEFAULT_REMOTE_COPY_ARGS[Server.OS_TYPES.windows] if (remote_cp_args is None) else remote_cp_args

            if sp_dest.server.is_local and not self.server.is_local:
                use_server = sp_dest.server
                source = self.remote
                dest = sp_dest.local
            else:
                use_server = self.server
                source = self.local
                dest = sp_dest.local if (self.server == sp_dest.server) else sp_dest.remote

            try:
                return use_server.run_command(remote_cp_command, source, dest, *remote_cp_args, use_shell=True)
            except CMDError as err:
                if remote_cp_command != self.DEFAULT_REMOTE_COPY_COMMAND[Server.OS_TYPES.windows]:
                    raise
                if 'returncode' in err.vars:
                    if err.vars['returncode'] in (1, 2, 3):
                        return
                    if err.vars['returncode'] in (8, 9):
                        raise ServerPathError(ServerPathError.REMOTE_COPY_SPACE_ERROR, dest=sp_dest)
                raise
        elif sp_dest.server.os_type == Server.OS_TYPES.linux:
            remote_cp_command = self.DEFAULT_REMOTE_COPY_COMMAND[Server.OS_TYPES.linux] if (remote_cp_command is None) else remote_cp_command
            remote_cp_args = self.DEFAULT_REMOTE_COPY_ARGS[Server.OS_TYPES.linux] if (remote_cp_args is None) else remote_cp_args
            return syscmd(remote_cp_command, *remote_cp_args, self.local, sp_dest.remote)

        # if you get here it is a file copy from Windows to Windows, just use shutil
        return copy(self.remote, sp_dest.remote)

    def walk(self):
        'Implementation of os.walk() adding remote server support'
        if self.server.is_local:
            return walk(self.local)
        if self.win_to_win:
            return walk(self.remote)
        raise ServerPathError(ServerPathError.INVALID_OPERATION)

# cSpell:ignore syscmd
