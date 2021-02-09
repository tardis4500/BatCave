"""This module provides a generic interface for local and remote server paths."""

# Import standard modules
from os import walk
from pathlib import Path, PurePosixPath, PureWindowsPath, WindowsPath
from string import Template
from shutil import copy
from typing import cast, Iterator, List, Optional, Tuple, Union, TYPE_CHECKING

# Import internal modules
from .platarch import OsType
from .sysutil import rmpath, syscmd, CMDError
from .lang import is_debug, BatCaveError, BatCaveException, CommandResult, PathName, WIN32
if TYPE_CHECKING:
    from .servermgr import Server


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
    DEFAULT_REMOTE_COPY_ARGS = {OsType.windows: ['/MIR', '/MT', '/R:0', '/NFL', '/NDL', '/NP', '/NJH', '/NJS'],
                                OsType.linux: ['-r', '-batch']}
    DEFAULT_REMOTE_COPY_COMMAND = {OsType.windows: 'robocopy', OsType.linux: 'pscp' if WIN32 else 'scp'}

    def __init__(self, server: 'Server', the_path: PathName, /):
        """
        Args:
            server: The server for which the file path is a reference.
            the_path: The file path on the server.

        Attributes:
            local: The .
            _raw_path: The value of the the_path argument.
            _server: The value of the server argument.
            win_to_win: .
        """
        self._server = server
        self._raw_path = the_path

    def __str__(self):
        return str(self.remote)

    def __truediv__(self, other: str):
        return ServerPath(self.server, self.local / other)

    is_win = property(lambda s: s._server.os_type == OsType.windows, doc='A read-only property which returns True if the path is on a Windows server.')
    local = property(lambda s: s.path_type(s._raw_path), doc='A read-only property which returns the value of the the_path argument when referenced locally on the server.')
    parent = property(lambda s: ServerPath(s.server, s.local.parent), doc='A read-only property which returns the parent of the path.')
    path_type = property(lambda s: PureWindowsPath if s.is_win else PurePosixPath, doc='A read-only property which returns the path type.')
    server = property(lambda s: s._server, doc='A read-only property which returns the owning server of the path.')
    win_to_win = property(lambda s: WIN32 and s.is_win, doc='A read-only property which returns True if the both the local and remote systems are Windows servers.')

    @property
    def remote(self) -> PathName:
        """A read-only property which returns the name of this remote server which hosts the path."""
        if self.server.is_local:
            return self.local
        if self.win_to_win:
            return WindowsPath(f'//{self.server.fqdn}/{self.local}'.replace(':', '$'))
        return f'{self.server.fqdn}:{self.local}'

    def copy(self, sp_dest: 'ServerPath', /, remote_cp_command: Optional[str] = None, remote_cp_args: Optional[List[str]] = None) -> CommandResult:
        """Implementation of shutil.copy() adding remote server support.

        Args:
            sp_dest: The destination of the copy.
            remote_cp_command (optional, default=None): If not None, the command to use if the path is remote other than the default.
            remote_cp_args (optional, default=None): If not None, the arguments to use if the path is remote other than the default.

        Returns:
            The result of the copy.

        Raises:
            ServerPathError.REMOTE_COPY_SPACE_ERROR: If the remote destination is out of space.
        """
        if self.win_to_win and WindowsPath(self.remote).is_dir():
            remote_cp_command = self.DEFAULT_REMOTE_COPY_COMMAND[OsType.windows] if (remote_cp_command is None) else remote_cp_command
            remote_cp_args = self.DEFAULT_REMOTE_COPY_ARGS[OsType.windows] if (remote_cp_args is None) else remote_cp_args

            dest: PathName
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
                if remote_cp_command != self.DEFAULT_REMOTE_COPY_COMMAND[OsType.windows]:
                    raise
                if 'returncode' in err.vars:
                    if err.vars['returncode'] in (1, 2, 3):
                        return ''
                    if err.vars['returncode'] in (8, 9):
                        raise ServerPathError(ServerPathError.REMOTE_COPY_SPACE_ERROR, dest=sp_dest) from err
                raise
        elif sp_dest.server.os_type == OsType.linux:
            remote_cp_command = self.DEFAULT_REMOTE_COPY_COMMAND[OsType.linux] if (remote_cp_command is None) else remote_cp_command
            remote_cp_args = self.DEFAULT_REMOTE_COPY_ARGS[OsType.linux] if (remote_cp_args is None) else remote_cp_args
            return syscmd(remote_cp_command, *remote_cp_args, self.local, sp_dest.remote)

        # if you get here it is a file copy from Windows to Windows, just use shutil
        return copy(self.remote, sp_dest.remote)

    def exists(self) -> bool:
        """Implementation of pathlib.Path.exists() adding remote server support.

        Returns:
            True if this path exists, False otherwise.
        """
        if self.server.is_local:
            if is_debug('SERVERPATH'):
                print(f'Testing local path: {self.local}')
            return Path(self.local).exists()
        if self.win_to_win:
            if is_debug('SERVERPATH'):
                print(f'Testing remote path: {self.remote}')
            return cast(Path, self.remote).exists()
        try:
            if is_debug('SERVERPATH'):
                print(f'Testing {self.server} remote path: {self.remote}')
            self.server.run_command('dir' if self.is_win else 'ls', self.local)
            return True
        except CMDError as err:
            if err.vars['errlines'][0].startswith('ls: cannot access'):
                return False
            raise

    def iterdir(self) -> Union[CommandResult, List[Path]]:
        """Implementation of pathlib.Path.iterdir() adding remote server support.

        Returns:
            The contents of this directory path.
        """
        if self.server.is_local:
            return [i for i in Path(self.local).iterdir()]  # pylint: disable=unnecessary-comprehension
        if self.win_to_win:
            return [i for i in cast(Path, self.remote).iterdir()]  # pylint: disable=unnecessary-comprehension
        return self.server.run_command('dir' if self.is_win else 'ls', self.local)

    def mkdir(self, mode: int = 0o777, /, *, parents: bool = False, exist_ok: bool = False) -> None:
        """Implementation of pathlib.Path.mkdir() adding remote server support.

        Args:
            mode (optional, default=0o777): The access mode of the created directory.
            parents (optional, default=False): If True, also create intermediate directories.
            exist_ok (optional, default=False): If True, do not throw an exception if the path already exists.

        Returns:
            Nothing.
        """
        if self.server.is_local:
            Path(self.local).mkdir(mode, parents, exist_ok)
        if self.win_to_win:
            cast(Path, self.remote).mkdir(mode, parents, exist_ok)
        cmd: List[PathName] = ['mkdir']
        if parents and not self.is_win:
            cmd.append('-p')
        cmd.append(self.local)
        self.server.run_command(*cmd)

    def rename(self, new: str, /) -> Union[CommandResult, PathName]:
        """Implementation of pathlib.Path.rename() adding remote server support.

        Args:
            new: The new path name.

        Returns:
            The result of the rename.
        """
        if self.server.is_local:
            Path(self.local).rename(new)
            return Path(new)  # TODO: In 3.8, the rename will return the correct value.
        if self.win_to_win:
            cast(Path, self.remote).rename(new)
            return Path(new)  # TODO: In 3.8, the rename will return the correct value.
        return self.server.run_command('ren' if self.is_win else 'mv', self.local, new)

    def rmdir(self, remote_rm_command: Optional[List[PathName]] = None, *, recursive: bool = False) -> None:
        """Implementation of pathlib.Path.rmdir() adding remote server support.

        Args:
            remote_rm_command (optional, default=None): If not None, the command to use if the path is remote other than the default.
            recursive (optional, default=False): If True, also remove all subdirectories.

        Returns:
            Nothing.
        """
        if remote_rm_command is None:
            remote_rm_command = ['RD', '/Q'] if self.is_win else ['rm', '-f']

        if not recursive:
            if self.server.is_local:
                Path(self.local).rmdir()
            if self.win_to_win:
                cast(Path, self.remote).rmdir()
            remote_rm_command.append(self.local)
            self.server.run_command(*remote_rm_command, use_shell=True)

        if self.server.is_local:
            rmpath(self.local)
        if self.win_to_win:
            rmpath(self.remote)
        remote_rm_command += ['/S' if self.is_win else '-r', self.local]
        self.server.run_command(*remote_rm_command, use_shell=True)

    def walk(self) -> Iterator[Tuple[str, List[str], List[str]]]:
        """Implementation of os.walk() adding remote server support.

        Returns:
            The result of the walk.

        raises:
            ServerPathError.INVALID_OPERATION: If the command is not supported on the target path.
        """
        if self.server.is_local:
            return walk(self.local)
        if self.win_to_win:
            return walk(self.remote)
        raise ServerPathError(ServerPathError.INVALID_OPERATION)

# cSpell:ignore syscmd
