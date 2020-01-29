"""This module provides utilities for managing cloud resources.

Attributes:
    _CLOUD_TYPES (Enum): The cloud providers supported by the Cloud class.
    gcloud (SysCmdRunner.run): A simple interface to the gcloud command line tool.
"""

# Import standard modules
from ast import literal_eval
from enum import Enum
from json import loads as json_read
from pathlib import Path
from string import Template
from typing import Any

# Import third-party modules
from docker import DockerClient

# Import internal modules
from .lang import switch, BatCaveError, BatCaveException, WIN32
from .sysutil import SysCmdRunner

_CLOUD_TYPES = Enum('cloud_types', ('local', 'gcloud', 'dockerhub'))

gcloud = SysCmdRunner('gcloud', '-q', use_shell=WIN32).run  # pylint: disable=invalid-name


class CloudError(BatCaveException):
    """Cloud Exceptions.

    Attributes:
        IMAGE_ERROR: There was an error working with a container image.
        INVALID_OPERATION: The specified cloud type does not support the requested operation.
        INVALID_TYPE: An invalid cloud type was specified.
    """
    IMAGE_ERROR = BatCaveError(1, Template('Error ${action}ing image: $err'))
    INVALID_OPERATION = BatCaveError(2, Template('Invalid Cloud type ($ctype) for this operation'))
    INVALID_TYPE = BatCaveError(3, Template('Invalid Cloud type ($ctype). Must be one of: ' + str([t.name for t in _CLOUD_TYPES])))


class Cloud:
    """Class to create a universal abstract interface for a cloud instance.

    Attributes:
        CLOUD_TYPES: The cloud providers currently supported by this class.
        containers: A read-only property that calls the get_containers() method with no filters.
    """
    CLOUD_TYPES: Enum = _CLOUD_TYPES

    def __init__(self, ctype: CLOUD_TYPES, auth: Any = None, login: bool = True):
        """
        Args:
            ctype: The cloud provider for this instance. Must be a member of _CLOUD_TYPES
            auth (optional, default=None): For local or Docker Hub this is a (username, password) tuple.
                For Google Cloud it is a service account keyfile found at ~/.ssh/{value}.json
            login (optional, default=True): Whether or not to login to the cloud provider at instance initialization.

        Attributes:
            auth: The value of the auth argument.
            type: The value of the ctype argument.
            _client: A reference to the underlying client API object.
        """
        self.type = ctype
        self.auth = auth
        self._client = None
        validatetype(self.type)
        if login:
            self.login()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def login(self):
        """Perform a login to the cloud provider.

        Returns:
            Nothing

        Raises:
            CloudError.INVALID_OPERATION: if the value of self.ctype is not in CLOUD_TYPES
        """
        for case in switch(self.type):
            if case(self.CLOUD_TYPES.local, self.CLOUD_TYPES.dockerhub):
                self._client = DockerClient()
                if self.type == self.CLOUD_TYPES.dockerhub:
                    self._client.login(*self.auth)
                break
            if case(self.CLOUD_TYPES.gcloud):
                gcloud(None, 'auth', 'activate-service-account', '--key-file', Path.home() / '.ssh' / (self.auth[0]+'.json'), ignore_stderr=True)
                gcloud(None, 'auth', 'configure-docker', ignore_stderr=True)
                self._client = True
                break
            if case():
                raise CloudError(CloudError.INVALID_OPERATION, ctype=self.type.name)

    def get_image(self, tag: str) -> Image:  # noqa:F821, pylint: disable=used-before-assignment
        """Get an image from the cloud container registry.

        Args:
            tag: the container image tag to retrive

        Returns:
            The image object
        """
        return Image(self, tag)

    def get_container(self, name: str) -> Container:  # noqa:F821, pylint: disable=used-before-assignment
        """Get a container from the cloud.

        Args:
            name: the container name to retrive

        Returns:
            The container object
        """
        return Container(self, name)

    def get_containers(self, filters=None):
        """Get a possibly filtered list of containers.

        Args:
            filter (optional): the container name to retrive

        Returns:
            The container object
        """
        for case in switch(self.type):
            if case(self.CLOUD_TYPES.local, self.CLOUD_TYPES.dockerhub):
                return [Container(self, c.name) for c in self._client.containers.list(filters=filters)]
            if case():
                raise CloudError(CloudError.INVALID_OPERATION, ctype=self.type.name)
    containers = property(get_containers)

    def exec(self, *args, **opts):
        'Execute a command against the cloud API'
        for case in switch(self.type):
            if case(self.CLOUD_TYPES.gcloud):
                return gcloud(None, *args, **opts)
            if case():
                raise CloudError(CloudError.INVALID_OPERATION, ctype=self.type.name)


class Image:
    """Class to create a universal abstract interface to a container image.

    Attributes:
        containers: A read-only property that will return all the containers for this image.
        tags: A read-only property that will return all the tags for this image.
    """

    def __init__(self, cloud, name):
        """
        Args:
            cloud: The API cloud reference.
            name: The image name.

        Attributes:
            cloud: The value of the cloud argument.
            name: The value of the name argument.
            _docker_client: A reference to the client from the Docker API.
            _ref: A reference to the underlying API object.

        Raises:
            CloudError.INVALID_OPERATION: If the specified cloud type is not supported.
        """
        self.cloud = cloud
        self.name = name
        self._docker_client = self.cloud.client if isinstance(self.cloud.client, DockerClient) else DockerClient()
        for case in switch(self.cloud.type):
            if case(Cloud.CLOUD_TYPES.local, Cloud.CLOUD_TYPES.dockerhub):
                self._ref = self.cloud.client.images.get(self.name)
                break
            if case(Cloud.CLOUD_TYPES.gcloud):
                self._ref = None
                break
            if case():
                raise CloudError(CloudError.INVALID_OPERATION, ctype=self.cloud.type.name)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def get_tags(self, image_filter=None):
        'Get a list of tags applied to the image'
        for case in switch(self.cloud.type):
            if case(Cloud.CLOUD_TYPES.local, Cloud.CLOUD_TYPES.dockerhub):
                return self._ref.tags
            if case(Cloud.CLOUD_TYPES.gcloud):
                args = ('--format=json',)
                if image_filter:
                    args += ('--filter='+image_filter,)
                return sorted([t for i in json_read(self.cloud.exec('container', 'images', 'list-tags', self.name, *args, show_stdout=False, flatten_output=True)) for t in i['tags']])
            if case():
                raise CloudError(CloudError.INVALID_OPERATION, ctype=self.cloud.type.name)
    tags = property(get_tags)
    containers = property(lambda s: s.cloud.get_containers({'ancestor': s.name}))

    def manage(self, action):
        'Manage an image in the cloud registry'
        for case in switch(self.cloud.type):
            if case(Cloud.CLOUD_TYPES.local, Cloud.CLOUD_TYPES.dockerhub, Cloud.CLOUD_TYPES.gcloud):
                docker_log = [literal_eval(l.strip()) for l in getattr(self._docker_client.images, action)(self.name).split('\n') if l]
                errors = [l['error'] for l in docker_log if 'error' in l]
                if errors:
                    raise CloudError(CloudError.IMAGE_ERROR, action=action, err=''.join(errors))
                return docker_log
            if case():
                raise CloudError(CloudError.INVALID_OPERATION, ctype=self.cloud.type.name)

    def push(self):
        'Push an image to the cloud registry'
        return self.manage('push')

    def pull(self):
        'Pull an image from the cloud registry'
        return self.manage('pull')

    def tag(self, new_tag):
        'Tag an image in the cloud registry'
        new_ref = None
        for case in switch(self.cloud.type):
            if case(Cloud.CLOUD_TYPES.local, Cloud.CLOUD_TYPES.dockerhub):
                self.pull()
                self._ref.tag(new_tag)
                new_ref = Image(self.cloud, new_tag)
                new_ref.push()
                break
            if case(Cloud.CLOUD_TYPES.gcloud):
                self.cloud.exec('container', 'images', 'add-tag', self.name, new_tag, ignore_stderr=True)
                new_ref = Image(self.cloud, new_tag)
                break
            if case():
                raise CloudError(CloudError.INVALID_OPERATION, ctype=self.cloud.type.name)
        return new_ref

    def run(self, detach=True, update=True, **args):
        'Run an image to create an active container'
        if update:
            self.pull()
        for case in switch(self.cloud.type):
            if case(Cloud.CLOUD_TYPES.local, Cloud.CLOUD_TYPES.dockerhub):
                return self.cloud.client.containers.run(self.name, detach=detach, **args)
            if case():
                raise CloudError(CloudError.INVALID_OPERATION, ctype=self.cloud.type.name)


class Container:
    """Class to create a universal abstract interface to a container."""

    def __init__(self, cloud, name):
        """
        Args:
            cloud: The API cloud reference.
            name: The container name.

        Attributes:
            cloud: The value of the cloud argument.
            name: The value of the name argument.
            _ref: A reference to the underlying API object.

        Raises:
            CloudError.INVALID_OPERATION: If the specified cloud type is not supported.
        """
        self.cloud = cloud
        self.name = name
        for case in switch(self.cloud.type):
            if case(Cloud.CLOUD_TYPES.local, Cloud.CLOUD_TYPES.dockerhub):
                self._ref = self.cloud.client.containers.get(self.name)
                break
            if case():
                raise CloudError(CloudError.INVALID_OPERATION, ctype=self.cloud.type.name)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def stop(self):
        'Stop a running container'
        for case in switch(self.cloud.type):
            if case(Cloud.CLOUD_TYPES.local, Cloud.CLOUD_TYPES.dockerhub):
                return self._ref.stop()
            if case():
                raise CloudError(CloudError.INVALID_OPERATION, ctype=self.cloud.type.name)


def validatetype(ctype):
    """Determines if the specified Cloud type is valid.

    Arguments:
        ctype: The Cloud type.

    Returns:
        Nothing.

    Raises
        CloudError.INVALID_TYPE: If the cloud type is not valid.
    """
    if ctype not in Cloud.CLOUD_TYPES:
        raise CloudError(CloudError.INVALID_TYPE, ctype=ctype)
