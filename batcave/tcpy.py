'TeamCity API interface'
# cSpell:ignore cacert

# Import standard modules
from pathlib import Path
from string import Template

# Import third-party modules
import requests
from requests import certs, codes, exceptions
from requests.auth import HTTPBasicAuth

# Import internal modules
from .lang import HALError, HALException, FROZEN, BATCAVE_HOME


class TeamCityError(HALException):
    'Container for TeamCity exceptions'
    INVALID_CONFIG = HALError(1, Template('Invalid configuration ID: $id'))


class TCBuildConfig:
    'Encapsulates a Build Configuration'
    def __init__(self, server, config_id):
        self._server = server
        self.config_id = config_id
        fail = False
        try:
            self.info = self._server.api_call('get', 'buildTypes/id:'+self.config_id)
        except exceptions.HTTPError:
            fail = True
        if fail:
            raise TeamCityError(TeamCityError.INVALID_CONFIG, id=self.config_id)

    def __str__(self):
        return str(self.info)

    def __getattr__(self, attr):
        if attr in self.info:
            return self.info[attr]
        return self._server.api_call('get', f'buildTypes/id:{self.config_id}/{attr}')


class TeamCityServer:
    'Represents a TeamCity server'
    _CA_CERT = (BATCAVE_HOME / 'cacert.pem') if FROZEN else Path(certs.where())

    def __init__(self, host, user, passwd, port='80'):
        self.url = f'http://{host}:{port}/httpAuth/app/rest/'
        self.auth = HTTPBasicAuth(user, passwd)

    users = property(lambda s: s.api_call('get', 'users')['user'])
    groups = property(lambda s: s.api_call('get', 'userGroups')['group'])
    build_configs = property(lambda s: s.api_call('get', 'buildTypes')['buildType'])

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def api_call(self, calltype, apicall, **params):
        'Make calls to the TeamCity API'
        caller = getattr(requests, calltype)
        result = caller(self.url+apicall, auth=self.auth, headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, json=params, verify=self._CA_CERT)
        if result.status_code != codes.ok:  # pylint: disable=E1101
            raise result.raise_for_status()
        return result.json()

    def create_group(self, name, key=None, description=''):
        'Create a user group'
        if not key:
            key = name.upper().replace(' ', '_')
        return self.api_call('post', 'userGroups', name=name, key=key, description=description)

    def create_user(self, username):
        'Creates a user'
        return self.api_call('post', 'users', username=username)

    def get_build_config(self, config):
        'Gets a build configuration'
        return TCBuildConfig(self, config)
