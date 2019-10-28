'Interface to generalize Code Management System interactions'
# pylint: disable=C0302,I1101
# cSpell:ignore checkin, unedit

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
from .lang import is_debug, switch, HALError, HALException, WIN32

if WIN32:
    import win32api
    import win32con

try:  # Load the Perforce API if available
    import P4
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


class CMSError(HALException):
    'Class for CMS errors'
    INVALIDTYPE = HALError(1, Template('Invalid CMS type ($ctype). Must be one of: ' + str([t.name for t in _CLIENT_TYPES])))
    CONNECT_FAILED = HALError(2, Template('Unable to connect to CMS server on $connectinfo'))
    CLIENT_NAME_REQUIRED = HALError(3, 'Name required if client is not being created')
    CLIENT_DATA_INVALID = HALError(4, Template('$data not valid if client exists'))
    CHANGELIST_NOT_EDITABLE = HALError(5, Template('changelist $changelist not opened for edit'))
    NO_CMS_FILE = HALError(6, Template('Unable to get CMS file: $filename'))
    INVALIDTYPE_FOR_OPERATION = HALError(7, Template('Invalid CMS type ($ctype) for this operation'))
    PROJECT_MAPPING_REQUIRED = HALError(8, 'A project is required')
    INVALIDTYPE_FOR_FIND = HALError(9, Template('Invalid find type: $file_type'))
    ATTRIBUTE_NOT_FOUND = HALError(10, Template('No such attribute: $attr'))
    GIT_FAILURE = HALError(11, Template('Git Error:\n$msg'))
    CLIENT_NOT_FOUND = HALError(12, Template('Client $name not found'))
    CONNECTINFO_REQUIRED = HALError(13, Template('Connectinfo required for CMS type ($ctype)'))


class Label:
    'Generalizes a SCM system label'
    LABEL_TYPES = Enum('label_types', ('file', 'project'))

    def __init__(self, name, label_type, client, description=None, selector=None, lock=False):
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
                    raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._client.type.name)
        if description:
            for case in switch(self._client.type):
                if case(Client.CLIENT_TYPES.perforce):
                    self._label['Description'] = description
                    changed = True
                    break
                if case():
                    raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._client.type.name)
        if changed:
            for case in switch(self._client.type):
                if case(Client.CLIENT_TYPES.perforce):
                    self._save()
                    break
                if case():
                    raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._client.type.name)
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
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._client.type.name)

    description = property(lambda s: s._get_info('Description'))
    name = property(lambda s: s._name)
    type = property(lambda s: s._client.type)
    root = property(lambda s: s._client.root)

    def _refresh(self):
        for case in switch(self._client.type):
            if case(Client.CLIENT_TYPES.perforce):
                self._label = self._client._p4fetch('label', self._name)  # pylint: disable=W0212
                break
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._client.type.name)

    def _save(self):
        for case in switch(self._client.type):
            if case(Client.CLIENT_TYPES.perforce):
                self._client._p4save('label', self._label)  # pylint: disable=W0212
                break
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._client.type.name)

    def _get_info(self, field):
        return self._label[field]

    def lock(self):
        'Make the label read-only'
        self._refresh()
        for case in switch(self._client.type):
            if case(Client.CLIENT_TYPES.perforce):
                self._label['Options'] = self._label['Options'].replace('unlocked', '')
                self._label['Options'] = self._label['Options'].replace('locked', '')
                self._label['Options'] += 'locked'
                break
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._client.type.name)
        self._save()

    def unlock(self):
        'Make the label changeable'
        self._refresh()
        for case in switch(self._client.type):
            if case(Client.CLIENT_TYPES.perforce):
                self._label['Options'] = self._label['Options'].replace('unlocked', '')
                self._label['Options'] = self._label['Options'].replace('locked', '')
                self._label['Options'] += 'unlocked'
                break
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._client.type.name)
        self._save()

    def apply(self, *files, no_execute=False):
        'Apply the label to a list of files'
        for case in switch(self._client.type):
            if case(Client.CLIENT_TYPES.perforce):
                if self._type == self.LABEL_TYPES.project:
                    raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._client.type.name)
                args = ['labelsync', '-l', self._name]
                if no_execute:
                    args.append('-n')
                if files:
                    args += files
                return self._client._p4run(*args)  # pylint: disable=W0212
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._client.type.name)

    def remove(self, *files):  # pylint: disable=W0613
        'Remove the label from a list of files'
        for case in switch(self._client.type):
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._client.type.name)


class Client:
    'wrapper class for the CMS toolkit'
    CLIENT_TYPES = _CLIENT_TYPES
    LINESTYLE_TYPES = Enum('linestyle_types', ('local', 'unix', 'mac', 'win', 'share', 'native', 'lf', 'crlf'))
    CLEAN_TYPES = Enum('clean_types', ('none', 'members', 'all'))
    INFO_TYPES = Enum('info_types', ('archive',))
    OBJECT_TYPES = Enum('object_types', ('changelist', 'string'))

    _DEFAULT_P4PORT = 'perforce:1666'
    _INFO_DUMMY_CLIENT = 'BatCave_info_dummy_client'

    def __init__(self, ctype, name=None, connectinfo=None, user=None, root=None, altroots=None, mapping=None, hostless=False,
                 changelist_options=None, linestyle=None, cleanup=None, create=None, info=False, password=None, branch=None):
        ''' Creates a client object for the requested CMS type
            The meaning of these value is based on the source type
                Source Type    : connectinfo      : user     : name           : root           : mapping        : branch
                -------------------------------------------------------------------------------------------------------------
                file           : directory        : NA       : NA             : connectinfo    : NA             : NA
                perforce       : P4PORT           : P4USER   : client name    : client root    : client view    : stream name
                git            : URL              : USERNAME : repo name      : repo root      : NA             : branch name '''
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
                    raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)
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
                    raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)
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
                        raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)
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
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

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

    type = property(lambda s: s._type)
    name = property(lambda s: s._name)

    @property
    def root(self):
        'Return the root of the changelist'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.file):
                return Path(self._connectinfo)
            if case(self.CLIENT_TYPES.git):
                return Path(self._client.working_tree_dir)
            if case(self.CLIENT_TYPES.perforce):
                return Path(self._p4fetch('client')['Root'])
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    @property
    def mapping(self):
        'Return the changelist mapping'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                return self._p4fetch('client')['View']
            if case():
                return self._mapping

    @mapping.setter
    def mapping(self, newmap):
        'Set the changelist mapping'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                self._mapping = newmap
                client_spec = self._p4fetch('client')
                client_spec['View'] = newmap
                self._p4save('client', client_spec)
                break
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    @property
    def cms_info(self):
        'Returns the CMS info'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.file):
                return 'CMS type is: file'
            if case(self.CLIENT_TYPES.git):
                return self._client.git.config('-l')
            if case(self.CLIENT_TYPES.perforce):
                return '\n'.join([f'{i}: {v}' for (i, v) in self._p4run('info')[0].items()] +
                                 ['server_level='+self._client.server_level, 'api_level='+self._client.api_level])
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    @property
    def branches(self):
        'Returns the branches'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.git):
                return self._client.heads + self._client.remotes.origin.refs
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    @property
    def streams(self):
        'Returns the streams'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                return self._p4run('streams', ['-T', 'Stream'])
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def _validatetype(self):
        'determines if the specified CMS type is valid'
        validatetype(self._type)

    def _p4run(self, method, *args):
        'runs a Perforce command'
        if self._type != self.CLIENT_TYPES.perforce:
            raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)
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
        return self._p4run('fetch_'+what, *args)

    def _p4save(self, what, *args):
        return self._p4run('save_'+what, *args)

    def update(self, *files, limiters=None, force=False, parallel=False, no_execute=False):
        'Updates the local client and returns the list of files that were updated if provided by the underlying client'
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
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def list(self):
        'returns a list of all the files in the current client'
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
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def find(self, file_regex=''):
        'returns a list of files matching the specifications'
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
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def integrate(self, source, target, no_execute=False):
        'integrates the source into the target'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                args = ['integrate', source, target]
                if no_execute:
                    args.append('-n')
                return self._p4run(*args)
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def reconcile(self, *files, no_execute=False):
        'reconciles the workspace against the server and creates a changelist for the changes'
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
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def add_files(self, *files, no_execute=False):
        'adds files to the client'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.file):
                break
            if case(self.CLIENT_TYPES.git):
                if not no_execute:
                    self._client.index.add([str(f) for f in files])
                break
            if case(self.CLIENT_TYPES.perforce):
                args = ['-n'] if no_execute else []
                args += files
                return self._p4run('add', *args)
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def remove_files(self, *files, no_execute=False):
        'removes files from the client'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.git):
                if not no_execute:
                    self._client.index.remove(files)
                # intentional fall-through to remove the file system file
            if case(self.CLIENT_TYPES.file):
                if not no_execute:
                    for filename in files:
                        (self.root / filename).unlink()
                break
            if case(self.CLIENT_TYPES.perforce):
                args = ['-n'] if no_execute else []
                args += files
                return self._p4run('delete', *args)
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def chmod_files(self, *files, mode, no_execute=False):
        'chmod the file list'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.git):
                for cms_file in files:
                    if not no_execute:
                        self._client.git.update_index(f'--chmod={mode}', cms_file)
                break
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def lock_files(self, *files, no_execute=False):
        'places a lock on the files to prevent edits by other users'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                args = ['-n'] if no_execute else []
                args += files
                return self._p4run('lock', *args)
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def unlock_files(self, *files, no_execute=False):
        'removes a lock on the files to allow edits by other users'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                args = ['-n'] if no_execute else []
                args += files
                return self._p4run('unedit', *args)
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def checkout_files(self, *files, no_execute=False):
        'opens files for editting on the client'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.file):
                for file_name in files:
                    file_path = self.root / file_name
                    if not no_execute:
                        file_path.chmod(file_path.stat().st_mode | S_IWUSR)
                break
            if case(self.CLIENT_TYPES.git):
                if not no_execute:
                    return self._client.index.add([str(f) for f in files])
            if case(self.CLIENT_TYPES.perforce):
                args = ['-n'] if no_execute else []
                args += files
                return self._p4run('edit', *args)
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def checkin_files(self, description, *files, all_branches=False, remote='origin', fail_on_empty=False, no_execute=False, **extra_args):
        'commits files open on the client'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.file):
                if not no_execute:
                    self.unco_files(files, no_execute=no_execute)
                break
            if case(self.CLIENT_TYPES.git):
                if not no_execute:
                    self._client.index.commit(description)
                    args = {'set_upstream': True, 'all': True} if all_branches else dict()
                    args.update(extra_args)
                    progress = git.RemoteProgress()
                    getattr(self._client.remotes, remote).push(progress=progress, **args)
                    if progress.error_lines:
                        raise CMSError(CMSError.GIT_FAILURE, msg=''.join(progress.error_lines).replace('error: ', ''))
                break
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
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def unco_files(self, *files, unchanged_only=False, no_execute=False):
        'reverts files open for editting on the client'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.file):
                for file_name in files:
                    file_path = self.root / file_name
                    if not no_execute:
                        file_path.chmod(file_path.stat().st_mode & S_IWUSR)
                break
            if case(self.CLIENT_TYPES.git):
                if not no_execute:
                    self._client.index.checkout(paths=files, force=True)
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
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def create_repo(self, repository, repo_type=None, no_execute=False):
        'Create a repository'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                depotspec = self._p4fetch('depot', repository)
                if repo_type:
                    depotspec['Type'] = repo_type
                if not no_execute:
                    self._p4save('depot', depotspec)
                break
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def create_branch(self, name, branch_from=None, repo=None, branch_type=None, options=None, no_execute=False):
        'Create a branch'
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
                        self._p4save('stream', streamspec)
                break
            if case(self.CLIENT_TYPES.git):
                args = [name]
                if branch_from:
                    args.append(branch_from)
                self._client.create_head(*args)
                getattr(self._client.heads, name).checkout()
                if not no_execute:
                    self._client.git.push('origin', name, set_upstream=True)
                break
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def populate_branch(self, source, target, no_execute=False):
        'Populate a branch'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                if not no_execute:
                    self._p4run('populate', [source, target])
                break
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def add_remote_ref(self, name, url, exists_ok=False, no_execute=False):
        'Add a remote reference for a DVCS client'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.git):
                if not no_execute:
                    if exists_ok and name in self._client.remotes:
                        self._client.delete_remote(name)
                    self._client.create_remote(name, url)
                break
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def rename_remote_ref(self, oldname, newname, no_execute=False):
        'Rename a remote reference for a DVCS client '
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.git):
                if not no_execute:
                    self._client.remotes[oldname].rename(newname)
                break
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def merge(self, source_branch, checkin=True, checkin_message=None, no_execute=False):
        'performs a file merge on files open on the client'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.git):
                branch_owner = self._client.heads if (f'refs/heads/{source_branch}' in [str(b) for b in self.branches]) else self._client.remotes.origin.refs
                self._client.git.merge(getattr(branch_owner, source_branch), '--no-ff')
                if checkin:
                    checkin_message = checkin_message if (checkin_message is not None) else f'Merging code from {source_branch} to {self._client.active_branch}'
                    self.checkin_files(checkin_message, all_branches=True, no_execute=no_execute)
                break
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def switch(self, branch):
        'switches to the specified branch'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.git):
                if branch not in [b.name.split('/')[-1] for b in self.branches]:
                    self._client.create_head(branch, getattr(self._client.remotes.origin.refs, branch))
                return self._client.git.checkout(branch)
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def get_users(self):
        'returns the list of valid users'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                return self._p4run('users')
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def get_file(self, filename, checkout=False):
        'returns the named file contents'
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
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def get_filepath(self, file_name):
        'returns the full local OS path to the file'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.file, self.CLIENT_TYPES.git):
                return self.root / file_name
            if case(self.CLIENT_TYPES.perforce):
                file_info = self._p4run('fstat', file_name)
                return file_info[0]['clientFile']
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def get_changelists(self, *names, forfiles=None, count=None):
        'returns a list of changelist objects for the specified changelist names'
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
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def get_changelist(self, name, *files, edit=False):
        'returns a list of changelist objects for the specified changelist names'
        if edit:
            return ChangeList(self, name, editable=True)
        else:
            return self.get_changelists(name, forfiles=files)[0]

    def add_label(self, tag_name, exists_ok=False, no_execute=False):
        'returns the labels in the cms system'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.git):
                if not no_execute:
                    if exists_ok and tag_name in self._client.tags:
                        self._client.delete_tag(tag_name)
                    self._client.create_tag(tag_name)
                break
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def get_labels(self, *args):
        'returns the labels in the cms system'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                return self._p4run('labels', *args)
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def get_clients(self, *args):
        'returns the clients in the cms system'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                return self._p4run('clients', *args)
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def get_repos(self, *args):
        'returns the repositories in the cms system'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                return self._p4run('depots', *args)
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def get_max_changelist(self, label=''):
        'Return the highest changelist number'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                if label:
                    label = '@' + label
                return self._p4run('changes', '-m1', f'//...{label}')[0]['change']
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def get_user_record(self, username):
        'returns the cms system information about the specified username'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.perforce):
                return self._p4fetch('user', username)
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)

    def get_server_connection(self):
        'returns the cms system name of the server'
        for case in switch(self._type):
            if case(self.CLIENT_TYPES.file):
                return 'CMS type: file'
            if case(self.CLIENT_TYPES.perforce):
                return self._connectinfo
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)
    server_name = property(lambda s: s.get_server_connection()[0])

    def close(self):
        'Closes any persistent connections to the SCM system'
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
        'delete the CMS client object from the CMS system'
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
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)
        if (clean == self.CLEAN_TYPES.all) and client_root and client_root.is_dir():
            rmtree_hard(client_root)
        return results

    def get_cms_sys_value(self, var):
        'Get a configuration value from the CMS system'
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
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._type.name)


def walk_git_tree(tree, parent=None):
    'Walk the git tree similar to os.walk()'
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
    ''' This class describes information about a file revision
            name - the name of the file
            revision - the revision number for this revision
            description - the description for this revision
            author - the user that made this revision
            labels - a list of labels on this revision '''

    def __init__(self, filename, revision, author, date, labels, desc):
        self.file = filename
        self.revision = revision
        self.author = author
        self.date = date
        self.labels = labels
        self.description = desc

    def __str__(self):
        return f'{self.file}#{self.revision} by {self.author} on {self.date}\nLabels: {self.labels}\nDescription: {self.description}\n'


class FileChangeRecord:
    ''' This class describes information about a file change
            name - the name of the file
            version - the version identifier for the file
            mod_type - the type of modification for the file '''

    def __init__(self, client, filename, revision, mod_type, changelist):
        self._client = client
        self.file = filename
        self.revision = revision
        self.type = mod_type
        self.changelist = changelist

    fullname = property(lambda s: f'{s.file}#{s.revision}')

    def __str__(self):
        for case in switch(self._client.type):
            if case(Client.CLIENT_TYPES.perforce):
                return f'{self.file}#{self.revision} {self.type} {self.changelist}'


class ChangeList:
    'ChangeList container class'
    def __init__(self, client, chg_list_id=None, editable=None):
        self._client = client
        self._id = chg_list_id
        self._files = None
        if editable is None:
            self._editable = False if self._id else True
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
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._client.type.name)

    name = property(lambda s: s._id)

    def __str__(self):
        return 'Changelist ' + self.name

    @property
    def user(self):
        'Returns the user'
        for case in switch(self._client.type):
            if case(Client.CLIENT_TYPES.perforce):
                return self._changelist['User' if self._editable else 'user']
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._client.type.name)

    @user.setter
    def user(self, newuser):
        'Sets the user'
        if not self._editable:
            raise CMSError(CMSError.CHANGELIST_NOT_EDITABLE, changelist=self._id)
        for case in switch(self._client.type):
            if case(Client.CLIENT_TYPES.perforce):
                self._changelist['User'] = newuser
                break
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._client.type.name)

    @property
    def time(self):
        'returns the time'
        for case in switch(self._client.type):
            if case(Client.CLIENT_TYPES.perforce):
                if self._editable:
                    return datetime.strptime(self._changelist['Date'], '%Y/%m/%d %H:%M:%S')
                else:
                    return datetime.fromtimestamp(int(self._changelist['time']))
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._client.type.name)

    @time.setter
    def time(self, newtime):
        'sets the time'
        if not self._editable:
            raise CMSError(CMSError.CHANGELIST_NOT_EDITABLE, changelist=self._id)
        for case in switch(self._client.type):
            if case(Client.CLIENT_TYPES.perforce):
                self._changelist['Date'] = newtime.strftime('%Y/%m/%d %H:%M:%S') if isinstance(newtime, datetime) else newtime
                break
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._client.type.name)

    @property
    def desc(self):
        'returns the description'
        for case in switch(self._client.type):
            if case(Client.CLIENT_TYPES.perforce):
                return self._changelist['Description' if self._editable else 'desc']
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._client.type.name)

    @desc.setter
    def desc(self, newdesc):
        'sets the description'
        if not self._editable:
            raise CMSError(CMSError.CHANGELIST_NOT_EDITABLE, changelist=self._id)
        for case in switch(self._client.type):
            if case(Client.CLIENT_TYPES.perforce):
                self._changelist['Description'] = newdesc
                break
            if case():
                raise CMSError(CMSError.INVALIDTYPE_FOR_OPERATION, ctype=self._client.type.name)

    @property
    def files(self):
        'Returns the file list'
        if self._files is None:
            desc = self._client._p4run('describe', '-s', self.name)[0]  # pylint: disable=W0212
            self._files = [FileChangeRecord(self._client, f, r, a, self.name)
                           for (f, r, a) in zip(desc['depotFile'], desc['rev'], desc['action'])]
        return self._files

    def store(self, no_execute=False):
        'Saves the changelist'
        if not no_execute:
            self._client._p4save('change', self._changelist, '-f')  # pylint: disable=W0212


def create_client_name(prefix=None, suffix=None, sep='_', licenseplate=False):
    'Automatically create a client name'
    parts = [getuser(), node()]
    if prefix:
        parts.insert(0, prefix)
    if suffix:
        parts.append(suffix)
    if licenseplate:
        parts.append(str(randint(0, 1000)))
    return sep.join(parts)


def validatetype(ctype):
    'determines if the specified CMS type is valid'
    if ctype not in Client.CLIENT_TYPES:
        raise CMSError(CMSError.INVALIDTYPE, ctype=ctype)


def get_labels(ctype):
    'returns the labels in the cms system'
    return Client(ctype, info=True).get_labels()


def initialize():
    'Initialize the CMS system'


def terminate():
    'Shutdown the CMS system'
