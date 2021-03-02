"""This module provides a Pythonic interface to the TeamCity RESTful API."""

# Import standard modules
from pathlib import Path
from string import Template
from typing import Any, Dict, Optional

# Import third-party modules
import requests
from requests import certs, codes, exceptions  # type: ignore[attr-defined]
from requests.auth import HTTPBasicAuth

# Import internal modules
from .lang import BatCaveError, BatCaveException, FROZEN, BATCAVE_HOME


class TeamCityError(BatCaveException):
    """TeamCity Exceptions.

    Attributes:
        BAD_CONFIG: The requested configuration was not found.
    """
    BAD_CONFIG = BatCaveError(1, Template('Invalid configuration ID: $id'))


class TCBuildConfig:
    """Class to create a universal abstract interface for a TeamCity build configuration."""

    def __init__(self, server: 'TeamCityServer', config_id: str, /):
        """
        Args:
            server: The Teamcity console containing this object.
            config_id: The configuration ID.

        Attributes:
            config_id: The value of the config_id argument.
            info: The configuration info returned from the Teamcity API.
            _server: The value of the server argument.
        """
        self._server = server
        self.config_id = config_id
        try:
            self.info = self._server.api_call('get', 'buildTypes/id:' + self.config_id)
        except exceptions.HTTPError as err:
            raise TeamCityError(TeamCityError.BAD_CONFIG, id=self.config_id) from err

    def __str__(self):
        return str(self.info)

    def __getattr__(self, attr: str):
        if attr in self.info:
            return self.info[attr]
        return self._server.api_call('get', f'buildTypes/id:{self.config_id}/{attr}')


class TeamCityServer:
    """Class to create a universal abstract interface for a TeamCity server."""

    _CA_CERT = (BATCAVE_HOME / 'cacert.pem') if FROZEN else Path(certs.where())

    def __init__(self, host: str, /, user: str, passwd: str, port: str = '80'):
        """
        Args:
            host: The server hosting the Teamcity instance.
            user: The Teamcity user for API access.
            password: The Teamcity password for API access.
            port (optional, default='80'): The port on which the instance is hosted.

        Attributes:
            url: The URL to the Teamcity RESTful API.
            auth: The authorization credentials for the Teamcity server.
        """
        self.url = f'http://{host}:{port}/httpAuth/app/rest/'
        self.auth = HTTPBasicAuth(user, passwd)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    build_configs = property(lambda s: s.api_call('get', 'buildTypes')['buildType'], doc='A read-only property which returns a list of the build configurations.')
    users = property(lambda s: s.api_call('get', 'users')['user'], doc='A read-only property which returns a list of the TeamCity users.')
    groups = property(lambda s: s.api_call('get', 'userGroups')['group'], doc='A read-only property which returns a list of the TeamCity groups.')

    def api_call(self, calltype: str, apicall: str, /, **params) -> Dict[str, Any]:
        """Provide an interface to the TeamCity RESTful API.

        Args:
            calltype: The API call type.
            apicall: The API call.
            **params (optional, default={}): Any parameters to pass to the API call.

        Returns:
            The result of the API call.

        Raises:
            An error unless the result of the API call is OK.
        """
        caller = getattr(requests, calltype)
        result = caller(self.url + apicall, auth=self.auth, headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, json=params, verify=self._CA_CERT)
        if result.status_code != codes.ok:  # pylint: disable=no-member
            raise result.raise_for_status()
        return result.json()

    def create_group(self, name: str, key: Optional[str] = None, /, description: str = '') -> Dict[str, Any]:
        """Create a user group.

        Args:
            name: The name of user group.
            key (optional, default=None): The key name to use for the user group.
            description (optional, default=''): The description to use for the user group.

        Returns:
            The result of the API call to create the user group.
        """
        if not key:
            key = name.upper().replace(' ', '_')
        return self.api_call('post', 'userGroups', name=name, key=key, description=description)

    def create_user(self, username: str, /) -> Dict[str, Any]:
        """Create a user.

        Args:
            username: The name of user.

        Returns:
            The result of the API call to create the user group.
        """
        return self.api_call('post', 'users', username=username)

    def get_build_config(self, config: str, /) -> 'TCBuildConfig':
        """Get the named build configuration.

        Args:
            config: The build configuration to return.

        Returns:
            The requested build configuration.
        """
        return TCBuildConfig(self, config)

# cSpell:ignore cacert
