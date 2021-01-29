"""This module provides utilities for managing configurations."""

# Import standard modules
from pathlib import Path
from string import Template
from typing import Optional
from xml.etree.ElementTree import ParseError

from .data import DataError, DataSource, SourceType
from .lang import switch, BatCaveError, BatCaveException, PathName


class ConfigurationError(BatCaveException):
    """Configuration Exceptions.

    Attributes:
        BAD_FORMAT: The configuration file format is invalid.
        BAD_SCHEMA: The configuration schema is not supported.
        CONFIG_NOT_FOUND: The specified configuration file was not found.
    """
    BAD_FORMAT = BatCaveError(1, Template('Bad format for configuration file: $file'))
    BAD_SCHEMA = BatCaveError(2, Template('Invalid schema in configuration file: $file'))
    CONFIG_NOT_FOUND = BatCaveError(3, Template('Unable to find the configuration file: $file'))


class ConfigCollection:
    """This is a container class to hold a collection of configurations read from a file.

    Attributes:
        INCLUDE_CONFIG_TAG: The configuration tag which indicates an include file.
        _CURRENT_CONFIG_SCHEMA: The default DataSource schema to use.
        _MASK_MISSING: The parameter to indicate that child configurations should be ignored.
        _PARAMS_CONFIGURATION: The configuration section which is used as configuration parameters for the collection.
        _PARENT_CONFIGURATION: The parameter to indicate the parent configuration name.
    """
    _CURRENT_CONFIG_SCHEMA = 1
    _MASK_MISSING = 'mask_missing'
    _PARAMS_CONFIGURATION = 'configuration'
    _PARENT_CONFIGURATION = 'parent'

    INCLUDE_CONFIG_TAG = 'include'

    def __init__(self, name: PathName, /, *, create: bool = False, suffix: str = '_config.xml'):
        """
        Args:
            name: The configuration collection name.
            create (optional, default=False): If True the configuration file will be created if it doesn't exist.
            suffix (optional, default=_config.xml): The suffix to add to the name to derive the configuration file name.

        Attributes:
            params: This is the list of configuration parameters read from the configuration section.
            parent: The parent configuration.
            _config_filename: The derived name of the configuration file.
            _configs: This is the collection of configurations.
            _current: This is the value used by the iterator.
            _data_source: A reference to the DataSource instance read from the configuration file.
            _mask_missing: This value is read from the configuration section and
                if True will prevent missing values from the parent from creating values.
            _name: The value of the name argument.

        Raises:
            ConfigurationError.BAD_FORMAT: The the format of the configuration file is not valid.
            ConfigurationError.BAD_SCHEMA: If the schema of the configuration file is not supported.
            ConfigurationError.CONFIG_NOT_FOUND: If the derived configuration file is not found.
        """
        self._name = (path_name := Path(name)).name
        self._config_filename = path_name.parent / (path_name.name + suffix)
        try:
            self._data_source = DataSource(SourceType.xml, self._config_filename, name=self.name, schema=self._CURRENT_CONFIG_SCHEMA, create=create)
        except DataError as err:
            for case in switch(err.code):
                if case(DataError.FILE_OPEN.code):
                    raise ConfigurationError(ConfigurationError.CONFIG_NOT_FOUND, file=self._config_filename) from err
                if case(DataError.BAD_SCHEMA.code):
                    raise ConfigurationError(ConfigurationError.BAD_SCHEMA, file=self._config_filename) from err
                if case():
                    raise
        except ParseError as err:
            raise ConfigurationError(ConfigurationError.BAD_FORMAT, file=self._config_filename) from err

        self.parent: Optional[ConfigCollection] = None
        self._mask_missing = True
        self.params = getattr(self, self._PARAMS_CONFIGURATION) if hasattr(self, self._PARAMS_CONFIGURATION) else None
        if hasattr(self.params, self._PARENT_CONFIGURATION):
            self.parent = ConfigCollection(getattr(self.params, self._PARENT_CONFIGURATION))
        self._mask_missing = hasattr(self.params, self._MASK_MISSING)

        self._configs = [getattr(self, t.name) for t in self._data_source.gettables() if t.name not in (DataSource.INFO_TABLE, self._PARAMS_CONFIGURATION)]
        config_names = [c.name for c in self._configs]
        if self.parent and not self._mask_missing:
            self._configs += [c for c in self.parent if c.name not in config_names]
        self._current = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False

    def __getattr__(self, attr: str):
        if self._data_source.hastable(attr):
            parent_config = getattr(self.parent, attr) if (self.parent and hasattr(self.parent, attr)) else None
            config = Configuration(self._data_source, attr, parent=parent_config)
            if hasattr(config, self.INCLUDE_CONFIG_TAG):
                config = Configuration(self._data_source, attr, parent=parent_config, include=getattr(self, getattr(config, self.INCLUDE_CONFIG_TAG)))
            return config
        if self.parent and not self._mask_missing:
            return getattr(self.parent, attr)
        raise AttributeError(f'Unknown configuration ({attr}) in {self._config_filename}')

    def __iter__(self):
        return self

    def __next__(self):
        if self._current >= len(self._configs):
            raise StopIteration()
        self._current += 1
        return self._configs[self._current - 1]

    name = property(lambda s: s._name, doc='A read-only property which returns the name of the configuration.')

    def add(self, name: str, /) -> str:
        """Add an item to the configuration collection.

        Args:
            name: The name of the item to add.

        Returns:
            The value of the added item.
        """
        self._data_source.addtable(name).addrow()
        self._data_source.commit()
        return getattr(self, name)

    def close(self) -> None:
        """Close the underlying data source."""
        self._data_source.close()


class Configuration:
    """This is a container class to hold an individual configuration in a collection."""

    def __init__(self, config_source: DataSource, name: str, /, *, parent: Optional['Configuration'] = None, include: Optional['Configuration'] = None):
        """
        Args:
            config_source: The configuration source.
            name: The configuration name.
            parent (optional, default=None): If not None, the parent configuration.
            include (optional, default=None): If not None, the configuration to include.

        Attributes:
            _data_source: The value of the config_source argument.
            _data_table: The DataTable holding the configuration values for this configuration.
            _include: The value of the include argument.
            _name: The value of the name argument.
            _parent: The value of the parent argument.
        """
        self._name = name
        self._data_source = config_source
        self._data_table = self._data_source.gettable(self._name)
        self._parent = parent
        self._include = include

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def __getattr__(self, attr: str) -> str:
        # First check this configuration to see if it has the requested attribute
        if values := self._data_table.getrows(attr):
            return values[0].getvalue(attr)

        # Next check the include configuration without considering its parents
        if self._include:
            include_parent_value = self._include._parent  # pylint: disable=protected-access
            self._include._parent = None  # pylint: disable=protected-access
            if hasattr(self._include, attr):
                self._include._parent = include_parent_value  # pylint: disable=protected-access
                return getattr(self._include, attr)
            self._include._parent = include_parent_value  # pylint: disable=protected-access

        # Next check the parent configuration considering its includes
        if self._parent and attr != ConfigCollection.INCLUDE_CONFIG_TAG:
            if hasattr(self._parent, attr):
                return getattr(self._parent, attr)

        # Finally check the include configuration considering its parents
        if self._include:
            if hasattr(self._include, attr):
                return getattr(self._include, attr)

        # The attribute wasn't found
        raise AttributeError(f'Unknown parameter ({attr}) for configuration: {self._name}')

    def __setattr__(self, attr: str, value: str) -> None:
        if attr.startswith('_'):
            super().__setattr__(attr, value)
            return
        self._data_table.getrows()[0].setvalue(attr, value)
        self._data_source.commit()

    name = property(lambda s: s._name, doc='A read-only property which returns the name of the configuration.')
