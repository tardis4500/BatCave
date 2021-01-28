"""This module provides a Pythonic interface to work with Internet Information Server."""

# Import standard modules
from os import getenv
from pathlib import Path
from string import Template
from typing import Dict, List, Optional, Type
from xml.etree.ElementTree import fromstring as xmlparse_str, fromstringlist as xmlparse_list

# Import internal modules
from .sysutil import syscmd, CMDError
from .lang import bool_to_str, str_to_pythonval, BatCaveError, BatCaveException, CommandResult, PathName


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

    def __init__(self, name: str, iis_ref: 'IISInstance', /):
        """
        Args:
            name: The name of the object.
            iis_ref: A reference to the IIS owner instance.

        Attributes:
            _iis_ref: The value of the iis_ref argument.
            _name: The value of the name argument.
        """
        self._iis_ref = iis_ref
        self._name = name

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    iis_ref = property(lambda s: s._iis_ref, doc='A read-only property which returns the reference to the IIS object.')
    name = property(lambda s: s._name, doc='A read-only property which returns the name of the IIS object.')

    def manage_item(self, action: str, /) -> None:
        """Perform action on this object.

        Args:
            action: The action to perform on this object.

        Returns:
            Nothing.
        """
        self.iis_ref.manage_item(action, type(self), self.name)

    def start(self) -> None:
        """Start this object.

        Returns:
            Nothing.
        """
        self.manage_item('start')

    def stop(self) -> None:
        """Stop this object.

        Returns:
            Nothing.
        """
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


class IISInstance:  # pylint: disable=too-many-public-methods
    """Class to create a universal abstract interface for an IIS instance.

    Attributes:
        _IIS_TYPE_MAP: Maps IIS object types to appcmd subcommands.
    """
    _IIS_TYPE_MAP = {VirtualDirectory: 'VDIR',
                     WebApplication: 'APP',
                     WebApplicationPool: 'APPPOOL',
                     WebSite: 'SITE'}

    def __init__(self, hostname: Optional[str] = None, /, *, remote_powershell: Optional[bool] = None):
        """
        Args:
            hostname (optional, default=localhost): The name of the IIS server hosting the instance.
            remote_powershell (optional): Determines if PowerShell remoting is used when executing appcmd against a remote server.
                Defaults to False for hostname is None, otherwise defaults to True.

        Attributes:
            _hostname: The value of the hostname argument.
            _remote_powershell: The resolved value of the remote_powershell argument.
        """
        self._hostname = hostname
        self._remote_powershell = (True if (remote_powershell is None) else remote_powershell) if hostname else False

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def __getattr__(self, attr: str) -> List[str]:
        tag = attr.upper()[0:-1]
        result = [i.attrib[f'{tag}.NAME'].rstrip('/') for i in xmlparse_list(appcmd('list', attr, hostname=self.hostname, remote_powershell=self._remote_powershell)).findall(tag)]
        if not result:
            raise AttributeError(attr)
        return result

    hostname = property(lambda s: s._hostname, doc='A read-only property which returns the hostname of the IIS server.')

    def create_virtual_dir(self, vdir_name: str, /, vdir_location: PathName, website: str) -> VirtualDirectory:
        """Create the specified virtual directory in the IIS instance.

        Args:
            vdir_name: The name of the virtual directory to create.
            vdir_location: The physical path for the virtual directory.
            website: The website for which to create the virtual directory.

        Returns:
            The newly created virtual directory.
        """
        self.manage_item('add', VirtualDirectory, f'/app.name:{website}/', f'/path:/{vdir_name}', f'/physicalPath:{vdir_location}')
        return self.get_virtual_dir(vdir_name)

    def create_webapp(self, app_name: str, appdir: PathName, website: str, pool: Optional[WebApplicationPool] = None) -> WebApplication:
        """Create the specified web application in the IIS instance.

        Args:
            app_name: The name of the web application to create.
            appdir: The physical path for the web application.
            website: The website for which to create the virtual directory.
            pool (optional, default=None): If not None, the application pool to which to assign the web application.

        Returns:
            The newly created web application.
        """
        self.manage_item('add', WebApplication, f'/site.name:{website}', f'/path:/{app_name}/', f'/physicalPath:{appdir}', f'/applicationPool:{pool}' if pool else '')
        return self.get_webapp(app_name)

    def create_webapp_pool(self, pool_name: str, /) -> WebApplicationPool:
        """Create the specified web application pool in the IIS instance.

        Args:
            pool_name: The name of the web application to create.

        Returns:
            The newly created web application pool.
        """
        self.manage_item('add', WebApplicationPool, f'/name:{pool_name}')
        return self.get_webapp_pool(pool_name)

    def exists(self) -> bool:
        """Test for existence of the IIS instance.

        Returns:
            True if the instance exists, False, otherwise.
        """
        try:
            str(self.get_configuration_section('log'))
        except CMDError as err:
            if err.code == CMDError.CMD_ERROR.code:
                return False
            raise
        return True

    def get_advanced_logger(self, path: Optional[PathName] = None, logtype: str = 'server', set_location: str = 'apphost') -> 'IISAdvancedLogger':
        """Get the advanced logger object from the IIS instance.

        Args:
            path (optional, default=None): If not None, return the advanced logger from the specified path.
            logtype (optional, default='server'): Use the specified set location to search for the advanced logger.
            set_location (optional, default='apphost'): Use the specified set location to search for the advanced logger.

        Returns:
            The specified advanced logger.
        """
        return IISAdvancedLogger(path, logtype=logtype, set_location=set_location, hostname=self.hostname)

    advanced_logger = property(get_advanced_logger, doc='A read-only property which returns the advanced logger object from the IIS instance.')

    def get_configuration_section(self, name: str, /, path: Optional[PathName] = None, set_location: str = 'apphost') -> 'IISConfigurationSection':
        """Get the named configuration section from the IIS configuration files.

        Args:
            name: The name of the configuration section to return.
            path (optional, default=None): If not None, return the configuration section from the specified path.
            set_location (optional, default='apphost'): Use the specified set location to search for the configuration section.

        Returns:
            The specified configuration section.
        """
        return IISConfigurationSection(name, path=path, set_location=set_location, hostname=self.hostname, remote_powershell=self._remote_powershell)

    def get_virtual_dir(self, vdir_name: str, /) -> VirtualDirectory:
        """Get the specified virtual directory from the IIS instance.

        Args:
            vdir_name: The name of the virtual directory to return.

        Returns:
            The virtual directory from the IIS instance.
        """
        return VirtualDirectory(vdir_name, self)

    def get_webapp(self, app_name: str, /) -> WebApplication:
        """Get the specified web application from the IIS instance.

        Args:
            app_name: The name of the web application to return.

        Returns:
            The web application from the IIS instance.
        """
        return WebApplication(app_name, self)

    def get_webapp_pool(self, pool_name: str, /) -> WebApplicationPool:
        """Get the specified web application pool from the IIS instance.

        Args:
            pool_name: The name of the web application pool to return.

        Returns:
            The web application pool from the IIS instance.
        """
        return WebApplicationPool(pool_name, self)

    def get_website(self, site_name: str, /) -> WebSite:
        """Get the specified website from the IIS instance.

        Args:
            site_name: The name of the website to return.

        Returns:
            The website from the IIS instance.
        """
        return WebSite(site_name, self)

    def has_item(self, item_type: Type[IISObject], item_name: str, /) -> bool:
        """Determine if the specified item of the specified type exists in the IIS instance.

        Args:
            item_type: The type of the item for which to search.
            item_name: The name of the item for which to search.

        Returns:
            True if the item exists in the IIS instance, False otherwise.
        """
        return item_name in getattr(self, f'{self._IIS_TYPE_MAP[item_type]}s')

    def has_virtual_dir(self, vdir_name: str, /) -> bool:
        """Determine if the IIS instance has the specified virtual directory.

        Args:
            vdir_name: The name of the virtual directory for which to search.

        Returns:
            True if the virtual directory exists in the IIS instance, False otherwise.
        """
        return self.has_item(VirtualDirectory, vdir_name)

    def has_webapp(self, app_name: str, /) -> bool:
        """Determine if the IIS instance has the specified web application.

        Args:
            app_name: The name of the web application for which to search.

        Returns:
            True if the web application exists in the IIS instance, False otherwise.
        """
        return self.has_item(WebApplication, app_name)

    def has_webapp_pool(self, pool_name: str, /) -> bool:
        """Determine if the IIS instance has the specified web application pool.

        Args:
            pool_name: The name of the web application pool for which to search.

        Returns:
            True if the web application pool exists in the IIS instance, False otherwise.
        """
        return self.has_item(WebApplicationPool, pool_name)

    def has_website(self, site_name: str, /) -> bool:
        """Determine if the IIS instance has the specified website.

        Args:
            site_name: The name of the web application for which to search.

        Returns:
            True if the website exists in the IIS instance, False otherwise.
        """
        return self.has_item(WebSite, site_name)

    def manage_item(self, action: str, item_type: Type[IISObject], /, *args) -> CommandResult:
        """Manage an IIS object using the standard IIS appcmd.

        Args:
            action: The management action to perform.
            item_type: The type of the item to manage.
            *args (optional, default=[]): Any other appcmd arguments to pass to the management action.

        Returns:
            The result of the appcmd command.
        """
        return appcmd(action, self._IIS_TYPE_MAP[item_type], *args, hostname=self.hostname, remote_powershell=self._remote_powershell)

    def remove_webapp(self, appname: str, /) -> None:
        """Remove the specified web application from the IIS instance.

        Args:
            appname: The name of the web application to remove.

        Returns:
            Nothing.
        """
        self.manage_item('delete', WebApplication, appname)

    def remove_webapp_pool(self, pool_name: str, /) -> None:
        """Remove the specified web application pool from the IIS instance.

        Args:
            appname: The name of the web application pool to remove.

        Returns:
            Nothing.
        """
        self.manage_item('delete', WebApplicationPool, pool_name)

    def reset(self, verbose: bool = True) -> CommandResult:
        """Reset the IIS instance.

        Args:
            quiet (optional, default=False): If True do not print result to standard output stream.

        Returns:
            The result of the reset command.
        """
        return syscmd('iisreset', remote=self.hostname, show_stdout=not verbose)

    def start(self, quiet: bool = False) -> CommandResult:
        """Start the IIS instance.

        Args:
            quiet (optional, default=False): If True do not print result to standard output stream.

        Returns:
            The result of the start command.
        """
        return syscmd('iisreset', '/start', remote=self.hostname, show_stdout=not quiet)

    def stop(self, quiet: bool = False) -> CommandResult:
        """Stop the IIS instance.

        Args:
            quiet (optional, default=False): If True do not print result to standard output stream.

        Returns:
            The result of the stop command.
        """
        return syscmd('iisreset', '/stop', remote=self.hostname, show_stdout=not quiet)


class IISConfigurationSection:
    """Class to create a universal abstract interface for an IIS configuration section."""

    def __init__(self, name: str, /, path: Optional[PathName], set_location: Optional[str] = None,
                 hostname: Optional[str] = None, remote_powershell: Optional[bool] = None):
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
        return ''.join([line for line in self._run_appcmd('list', 'config', self._path, f'/section:{self._name}') if line.strip()])

    def __getattr__(self, attr: str) -> str:
        if (config := xmlparse_str(str(self))[0]).attrib['CONFIG.SECTION'] != self._name:
            raise IISConfigurationError(IISConfigurationError.PARSE_ERROR, expected=self._name)
        result = None
        if cfg_section := config.find(self._name.replace('/', '-')):
            if attr in cfg_section.attrib:
                return str_to_pythonval(cfg_section.attrib[attr])
            if attr.endswith('s'):
                if cfg_section_plural := cfg_section.findall('.//' + attr.rstrip('s'))[0]:
                    return str(cfg_section_plural.text)
            result = cfg_section.find(f'./[@{attr}]')
        if not result:
            raise AttributeError(attr)
        return str(result.text)

    def __setattr__(self, attr: str, value: str) -> None:
        if attr.startswith('_'):
            super().__setattr__(attr, value)
            return
        if isinstance(value, bool):
            value = bool_to_str(value)
        self._run_appcmd('set', 'config', self._path, f'/section:{self._name}', f'/{attr}:{value}')

    def _run_appcmd(self, *args) -> CommandResult:
        """Run the IIS appcmd against this IIS configuration section.

        Args:
            *args: The arguments to pass to appcmd.

        Returns:
            The output from appcmd.
        """
        cmd_args = list(args)
        if self._set_location:
            cmd_args += [f'/commit:{self._set_location}']
        return appcmd(*cmd_args, hostname=self._hostname, remote_powershell=self._remote_powershell)

    def add_collection_member(self, collection: str, /, properties: Dict, changes: Optional[Dict]) -> None:
        """Add the specified properties to the collection.

        Args:
            collection: The collection to which to add the properties.
            properties: The properties to add to the collection.
            changes: Changes to make to the properties before adding.

        Returns:
            Nothing.
        """
        if changes:
            properties.update(changes)
        self.add_property(collection, dict2expat(properties))

    def add_property(self, propname: str, value: str, /) -> None:
        """Add a property with the specified value.

        Args:
            propname: The name of the property to add.
            value: The value of the property to add.

        Returns:
            Nothing.
        """
        self._run_appcmd('set', 'config', self._path, f'/section:{self._name}', f'/+{propname}.{value}')

    def has_collection_member(self, collection: str, /, filter_on: str, value: str) -> bool:
        """Determine if a collection has a specified member.

        Args:
            collection: The collection to search.
            filter_on: Then member to filter on.
            value: The value for which to search.

        Returns:
            True if the collection has the specified member, False otherwise.
        """
        return bool([m for m in getattr(self, collection) if m.attrib[filter_on] == value])

    def rm_collection_member(self, collection: str, /, selectors: Dict) -> None:
        """Remove the specified properties from the collection.

        Args:
            collection: The collection from which to remove the properties.
            selectors: The selectors to identify the properties.

        Returns:
            Nothing.
        """
        self.rm_property(collection, dict2expat(selectors))

    def rm_property(self, propname: str, value: Optional[str] = None, /) -> None:
        """Remove a property conditionally with the specified value.

        Args:
            propname: The name of the property to remove.
            value (optional, default=None): If not None, only remove the property if it has the specified value.

        Returns:
            Nothing.
        """
        propspec = f'{propname}.{value}' if value else propname
        self._run_appcmd('set', 'config', self._path, f'/section:{self._name}', f'/-{propspec}')


class IISAdvancedLogger(IISConfigurationSection):
    """Class to create a universal abstract interface for the IIS advanced logger."""

    def __init__(self, path: Optional[PathName], /, logtype: str, set_location: str,
                 hostname: Optional[str] = None, remote_powershell: Optional[bool] = None):
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

    def _run_appcmd(self, *cmd_args) -> CommandResult:
        """Run the IIS appcmd against this IIS advanced logger configuration.

        Args:
            *cmd_args: The arguments to pass to appcmd.

        Returns:
            The output from appcmd.
        """
        try:
            return super()._run_appcmd(*cmd_args)
        except IISConfigurationError as err:
            if ('message' not in err.vars) or ('Unknown config section "advancedLogging' not in err.vars['message']):
                raise
        raise IISAdvancedLogError(IISAdvancedLogError.NOT_INSTALLED)

    def add_field(self, field_id: str, field_values: Optional[Dict] = None, /) -> None:
        """Add a field to the advanced logger configuration.

        Args:
            field_id: The field ID to add.
            field_values (optional, default=dict()): Any field values to add to override the default values.

        Returns:
            Nothing.
        """
        default_values = {'id': field_id,
                          'sourceName': field_id,
                          'sourceType': 'RequestHeader',
                          'logHeaderName': field_id,
                          'category': 'Default',
                          'description': '',
                          'defaultValue': '',
                          'loggingDataType': 'TypeLPCSTR'}
        if field_values and 'sourceName' not in field_values:
            default_values['sourceName'] = field_id
        self.add_collection_member('fields', default_values, field_values)

    def add_log(self, log_name: str, /, log_values: Optional[Dict] = None, fields: Optional[Dict] = None) -> None:
        """Add a log definition to the advanced logger configuration.

        Args:
            log_name: The name of the log to add.
            log_values (optional, default=None): Any log values to add to override the default values.
            fields (optional, default=None): Any fields to add to the log definition.

        Returns:
            Nothing.
        """
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

    def add_logfield(self, log_name: str, field_name: str, field_values: Optional[Dict] = None, /) -> None:
        """Add a field to an advanced logger log definition.

        Args:
            log_name: The name of the log to which to add the field.
            field_name: The name of the field to add.
            field_values (optional, default=None): Any fields values to add to the field.

        Returns:
            Nothing.
        """
        if not self.has_collection_member('fields', 'id', field_name):
            raise IISAdvancedLogError(IISAdvancedLogError.BAD_FIELD, field=field_name)
        self.add_collection_member(f"logDefinitions.[baseFileName='{log_name}'].selectedFields",
                                   {'id': field_name,
                                    'logHeaderName': '',
                                    'required': 'false',
                                    'defaultValue': ''},
                                   field_values)

    def has_field(self, field_id: str, /) -> bool:
        """Determine if the advanced logger configuration has the specified field.

        Args:
            field_id: The field ID for which to search.

        Returns:
            True if the advanced logger configuration has the specified field, False otherwise.
        """
        return self.has_collection_member('fields', 'id', field_id)

    def rm_field(self, field_id: str, /) -> None:
        """Remove a field from the advanced logger configuration.

        Args:
            field_id: The field ID to remove.

        Returns:
            Nothing.
        """
        self.rm_collection_member('fields', {'id': field_id})

    def rm_log(self, log_name: str, /) -> None:
        """Remove a log definition to the advanced logger configuration.

        Args:
            log_name: The name of the log to remove.

        Returns:
            Nothing.
        """
        self.rm_collection_member('logDefinitions', {'baseFileName': log_name})


def appcmd(*cmd_args, hostname: Optional[str], **sys_cmd_args) -> CommandResult:
    """Interface to run the standard IIS appcmd command-line tool.

    Args:
        *cmd_args: The arguments to pass to appcmd.
        hostname: The hostname to pass to appcmd.
        **sys_cmd_args: The arguments to pass to syscmd when running appcmd.

    Returns:
        The result of the appcmd call.

    Raises:
        AppCmdError.APPCMD_ERROR: If there are errors reported by appcmd.
    """
    _appcmd = Path(getenv('SystemRoot', ''), 'system32/inetsrv/appcmd.exe')

    if hostname and ('remote_powershell' not in sys_cmd_args):
        sys_cmd_args['remote_powershell'] = True
    try:
        return syscmd(str(_appcmd), *cmd_args, '/xml', remote=hostname, **sys_cmd_args)
    except CMDError as err:
        if ('outlines' not in err.vars) or not err.vars['outlines']:
            raise

        if (errmsg := xmlparse_list(err.vars['outlines']).find('ERROR')) is None:
            raise
        return_code = err.vars['returncode']

    err_object = AppCmdError(AppCmdError.APPCMD_ERROR, message=errmsg.attrib['message'])
    err_object.vars['returncode'] = return_code
    raise err_object


def dict2expat(py_dict: Dict, /) -> str:
    """Converts Python dictionaries to the syntax understood by the IIS appcmd command-line tool.

    Args:
        py_dict: The Python dictionary to convert.

    Returns:
        The appcmd format for the dictionary.
    """
    return '[' + ','.join([f"{k}='{v}'" for k, v in py_dict.items()]) + "]"

# cSpell:ignore iisreset inetsrv syscmd vdir
