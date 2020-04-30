"""This module provides utilities for managing cloud resources.

Attributes:
    CloudType (Enum): The cloud providers supported by the Cloud class.
    gcloud (SysCmdRunner.run): A simple interface to the gcloud command line tool.
"""

# Import standard modules
from ast import literal_eval
from enum import Enum
from json import loads as json_read
from pathlib import Path
from string import Template
from typing import Any, List, Optional, Sequence, Union

# Import third-party modules
from docker import DockerClient
from docker.models.containers import Container as DockerContainer

# Import internal modules
from .lang import switch, BatCaveError, BatCaveException, WIN32
from .sysutil import SysCmdRunner

CloudType = Enum('CloudType', ('local', 'gcloud', 'dockerhub'))  # pylint: disable=invalid-name

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
    INVALID_TYPE = BatCaveError(3, Template('Invalid Cloud type ($ctype). Must be one of: ' + str([t.name for t in CloudType])))


class Cloud:
    """Class to create a universal abstract interface for a cloud instance.

    Attributes:
        CLOUD_TYPES: The cloud providers currently supported by this class.
    """
    def __init__(self, ctype: CloudType, auth: Union[str, Sequence[str]] = tuple(), login: bool = True):
        """
        Args:
            ctype: The cloud provider for this instance. Must be a member of CloudType.
            auth (optional, default=None): For local or Docker Hub this is a (username, password) tuple.
                For Google Cloud it is a service account keyfile found at ~/.ssh/{value}.json.
            login (optional, default=True): Whether or not to login to the cloud provider at instance initialization.

        Attributes:
            auth: The value of the auth argument.
            type: The value of the ctype argument.
            _client: A reference to the underlying client API object.
        """
        self.type = ctype
        self.auth = auth
        self._client = False
        validatetype(self.type)
        if login:
            self.login()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info: Any):
        return False

    client = property(lambda s: s._client)

    def exec(self, *args, **kwargs) -> str:
        """Execute a command against the cloud API.

        Args:
            *args (optional, default=[]): A list of arguments to pass to the API.
            **kwargs (optional, default={}): A dictionary to pass to the API.

        Returns:
            The result of the API call.

        Raises:
            CloudError.INVALID_OPERATION: If the cloud type does not support an API call.
        """
        for case in switch(self.type):
            if case(CloudType.gcloud):
                return gcloud(None, *args, **kwargs)
        raise CloudError(CloudError.INVALID_OPERATION, ctype=self.type.name)

    def get_container(self, name: str) -> Container:  # noqa:F821, pylint: disable=used-before-assignment
        """Get a container from the cloud.

        Args:
            name: The container name to retrive.

        Returns:
            The container object.
        """
        return Container(self, name)

    def get_containers(self, filters: str = None) -> List['Container']:
        """Get a possibly filtered list of containers.

        Args:
            filter (optional, default=None): the container name to retrive.

        Returns:
            The container object.

        Raises:
            CloudError.INVALID_OPERATION: If the cloud type does not support login.
        """
        for case in switch(self.type):
            if case(CloudType.local, CloudType.dockerhub):
                return [Container(self, c.name) for c in self._client.containers.list(filters=filters)]  # type: ignore[attr-defined] # noqa:F821
        raise CloudError(CloudError.INVALID_OPERATION, ctype=self.type.name)

    containers = property(get_containers, doc='A read-only property which calls the get_containers() method with no filters.')

    def get_image(self, tag: str) -> Image:  # noqa:F821, pylint: disable=used-before-assignment
        """Get an image from the cloud container registry.

        Args:
            tag: The container image tag to retrive.

        Returns:
            The image object.
        """
        return Image(self, tag)

    def login(self) -> None:
        """Perform a login to the cloud provider.

        Returns:
            Nothing.

        Raises:
            CloudError.INVALID_OPERATION: If the value of self.ctype is not in CLOUD_TYPES.
        """
        for case in switch(self.type):
            if case(CloudType.local, CloudType.dockerhub):
                self._client = DockerClient()
                if self.type == CloudType.dockerhub:
                    self._client.login(*self.auth)  # type: ignore[attr-defined] # noqa:F821
                break
            if case(CloudType.gcloud):
                gcloud(None, 'auth', 'activate-service-account', '--key-file', Path.home() / '.ssh' / f'{self.auth[0]}.json', ignore_stderr=True)
                gcloud(None, 'auth', 'configure-docker', ignore_stderr=True)
                self._client = True
                break
            if case():
                raise CloudError(CloudError.INVALID_OPERATION, ctype=self.type.name)


class Image:
    """Class to create a universal abstract interface to a container image."""

    def __init__(self, cloud: Cloud, name: str):
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
            if case(CloudType.local, CloudType.dockerhub):
                self._ref = self.cloud.client.images.get(self.name)
                break
            if case(CloudType.gcloud):
                self._ref = None
                break
            if case():
                raise CloudError(CloudError.INVALID_OPERATION, ctype=self.cloud.type.name)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info: Any):
        return False

    containers = property(lambda s: s.cloud.get_containers({'ancestor': s.name}),
                          doc='A read-only property which returns all the containers for this image.')

    def get_tags(self, image_filter: str = None) -> List[str]:
        """Get a list of tags applied to the image.

        Args:
            image_filter (optional, default=None): A filter to apply to the image list.

        Returns:
            The sorted list of tags applied to the image.

        Raises:
            CloudError.INVALID_OPERATION: If the cloud type does not support image tags.
        """
        for case in switch(self.cloud.type):
            if case(CloudType.local, CloudType.dockerhub):
                return self._ref.tags
            if case(CloudType.gcloud):
                args = ['--format=json']
                if image_filter:
                    args += ['--filter=' + image_filter]
                return sorted([t for i in json_read(self.cloud.exec('container', 'images', 'list-tags', self.name, *args, show_stdout=False, flatten_output=True)) for t in i['tags']])
        raise CloudError(CloudError.INVALID_OPERATION, ctype=self.cloud.type.name)

    tags = property(get_tags, doc='A read-only property which calls the get_tags() method with no filters.')

    def manage(self, action: str) -> List[str]:
        """Manage an image in the cloud registry.

        Args:
            action: The management action to perform on the image.

        Returns:
            The log message of the management action.

        Raises:
            CloudError.INVALID_OPERATION: If the cloud type does not support image management.
        """
        for case in switch(self.cloud.type):
            if case(CloudType.local, CloudType.dockerhub, CloudType.gcloud):
                docker_log = [literal_eval(l.strip()) for l in getattr(self._docker_client.images, action)(self.name).split('\n') if l]
                errors = [l['error'] for l in docker_log if 'error' in l]
                if errors:
                    raise CloudError(CloudError.IMAGE_ERROR, action=action, err=''.join(errors))
                return docker_log
        raise CloudError(CloudError.INVALID_OPERATION, ctype=self.cloud.type.name)

    def pull(self) -> List[str]:
        """Pull the image from the registry.

        Returns:
            The result of the self.manage() call.
        """
        return self.manage('pull')

    def push(self) -> List[str]:
        """Push the image to the registry.

        Returns:
            The result of the self.manage() call.
        """
        return self.manage('push')

    def run(self, detach: bool = True, update: bool = True, **kwargs) -> DockerContainer:
        """Run an image to create an active container.

        Args:
            detach (optional, default=True): If True, do not wait for the container to complete.
            update (optional, default=True): If True, perform a pull of the image from the registry before running.
            **kwargs (optional, default={}): A dictionary of arguments to pass to the run command.

        Returns:
            A reference to the active container.

        Raises:
            CloudError.INVALID_OPERATION: If the cloud type does not support running an image.
        """
        if update:
            self.pull()
        for case in switch(self.cloud.type):
            if case(CloudType.local, CloudType.dockerhub):
                return self.cloud.client.containers.run(self.name, detach=detach, **kwargs)
        raise CloudError(CloudError.INVALID_OPERATION, ctype=self.cloud.type.name)

    def tag(self, new_tag: str) -> Optional['Image']:
        """Tag an image in the registry.

        Returns:
            The tagged image.

        Raises:
            CloudError.INVALID_OPERATION: If the cloud type does not support image tagging.
        """
        new_ref = None
        for case in switch(self.cloud.type):
            if case(CloudType.local, CloudType.dockerhub):
                self.pull()
                self._ref.tag(new_tag)
                new_ref = Image(self.cloud, new_tag)
                new_ref.push()
                break
            if case(CloudType.gcloud):
                self.cloud.exec('container', 'images', 'add-tag', self.name, new_tag, ignore_stderr=True)
                new_ref = Image(self.cloud, new_tag)
                break
            if case():
                raise CloudError(CloudError.INVALID_OPERATION, ctype=self.cloud.type.name)
        return new_ref


class Container:
    """Class to create a universal abstract interface to a container."""

    def __init__(self, cloud: Cloud, name: str):
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
            if case(CloudType.local, CloudType.dockerhub):
                self._ref = self.cloud.client.containers.get(self.name)
                break
            if case():
                raise CloudError(CloudError.INVALID_OPERATION, ctype=self.cloud.type.name)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info: Any):
        return False

    def stop(self) -> DockerContainer:
        """Stop a running container.

        Returns:
            A reference to the stopped container.

        Raises:
            CloudError.INVALID_OPERATION: If the cloud type does not support stopping an container.
        """
        for case in switch(self.cloud.type):
            if case(CloudType.local, CloudType.dockerhub):
                return self._ref.stop()
        raise CloudError(CloudError.INVALID_OPERATION, ctype=self.cloud.type.name)


def validatetype(ctype: CloudType) -> None:
    """Determine if the specified Cloud type is valid.

    Args:
        ctype: The Cloud type.

    Returns:
        Nothing.

    Raises
        CloudError.INVALID_TYPE: If the cloud type is not valid.
    """
    if ctype not in CloudType:
        raise CloudError(CloudError.INVALID_TYPE, ctype=ctype)
