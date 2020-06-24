"""This module provides utilities for working with servers.

Attributes:
    _STATUS_CHECK_INTERVAL (int, default=2): This is the default wait in seconds when performing any checks.
"""
# pylint: disable=invalid-name

# Import standard modules
from csv import DictReader
from enum import Enum
from os import getenv
from pathlib import Path
from platform import node
from socket import getfqdn, gethostbyname, gaierror
from string import Template
from time import sleep
from typing import Any, Union
from xml.etree.ElementTree import SubElement, parse as xmlparse

# Import third-party modules
from psutil import process_iter, NoSuchProcess, Process as _LinuxProcess

# Import internal modules
from .serverpath import ServerPath
from .sysutil import syscmd, CMDError
from .lang import switch, BatCaveError, BatCaveException, WIN32

if WIN32:
    from pywintypes import com_error  # pylint: disable=E0611
    from win32com.client import CDispatch, DispatchEx
    from wmi import WMI, x_wmi
    from .iispy import IISInstance
else:
    class x_wmi(Exception):
        'Needed to avoid errors on Linux'

_STATUS_CHECK_INTERVAL = 2

OsType = Enum('OsType', ('linux', 'windows'))
ProcessSignal = Enum('ProcessSignal', ('stop', 'kill'))
ServiceSignal = Enum('ServiceSignal', ('disable', 'enable', 'start', 'stop', 'pause', 'resume', 'restart'))
ServiceState = Enum('ServiceState', ('StartPending', 'ContinuePending', 'Running', 'StopPending', 'Stopped', 'PausePending', 'Paused'))
ServiceType = Enum('ServiceType', ('systemd', 'sysv', 'upstart', 'windows'))
TaskSignal = Enum('TaskSignal', ('enable', 'disable', 'run', 'end'))

ServerType = Union[str, 'Server']


class ServerObjectManagementError(BatCaveException):
    """Server Exceptions.

    Attributes:
        BAD_FILTER: Multiple filters were specified when only one is allowed.
        BAD_OBJECT_SIGNAL: The signal type is invalid.
        BAD_OBJECT_STATE: The object state is unknown.
        BAD_TRANSITION: The object state transition was unexpected.
        OBJECT_NOT_FOUND: The requested object was not found.
        REMOTE_CONNECTION_ERROR: The was an error attempting to connect to the remote server.
        REMOTE_NOT_SUPPORTED: The request action is not supported for remote servers.
        SERVER_NOT_FOUND: The requested server was not found.
        NOT_UNIQUE: A unique instance of the object was not found.
        STATUS_CHECK_TIMEOUT: The was a timeout checking for the status of the object.
        WMI_ERROR: The was a WMI error.
    """
    BAD_FILTER = BatCaveError(1, 'One and only one filter must be provided for this object')
    BAD_OBJECT_SIGNAL = BatCaveError(2, Template('Unknown object signal: $signal'))
    BAD_OBJECT_STATE = BatCaveError(3, Template('Unknown object state: $state'))
    BAD_TRANSITION = BatCaveError(4, Template('Invalid state transition from $from_state to $to_state'))
    NOT_UNIQUE = BatCaveError(5, Template('Unable to locate unique $type according to $filters'))
    OBJECT_NOT_FOUND = BatCaveError(6, Template('No $type object found'))
    REMOTE_CONNECTION_ERROR = BatCaveError(7, Template('Unable to connect to remote server $server: $msg'))
    REMOTE_NOT_SUPPORTED = BatCaveError(8, 'Remote objects are not supported for Linux servers')
    SERVER_NOT_FOUND = BatCaveError(9, Template('No server found: $server'))
    STATUS_CHECK_TIMEOUT = BatCaveError(10, Template('Timeout waiting for expected $type state: $state'))
    WMI_ERROR = BatCaveError(11, Template('WMI error on server $server: $msg'))


class Server:
    """Class to create a universal abstract interface for a server.

    Attributes:
        _WSA_NAME_OR_SERVICE_NOT_KNOWN: Error code indicating the service is unknown.
        _WSAHOST_NOT_FOUND: Error code indicating the host was not found.
        _WMI_SERVICE_CREATE_ERRORS: A dictionary to map WMI errors to errors messages.
    """
    _WMI_SERVICE_CREATE_ERRORS = {1: 'The request is not supported.',
                                  2: 'The user did not have the necessary access.',
                                  3: 'The service cannot be stopped because other services that are running are dependent on it.',
                                  4: 'The requested control code is not valid, or it is unacceptable to the service.',
                                  5: 'The requested control code cannot be sent to the service because the state of the service (State property of the Win32_BaseService class) is equal to 0, 1, or 2.',  # noqa: E501, pylint: disable=line-too-long
                                  6: 'The service has not been started.',
                                  7: 'The service did not respond to the start request in a timely fashion.',
                                  8: 'Unknown failure when starting the service.',
                                  9: 'The directory path to the service executable file was not found.',
                                  10: 'The service is already running.',
                                  11: 'The database to add a new service is locked.',
                                  12: 'A dependency this service relies on has been removed from the system.',
                                  13: 'The service failed to find the service needed from a dependent service.',
                                  14: 'The service has been disabled from the system.',
                                  15: 'The service does not have the correct authentication to run on the system.',
                                  16: 'This service is being removed from the system.',
                                  17: 'The service has no execution thread.',
                                  18: 'The service has circular dependencies when it starts.',
                                  19: 'A service is running under the same name.',
                                  20: 'The service name has invalid characters.',
                                  21: 'Invalid parameters have been passed to the service.',
                                  22: 'The account under which this service runs is either invalid or lacks the permissions to run the service.',
                                  23: 'The service exists in the database of services available from the system.',
                                  24: 'The service is currently paused in the system.'}
    _WSA_NAME_OR_SERVICE_NOT_KNOWN = -2
    _WSAHOST_NOT_FOUND = 11001

    def __init__(self, hostname=None, domain=None, auth=None, defer_wmi=True, ip=None, os_type=OsType.windows if WIN32 else OsType.linux):
        """
        Args:
            hostname (optional): The server hostname. If not specified, will default to the name of the localhost.
            domain (optional): The server domain. If not specified, will default to the domain of the localhost.
            auth (optional, default=None): A tuple of (username, password) for access to the host if remote.
            defer_wmi (optional, default=True): Only valid for Windows servers. If True, defers initializing the WMI interface until first use.
            ip (optional): The server IP address. If not specified, will default to the IP of the localhost.
            os_type (optional): The server type. If not specified, will default to the type of the localhost.

        Attributes:
            auth: The value of the auth argument.
            domain: The derived value of the domain argument.
            hostname: The derived value of the hostname argument.
            ip: The derived value of the ip argument.
            is_local: True if the server is localhost, False otherwise.
            os_type: The value of the os_type argument.
            _os_manager: The remote management interface for remote servers, None otherwise.
            _wmi_manager: The WMI object.

        Raises:
            ServerObjectManagementError.SERVER_NOT_FOUND: If the remote server IP is not found.
        """
        self.hostname = (hostname if hostname else node().split('.')[0]).lower()
        try:
            self.domain = (domain if domain else getfqdn().split('.', 1)[1]).lower()
        except IndexError:
            self.domain = None
        self.auth = auth
        self.ip = ip
        self.os_type = os_type
        self._wmi_manager = None
        if not self.ip:
            try:
                self.ip = gethostbyname(self.fqdn)
            except gaierror as err:
                server_found = False
                if err.errno not in (self._WSAHOST_NOT_FOUND, self._WSA_NAME_OR_SERVICE_NOT_KNOWN):
                    raise
            else:
                server_found = True
            if not server_found:
                if self.is_local:
                    self.ip = '127.0.0.1'
                else:
                    raise ServerObjectManagementError(ServerObjectManagementError.SERVER_NOT_FOUND, server=self.fqdn)
        self._os_manager = OSManager(None if self.is_local else self.hostname, self.auth)
        if not defer_wmi:
            self._connect_wmi()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def _connect_wmi(self):
        """Make a WMI connection to the server.

        Returns:
            Nothing.

        Raises:
            ServerObjectManagementError.REMOTE_CONNECTION_ERROR: If there was an error connecting to the WMI manager.
        """
        manager_args = dict() if self.is_local else {'computer': self.hostname}
        if self.auth:
            manager_args['user'] = self.auth[0]
            manager_args['password'] = self.auth[1]

        raise_error = False
        try:
            self._wmi_manager = WMI(**manager_args)
        except x_wmi as err:
            raise_error = err
        if raise_error:
            raise ServerObjectManagementError(ServerObjectManagementError.REMOTE_CONNECTION_ERROR, server=self.hostname, msg=str(raise_error))

    def _get_object_manager(self, item_type, wmi):
        """Return the correct object manager for the platform and item type.

        Args:
            item_type: The item type for which the object manager is requested.
            wmi: The WMI manager.

        Returns:
            The object manager.

        Raises:
            ServerObjectManagementError.REMOTE_NOT_SUPPORTED: If the platform is Linux or the item_type is Service.
        """
        if (item_type != 'Service') and (self.os_type != self.OS_TYPES.windows) and not self.is_local:
            raise ServerObjectManagementError(ServerObjectManagementError.REMOTE_NOT_SUPPORTED)
        if wmi and not self._wmi_manager:
            self._connect_wmi()
        return self._wmi_manager if wmi else self._os_manager

    fqdn = property(lambda s: f'{s.hostname}.{s.domain}' if s.domain else s.hostname, doc='A read-only property which returns the full-qualified domain name of the server.')
    is_local = property(lambda s: getfqdn().lower() == s.fqdn, doc='A read-only property which returns True if the server is the local host.')

    def create_management_object(self, item_type, unique_id, wmi=True if WIN32 else False, error_if_exists=True, **key_args):
        """Create a management object of the specified type.

        Args:
            item_type: The item type of the object to create.
            unique_id: The unique object identifier.
            wmi (optional): True if this is a Windows platform, False otherwise.
            error_if_exists (optional, default=True): If True raise an error if the object already exists.
            **key_args (optional, default={}): A dictionary of key value pairs to pass to add to the create object.

        Returns:
            The created management object.

        Raises:
            ServerObjectManagementError.WMI_ERROR: If there was an error creating the object.
        """
        manager = self._get_object_manager(item_type, wmi)
        unique_key = 'ProcessId' if (item_type == 'Process') else 'Name'
        creation_args = {unique_key: unique_id, 'DisplayName': unique_id}

        created_object = self.get_unique_object(item_type, wmi, **{unique_key: unique_id})
        if error_if_exists or not created_object:
            result = getattr(manager, ManagementObject.OBJECT_PREFIX + item_type).Create(**creation_args, **key_args)[0]
        else:
            result = False

        if result:
            msg = self._WMI_SERVICE_CREATE_ERRORS[result] if (result in self._WMI_SERVICE_CREATE_ERRORS) else f'Return value: {result}'
            raise ServerObjectManagementError(ServerObjectManagementError.WMI_ERROR, server=self.hostname, msg=msg)

        if not created_object:
            created_object = self.get_unique_object(item_type, wmi, **{unique_key: unique_id})
        return globals()[item_type](created_object, manager, unique_key, unique_id)

    def create_scheduled_task(self, task, exe, schedule_type, schedule, user=None, password=None, start_in=None, disable=False):
        """Create a scheduled task.

        Args:
            task: The name of the scheduled task to create.
            exe: The executable the scheduled task will run.
            schedule_type: The schedule type.
            schedule: The schedule on which to run the task.
            user (optional, default=None): In not None, the user account that the task will run under.
            password (optional, default=None): The password for the user account that the task will run under.
            start_in (optional, default=None): If not None, the directory in which the task will start.
            disable (optional, default=False): If True the task will be created as disabled.

        Returns:
            The created scheduled task.
        """
        if isinstance(exe, str):
            exe_args = list()
        else:
            exe_args = exe[1:]
            exe = exe[0]

        create_base = ['/Create', '/F', '/TN', task]
        cmd_args = create_base + ['/TR', ' '.join([f'"{exe}"'] + exe_args),
                                  '/SC', schedule_type,
                                  ('/ST' if (schedule_type.lower() == 'daily') else '/MO'), schedule]

        if user:
            cmd_args += ['/RU', user]
        if password:
            cmd_args += ['/RP', password]
        if not self.is_local:
            cmd_args += ['/S', self.hostname]
        if self.auth:
            cmd_args += ['/U', self.auth[0], '/P', self.auth[1]]
        _run_task_scheduler(*cmd_args)
        task_object = self.get_scheduled_task(task)

        if disable:
            task_object.manage(ScheduledTask.TaskSignal.disable)

        if start_in is None:
            start_in = Path(exe).parent
        if start_in:
            task_file = ScheduledTask.TASK_HOME / task
            task_xml = xmlparse(task_file)
            exec_el = task_xml.find('ns:Actions/ns:Exec', {'ns': ScheduledTask.TASK_NAMESPACE})
            SubElement(exec_el, f'{{{ScheduledTask.TASK_NAMESPACE}}}WorkingDirectory').text = str(start_in)
            task_xml.write(task_file)
            cmd_args = create_base + ['/XML', str(task_file)]
            if password:
                cmd_args += ['/RU', user, '/RP', password]
            _run_task_scheduler(*cmd_args)

        return task_object

    def create_service(self, service, exe, user=None, password=None, start=False, timeout=False, error_if_exists=True):
        """Create a service.

        Args:
            service: The name of the service to create.
            exe: The executable the service will run.
            user (optional, default=None): In not None, the user account that the service will run under.
            password (optional, default=None): The password for the user account that the service will run under.
            timeout (optional, default=False): If not False, the number of seconds to wait for the service to start.
            error_if_exists (optional, default=True): If True raise an error if the object already exists.

        Returns:
            The created service.
        """
        service_obj = self.create_management_object('Service', service, PathName=str(exe), StartName=user, StartPassword=password, error_if_exists=error_if_exists)
        if start:
            service_obj.manage(Service.ServiceSignal.start, timeout=timeout)
        return service_obj

    def get_iis_instance(self):
        """Get the IIS instance for this server.

        Returns:
            The IIS instance for this server.
        """
        return IISInstance(self.fqdn if not self.is_local else None)

    def get_management_objects(self, item_type, wmi=True if WIN32 else False, **filters):
        """Get a list of management objects.

        Args:
            item_type: The item type of the objects.
            wmi (optional): True if this is a Windows platform, False otherwise.
            **filters (optional, default={}): A dictionary of filters to pass to the manager to filter the objects returned.

        Returns:
            The list of management objects.
        """
        manager = self._get_object_manager(item_type, wmi)
        unique_key = 'ProcessId' if (item_type == 'Process') else 'Name'
        extra_keys = dict()
        for (key, item_list) in {'service_type': 'Service'}.items():
            if (item_type in item_list) and (key in filters):
                if self.os_type != self.OS_TYPES.windows:
                    extra_keys[key] = filters[key]
                else:
                    del filters[key]
        return [globals()[item_type](r, manager, unique_key, getattr(r, unique_key), **extra_keys) for r in getattr(manager, ManagementObject.OBJECT_PREFIX + item_type)(**filters)]

    def get_object_by_name(self, item_type, name, wmi=True if WIN32 else False, **filters):
        """Get a management object by name.

        Args:
            item_type: The item type of the object.
            name: The name of the object.
            wmi (optional): True if this is a Windows platform, False otherwise.
            **filters (optional, default={}): A dictionary of filters to pass to the manager to filter for the object.

        Returns:
            The requested management object.

        Raises:
            ServerObjectManagementError.NOT_UNIQUE: If more than one management object was found.
        """
        return self.get_unique_object(item_type, wmi, Name=name, **filters)

    def get_path(self, the_path):
        """Get the specified path as a ServerPath object.

        Args:
            the_path: The path to return.

        Return:
            The specified path as a ServerPath object.
        """
        return ServerPath(self, the_path)

    def get_process_connection(self, process):
        """Get a COM connection to the specified process.

        Returns:
            The COM connection to the specified process.
        """
        return COMObject(process, self.ip)

    def get_process_list(self, **filters):
        """Get the process list for this server.

        Returns:
            The process list for this server.
        """
        return self.get_management_objects('Process', **filters)

    def get_scheduled_task(self, task):
        """Get the specified scheduled task.

        Returns:
            The specified scheduled task.
        """
        return self.get_object_by_name('ScheduledTask', task, False)

    def get_scheduled_task_list(self):
        """Get the scheduled tasks for this server.

        Returns:
            The scheduled tasks for this server.
        """
        cmd_args = ['/Query', '/FO', 'CSV']
        if not self.is_local:
            cmd_args += ['/S', self.fqdn]
        if self.auth:
            cmd_args += ('/U', self.auth[0], '/P', self.auth[1])
        return [self.get_scheduled_task(t['TaskName']) for t in DictReader(_run_task_scheduler(*cmd_args))]

    def get_service(self, service, **key_args):
        """Get the specified service.

        Args:
            **key_args (optional, default={}): A dictionary of key value pairs to apply as filters when retrieving the service.

        Returns:
            The specified service.
        """
        if 'service_type' not in key_args:
            if self.os_type == self.OS_TYPES.windows:
                service_type = Service.ServiceType.windows
            elif self.get_path('/sbin/initctl').exists():
                service_type = Service.ServiceType.upstart
            elif self.get_path('/bin/systemctl').exists():
                service_type = Service.ServiceType.systemd
            else:
                service_type = Service.ServiceType.sysv
            key_args['service_type'] = service_type
        return self.get_object_by_name('Service', service, **key_args)

    def get_service_list(self, service_type=None):
        """Get the services for this server.

        Args:
            service_type (optional, default=None): If None, determine the service type based on the OS.

        Returns:
            The services for this server.
        """
        if service_type is None:
            if self.os_type == self.OS_TYPES.windows:
                service_type = Service.ServiceType.windows
            elif self.get_path('/sbin/initctl').exists():
                service_type = Service.ServiceType.upstart
            elif self.get_path('/bin/systemctl').exists():
                service_type = Service.ServiceType.systemd
            else:
                service_type = Service.ServiceType.sysv
        return self.get_management_objects('Service', service_type=service_type)

    def get_unique_object(self, item_type, wmi=True if WIN32 else False, **filters):
        """Get the requested management object which must be unique.

        Args:
            item_type: The item type of the object.
            wmi (optional): True if this is a Windows platform, False otherwise.
            **filters (optional, default={}): A dictionary of filters to pass to the manager to filter for the object.

        Returns:
            The requested management object.

        Raises:
            ServerObjectManagementError.NOT_UNIQUE: If more than one management object was found.
        """
        results = self.get_management_objects(item_type, wmi, **filters)
        for case in switch(len(results)):
            if case(0):
                return None
            if case(1):
                return results[0]
            if case():
                raise ServerObjectManagementError(ServerObjectManagementError.NOT_UNIQUE, type=item_type, filters=filters)

    def remove_management_object(self, item_type, unique_id, wmi=True if WIN32 else False, error_if_not_exists=False):
        """Remove a management object.

        Args:
            item_type: The item type of the object to remove.
            unique_id: The unique identifier of the object to remove.
            wmi (optional): True if this is a Windows platform, False otherwise.
            error_if_not_exists (optional, default=False): If False raise an error if the object does not exist.

        Returns:
            Nothing.

        Raises:
            ServerObjectManagementError.WMI_ERROR: If there was an error removing the object.
        """
        unique_key = 'ProcessId' if (item_type == 'Process') else 'Name'
        removal_object = self.get_unique_object(item_type, wmi, **{unique_key: unique_id})
        if error_if_not_exists and not removal_object:
            raise ServerObjectManagementError(ServerObjectManagementError.OBJECT_NOT_FOUND, type=item_type)
        result = removal_object.Delete()[0] if removal_object else False
        if result:
            msg = self._WMI_SERVICE_CREATE_ERRORS[result] if (result in self._WMI_SERVICE_CREATE_ERRORS) else f'Return value: {result}'
            raise ServerObjectManagementError(ServerObjectManagementError.WMI_ERROR, server=self.hostname, msg=msg)

    def remove_scheduled_task(self, task):
        """Remove the specified scheduled task.

        Args:
            task: The name of the scheduled task to remove.

        Returns:
            Nothing.
        """
        self.get_scheduled_task(task).remove()

    def remove_service(self, service, error_if_not_exists=False):
        """Remove the specified service.

        Args:
            service: The name of the service to remove.
            error_if_not_exists (optional, default=False): If False raise an error if the object does not exist.

        Returns:
            Nothing.
        """
        self.remove_management_object('Service', service, error_if_not_exists=error_if_not_exists)

    def run_command(self, command, *cmd_args, **sys_cmd_args):
        """Run a command on the server.

        Args:
            command: The command to run.
            *cmd_args (optional, default=[]): The arguments to pass to the command.
            *sys_cmd_args (optional, default={}): A dictionary of named arguments to pass to the command.

        Returns:
            The result of the command.
        """
        if (not self.is_local) and self.auth:
            sys_cmd_args['remote_auth'] = self.auth
        return syscmd(command, *cmd_args, remote=(False if self.is_local else self.ip), remote_is_windows=(not self.is_local) and (self.os_type == self.OS_TYPES.windows), **sys_cmd_args)


class OSManager:
    """Class to make non WMI OS management look like WMI management."""

    def __init__(self, computer=None, auth=None):
        """
        Args:
            computer (optional, default=None): The remote computer.
            auth (optional, default=None): A (username, password) tuple for remote server access.

        Attributes:
            auth: The value of the auth argument.
            computer: The value of the computer argument.
        """
        self.computer = computer
        self.auth = auth

    def get_object_as_list(self, object_type, Name, **key_args):
        """Get the specified OS object.

        Args:
            object_type: The object type.
            Name: The name of the object to return.
            **key_args (optional, default={}): A dictionary of filters to pass to the manager to filter the objects returned.

        Returns:
            The list of management objects.
        """
        try:
            return [globals()[object_type](Name, self.computer, self.auth, **key_args)]
        except ServerObjectManagementError as err:
            if err.code == ServerObjectManagementError.OBJECT_NOT_FOUND.code:
                return list()
            raise

    def LinuxProcess(self, CommandLine=None, ExecutablePath=None, Name=None, ProcessId=None):
        """Get the specified Linux process.

        Args:
            Exactly one of these options must be specified:
            CommandLine (optional, default=None): The command line for the process.
            ExecutablePath (optional, default=None): The command line for the process.
            Name (optional, default=None): The command line for the process.
            ProcessId (optional, default=None): The command line for the process.

        Returns:
            The specified Linux process.

        Raises:
            ServerObjectManagementError.BAD_FILTER: If more than one selection option is specified.
        """
        if len([v for v in (CommandLine, ExecutablePath, Name, ProcessId) if v is not None]) != 1:
            raise ServerObjectManagementError(ServerObjectManagementError.BAD_FILTER)

        if ProcessId:
            try:
                return [LinuxProcess(ProcessId)]
            except NoSuchProcess:
                return list()

        process_list = [p for p in process_iter(attrs=('pid', 'cmdline', 'exe', 'name'))]
        if CommandLine:
            return [LinuxProcess(p.pid) for p in process_list if p.info['cmdline'] == CommandLine]
        if ExecutablePath:
            return [LinuxProcess(p.pid) for p in process_list if p.info['exe'] == ExecutablePath]
        if Name:
            return [LinuxProcess(p.pid) for p in process_list if p.info['name'] == Name]

    def LinuxService(self, Name, service_type):
        """Get the specified Linux service.

        Args:
            Name: The name of the service to return.
            service_type: The type of service to return.

        Returns:
            The specified Linux service.
        """
        return self.get_object_as_list('LinuxService', Name, service_type=service_type)

    def Win32_ScheduledTask(self, Name):
        """Get the specified Windows Scheduled Task.

        Args:
            Name: The name of the scheduled task to return.

        Returns:
            The specified Windows scheduled task.
        """
        return self.get_object_as_list('Win32_ScheduledTask', Name)


class NamedOSObject:
    """Class to allow management of all OS objects using a similar interface."""

    def __init__(self, Name, computer, auth):
        """
        Args:
            Name: The name of the object.
            computer: The remote computer.
            auth: A (username, password) tuple for remote server access.

        Attributes:
            auth: The value of the auth argument.
            computer: The value of the computer argument.
            Name: The value of the Name argument.
        """
        self.Name = Name
        self.computer = computer
        self.auth = auth
        self.validate()  # pylint: disable=E1101


class LinuxService(NamedOSObject):
    """Class to create a universal abstract interface for a Linux daemon service."""

    def __init__(self, Name, computer, auth, service_type):
        """
        Args:
            Name: The name of the object.
            computer: The remote computer.
            auth: A (username, password) tuple for remote server access.
            service_type: The type of the Linux service

        Attributes:
            type: The value of the service_type argument.
        """
        self.type = service_type
        super().__init__(Name, computer, auth)

    def _manage(self, command):
        """Manage the service.

        Args:
            command: The management action to perform.

        Returns:
            The result of the management command.
        """
        control_command = ['service', self.Name, command] if (self.type == Service.ServiceType.sysv) \
            else ['systemctl' if (self.type == Service.ServiceType.systemd) else 'initctl', command, self.Name]
        try:
            return syscmd(*control_command, use_shell=True, ignore_stderr=True, remote=self.computer, remote_auth=self.auth)
        except CMDError as err:
            if command == 'status':
                return err
            raise

    @property
    def state(self):
        """A read-only property which returns the state value of the service."""
        result = self._manage('status')
        if result and isinstance(result, list) and ('stop' in result[0]):
            return 'Stopped'
        if not hasattr(result, 'vars'):
            return 'Running'
        if result.vars['returncode'] == 3:
            return 'Stopped'
        raise result

    def DisableService(self):
        """Disable the service.

        Returns:
            Nothing.
        """
        self.StopService()
        self._manage('disable')

    def EnableService(self):
        """Enable the service.

        Returns:
            Nothing.
        """
        self._manage('enable')
        self.StartService()

    def RestartService(self):
        """Restart the service.

        Returns:
            Nothing.
        """
        self._manage('restart')

    def StartService(self):
        """Start the service.

        Returns:
            Nothing.
        """
        self._manage('start')

    def StopService(self):
        """Stop the service.

        Returns:
            Nothing.
        """
        self._manage('stop')

    def validate(self):
        """Determine if the service exists.

        Returns:
            Nothing.

        Raises:
            ServerObjectManagementError.OBJECT_NOT_FOUND: If the service is not found.
        """
        not_found = False
        try:
            self.state
        except CMDError as err:
            if not err.vars['returncode'] == (4 if (self.type == Service.ServiceType.systemd) else 1):
                raise
            not_found = True
        if not_found:
            raise ServerObjectManagementError(ServerObjectManagementError.OBJECT_NOT_FOUND, type=type(self).__name__)


class LinuxProcess:
    """Class to create a universal abstract interface for a Linux process."""

    def __init__(self, ProcessId):
        """
        Args:
            ProcessId: The process ID of the process.

        Attributes:
            process_obj: The API object representing the process.
            ProcessId: The value of the ProcessId argument.
        """
        self.ProcessId = ProcessId
        self.process_obj = _LinuxProcess(self.ProcessId)

    CommandLine = property(lambda s: s.process_obj.cmdline(), doc='A read-only property which returns the command line for the process.')
    ExecutablePath = property(lambda s: s.process_obj.exe(), doc='A read-only property which returns the executable path for the process.')
    Name = property(lambda s: s.process_obj.name(), doc='A read-only property which returns the name of the process.')

    def Kill(self):
        """Kill the process.

        Returns:
            Nothing.
        """
        self.process_obj.kill()

    def Terminate(self):
        """Terminate the process.

        Returns:
            Nothing.
        """
        self.process_obj.terminate()


class LinuxScheduledTask:
    """Class to create a universal abstract interface for a Linux cron job."""


class Win32_ScheduledTask(NamedOSObject):
    """Class to abstract a Windows Scheduled Task since they are not available using WMI."""

    def __getattr__(self, attr):
        if attr == 'state':
            attr = 'scheduled_task_state'
        attr = attr.title().replace('_', ' ')
        task_info = [l for l in DictReader(self._run_task_scheduler('/Query', '/V', '/FO', 'CSV'))][0]
        if attr not in task_info:
            raise AttributeError(f"'{type(self)}' object has no attribute '{attr}'")
        return task_info[attr]

    def _run_task_scheduler(self, *cmd_args, **sys_cmd_args):
        """Run the Windows sc command to manage the service.

        Args:
            *cmd_args (optional, default=[]): The command and arguments.
            **sys_cmd_args (optional, default={}): The named arguments.

        Returns:
            The result of the sc command.
        """
        cmd_args = list(cmd_args) + ['/TN', self.Name]
        if self.computer:
            cmd_args += ['/S', self.computer]
        if self.auth:
            cmd_args += ('/U', self.auth[0], '/P', self.auth[1])
        return _run_task_scheduler(*cmd_args, **sys_cmd_args)

    def manage(self, signal, wait=True):
        """Manage the scheduled task.

        Args:
            signal: The signal to send to the scheduled task.
            wait (optional, default=True): If True, wait for the action to complete.

        Returns:
            Nothing.

        Raises:
            ServerObjectManagementError.BAD_OBJECT_SIGNAL: If the signal is unknown.
        """
        for case in switch(signal):
            if case(ScheduledTask.TaskSignal.enable):
                control_args = ('/Change', '/ENABLE')
                break
            if case(ScheduledTask.TaskSignal.disable):
                control_args = ('/Change', '/DISABLE')
                break
            if case(ScheduledTask.TaskSignal.run):
                control_args = ('/Run',)
                break
            if case(ScheduledTask.TaskSignal.end):
                control_args = ('/End',)
                break
            if case():
                raise ServerObjectManagementError(ServerObjectManagementError.BAD_OBJECT_SIGNAL, signal=signal.name)

        self._run_task_scheduler(*control_args)
        while wait and (self.status.lower() == 'running'):
            sleep(_STATUS_CHECK_INTERVAL)

    def remove(self):
        """Remove the scheduled task.

        Returns:
            The result of the remove command.
        """
        return self._run_task_scheduler('/Delete', '/F')

    def validate(self):
        """Determine if the scheduled task exists.

        Returns:
            Nothing.

        Raises:
            ServerObjectManagementError.OBJECT_NOT_FOUND: If the scheduled task is not found.
        """
        not_found = False
        try:
            self.state
        except CMDError as err:
            if not err.vars['returncode'] == 1:
                raise
            not_found = True
        if not_found:
            raise ServerObjectManagementError(ServerObjectManagementError.OBJECT_NOT_FOUND, type=type(self).__name__)


class COMObject:
    """Class to create a universal abstract interface for a Windows COM object."""

    def __init__(self, ref, hostname=None):
        """
        Args:
            ref: The Windows COM object.
            hostname (optional): The server hostname. If not specified, will default to the name of the localhost.

        Attributes:
            _connection: The value of the ref argument.
            _hostname: The derived value of the hostname argument.

        Raises:
            ServerObjectManagementError.REMOTE_CONNECTION_ERROR: If there was a failure making a connection to the COM object.
        """
        self._hostname = hostname
        raise_error = False
        try:
            if isinstance(ref, CDispatch):
                self._connection = ref
                str(self._connection)
            else:
                self._connection = DispatchEx(ref, self._hostname)
        except com_error as err:
            raise_error = err
        if raise_error:
            raise ServerObjectManagementError(ServerObjectManagementError.REMOTE_CONNECTION_ERROR, server=self._hostname, msg=str(raise_error))

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.disconnect()
        return False

    def __getattr__(self, attr):
        return getattr(self._connection, attr)

    def __setattr__(self, attr, value):
        if attr.startswith('_'):
            super().__setattr__(attr, value)
            return
        setattr(self._connection, attr, value)

    def disconnect(self):
        """Disconnect the COM object.

        Returns:
            Nothing.
        """
        del self._connection


class ManagementObject:
    """Management object to provide OS independent interface.

    Attributes:
        OBJECT_PREFIX: The prefix to use to correctly translate to a NamesOSObject type.
    """
    OBJECT_PREFIX = 'Win32_' if WIN32 else 'Linux'

    def __init__(self, object_ref, manager, key, value, **key_values):
        """
        Args:
            object_ref: A reference to the management object.
            manager: A reference to the manager of the object.
            key: The unique key used to identify the object to the manager.
            value: The unique value used to identify the object to the manager.
            key_values (optional): A additional dictionary of key/value pairs to apply when referencing the object in the manager.

        Attributes:
            key: The value of the key argument.
            key_values: The value of the key_values argument.
            manager: The value of the manager argument.
            object_ref: The value of the object_ref argument.
            type: The object type.
            value: The value of the value argument.
        """
        self.type = self.OBJECT_PREFIX + type(self).__name__
        self.object_ref = object_ref
        self.manager = manager
        self.key = key
        self.value = value
        self.key_values = key_values

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        del self.object_ref
        return False

    def __getattr__(self, attr):
        self.refresh()
        return getattr(self.object_ref, attr)

    def refresh(self):
        """Refresh the state of the object.

        Returns:
            Nothing.

        Raises:
            ServerObjectManagementError.NOT_UNIQUE: If the object is not unique.
        """
        if self.object_ref:
            results = getattr(self.manager, self.type)(**{self.key: self.value}, **self.key_values)
            if len(results) > 1:
                raise ServerObjectManagementError(ServerObjectManagementError.NOT_UNIQUE, type=self.type, key=self.key, val=self.value)
            self.object_ref = results[0] if results else None


class Service(ManagementObject):
    """Class to create a universal abstract interface for an OS service."""

    def __getattr__(self, attr):
        if attr == 'state':
            return self.ServiceState[super().__getattr__(attr).replace(' ', '')]
        return super().__getattr__(attr)

    def manage(self, signal, wait=True, ignore_state=False, timeout=False):
        """Manage the service.

        Args:
            signal: The signal to send to the service.
            wait (optional, default=True): If True, wait for the action to complete.
            ignore_state (optional, default=False): If False, do not check the initial state before performing the action.
            timeout (optional, default=False): If wait is True, the number of seconds to wait for the action to complete, indefinitely if False.

        Returns:
            Nothing.

        Raises:
            ServerObjectManagementError.BAD_OBJECT_SIGNAL: If the requested action is invalid.
            ServerObjectManagementError.BAD_OBJECT_STATE: If ignore_state is False and the current state is invalid.
            ServerObjectManagementError.BAD_TRANSITION: If ignore_state is False and the requested action is not valid for the current state.
            ServerObjectManagementError.STATUS_CHECK_TIMEOUT: If wait is True and timeout is not False and the object has not reached the required state.
        """
        for case in switch(signal):
            if case(self.ServiceSignal.enable, self.ServiceSignal.start, self.ServiceSignal.resume, self.ServiceSignal.restart):
                for signal_case in switch(signal):
                    if signal_case(self.ServiceSignal.enable):
                        control_method = 'EnableService'
                        break
                    if signal_case(self.ServiceSignal.start):
                        control_method = 'StartService'
                        break
                    if signal_case(self.ServiceSignal.resume):
                        control_method = 'ResumeService'
                        break
                    if signal_case(self.ServiceSignal.restart):
                        control_method = 'RestartService'
                        break
                final_state = self.ServiceState.Running
                break
            if case(self.ServiceSignal.disable, self.ServiceSignal.stop):
                control_method = 'StopService' if self.ServiceSignal.stop else 'DisableService'
                final_state = self.ServiceState.Stopped
                break
            if case(self.ServiceSignal.pause):
                control_method = 'PauseService'
                final_state = self.ServiceState.Paused
                break
            if case():
                raise ServerObjectManagementError(ServerObjectManagementError.BAD_OBJECT_SIGNAL, signal=signal.name)

        if not ignore_state:
            for case in switch(self.state):
                if case(self.ServiceState.StartPending, self.ServiceState.Running, self.ServiceState.ContinuePending):
                    waitfor = self.ServiceState.Running
                    if signal in (self.ServiceSignal.enable, self.ServiceSignal.start, self.ServiceSignal.resume):
                        control_method = None
                    break
                if case(self.ServiceState.StopPending, self.ServiceState.Stopped):
                    waitfor = self.ServiceState.Stopped
                    for signal_case in switch(signal):
                        if signal_case(self.ServiceSignal.disable, self.ServiceSignal.stop):
                            control_method = None
                            break
                        if signal_case(self.ServiceSignal.resume, self.ServiceSignal.restart):
                            control_method = 'StartService'
                            break
                        if signal_case(self.ServiceSignal.pause):
                            raise ServerObjectManagementError(ServerObjectManagementError.BAD_TRANSITION, from_state='stopped', to_state='paused')
                    break
                if case(self.ServiceState.PausePending, self.ServiceState.Paused):
                    waitfor = self.ServiceState.Paused
                    if signal == self.ServiceSignal.start:
                        control_method = 'ResumeService'
                    break
                if case():
                    raise ServerObjectManagementError(ServerObjectManagementError.BAD_OBJECT_STATE, state=self.state)
            wait_length = 0
            while self.state != waitfor:
                sleep(_STATUS_CHECK_INTERVAL)
                wait_length += _STATUS_CHECK_INTERVAL
                if timeout and (wait_length > timeout):
                    raise ServerObjectManagementError(ServerObjectManagementError.STATUS_CHECK_TIMEOUT, type='service', state=waitfor.name)

        if control_method:
            if WIN32 and control_method == 'RestartService':
                self.manage(self.ServiceSignal.stop, wait, ignore_state)
                self.manage(self.ServiceSignal.start, wait, ignore_state)
            else:
                getattr(self, control_method)()
                sleep(_STATUS_CHECK_INTERVAL)
        wait_length = 0
        while wait and (self.state != final_state):
            sleep(_STATUS_CHECK_INTERVAL)
            wait_length += _STATUS_CHECK_INTERVAL
            if timeout and (wait_length > timeout):
                raise ServerObjectManagementError(ServerObjectManagementError.STATUS_CHECK_TIMEOUT, type='service', state=final_state.name)


class Process(ManagementObject):
    """Class to create a universal abstract interface for an OS process."""

    def manage(self, signal, wait=True, timeout=False):
        """Manage the process.

        Args:
            signal: The signal to send to the process.
            wait (optional, default=True): If True, wait for the action to complete.
            timeout (optional, default=False): If wait is True, the number of seconds to wait for the action to complete, indefinitely if False.

        Returns:
            Nothing.

        Raises:
            ServerObjectManagementError.BAD_OBJECT_SIGNAL: If the requested action is invalid.
            ServerObjectManagementError.STATUS_CHECK_TIMEOUT: If wait is True and timeout is not False and the object has not reached the required state.
        """
        for case in switch(signal):
            if case(self.ProcessSignal.stop):
                control_method = 'Terminate'
                break
            if case(self.ProcessSignal.kill):
                control_method = 'Terminate' if WIN32 else 'Kill'
                break
            if case():
                raise ServerObjectManagementError(ServerObjectManagementError.BAD_OBJECT_SIGNAL, signal=signal.name)

        if control_method:
            getattr(self, control_method)()
        wait_length = 0
        while wait and self.object_ref:
            sleep(_STATUS_CHECK_INTERVAL)
            self.refresh()
            wait_length += _STATUS_CHECK_INTERVAL
            if timeout and (wait_length > timeout):
                raise ServerObjectManagementError(ServerObjectManagementError.STATUS_CHECK_TIMEOUT, type='process', state=signal.name)


class ScheduledTask(ManagementObject):
    """Class to create a universal abstract interface for an OS scheduled task.

    Attributes:
        TASK_HOME: The directory where task definitions are stored.
        TASK_NAMESPACE: The Windows task namespace needed to parse the XML task definitions.
    """
    TASK_HOME = Path(getenv('SystemRoot'), 'system32/Tasks') if WIN32 else Path('/opt/cronjobs')
    TASK_NAMESPACE = 'http://schemas.microsoft.com/windows/2004/02/mit/task'

def _get_server_object(server):
    """Get a server object for the specific fqdn.

    Args:
        server: The fqdn string for the server

    Returns:
        Returns the Server object.
    """
    if isinstance(server, Server):
        return server
    if not isinstance(server, str):
        raise TypeError(server)
    return Server(*(server.split('.', 1)))


def _run_task_scheduler(*cmd_args, **sys_cmd_args):
    """Interface to run the standard Windows schtasks command-line tool.

    Args:
        *cmd_args: The arguments to pass to schtasks.
        **sys_cmd_args: The arguments to pass to syscmd when running schtasks.

    Returns:
        The result of the syscmd call to schtasks.
    """
    return syscmd('schtasks.exe', *cmd_args, **sys_cmd_args)

# cSpell:ignore cmdline sbin wsahost psutil syscmd iispy
