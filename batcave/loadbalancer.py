"""This module provides utilities for working with load balancers."""

# Import standard modules
from enum import Enum
from string import Template
from time import sleep
from typing import Any

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

# Import internal modules
from .lang import BatCaveError, BatCaveException
from .servermgr import _get_server_object, Server

_STATUS_CHECK_INTERVAL = 2


class LoadBalancerError(BatCaveException):
    """Loadbalancer Exceptions.

    Attributes:
        BAD_OBJECT: The object type was not found in the load balancer.
        BAD_SERVER_SIGNAL: The signal is invalid.
    """
    BAD_OBJECT = BatCaveError(1, Template('Requested $type not in load balancer: $name'))
    BAD_SERVER_SIGNAL = BatCaveError(2, Template('Unknown server signal: $signal'))


class LoadBalancer:
    """Class to create a universal abstract interface for a load balancer.

    Attributes:
        LB_SERVER_SIGNALS: The signals that can be sent to a load balancer to control a server in a VIP.
        LB_TYPES: The supported load balancer types.
        LB_VIP_TYPES: The supported load balancer VIP types.
    """
    LB_SERVER_SIGNALS = Enum('lb_server_signals', ('enable', 'disable'))
    LB_TYPES = Enum('lb_types', ('netscaler',))
    LB_VIP_TYPES = Enum('lb_vip_types', ('HTTP', 'SSL', 'SSL_OFFLOAD'))

    def __init__(self, lb_type, ip_address, user, password):
        """
        Args:
            lb_type: The load balancer type.
            ip_address: The hostname or IP address of the load balancer.
            user: The load balancer user for API access.
            password: The load balancer password for API access.

        Attributes:
            ip_address: The value of the ip_address argument.
            password: The value of the password argument.
            type: The value of the lb_type argument.
            user: The value of the user argument.
            _api: The API object for the load balancer

        Raises:
            StateMachineError.BAD_STATUS: if the value of self.status is not in STATE_STATUSES
        """
        self.type = lb_type
        self.ip_address = ip_address
        self.user = user
        self.password = password
        self._api = NetScalerService(self.ip_address)
        self._api.login(self.user, self.password, 3600)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info: Any):
        self._api.logout()
        return False

    def add_server(self, server_info):
        """Add the specified server to the load balancer.

        Args:
            server_info: The info about the server to add.

        Returns:
            The result of the server add call.
        """
        server_object = _get_server_object(server_info)
        ns_server = NetScalerServer()
        ns_server.name = server_object.hostname
        ns_server.ipaddress = server_object.ip
        NetScalerServer.add(self._api, ns_server)
        return self.get_server(server_info)

    def add_virtual_server(self, server_info, service_type=LB_VIP_TYPES.HTTP, port=None, servers=tuple(), services=tuple(), certificates=tuple(), responder_policies=tuple()):
        """Add a virtual server to the load balancer.

        Args:
            server_info: The info about the virtual server to add.
            service_type (optional, default=LB_VIP_TYPES.HTTP): The service type for the virtual server.
            port (optional, default=None): The port for the virtual server, if None the default is based on the service_type.
                self.LB_VIP_TYPES.HTTP, self.LB_VIP_TYPES.SSL_OFFLOAD: 80
                self.LB_VIP_TYPES.SSL: 443
            servers (optional, default=[]): The list of servers to add to the virtual server.
            certificates (optional, default=[]): The list of certificates to add to the virtual server.
            responder_policies (optional, default=[]): The list of responder policies to add to the virtual server.

        Returns:
            The virtual server if there is not offload server, otherwise a tuple of the virtual server and offload server.
        """
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
        NetScalerVirtualServer.add(self._api, ns_virtual_server)
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

    def flush_cache_content(self, group_name):
        """Flush the specified load balancer cache content group.

        Args:
            group_name: The name of the group to flush.

        Returns:
            The result of the flush call.
        """
        group_ref = self.get_cache_content_group(group_name)
        return NetScalerCacheContentGroup.flush(self._api, group_ref)

    def get_cache_content_group(self, group_name):
        """Get the specified load balancer cache content group.

        Args:
            group_name: The name of the group to return.

        Returns:
            The requested cache content group.

        Raises:
            LoadBalancerError.BAD_OBJECT: If the requested group could not be found.
        """
        try:
            group_ref = NetScalerCacheContentGroup.get(self._api, group_name)
            group_ref.query = group_ref.host = group_ref.selectorvalue = ''
            return group_ref
        except NetScalerError as err:
            if err.errorcode == 258:
                raise LoadBalancerError(LoadBalancerError.BAD_OBJECT, type='cache content group', name=group_name)
            raise

    def get_server(self, server_info):
        """Get the specified server from the load balancer.

        Args:
            server_info: The info about the server to return.

        Returns:
            The requested server.

        Raises:
            LoadBalancerError.BAD_OBJECT: If the requested server could not be found.
        """
        server_hostname = _get_server_object(server_info).hostname
        try:
            return LoadBalancerServer(self, NetScalerServer.get(self._api, server_hostname))
        except NetScalerError as err:
            if err.errorcode == 258:
                raise LoadBalancerError(LoadBalancerError.BAD_OBJECT, type='server', name=server_hostname)
            raise

    def get_virtual_server(self, server_name):
        """Get the specified virtual server from the load balancer.

        Args:
            server_name: The name of the virtual server to return.

        Returns:
            The requested server virtual.

        Raises:
            LoadBalancerError.BAD_OBJECT: If the requested virtual server could not be found.
        """
        server_hostname = _get_server_object(server_name).hostname
        try:
            return LoadBalancerVirtualServer(self, NetScalerVirtualServer.get(self._api, server_hostname))
        except NetScalerError as err:
            if err.errorcode == 258:
                raise LoadBalancerError(LoadBalancerError.BAD_OBJECT, type='virtual server', name=server_hostname)
            raise

    def has_server(self, server_info):
        """Determine if the load balancer server exists.

        Args:
            server_info: The info about the server for which to search.

        Returns:
            True if the requested server exists, False otherwise.
        """
        try:
            self.get_server(server_info)
        except LoadBalancerError as err:
            if err.code == LoadBalancerError.BAD_OBJECT.code:
                return False
            raise
        else:
            return True

    def manage_servers(self, signal, servers, validate=True):
        """Perform an action on servers managed by the load balancer.

        Args:
            signal: The action to perform on the managed server.
            servers: The list of servers to manage.
            validate (optional, default=True): Confirm that the request action is complete.

        Returns:
            Nothing.

        Raises:
            LoadBalancerError.BAD_OBJECT: If the requested virtual server could not be found.
        """
        if signal not in (self.LB_SERVER_SIGNALS.enable, self.LB_SERVER_SIGNALS.disable):
            raise LoadBalancerError(LoadBalancerError.BAD_SERVER_SIGNAL, signal=signal.name)

        if not (isinstance(servers, tuple) or isinstance(servers, list)):
            servers = [servers]

        for server in [_get_server_object(s) for s in servers]:
            getattr(NetScalerServer, signal.name)(self._api, server.hostname)
            while validate and (self.get_server(server).state.lower() != (signal.name + 'd')):
                sleep(_STATUS_CHECK_INTERVAL)


class LoadBalancerObject:
    """Class to create a universal abstract interface for an object in a load balancer."""

    def __init__(self, load_balancer_ref, lb_object_ref):
        """
        Args:
            load_balancer_ref: The load balancer object containing this object.
            lb_object_ref: The load balancer API object reference.

        Attributes:
            load_balancer_ref: The value of the load_balancer_ref argument.
            lb_object_ref: The value of the lb_object_ref argument.
        """
        self.load_balancer_ref = load_balancer_ref
        self.lb_object_ref = lb_object_ref

    def __getattr__(self, attr):
        return getattr(self.lb_object_ref, attr)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info: Any):
        return False


class LoadBalancerServer(LoadBalancerObject):
    """Class to create a universal abstract interface for a load balancer server."""

    def add_service(self, service_name, service_type='HTTP', port=80):
        """Add a service to a server in the load balancer.

        Args:
            service_name: The name of the service to add.
            server_type (optional, default='HTTP'): The type of the service to add.
            port (optional, default=80): The port for the service to add.

        Returns:
            The added service.
        """
        ns_service = NetScalerServerService()
        ns_service.servicetype = service_type
        ns_service.name = service_name
        ns_service.servername = self.lb_object_ref.name
        ns_service.port = port
        NetScalerServerService.add(self.load_balancer_ref.ns_session, ns_service)
        return self.get_service(service_name)

    def get_service(self, service_name):
        """Get the specified service.

        Args:
            service_name: The name of the service to return.

        Returns:
            The requested service.

        Raises:
            LoadBalancerError.BAD_OBJECT: If the requested service could not be found.
        """
        try:
            return LoadBalancerService(self, NetScalerServerService.get(self.load_balancer_ref.ns_session, service_name))
        except NetScalerError as err:
            if err.errorcode == 258:
                raise LoadBalancerError(LoadBalancerError.BAD_OBJECT, type='service', name=service_name)
            raise


class LoadBalancerService(LoadBalancerObject):
    """Class to create a universal abstract interface for a load balancer service."""


class LoadBalancerVirtualServer(LoadBalancerObject):
    """Class to create a universal abstract interface for a load balancer virtual server."""

    def bind_certificate(self, cert_name):
        """Bind a certificate to the virtual server.

        Args:
            cert_name: The name of the certificate to bind.

        Returns:
            Nothing.
       """
        ns_certificate_binding = NetScalerCertificateBinding()
        ns_certificate_binding.vservername = self.name
        ns_certificate_binding.certkeyname = cert_name
        NetScalerCertificateBinding.add(self.load_balancer_ref.ns_session, ns_certificate_binding)

    def bind_responder_policy(self, policy_name, policy_priority=100):
        """Bind a responder policy to the virtual server.

        Args:
            policy_name: The name of the responder policy to bind.
            policy_priority (optional, default=100): The priority of the policy to bind.

        Returns:
            Nothing.
       """
        ns_policy_binding = NetScalerResponderPolicyBinding()
        ns_policy_binding.name = self.name
        ns_policy_binding.policyname = policy_name
        ns_policy_binding.priority = policy_priority
        NetScalerResponderPolicyBinding.add(self.load_balancer_ref.ns_session, ns_policy_binding)

    def bind_service(self, service):
        """Bind a service to the virtual server.

        Args:
            service: The service to bind.

        Returns:
            Nothing.
       """
        ns_virtual_service_binding = NetScalerVirtualServiceBinding()
        ns_virtual_service_binding.name = self.name
        ns_virtual_service_binding.servicename = service.name if isinstance(service, LoadBalancerService) else service
        NetScalerVirtualServiceBinding.add(self.load_balancer_ref.ns_session, ns_virtual_service_binding)

# cSpell:ignore ipaddress nssrc lbvserver sslcertkey sslvserver vservername
