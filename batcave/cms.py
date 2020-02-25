"""This module provides utilities for managing source code systems.

Attributes:
    P4_LOADED (bool/str): If not False then it is the string version of the Perforce API.
    GIT_LOADED (bool/str): If not False then it is the string version of the GitPython API.
    _CLIENT_TYPES (Enum): The CMS providers supported by the Client class.
"""

# pylint: disable=C0302,I1101

# Import standard modules
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

# Import internal modules
from .sysutil import popd, pushd, rmtree_hard
from .lang import is_debug, switch, BatCaveError, BatCaveException, WIN32

if WIN32:
    import win32api
    import win32con

try:  # Load the Perforce API if available
    import P4  # pylint: disable=import-error
except Exception:  # pylint: disable=W0703
    P4_LOADED = False
else:
    P4_LOADED = str(P4.P4().api_level)

try:  # Load the Git API if available
    import git
except Exception:  # pylint: disable=W0703
    GIT_LOADED = False
else:
    GIT_LOADED = git.__version__ if hasattr(git, '__version__') else False

_CLIENT_TYPES = Enum('client_types', ('file', 'git', 'perforce'))


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
    INVALID_TYPE = BatCaveError(9, Template('Invalid CMS type ($ctype). Must be one of: ' + str([t.name for t in _CLIENT_TYPES])))


class Label:
    """Class to create a universal abstract interface for a CMS system label.

    Attributes:
        LABEL_TYPES: The label providers currently supported by this class.
    """
    LABEL_TYPES = Enum('label_types', ('file', 'project'))

    def __init__(self, name, label_type, client, description=None, selector=None, lock=False):
        """
        Args:
            name: The label name.
            label_type: The label type.
            client: The CMS client used to interact with the label.
            description (optional, default=None): The description to attach to the label.
            selector (optional, default=None): The file selector to which to apply the label.
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
        self._refresh()
        changed = False
        if self._selector:
            for case in switch(self._client.type):
                if case(Client.CLIENT_TYPES.perforce):
                    self._label['View'] = self._selector
                    changed = True
                    break
                if case():
                    raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)
        if description:
            for case in switch(self._client.type):
                if case(Client.CLIENT_TYPES.perforce):
                    self._label['Description'] = description
                    changed = True
                    break
                if case():
                    raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)
        if changed:
            for case in switch(self._client.type):
                if case(Client.CLIENT_TYPES.perforce):
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
            if case(Client.CLIENT_TYPES.perforce):
                return '\n'.join([f'{i}: {v}' for (i, v) in self._client._p4fetch('label', self._name).items()])  # pylint: disable=W0212
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)

    description = property(lambda s: s._get_info('Description'), doc='A read-only property which returns the description of the label.')
    name = property(lambda s: s._name, doc='A read-only property which returns the name of the label.')
    type = property(lambda s: s._client.type, doc='A read-only property which returns the CMS type.')
    root = property(lambda s: s._client.root, doc='A read-only property which returns the root for the label.')

    def _refresh(self):
        """Refresh the label information from the central repository.

        Returns:
            Nothing

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._client.type):
            if case(Client.CLIENT_TYPES.perforce):
                self._label = self._client._p4fetch('label', self._name)  # pylint: disable=W0212
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)

    def _save(self):
        """Save the label to the central repository.

        Returns:
            Nothing

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._client.type):
            if case(Client.CLIENT_TYPES.perforce):
                self._client._p4save('label', self._label)  # pylint: disable=W0212
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)

    def _get_info(self, field):
        """Return the info for the specified field.

        Returns:
            The contents of the specified field.
        """
        return self._label[field]

    def lock(self):
        """Set the label to read-only.

        Returns:
            Nothing

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        self._refresh()
        for case in switch(self._client.type):
            if case(Client.CLIENT_TYPES.perforce):
                self._label['Options'] = self._label['Options'].replace('unlocked', '')
                self._label['Options'] = self._label['Options'].replace('locked', '')
                self._label['Options'] += 'locked'
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)
        self._save()

    def unlock(self):
        """Set the label to read-write.

        Returns:
            Nothing

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        self._refresh()
        for case in switch(self._client.type):
            if case(Client.CLIENT_TYPES.perforce):
                self._label['Options'] = self._label['Options'].replace('unlocked', '')
                self._label['Options'] = self._label['Options'].replace('locked', '')
                self._label['Options'] += 'unlocked'
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)
        self._save()

    def apply(self, *files, no_execute=False):
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
            if case(Client.CLIENT_TYPES.perforce):
                if self._type == self.LABEL_TYPES.project:
                    raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)
                args = ['labelsync', '-l', self._name]
                if no_execute:
                    args.append('-n')
                if files:
                    args += files
                return self._client._p4run(*args)  # pylint: disable=W0212
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)

    def remove(self, *files, no_execute=False):
        """Remove the label from the list of files.

        Args:
            files: The list of files to which to apply the label.
            no_execute (optional, default=False): If True, run the command but don't commit the results.

        Returns:
            The result of the command from the CMS API.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._client.type):
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)


class Client:
    """Class to create a universal abstract interface for a CMS system client.

    Attributes:
        CLIENT_TYPES: The CMS providers currently supported by this class.
        LINESTYLE_TYPES = The line ending styles.
        CLEAN_TYPES = The types cleanup that can be performed on a client when disposing of an instance.
        INFO_TYPES = The types of information clients.
        OBJECT_TYPES = The types of objects that can be reported on by a client.
    """
    CLIENT_TYPES = _CLIENT_TYPES
    LINESTYLE_TYPES = Enum('linestyle_types', ('local', 'unix', 'mac', 'win', 'share', 'native', 'lf', 'crlf'))
    CLEAN_TYPES = Enum('clean_types', ('none', 'members', 'all'))
    INFO_TYPES = Enum('info_types', ('archive',))
    OBJECT_TYPES = Enum('object_types', ('changelist', 'string'))

    _DEFAULT_P4PORT = 'perforce:1666'
    _INFO_DUMMY_CLIENT = 'BatCave_info_dummy_client'

    def __init__(self, ctype, name=None, connectinfo=None, user=None, root=None, altroots=None, mapping=None, hostless=False,
                 changelist_options=None, linestyle=None, cleanup=None, create=None, info=False, password=None, branch=None):
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
        self._client = None

        if not connectinfo:
            for case in switch(self._type):
                if case(self.CLIENT_TYPES.file):
                    raise CMSError(CMSError.CONNECTINFO_REQUIRED, ctype=self._type.name)
                if case(self.CLIENT_TYPES.git):
                    connectinfo = getenv('GIT_WORK_TREE')
                    break
                if case(self.CLIENT_TYPES.perforce):
                    connectinfo = self.get_cms_sys_value('P4PORT')
                    break
                if case():
                    raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)
        self._connectinfo = connectinfo

        if not user:
            for case in switch(self._type):
                if case(self.CLIENT_TYPES.file, self.CLIENT_TYPES.git):
                    user = self.get_cms_sys_value('USER')
                    break
                if case(self.CLIENT_TYPES.perforce):
                    user = self.get_cms_sys_value('P4USER')
                    break
                if case():
                    raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)
        self._user = user

        if info:
            name = f'{self._INFO_DUMMY_CLIENT}_{randint(0, 1000)}' if (name is None) else name

        create_arg = create
        if create is None:
            create = False if (info and (self._type != self.CLIENT_TYPES.git)) else True

        if cleanup is None:
            if self._type == self.CLIENT_TYPES.file:
                self._cleanup = False
            elif (self._type == self.CLIENT_TYPES.git) and (create_arg is None):
                self._cleanup = True
            else:
                self._cleanup = bool(create)
        else:
            self._cleanup = bool(cleanup)

        self._tmpdir = None
        if create:
            self._tmpdir = Path(mkdtemp(prefix='cms'))
            if not name:
                for case in switch(self._type):
                    if case(self.CLIENT_TYPES.file):
                        break
                    if case(self.CLIENT_TYPES.git, self.CLIENT_TYPES.perforce):
                        name = self._user + '_' + self._tmpdir.name
                        break
                    if case():
                        raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)
        elif not name:
            raise CMSError(CMSError.CLIENT_NAME_REQUIRED)
        self._name = name

        if create:
            if root is None:
                root = self._tmpdir
            if (self._mapping is None) and (self._type == self.CLIENT_TYPES.perforce) and info:
                self._mapping = [f'-//spec/... //{self.name}/...']
            if (linestyle is None) and (self._type == self.CLIENT_TYPES.perforce):
                linestyle = self.LINESTYLE_TYPES.local
        elif root:
            raise CMSError(CMSError.CLIENT_DATA_INVALID, data='root')
        elif self._mapping:
            raise CMSError(CMSError.CLIENT_DATA_INVALID, data='mapping')

        for case in switch(self._type):
            if case(self.CLIENT_TYPES.file):
                self._connected = True
                break
            if case(self.CLIENT_TYPES.git):
                git_args = dict()
                if branch:
                    git_args['branch'] = branch
                if info:
                    git_args['depth'] = 1
                self._client = git.Repo.clone_from(self._connectinfo, root, branch=(branch if branch else 'master')) if create else git.Repo(str(self._connectinfo))
                self._connected = True
                break
            if case(self.CLIENT_TYPES.perforce):
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
                        raise CMSError(CMSError.CONNECT_FAILED, connectinfo=self._connectinfo)
                    raise
                self._connected = True
                if create:
                    clientspec = self._p4fetch('client')
                    clientspec['Root'] = root
                    clientspec['LineEnd'] = linestyle.name
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
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                infostr = '\n'.join([f'{i}: {v}' for (i, v) in self._p4fetch('client').items()])
                break
            if case():
                infostr = self.name
        return f'{self.type} {infostr}'

    type = property(lambda s: s._type, doc='A read-only property which returns the CMS type.')
    name = property(lambda s: s._name, doc='A read-only property which returns the name of the client.')

    @property
    def root(self):
        """A read-only property which returns the root of the client."""
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.file):
                return Path(self._connectinfo)
            if case(self.CLIENT_TYPES.git):
                return Path(self._client.working_tree_dir)
            if case(self.CLIENT_TYPES.perforce):
                return Path(self._p4fetch('client')['Root'])
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    @property
    def mapping(self):
        """A read-write property which returns and sets the client mapping."""
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                return self._p4fetch('client')['View']
            if case():
                return self._mapping

    @mapping.setter
    def mapping(self, newmap):
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                self._mapping = newmap
                client_spec = self._p4fetch('client')
                client_spec['View'] = newmap
                self._p4save('client', client_spec)
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    @property
    def cms_info(self):
        """A read-only property which returns the CMS info."""
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.file):
                return 'CMS type is: file'
            if case(self.CLIENT_TYPES.git):
                return self._client.git.config('-l')
            if case(self.CLIENT_TYPES.perforce):
                return '\n'.join([f'{i}: {v}' for (i, v) in self._p4run('info')[0].items()] +
                                 ['server_level='+self._client.server_level, 'api_level='+self._client.api_level])
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    @property
    def branches(self):
        """A read-only property which returns the client branch list."""
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.git):
                return self._client.heads + self._client.remotes.origin.refs
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    @property
    def streams(self):
        """A read-only property which returns the client stream list."""
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                return self._p4run('streams', ['-T', 'Stream'])
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def _validatetype(self):
        """Determines if the specified CMS type is valid.

        Returns:
            Nothing
        """
        validatetype(self._type)

    def _p4run(self, method, *args):
        """Runs a Perforce command using the API if possible.

        Args:
            method: The command to run.
            args (optional): The arguments to pass to the command.

        Returns:
            The result of the command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
            P4.P4Exception: If the command generates errors
            TypeError: If the requested command is invalid.
            AttributeError: If the requested command is not found.
        """
        if self._type != self.CLIENT_TYPES.perforce:
            raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)
        if is_debug('P4'):
            print('Executing P4 command:', method, args, self._connected)
        try:
            if isinstance(method, Callable):
                return method(*args)
            elif hasattr(self._client, method) and isinstance(getattr(self._client, method), Callable):
                return getattr(self._client, method)(*args)
            elif hasattr(self._client, 'run_'+method) and isinstance(getattr(self._client, 'run_'+method), Callable):
                return getattr(self._client, 'run_'+method)(*args)
            elif hasattr(self._client, method):
                raise TypeError(method)  # not callable
            else:
                raise AttributeError(f"'{type(self)}' object has no attribute '{method}'")
        except P4.P4Exception:
            raise
        except Exception:  # pylint: disable=W0703
            if self._client.errors:
                raise P4.P4Exception('\n'.join(self._client.errors))
            else:
                raise

    def _p4fetch(self, what, *args):
        """Runs the Perforce fetch command.

        Args:
            what: The item to fetch.
            args (optional): The arguments to pass to the command.

        Returns:
            The result of the command.
        """
        return self._p4run('fetch_'+what, *args)

    def _p4save(self, what, *args):
        """Runs the Perforce save command.

        Args:
            what: The item to save.
            args (optional): The arguments to pass to the command.

        Returns:
            The result of the command.
        """
        return self._p4run('save_'+what, *args)

    def update(self, *files, limiters=None, force=False, parallel=False, no_execute=False):
        """Updates the local client files.

        Args:
            files (optional): The files to update, otherwise all will be updated.
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
            if case(self.CLIENT_TYPES.file):
                break
            if case(self.CLIENT_TYPES.git):
                info = self._client.remotes.origin.pull()[0]
                return info.note if info.note else info.ref
            if case(self.CLIENT_TYPES.perforce):
                args = ['sync']
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
                        return []
                    raise
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def list(self):
        """Get the local client files.

        Returns:
            The list of files on the current client.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.file):
                pushd(self.root)
                files = glob('**')
                popd()
                return files
            if case(self.CLIENT_TYPES.git):
                file_list = list()
                for (root, dirs, files) in walk_git_tree(self._client.tree()):  # pylint: disable=W0612
                    file_list += [f'{root}/{f}' for f in files]
                return file_list
            if case(self.CLIENT_TYPES.perforce):
                return self._p4run('have')
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def find(self, file_regex=''):
        """Search for files on the current client.

        Args:
            files_regex (optional, default=''): The regular expression to use to search for files.

        Returns:
            The list of files that were found.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.file, self.CLIENT_TYPES.git):
                regex = re_compile(file_regex)
                return [f for f in self.list() if regex.search(f)]
            if case(self.CLIENT_TYPES.perforce):
                try:
                    return self._p4run('files', file_regex)
                except P4.P4Exception as err:
                    if 'no such file' not in str(err):
                        raise
                return list()
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def integrate(self, source, target, no_execute=False):
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
            if case(self.CLIENT_TYPES.perforce):
                args = ['integrate', source, target]
                if no_execute:
                    args.append('-n')
                return self._p4run(*args)
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def reconcile(self, *files, no_execute=False):
        """Reconciles the workspace against the server and creates a changelist for the changes.

        Args:
            files (optional): The files to reconcile, otherwise all will be reconciled.
            no_execute (optional, default=False): If True, run the command but don't commit the results.

        Returns:
            The result of the reconcile command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        files = files if files else ['//...']
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                args = ['reconcile']
                if no_execute:
                    args.append('-n')
                if files:
                    args += files
                return self._p4run(*args)
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def add_files(self, *files, no_execute=False):
        """Adds files to the client.

        Args:
            files: The files to add.
            no_execute (optional, default=False): If True, run the command but don't commit the results.

        Returns:
            The result of the add files command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.file):
                break
            if case(self.CLIENT_TYPES.git):
                if not no_execute:
                    return self._client.index.add([str(f) for f in files])
                break
            if case(self.CLIENT_TYPES.perforce):
                args = ['-n'] if no_execute else []
                args += files
                return self._p4run('add', *args)
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def remove_files(self, *files, no_execute=False):
        """Remove files from the client.

        Args:
            files: The files to remove.
            no_execute (optional, default=False): If True, run the command but don't commit the results.

        Returns:
            The result of the remove files command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        result = None
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.git):
                if not no_execute:
                    result = self._client.index.remove(files)
                # intentional fall-through to remove the file system file
            if case(self.CLIENT_TYPES.file):
                if not no_execute:
                    for filename in files:
                        (self.root / filename).unlink()
                return result
            if case(self.CLIENT_TYPES.perforce):
                args = ['-n'] if no_execute else []
                args += files
                return self._p4run('delete', *args)
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def chmod_files(self, *files, mode, no_execute=False):
        """Perform a chmod of the files.

        Args:
            files: The files to chmod.
            mode: The new mode to apply.
            no_execute (optional, default=False): If True, run the command but don't commit the results.

        Returns:
            The result of the chmod command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.git):
                for cms_file in files:
                    if not no_execute:
                        return self._client.git.update_index(f'--chmod={mode}', cms_file)
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def lock_files(self, *files, no_execute=False):
        """Places a lock on the files to prevent edits by other users.

        Args:
            files: The files to lock.
            no_execute (optional, default=False): If True, run the command but don't commit the results.

        Returns:
            The result of the lock files command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                args = ['-n'] if no_execute else []
                args += files
                return self._p4run('lock', *args)
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def unlock_files(self, *files, no_execute=False):
        """Removes a lock on the files to allow edits by other users.

        Args:
            files: The files to unlock.
            no_execute (optional, default=False): If True, run the command but don't commit the results.

        Returns:
            The result of the unlock files command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                args = ['-n'] if no_execute else []
                args += files
                return self._p4run('unedit', *args)
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def checkout_files(self, *files, no_execute=False):
        """Opens files for editing on the client.

        Args:
            files: The files to unlock.
            no_execute (optional, default=False): If True, run the command but don't checkout the files.

        Returns:
            The result of the checkout command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.file):
                for file_name in files:
                    file_path = self.root / file_name
                    if not no_execute:
                        file_path.chmod(file_path.stat().st_mode | S_IWUSR)
                return None
            if case(self.CLIENT_TYPES.git):
                if not no_execute:
                    return self._client.index.add([str(f) for f in files])
            if case(self.CLIENT_TYPES.perforce):
                args = ['-n'] if no_execute else []
                args += files
                return self._p4run('edit', *args)
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def checkin_files(self, description, *files, all_branches=False, remote='origin', fail_on_empty=False, no_execute=False, **extra_args):
        """Commit opens files on the client.

        Args:
            description: A description of the changes.
            files (optional): If provided, a subset of the files to commit, otherwise all will be submitted.
            all_branches (optional, default=False): If True, commit all branches, otherwise only the current branch.
            fail_on_empty (optional, default=False): If True, raise an error if there are no files to commit, otherwise just return.
            no_execute (optional, default=False): If True, run the command but don't commit the results.
            extra_args (optional): Any extra API specific arguments or the commit.

        Returns:
            The result of the checkin command.

        Raises:
            CMSError.GIT_FAILURE: If there is a Git failure.
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.file):
                if not no_execute:
                    return self.unco_files(files, no_execute=no_execute)
                return None
            if case(self.CLIENT_TYPES.git):
                if not no_execute:
                    self._client.index.commit(description)
                    args = {'set_upstream': True, 'all': True} if all_branches else dict()
                    args.update(extra_args)
                    progress = git.RemoteProgress()
                    result = getattr(self._client.remotes, remote).push(progress=progress, **args)
                    if progress.error_lines:
                        raise CMSError(CMSError.GIT_FAILURE, msg=''.join(progress.error_lines).replace('error: ', ''))
                    return result
                return None
            if case(self.CLIENT_TYPES.perforce):
                changelist = self._p4fetch('change')
                changelist['Description'] = description
                try:
                    return self._p4save('submit' if not no_execute else 'change', changelist)
                except P4.P4Exception as err:
                    if ('No files to submit.' not in str(err)) or fail_on_empty:
                        raise
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def unco_files(self, *files, unchanged_only=False, no_execute=False):
        """Revert open files for editing on the client.

        Args:
            files (optional): If provided, a subset of the files to revert, otherwise all will be reverted.
            unchanged_only (optional, default=False): If True, only revert unchanged files, otherwise all will be reverted.
            no_execute (optional, default=False): If True, run the command but don't revert the files.

        Returns:
            The result of the revert command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.file):
                for file_name in files:
                    file_path = self.root / file_name
                    if not no_execute:
                        file_path.chmod(file_path.stat().st_mode & S_IWUSR)
                return None
            if case(self.CLIENT_TYPES.git):
                if not no_execute:
                    return self._client.index.checkout(paths=files, force=True)
                break
            if case(self.CLIENT_TYPES.perforce):
                args = ['-n'] if no_execute else []
                if unchanged_only:
                    args.append('-a')
                args += files if files else ['//...']
                try:
                    return self._p4run('revert', *args)
                except P4.P4Exception as err:
                    if 'file(s) not opened on this client.' not in str(err):
                        raise
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def create_repo(self, repository, repo_type=None, no_execute=False):
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
            if case(self.CLIENT_TYPES.perforce):
                depotspec = self._p4fetch('depot', repository)
                if repo_type:
                    depotspec['Type'] = repo_type
                if not no_execute:
                    return self._p4save('depot', depotspec)
                return None
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def create_branch(self, name, branch_from=None, repo=None, branch_type=None, options=None, no_execute=False):
        """Create the specified branch.

        Args:
            name: The name of the branch to create.
            branch_from (optional, default=None): If None, use the current branch, otherwise use the branch specified.
            repo (optional, default=None): If None, use the current repo, otherwise use the repo specified.
            branch_type (optional, default=None): If None, use the default branch type, otherwise use the branch type specified.
            options (optional, default=None): Any API specific options to use when creating the branch.
            no_execute (optional, default=False): If True, run the command but don't revert the files.

        Returns:
            The result of the branch create command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                if branch_type.startswith('stream'):
                    (branch_type, stream_type) = branch_type.split(':')
                    streamspec = self._p4fetch(branch_type, f'//{repo}/{name}')
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
                return None
            if case(self.CLIENT_TYPES.git):
                args = [name]
                if branch_from:
                    args.append(branch_from)
                self._client.create_head(*args)
                getattr(self._client.heads, name).checkout()
                if not no_execute:
                    return self._client.git.push('origin', name, set_upstream=True)
                return None
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def populate_branch(self, source, target, no_execute=False):
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
            if case(self.CLIENT_TYPES.perforce):
                if not no_execute:
                    return self._p4run('populate', [source, target])
                return None
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def add_remote_ref(self, name, url, exists_ok=False, no_execute=False):
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
            if case(self.CLIENT_TYPES.git):
                if not no_execute:
                    if exists_ok and name in self._client.remotes:
                        self._client.delete_remote(name)
                    return self._client.create_remote(name, url)
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def rename_remote_ref(self, old_name, new_name, no_execute=False):
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
            if case(self.CLIENT_TYPES.git):
                if not no_execute:
                    return self._client.remotes[old_name].rename(new_name)
                return None
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def merge(self, source_branch, checkin=True, checkin_message=None, no_execute=False):
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
            if case(self.CLIENT_TYPES.git):
                branch_owner = self._client.heads if (f'refs/heads/{source_branch}' in [str(b) for b in self.branches]) else self._client.remotes.origin.refs
                result = self._client.git.merge(getattr(branch_owner, source_branch), '--no-ff')
                if checkin:
                    checkin_message = checkin_message if (checkin_message is not None) else f'Merging code from {source_branch} to {self._client.active_branch}'
                    self.checkin_files(checkin_message, all_branches=True, no_execute=no_execute)
                return result
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def switch(self, branch):
        """Switch to the specified branch.

        Args:
            branch: The branch to which to switch.

        Returns:
            The result of the switch command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.git):
                if branch not in [b.name.split('/')[-1] for b in self.branches]:
                    self._client.create_head(branch, getattr(self._client.remotes.origin.refs, branch))
                return self._client.git.checkout(branch)
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def get_users(self):
        """Get the list of users.

        Returns:
            The list of users.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                return self._p4run('users')
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def get_file(self, filename, checkout=False):
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
            return self.get_filepath(filename)

        for case in switch(self._type):
            if case(self.CLIENT_TYPES.file, self.CLIENT_TYPES.git):
                return open(self.root / filename)
            if case(self.CLIENT_TYPES.perforce):
                return self._p4run('print', filename)[1:]
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def get_filepath(self, file_name):
        """Get the full local OS path to the file.

        Args:
            file_name: The name of the file for which to return the path.

        Returns:
            The full local OS path to the file.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.file, self.CLIENT_TYPES.git):
                return self.root / file_name
            if case(self.CLIENT_TYPES.perforce):
                file_info = self._p4run('fstat', file_name)
                return file_info[0]['clientFile']
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def get_changelists(self, *names, forfiles=None, count=None):
        """Get a list of changelist objects for the specified changelist names.

        Args:
            names: The list of changelist names.
            forfiles (optional, default=None): If not none, restrict the list based on the list of files.
            count (optional, default=None): If not None, the number of objects to return, otherwise return all.

        Returns:
            The changelist objects.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                arglist = ['-l', '-s', 'submitted']
                if not names:
                    if count:
                        arglist += ['-m', count]
                    if forfiles:
                        arglist += forfiles
                    names = self._p4run('changes', *arglist)
                return [ChangeList(self, c, ) for c in names]
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def get_changelist(self, name, *files, edit=False):
        """Get a ChangeList objects for the specified changelist.

        Args:
            name: The name of the changelist.
            files (optional): Restrict the list based on the list of files.
            edit (optional, default=False): If True, return and editable ChangeList object.

        Returns:
            The changelist object.
        """
        if edit:
            return ChangeList(self, name, editable=True)
        else:
            return self.get_changelists(name, forfiles=files)[0]

    def add_label(self, tag_name, exists_ok=False, no_execute=False):
        """Add a label.

        Args:
            tag_name: The name of the label to add.
            exists_ok (optional, default=False): If True and the label already exists, delete the label before adding it.
            no_execute (optional, default=False): If True, run the command but don't revert the files.

        Returns:
            The result of the add label command.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.git):
                if not no_execute:
                    if exists_ok and tag_name in self._client.tags:
                        self._client.delete_tag(tag_name)
                    return self._client.create_tag(tag_name)
                return None
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def get_labels(self, *args):
        """Gets the labels in the CMS system.

        Args:
            args (optional): Any API specific arguments to use.

        Returns:
            The list of labels.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                return self._p4run('labels', *args)
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def get_clients(self, *args):
        """Gets the clients in the CMS system.

        Args:
            args (optional): Any API specific arguments to use.

        Returns:
            The list of clients.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                return self._p4run('clients', *args)
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def get_repos(self, *args):
        """Gets the repositories in the CMS system.

        Args:
            args (optional): Any API specific arguments to use.

        Returns:
            The list of repositories.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                return self._p4run('depots', *args)
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def get_max_changelist(self, label=''):
        """Gets the highest changelist number.

        Args:
            label (optional, default=''): If not empty, limit the number by the specified label.

        Returns:
            The highest changelist number.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                if label:
                    label = '@' + label
                return self._p4run('changes', '-m1', f'//...{label}')[0]['change']
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def get_user_record(self, username):
        """Gets the CMS system information about the specified username.

        Args:
            username: The user for which to find the information.

        Returns:
            The information about the specified user.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                return self._p4fetch('user', username)
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)

    def get_server_connection(self):
        """Gets the name of the CMS server.

        Returns:
            The name of the CMS server.

        Raises:
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.file):
                return 'CMS type: file'
            if case(self.CLIENT_TYPES.perforce):
                return self._connectinfo
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)
    server_name = property(lambda s: s.get_server_connection()[0])

    def close(self):
        """Closes any persistent connections to the CMS system.

        Returns:
            Nothing.
        """
        if self._connected and self._type == self.CLIENT_TYPES.git:
            self._client.__del__()
            self._connected = False
        if self._cleanup:
            self.remove(self.CLEAN_TYPES.all)
            if self._tmpdir and self._tmpdir.exists() and (self._tmpdir != self.root):
                rmtree_hard(self._tmpdir)
        if self._connected and self._type == self.CLIENT_TYPES.perforce:
            self._p4run('disconnect')
            self._connected = False

    def remove(self, clean=CLEAN_TYPES.none):
        """Delete the client object from the CMS system.

        Args:
            clean (optional, default=CLEAN_TYPES.none): Specifies the amount of cleaning of the local file system.

        Returns:
            The result of the client removal command.

        Raises:
            CMSError.CLIENT_NOT_FOUND: If the client is not found.
            CMSError.INVALID_OPERATION: If the client CMS type is not supported.
        """
        client_root = self.root
        results = []
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                if clean in (self.CLEAN_TYPES.members, self.CLEAN_TYPES.all):
                    try:
                        results = self._p4run('sync', '//...#none')
                    except P4.P4Exception as err:
                        if ('file(s) not in client view' not in str(err)) and ('file(s) up-to-date' not in str(err)) and ("Can't clobber writable file" not in str(err)):
                            raise
                try:
                    results += self._p4run('client', '-d', '-f', self._name)
                except P4.P4Exception as err:
                    if "doesn't exist" in str(err):
                        raise CMSError(CMSError.CLIENT_NOT_FOUND, name=self._name)
                    results += self._p4run('client', '-d', self._name)
                break
            if case(self.CLIENT_TYPES.git):
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)
        if (clean == self.CLEAN_TYPES.all) and client_root and client_root.is_dir():
            rmtree_hard(client_root)
        return results

    def get_cms_sys_value(self, var):
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
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                if WIN32:
                    for key in (win32con.HKEY_CURRENT_USER, win32con.HKEY_LOCAL_MACHINE):
                        try:
                            keyhandle = win32api.RegOpenKeyEx(key, r'Software\perforce\environment', 0, win32con.KEY_READ)
                            if win32api.RegQueryValueEx(keyhandle, var):
                                return win32api.RegQueryValueEx(keyhandle, var)[0]
                        except win32api.error as err:
                            if err.winerror != 2:  # ERROR_FILE_NOT_FOUND
                                raise
                for inner_case in switch(var):
                    if inner_case('P4PORT'):
                        return self._DEFAULT_P4PORT
                    if inner_case('P4USER'):
                        username = getuser().lower()
                        if username:
                            return username
                raise P4.P4Exception('unable to determine ' + var)
            if case():
                if var == 'USER':
                    if getuser():
                        return getuser()
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._type.name)


def walk_git_tree(tree, parent=None):
    """Walks the git tree similar to os.walk().

    Attributes:
        tree: The git tree to walk.
        parent (optional, default=None): Use a different parent than the root of the tree.

    Yields:
        Runs like an iterator which yields tuples of
            (the new parent, the tree names, the git blobs)
    """
    (tree_names, trees, blobs) = (list(), list(), list())
    for entry in tree:
        if isinstance(entry, git.Tree):
            tree_names.append(entry.name)
            trees.append(entry)
        else:
            blobs.append(entry.name)

    new_parent = f'{parent}/{tree.name}' if parent else tree.name
    for tree in trees:
        yield from walk_git_tree(tree, new_parent)

    yield new_parent, tree_names, blobs


class FileRevision:
    """This class describes information about a file revision."""

    def __init__(self, filename, revision, author, date, labels, description):
        """
        Args/Attributes:
            filename: The name of the file.
            revision: The revision number for this revision.
            description: The description for this revision.
            author: The user that made this revision.
            labels: A list of labels on this revision.
        """

        self.filename = filename
        self.revision = revision
        self.author = author
        self.date = date
        self.labels = labels
        self.description = description

    def __str__(self):
        return f'{self.filename}#{self.revision} by {self.author} on {self.date}\nLabels: {self.labels}\nDescription: {self.description}\n'


class FileChangeRecord:
    """This class describes information about a file change."""

    def __init__(self, client, filename, revision, mod_type, changelist):
        """
        Args/Attributes:
            client: The CMS Client object where this file change record is located.
            filename: The name of the file.
            revision: The revision number for this revision.
            mod_type: The type of modification for the file.
            changelist: The changelist number for the change record.
        """

        self._client = client
        self.filename = filename
        self.revision = revision
        self.type = mod_type
        self.changelist = changelist

    fullname = property(lambda s: f'{s.filename}#{s.revision}', doc='A read-only property which returns the full name of the changed file.')

    def __str__(self):
        for case in switch(self._client.type):
            if case(Client.CLIENT_TYPES.perforce):
                return f'{self.filename}#{self.revision} {self.type} {self.changelist}'


class ChangeList:
    """Class to create a universal abstract interface for a CMS changelist."""

    def __init__(self, client, chg_list_id=None, editable=None):
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
        self._id = chg_list_id
        self._files = None
        if editable is None:
            self._editable = not bool(self._id)
        else:
            self._editable = editable
        for case in switch(client.type):
            if case(Client.CLIENT_TYPES.perforce):
                if isinstance(id, str) or isinstance(id, int):
                    self._id = str(id)
                    if self._editable:
                        self._changelist = self._client._p4fetch('change', self._id)  # pylint: disable=W0212
                    else:
                        self._changelist = self._client._p4run('describe', '-s', self._id)[0]  # pylint: disable=W0212
                else:
                    self._changelist = chg_list_id if chg_list_id else self._client._p4fetch('change')  # pylint: disable=W0212
                    self._id = self._changelist['change']
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)

    name = property(lambda s: s._id, doc='A read-only property which returns the name of the change list.')

    def __str__(self):
        return 'Changelist ' + self.name

    @property
    def user(self):
        """A read-write property which returns and sets the change list user."""
        for case in switch(self._client.type):
            if case(Client.CLIENT_TYPES.perforce):
                return self._changelist['User' if self._editable else 'user']
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)

    @user.setter
    def user(self, newuser):
        if not self._editable:
            raise CMSError(CMSError.CHANGELIST_NOT_EDITABLE, changelist=self._id)
        for case in switch(self._client.type):
            if case(Client.CLIENT_TYPES.perforce):
                self._changelist['User'] = newuser
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)

    @property
    def time(self):
        """A read-write property which returns and sets the change list time."""
        for case in switch(self._client.type):
            if case(Client.CLIENT_TYPES.perforce):
                if self._editable:
                    return datetime.strptime(self._changelist['Date'], '%Y/%m/%d %H:%M:%S')
                else:
                    return datetime.fromtimestamp(int(self._changelist['time']))
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)

    @time.setter
    def time(self, newtime):
        if not self._editable:
            raise CMSError(CMSError.CHANGELIST_NOT_EDITABLE, changelist=self._id)
        for case in switch(self._client.type):
            if case(Client.CLIENT_TYPES.perforce):
                self._changelist['Date'] = newtime.strftime('%Y/%m/%d %H:%M:%S') if isinstance(newtime, datetime) else newtime
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)

    @property
    def desc(self):
        """A read-write property which returns and sets the change list description."""
        for case in switch(self._client.type):
            if case(Client.CLIENT_TYPES.perforce):
                return self._changelist['Description' if self._editable else 'desc']
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)

    @desc.setter
    def desc(self, newdesc):
        if not self._editable:
            raise CMSError(CMSError.CHANGELIST_NOT_EDITABLE, changelist=self._id)
        for case in switch(self._client.type):
            if case(Client.CLIENT_TYPES.perforce):
                self._changelist['Description'] = newdesc
                break
            if case():
                raise CMSError(CMSError.INVALID_OPERATION, ctype=self._client.type.name)

    @property
    def files(self):
        """A read-only property which returns the list of files in the change list."""
        if self._files is None:
            desc = self._client._p4run('describe', '-s', self.name)[0]  # pylint: disable=W0212
            self._files = [FileChangeRecord(self._client, f, r, a, self.name)
                           for (f, r, a) in zip(desc['depotFile'], desc['rev'], desc['action'])]
        return self._files

    def store(self, no_execute=False):
        """Save the ChangeList to the CMS server.

        Args:
            no_execute (optional, default=False): If True, run the command but don't commit the results.

        Returns:
            The result of the changelist save command.
        """
        if not no_execute:
            return self._client._p4save('change', self._changelist, '-f')  # pylint: disable=W0212
        return None


def create_client_name(prefix=None, suffix=None, sep='_', licenseplate=False):
    """Automatically creates a client name from the user and hostname.

    Attributes:
        prefix (optional, default=None): If not None, the prefix for the client.
        suffix (optional, default=None): If not None, the suffix for the client.
        sep (optional, default='_'): The separator for the different pieces of the name.
        licenseplate (optional, default=False): If not False, adds a random number to the end of the name.
            Will be appended after the suffix.

    Returns:
        Returns the client name.
    """
    parts = [getuser(), node()]
    if prefix:
        parts.insert(0, prefix)
    if suffix:
        parts.append(suffix)
    if licenseplate:
        parts.append(str(randint(0, 1000)))
    return sep.join(parts)


def validatetype(ctype):
    """Determines if the specified CMS type is valid.

    Arguments:
        ctype: The CMS type.

    Returns:
        Nothing.

    Raises
        CMSError.INVALID_TYPE: If the CMS type is not valid.
    """
    if ctype not in Client.CLIENT_TYPES:
        raise CMSError(CMSError.INVALID_TYPE, ctype=ctype)


# cSpell:ignore checkin unedit
