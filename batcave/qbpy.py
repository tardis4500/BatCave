'This provides a Pythonic interface to the QuickBuild RESTful API'
# cSpell:ignore tful

# Import standard modules
from xml.etree.ElementTree import fromstring, tostring

# Import third-party modules
from requests import codes, delete as req_del, get as req_get, post as req_post
from requests.exceptions import HTTPError

# Import internal modules
from .lang import bool_to_str


class QuickBuildObject:
    'Base class for all QuickBuild objects'
    def __init__(self, console, object_id):
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

    id = property(lambda s: s._object_id)


class QuickBuildBuild(QuickBuildObject):
    'Holds a single QuickBuild build run'


class QuickBuildDashboard(QuickBuildObject):
    'Holds a single QuickBuild dashboard'


class QuickBuildCfg(QuickBuildObject):
    'Holds a single QuickBuild configuration'
    def _get_id(self, thing):
        if isinstance(thing, int):
            return thing
        if isinstance(thing, QuickBuildCfg):
            return thing.id
        else:
            return self._console.configs[thing].id

    def get_children(self, recurse=False):
        'Return the child configurations as a list'
        ans = self._console.qb_runner(f'configurations?parent_id={self._object_id}&recursive=' + bool_to_str(recurse))
        return [QuickBuildCfg(self._console, c.find('id').text) for c in fromstring(ans.text).findall('com.pmease.quickbuild.model.Configuration')]
    children = property(get_children)

    @property
    def latest_build(self):
        'Returns the latest build for this configuration'
        return QuickBuildBuild(self._console, fromstring(self._console.qb_runner(f'latest_builds/{self._object_id}').text).find('id').text)

    def enable(self):
        'Enables this configuration'
        self.disabled = 'false'  # pylint: disable=attribute-defined-outside-init

    def disable(self, wait=False):
        'Disables this configuration and optionally waits for it to complete'
        self.disabled = 'true'  # pylint: disable=attribute-defined-outside-init
        while wait and self.latest_build.status.upper() not in ('SUCCESSFUL', 'FAILED'):
            pass

    def remove(self):
        'Remove this configuration'
        self._console.qb_runner(f'configurations/{self._object_id}', delete=True)

    def copy(self, parent, name, recurse=False):
        'Copy a configuration within a parent'
        new_id = self._console.qb_runner(f'configurations/{self._object_id}/copy?parent_id={self._get_id(parent)}&name={name}&recursive=' + bool_to_str(recurse))
        new_cfg = QuickBuildCfg(self._console, new_id.text)
        self._console.updater()
        return new_cfg

    def reparent(self, newparent, rename=False):
        'Reparent a configuration'
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
        'Rename a configuration'
        cfgxml = fromstring(self._console.qb_runner(f'configurations/{self._object_id}').text)
        name = cfgxml.find('name')
        name.text = newname
        self._console.qb_runner('configurations', cfgxml)
        self._console.updater()
        return self

    def change_var(self, var, val):
        'Change the value of a variable'
        cfgxml = fromstring(self._console.qb_runner(f'configurations/{self._object_id}').text)
        for varxml in cfgxml.find('variables').findall('com.pmease.quickbuild.variable.Variable'):
            if varxml.find('name').text == var:
                valref = varxml.find('valueProvider').find('value')
                valref.text = val
        self._console.qb_runner('configurations', cfgxml)
        return self


class QuickBuildConsole:
    'Container for a QuickBuild console'
    def __init__(self, host, user, password):
        self._host = host
        self._user = user
        self._password = password
        self._update = True
        self.configs = dict()
        self.dashboards = dict()
        self.updater()

    @property
    def update(self):
        'Return the update status'
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
        'Create the dashboard from the dashboard object'
        xml_data = str(dashboard) if isinstance(dashboard, QuickBuildDashboard) else dashboard
        if isinstance(xml_data, str):
            xml_data = fromstring(xml_data)
        id_tag = xml_data.find('id')
        if id_tag is not None:
            xml_data.remove(id_tag)
        xml_data.find('name').text = name
        return QuickBuildDashboard(self, self.qb_runner(f'dashboards', xmldata=xml_data).text)

    def get_dashboard(self, dashboard):
        'Return the dashboard specified by the requested name'
        return self.dashboards[dashboard]

    def has_dashboard(self, dashboard):
        'Determine if the specified dashboard exists'
        return dashboard in self.dashboards

    def updater(self):
        'Update the configuration list'
        if self._update:
            top = QuickBuildCfg(self, 1)
            self.configs = {c.path: c for c in top.get_children(True)}
            self.configs[top.path] = top

            for dashboard in fromstring(self.qb_runner('dashboards').text).iter('com.pmease.quickbuild.model.Dashboard'):
                self.dashboards[dashboard.find('name').text] = QuickBuildDashboard(self, dashboard.find('id').text)

    def qb_runner(self, cmd, xmldata=None, delete=False):
        'Interface to the RESTful API'
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
