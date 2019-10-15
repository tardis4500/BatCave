'This provides a Pythonic server management interface'
# pylint: disable=C0103
# cSpell:ignore cmdline, ipaddress, lbvserver, nssrc, sbin, sslvserver, sslcertkey, vservername, wsahost

# Import standard modules
from csv import DictReader
# from datetime import datetime as dt, timedelta
from enum import Enum
from os import getenv, walk
from pathlib import Path, PurePosixPath, PureWindowsPath, WindowsPath
from platform import node
from shutil import copy
from socket import getfqdn, gethostbyname, gaierror
from string import Template
from time import sleep
from xml.etree.ElementTree import SubElement, parse as xmlparse

# Import third-party modules
from nssrc.com.citrix.netscaler.nitro.resource.config.ssl.sslvserver_sslcertkey_binding import sslvserver_sslcertkey_binding as NetScalerCertificateBinding
from nssrc.com.citrix.netscaler.nitro.resource.config.cache.cachecontentgroup import cachecontentgroup as NetScalerCacheContentGroup
from nssrc.com.citrix.netscaler.nitro.exception.nitro_exception import nitro_exception as NetScalerError
from nssrc.com.citrix.netscaler.nitro.resource.config.lb.lbvserver_responderpolicy_binding import lbvserver_responderpolicy_binding as NetScalerResponderPolicyBinding
from nssrc.com.citrix.netscaler.nitro.resource.config.basic.server import server as NetScalerServer
from nssrc.com.citrix.netscaler.nitro.resource.config.basic.service import service as NetScalerServerService
from nssrc.com.citrix.netscaler.nitro.service.nitro_service import nitro_service as NetScalerService
from nssrc.com.citrix.netscaler.nitro.resource.config.lb.lbvserver import lbvserver as NetScalerVirtualServer
from nssrc.com.citrix.netscaler.nitro.resource.config.lb.lbvserver_service_binding import lbvserver_service_binding as NetScalerVirtualServiceBinding
from psutil import process_iter, NoSuchProcess, Process as _LinuxProcess

# Import internal modules
from .sysutil import rmpath, syscmd, CMDError
from .lang import is_debug, switch, HALError, HALException, WIN32

if WIN32:
    from pywintypes import com_error  # pylint: disable=E0611
    from win32com.client import CDispatch, DispatchEx
    from wmi import WMI, x_wmi
    from .iispy import IISInstance
else:
    class x_wmi(Exception):
        'Needed to avoid errors on Linux'


_STATUS_CHECK_INTERVAL = 2


class LoadBalancerError(HALException):
    'Class for LoadBalancer related error'
    INVALID_OBJECT = HALError(1, Template('Requested $type not in load balancer: $name'))
    UNKNOWN_SERVER_SIGNAL = HALError(2, Template('Unknown server signal: $signal'))


class ServerObjectManagementError(HALException):
    'Class for Service related errors'
    UNKNOWN_OBJECT_STATE = HALError(1, Template('Unknown object state: $state'))
    UNKNOWN_OBJECT_SIGNAL = HALError(2, Template('Unknown object signal: $signal'))
    BAD_TRANSITION = HALError(3, Template('Invalid state transition from $from_state to $to_state'))
    SERVER_NOT_FOUND = HALError(4, Template('No server found: $server'))
    REMOTE_CONNECTION_ERROR = HALError(5, Template('Unable to connect to remote server $server: $msg'))
    NOT_UNIQUE = HALError(6, Template('Unable to locate unique $type according to $filters'))
    SERVICE_CONTROL_ERROR = HALError(7, Template('Error sending $signal signal to service: $ret'))
    OBJECT_NOT_FOUND = HALError(8, Template('No $type object found'))
    BAD_FILTER = HALError(9, 'One and only one filter must be provided for this object')
    REMOTE_NOT_SUPPORTED = HALError(10, 'Remote objects are not supported for Linux servers')
    STATUS_CHECK_TIMEOUT = HALError(11, Template('Timeout waiting for expected $type state: $state'))
    WMI_ERROR = HALError(12, Template('WMI error on server $server: $msg'))


class ServerPathError(HALException):
    'Class for ServerPath related errors'
    REMOTE_COPY_SPACE_ERROR = HALError(1, Template('Error during robocopy, possible lack of disk space on $dest'))
    UNSUPPORTED = HALError(2, 'This function is only supported for remote Windows servers from Windows servers')


class LoadBalancer:
    'Class for managing a load balancer'
    LB_SERVER_SIGNALS = Enum('lb_server_signals', ('enable', 'disable'))
    LB_TYPES = Enum('lb_types', ('netscaler',))
    LB_VIP_TYPES = Enum('lb_vip_types', ('HTTP', 'SSL', 'SSL_OFFLOAD'))

    def __init__(self, lb_type, ip, user, password):
        self.type = lb_type
        self.ip = ip
        self.user = user
        self.password = password
        self.ns_session = NetScalerService(self.ip)
        self.ns_session.login(self.user, self.password, 3600)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.ns_session.logout()
        return False

    def get_cache_content_group(self, group_name):
        'Get the NetScaler cache content group'
        try:
            group_ref = NetScalerCacheContentGroup.get(self.ns_session, group_name)
            group_ref.query = group_ref.host = group_ref.selectorvalue = ''
            return group_ref
        except NetScalerError as err:
            if err.errorcode == 258:
                raise LoadBalancerError(LoadBalancerError.INVALID_OBJECT, type='cache content group', name=group_name)
            raise

    def flush_cache_content(self, group_name):
        'Flush the NetScaler cache content for the specified group'
        group_ref = self.get_cache_content_group(group_name)
        return NetScalerCacheContentGroup.flush(self.ns_session, group_ref)

    def has_server(self, server_info):
        'Determine if the load balancer server exists'
        try:
            self.get_server(server_info)
        except LoadBalancerError as err:
            if err.code == LoadBalancerError.INVALID_OBJECT.code:
                return False
            raise
        else:
            return True

    def add_server(self, server_info):
        'Add a server to the load balancer'
        server_object = _get_server_object(server_info)
        ns_server = NetScalerServer()
        ns_server.name = server_object.hostname
        ns_server.ipaddress = server_object.ip
        NetScalerServer.add(self.ns_session, ns_server)
        return self.get_server(server_info)

    def get_server(self, server_info):
        'Get a handle to the load balancer server'
        server_hostname = _get_server_object(server_info).hostname
        try:
            return LoadBalancerServer(self, NetScalerServer.get(self.ns_session, server_hostname))
        except NetScalerError as err:
            if err.errorcode == 258:
                raise LoadBalancerError(LoadBalancerError.INVALID_OBJECT, type='server', name=server_hostname)
            raise

    def add_virtual_server(self, server_info, service_type=LB_VIP_TYPES.HTTP, port=None, servers=tuple(), services=tuple(), certificates=tuple(), responder_policies=tuple()):
        'Add a virtual server to the load balancer'
        if port is not None:
            port_value = port
        elif service_type in (self.LB_VIP_TYPES.HTTP, self.LB_VIP_TYPES.SSL_OFFLOAD):
            port_value = 80
        elif service_type == self.LB_VIP_TYPES.SSL:
            port_value = 443
        else:
            port_value = port

        server_objects = [_get_server_object(s) for s in (list(servers) if (isinstance(servers, tuple) or isinstance(servers, list)) else [servers])]  # pylint: disable=C0325
        service_objects = list(services) if (isinstance(services, tuple) or isinstance(services, list)) else [services]
        certificates = certificates if (isinstance(certificates, list) or isinstance(certificates, tuple)) else [certificates]
        responder_policies = responder_policies if (isinstance(responder_policies, list) or isinstance(responder_policies, tuple)) else [responder_policies]

        server_object = _get_server_object(server_info)
        ns_virtual_server = NetScalerVirtualServer()
        ns_virtual_server.name = server_object.hostname
        ns_virtual_server.servicetype = 'HTTP' if (service_type == self.LB_VIP_TYPES.SSL_OFFLOAD) else service_type.name
        ns_virtual_server.ipv46 = server_object.ip
        ns_virtual_server.port = port_value
        NetScalerVirtualServer.add(self.ns_session, ns_virtual_server)
        virtual_server = self.get_virtual_server(server_info)
        offload_server = None

        for server_object in server_objects:
            if not self.has_server(server_object):
                server = self.add_server(server_object)
                service_name = f'svc_{server.name}_{port_value}'
                server.add_service(service_name)
                service_objects.append(service_name)
        for service in service_objects:
            virtual_server.bind_service(service)
        for policy in responder_policies:
            virtual_server.bind_responder_policy(policy)
        if service_type == self.LB_VIP_TYPES.SSL:
            for cert in certificates:
                virtual_server.bind_certificate(cert)
        elif service_type == self.LB_VIP_TYPES.SSL_OFFLOAD:
            offload_server_object = Server(f'{server_info.hostname}_offload', ip=server_info.ip)
            offload_server = self.add_virtual_server(offload_server_object, service_type=self.LB_VIP_TYPES.SSL, services=service_objects, certificates=certificates)

        return (virtual_server, offload_server) if offload_server else virtual_server

    def get_virtual_server(self, server_name):
        'Get a handle to a virtual load balancer server'
        server_hostname = _get_server_object(server_name).hostname
        try:
            return LoadBalancerVirtualServer(self, NetScalerVirtualServer.get(self.ns_session, server_hostname))
        except NetScalerError as err:
            if err.errorcode == 258:
                raise LoadBalancerError(LoadBalancerError.INVALID_OBJECT, type='virtual server', name=server_hostname)
            raise

    def manage_servers(self, signal, servers, validate=True):
        'Manage a server serviced by the load balancer'
        if signal not in (self.LB_SERVER_SIGNALS.enable, self.LB_SERVER_SIGNALS.disable):
            raise LoadBalancerError(LoadBalancerError.UNKNOWN_SERVER_SIGNAL, signal=signal.name)

        if not (isinstance(servers, tuple) or isinstance(servers, list)):
            servers = [servers]

        for server in [_get_server_object(s) for s in servers]:
            getattr(NetScalerServer, signal.name)(self.ns_session, server.hostname)
            while validate and (self.get_server(server).state.lower() != (signal.name + 'd')):
                sleep(_STATUS_CHECK_INTERVAL)


class LoadBalancerObject:
    'Base class for all load balancer objects'
    def __init__(self, load_balancer_ref, lb_object_ref):
        self.load_balancer_ref = load_balancer_ref
        self.lb_object_ref = lb_object_ref

    def __getattr__(self, attr):
        return getattr(self.lb_object_ref, attr)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class LoadBalancerServer(LoadBalancerObject):
    'Class to represent a server in the load balancer'
    def add_service(self, service_name, service_type='HTTP', port=80):
        'Add a service to a server in the load balancer'
        ns_service = NetScalerServerService()
        ns_service.servicetype = service_type
        ns_service.name = service_name
        ns_service.servername = self.lb_object_ref.name
        ns_service.port = port
        NetScalerServerService.add(self.load_balancer_ref.ns_session, ns_service)
        return self.get_service(service_name)

    def get_service(self, service_name):
        'Get a handle to the load balancer server'
        try:
            return LoadBalancerService(self, NetScalerServerService.get(self.load_balancer_ref.ns_session, service_name))
        except NetScalerError as err:
            if err.errorcode == 258:
                raise LoadBalancerError(LoadBalancerError.INVALID_OBJECT, type='service', name=service_name)
            raise


class LoadBalancerService(LoadBalancerObject):
    'Class to represent a service in the load balancer'


class LoadBalancerVirtualServer(LoadBalancerObject):
    'Class to represent a virtual server in the load balancer'
    def bind_service(self, service):
        'Bind a service to the virtual server'
        ns_virtual_service_binding = NetScalerVirtualServiceBinding()
        ns_virtual_service_binding.name = self.name
        ns_virtual_service_binding.servicename = service.name if isinstance(service, LoadBalancerService) else service
        NetScalerVirtualServiceBinding.add(self.load_balancer_ref.ns_session, ns_virtual_service_binding)

    def bind_certificate(self, cert_name):
        'Bind a certificate to the virtual server'
        ns_certificate_binding = NetScalerCertificateBinding()
        ns_certificate_binding.vservername = self.name
        ns_certificate_binding.certkeyname = cert_name
        NetScalerCertificateBinding.add(self.load_balancer_ref.ns_session, ns_certificate_binding)

    def bind_responder_policy(self, policy_name, policy_priority=100):
        'Bind a responder policy to the virtual server'
        ns_policy_binding = NetScalerResponderPolicyBinding()
        ns_policy_binding.name = self.name
        ns_policy_binding.policyname = policy_name
        ns_policy_binding.priority = policy_priority
        NetScalerResponderPolicyBinding.add(self.load_balancer_ref.ns_session, ns_policy_binding)


class Server:
    'Class to encapsulate a server as an object'
    OS_TYPES = Enum('os_types', ('linux', 'windows'))
    _WSA_NAME_OR_SERVICE_NOT_KNOWN = -2
    _WSAHOST_NOT_FOUND = 11001
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

    def __init__(self, hostname=None, domain=None, auth=None, defer_wmi=True, ip=None, os_type=OS_TYPES.windows if WIN32 else OS_TYPES.linux):
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

    fqdn = property(lambda s: f'{s.hostname}.{s.domain}' if s.domain else s.hostname)
    is_local = property(lambda s: getfqdn().lower() == s.fqdn)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def _connect_wmi(self):
        'Make a WMI connection to the server'
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
        if (item_type != 'Service') and (self.os_type != self.OS_TYPES.windows) and not self.is_local:
            raise ServerObjectManagementError(ServerObjectManagementError.REMOTE_NOT_SUPPORTED)
        if wmi and not self._wmi_manager:
            self._connect_wmi()
        return self._wmi_manager if wmi else self._os_manager

    def get_management_objects(self, item_type, wmi=True if WIN32 else False, **filters):
        'Get the requested management objects as a list'
        manager = self._get_object_manager(item_type, wmi)
        unique_key = 'ProcessId' if (item_type == 'Process') else 'Name'
        extra_keys = dict()
        for (key, item_list) in {'service_type': 'Service'}.items():
            if (item_type in item_list) and (key in filters):
                if self.os_type != self.OS_TYPES.windows:
                    extra_keys[key] = filters[key]
                else:
                    del filters[key]
        return [globals()[item_type](r, manager, unique_key, getattr(r, unique_key), **extra_keys) for r in getattr(manager, ManagementObject.OBJECT_PREFIX+item_type)(**filters)]

    def get_unique_object(self, item_type, wmi=True if WIN32 else False, **filters):
        'Get the requested management object and error if more than one is found for the specified filters'
        results = self.get_management_objects(item_type, wmi, **filters)
        for case in switch(len(results)):
            if case(0):
                return None
            if case(1):
                return results[0]
            if case():
                raise ServerObjectManagementError(ServerObjectManagementError.NOT_UNIQUE, type=item_type, filters=filters)

    def get_object_by_name(self, item_type, name, wmi=True if WIN32 else False, **key_args):
        'Get the requested management object by name and error if more than one is found'
        return self.get_unique_object(item_type, wmi, Name=name, **key_args)

    def create_management_object(self, item_type, unique_id, wmi=True if WIN32 else False, error_if_exists=True, **key_args):
        'Create the requested management object'
        manager = self._get_object_manager(item_type, wmi)
        unique_key = 'ProcessId' if (item_type == 'Process') else 'Name'
        creation_args = {unique_key: unique_id, 'DisplayName': unique_id}

        created_object = self.get_unique_object(item_type, wmi, **{unique_key: unique_id})
        if error_if_exists or not created_object:
            result = getattr(manager, ManagementObject.OBJECT_PREFIX+item_type).Create(**creation_args, **key_args)[0]
        else:
            result = False

        if result:
            msg = self._WMI_SERVICE_CREATE_ERRORS[result] if (result in self._WMI_SERVICE_CREATE_ERRORS) else f'Return value: {result}'
            raise ServerObjectManagementError(ServerObjectManagementError.WMI_ERROR, server=self.hostname, msg=msg)

        if not created_object:
            created_object = self.get_unique_object(item_type, wmi, **{unique_key: unique_id})
        return globals()[item_type](created_object, manager, unique_key, unique_id)

    def remove_management_object(self, item_type, unique_id, wmi=True if WIN32 else False, error_if_not_exists=False):
        'Remove the requested management object'
        unique_key = 'ProcessId' if (item_type == 'Process') else 'Name'
        removal_object = self.get_unique_object(item_type, wmi, **{unique_key: unique_id})
        if error_if_not_exists and not removal_object:
            raise ServerObjectManagementError(ServerObjectManagementError.OBJECT_NOT_FOUND, type=item_type)
        result = removal_object.Delete()[0] if removal_object else False
        if result:
            msg = self._WMI_SERVICE_CREATE_ERRORS[result] if (result in self._WMI_SERVICE_CREATE_ERRORS) else f'Return value: {result}'
            raise ServerObjectManagementError(ServerObjectManagementError.WMI_ERROR, server=self.hostname, msg=msg)

    def get_iis_instance(self):
        'Get the IIS instance for this server'
        return IISInstance(self.fqdn if not self.is_local else None)

    def get_process_list(self, **filters):
        'Get the process list for this server as a management object list'
        return self.get_management_objects('Process', **filters)

    def get_process_connection(self, process):
        'Make a COM connection to the specified process'
        return COMObject(process, self.ip)

    def get_scheduled_task_list(self):
        'Get a list of the scheduled task management objects'
        cmd_args = ['/Query', '/FO', 'CSV']
        if not self.is_local:
            cmd_args += ['/S', self.fqdn]
        if self.auth:
            cmd_args += ('/U', self.auth[0], '/P', self.auth[1])
        return [self.get_scheduled_task(t['TaskName']) for t in DictReader(_run_task_scheduler(*cmd_args))]

    def get_scheduled_task(self, task):
        'Get the specified scheduled task as a management object'
        return self.get_object_by_name('ScheduledTask', task, False)

    def create_scheduled_task(self, task, exe, schedule_type, schedule, user=None, password=None, start_in=None, disable=False):
        'Create the specified scheduled task'
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
            task_object.manage(ScheduledTask.TASK_SIGNALS.disable)

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

    def remove_scheduled_task(self, task):
        'Remove the specified scheduled task'
        self.get_scheduled_task(task).remove()

    def get_service_list(self, service_type=None):
        'Get a list of the services'
        if service_type is None:
            if self.os_type == self.OS_TYPES.windows:
                service_type = Service.SERVICE_TYPES.windows
            elif self.get_path('/sbin/initctl').exists():
                service_type = Service.SERVICE_TYPES.upstart
            elif self.get_path('/bin/systemctl').exists():
                service_type = Service.SERVICE_TYPES.systemd
            else:
                service_type = Service.SERVICE_TYPES.sysv
        return self.get_management_objects('Service', service_type=service_type)

    def get_service(self, service, **key_args):
        'Get the specified service as a management object'
        if 'service_type' not in key_args:
            if self.os_type == self.OS_TYPES.windows:
                service_type = Service.SERVICE_TYPES.windows
            elif self.get_path('/sbin/initctl').exists():
                service_type = Service.SERVICE_TYPES.upstart
            elif self.get_path('/bin/systemctl').exists():
                service_type = Service.SERVICE_TYPES.systemd
            else:
                service_type = Service.SERVICE_TYPES.sysv
            key_args['service_type'] = service_type
        return self.get_object_by_name('Service', service, **key_args)

    def create_service(self, service, exe, user=None, password=None, start=False, timeout=False, error_if_exists=True):
        'Create the specified service'
        service_obj = self.create_management_object('Service', service, PathName=str(exe), StartName=user, StartPassword=password, error_if_exists=error_if_exists)
        if start:
            service_obj.manage(Service.SERVICE_SIGNALS.start, timeout=timeout)
        return service_obj

    def remove_service(self, service, error_if_not_exists=False):
        'Remove the specified service'
        self.remove_management_object('Service', service, error_if_not_exists=error_if_not_exists)

    def run_command(self, command, *cmd_args, **sys_cmd_args):
        'Run the specified command'
        if (not self.is_local) and self.auth:
            sys_cmd_args['remote_auth'] = self.auth
        return syscmd(command, *cmd_args, remote=(False if self.is_local else self.ip), remote_is_windows=(not self.is_local) and (self.os_type == self.OS_TYPES.windows), **sys_cmd_args)

    def get_path(self, the_path):
        'Get the specified path as a ServerPath object'
        return ServerPath(self, the_path)


class OSManager:
    'Class to make non WMI OS management look like WMI management'
    def __init__(self, computer=None, auth=None):
        self.computer = computer
        self.auth = auth

    def get_object_as_list(self, object_type, Name, **key_args):
        'Get the specified object as a list'
        try:
            return [globals()[object_type](Name, self.computer, self.auth, **key_args)]
        except ServerObjectManagementError as err:
            if err.code == ServerObjectManagementError.OBJECT_NOT_FOUND.code:
                return list()
            raise

    def LinuxService(self, Name, service_type):
        'Return the specified Linux service as an object list'
        return self.get_object_as_list('LinuxService', Name, service_type=service_type)

    def LinuxProcess(self, CommandLine=None, ExecutablePath=None, Name=None, ProcessId=None):
        'Return the specified Linux process as an object list'
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

    def Win32_ScheduledTask(self, Name):
        'Provides a WMI-like interface to a Windows Scheduled Task'
        return self.get_object_as_list('Win32_ScheduledTask', Name)


class NamedOSObject:
    'Class to allow management of all OS objects using a similar interface'
    def __init__(self, Name, computer, auth):
        self.Name = Name
        self.computer = computer
        self.auth = auth
        self.validate()  # pylint: disable=E1101


class LinuxService(NamedOSObject):
    'Class to abstract a Linux service'
    def __init__(self, Name, computer, auth, service_type):
        self.type = service_type
        super().__init__(Name, computer, auth)

    @property
    def state(self):
        'Returns the state value of the service'
        result = self._manage('status')
        if result and isinstance(result, list) and ('stop' in result[0]):
            return 'Stopped'
        if not hasattr(result, 'vars'):
            return 'Running'
        if result.vars['returncode'] == 3:
            return 'Stopped'
        raise result

    def _manage(self, command):
        control_command = ['service', self.Name, command] if (self.type == Service.SERVICE_TYPES.sysv) \
                                                          else ['systemctl' if (self.type == Service.SERVICE_TYPES.systemd) else 'initctl', command, self.Name]
        try:
            return syscmd(*control_command, use_shell=True, ignore_stderr=True, remote=self.computer, remote_auth=self.auth)
        except CMDError as err:
            if command == 'status':
                return err
            raise

    def validate(self):
        'Determines if the service exists'
        not_found = False
        try:
            self.state
        except CMDError as err:
            if not err.vars['returncode'] == (4 if (self.type == Service.SERVICE_TYPES.systemd) else 1):
                raise
            not_found = True
        if not_found:
            raise ServerObjectManagementError(ServerObjectManagementError.OBJECT_NOT_FOUND, type=type(self).__name__)

    def DisableService(self):
        'Disables the service'
        self.StopService()
        self._manage('disable')

    def EnableService(self):
        'Enables the service'
        self._manage('enable')
        self.StartService()

    def StopService(self):
        'Stops the service'
        self._manage('stop')

    def StartService(self):
        'Starts the service'
        self._manage('start')

    def RestartService(self):
        'Restarts the service'
        self._manage('restart')


class LinuxProcess:
    'Class to abstract a Linux process'
    def __init__(self, ProcessId):
        self.ProcessId = ProcessId
        self.process_obj = _LinuxProcess(self.ProcessId)

    CommandLine = property(lambda s: s.process_obj.cmdline())
    ExecutablePath = property(lambda s: s.process_obj.exe())
    Name = property(lambda s: s.process_obj.name())

    def Kill(self):
        'Kills the process'
        self.process_obj.kill()

    def Terminate(self):
        'Terminates the service'
        self.process_obj.terminate()


class LinuxScheduledTask:
    'Class to abstract a Linux cron job'


class Win32_ScheduledTask(NamedOSObject):
    'Class to abstract a Windows Scheduled Task since they are not available using WMI'
    def __getattr__(self, attr):
        if attr == 'state':
            attr = 'scheduled_task_state'
        attr = attr.title().replace('_', ' ')
        task_info = [l for l in DictReader(self._run_task_scheduler('/Query', '/V', '/FO', 'CSV'))][0]
        if attr not in task_info:
            raise AttributeError(f"'{type(self)}' object has no attribute '{attr}'")
        return task_info[attr]

    def validate(self):
        'Determines if the scheduled task exists'
        not_found = False
        try:
            self.state
        except CMDError as err:
            if not err.vars['returncode'] == 1:
                raise
            not_found = True
        if not_found:
            raise ServerObjectManagementError(ServerObjectManagementError.OBJECT_NOT_FOUND, type=type(self).__name__)

    def manage(self, signal, wait=True):
        'Method to provide generic management interface for the scheduled task'
        for case in switch(signal):
            if case(ScheduledTask.TASK_SIGNALS.enable):
                control_args = ('/Change', '/ENABLE')
                break
            if case(ScheduledTask.TASK_SIGNALS.disable):
                control_args = ('/Change', '/DISABLE')
                break
            if case(ScheduledTask.TASK_SIGNALS.run):
                control_args = ('/Run',)
                break
            if case(ScheduledTask.TASK_SIGNALS.end):
                control_args = ('/End',)
                break
            if case():
                raise ServerObjectManagementError(ServerObjectManagementError.UNKNOWN_OBJECT_SIGNAL, signal=signal.name)

        self._run_task_scheduler(*control_args)
        while wait and (self.status.lower() == 'running'):
            sleep(_STATUS_CHECK_INTERVAL)

    def remove(self):
        'Removes the scheduled task'
        return self._run_task_scheduler('/Delete', '/F')

    def _run_task_scheduler(self, *cmd_args, **sys_cmd_args):
        'Uses the container server info to run the Windows sc command'
        cmd_args = list(cmd_args) + ['/TN', self.Name]
        if self.computer:
            cmd_args += ['/S', self.computer]
        if self.auth:
            cmd_args += ('/U', self.auth[0], '/P', self.auth[1])
        return _run_task_scheduler(*cmd_args, **sys_cmd_args)


class COMObject:
    'Generic interface for Windows COM objects'
    def __init__(self, ref, hostname=None):
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
        'Disconnect the COM object'
        del self._connection


class ManagementObject:
    'Management object to provide OS independent interface'
    OBJECT_PREFIX = 'Win32_' if WIN32 else 'Linux'

    def __init__(self, object_ref, manager, key, value, **key_values):
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
        'Refresh the state of the object'
        if self.object_ref:
            results = getattr(self.manager, self.type)(**{self.key: self.value}, **self.key_values)
            if len(results) > 1:
                raise ServerObjectManagementError(ServerObjectManagementError.NOT_UNIQUE, type=self.type, key=self.key, val=self.value)
            self.object_ref = results[0] if results else None


class Service(ManagementObject):
    'Class to provide OS independent service management'
    SERVICE_SIGNALS = Enum('service_signals', ('disable', 'enable', 'start', 'stop', 'pause', 'resume', 'restart'))
    SERVICE_STATES = Enum('service_states', ('StartPending', 'ContinuePending', 'Running', 'StopPending', 'Stopped', 'PausePending', 'Paused'))
    SERVICE_TYPES = Enum('linux_service_types', ('systemd', 'sysv', 'upstart', 'windows'))

    def __getattr__(self, attr):
        if attr == 'state':
            return self.SERVICE_STATES[super().__getattr__(attr).replace(' ', '')]
        return super().__getattr__(attr)

    def manage(self, signal, wait=True, ignore_state=False, timeout=False):
        'Provides a management interface for the service'
        for case in switch(signal):
            if case(self.SERVICE_SIGNALS.enable, self.SERVICE_SIGNALS.start, self.SERVICE_SIGNALS.resume, self.SERVICE_SIGNALS.restart):
                for signal_case in switch(signal):
                    if signal_case(self.SERVICE_SIGNALS.enable):
                        control_method = 'EnableService'
                        break
                    if signal_case(self.SERVICE_SIGNALS.start):
                        control_method = 'StartService'
                        break
                    if signal_case(self.SERVICE_SIGNALS.resume):
                        control_method = 'ResumeService'
                        break
                    if signal_case(self.SERVICE_SIGNALS.restart):
                        control_method = 'RestartService'
                        break
                final_state = self.SERVICE_STATES.Running
                break
            if case(self.SERVICE_SIGNALS.disable, self.SERVICE_SIGNALS.stop):
                control_method = 'StopService' if self.SERVICE_SIGNALS.stop else 'DisableService'
                final_state = self.SERVICE_STATES.Stopped
                break
            if case(self.SERVICE_SIGNALS.pause):
                control_method = 'PauseService'
                final_state = self.SERVICE_STATES.Paused
                break
            if case():
                raise ServerObjectManagementError(ServerObjectManagementError.UNKNOWN_OBJECT_SIGNAL, signal=signal.name)

        if not ignore_state:
            for case in switch(self.state):
                if case(self.SERVICE_STATES.StartPending, self.SERVICE_STATES.Running, self.SERVICE_STATES.ContinuePending):
                    waitfor = self.SERVICE_STATES.Running
                    if signal in (self.SERVICE_SIGNALS.enable, self.SERVICE_SIGNALS.start, self.SERVICE_SIGNALS.resume):
                        control_method = None
                    break
                if case(self.SERVICE_STATES.StopPending, self.SERVICE_STATES.Stopped):
                    waitfor = self.SERVICE_STATES.Stopped
                    for signal_case in switch(signal):
                        if signal_case(self.SERVICE_SIGNALS.disable, self.SERVICE_SIGNALS.stop):
                            control_method = None
                            break
                        if signal_case(self.SERVICE_SIGNALS.resume, self.SERVICE_SIGNALS.restart):
                            control_method = 'StartService'
                            break
                        if signal_case(self.SERVICE_SIGNALS.pause):
                            raise ServerObjectManagementError(ServerObjectManagementError.BAD_TRANSITION, from_state='stopped', to_state='paused')
                    break
                if case(self.SERVICE_STATES.PausePending, self.SERVICE_STATES.Paused):
                    waitfor = self.SERVICE_STATES.Paused
                    if signal == self.SERVICE_SIGNALS.start:
                        control_method = 'ResumeService'
                    break
                if case():
                    raise ServerObjectManagementError(ServerObjectManagementError.UNKNOWN_OBJECT_STATE, state=self.state)
            wait_length = 0
            while self.state != waitfor:
                sleep(_STATUS_CHECK_INTERVAL)
                wait_length += _STATUS_CHECK_INTERVAL
                if timeout and (wait_length > timeout):
                    raise ServerObjectManagementError(ServerObjectManagementError.STATUS_CHECK_TIMEOUT, type='service', state=waitfor.name)

        if control_method:
            if WIN32 and control_method == 'RestartService':
                self.manage(self.SERVICE_SIGNALS.stop, wait, ignore_state)
                self.manage(self.SERVICE_SIGNALS.start, wait, ignore_state)
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
    'Class to provide OS independent process management'
    PROCESS_SIGNALS = Enum('process_signals', ('stop', 'kill'))

    def manage(self, signal, wait=True, timeout=False):
        'Provides a management interface for the process'
        for case in switch(signal):
            if case(self.PROCESS_SIGNALS.stop):
                control_method = 'Terminate'
                break
            if case(self.PROCESS_SIGNALS.kill):
                control_method = 'Terminate' if WIN32 else 'Kill'
                break
            if case():
                raise ServerObjectManagementError(ServerObjectManagementError.UNKNOWN_OBJECT_SIGNAL, signal=signal.name)

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
    'Class to provide OS independent scheduled task management'
    TASK_HOME = Path(getenv('SystemRoot'), 'system32/Tasks') if WIN32 else Path('/opt/cronjobs')
    TASK_NAMESPACE = 'http://schemas.microsoft.com/windows/2004/02/mit/task'
    TASK_SIGNALS = Enum('task_signals', ('enable', 'disable', 'run', 'end'))


class ServerPath:
    'Class to provide an interface for working with remote paths like local ones'
    DEFAULT_REMOTE_COPY_COMMAND = {Server.OS_TYPES.windows: 'robocopy', Server.OS_TYPES.linux: 'pscp' if WIN32 else 'scp'}
    DEFAULT_REMOTE_COPY_ARGS = {Server.OS_TYPES.windows: ['/MIR', '/MT', '/R:0', '/NFL', '/NDL', '/NP', '/NJH', '/NJS'],
                                Server.OS_TYPES.linux: ['-r', '-batch']}

    def __init__(self, server, the_path):
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
        'Returns the name of this remote server'
        if self.server.is_local:
            return self.local
        if self.win_to_win:
            return WindowsPath(f'//{self.server.fqdn}/{self.local}'.replace(':', '$'))
        return f'{self.server.fqdn}:{self.local}'
    parent = property(lambda s: ServerPath(s.server, s.local.parent))

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
        raise ServerPathError(ServerPathError.UNSUPPORTED)


def _get_server_object(server):
    if isinstance(server, Server):
        return server
    if not isinstance(server, str):
        raise TypeError(server)
    return Server(*(server.split('.', 1)))


def _run_task_scheduler(*cmd_args, **sys_cmd_args):
    return syscmd('schtasks.exe', *cmd_args, **sys_cmd_args)
