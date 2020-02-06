"""This module provides a simplified interface to the standard logging module."""

# Import standard modules
from logging import Formatter, getLogger, FileHandler, StreamHandler, shutdown
from logging import INFO, WARN, WARNING, ERROR, CRITICAL, FATAL, DEBUG  # noqa: F401, pylint: disable=W0611
from pathlib import Path


class Logger:
    """Class to provide a simplified interface to the standard logging module."""

    def __init__(self, logname=None, stream=None, pipe=None, queue=None, msg_fmt='%(asctime)s %(levelname)s %(message)s', date_fmt='%Y/%m/%d %H:%M:%S',
                 logref='batcave', logref_suffix=None):
        """
        Args:
            logname (optional, default=None): The name of the logfile to be used.
            stream (optional, default=None): The stream to which message should be written.
            pipe (optional, default=None): The pipe to which message should be written.
            queue (optional, default=None): The queue to which message should be written.
            msg_fmt (optional, default='%(asctime)s %(levelname)s %(message)s'): The output message formatting string.
            date_fmt (optional, default='%Y/%m/%d %H:%M:%S'): The message date formatting string.
            logref (optional, default='batcave'): A string to uniquely identify this Logger instance.
            logref_suffix (optional, default=None): The suffix to append to the value of logref.

        Attributes:
            level: The current logging level. Initialized to INFO.
            _logger: The standard module logging instance used to handle logging.
            _pipe: The value of the pipe argument.
            _queue: The value of the queue argument.
        """
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
        """A read-write property which returns and sets the current logging level."""
        return self._logger.getEffectiveLevel()

    @level.setter
    def level(self, level):
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
