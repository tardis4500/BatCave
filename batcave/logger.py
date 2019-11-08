''' The logger is initialized by instantiating the Logger class with the following arguments:
        logname: the name of the logfile to be used (optional, default=None)
        stream: also write the message to a stream (optional, default=None)
        pipe: also write the message to a pipe (optional, default=None)
        queue: also place the message in a queue (optional, default=None) '''

# Import standard modules
from logging import Formatter, getLogger, FileHandler, StreamHandler, shutdown
from logging import INFO, WARN, WARNING, ERROR, CRITICAL, FATAL, DEBUG  # noqa: F401, pylint: disable=W0611
from pathlib import Path


class Logger:
    'This provides all the logging functionality'
    def __init__(self, logname=None, stream=None, pipe=None, queue=None, msg_fmt='%(asctime)s %(levelname)s %(message)s', date_fmt='%Y/%m/%d %H:%M:%S',
                 logref='batcave', logref_suffix=None):
        formatter = Formatter(msg_fmt, date_fmt)
        logref += f'.{logref_suffix}' if logref_suffix else ''

        self._logger = getLogger(logref)
        if logname:
            handler = FileHandler(Path(logname))
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)

        if stream:
            handler = StreamHandler(stream)
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)

        self._pipe = pipe
        self._queue = queue
        self.level = INFO

    @property
    def level(self):
        'Return the current logging level'
        return self._logger.getEffectiveLevel()

    @level.setter
    def level(self, level):
        'Changes the logging level'
        self._logger.setLevel(level)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.shutdown()
        return False

    def logdebug(self, msg):
        'Create a DEBUG level log message'
        self._logger.debug(msg)
        if self._pipe:
            self._pipe.send(msg)
        if self._queue:
            self._queue.put(msg)

    def loginfo(self, msg):
        'Create an INFO level log message'
        self._logger.info(msg)
        if self._pipe:
            self._pipe.send(msg)
        if self._queue:
            self._queue.put(msg)

    def logwarn(self, msg):
        'Create a WARNING level log message'
        self._logger.warning(msg)
        if self._pipe:
            self._pipe.send(msg)
        if self._queue:
            self._queue.put(msg)

    def logerror(self, msg):
        'Create an ERROR level log message'
        self._logger.error(msg)
        if self._pipe:
            self._pipe.send(msg)
        if self._queue:
            self._queue.put(msg)

    def shutdown(self):
        'Close the log'
        shutdown()
