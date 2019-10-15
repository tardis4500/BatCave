'Interface for building automation'

# Import standard modules
import sys
from pathlib import Path

# Import internal modules
from .sysutil import popd, SysCmdRunner


class ActionCommandRunner(SysCmdRunner):
    'Class to wrap SysCmdRunner for simple usage with auto-logging.'
    def __init__(self, command, guard='', default_args=tuple(), **keys):
        super().__init__(command, *default_args, show_cmd=True, show_stdout=True, **keys)
        self.guard = guard

    def run(self, message, *args, **keys):
        if self.guard:
            self.writer(self.guard)
        return super().run(message, *args, **keys)


class Action:
    ''' The common base class for all actions
        This is a virtual class and the inheriting class must at least include a _execute() method
        The action is invoked by calling the execute() method this will run the following methods:
            pre()
            _execute()
            post()
        These are run in a try to catch any exceptions after which
            always_post()
        is run '''

    MESSAGE_GUARD = f"{'*'*70}"

    def __init__(self, **args):  # pylint: disable=W0613
        self.project_root = Path.cwd().parent

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def pre(self):
        'Executed before _execute()'

    def post(self):
        'Executed after _execute()'

    def always_post(self):
        'Executed after _execute() like finally in try/catch/finally'
        popd()

    def execute(self):
        'Runs the _execute() method from the child class'
        try:
            self.pre()
            self._execute()  # pylint: disable=E1101
            self.post()
        finally:
            self.always_post()

    def log_message(self, message, guard=False, leader='INFO'):
        'Logs a message to stdout and flushes the stream'
        guard = self.MESSAGE_GUARD if (guard is True) else ''
        leader = f'{leader} ' if leader else ''
        if guard:
            print(f'{leader}{guard}')
        print(f'{leader}{message}')
        sys.stdout.flush()
