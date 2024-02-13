"""Unit tests for the fileutil module."""

# pylint: disable=missing-class-docstring,missing-function-docstring,invalid-name
# flake8: noqa

from datetime import datetime as dt, timedelta
from os import utime
from pathlib import Path
from tempfile import mkdtemp
from time import mktime, time
from unittest import main, TestCase

from batcave.fileutil import prune_in_directory, rmtree_hard


class TestDirStack(TestCase):
    @property
    def _file_list(self):
        return sorted(list(self._tempdir.iterdir()))

    def _prune_in_directory(self, **kwargs):
        prune_in_directory(self._tempdir, self._file_list, self._time, **kwargs, quiet=True)

    def setUp(self):
        self._tempdir = Path(mkdtemp()).resolve()
        self._time = time()
        file_time = dt.now()
        for c in 'abcd':
            for i in (1, 2):
                Path(temp_file := self._tempdir / f'{c}{i}.txt').touch()
                if i == 1:
                    file_time += timedelta(days=2)
                utime(temp_file, (file_epoch_time := mktime(file_time.timetuple()), file_epoch_time))
        self._full_file_list = self._file_list

    def tearDown(self):
        rmtree_hard(self._tempdir)

    def test_prune_in_directory_1_no_removal(self):
        self._prune_in_directory()
        self.assertEqual(self._full_file_list, self._file_list)

    def test_prune_in_directory_2_by_age(self):
        self._prune_in_directory(age=10)
        self.assertEqual(self._full_file_list, self._file_list)
        self._prune_in_directory(age=6)
        self.assertEqual(self._full_file_list[:-2], self._file_list)
        self._prune_in_directory(age=4)
        self.assertEqual(self._full_file_list[:-4], self._file_list)

    def test_prune_in_directory_3_by_count(self):
        self._prune_in_directory(count=10)
        self.assertEqual(self._full_file_list, self._file_list)
        self._prune_in_directory(count=2)
        print([f.name for f in self._full_file_list])
        print([f.name for f in self._file_list])
        self.assertEqual(self._full_file_list[:-2], self._file_list)
        self._prune_in_directory(count=4)
        self.assertEqual(self._full_file_list[:-4], self._file_list)


if __name__ == '__main__':
    main()

# cSpell:ignore batcave fileutil dcba
