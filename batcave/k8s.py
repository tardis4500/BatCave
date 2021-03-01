"""This module provides a simplified interface to the kubernetes module.

Attributes:
    kubectl (SysCmdRunner.run): A simple interface to the kubectl command line tool.
"""

# Import standard modules
from datetime import datetime as dt, timedelta
from pathlib import Path
from string import Template
from time import sleep
from typing import cast, Any, Callable, List, Optional, Type, TypeVar

# Import third-party modules
from kubernetes import config as k8s_config
from kubernetes.client import BatchV1Api, CoreV1Api, V1Namespace, V1ObjectMeta
from kubernetes.stream import stream as k8s_process
from yaml import safe_load as yaml_load

# Import internal modules
from .lang import BatCaveError, BatCaveException, CommandResult, PathName
from .sysutil import SysCmdRunner

K8sObject = TypeVar('K8sObject', 'Pod', 'Job', 'Namespace')

kubectl = SysCmdRunner('kubectl').run  # pylint: disable=invalid-name


class ClusterError(BatCaveException):
    """Kubernetes Cluster Exceptions.

    Attributes:
        BAD_ARGS: Bad arguments were specified.
        TIMEOUT: There was a timeout on the cluster.
    """
    BAD_ARGS = BatCaveError(1, Template('$error'))
    TIMEOUT = BatCaveError(2, Template('Timeout waiting for $seconds seconds for $what $action'))


class PodError(BatCaveException):
    """Kubernetes Pod Exceptions.

    Attributes:
        BAD_COPY_FILENAME: The file specified for the copy was invalid.
        COPY_ERROR: There was an error transfering a file to or from a pod.
        EXEC_ERROR: There was an error executing a pod command.
        FILE_NOT_FOUND: The file specified for the copy was not found in the pod.
        INVALID_COPY_MODE: The copy mode was invalid.
    """
    BAD_COPY_FILENAME = BatCaveError(1, Template('File not copied $mode, check filenames'))
    COPY_ERROR = BatCaveError(2, Template('Error copying pod file: $errlines'))
    EXEC_ERROR = BatCaveError(3, Template('Error executing pod command: $errlines'))
    FILE_NOT_FOUND = BatCaveError(4, Template('File not found in pod: $filename'))
    INVALID_COPY_MODE = BatCaveError(5, Template('Invalid pod file copy mode ($mode). Must be one of: (in, out)'))


class Cluster:
    """Class to create a universal abstract interface for a Kubernetes cluster."""

    def __init__(self, cluster_config: Optional[PathName] = None, context: Optional[str] = None):
        """
        Args:
            cluster_config (optional, default=None): The cluster configuration file to use.
            context (optional, default=None): The cluster configuration file context to use.

        Attributes:
            _batch_api: A reference to the BatchV1Api object.
            _config: The value of the cluster_config argument.
            _context: The value of the context argument.
            _core_api: A reference to the CoreV1Api object.
        """
        self._config = str(cluster_config) if isinstance(cluster_config, Path) else cluster_config
        self._context = context
        k8s_config.load_kube_config(self.config, self._context)
        self._core_api = CoreV1Api()
        self._batch_api = BatchV1Api()

    def __getattr__(self, attr: str) -> Any:
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
        try:
            return getattr(self, f'get_{attr}')()
        except KeyError as err:
            raise AttributeError(f'No attribute for cluster: {attr}') from err

    config = property(lambda s: s._config, doc='A read-only property which returns configuration file for the cluster.')
    pod_exec = property(lambda s: s._core_api.connect_get_namespaced_pod_exec, doc='A read-only property which returns the pd exec function for the cluster.')

    def create_namespace(self, name: str, /, *, exists_ok: bool = False) -> 'Namespace':
        """Create a namespace.

        Args:
            name: The name of the namespace to create.
            exists_ok (optional, default=False): If True and the item already exists, delete before creating.

        Returns:
            The created namespace.
        """
        if not (self.has_item(Namespace, name) and exists_ok):
            namespace = V1Namespace()
            namespace.metadata = V1ObjectMeta()
            namespace.metadata.name = name
            self._core_api.create_namespace(namespace)
        return self.get_item(Namespace, name)

    def create_item(self, item_class: Type[K8sObject], item_spec: PathName, /, *, namespace: str = 'default', exists_ok: bool = False) -> K8sObject:
        """Create a new item using the specified spec.

        Args:
            item_class: The class of the item to create.
            item_spec: A file containing the Kubernetes specification.
            namespace (optional, default='default'): The Kubernetes namespace in which to create the item.
            exists_ok (optional, default=False): If True and the item already exists, delete before creating.

        Returns:
            The created item.
        """
        with open(item_spec) as yaml_file:
            item_spec_content = yaml_load(yaml_file)
            item_name = item_spec_content['metadata']['name']
            if self.has_item(item_class, item_name, namespace=namespace) and exists_ok:
                self.find_method(item_class, 'delete')(item_name, namespace)
            return item_class(self, self.find_method(item_class, 'create')(namespace, item_spec_content))

    def create_job(self, job_spec: PathName, /, *, namespace: str = 'default', exists_ok: bool = False,
                   wait_for: bool = False, check_every: int = 2, timeout: bool = False) -> 'Job':
        """Create a job and wait for the specified condition.

        Args:
            job_spec: A file containing the Kubernetes job specification.
            namespace (optional, default='default'): The Kubernetes namespace in which to create the job.
            exists_ok (optional, default=False): If True and the item already exists, delete before creating.
            wait_for (optional, default=False): If True, wait until the job completes before returning.
            check_every (optional, default=2): The number of seconds to wait between every check to see if the job has completed.
            timeout (optional, default=False): If not False, this is the maximum number of seconds to wait for the job to complete.

        Raises:
            ClusterError.TIMEOUT: If timeout is True and the maximum number of seconds is exceeded.

        Returns:
            The created job.
        """
        if wait_for not in (False, 'start', 'finish'):
            raise ClusterError(ClusterError.BAD_ARGS, error=f"wait_for must be one of (start, finish, False) not '{wait_for}'")
        job = self.create_item(Job, job_spec, namespace=namespace, exists_ok=exists_ok)
        if not wait_for:
            return job

        start_time = dt.now()
        while not (job.status.active or job.status.succeeded or job.status.failed):
            if timeout and (dt.now() - start_time) > timedelta(seconds=timeout):
                raise ClusterError(ClusterError.TIMEOUT, seconds=timeout, what='Job', action='start')
            sleep(check_every)
            job = self.get_job(job.name, namespace)
        if wait_for == 'start':
            return job

        start_time = dt.now()
        while job.status.active:
            if timeout and (dt.now() - start_time) > timedelta(seconds=timeout):
                raise ClusterError(ClusterError.TIMEOUT, seconds=timeout, what='Job', action='finish')
            sleep(check_every)
            job = self.get_job(job.name, namespace)
        return job

    def delete_item(self, item_class: Type[K8sObject], name: str, /, *, namespace: str = 'default') -> None:
        """Delete the named item.

        Args:
            item_class: The class of the item to create.
            name: The name of the item to delete.
            namespace (optional, default='default'): The Kubernetes namespace from which to return the item.

        Returns:
            Nothing.
        """
        item_class(self, self.find_method(item_class, 'delete')(name, namespace))

    def find_method(self, item_class: Type[K8sObject], method: str, /, suffix: str = '') -> Callable:
        """Search all the APIs for the specified method.

        Args:
            item_class: The item class to search.
            method: The method for which to search.
            suffix(optional, default=None): If not None, append to the method name with an underscore when searching.

        Returns:
            A reference to method.

        Raises:
            AttributeError: If the method is not found.
        """
        method_name = method
        if item_class.NAMESPACED:
            method_name += '_namespaced'
        method_name += f'_{item_class.__name__.lower()}'
        if suffix:
            method_name += f'_{suffix}'
        for api in (self._core_api, self._batch_api):
            if hasattr(api, method_name):
                return getattr(api, method_name)
        raise AttributeError(f'No method found: {method_name}')

    def get_item(self, item_class: Type[K8sObject], name: str, /, *, namespace: str = 'default') -> K8sObject:
        """Get the requested item.

        Args:
            item_class: The item class.
            item_name: The name of the item to return.
            namespace (optional, default='default'): The Kubernetes namespace from which to return the item.

        Returns:
            The requested item.
        """
        args = [name]
        if item_class.NAMESPACED:
            args.append(namespace)
        return item_class(self, self.find_method(item_class, 'read')(*args))

    def get_items(self, item_class: Type[K8sObject], /, *, namespace: str = 'default', **keys) -> List[K8sObject]:
        """Get all the item of the requested type.

        Args:
            item_class: The item class.
            namespace (optional, default='default'): The Kubernetes namespace from which to return the items.
            keys (optional): A list of keys by which to filter the items.

        Returns:
            The requested item list.
        """
        if item_class.NAMESPACED:
            keys['namespace'] = namespace
        return [item_class(self, i) for i in self.find_method(item_class, 'list')(**keys).items]

    def has_item(self, item_class: Type[K8sObject], item_name: str, /, *, namespace: str = 'default') -> bool:
        """Determine if the named items of the specified class exists.

        Args:
            item_class: The item class for which to search.
            item_name: The name of the item to search for.
            namespace (optional, default='default'): The Kubernetes namespace to search.

        Returns:
            Returns True if the named item exists, False otherwise.
        """
        return bool([i for i in self.get_items(item_class, namespace=namespace) if i.name == item_name])

    def kubectl(self, *args, **kwargs) -> CommandResult:
        """Run a kubectl command.

        Args:
            *args: The arguments to pass to kubectl.
            *kwargs: The named arguments to pass to kubectl.

        Returns:
            The result of the kubectl command.
        """
        config_args = dict()
        if self.config:
            config_args['kubeconfig'] = self.config
        if self._context:
            config_args['context'] = self._context
        return kubectl(*args, **config_args, **kwargs)


class ClusterObject:  # pylint: disable=too-few-public-methods
    """Class to create a universal abstract interface for a Kubernetes cluster object.

    Attributes:
        NAMESPACED: If True, the object is a cluster namespaced object.
    """
    NAMESPACED = True

    def __init__(self, cluster: Cluster, object_ref: Any, /):
        """
        Args:
            cluster: The cluster containing this object.
            object_ref: A reference to the underlying API object.

        Attributes:
            _cluster_obj: The value of the cluster argument.
            _object_ref: The value of the object_ref argument.
        """
        self._cluster_obj = cluster
        self._object_ref = object_ref

    def __getattr__(self, attr: str) -> 'ClusterObject':
        if hasattr(self._object_ref, attr):
            return getattr(self._object_ref, attr)
        return getattr(self._object_ref.metadata, attr)


class Namespace(ClusterObject):  # pylint: disable=too-few-public-methods
    """Class to create a universal abstract interface for a Kubernetes namespace."""
    NAMESPACED = False


class Pod(ClusterObject):
    """Class to create a universal abstract interface for a Kubernetes pod."""

    logs = property(lambda s: s._cluster_obj.kubectl('logs', s.name, namespace=s.namespace), doc='A read-only property which returns the pod logs.')

    def cp_file(self, mode: str, source: PathName, target: PathName, /) -> None:
        """Copy a file into or out of the pod.

        Args:
            mode: The direction of the copy ('in' or 'out').
            source: The source file for the copy.
            target: The target file for the copy.

        Returns:
            Nothing.

        Raises:
            PodError.BAD_COPY_FILENAME: If the source or target name was not found.
            PodError.COPY_ERROR: If there was an error when copying the file.
            PodError.INVALID_COPY_MODE: If the specified mode is not known.
        """
        source_path: PathName
        target_path: PathName
        if mode == 'in':
            source_path = Path(source)
            target_path = f'{self.namespace}/{self.name}:{target}'
        elif mode == 'out':
            source_path = f'{self.namespace}/{self.name}:{source}'
            target_path = Path(target)
        else:
            raise PodError(PodError.INVALID_COPY_MODE, mode=mode)

        output = self._cluster_obj.kubectl('cp', str(source_path), str(target_path))
        if not (self.has_file(str(target)) if (mode == 'in') else cast(Path, target_path).exists()):  # pylint: disable=superfluous-parens
            if output:
                raise PodError(PodError.COPY_ERROR, errlines=output)
            raise PodError(PodError.BAD_COPY_FILENAME, mode=mode)

    def exec(self, *command, **k8s_api_kwargs) -> str:
        """Execute a command in the pod.

        Args:
            *command: The command and arguments to execute.
            **k8s_api_kwargs: The Kubernetes API parameters to pass to the stream call.

        Returns:
            The output from the command.

        Raises:
            PodError.EXEC_ERROR: If the word 'error' occurs in the output.
        """
        output = k8s_process(self._cluster_obj.pod_exec, self.name, self.namespace,
                             command=list(command), stderr=True, stdin=False, stdout=True, tty=False, _preload_content=True, **k8s_api_kwargs)
        if 'error' in output:
            raise PodError(PodError.EXEC_ERROR, errlines=output)
        return output.splitlines()[0:-1]

    def get_file(self, source: str, target: Optional[PathName] = None, /) -> None:
        """Copy a file out of the pod.

        Args:
            source: The source for the copy.
            target (optional, default=None): If not None, the target for the copy.

        Returns:
            Nothing.
        """
        target_path = Path(target) if target else Path(Path(source).name)
        self.cp_file('out', source, target_path)

    def has_file(self, filename: str, /) -> bool:
        """Determine if the pod has the specified file.

        Args:
            filename: The name of the file for which to search.

        Returns:
            True if the specified file exists, False otherwise.
        """
        return filename == self.exec('ls', filename)[0]

    def put_file(self, source: PathName, target: str, /) -> None:
        """Copy a file into the pod.

        Args:
            source: The source for the copy.
            target: The target for the copy.

        Returns:
            Nothing.
        """
        self.cp_file('in', source, target)

    def remove_file(self, filename: str, /, *, not_exists_ok: bool = False) -> None:
        """Remove the specified file from the pod.

        Args:
            filename: The name of the file to remove.
            not_exists_ok (optional, default=False): If True, raise an exception if the file does not exist.

        Returns:
            Nothing.

        Raises:
            PodError.FILE_NOT_FOUND: If the file is not found.
        """
        if not (not_exists_ok or self.has_file(filename)):
            raise PodError(PodError.FILE_NOT_FOUND, filename=filename)
        self.exec('rm', filename)


class Job(ClusterObject):  # pylint: disable=too-few-public-methods
    """Class to create a universal abstract interface for a Kubernetes job."""

# cSpell:ignore kube kubeconfig
