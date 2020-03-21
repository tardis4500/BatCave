"""This module provides a Pythonic interface to the QuickBuild RESTful API."""

# Import standard modules
from xml.etree.ElementTree import fromstring, tostring

# Import third-party modules
from requests import codes, delete as req_del, get as req_get, post as req_post
from requests.exceptions import HTTPError

# Import internal modules
from .lang import bool_to_str


class QuickBuildObject:
    """Class to create a universal abstract interface for a QuickBuild object."""

    def __init__(self, console, object_id):
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

    def __str__(self):
        return self._console.qb_runner(self._object_path).text

    def __getattr__(self, attr):
        try:
            return self._console.qb_runner(f'{self._object_path}/{attr}').text
        except HTTPError as err:
            if not err.response.status_code == 500:
                raise
        raise AttributeError(f'{self._object_type.capitalize()} {self._object_id} has no attribute: {attr}')

    def __setattr__(self, attr, value):
        if attr.startswith('_'):
            super().__setattr__(attr, value)
            return

        getattr(self, attr)  # Need to raise AttributeError if this attribute doesn't exist
        object_xml = fromstring(self._console.qb_runner(self._object_path).text)
        object_xml.find(attr).text = value
        self._console.qb_runner(f'{self._object_type}s', object_xml)

    id = property(lambda s: s._object_id, doc='A read-only property which returns the QuickBuild object ID.')


class QuickBuildBuild(QuickBuildObject):
    """Class to create a universal abstract interface for a QuickBuild configuration run."""


class QuickBuildDashboard(QuickBuildObject):
    """Class to create a universal abstract interface for a QuickBuild dashboard."""


class QuickBuildCfg(QuickBuildObject):
    """Class to create a universal abstract interface for a QuickBuild configuration."""

    def _get_id(self, thing):
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
        else:
            return self._console.configs[thing].id

    def get_children(self, recurse=False):
        """Get the child configurations.
        
        Args:
            recurse (optional, default=False): Get the children recursively.
            
        Returns:
            The list of child configurations.
        """
        ans = self._console.qb_runner(f'configurations?parent_id={self._object_id}&recursive=' + bool_to_str(recurse))
        return [QuickBuildCfg(self._console, c.find('id').text) for c in fromstring(ans.text).findall('com.pmease.quickbuild.model.Configuration')]

    children = property(get_children, doc='A read-only property which returns a list of children for the object.')

    @property
    def latest_build(self):
        """A read-only property which returns the latest build for this configuration."""
        return QuickBuildBuild(self._console, fromstring(self._console.qb_runner(f'latest_builds/{self._object_id}').text).find('id').text)

    def enable(self):
        """Enable this configuration.
        
        Returns:
            Nothing.
        """
        self.disabled = 'false'  # pylint: disable=attribute-defined-outside-init

    def disable(self, wait=False):
        """Disable this configuration.
        
        Args:
            wait (optional, default=False): If True, wait for the configuration to be disabled.
            
        Returns:
            Nothing.
        """
        self.disabled = 'true'  # pylint: disable=attribute-defined-outside-init
        while wait and self.latest_build.status.upper() not in ('SUCCESSFUL', 'FAILED'):
            pass

    def remove(self):
        """Remove this configuration.
        
        Returns:
            Nothing.
        """
        self._console.qb_runner(f'configurations/{self._object_id}', delete=True)

    def copy(self, parent, name, recurse=False):
        """Copy this configuration to a new configuration.
        
        Args:
            parent: The parent to which to copy the configuration.
            name: The name of the new configuration.
            recurse (optional, default=False): If True, copy the children configurations also.
            
        Returns:
            The new configuration.
        """
        new_id = self._console.qb_runner(f'configurations/{self._object_id}/copy?parent_id={self._get_id(parent)}&name={name}&recursive=' + bool_to_str(recurse))
        new_cfg = QuickBuildCfg(self._console, new_id.text)
        self._console.updater()
        return new_cfg

    def reparent(self, newparent, rename=False):
        """Reparent this configuration.
        
        Args:
            newparent: The new parent for the configuration.
            rename (optional, default=False): If not False, rename the configuration when moved.
            
        Returns:
            The moved configuration.
        """
        cfgxml = fromstring(self._console.qb_runner(f'configurations/{self._object_id}').text)
        parent = cfgxml.find('parent')
        parent.text = str(newparent.id)
        if rename:
            name = cfgxml.find('name')
            name.text = rename
        self._console.qb_runner('configurations', cfgxml)
        self._console.updater()
        return self

    def rename(self, newname):
        """Rename this configuration.
        
        Args:
            newname: The new name for the configuration.
            
        Returns:
            The renamed configuration.
        """
        cfgxml = fromstring(self._console.qb_runner(f'configurations/{self._object_id}').text)
        name = cfgxml.find('name')
        name.text = newname
        self._console.qb_runner('configurations', cfgxml)
        self._console.updater()
        return self

    def change_var(self, var, val):
        """Change the value of a variable in this configuration.
        
        Args:
            var: The variable to change.
            val: The new value of the variable.
            
        Returns:
            The configuration.
        """
        cfgxml = fromstring(self._console.qb_runner(f'configurations/{self._object_id}').text)
        for varxml in cfgxml.find('variables').findall('com.pmease.quickbuild.variable.Variable'):
            if varxml.find('name').text == var:
                valref = varxml.find('valueProvider').find('value')
                valref.text = val
        self._console.qb_runner('configurations', cfgxml)
        return self


class QuickBuildConsole:
    """Class to create a universal abstract interface for a QuickBuild console."""

    def __init__(self, host, user, password):
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
        self.configs = dict()
        self.dashboards = dict()
        self.updater()

    @property
    def update(self):
        """A read-write property which returns and sets the update state for the console."""
        return self._update

    @update.setter
    def update(self, val):
        self._update = val
        self.updater()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def __getattr__(self, attr):
        if attr in self.configs:
            return self.configs[attr]
        raise AttributeError(f'No such configuration: {attr}')

    def create_dashboard(self, name, dashboard):
        """Create a dashboard from an existing one.
        
        Args:
            name: The name of the new dashboard.
            dashboard: The dashboard from which to make the copy.
            
        Returns:
            The new dashboard.
        """
        xml_data = str(dashboard) if isinstance(dashboard, QuickBuildDashboard) else dashboard
        if isinstance(xml_data, str):
            xml_data = fromstring(xml_data)
        id_tag = xml_data.find('id')
        if id_tag is not None:
            xml_data.remove(id_tag)
        xml_data.find('name').text = name
        return QuickBuildDashboard(self, self.qb_runner(f'dashboards', xmldata=xml_data).text)

    def get_dashboard(self, dashboard):
        """Get the named dashboard.
        
        Args:
            dashboard: The dashboard to return.
            
        Returns:
            The requested dashboard.
        """
        return self.dashboards[dashboard]

    def has_dashboard(self, dashboard):
        """Determine if the specified dashboard exists.
        
        Args:
            dashboard: The dashboard for which to search.
            
        Returns:
            True if the requested dashboard exists, False otherwise.
        """
        return dashboard in self.dashboards

    def updater(self):
        """Update the configuration list.
            
        Returns:
            Nothing.
        """
        if self._update:
            top = QuickBuildCfg(self, 1)
            self.configs = {c.path: c for c in top.get_children(True)}
            self.configs[top.path] = top

            for dashboard in fromstring(self.qb_runner('dashboards').text).iter('com.pmease.quickbuild.model.Dashboard'):
                self.dashboards[dashboard.find('name').text] = QuickBuildDashboard(self, dashboard.find('id').text)

    def qb_runner(self, cmd, xmldata=None, delete=False):
        """Provide an interface to the RESTful API.

        Args:
            cmd: The API command to run.
            xmldata (optional, default=None): Any data to pass to the command.
            delete (optional, default=False): If True, use delete, otherwise use get.
            
        Returns:
            The result of the API call.
        """
        api_call = f'http://{self._host}/rest/{cmd}'
        api_args = {'auth': (self._user, self._password)}
        if delete:
            caller = req_del
        elif xmldata is None:
            caller = req_get
        else:
            caller = req_post
            api_args['data'] = xmldata if isinstance(xmldata, str) else tostring(xmldata)
        result = caller(api_call, **api_args)
        if result.status_code != codes.ok:  # pylint: disable=E1101
            result.raise_for_status()
        return result

# cSpell:ignore tful
