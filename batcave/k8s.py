'This provides a more Pythonic interface to the kubernetes module'
# cSpell:ignore kube, kubeconfig

# # Import standard modules
from pathlib import Path
from string import Template

# # Import third-party modules
from kubernetes import config as k8s_config
from kubernetes.client import BatchV1Api, CoreV1Api
from kubernetes.stream import stream as k8s_process
from yaml import safe_load as yaml_load

# Import internal modules
from .lang import HALError, HALException
from .sysutil import SysCmdRunner

kubectl = SysCmdRunner('kubectl').run  # pylint: disable=invalid-name


class PodError(HALException):
    'Class to handle cloud exceptions'
    BAD_COPY_FILENAME = HALError(1, Template('File not copied $mode, check filenames'))
    COPY_ERROR = HALError(2, Template('Error copying pod file: $errlines'))
    EXEC_ERROR = HALError(3, Template('Error executing pod command: $errlines'))
    FILE_NOT_FOUND = HALError(4, Template('File not found in pod: $filename'))
    INVALID_COPY_MODE = HALError(5, Template('Invalid pod file copy mode ($mode). Must be one of: (in, out)'))


class Cluster:
    'Class to represent a kubernetes cluster'
    def __init__(self, cluster_config=None):
        self.config = str(cluster_config) if isinstance(cluster_config, Path) else cluster_config
        k8s_config.load_kube_config(self.config)
        self._core_api = CoreV1Api()
        self._batch_api = BatchV1Api()

    pod_exec = property(lambda s: s._core_api.connect_get_namespaced_pod_exec)

    def __getattr__(self, attr):
        if '_' in attr:
            (verb, item_class_name) = attr.split('_')
            if item_class_name.endswith('s'):
                item_class_name = item_class_name[0:-1]
                plural = 's'
            else:
                plural = ''
            item_class = globals()[item_class_name.capitalize()]
            method = getattr(self, f'{verb}_item{plural}')
            return lambda *a, **k: method(item_class, *a, **k)
        return super.__getattr__(attr)

    def find_method(self, item_class, method, suffix=None):
        'Search all the APIs for the specified method'
        method_name = f'{method}_namespaced_{item_class.__name__.lower()}'
        if suffix:
            method_name += f'_{suffix}'
        for api in (self._core_api, self._batch_api):
            if hasattr(api, method_name):
                return getattr(api, method_name)
        raise AttributeError(f'No method found: {method_name}')

    def has_item(self, item_class, item_name, namespace='default'):
        'Return a boolean value for the existence of the specified item'
        return bool([i for i in self.get_items(item_class, namespace) if i.name == item_name])

    def get_item(self, item_class, name, namespace='default'):
        'Return a list of the specified items'
        return item_class(self, self.find_method(item_class, 'read')(name, namespace))

    def get_items(self, item_class, namespace='default', **keys):
        'Return a list of the specified items'
        return [item_class(self, i) for i in self.find_method(item_class, 'list')(namespace, **keys).items]

    def create_item(self, item_class, item_spec, namespace='default', exists_ok=False):
        'Create the specified item'
        with open(item_spec) as yaml_file:
            item_spec = yaml_load(yaml_file)
            item_name = item_spec['metadata']['name']
            if self.has_item(item_class, item_name, namespace) and exists_ok:
                self.find_method(item_class, 'delete')(item_name, namespace)
            return item_class(self, self.find_method(item_class, 'create')(namespace, item_spec))

    def delete_item(self, item_class, name, namespace='default'):
        'Return a list of the specified items'
        item_class(self, self.find_method(item_class, 'delete')(name, namespace))

    def kubectl(self, *args):
        'Provide kubectl for things that are not implemented directly in the API'
        return kubectl(None, f'--kubeconfig={self.config}', *args).decode()


class ClusterObject:
    'Class to represent a generic kubernetes cluster object'
    def __init__(self, cluster, object_ref):
        self._cluster_obj = cluster
        self._object_ref = object_ref

    def __getattr__(self, attr):
        if hasattr(self._object_ref, attr):
            return getattr(self._object_ref, attr)
        return getattr(self._object_ref.metadata, attr)


class Pod(ClusterObject):
    'Class to represent a kubernetes pod'
    logs = property(lambda s: s._cluster_obj.kubectl('logs', f'--namespace={s.namespace}', s.name))

    def exec(self, *command):
        'Execute a command on the specified pod'
        output = k8s_process(self._cluster_obj.pod_exec, self.name, self.namespace,
                             command=list(command), stderr=True, stdin=False, stdout=True, tty=False, _preload_content=True)
        if 'error' in output:
            raise PodError(PodError.EXEC_ERROR, errlines=output)
        return output.split('\n')[0:-1]

    def has_file(self, filename):
        'Find out if the pod has the specified file'
        return filename == self.exec('ls', filename)[0]

    def remove_file(self, filename, not_exists_ok=False):
        'Remove the specified file from the pod'
        if not (not_exists_ok or self.has_file(filename)):
            raise PodError(PodError.FILE_NOT_FOUND, filename=filename)
        self.exec('rm', filename)

    def cp_file(self, mode, source, target):
        'Copy a file in to or out of a pod'
        if mode == 'in':
            source_path = Path(source)
            target_path = f'{self.namespace}/{self.name}:{target}'
        elif mode == 'out':
            source_path = f'{self.namespace}/{self.name}:{source}'
            target_path = Path(target)
        else:
            raise PodError(PodError.INVALID_COPY_MODE, mode=mode)

        output = self._cluster_obj.kubectl('cp', str(source_path), str(target_path))
        if not (self.has_file(target) if (mode == 'in') else target_path.exists()):  # pylint: disable=superfluous-parens
            if output:
                raise PodError(PodError.COPY_ERROR, errlines=output)
            raise PodError(PodError.BAD_COPY_FILENAME, mode=mode)

    def get_file(self, source, target=None):
        'Copy a file from a pod'
        target_path = Path(target) if target else Path(Path(source).name)
        self.cp_file('out', source, target_path)

    def put_file(self, source, target):
        'Copy a file from a pod'
        self.cp_file('in', source, target)


class Job(ClusterObject):
    'Class to represent a kubernetes job'
