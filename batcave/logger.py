"""This module provides a simplified interface to the standard logging module."""

# Import standard modules
from logging import Formatter, getLogger, FileHandler, StreamHandler, shutdown
from logging import INFO, WARN, WARNING, ERROR, CRITICAL, FATAL, DEBUG  # noqa: F401, pylint: disable=W0611
from multiprocessing import Queue
from pathlib import Path
from socket import SocketType
from typing import Optional, TextIO


class Logger:
    """Class to provide a simplified interface to the standard logging module."""

    def __init__(self, logname: str = '', stream: Optional[TextIO] = None, pipe: Optional[SocketType] = None, queue: Optional[Queue] = None,
                 msg_fmt: str = '%(asctime)s %(levelname)s %(message)s', date_fmt: str = '%Y/%m/%d %H:%M:%S', logref: str = 'batcave', logref_suffix: str = ''):
        """
        Args:
            logname (optional, default=''): The name of the logfile to be used.
            stream (optional, default=None): The stream to which message should be written.
            pipe (optional, default=None): The pipe to which message should be written.
            queue (optional, default=None): The queue to which message should be written.
            msg_fmt (optional, default='%(asctime)s %(levelname)s %(message)s'): The output message formatting string.
            date_fmt (optional, default='%Y/%m/%d %H:%M:%S'): The message date formatting string.
            logref (optional, default='batcave'): A string to uniquely identify this Logger instance.
            logref_suffix (optional, default=''): The suffix to append to the value of logref.

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
            file_handler = FileHandler(Path(logname))
            file_handler.setFormatter(formatter)
            self._logger.addHandler(file_handler)

        if stream:
            stream_handler = StreamHandler(stream)
            stream_handler.setFormatter(formatter)
            self._logger.addHandler(stream_handler)

        self._pipe = pipe
        self._queue = queue
        self.level = INFO

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.shutdown()
        return False

    @property
    def level(self) -> int:
        """A read-write property which returns and sets the current logging level."""
        return self._logger.getEffectiveLevel()

    @level.setter
    def level(self, level: int) -> None:
        self._logger.setLevel(level)

    def logdebug(self, msg: str) -> None:
        """Create a DEBUG level log message.

        Args:
            msg: The message to log.

        Returns:
            Nothing.
        """
        self._logger.debug(msg)
        if self._pipe:
            self._pipe.send(msg)
        if self._queue:
            self._queue.put(msg)

    def logerror(self, msg: str) -> None:
        """Create an ERROR level log message.

        Args:
            msg: The message to log.

        Returns:
            Nothing.
        """
        self._logger.error(msg)
        if self._pipe:
            self._pipe.send(msg)
        if self._queue:
            self._queue.put(msg)

    def loginfo(self, msg: str) -> None:
        """Create an INFO level log message.

        Args:
            msg: The message to log.

        Returns:
            Nothing.
        """
        self._logger.info(msg)
        if self._pipe:
            self._pipe.send(msg)
        if self._queue:
            self._queue.put(msg)

    def logwarn(self, msg: str) -> None:
        """Create a WARN level log message.

        Args:
            msg: The message to log.

        Returns:
            Nothing.
        """
        self._logger.warning(msg)
        if self._pipe:
            self._pipe.send(msg)
        if self._queue:
            self._queue.put(msg)

    def shutdown(self) -> None:
        """Shutdown the logging subsystem.

        Returns:
            Nothing.
        """
        shutdown()
