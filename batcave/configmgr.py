'This provides an interface to manage configurations'
# Import standard modules
from pathlib import Path
from string import Template
from xml.etree.ElementTree import ParseError

from .data import DataError, DataSource
from .lang import switch, HALError, HALException


class ConfigurationError(HALException):
    'Class for EnvironmentConfiguration related errors'
    CONFIG_NOT_FOUND = HALError(1, Template('Unable to find the configuration file: $file'))
    BAD_FORMAT = HALError(2, Template('Bad format for configuration file: $file'))
    BAD_SCHEMA = HALError(3, Template('Invalid schema in configuration file: $file'))


class ConfigCollection:
    'Represents a configuration collection'
    INCLUDE_CONFIG_TAG = 'include'
    _CURRENT_CONFIG_SCHEMA = 1
    _MASK_MISSING = 'mask_missing'
    _PARAMS_CONFIGURATION = 'configuration'
    _PARENT_CONFIGURATION = 'parent'

    def __init__(self, config_name, create=False, suffix='_config.xml'):
        if isinstance(config_name, Path):
            self.name = config_name.name
            self.config_filename = config_name.parent / (config_name.name + suffix)
        else:
            self.name = config_name
            self.config_filename = Path(self.name + suffix)
        failure = False
        try:
            self.data_source = DataSource(DataSource.SOURCE_TYPES.xml, self.config_filename, self.name, self._CURRENT_CONFIG_SCHEMA, create)
        except DataError as err:
            for case in switch(err.code):
                if case(DataError.FILEOPEN.code):
                    failure = ConfigurationError.CONFIG_NOT_FOUND
                    break
                if case(DataError.WRONGSCHEMA.code):
                    failure = ConfigurationError.BAD_SCHEMA
                    break
                if case():
                    raise
        except ParseError:
            failure = ConfigurationError.BAD_FORMAT

        if failure:
            raise ConfigurationError(failure, file=self.config_filename)

        self.parent = None
        self._mask_missing = True
        self.params = getattr(self, self._PARAMS_CONFIGURATION) if hasattr(self, self._PARAMS_CONFIGURATION) else None
        if hasattr(self.params, self._PARENT_CONFIGURATION):
            self.parent = ConfigCollection(getattr(self.params, self._PARENT_CONFIGURATION))
        self._mask_missing = True if hasattr(self.params, self._MASK_MISSING) else False

        self._configs = [getattr(self, t.name) for t in self.data_source.gettables() if t.name not in (DataSource.INFO_TABLE, self._PARAMS_CONFIGURATION)]
        config_names = [c.name for c in self._configs]
        if self.parent and not self._mask_missing:
            self._configs += [c for c in self.parent if c.name not in config_names]
        self._current = 0

    def __getattr__(self, attr):
        if self.data_source.hastable(attr):
            parent_config = getattr(self.parent, attr) if (self.parent and hasattr(self.parent, attr)) else None
            config = Configuration(self.data_source, attr, parent_config)
            if hasattr(config, self.INCLUDE_CONFIG_TAG):
                config = Configuration(self.data_source, attr, parent_config, getattr(self, getattr(config, self.INCLUDE_CONFIG_TAG)))
            return config
        elif self.parent and not self._mask_missing:
            return getattr(self.parent, attr)
        raise AttributeError(f'Unknown configuration ({attr}) in {self.config_filename}')

    def __iter__(self):
        return self

    def __next__(self):
        if self._current >= len(self._configs):
            raise StopIteration()
        self._current += 1
        return self._configs[self._current-1]

    def add(self, name):
        'Adds an item to the configuration collection'
        self.data_source.addtable(name).addrow()
        self.data_source.commit()
        return getattr(self, name)


class Configuration:
    'Represents a single configuration in the collection.'
    def __init__(self, config_source, name, parent=None, include=None):
        self._name = name
        self._data_source = config_source
        self._data_table = self._data_source.gettable(name)
        self._parent = parent
        self._include = include

    name = property(lambda s: s._name)

    def __getattr__(self, attr):
        # First check this configuration to see if it has the requested attribute
        values = self._data_table.getrows(attr)
        if values:
            return values[0].getvalue(attr)

        # Next check the include configuration without considering its parents
        if self._include:
            include_parent_value = self._include._parent  # pylint: disable=protected-access
            self._include._parent = False  # pylint: disable=protected-access
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

    def __setattr__(self, attr, value):
        if attr.startswith('_'):
            super().__setattr__(attr, value)
            return
        data_row = self._data_table.getrows()[0]
        data_row.setvalue(attr, value)
        self._data_source.commit()
