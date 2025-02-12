"""Unit tests for the fileutil module."""

# pylint: disable=missing-class-docstring,missing-function-docstring,invalid-name
# flake8: noqa

from datetime import datetime as dt, timedelta
from os import utime
from pathlib import Path
from stat import S_IREAD
from tempfile import mkdtemp
from time import mktime, time
from unittest import main, TestCase

from batcave.fileutil import prune
from batcave.lang import WIN32
from batcave.sysutil import rmtree_hard


class TestPrune(TestCase):
    @property
    def _file_list(self):
        return sorted(list(self._tempdir.iterdir()))

    def _prune(self, age, **kwargs):
        prune(self._tempdir, age, **kwargs)

    def _print_list(self, full=False):
        print([f.name for f in (self._full_file_list if full else self._file_list)])

    def setUp(self):
        self._tempdir = Path(mkdtemp()).resolve()
        self._time = time()
        file_time = dt.now()
        for c in 'ab':
            for i in (1, 2):
                Path(temp_file1 := self._tempdir / f'{c}{i}.Ext{i}').touch()
                Path(temp_file2 := self._tempdir / f'{c}{i}.Txt{i}').touch()
                if i == 1:
                    file_time += timedelta(days=2)
                utime(temp_file1, (file_epoch_time := mktime(file_time.timetuple()), file_epoch_time))
                utime(temp_file2, (file_epoch_time, file_epoch_time))
        self._full_file_list = self._file_list

    def tearDown(self):
        rmtree_hard(self._tempdir)

    def test_prune_1_no_removal(self):
        self._prune(10)
        self.assertEqual(self._full_file_list, self._file_list)

    def test_prune_2_simple(self):
        self._prune(age=10)
        self.assertEqual(self._full_file_list, self._file_list)
        self._prune(age=2)
        self.assertEqual(self._full_file_list[:-4], self._file_list)

    def test_prune_3_by_ext(self):
        self._prune(age=2, exts=['.txt'])
        self.assertEqual(self._full_file_list, self._file_list)
        self._prune(age=2, exts=['.Txt2'])
        self.assertEqual(self._full_file_list[:-1], self._file_list)

    def test_prune_4_by_ext_ignore_case(self):
        self._prune(age=2, exts=['.txt2'], ignore_case=True)
        self.assertEqual(self._full_file_list[:-1], self._file_list)

    def test_prune_5_force(self):
        for item in self._full_file_list:
            item.chmod(S_IREAD)
        self._tempdir.chmod(S_IREAD)
        self.assertRaises(PermissionError, lambda: self._prune(age=2))
        self.assertEqual(self._full_file_list, self._file_list)
        self._prune(age=2, force=True)
        self.assertEqual(self._full_file_list[:-4], self._file_list)

if __name__ == '__main__':
    main()

# cSpell:ignore batcave fileutil
