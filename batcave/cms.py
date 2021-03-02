"""This module provides utilities for managing source code systems.

Attributes:
    P4_LOADED (str): If not empty then it is the string version of the Perforce API.
    GIT_LOADED (str): If not empty then it is the string version of the GitPython API.
    ClientType (Enum): The CMS providers supported by the Client class.
"""

# pylint: disable=too-many-lines,too-many-branches,too-many-public-methods,too-many-locals,too-many-statements,c-extension-no-member

# Import standard modules
import sys
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from glob import glob
from collections.abc import Callable
from getpass import getuser
from os import environ, getenv
from pathlib import Path
from platform import node
from random import randint
from re import compile as re_compile
from stat import S_IWUSR
from string import Template
from tempfile import mkdtemp
from typing import cast, Any, Dict, Generator, Iterable, List, Optional, Pattern, Sequence, Tuple, Union

# Import internal modules
from .fileutil import slurp
from .sysutil import popd, pushd, rmtree_hard
from .lang import is_debug, switch, BatCaveError, BatCaveException, PathName

if sys.platform == 'win32':
    from win32api import error as Win32Error, RegOpenKeyEx, RegQueryValueEx  # pylint: disable=import-error,no-name-in-module
    from win32con import HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE, KEY_READ  # pylint: disable=import-error,no-name-in-module
    from win32typing import PyHKEY  # pylint: disable=import-error,no-name-in-module

P4_LOADED: str
try:  # Load the Perforce API if available
    import P4  # type: ignore[missing-import]  # pylint: disable=import-error
except Exception:  # pylint: disable=broad-except
    P4_LOADED = ''
else:
    P4_LOADED = str(P4.P4().api_level)

import git  # noqa:E402  # pylint: disable=wrong-import-order,wrong-import-position
from git import RemoteProgress as git_remote_progress, Repo as GitRepo, Tree as GitTree  # type:ignore  # noqa:E402  # pylint: disable=wrong-import-order,wrong-import-position
GIT_LOADED = git.__version__ if hasattr(git, '__version__') else ''

CleanType = Enum('CleanType', ('none', 'members', 'all'))
ClientType = Enum('ClientType', ('file', 'git', 'perforce'))
InfoType = Enum('InfoType', ('archive',))
LabelType = Enum('LabelType', ('file', 'project'))
LineStyle = Enum('LineStyle', ('local', 'unix', 'mac', 'win', 'share', 'native', 'lf', 'crlf'))
ObjectType = Enum('ObjectType', ('changelist', 'string'))


class CMSError(BatCaveException):
    """CMS Exceptions.

    Attributes:
        CHANGELIST_NOT_EDITABLE: An attempt was made to edit a readonly changelist.
        CLIENT_DATA_INVALID: The root and mapping arguments cannot be specified if create=False.
        CLIENT_NAME_REQUIRED: A client name is required if create=False.
        CLIENT_NOT_FOUND: The specified client was not found.
        CONNECT_FAILED: Error connecting to the CMS system.
        CONNECTINFO_REQUIRED: Connection info is required for the specified CMS type.
        GIT_FAILURE: Gir returned an error.
        INVALID_OPERATION: The specified CMS type does not support the requested operation.
        INVALID_TYPE: An invalid CMS type was specified.
    """
    CHANGELIST_NOT_EDITABLE = BatCaveError(1, Template('Changelist $changelist not opened for edit'))
    CLIENT_DATA_INVALID = BatCaveError(2, Template('$data not valid if client exists'))
    CLIENT_NAME_REQUIRED = BatCaveError(3, 'Name required if client is not being created')
    CLIENT_NOT_FOUND = BatCaveError(4, Template('Client $name not found'))
    CONNECT_FAILED = BatCaveError(5, Template('Unable to connect to CMS server on $connectinfo'))
    CONNECTINFO_REQUIRED = BatCaveError(6, Template('Connectinfo required for CMS type ($ctype)'))
    GIT_FAILURE = BatCaveError(7, Template('Git Error:\n$msg'))
    INVALID_OPERATION = BatCaveError(8, Template('Invalid CMS type ($ctype) for this operation'))
    INVALID_TYPE = BatCaveError(9, Template('Invalid CMS type ($ctype). Must be one of: ' + str([t.name for t in ClientType])))


class Label:
    """Class to create a universal abstract interface for a CMS system label."""

    def __init__(self, name: str, label_type: LabelType, client: 'Client', /, *, description: str = '', selector: str = '', lock: bool = False):
        """
        Args:
            name: The label name.
            label_type: The label type.
            client: The CMS client used to interact with the label.
            description (optional, default=''): The description to attach to the label.
            selector (optional, default=''): The file selector to which to apply the label.
            lock (optional, default=False): If True the label will be locked against making changes.

        Attributes:
            _cloud: The value of the client argument.
            _name: The value of the name argument.
            _selector: The value of the selector argument.
            _type: The value of the label_type argument.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        self._client = client
        self._name = name
        self._type = label_type
        self._selector = selector
        self._label: Dict[str, str] = dict()
        self._refresh()
        changed = False
        if self._selector:
            for case in switch(self._client.type):
                if case(ClientType.perforce):
                    self._label['View'] = self._selector
                    changed = True
                    break
                if case():
                    raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)
        if description:
            for case in switch(self._client.type):
                if case(ClientType.perforce):
                    self._label['Description'] = description
                    changed = True
                    break
                if case():
                    raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)
        if changed:
            for case in switch(self._client.type):
                if case(ClientType.perforce):
                    self._save()
                    break
                if case():
                    raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)
        if lock:
            self.lock()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def __str__(self):
        for case in switch(self._client.type):
            if case(ClientType.perforce):
                return '\n'.join([f'{i}: {v}' for (i, v) in self._client._p4fetch('label', self._name).items()])
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)

    def _get_info(self, field: str, /) -> str:
        """Return the info for the specified field.

        Returns:
            The contents of the specified field.
        """
        return self._label[field]

    def _refresh(self) -> None:
        """Refresh the label information from the central repository.

        Returns:
            Nothing.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._client.type):
            if case(ClientType.perforce):
                self._label = self._client._p4fetch('label', self._name)  # pylint: disable=protected-access
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)

    def _save(self) -> None:
        """Save the label to the central repository.

        Returns:
            Nothing.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._client.type):
            if case(ClientType.perforce):
                self._client._p4save('label', self._label)  # pylint: disable=protected-access
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)

    description = property(lambda s: s._get_info('Description'), doc='A read-only property which returns the description of the label.')
    name = property(lambda s: s._name, doc='A read-only property which returns the name of the label.')
    root = property(lambda s: s._client.root, doc='A read-only property which returns the root for the label.')
    type = property(lambda s: s._client.type, doc='A read-only property which returns the CMS type.')

    def apply(self, *files: str, no_execute: bool = False) -> List[str]:
        """Apply the label to a list of files.

        Args:
            files: The list of files to which to apply the label.
            no_execute (optional, default=False): If True, run the command but don't commit the results.

        Returns:
            The result of the command from the CMS API.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._client.type):
            if case(ClientType.perforce):
                if self._type == LabelType.project:
                    raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)
                args: List[str] = ['labelsync', '-l', self._name]
                if no_execute:
                    args.append('-n')
                if files:
                    args += files
                return self._client._p4run(*args)  # pylint: disable=protected-access
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)

    def lock(self) -> None:
        """Set the label to read-only.

        Returns:
            Nothing.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        self._refresh()
        for case in switch(self._client.type):
            if case(ClientType.perforce):
                self._label['Options'] = self._label['Options'].replace('unlocked', '')
                self._label['Options'] = self._label['Options'].replace('locked', '')
                self._label['Options'] += 'locked'
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)
        self._save()

    def remove(self, *files: str, no_execute: bool = False) -> List[str]:
        """Remove the label from the list of files.

        Args:
            files: The list of files to which to apply the label.
            no_execute (optional, default=False): If True, run the command but don't commit the results.

        Returns:
            The result of the command from the CMS API.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)

    def unlock(self) -> None:
        """Set the label to read-write.

        Returns:
            Nothing.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        self._refresh()
        for case in switch(self._client.type):
            if case(ClientType.perforce):
                self._label['Options'] = self._label['Options'].replace('unlocked', '')
                self._label['Options'] = self._label['Options'].replace('locked', '')
                self._label['Options'] += 'unlocked'
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)
        self._save()


class Client:
    """Class to create a universal abstract interface for a CMS system client.

    Attributes:
        _DEFAULT_P4PORT: The default Perforce port.
        _INFO_DUMMY_CLIENT: The default name for a dummy client.
    """
    _DEFAULT_P4PORT = 'perforce:1666'
    _INFO_DUMMY_CLIENT = 'BatCave_info_dummy_client'

    def __init__(self, ctype: ClientType, /, name: str = '', connectinfo: str = '', *, user: str = '',
                 root: Optional[Path] = None, altroots: Optional[Sequence[str]] = None, mapping: Optional[List[str]] = None, hostless: bool = False,
                 changelist_options: Optional[str] = None, linestyle: Optional[LineStyle] = None, cleanup: Optional[bool] = None,
                 create: Optional[bool] = None, info: bool = False, password: Optional[str] = None, branch: Optional[str] = None):
        """
        Args:
            ctype: The client type.
            name: Required if create is True and info is False.
                If not required and not provided, it is derived based on the client type:
                    file: not applicable
                    git: the repo name
                    perforce: the client name
            connectinfo: Required for client type of 'file.'
                If not required and not provided, it is derived based on the client type:
                    file: required
                    git: The value of the GIT_WORK_TREE environment variable
                    perforce: The value of the P4PORT environment variable
            user (optional): The name of the CMS user.
                If not provided, it is derived based on the client type:
                    file: The value of the USER environment variable
                    git: The value of the USER environment variable
                    perforce: The value of the P4USER environment variable
            root (optional): If create is False, this value is not allowed.
                If create is True and it is not provided, a temporary root directory will be created.
            altroots (optional): If create is False, this value is ignored.
                Provides the altroot field for the Perforce client spec.
            mapping (optional): If create is False, this value is not allowed.
                Provides the mapping field for the Perforce client spec.
            hostless (optional): If create is False, this value is ignored.
                Provides the host field for the Perforce client spec.
            changelist_options (optional): If create is False, this value is ignored.
                Provides the SubmitOptions field for the Perforce client spec.
            linestyle (optional): If create is False, this value is ignored.
                Provides the LineEnd field for the Perforce client spec.
            cleanup (optional): If True, the client directory will be removed when the Client instance is disposed of.
                The default value depends on the CMS type and will be determined for an argument value of None.
                    file clients: False
                    Git clients if create argument is not specified: True
                    Others: The value of the create argument
            create (optional): If True, the client will be created.
                The default value depends on the CMS type and will be determined for an argument value of None.
                    If not a Git client and the info argument is true: False
                    Otherwise: True
            info (optional, default=False): This client will only be used to pull information from the central repository server.
            password (optional, default=None): This CMS system password used to access the client.
            branch (optional, default=None): This initial branch against which to create the client.

        Attributes:
            _connectinfo: The dervied value of the connectinfo argument.
            _cleanup: The dervied value of the cleanup argument.
            _client: A reference to the underlying API client.
            _mapping: The dervied value of the mapping argument.
            _name: The dervied value of the name argument.
            _type: The value of the ctype argument.
            _user: The dervied value of the user argument.

        Raises:
            CMSError.CLIENT_DATA_INVALID: If client creation info was provided by the create argument was False.
            CMSError.CLIENT_NAME_REQUIRED: If  a client name was not supplied when required.
            CMSError.CONNECT_FAILED: There was an error connecting to the CMS server.
            CMSError.CONNECTINFO_REQUIRED: If connection info was not supplied when required.
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        self._type = ctype
        self._validatetype()
        self._mapping = mapping
        self._connected = False
        self._client: Any = None

        if not connectinfo:
            for case in switch(self._type):
                if case(ClientType.file):
                    raise CMSError(CMSError.CONNECTINFO_REQUIRED, ctype=self._type.name)
                if case(ClientType.git):
                    connectinfo = getenv('GIT_WORK_TREE', '')
                    break
                if case(ClientType.perforce):
                    connectinfo = self.get_cms_sys_value('P4PORT')
                    break
                if case():
                    raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)
        self._connectinfo: str = connectinfo

        if not user:
            for case in switch(self._type):
                if case(ClientType.file, ClientType.git):
                    user = self.get_cms_sys_value('USER')
                    break
                if case(ClientType.perforce):
                    user = self.get_cms_sys_value('P4USER')
                    break
                if case():
                    raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)
        self._user: str = user

        if info:
            client_name = name if name else f'{self._INFO_DUMMY_CLIENT}_{randint(0, 1000)}'
        else:
            client_name = name

        create_client: bool
        if create is None:
            create_client = not (info and (self._type != ClientType.git))
        else:
            create_client = create

        self._cleanup: bool
        if cleanup is None:
            if self._type == ClientType.file:
                self._cleanup = False
            elif (self._type == ClientType.git) and (create_client is None):
                self._cleanup = True
            else:
                self._cleanup = create_client
        else:
            self._cleanup = cleanup

        self._tmpdir: Path
        if create_client:
            self._tmpdir = Path(mkdtemp(prefix='cms'))
            if not client_name:
                for case in switch(self._type):
                    if case(ClientType.file):
                        break
                    if case(ClientType.git, ClientType.perforce):
                        client_name = f'{self._user}_{self._tmpdir.name}'
                        break
                    if case():
                        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)
        elif not client_name:
            raise CMSError(CMSError.CLIENT_NAME_REQUIRED)
        self._name: str = client_name

        client_root: Optional[Path] = None
        if create_client:
            client_root = self._tmpdir if (root is None) else root
            if (self._mapping is None) and (self._type == ClientType.perforce) and info:
                self._mapping = [f'-//spec/... //{self.name}/...']
            if (linestyle is None) and (self._type == ClientType.perforce):
                linestyle = LineStyle.local
        elif root:
            raise CMSError(CMSError.CLIENT_DATA_INVALID, data='root')
        elif self._mapping:
            raise CMSError(CMSError.CLIENT_DATA_INVALID, data='mapping')

        for case in switch(self._type):
            if case(ClientType.file):
                self._connected = True
                break
            if case(ClientType.git):
                git_args: Dict[str, Union[int, str]] = dict()
                if branch:
                    git_args['branch'] = branch
                if info:
                    git_args['depth'] = 1
                self._client = GitRepo.clone_from(self._connectinfo, client_root, branch=(branch if branch else 'master')) if create_client else GitRepo(self._connectinfo)
                self._connected = True
                break
            if case(ClientType.perforce):
                self._client = self._p4run(P4.P4)
                self._client.port = self._connectinfo
                self._client.user = self._user
                self._client.client = str(self._name)
                if password:
                    self._client.password = password
                # self._client.api_level = P4API_LEVEL
                try:
                    self._p4run('connect')
                except P4.P4Exception as err:
                    if 'Connect to server failed' in err.value:
                        raise CMSError(CMSError.CONNECT_FAILED, connectinfo=self._connectinfo) from err
                    raise
                self._connected = True
                if create_client:
                    clientspec: Dict[str, Any] = self._p4fetch('client')
                    clientspec['Root'] = str(client_root)
                    clientspec['LineEnd'] = cast(LineStyle, linestyle).name
                    clientspec['SubmitOptions'] = changelist_options if changelist_options else 'revertunchanged'
                    if self._mapping:
                        clientspec['View'] = self._mapping
                    if branch:
                        clientspec['Stream'] = branch
                    if hostless:
                        clientspec['Host'] = ''
                    if altroots:
                        clientspec['AltRoots'] = altroots
                    self._p4save('client', clientspec)
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False

    def __str__(self):
        infostr: str = ''
        for case in switch(self._type):
            if case(ClientType.perforce):
                infostr = '\n'.join([f'{i}: {v}' for (i, v) in self._p4fetch('client').items()])
                break
            if case():
                infostr = self.name
        return f'{self.type} {infostr}'

    def _p4fetch(self, what: str, /, *args) -> Dict[str, Any]:
        """Run the Perforce fetch command.

        Args:
            what: The item to fetch.
            *args (optional): The arguments to pass to the command.

        Returns:
            The result of the command.
        """
        return self._p4run(f'fetch_{what}', *args)

    def _p4run(self, method: Any, /, *args) -> Any:
        """Run a Perforce command using the API if possible.

        Args:
            method: The command to run.
            *args (optional): The arguments to pass to the command.

        Returns:
            The result of the command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
            P4.P4Exception: If the command generates errors
            TypeError: If the requested command is invalid.
            AttributeError: If the requested command is not found.
        """
        if self._type != ClientType.perforce:
            raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)
        if is_debug('P4'):
            print('Executing P4 command:', method, args, self._connected)
        try:
            if isinstance(method, cast(type, Callable)):
                return cast(Callable, method)(*args)
            if hasattr(self._client, method) and isinstance(getattr(self._client, method), cast(type, Callable)):
                return getattr(self._client, method)(*args)
            if hasattr(self._client, f'run_{method}') and isinstance(getattr(self._client, f'run_{method}'), cast(type, Callable)):
                return getattr(self._client, f'run_{method}')(*args)
            if hasattr(self._client, method):
                raise TypeError(method)  # not callable
            raise AttributeError(f"'{type(self)}' object has no attribute '{method}'")
        except P4.P4Exception:
            raise
        except Exception as err:  # pylint: disable=broad-except
            if self._client.errors:
                raise P4.P4Exception('\n'.join(self._client.errors)) from err
            raise

    def _p4save(self, what: str, /, *args) -> List[str]:
        """Run the Perforce save command.

        Args:
            what: The item to save.
            *args (optional): The arguments to pass to the command.

        Returns:
            The result of the command.
        """
        return self._p4run(f'save_{what}', *args)

    def _validatetype(self) -> None:
        """Determine if the specified CMS type is valid.

        Returns:
            Nothing.
        """
        validatetype(self._type)

    name = property(lambda s: s._name, doc='A read-only property which returns the name of the client.')
    server_name = property(lambda s: s.get_server_connection()[0])
    type = property(lambda s: s._type, doc='A read-only property which returns the CMS type.')

    @property
    def branches(self) -> Any:
        """A read-only property which returns the client branch list."""
        for case in switch(self._type):
            if case(ClientType.git):
                return self._client.heads + self._client.remotes.origin.refs
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    @property
    def cms_info(self) -> str:
        """A read-only property which returns the CMS info."""
        for case in switch(self._type):
            if case(ClientType.file):
                return 'CMS type is: file'
            if case(ClientType.git):
                return self._client.git.config('-l')
            if case(ClientType.perforce):
                return '\n'.join([f'{i}: {v}' for (i, v) in self._p4run('info')[0].items()] + [f'server_level={self._client.server_level}', f'api_level={self._client.api_level}'])
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    @property
    def mapping(self) -> List[str]:
        """A read-write property which returns and sets the client mapping."""
        for case in switch(self._type):
            if case(ClientType.perforce):
                return cast(List[str], self._p4fetch('client')['View'])
        return cast(List[str], self._mapping)

    @mapping.setter
    def mapping(self, newmap: List[str], /) -> None:
        for case in switch(self._type):
            if case(ClientType.perforce):
                self._mapping = newmap
                client_spec = self._p4fetch('client')
                client_spec['View'] = newmap
                self._p4save('client', client_spec)
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    @property
    def root(self) -> Path:
        """A read-only property which returns the root of the client."""
        for case in switch(self._type):
            if case(ClientType.file):
                return Path(self._connectinfo)
            if case(ClientType.git):
                return Path(self._client.working_tree_dir)
            if case(ClientType.perforce):
                return Path(self._p4fetch('client')['Root'])
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    @property
    def streams(self) -> List[str]:
        """A read-only property which returns the client stream list."""
        for case in switch(self._type):
            if case(ClientType.perforce):
                return self._p4run('streams', ['-T', 'Stream'])
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def list(self) -> List[str]:
        """Get the local client files.

        Returns:
            The list of files on the current client.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.file):
                pushd(self.root)
                files: List[str] = glob('**')
                popd()
                return files
            if case(ClientType.git):
                return [f'{root}/{f}' for (root, _unused_dirs, files) in walk_git_tree(self._client.tree()) for f in files]
            if case(ClientType.perforce):
                return self._p4run('have')
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def add_files(self, *files: PathName, no_execute: bool = False) -> List[str]:
        """Add files to the client.

        Args:
            *files: The files to add.
            no_execute (optional, default=False): If True, run the command but don't commit the results.

        Returns:
            The result of the add files command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.file):
                break
            if case(ClientType.git):
                if not no_execute:
                    return self._client.index.add([str(f) for f in files])
                break
            if case(ClientType.perforce):
                args: List[str] = ['-n'] if no_execute else list()
                args += [str(f) for f in files]
                return self._p4run('add', *args)
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def add_label(self, tag_name: str, tag_message: str, /, *, exists_ok: bool = False, no_execute: bool = False) -> List[str]:
        """Add a label.

        Args:
            tag_name: The name of the label to add.
            tag_message: The message used as a tag annotation.
            exists_ok (optional, default=False): If True and the label already exists, delete the label before adding it.
            no_execute (optional, default=False): If True, run the command but don't revert the files.

        Returns:
            The list of label objects.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.git):
                args: Dict[str, Any] = dict()
                if not no_execute:
                    if exists_ok:
                        args['force'] = True
                    if tag_message:
                        args['message'] = tag_message
                    return [self._client.create_tag(tag_name, **args)]
                return list()
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def add_remote_ref(self, name: str, url: str, /, *, exists_ok: bool = False, no_execute: bool = False) -> List[str]:
        """Add a remote reference for a DVCS client.

        Args:
            name: The name of the remote reference to add.
            url: The URL of the remote reference to add.
            exists_ok (optional, default=False): If False, attempt to add the remote reference if it already exists, otherwise just return.
            no_execute (optional, default=False): If True, run the command but don't revert the files.

        Returns:
            The result of the add remote command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.git):
                if not no_execute:
                    if exists_ok and name in self._client.remotes:
                        self._client.delete_remote(name)
                    return self._client.create_remote(name, url)
                break
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def checkin_files(self, description: str, /, *files: str, all_branches: bool = False, remote: str = 'origin',
                      fail_on_empty: bool = False, no_execute: bool = False, **extra_args) -> List[str]:
        """Commit open files on the client.

        Args:
            description: A description of the changes.
            *files (optional): If provided, a subset of the files to commit, otherwise all will be submitted.
            all_branches (optional, default=False): If True, commit all branches, otherwise only the current branch.
            fail_on_empty (optional, default=False): If True, raise an error if there are no files to commit, otherwise just return.
            no_execute (optional, default=False): If True, run the command but don't commit the results.
            **extra_args (optional): Any extra API specific arguments or the commit.

        Returns:
            The result of the checkin command.

        Raises:
            CMSError.GIT_FAILURE: If there is a Git failure.
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.file):
                if not no_execute:
                    return self.unco_files(*files, no_execute=no_execute)
                return list()
            if case(ClientType.git):
                if not no_execute:
                    self._client.index.commit(description)
                    args: Dict[str, Union[bool, str]] = {'set_upstream': True, 'all': True} if all_branches else dict()
                    args.update(extra_args)
                    progress = git_remote_progress()
                    result = getattr(self._client.remotes, remote).push(progress=progress, **args)
                    if progress.error_lines:
                        raise CMSError(CMSError.GIT_FAILURE, msg=''.join(progress.error_lines).replace('error: ', ''))
                    return result
                return list()
            if case(ClientType.perforce):
                changelist: Dict[str, Any] = self._p4fetch('change')
                changelist['Description'] = description
                try:
                    return self._p4save('submit' if not no_execute else 'change', changelist)
                except P4.P4Exception as err:
                    if ('No files to submit.' not in str(err)) or fail_on_empty:
                        raise
                break
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def checkout_files(self, *files: str, no_execute: bool = False) -> List[str]:
        """Open files for editing on the client.

        Args:
            *files: The files to unlock.
            no_execute (optional, default=False): If True, run the command but don't checkout the files.

        Returns:
            The result of the checkout command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.file):
                for file_name in files:
                    file_path: Path = self.root / file_name
                    if not no_execute:
                        file_path.chmod(file_path.stat().st_mode | S_IWUSR)
                return list()
            if case(ClientType.git):
                if not no_execute:
                    return self._client.index.add([str(f) for f in files])
                return list()
            if case(ClientType.perforce):
                args: List[str] = ['-n'] if no_execute else list()
                args += files
                return self._p4run('edit', *args)
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def chmod_files(self, *files: str, mode: str, no_execute: bool = False) -> List[str]:
        """Perform a chmod of the files.

        Args:
            *files: The files to chmod.
            mode: The new mode to apply.
            no_execute (optional, default=False): If True, run the command but don't commit the results.

        Returns:
            The result of the chmod command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.git):
                for cms_file in files:
                    if not no_execute:
                        return self._client.git.update_index(f'--chmod={mode}', cms_file)
                return list()
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def close(self) -> None:
        """Close any persistent connections to the CMS system.

        Returns:
            Nothing.
        """
        if self._connected and self._type == ClientType.git:
            self._client.__del__()
            self._connected = False
        if self._cleanup:
            self.remove(CleanType.all)
            if self._tmpdir and self._tmpdir.exists() and (self._tmpdir != self.root):
                rmtree_hard(self._tmpdir)
        if self._connected and self._type == ClientType.perforce:
            self._p4run('disconnect')
            self._connected = False

    def create_branch(self, name: str, /, *, branch_from: str = '', repo: str = '',
                      branch_type: str = '', options: Optional[Dict[str, str]] = None, no_execute: bool = False) -> List[str]:
        """Create the specified branch.

        Args:
            name: The name of the branch to create.
            branch_from (optional, default=None): If None, use the current branch, otherwise use the branch specified.
            repo (optional, default=''): If None, use the current repo, otherwise use the repo specified.
            branch_type (optional, default=''): If None, use the default branch type, otherwise use the branch type specified.
            options (optional, default=''): Any API specific options to use when creating the branch.
            no_execute (optional, default=False): If True, run the command but don't revert the files.

        Returns:
            The result of the branch create command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.perforce):
                if branch_type.startswith('stream'):
                    (branch_type, stream_type) = branch_type.split(':')
                    streamspec: Dict[str, Any] = self._p4fetch(branch_type, f'//{repo}/{name}')
                    streamspec['Type'] = stream_type
                    if branch_from:
                        streamspec['Parent'] = f'//{repo}/{branch_from}'
                    if stream_type == 'virtual':
                        streamspec['Options'] = ' '.join(['%s%s' % ('no' if 'parent' in o else '', o) for o in streamspec['Options'].split()])
                    if options:
                        for (optname, optval) in options.items():
                            streamspec[optname] = optval
                    if not no_execute:
                        return self._p4save('stream', streamspec)
                return list()
            if case(ClientType.git):
                args: List[str] = [name]
                if branch_from:
                    args.append(branch_from)
                self._client.create_head(*args)
                getattr(self._client.heads, name).checkout()
                if no_execute:
                    return list()
                return self._client.git.push('origin', name, set_upstream=True)
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def create_repo(self, repository: str, /, *, repo_type: Optional[str] = None, no_execute: bool = False) -> List[str]:
        """Create the specified repository.

        Args:
            repository: The name of the repository to create.
            repo_type (optional, default=None): If None, use the default repository type, otherwise use the type specified.
            no_execute (optional, default=False): If True, run the command but don't revert the files.

        Returns:
            The result of the repository creation command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.perforce):
                depotspec: Dict[str, Any] = self._p4fetch('depot', repository)
                if repo_type:
                    depotspec['Type'] = repo_type
                if no_execute:
                    return list()
                return self._p4save('depot', depotspec)
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def find(self, file_regex: str = '', /) -> List[str]:
        """Search for files on the current client.

        Args:
            files_regex (optional, default=''): The regular expression to use to search for files.

        Returns:
            The list of files that were found.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.file, ClientType.git):
                regex: Pattern = re_compile(file_regex)
                return [f for f in self.list() if regex.search(f)]
            if case(ClientType.perforce):
                try:
                    return self._p4run('files', file_regex)
                except P4.P4Exception as err:
                    if 'no such file' not in str(err):
                        raise
                return list()
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def get_changelist(self, name: str, /, *files: str, edit: bool = False) -> 'ChangeList':
        """Get a ChangeList objects for the specified changelist.

        Args:
            name: The name of the changelist.
            *files (optional): Restrict the list based on the list of files.
            edit (optional, default=False): If True, return and editable ChangeList object.

        Returns:
            The changelist object.
        """
        if edit:
            return ChangeList(self, name, editable=True)
        return self.get_changelists(name, forfiles=files)[0]

    def get_changelists(self, *names: Optional[Iterable[str]], forfiles: Optional[Iterable[str]] = tuple(), count: Optional[int] = None) -> List['ChangeList']:
        """Get a list of changelist objects for the specified changelist names.

        Args:
            *names: The list of changelist names.
            forfiles (optional, default=None): If not none, restrict the list based on the list of files.
            count (optional, default=None): If not None, the number of objects to return, otherwise return all.

        Returns:
            The changelist objects.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.perforce):
                arglist: List[str] = ['-l', '-s', 'submitted']
                changelist_names: List[str]
                if not names:
                    if count is not None:
                        arglist += ['-m', str(count)]
                    if forfiles:
                        arglist += forfiles
                    changelist_names = self._p4run('changes', *arglist)
                else:
                    changelist_names = [str(n) for n in names]
                return [ChangeList(self, c) for c in changelist_names]
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def get_clients(self, *args) -> List['Client']:
        """Get the clients in the CMS system.

        Args:
            *args (optional): Any API specific arguments to use.

        Returns:
            The list of clients.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.perforce):
                return self._p4run('clients', *args)
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def get_cms_sys_value(self, var: str, /) -> str:
        """Get a configuration value from the CMS system.

        Args:
            var: The configuration value to return.

        Returns:
            The value of the specified configuration item.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        if var in environ:
            return environ[var]
        for case in switch(self._type):  # pylint: disable=too-many-nested-blocks
            if case(ClientType.perforce):
                if sys.platform == 'win32':
                    for key in (HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE):
                        try:
                            keyhandle: PyHKEY = RegOpenKeyEx(key, r'Software\perforce\environment', 0, KEY_READ)
                            if RegQueryValueEx(keyhandle, var):
                                return RegQueryValueEx(keyhandle, var)[0]
                        except Win32Error as err:
                            if err.winerror != 2:  # ERROR_FILE_NOT_FOUND
                                raise
                for inner_case in switch(var):
                    if inner_case('P4PORT'):
                        return self._DEFAULT_P4PORT
                    if inner_case('P4USER'):
                        username: str = getuser().lower()
                        if username:
                            return username
                raise P4.P4Exception('unable to determine ' + var)
        if var == 'USER':
            if getuser():
                return getuser()
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def get_file(self, filename: str, /, *, checkout: bool = False) -> List[str]:
        """Get the contents of the specified file.

        Args:
            filename: The name of the file for which to return the contents.
            checkout (optional, default=False): If True, update and checkout the files before retrieving the contents.

        Returns:
            The contents of the specified file.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        if checkout:
            self.update(filename)
            self.checkout_files(filename)
            return slurp(self.get_filepath(filename))

        for case in switch(self._type):
            if case(ClientType.file, ClientType.git):
                return slurp(self.root / filename)
            if case(ClientType.perforce):
                return self._p4run('print', filename)[1:]
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def get_filepath(self, file_name: str, /) -> Path:
        """Get the full local OS path to the file.

        Args:
            file_name: The name of the file for which to return the path.

        Returns:
            The full local OS path to the file.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.file, ClientType.git):
                return self.root / file_name
            if case(ClientType.perforce):
                file_info: List[Dict[str, Any]] = self._p4run('fstat', file_name)
                return file_info[0]['clientFile']
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def get_labels(self, *args) -> List[Label]:
        """Get the labels in the CMS system.

        Args:
            *args (optional): Any API specific arguments to use.

        Returns:
            The list of labels.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.perforce):
                return self._p4run('labels', *args)
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def get_max_changelist(self, label: str = '', /) -> int:
        """Get the highest changelist number.

        Args:
            label (optional, default=''): If not empty, limit the number by the specified label.

        Returns:
            The highest changelist number.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.perforce):
                label_name: str = f'@{label}' if label else label
                return self._p4run('changes', '-m1', f'//...{label_name}')[0]['change']
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def get_repos(self, *args) -> List[str]:
        """Get the repositories in the CMS system.

        Args:
            *args (optional): Any API specific arguments to use.

        Returns:
            The list of repositories.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.perforce):
                return self._p4run('depots', *args)
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def get_server_connection(self) -> str:
        """Get the name of the CMS server.

        Returns:
            The name of the CMS server.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.file):
                return 'CMS type: file'
            if case(ClientType.perforce):
                return self._connectinfo
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def get_user_record(self, username: str, /) -> Dict[str, str]:
        """Get the CMS system information about the specified username.

        Args:
            username: The user for which to find the information.

        Returns:
            The information about the specified user.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.perforce):
                return self._p4fetch('user', username)
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def get_users(self) -> List[str]:
        """Get the list of users.

        Returns:
            The list of users.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.perforce):
                return self._p4run('users')
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def integrate(self, source: str, target: str, /, *, no_execute: bool = False) -> List[str]:
        """Integrate branches.

        Args:
            source: The source branch of the integration.
            target: The target branch of the integration.
            no_execute (optional, default=False): If True, run the command but don't commit the results.

        Returns:
            The result of the integration command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.perforce):
                args: List[str] = ['integrate', source, target]
                if no_execute:
                    args.append('-n')
                return self._p4run(*args)
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def lock_files(self, *files: str, no_execute: bool = False) -> List[str]:
        """Place a lock on the files to prevent edits by other users.

        Args:
            *files: The files to lock.
            no_execute (optional, default=False): If True, run the command but don't commit the results.

        Returns:
            The result of the lock files command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.perforce):
                args: List[str] = ['-n'] if no_execute else list()
                args += files
                return self._p4run('lock', *args)
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def merge(self, source_branch: str, /, *, checkin: bool = True, checkin_message: Optional[str] = None, no_execute: bool = False) -> List[str]:
        """Perform a merge from the specified branch.

        Args:
            source_branch: The source branch to use for the merge.
            checkin (optional, default=True): If True, checkin the changed files after the merge.
            checkin_message (optional, default=None): If None, generate a message for the merge.
            no_execute (optional, default=False): If True, run the command but don't revert the files.

        Returns:
            The result of the merge command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.git):
                branch_owner: str = self._client.heads if (f'refs/heads/{source_branch}' in [str(b) for b in self.branches]) else self._client.remotes.origin.refs
                result: List[str] = self._client.git.merge(getattr(branch_owner, source_branch), '--no-ff')
                if checkin:
                    final_message: str = checkin_message if (checkin_message is not None) else f'Merging code from {source_branch} to {self._client.active_branch}'
                    self.checkin_files(final_message, all_branches=True, no_execute=no_execute)
                return result
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def populate_branch(self, source: str, target: str, /, *, no_execute: bool = False) -> List[str]:
        """Populate the target branch from the source.

        Args:
            source: The name of the source branch to use.
            target: The name of the target branch to use.
            no_execute (optional, default=False): If True, run the command but don't revert the files.

        Returns:
            The result of the populate command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.perforce):
                if not no_execute:
                    return self._p4run('populate', [source, target])
                return list()
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def reconcile(self, *files: str, no_execute: bool = False) -> List[str]:
        """Reconcile the workspace against the server and creates a changelist for the changes.

        Args:
            *files (optional): The files to reconcile, otherwise all will be reconciled.
            no_execute (optional, default=False): If True, run the command but don't commit the results.

        Returns:
            The result of the reconcile command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        use_files: List[str] = list(files) if files else ['//...']
        for case in switch(self._type):
            if case(ClientType.perforce):
                args: List[str] = ['reconcile']
                if no_execute:
                    args.append('-n')
                if use_files:
                    args += use_files
                return self._p4run(*args)
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def remove(self, clean: CleanType = CleanType.none, /) -> List[str]:
        """Delete the client object from the CMS system.

        Args:
            clean (optional, default=CleanType.none): Specifies the amount of cleaning of the local file system.

        Returns:
            The result of the client removal command.

        Raises:
            CMSError.CLIENT_NOT_FOUND: If the client is not found.
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        client_root: Path = self.root
        results: List[str] = list()
        for case in switch(self._type):
            if case(ClientType.perforce):
                if clean in (CleanType.members, CleanType.all):
                    try:
                        results = self._p4run('sync', '//...#none')
                    except P4.P4Exception as err:
                        if ('file(s) not in client view' not in str(err)) and ('file(s) up-to-date' not in str(err)) and ("Can't clobber writable file" not in str(err)):
                            raise
                try:
                    results += self._p4run('client', '-d', '-f', self._name)
                except P4.P4Exception as err:
                    if "doesn't exist" in str(err):
                        raise CMSError(CMSError.CLIENT_NOT_FOUND, name=self._name) from err
                    results += self._p4run('client', '-d', self._name)
                break
            if case(ClientType.git):
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)
        if (clean == CleanType.all) and client_root and client_root.is_dir():
            rmtree_hard(client_root)
        return results

    def remove_files(self, *files: str, no_execute: bool = False) -> List[str]:
        """Remove files from the client.

        Args:
            *files: The files to remove.
            no_execute (optional, default=False): If True, run the command but don't commit the results.

        Returns:
            The result of the remove files command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        result: List[str] = list()
        for case in switch(self._type):
            if case(ClientType.git):
                if not no_execute:
                    result = self._client.index.remove(files)
                # intentional fall-through to remove the file system file
            if case(ClientType.file):
                if not no_execute:
                    for filename in files:
                        (self.root / filename).unlink()
                return result
            if case(ClientType.perforce):
                args: List[str] = ['-n'] if no_execute else list()
                args += files
                return self._p4run('delete', *args)
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def rename_remote_ref(self, old_name: str, new_name: str, /, *, no_execute: bool = False) -> List[str]:
        """Rename a remote reference for a DVCS client.

        Args:
            old_name: The name of the remote reference to rename.
            new_name: The new name of the remote.
            no_execute (optional, default=False): If True, run the command but don't revert the files.

        Returns:
            The result of the rename command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.git):
                if not no_execute:
                    return self._client.remotes[old_name].rename(new_name)
                return list()
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def switch(self, branch: str, /) -> List[str]:
        """Switch to the specified branch.

        Args:
            branch: The branch to which to switch.

        Returns:
            The result of the switch command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.git):
                self._client.git.fetch('--all')
                if branch not in {b.name.replace('origin/', '') for b in self.branches}:
                    self.create_branch(branch)
                return self._client.git.checkout(branch)
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def unco_files(self, *files: str, unchanged_only: bool = False, no_execute: bool = False) -> List[str]:
        """Revert open files for editing on the client.

        Args:
            *files (optional): If provided, a subset of the files to revert, otherwise all will be reverted.
            unchanged_only (optional, default=False): If True, only revert unchanged files, otherwise all will be reverted.
            no_execute (optional, default=False): If True, run the command but don't revert the files.

        Returns:
            The result of the revert command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.file):
                for file_name in files:
                    file_path: Path = self.root / file_name
                    if not no_execute:
                        file_path.chmod(file_path.stat().st_mode & S_IWUSR)
                return list()
            if case(ClientType.git):
                if not no_execute:
                    return self._client.index.checkout(paths=files, force=True)
                return list()
            if case(ClientType.perforce):
                args: List[str] = ['-n'] if no_execute else list()
                if unchanged_only:
                    args.append('-a')
                args += files if files else ['//...']
                try:
                    return self._p4run('revert', *args)
                except P4.P4Exception as err:
                    if 'file(s) not opened on this client.' not in str(err):
                        raise
                return list()
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def unlock_files(self, *files: str, no_execute: bool = False) -> List[str]:
        """Remove a lock on the files to allow edits by other users.

        Args:
            *files: The files to unlock.
            no_execute (optional, default=False): If True, run the command but don't commit the results.

        Returns:
            The result of the unlock files command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.perforce):
                args: List[str] = ['-n'] if no_execute else list()
                args += files
                return self._p4run('unedit', *args)
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def update(self, *files: str, limiters: Optional[str] = None, force: bool = False, parallel: bool = False, no_execute: bool = False) -> List[str]:
        """Update the local client files.

        Args:
            *files (optional): The files to update, otherwise all will be updated.
            limiters (optional, default=None): Arguments to limit the updated files.
            force (optional, default=False): If True update files that are already up-to-date.
            parallel (optional, default=False): If True update files in parallel.
            no_execute (optional, default=False): If True, run the command but don't commit the results.

        Returns:
            The list of files that were updated if provided by the underlying API.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(ClientType.file):
                break
            if case(ClientType.git):
                info = self._client.remotes.origin.pull()[0]
                return info.note if info.note else info.ref
            if case(ClientType.perforce):
                args: List[str] = ['sync']
                if force:
                    args.append('-f')
                if no_execute:
                    args.append('-n')
                if parallel:
                    args += ['--parallel', 'thread=4,min=1,minsize=1']
                if limiters:
                    args += limiters
                if files:
                    args += files
                try:
                    return self._p4run(*args)
                except P4.P4Exception as err:
                    if ('file(s) up-to-date.' in str(err)) or ('File(s) up-to-date.' in str(err)):
                        return list()
                    raise
                return list()
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)


@dataclass(frozen=True)
class FileRevision:
    """This class describes information about a file revision.

        Attributes:
            filename: The name of the file.
            revision: The revision number for this revision.
            description: The description for this revision.
            author: The user that made this revision.
            labels: A list of labels on this revision.
    """
    filename: str
    revision: str
    author: str
    date: str
    labels: List[str]
    description: str

    def __str__(self):
        return f'{self.filename}#{self.revision} by {self.author} on {self.date}\nLabels: {self.labels}\nDescription: {self.description}\n'


@dataclass(frozen=True)
class FileChangeRecord:
    """This class describes information about a file change.

        Attributes:
            client: The CMS Client object where this file change record is located.
            filename: The name of the file.
            revision: The revision number for this revision.
            mod_type: The type of modification for the file.
            changelist: The changelist number for the change record.
    """
    client: Client
    filename: str
    revision: str
    type: str
    changelist: str

    def __str__(self):
        for case in switch(self.client.type):
            if case(ClientType.perforce):
                return f'{self.filename}#{self.revision} {self.type} {self.changelist}'
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self.client.type.name)

    fullname = property(lambda s: f'{s.filename}#{s.revision}', doc='A read-only property which returns the full name of the changed file.')


class ChangeList:
    """Class to create a universal abstract interface for a CMS changelist."""

    def __init__(self, client: Client, chg_list_id: Any = None, /, editable: Optional[bool] = None):
        """
        Args:
            client: The CMS Client object where this file change record is located.
            chg_list_id (optional, default=None): The unique ID for this changelist.
            editable (optional, default=not bool(chg_list_id)): If true, this changelist can be editted.

        Attributes:
            _changelist: A reference to the underlying API changelist.
            _client: The value of the client argument.
            _editable: The dervied value of the editable argument.
            _files: The list of files in the changelist.
            _id: The value of the chg_list_id argument.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        self._client = client
        self._files: Optional[List[FileChangeRecord]] = None
        self._id: str
        self._changelist: Dict[str, str]
        self._editable: bool = editable if (editable is not None) else not bool(id)
        for case in switch(client.type):
            if case(ClientType.perforce):
                if isinstance(id, (str, int)):
                    self._id = str(id)
                    if self._editable:
                        self._changelist = self._client._p4fetch('change', self._id)
                    else:
                        self._changelist = self._client._p4run('describe', '-s', self._id)[0]
                else:
                    self._changelist = chg_list_id if chg_list_id else self._client._p4fetch('change')
                    self._id = self._changelist['change']
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)

    def __str__(self):
        return 'Changelist ' + self.name

    name = property(lambda s: s._id, doc='A read-only property which returns the name of the change list.')

    @property
    def desc(self) -> str:
        """A read-write property which returns and sets the change list description."""
        for case in switch(self._client.type):
            if case(ClientType.perforce):
                return self._changelist['Description' if self._editable else 'desc']
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)

    @desc.setter
    def desc(self, newdesc: str, /) -> None:
        if not self._editable:
            raise CMSError(CMSError.CHANGELIST_NOT_EDITABLE, changelist=self._id)
        for case in switch(self._client.type):
            if case(ClientType.perforce):
                self._changelist['Description'] = newdesc
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)

    @property
    def files(self) -> List[FileChangeRecord]:
        """A read-only property which returns the list of files in the change list."""
        if self._files is None:
            desc: Dict[str, str] = self._client._p4run('describe', '-s', self.name)[0]  # pylint: disable=protected-access
            self._files = [FileChangeRecord(self._client, f, r, a, self.name)
                           for (f, r, a) in zip(desc['depotFile'], desc['rev'], desc['action'])]
        return self._files

    @property
    def time(self) -> datetime:
        """A read-write property which returns and sets the change list time."""
        for case in switch(self._client.type):
            if case(ClientType.perforce):
                if self._editable:
                    return datetime.strptime(self._changelist['Date'], '%Y/%m/%d %H:%M:%S')
                return datetime.fromtimestamp(int(self._changelist['time']))
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)

    @time.setter
    def time(self, newtime: Union[str, datetime], /) -> None:
        if not self._editable:
            raise CMSError(CMSError.CHANGELIST_NOT_EDITABLE, changelist=self._id)
        for case in switch(self._client.type):
            if case(ClientType.perforce):
                self._changelist['Date'] = newtime.strftime('%Y/%m/%d %H:%M:%S') if isinstance(newtime, datetime) else newtime
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)

    @property
    def user(self) -> str:
        """A read-write property which returns and sets the change list user."""
        for case in switch(self._client.type):
            if case(ClientType.perforce):
                return self._changelist['User' if self._editable else 'user']
        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)

    @user.setter
    def user(self, newuser: str, /) -> None:
        if not self._editable:
            raise CMSError(CMSError.CHANGELIST_NOT_EDITABLE, changelist=self._id)
        for case in switch(self._client.type):
            if case(ClientType.perforce):
                self._changelist['User'] = newuser
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)

    def store(self, /, *, no_execute: bool = False) -> None:
        """Save the ChangeList to the CMS server.

        Args:
            no_execute (optional, default=False): If True, run the command but don't commit the results.

        Returns:
            Nothing.
        """
        if not no_execute:
            self._client._p4save('change', self._changelist, '-f')  # pylint: disable=protected-access


def create_client_name(*, prefix: Optional[str] = None, suffix: Optional[str] = None, sep: str = '_', licenseplate: bool = False) -> str:
    """Automatically create a client name from the user and hostname.

    Attributes:
        prefix (optional, default=None): If not None, the prefix for the client.
        suffix (optional, default=None): If not None, the suffix for the client.
        sep (optional, default='_'): The separator for the different pieces of the name.
        licenseplate (optional, default=False): If not False, adds a random number to the end of the name.
            Will be appended after the suffix.

    Returns:
        Returns the client name.
    """
    parts: List[str] = [getuser(), node()]
    if prefix:
        parts.insert(0, prefix)
    if suffix:
        parts.append(suffix)
    if licenseplate:
        parts.append(str(randint(0, 1000)))
    return sep.join(parts)


def validatetype(ctype: ClientType, /) -> None:
    """Determine if the specified CMS type is valid.

    Args:
        ctype: The CMS type.

    Returns:
        Nothing.

    Raises
        CMSError.INVALID_TYPE: If the CMS type is not valid.
    """
    if ctype not in ClientType:
        raise CMSError(CMSError.INVALID_TYPE, ctype=ctype)


def walk_git_tree(tree: GitTree, /, *, parent: Optional[GitTree] = None) -> Generator[Tuple, Tuple, None]:
    """Walk the git tree similar to os.walk().

    Attributes:
        tree: The git tree to walk.
        parent (optional, default=None): Use a different parent than the root of the tree.

    Yields:
        Runs like an iterator which yields tuples of
            (the new parent, the tree names, the git blobs)
    """
    (tree_names, trees, blobs) = (list(), list(), list())
    for entry in tree:
        if isinstance(entry, GitTree):
            tree_names.append(entry.name)
            trees.append(entry)
        else:
            blobs.append(entry.name)

    new_parent: str = f'{parent}/{tree.name}' if parent else tree.name
    for subtree in trees:
        yield from walk_git_tree(subtree, parent=new_parent)

    yield new_parent, tree_names, blobs

# cSpell:ignore checkin unedit
