"""This module provides a Pythonic interface to the QuickBuild RESTful API."""

# Import standard modules
from typing import cast, Any, Dict, List, Optional, Union
from xml.etree.ElementTree import fromstring, tostring, Element

# Import third-party modules
from requests import codes, delete as req_del, get as req_get, post as req_post, Response
from requests.exceptions import HTTPError

# Import internal modules
from .lang import bool_to_str


class QuickBuildObject:
    """Class to create a universal abstract interface for a QuickBuild object."""

    def __init__(self, console: 'QuickBuildConsole', object_id: Union[int, str], /):
        """
        Args:
            console: The QuickBuild console containing this object.
            object_id: The object ID.

        Attributes:
            _console: The value of the console argument.
            _object_id: The value of the object_id argument.
            _object_path: The RESTful API path to the object.
            _object_type: The object type.
        """
        self._console = console
        self._object_id = int(object_id)
        object_name = self.__class__.__name__.lower().replace('quickbuild', '')
        self._object_type = 'configuration' if (object_name == 'cfg') else f'{object_name}'
        self._object_path = f'{self._object_type}s/{self._object_id}'

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def __getattr__(self, attr: str) -> Optional[str]:
        try:
            return self._console.qb_runner(f'{self._object_path}/{attr}').text
        except HTTPError as err:
            if not err.response.status_code == 500:
                raise
        raise AttributeError(f'{self._object_type.capitalize()} {self._object_id} has no attribute: {attr}')

    def __setattr__(self, attr: str, value: str) -> None:
        if attr.startswith('_'):
            super().__setattr__(attr, value)
            return

        getattr(self, attr)  # Need to raise AttributeError if this attribute doesn't exist
        object_xml = fromstring(self._console.qb_runner(self._object_path).text)
        attr_element = cast(Element, object_xml.find(attr))
        attr_element.text = value
        self._console.qb_runner(f'{self._object_type}s', xmldata=object_xml)

    def __str__(self):
        return self._console.qb_runner(self._object_path).text

    id = property(lambda s: s._object_id, doc='A read-only property which returns the QuickBuild object ID.')


class QuickBuildBuild(QuickBuildObject):  # pylint: disable=too-few-public-methods
    """Class to create a universal abstract interface for a QuickBuild configuration run."""


class QuickBuildDashboard(QuickBuildObject):  # pylint: disable=too-few-public-methods
    """Class to create a universal abstract interface for a QuickBuild dashboard."""


class QuickBuildCfg(QuickBuildObject):
    """Class to create a universal abstract interface for a QuickBuild configuration."""

    def _get_id(self, thing: Union[int, 'QuickBuildCfg'], /) -> int:
        """Get the ID of the specified configuration.

        Args:
            thing: The configuration for which to return the ID.

        Returns:
            The ID of the specified configuration.
        """
        if isinstance(thing, int):
            return thing
        if isinstance(thing, QuickBuildCfg):
            return thing.id
        return self._console.configs[thing].id

    @property
    def latest_build(self) -> QuickBuildBuild:
        """A read-only property which returns the latest build for this configuration."""
        build_element = str(cast(Element, fromstring(self._console.qb_runner(f'latest_builds/{self._object_id}').text).find('id')).text)
        return QuickBuildBuild(self._console, build_element)

    def change_var(self, var: str, val: str, /) -> 'QuickBuildCfg':
        """Change the value of a variable in this configuration.

        Args:
            var: The variable to change.
            val: The new value of the variable.

        Returns:
            The configuration.
        """
        cfgxml = fromstring(self._console.qb_runner(f'configurations/{self._object_id}').text)
        for varxml in cast(Element, cfgxml.find('variables')).findall('com.pmease.quickbuild.variable.Variable'):
            if cast(Element, varxml.find('name')).text == var:
                valref = cast(Element, cast(Element, varxml.find('valueProvider')).find('value'))
                valref.text = val
        self._console.qb_runner('configurations', xmldata=cfgxml)
        return self

    def copy(self, parent: 'QuickBuildCfg', name: str, /, *, recurse: bool = False) -> 'QuickBuildCfg':
        """Copy this configuration to a new configuration.

        Args:
            parent: The parent to which to copy the configuration.
            name: The name of the new configuration.
            recurse (optional, default=False): If True, copy the children configurations also.

        Returns:
            The new configuration.
        """
        new_id = self._console.qb_runner(f'configurations/{self._object_id}/copy?parent_id={self._get_id(parent)}&name={name}&recursive=' + bool_to_str(recurse))
        new_cfg = QuickBuildCfg(self._console, str(new_id.text))
        self._console.updater()
        return new_cfg

    def disable(self, /, *, wait: bool = False) -> None:
        """Disable this configuration.

        Args:
            wait (optional, default=False): If True, wait for the configuration to be disabled.

        Returns:
            Nothing.
        """
        self.disabled = 'true'  # pylint: disable=attribute-defined-outside-init
        while wait and str(self.latest_build.status).upper() not in ('SUCCESSFUL', 'FAILED'):
            pass

    def enable(self) -> None:
        """Enable this configuration.

        Returns:
            Nothing.
        """
        self.disabled = 'false'  # pylint: disable=attribute-defined-outside-init

    def get_children(self, /, *, recurse: bool = False) -> List['QuickBuildCfg']:
        """Get the child configurations.

        Args:
            recurse (optional, default=False): Get the children recursively.

        Returns:
            The list of child configurations.
        """
        ans = self._console.qb_runner(f'configurations?parent_id={self._object_id}&recursive=' + bool_to_str(recurse))
        return [QuickBuildCfg(self._console, str(cast(Element, c.find('id')).text)) for c in fromstring(ans.text).findall('com.pmease.quickbuild.model.Configuration')]

    children = property(get_children, doc='A read-only property which returns a list of children for the object.')

    def remove(self) -> None:
        """Remove this configuration.

        Returns:
            Nothing.
        """
        self._console.qb_runner(f'configurations/{self._object_id}', delete=True)

    def rename(self, newname: str, /) -> 'QuickBuildCfg':
        """Rename this configuration.

        Args:
            newname: The new name for the configuration.

        Returns:
            The renamed configuration.
        """
        cfgxml = fromstring(self._console.qb_runner(f'configurations/{self._object_id}').text)
        name = cast(Element, cfgxml.find('name'))
        name.text = newname
        self._console.qb_runner('configurations', xmldata=cfgxml)
        self._console.updater()
        return self

    def reparent(self, newparent: 'QuickBuildCfg', /, *, rename: bool = False) -> 'QuickBuildCfg':
        """Reparent this configuration.

        Args:
            newparent: The new parent for the configuration.
            rename (optional, default=False): If not False, rename the configuration when moved.

        Returns:
            The moved configuration.
        """
        cfgxml = fromstring(self._console.qb_runner(f'configurations/{self._object_id}').text)
        parent = cast(Element, cfgxml.find('parent'))
        parent.text = str(newparent.id)
        if rename:
            name = cast(Element, cfgxml.find('name'))
            name.text = bool_to_str(rename)
        self._console.qb_runner('configurations', xmldata=cfgxml)
        self._console.updater()
        return self


class QuickBuildConsole:
    """Class to create a universal abstract interface for a QuickBuild console."""

    def __init__(self, host: str, /, *, user: str, password: str):
        """
        Args:
            host: The server hosting the QuickBuild console.
            user: The QuickBuild user for API access.
            password: The QuickBuild password for API access.

        Attributes:
            _host: The value of the host argument.
            _password: The value of the password argument.
            _update: When True, the internal values need to be refreshed from the API.
            _user: The value of the user argument.
        """
        self._host = host
        self._user = user
        self._password = password
        self._update = True
        self.configs: Dict[str, QuickBuildCfg] = dict()
        self.dashboards: Dict[str, QuickBuildDashboard] = dict()
        self.updater()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def __getattr__(self, attr: str) -> QuickBuildCfg:
        if attr in self.configs:
            return self.configs[attr]
        raise AttributeError(f'No such configuration: {attr}')

    @property
    def update(self) -> bool:
        """A read-write property which returns and sets the update state for the console."""
        return self._update

    @update.setter
    def update(self, val: bool) -> None:
        self._update = val
        self.updater()

    def create_dashboard(self, name: str, dashboard: Union[str, QuickBuildDashboard], /) -> QuickBuildDashboard:
        """Create a dashboard from an existing one.

        Args:
            name: The name of the new dashboard.
            dashboard: The dashboard from which to make the copy.

        Returns:
            The new dashboard.
        """
        xml_data: Union[str, Element] = str(dashboard) if isinstance(dashboard, QuickBuildDashboard) else dashboard
        if isinstance(xml_data, str):
            xml_data = fromstring(xml_data)
        if (id_tag := xml_data.find('id')) is not None:
            xml_data.remove(id_tag)
        cast(Element, xml_data.find('name')).text = name
        return QuickBuildDashboard(self, str(self.qb_runner('dashboards', xmldata=xml_data).text))

    def get_dashboard(self, dashboard: str, /) -> QuickBuildDashboard:
        """Get the named dashboard.

        Args:
            dashboard: The dashboard to return.

        Returns:
            The requested dashboard.
        """
        return self.dashboards[dashboard]

    def has_dashboard(self, dashboard: str, /) -> bool:
        """Determine if the specified dashboard exists.

        Args:
            dashboard: The dashboard for which to search.

        Returns:
            True if the requested dashboard exists, False otherwise.
        """
        return dashboard in self.dashboards

    def qb_runner(self, cmd: str, /, *, xmldata: Optional[Any] = None, delete: bool = False) -> Response:
        """Provide an interface to the RESTful API.

        Args:
            cmd: The API command to run.
            xmldata (optional, default=None): Any data to pass to the command.
            delete (optional, default=False): If True, use delete, otherwise use get.

        Returns:
            The result of the API call.
        """
        api_call = f'http://{self._host}/rest/{cmd}'
        api_args: Dict[str, Any] = {'auth': (self._user, self._password)}
        if delete:
            caller = req_del
        elif xmldata is None:
            caller = req_get
        else:
            caller = req_post
            api_args['data'] = xmldata if isinstance(xmldata, str) else tostring(xmldata)
        if (result := caller(api_call, **api_args)).status_code != codes.ok:  # pylint: disable=no-member
            result.raise_for_status()
        return result

    def updater(self) -> None:
        """Update the configuration list.

        Returns:
            Nothing.
        """
        if self._update:
            top = QuickBuildCfg(self, 1)
            self.configs = {str(c.path): c for c in top.get_children(recurse=True)}
            self.configs[str(top.path)] = top

            for dashboard in fromstring(self.qb_runner('dashboards').text).iter('com.pmease.quickbuild.model.Dashboard'):
                self.dashboards[str(cast(Element, dashboard.find('name')).text)] = QuickBuildDashboard(self, str(cast(Element, dashboard.find('id')).text))

# cSpell:ignore tful
