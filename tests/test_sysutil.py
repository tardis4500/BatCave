"""Unit tests for the sysutil module."""

# pylint: disable=missing-class-docstring,missing-function-docstring,invalid-name
# flake8: noqa

from enum import Enum
from multiprocessing import Process, Queue
from os import fdopen
from pathlib import Path
from tempfile import mkdtemp, mkstemp
from unittest import main, skip, TestCase

from batcave.sysutil import pushd, popd, CMDError, LockFile, LockError, LockMode

LockSignal = Enum('LockSignal', ('true', 'false'))


class TestExceptions(TestCase):
    def test_PlatformException(self):
        try:
            raise CMDError(CMDError.INVALID_OPERATION, platform='badplatform')
        except CMDError as err:
            self.assertEqual(CMDError.INVALID_OPERATION.code, err.code)


class TestLockFile(TestCase):
    def setUp(self):
        (fd, fn) = mkstemp()
        self._fh = fdopen(fd)
        self._fn = Path(fn)
        self._gotlock = Queue()
        self._lockagain = Process(target=secondary_lock_process, args=(self._fn, self._gotlock))

    def tearDown(self):
        self._gotlock.close()
        self._fh.close()
        if self._fn.exists():
            self._fn.unlink()

    def test_cleanup(self):
        with LockFile(self._fn, handle=self._fh, cleanup=True):
            pass
        self.assertFalse(self._fn.exists())

    def test_no_cleanup(self):
        with LockFile(self._fn, handle=self._fh, cleanup=False):
            pass
        self.assertTrue(self._fn.exists())

    @skip('Problems with secondary process')
    def test_lock(self):
        with LockFile(self._fn, handle=self._fh, cleanup=True):
            self._lockagain.start()
            gotlock = self._gotlock.get()
            self._lockagain.join()
            self.assertTrue(gotlock == LockSignal.false)

    @skip('Problems with secondary process')
    def test_unlock(self):
        with LockFile(self._fn, handle=self._fh, cleanup=True) as lockfile:
            lockfile.action(LockMode.unlock)
            self._lockagain.start()
            gotlock = self._gotlock.get()
            self._lockagain.join()
            lockfile.action(LockMode.lock)
            self.assertTrue(gotlock == LockSignal.true)


def secondary_lock_process(filename, queue):
    try:
        with LockFile(filename, cleanup=False) as lockagain:
            lockagain.action(LockMode.unlock)
            queue.put(LockSignal.true)
    except LockError:
        queue.put(LockSignal.false)


class TestDirStack(TestCase):
    def setUp(self):
        self._tempdir = Path(mkdtemp())

    def tearDown(self):
        self._tempdir.rmdir()

    def test_push_and_pop(self):
        start = Path.cwd()

        olddir = pushd(self._tempdir)
        newdir = Path.cwd()
        self.assertEqual(olddir, start)
        self.assertEqual(newdir, self._tempdir)

        olddir = popd()
        newdir = Path.cwd()
        self.assertEqual(olddir, start)
        self.assertEqual(newdir, start)


if __name__ == '__main__':
    main()
