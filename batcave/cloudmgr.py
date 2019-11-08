'This provides a Pythonic cloud management interface'

# Import standard modules
from ast import literal_eval
from enum import Enum
from json import loads as json_read
from pathlib import Path
from string import Template

# Import third-party modules
from docker import DockerClient

# Import internal modules
from .lang import switch, HALError, HALException, WIN32
from .sysutil import SysCmdRunner

_CLOUD_TYPES = Enum('cloud_types', ('local', 'gcloud', 'dockerhub'))

gcloud = SysCmdRunner('gcloud', '-q', use_shell=WIN32).run  # pylint: disable=invalid-name


class CloudError(HALException):
    'Class to handle cloud exceptions'
    INVALIDTYPE = HALError(1, Template('Invalid Cloud type ($ctype). Must be one of: ' + str([t.name for t in _CLOUD_TYPES])))
    INVALIDTYPE_FOR_OPERATION = HALError(2, Template('Invalid Cloud type ($ctype) for this operation'))
    IMAGE_ERROR = HALError(3, Template('Error ${action}ing image: $err'))


class Cloud:
    'Class to manage a cloud instance'
    CLOUD_TYPES = _CLOUD_TYPES

    def __init__(self, ctype, auth=None, login=True):
        self.type = ctype
        self.auth = auth
        self.client = None
        validatetype(self.type)
        if login:
            self.login()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def login(self):
        'Login to the cloud provider'
        for case in switch(self.type):
            if case(self.CLOUD_TYPES.local, self.CLOUD_TYPES.dockerhub):
                self.client = DockerClient()
                if self.type == self.CLOUD_TYPES.dockerhub:
                    self.client.login(*self.auth)
                break
            if case(self.CLOUD_TYPES.gcloud):
                gcloud(None, 'auth', 'activate-service-account', '--key-file', Path.home() / '.ssh' / (self.auth[0]+'.json'), ignore_stderr=True)
                gcloud(None, 'auth', 'configure-docker', ignore_stderr=True)
                self.client = True
                break
            if case():
                raise CloudError(CloudError.INVALIDTYPE_FOR_OPERATION, ctype=self.type.name)

    def get_image(self, tag):
        'Get an image from the cloud container registry'
        return Image(self, tag)

    def get_container(self, name):
        'Get a container from the cloud'
        return Container(self, name)

    def get_containers(self, filters=None):
        'Get a possibly filtered list of containers'
        for case in switch(self.type):
            if case(self.CLOUD_TYPES.local, self.CLOUD_TYPES.dockerhub):
                return [Container(self, c.name) for c in self.client.containers.list(filters=filters)]
            if case():
                raise CloudError(CloudError.INVALIDTYPE_FOR_OPERATION, ctype=self.type.name)
    containers = property(get_containers)

    def exec(self, *args, **opts):
        'Execute a command against the cloud API'
        for case in switch(self.type):
            if case(self.CLOUD_TYPES.gcloud):
                return gcloud(None, *args, **opts)
            if case():
                raise CloudError(CloudError.INVALIDTYPE_FOR_OPERATION, ctype=self.type.name)


class Image:
    'Class to interface with a container image object'
    def __init__(self, cloud, name):
        self.cloud = cloud
        self.name = name
        self.docker_client = self.cloud.client if isinstance(self.cloud.client, DockerClient) else DockerClient()
        for case in switch(self.cloud.type):
            if case(Cloud.CLOUD_TYPES.local, Cloud.CLOUD_TYPES.dockerhub):
                self.ref = self.cloud.client.images.get(self.name)
                break
            if case(Cloud.CLOUD_TYPES.gcloud):
                self.ref = None
                break
            if case():
                raise CloudError(CloudError.INVALIDTYPE_FOR_OPERATION, ctype=self.cloud.type.name)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def get_tags(self, image_filter=None):
        'Get a list of tags applied to the image'
        for case in switch(self.cloud.type):
            if case(Cloud.CLOUD_TYPES.local, Cloud.CLOUD_TYPES.dockerhub):
                return self.ref.tags
            if case(Cloud.CLOUD_TYPES.gcloud):
                args = ('--format=json',)
                if image_filter:
                    args += ('--filter='+image_filter,)
                return sorted([t for i in json_read(self.cloud.exec('container', 'images', 'list-tags', self.name, *args, show_stdout=False, flatten_output=True)) for t in i['tags']])
            if case():
                raise CloudError(CloudError.INVALIDTYPE_FOR_OPERATION, ctype=self.cloud.type.name)
    tags = property(get_tags)
    containers = property(lambda s: s.cloud.get_containers({'ancestor': s.name}))

    def manage(self, action):
        'Manage an image in the cloud registry'
        for case in switch(self.cloud.type):
            if case(Cloud.CLOUD_TYPES.local, Cloud.CLOUD_TYPES.dockerhub, Cloud.CLOUD_TYPES.gcloud):
                docker_log = [literal_eval(l.strip()) for l in getattr(self.docker_client.images, action)(self.name).split('\n') if l]
                errors = [l['error'] for l in docker_log if 'error' in l]
                if errors:
                    raise CloudError(CloudError.IMAGE_ERROR, action=action, err=''.join(errors))
                return docker_log
            if case():
                raise CloudError(CloudError.INVALIDTYPE_FOR_OPERATION, ctype=self.cloud.type.name)

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
                self.ref.tag(new_tag)
                new_ref = Image(self.cloud, new_tag)
                new_ref.push()
                break
            if case(Cloud.CLOUD_TYPES.gcloud):
                self.cloud.exec('container', 'images', 'add-tag', self.name, new_tag, ignore_stderr=True)
                new_ref = Image(self.cloud, new_tag)
                break
            if case():
                raise CloudError(CloudError.INVALIDTYPE_FOR_OPERATION, ctype=self.cloud.type.name)
        return new_ref

    def run(self, detach=True, update=True, **args):
        'Run an image to create an active container'
        if update:
            self.pull()
        for case in switch(self.cloud.type):
            if case(Cloud.CLOUD_TYPES.local, Cloud.CLOUD_TYPES.dockerhub):
                return self.cloud.client.containers.run(self.name, detach=detach, **args)
            if case():
                raise CloudError(CloudError.INVALIDTYPE_FOR_OPERATION, ctype=self.cloud.type.name)


class Container:
    'Interface to handle a container'
    def __init__(self, cloud, name):
        self.cloud = cloud
        self.name = name
        for case in switch(self.cloud.type):
            if case(Cloud.CLOUD_TYPES.local, Cloud.CLOUD_TYPES.dockerhub):
                self.ref = self.cloud.client.containers.get(self.name)
                break
            if case():
                raise CloudError(CloudError.INVALIDTYPE_FOR_OPERATION, ctype=self.cloud.type.name)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def stop(self):
        'Stop a running container'
        for case in switch(self.cloud.type):
            if case(Cloud.CLOUD_TYPES.local, Cloud.CLOUD_TYPES.dockerhub):
                return self.ref.stop()
            if case():
                raise CloudError(CloudError.INVALIDTYPE_FOR_OPERATION, ctype=self.cloud.type.name)


def validatetype(ctype):
    'determines if the specified Cloud type is valid'
    if ctype not in Cloud.CLOUD_TYPES:
        raise CloudError(CloudError.INVALIDTYPE, ctype=ctype)
