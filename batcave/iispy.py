"""This module provides a Pythonic interface to work with Internet Information Server."""

# Import standard modules
from os import getenv
from pathlib import Path
from string import Template
from xml.etree.ElementTree import fromstring as xmlparse_str, fromstringlist as xmlparse_list

# Import internal modules
from .sysutil import syscmd, CMDError
from .lang import bool_to_str, str_to_pythonval, BatCaveError, BatCaveException


class AppCmdError(BatCaveException):
    """appcmd Exceptions.

    Attributes:
        APPCMD_ERROR: There was an error executing appcmd.exe.
    """
    APPCMD_ERROR = BatCaveError(1, Template('Error running appcmd: $message'))


class IISConfigurationError(BatCaveException):
    """IIS Configuration Exceptions.

    Attributes:
        PARSE_ERROR: There was an error locating the specified configuration section.
    """
    PARSE_ERROR = BatCaveError(1, Template("Unable to locate '$expected' in configuration"))


class IISAdvancedLogError(BatCaveException):
    """IIS AdvancedLog Exceptions.

    Attributes:
        BAD_FIELD: There was an attempt to add a non-existent field.
        NOT_INSTALLED: Advanced logging is not installed.
    """
    BAD_FIELD = BatCaveError(1, Template('Attempt to add non-existent field: $field'))
    NOT_INSTALLED = BatCaveError(2, 'IIS Advanced Logging is not installed on the target system')


class IISObject:
    """Class to create a universal abstract interface for an IIS object."""

    def __init__(self, name, iis_ref):
        """
        Args:
            name: The name of the object.
            iis_ref: A reference to the IIS owner instance.

        Attributes:
            name: The value of the name argument.
            iis_ref: The value of the iis_ref argument.
        """
        self.name = name
        self.iis_ref = iis_ref

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def manage_item(self, action):
        'Generic method to manage this item'
        self.iis_ref.manage_item(action, type(self), self.name)

    def start(self):
        'Performs the start action on an IISObject'
        self.manage_item('start')

    def stop(self):
        'Performs the stop action on an IISObject'
        try:
            self.manage_item('stop')
        except AppCmdError as err:
            if err.vars['returncode'] != 1062:
                raise


class VirtualDirectory(IISObject):
    """Class to create a universal abstract interface for an IIS virtual directory."""


class WebApplication(IISObject):
    """Class to create a universal abstract interface for an IIS web application."""


class WebApplicationPool(IISObject):
    """Class to create a universal abstract interface for an IIS web application pool."""


class WebSite(IISObject):
    """Class to create a universal abstract interface for an IIS website."""


class IISInstance:
    """Class to create a universal abstract interface for an IIS instance.

    Attributes:
        _IIS_TYPE_MAP: Maps IIS object types to appcmd subcommands.
    """
    _IIS_TYPE_MAP = {VirtualDirectory: 'VDIR',
                     WebApplication: 'APP',
                     WebApplicationPool: 'APPPOOL',
                     WebSite: 'SITE'}

    def __init__(self, hostname=None, remote_powershell=None):
        """
        Args:
            hostname (optional, default=localhost): The name of the IIS server hosting the instance.
            remote_powershell (optional): Determines if PowerShell remoting is used when executing appcmd against a remote server.
                Defaults to False for hostname is None, otherwise defaults to True.

        Attributes:
            hostname: The value of the hostname argument.
            _remote_powershell: The resolved value of the remote_powershell argument.
        """
        self.hostname = hostname
        self._remote_powershell = (True if (remote_powershell is None) else remote_powershell) if hostname else False

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def __getattr__(self, attr):
        tag = attr.upper()[0:-1]
        result = [i.attrib[f'{tag}.NAME'].rstrip('/') for i in xmlparse_list(appcmd('list', attr, hostname=self.hostname, remote_powershell=self._remote_powershell)).findall(tag)]
        if not result:
            raise AttributeError(attr)
        return result

    def exists(self):
        'Tests for existence of the IIS instance'
        try:
            str(self.get_configuration_section('log'))
        except CMDError as err:
            if err.code == CMDError.CMD_ERROR.code:
                return False
            raise
        return True

    def start(self, verbose=True):
        'Perform a reset on the IIS instance'
        return syscmd('iisreset', '/start', remote=self.hostname, show_stdout=verbose)

    def stop(self, verbose=True):
        'Perform a reset on the IIS instance'
        return syscmd('iisreset', '/stop', remote=self.hostname, show_stdout=verbose)

    def reset(self, verbose=True):
        'Perform a reset on the IIS instance'
        return syscmd('iisreset', remote=self.hostname, show_stdout=verbose)

    def get_configuration_section(self, name, path=None, set_location='apphost'):
        'Get the named configuration section from the IIS configuration files'
        return IISConfigurationSection(name=name, path=path, set_location=set_location, hostname=self.hostname, remote_powershell=self._remote_powershell)

    def get_advanced_logger(self, path=None, logtype='server', set_location='apphost'):
        'Get the advanced logger object from the IIS instance'
        return IISAdvancedLogger(path=path, logtype=logtype, set_location=set_location, hostname=self.hostname)
    advanced_logger = property(get_advanced_logger, doc='A read-only property which returns the advanced logger object from the IIS instance.')

    def has_item(self, item_type, item_name):
        'Generic method to look for a specific item'
        return item_name in getattr(self, f'{self._IIS_TYPE_MAP[item_type]}s')

    def manage_item(self, action, item_type, *args):
        'Manage an IIS object using the standard IIS appcmd'
        return appcmd(action, self._IIS_TYPE_MAP[item_type], *args, hostname=self.hostname, remote_powershell=self._remote_powershell)

    def has_virtual_dir(self, app_name):
        'Determine if the IIS instance has a specific web application'
        return self.has_item(VirtualDirectory, app_name)

    def get_virtual_dir(self, vdir_name):
        'Return an object instance of the requested web application'
        return VirtualDirectory(vdir_name, self)

    def create_virtual_dir(self, vdir_name, vdir_location, website):
        'Create the specific web application in the IIS instance'
        self.manage_item('add', VirtualDirectory, f'/app.name:{website}/', f'/path:/{vdir_name}', f'/physicalPath:{vdir_location}')
        return self.get_virtual_dir(vdir_name)

    def has_webapp(self, app_name):
        'Determine if the IIS instance has a specific web application'
        return self.has_item(WebApplication, app_name)

    def get_webapp(self, app_name):
        'Return an object instance of the requested web application'
        return WebApplication(app_name, self)

    def create_webapp(self, app_name, appdir, website, pool=None):
        'Create the specific web application in the IIS instance'
        self.manage_item('add', WebApplication, f'/site.name:{website}', f'/path:/{app_name}/', f'/physicalPath:{appdir}', f'/applicationPool:{pool}' if pool else '')
        return self.get_webapp(app_name)

    def remove_webapp(self, appname):
        'Remove the specific web application from the IIS instance'
        self.manage_item('delete', WebApplication, appname)

    def has_webapp_pool(self, pool_name):
        'Determine if the IIS instance has a specific web application pool'
        return self.has_item(WebApplicationPool, pool_name)

    def get_webapp_pool(self, pool_name):
        'Return an object instance of the requested web application'
        return WebApplicationPool(pool_name, self)

    def create_webapp_pool(self, pool_name):
        'Create the specific web application pool in the IIS instance'
        self.manage_item('add', WebApplicationPool, f'/name:{pool_name}')
        return self.get_webapp_pool(pool_name)

    def remove_webapp_pool(self, pool_name):
        'Remove the specific web application pool from the IIS instance'
        self.manage_item('delete', WebApplicationPool, pool_name)

    def has_website(self, site_name):
        'Determine if the IIS instance has a specific website'
        return self.has_item(WebSite, site_name)

    def get_website(self, site_name):
        'Return an object instance of the requested website'
        return WebSite(site_name, self)


class IISConfigurationSection:
    """Class to create a universal abstract interface for an IIS configuration section."""

    def __init__(self, name, path, set_location=None, hostname=None, remote_powershell=None):
        """
        Args:
            name: The name of the IIS configuration section.
            path: The path to the configuration section.
            set_location (optional, default=None): If not None, will be applied to the appcmd /commit option.
            hostname (optional, default=localhost): The name of the IIS server hosting the instance.
            remote_powershell (optional): Determines if PowerShell remoting is used when executing appcmd against a remote server.
                Defaults to False for hostname is None, otherwise defaults to True.

        Attributes:
            _hostname: The value of the hostname argument.
            _name: The value of the name argument.
            _path: The value of the path argument.
            _remote_powershell: The resolved value of the remote_powershell argument.
            _set_location: The value of the set_location argument.
        """
        self._name = name
        self._path = path if path else ''
        self._set_location = set_location
        self._hostname = hostname
        self._remote_powershell = (True if (remote_powershell is None) else remote_powershell) if hostname else False

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def __str__(self):
        return ''.join([l for l in self._run_appcmd('list', 'config', self._path, f'/section:{self._name}') if l.strip()])

    def __getattr__(self, attr):
        config = xmlparse_str(str(self))[0]
        if config.attrib['CONFIG.SECTION'] != self._name:
            raise IISConfigurationError(IISConfigurationError.PARSE_ERROR, expected=self._name)
        cfg_section = config.find(self._name.replace('/', '-'))
        if attr in cfg_section.attrib:
            return str_to_pythonval(cfg_section.attrib[attr])
        if attr.endswith('s') and cfg_section.findall('.//'+attr.rstrip('s')):
            return cfg_section.findall('.//'+attr.rstrip('s'))
        result = cfg_section.find(f'./[@{attr}]')
        if not result:
            raise AttributeError(attr)
        return result.text

    def __setattr__(self, attr, value):
        if attr.startswith('_'):
            super().__setattr__(attr, value)
            return
        if isinstance(value, bool):
            value = bool_to_str(value)
        self._run_appcmd('set', 'config', self._path, f'/section:{self._name}', f'/{attr}:{value}')

    def add_property(self, propname, value):
        'Adds a property with the specified value'
        self._run_appcmd('set', 'config', self._path, f'/section:{self._name}', f'/+{propname}.{value}')

    def rm_property(self, propname, value=None):
        'Removes a property conditionally with the specified value'
        propspec = f'{propname}.{value}' if value else propname
        self._run_appcmd('set', 'config', self._path, f'/section:{self._name}', f'/-{propspec}')

    def has_collection_member(self, collection, filter_on, value):
        'Determines if a collection has a specified member'
        return bool([m for m in getattr(self, collection) if m.attrib[filter_on] == value])

    def add_collection_member(self, collection, properties, changes):
        'Converts Python dictionaries to the syntax understood by appcmd'
        if changes:
            properties.update(changes)
        self.add_property(collection, dict2expat(properties))

    def rm_collection_member(self, collection, selectors):
        'Converts Python dictionaries to the syntax understood by appcmd'
        self.rm_property(collection, dict2expat(selectors))

    def _run_appcmd(self, *cmd_args):
        if self._set_location:
            cmd_args += [f'/commit:{self._set_location}']
        return appcmd(*cmd_args, hostname=self._hostname, remote_powershell=self._remote_powershell)


class IISAdvancedLogger(IISConfigurationSection):
    """Class to create a universal abstract interface for the IIS advanced logger."""

    def __init__(self, path, logtype, set_location, hostname=None, remote_powershell=None):
        """
        Args:
            path: The path to AdvancedLogger configuration section.
            logtype: The AdvancedLogger type.
            set_location: Passed to the base class.
            hostname (optional, default=localhost): The name of the IIS server hosting the instance.
            remote_powershell (optional): Determines if PowerShell remoting is used when executing appcmd against a remote server.
                Defaults to False for hostname is None, otherwise defaults to True.
        """
        super().__init__(f'advancedLogging/{logtype}', path=path, set_location=set_location, hostname=hostname, remote_powershell=remote_powershell)

    def add_field(self, field_id, field_values=None):
        'Adds a field to the advanced logger configuration'
        default_values = {'id': field_id,
                          'sourceName': field_id,
                          'sourceType': 'RequestHeader',
                          'logHeaderName': field_id,
                          'category': 'Default',
                          'description': '',
                          'defaultValue': '',
                          'loggingDataType': 'TypeLPCSTR'}
        if 'sourceName' not in field_values:
            default_values['sourceName'] = field_id
        self.add_collection_member('fields', default_values, field_values)

    def has_field(self, field_id):
        'Determines if the advanced logger configuration has the specified field'
        return self.has_collection_member('fields', 'id', field_id)

    def rm_field(self, field_id):
        'Removed a field from the advanced logger configuration'
        self.rm_collection_member('fields', {'id': field_id})

    def add_log(self, log_name, log_values=None, fields=None):
        'Adds a log definition to the advanced logger configuration'
        self.add_collection_member('logDefinitions',
                                   {'baseFileName': log_name,
                                    'writeLogDataToDisk': 'true',
                                    'enabled': 'true',
                                    'logRollOption': 'Schedule',
                                    'maxDurationSeconds': '86400',
                                    'maxFileSizeKB': '1024',
                                    'schedule': 'Hourly'},
                                   log_values)
        if fields:
            if not isinstance(fields, dict):
                fields = {f: dict() for f in fields}
        else:
            fields = dict()
        for (field, values) in fields.items():
            self.add_logfield(log_name, field, values)

    def rm_log(self, log_name):
        'Removes a log definition from the advanced logger configuration'
        self.rm_collection_member('logDefinitions', {'baseFileName': log_name})

    def add_logfield(self, log_name, field_name, field_values=None):
        'Adds a field to a log definition'
        if not self.has_collection_member('fields', 'id', field_name):
            raise IISAdvancedLogError(IISAdvancedLogError.BAD_FIELD, field=field_name)
        self.add_collection_member(f"logDefinitions.[baseFileName='{log_name}'].selectedFields",
                                   {'id': field_name,
                                    'logHeaderName': '',
                                    'required': 'false',
                                    'defaultValue': ''},
                                   field_values)

    def _run_appcmd(self, *cmd_args):
        try:
            return super()._run_appcmd(*cmd_args)
        except IISConfigurationError as err:
            if ('message' not in err.vars) or ('Unknown config section "advancedLogging' not in err.vars['message']):
                raise
        raise IISAdvancedLogError(IISAdvancedLogError.NOT_INSTALLED)


def dict2expat(py_dict):
    """Converts Python dictionaries to the syntax understood by the IIS appcmd command-line tool.

    Arguments:
        py_dict: The Python dictionary to convert.

    Returns:
        The appcmd format for the dictionary.
    """
    return '[' + ','.join([f"{k}='{v}'" for k, v in py_dict.items()]) + "]"


def appcmd(*cmd_args, hostname, **sys_cmd_args):
    """Interface to run the standard IIS appcmd command-line tool.

    Arguments:
        *cmd_args: The arguments to pass to appcmd.
        hostname: The hostname to pass to appcmd.
        **sys_cmd_args: The arguments to pass to syscmd when running appcmd.

    Returns:
        Nothing.

    Raises:
        AppCmdError.APPCMD_ERROR: If there are errors reported by appcmd.
    """
    _appcmd = Path(getenv('SystemRoot', ''), 'system32/inetsrv/appcmd.exe')

    if hostname and ('remote_powershell' not in sys_cmd_args):
        sys_cmd_args['remote_powershell'] = True
    try:
        return syscmd(_appcmd, *cmd_args, '/xml', remote=hostname, **sys_cmd_args)
    except CMDError as err:
        if ('outlines' not in err.vars) or not err.vars['outlines']:
            raise

        errmsg = xmlparse_list(err.vars['outlines']).find('ERROR')
        if errmsg is None:
            raise
        return_code = err.vars['returncode']

    err_object = AppCmdError(AppCmdError.APPCMD_ERROR, message=errmsg.attrib['message'])
    err_object.vars['returncode'] = return_code
    raise err_object

# cSpell:ignore iisreset inetsrv syscmd vdir
