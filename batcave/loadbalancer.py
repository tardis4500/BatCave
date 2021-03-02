"""This module provides utilities for working with load balancers."""

# Import standard modules
from enum import Enum
from string import Template
from time import sleep
from typing import cast, Iterable, Optional, Tuple, Type, Union

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
from .servermgr import get_server_object, Server, ServerType

_STATUS_CHECK_INTERVAL = 2

LbServerSignal = Enum('LbServerSignal', ('enable', 'disable'))
LbType = Enum('LbType', ('netscaler',))
LbVipType = Enum('LbVipType', ('HTTP', 'SSL', 'SSL_OFFLOAD'))


class LoadBalancerError(BatCaveException):
    """Loadbalancer Exceptions.

    Attributes:
        BAD_OBJECT: The object type was not found in the load balancer.
        BAD_SERVER_SIGNAL: The signal is invalid.
    """
    BAD_OBJECT = BatCaveError(1, Template('Requested $type not in load balancer: $name'))
    BAD_SERVER_SIGNAL = BatCaveError(2, Template('Unknown server signal: $signal'))


class LoadBalancer:
    """Class to create a universal abstract interface for a load balancer."""

    def __init__(self, lb_type: LbType, ip_address: str, /, user: str, password: str):
        """
        Args:
            lb_type: The load balancer type.
            ip_address: The hostname or IP address of the load balancer.
            user: The load balancer user for API access.
            password: The load balancer password for API access.

        Attributes:
            ip_address: The value of the ip_address argument.
            type: The value of the lb_type argument.
            _api: The API object for the load balancer

        Raises:
            StateMachineError.BAD_STATUS: if the value of self.status is not in STATE_STATUSES
        """
        self._type = lb_type
        self._ip_address = ip_address
        self._api = NetScalerService(self.ip_address)
        self._api.login(user, password, 3600)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self._api.logout()
        return False

    ip_address = property(lambda s: s._ip_address, doc='A read-only property which returns the IP address of the load balancer.')
    type = property(lambda s: s._type, doc='A read-only property which returns the type of the load balancer.')

    def add_server(self, server_info: ServerType, /) -> 'LoadBalancerServer':
        """Add the specified server to the load balancer.

        Args:
            server_info: The info about the server to add.

        Returns:
            The result of the server add call.
        """
        server_object = get_server_object(server_info)
        ns_server = NetScalerServer()
        ns_server.name = server_object.hostname
        ns_server.ipaddress = server_object.ip
        NetScalerServer.add(self._api, ns_server)
        return self.get_server(server_info)

    def add_virtual_server(self, server_info: ServerType, /, *, service_type: LbVipType = LbVipType.HTTP,  # pylint: disable=too-many-locals
                           port: Optional[int] = None, servers: Iterable[ServerType] = tuple(),
                           services: Iterable = tuple(), certificates: Iterable = tuple(),
                           responder_policies: Iterable = tuple()) -> Union['LoadBalancerVirtualServer', Tuple['LoadBalancerVirtualServer', 'LoadBalancerVirtualServer']]:
        """Add a virtual server to the load balancer.

        Args:
            server_info: The info about the virtual server to add.
            service_type (optional, default=LbVipType.HTTP): The service type for the virtual server.
            port (optional, default=None): The port for the virtual server, if None the default is based on the service_type.
                LbVipType.HTTP, LbVipType.SSL_OFFLOAD: 80
                LbVipType.SSL: 443
            servers (optional, default=[]): The list of servers to add to the virtual server.
            certificates (optional, default=[]): The list of certificates to add to the virtual server.
            responder_policies (optional, default=[]): The list of responder policies to add to the virtual server.

        Returns:
            The virtual server if there is not offload server, otherwise a tuple of the virtual server and offload server.
        """
        port_value = None
        if port is not None:
            port_value = port
        elif service_type in (LbVipType.HTTP, LbVipType.SSL_OFFLOAD):
            port_value = 80
        elif service_type == LbVipType.SSL:
            port_value = 443
        else:
            port_value = port

        server_objects = [get_server_object(s) for s in (list(servers) if isinstance(servers, (tuple, list)) else [servers])]  # pylint: disable=superfluous-parens
        service_objects = list(services) if isinstance(services, (tuple, list)) else [services]
        certificates = certificates if isinstance(certificates, (tuple, list)) else [certificates]
        responder_policies = responder_policies if isinstance(responder_policies, (tuple, list)) else [responder_policies]

        server_object = get_server_object(server_info)
        ns_virtual_server = NetScalerVirtualServer()
        ns_virtual_server.name = server_object.hostname
        ns_virtual_server.servicetype = 'HTTP' if (service_type == LbVipType.SSL_OFFLOAD) else service_type.name
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
        if service_type == LbVipType.SSL:
            for cert in certificates:
                virtual_server.bind_certificate(cert)
        elif service_type == LbVipType.SSL_OFFLOAD:
            server_object = get_server_object(server_info)
            offload_server_object = Server(f'{server_object.hostname}_offload', ip=server_object.ip)
            offload_server = self.add_virtual_server(offload_server_object, service_type=LbVipType.SSL, services=service_objects, certificates=certificates)

        return (virtual_server, offload_server) if offload_server else virtual_server  # type: ignore[return-value]

    def flush_cache_content(self, group_name: str, /) -> str:
        """Flush the specified load balancer cache content group.

        Args:
            group_name: The name of the group to flush.

        Returns:
            The result of the flush call.
        """
        return NetScalerCacheContentGroup.flush(self._api, self.get_cache_content_group(group_name))

    def get_cache_content_group(self, group_name: str, /) -> str:
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
                raise LoadBalancerError(LoadBalancerError.BAD_OBJECT, type='cache content group', name=group_name) from err
            raise

    def get_server(self, server_info: ServerType, /) -> 'LoadBalancerServer':
        """Get the specified server from the load balancer.

        Args:
            server_info: The info about the server to return.

        Returns:
            The requested server.

        Raises:
            LoadBalancerError.BAD_OBJECT: If the requested server could not be found.
        """
        server_hostname = get_server_object(server_info).hostname
        try:
            return LoadBalancerServer(self, NetScalerServer.get(self._api, server_hostname))
        except NetScalerError as err:
            if err.errorcode == 258:
                raise LoadBalancerError(LoadBalancerError.BAD_OBJECT, type='server', name=server_hostname) from err
            raise

    def get_virtual_server(self, server_name: ServerType, /) -> 'LoadBalancerVirtualServer':
        """Get the specified virtual server from the load balancer.

        Args:
            server_name: The name of the virtual server to return.

        Returns:
            The requested server virtual.

        Raises:
            LoadBalancerError.BAD_OBJECT: If the requested virtual server could not be found.
        """
        server_hostname = get_server_object(server_name).hostname
        try:
            return LoadBalancerVirtualServer(self, NetScalerVirtualServer.get(self._api, server_hostname))
        except NetScalerError as err:
            if err.errorcode == 258:
                raise LoadBalancerError(LoadBalancerError.BAD_OBJECT, type='virtual server', name=server_hostname) from err
            raise

    def has_server(self, server_info: ServerType, /) -> bool:
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

    def manage_servers(self, signal: LbServerSignal, servers: Union[ServerType, Iterable[ServerType]], /, *, validate: bool = True) -> None:
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
        if signal not in (LbServerSignal.enable, LbServerSignal.disable):
            raise LoadBalancerError(LoadBalancerError.BAD_SERVER_SIGNAL, signal=signal.name)

        server_list = servers if isinstance(servers, (tuple, list)) else [cast(ServerType, servers)]
        for server in [get_server_object(s) for s in server_list]:
            getattr(NetScalerServer, signal.name)(self._api, server.hostname)
            while validate and (self.get_server(server).state.lower() != (signal.name + 'd')):
                sleep(_STATUS_CHECK_INTERVAL)


class LoadBalancerObject:
    """Class to create a universal abstract interface for an object in a load balancer."""

    def __init__(self, load_balancer_ref: NetScalerServer, lb_object_ref: Type['LoadBalancerObject'], /):
        """
        Args:
            load_balancer_ref: The load balancer API object reference.
            lb_object_ref: The load balancer object containing this object.

        Attributes:
            _lb_object_ref: The value of the lb_object_ref argument.
            _load_balancer_ref: The value of the load_balancer_ref argument.
        """
        self._load_balancer_ref = load_balancer_ref
        self._lb_object_ref = lb_object_ref

    def __getattr__(self, attr: str) -> str:
        return getattr(self._lb_object_ref, attr)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class LoadBalancerServer(LoadBalancerObject):
    """Class to create a universal abstract interface for a load balancer server."""

    def add_service(self, service_name: str, /, *, service_type: str = 'HTTP', port: int = 80) -> 'LoadBalancerService':
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
        ns_service.servername = self._lb_object_ref.name  # type: ignore[attr-defined]
        ns_service.port = port
        NetScalerServerService.add(self._load_balancer_ref.ns_session, ns_service)
        return self.get_service(service_name)

    def get_service(self, service_name: str, /) -> 'LoadBalancerService':
        """Get the specified service.

        Args:
            service_name: The name of the service to return.

        Returns:
            The requested service.

        Raises:
            LoadBalancerError.BAD_OBJECT: If the requested service could not be found.
        """
        try:
            return LoadBalancerService(self, NetScalerServerService.get(self._load_balancer_ref.ns_session, service_name))
        except NetScalerError as err:
            if err.errorcode == 258:
                raise LoadBalancerError(LoadBalancerError.BAD_OBJECT, type='service', name=service_name) from err
            raise


class LoadBalancerService(LoadBalancerObject):  # pylint: disable=too-few-public-methods
    """Class to create a universal abstract interface for a load balancer service."""


class LoadBalancerVirtualServer(LoadBalancerObject):
    """Class to create a universal abstract interface for a load balancer virtual server."""

    def bind_certificate(self, cert_name: str, /) -> None:
        """Bind a certificate to the virtual server.

        Args:
            cert_name: The name of the certificate to bind.

        Returns:
            Nothing.
       """
        ns_certificate_binding = NetScalerCertificateBinding()
        ns_certificate_binding.vservername = self.name
        ns_certificate_binding.certkeyname = cert_name
        NetScalerCertificateBinding.add(self._load_balancer_ref.ns_session, ns_certificate_binding)

    def bind_responder_policy(self, policy_name: str, /, *, policy_priority: int = 100) -> None:
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
        NetScalerResponderPolicyBinding.add(self._load_balancer_ref.ns_session, ns_policy_binding)

    def bind_service(self, service: LoadBalancerService, /) -> None:
        """Bind a service to the virtual server.

        Args:
            service: The service to bind.

        Returns:
            Nothing.
       """
        ns_virtual_service_binding = NetScalerVirtualServiceBinding()
        ns_virtual_service_binding.name = self.name
        ns_virtual_service_binding.servicename = service.name if isinstance(service, LoadBalancerService) else service
        NetScalerVirtualServiceBinding.add(self._load_balancer_ref.ns_session, ns_virtual_service_binding)

# cSpell:ignore ipaddress nssrc lbvserver sslcertkey sslvserver vservername
