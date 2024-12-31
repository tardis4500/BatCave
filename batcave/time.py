"""This module provides improved date/time support."""

# Import standard modules
from copy import deepcopy
from datetime import datetime, timezone
from string import Template
from typing import Optional, Union

# Import third-party modules
from dateutil.parser import parse as parse_timestamp
from google.api_core.datetime_helpers import DatetimeWithNanoseconds

# Import internal modules
from .lang import BatCaveError, BatCaveException

type BatCaveDateTimeType = Union[DatetimeWithNanoseconds, float, str, datetime, 'BatCaveDateTime']


class TimeError(BatCaveException):
    """Class for time exceptions."""
    BAD_CONVERSION_TYPE = BatCaveError(1, Template('Unable to convert $type to TMDateTime'))


class BatCaveDateTime:
    """Class to manage date/time values."""
    _OUTPUT_FORMAT = '%Y-%m-%d-%H-%M-%S%Z'
    _INPUT_FORMAT = '%Y-%m-%d-%H-%M-%S%z'

    def __init__(self, time_info: Optional[BatCaveDateTimeType] = None):
        self._datetime = self._to_dt(deepcopy(time_info) if time_info else datetime.now(timezone.utc))

    def __eq__(self, other: object):
        if isinstance(other, BatCaveDateTime):
            return self.datetime == other.datetime
        return self.datetime == other

    def __ne__(self, other: object):
        if isinstance(other, BatCaveDateTime):
            return self.datetime != other.datetime
        return self.datetime != other

    def __gt__(self, other: object):
        if isinstance(other, BatCaveDateTime):
            return self.datetime > other.datetime
        return self.datetime > other

    def __lt__(self, other: object):
        if isinstance(other, BatCaveDateTime):
            return self.datetime < other.datetime
        return self.datetime < other

    def __str__(self):
        return self._dt_to_str(self.datetime)

    def __sub__(self, other: object):
        if isinstance(other, BatCaveDateTime):
            return self.datetime - other.datetime
        return self.datetime - other

    def _dt_to_str(self, dt_obj: 'datetime') -> str:
        return dt_obj.strftime(self._OUTPUT_FORMAT)

    def _str_to_dt(self, dt_str: str) -> datetime:
        if len(dt_str.split('-')) == 6:
            return datetime.strptime(dt_str.removesuffix('UTC') + '+0000', self._INPUT_FORMAT)
        return parse_timestamp(dt_str).astimezone(timezone.utc)

    def _to_dt(self, time_info: BatCaveDateTimeType) -> datetime:
        if isinstance(time_info, DatetimeWithNanoseconds):
            return self._str_to_dt(self._dt_to_str(time_info))
        if isinstance(time_info, float):
            return datetime.utcfromtimestamp(time_info)
        if isinstance(time_info, str):
            return self._str_to_dt(time_info)
        if isinstance(time_info, datetime):
            if not time_info.tzinfo:
                time_info = self._str_to_dt(self._dt_to_str(time_info) + 'UTC')
            return time_info
        if isinstance(time_info, BatCaveDateTime):
            return time_info.datetime
        raise TimeError(TimeError.BAD_CONVERSION_TYPE, type=type(time_info))

    datetime = property(lambda s: s._datetime, doc='A read-only property which returns the datetime representation.')

    def ctime(self) -> str:
        """Return the ctime representation."""
        return self.datetime.ctime()

# cSpell:ignore astimezone dateutil
