'Unit tests for the package language extensions module'
# pylint: disable=C0103,C0111

import os
from unittest import main, TestCase

from batcave.lang import is_debug


class TestIsDebug(TestCase):
    def setUp(self):
        self._keeper = None
        if 'BATCAVE_DEBUG' in os.environ:
            self._keeper = os.environ['BATCAVE_DEBUG']
            del os.environ['BATCAVE_DEBUG']

    def tearDown(self):
        if self._keeper:
            os.environ['BATCAVE_DEBUG'] = self._keeper

    def test_is_debug_False(self):
        self.assertFalse(is_debug())

    def test_is_debug_True(self):
        os.environ['BATCAVE_DEBUG'] = '1'
        self.assertTrue(is_debug())

    def test_is_debug_SingleValue(self):
        os.environ['BATCAVE_DEBUG'] = 'TestValue'
        self.assertTrue(is_debug('TestValue'))
        self.assertFalse(is_debug('TestBadValue'))

    def test_is_debug_MultiValue(self):
        os.environ['BATCAVE_DEBUG'] = 'TestValue1:TestValue2'
        self.assertTrue(is_debug('TestValue1'))
        self.assertTrue(is_debug('TestValue2'))
        self.assertFalse(is_debug('TestBadValue'))


if __name__ == '__main__':
    main()
