"""This module provides utilities for managing data sources.

Data source definitions:
    TEXT
        source - a text file with '>NAME' delimiting tables
        table - a list of rows
        row - a line of the format column1:value1|column2:value2
        column - : delimited part of the line
    INI
        source - an ini file
        table - an ini section of the form
                    [TABLENAME]
                    ROWS: 1,...,N
        row - an ini section of the form
                    [TABLENAME ROW N]
                    col1: val1
                    col2: val2
        column - a section option
    PICKLE
        source - a Python pickle file containing a single dictionary
        table - a member of the top level dictionary which is a list of rows
        row - a dictionary of column:value pairs
    XML_SINGLE
        This format is a kludge to support the old RCFile format
        source - an XML file with the top level element the name of the datasource
        table - there is only one table which has the same name as the top level element
        row - an XML element of the form
                <environment name=COL-NAME-VALUE>
                    COLUMNS
                </environment>
        column - an XML element of the form
                <COL-NAME>COL-VALUE</COL-NAME>
    XML_FLAT
        source - an XML file with the top level element the name of the datasource
        table - a collection of XML elements
        row - an XML element of the form
                <TABLE-NAME COL-NAME="COL-VAL" />
        column - an XML element attribute
    XML
        source - an XML file with the top level element the name of the datasource
        table - an XML element of the form
                <TABLE name="TABLE-NAME">
                    ROWS
                </TABLE>
        row - an XML element of the form
                <ROW>
                    COLUMNS
                </ROW>
        column - an XML element of the form
                <COL-NAME>COL-VALUE</COL-NAME>

Attributes:
    _SOURCE_TYPES (Enum): The source providers supported by the DataSource class.
"""

# Import standard modules
from configparser import RawConfigParser
from enum import Enum
from pathlib import PurePath
from pickle import dump as pickle_dump, load as pickle_load
from string import Template
from urllib.request import urlopen
from xml.parsers import expat
import xml.etree.ElementTree as xml_etree

# Import internal modules
from .lang import switch, BatCaveError, BatCaveException

_SOURCE_TYPES = Enum('source_types', ('text', 'ini', 'pickle', 'xml_single', 'xml_flat', 'xml'))


class DataError(BatCaveException):
    """Data related Exceptions.

    Attributes:
        BAD_COLUMN: The column specified was not found.
        BAD_ROOT: The root element for the XML data source was not the one requested.
        BAD_SCHEMA: The data source schema does not match the one requested.
        BAD_TABLE: The requested table was not found.
        BAD_URL: The URL specified does not contain a valid data source.
        FILE_OPEN: Error opening the data source file.
        INVALID_OPERATION: The specified data source type does not support the requested operation.
        INVALID_TYPE: An invalid data source type was specified.
    """
    BAD_COLUMN = BatCaveError(1, Template('Invalid column: $col\nonline $line'))
    BAD_ROOT = BatCaveError(2, Template('The root element "$root_name" is not the one requested ($expected) in $source_name'))
    BAD_SCHEMA = BatCaveError(3, Template('Wrong schema ($schema) specified for data source ($found)'))
    BAD_TABLE = BatCaveError(4, Template('No table named "$table_name" in data source "$source_name"'))
    BAD_URL = BatCaveError(5, Template('No valid DataSource found at URL: $url'))
    FILE_OPEN = BatCaveError(6, Template('Unable to open file: $errmsg'))
    INVALID_OPERATION = BatCaveError(7, Template('Function "$function" not supported for source type "$source_type"'))
    INVALID_TYPE = BatCaveError(8, 'Invalid data source type. Must be one of: ' + str([t.name for t in _SOURCE_TYPES]))


class DataSource:
    """Class to create a universal abstract interface for a data source.

    Attributes:
        SOURCE_TYPES: The data source types currently supported by this class.
        INFO_TABLE: The table in the data source which has info about the source.
        _SCHEMA_DATA: The row which contains the schema version.

        INI_ROWLIST_OPT: The INI file section which contains the rows.
        INI_ROW_TAG: The INI file tag to mark a row.

        _TEXT_TABLE_DELIMITER: The table delimeter for a text file.
        _TEXT_VAL_DELIMITER: The value delimeter for a text file.

        _XML_TABLE_TAG: The XML file tag to denote a table.
        _XML_TABLE_NAME_ATTRIBUTE: The XML file attribute to denote a table name.
        _XML_SINGLE_COL_NAME: The XML file attribute to denote a column name.
    """
    SOURCE_TYPES = _SOURCE_TYPES
    INFO_TABLE = 'DataSourceInfo'
    _SCHEMA_DATA = 'schema'

    INI_ROWLIST_OPT = 'ROWS'
    INI_ROW_TAG = ' ROW '

    _TEXT_TABLE_DELIMITER = '>'
    _TEXT_VAL_DELIMITER = ':'

    _XML_TABLE_TAG = 'TABLE'
    _XML_TABLE_NAME_ATTRIBUTE = 'name'
    _XML_SINGLE_COL_NAME = 'name'

    def __init__(self, data_type, connectinfo, name, schema, create=False):
        """
        Args:
            data_type: The data source type.
            connectinfo: The data source file name.
            name: The data source name.
            schema: The schema version of the data source.
            create (optional, default=False): If True, the data source will be created if it does not exist.

        Attributes:
            name: The value of the name argument.
            type: The value of the data_type argument.
            _closer: This is the method used to close the data source.
            _connectinfo: The value of the connectinfo argument.
            _connection: For XML_* data source types, this it the parsed XML tree,
                otherwise it is a temporary file object.
            _schema: The value of the schema argument.
            _source: The value depends on the data source type.
                TEXT: the file contents
                PICKLE: the top dictionary
                INI: The RawConfigParser object from the INI file
                XML_*: The XML root of the file

        Raises:
            DataError.FILE_OPEN: If the data source file is already open.
        """
        self.type = data_type
        self.name = name
        self._schema = schema
        self._source = None
        self._connectinfo = connectinfo
        self._connection = None
        self._closer = None
        self._validate_type()
        try:
            self._load()
            self._validate_schema()
        except IOError as ioe:
            if create and (ioe.errno == 2):
                self._create()
            else:
                raise DataError(DataError.FILE_OPEN, errmsg=str(ioe))

    filename = property(lambda s: s._connectinfo, doc='A read-only property which returns the file name of the data source.')

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False

    @property
    def dict_repr(self):
        """A read-only property which returns a the data source as a dictionary."""
        dictrepr = dict()
        for table in self.gettables():
            with table.getrows()[0] as row:
                dictrepr[table.name] = {c: row.getvalue(c) for c in row.getcolumns()}
        return dictrepr

    @property
    def schema(self):
        """A read-only property which returns the schema value of the data source."""
        try:
            return int(self.gettable(self.INFO_TABLE).getrows(col=self._SCHEMA_DATA)[0].getvalue(self._SCHEMA_DATA))
        except IndexError:
            return 0
        except DataError as err:
            if err.code != DataError.BAD_TABLE.code:
                raise
            return 0

    def _validate_type(self):
        """Determines if the specified data source type is valid.

        Returns:
            Nothing
            
        Raises:
            DataError.INVALID_TYPE: If the data source type is invalid.
        """
        if self.type not in self.SOURCE_TYPES:
            raise DataError(DataError.INVALID_TYPE)

    def _validate_schema(self):
        """Determines if the data source schema is valid.

        Returns:
            Nothing
            
        Raises:
            DataError.BAD_SCHEMA: If the data source schema is invalid.
        """
        if self._schema != self.schema:
            raise DataError(DataError.BAD_SCHEMA, schema=self._schema, found=self.schema)

    def _create(self):
        """Creates the data source.

        Returns:
            Nothing
        """
        for case in switch(self.type):
            if case(self.SOURCE_TYPES.text):
                pass
            if case(self.SOURCE_TYPES.pickle):
                self._source = dict()
                break
            if case(self.SOURCE_TYPES.ini):
                self._source = RawConfigParser()
                break
            if case(self.SOURCE_TYPES.xml_single):
                pass
            if case(self.SOURCE_TYPES.xml_flat):
                pass
            if case(self.SOURCE_TYPES.xml):
                self._source = xml_etree.Element(self.name)
                self._connection = xml_etree.ElementTree(self._source)
                break
        if self.type != self.SOURCE_TYPES.xml_single:
            source_info = self.addtable(self.INFO_TABLE)
            source_info.addrow(schema=str(self._schema))
        self.commit()

    def _load(self):
        """Loads the data source.

        Returns:
            Nothing
            
        Raises:
            DataError.BAD_COLUMN: If a text type data source has a column with no value.
            DataError.BAD_ROOT: If the root of the data source does not match the name.
            DataError.BAD_URL: If the data source is specified as a malformed URL.
        """
        for case in switch(self.type):
            if case(self.SOURCE_TYPES.text):
                self._source = dict()
                for line in open(self._connectinfo):
                    line = line.strip()
                    if line.startswith(self._TEXT_TABLE_DELIMITER):
                        table_name = line.lstrip(self._TEXT_TABLE_DELIMITER)
                        self._source[table_name] = list()
                        continue
                    row = dict()
                    for pair in line.split(self._TEXT_TABLE_DELIMITER):
                        try:
                            (col, val) = pair.split(self._TEXT_VAL_DELIMITER)
                        except ValueError:
                            raise DataError(DataError.BAD_COLUMN, col=pair, line=line)
                        row[col] = val
                    self._source[table_name].append(row)
                break
            if case(self.SOURCE_TYPES.pickle):
                self._source = pickle_load(open(self._connectinfo))
                break
            if case(self.SOURCE_TYPES.ini):
                self._source = RawConfigParser()
                if isinstance(self._connectinfo, str):
                    with open(self._connectinfo) as ini_tmp:
                        self._source.read_file(ini_tmp)
                else:
                    self._source.read_string(''.join(self._connectinfo))
                break
            if case(self.SOURCE_TYPES.xml_single):
                pass
            if case(self.SOURCE_TYPES.xml_flat):
                pass
            if case(self.SOURCE_TYPES.xml):
                if isinstance(self._connectinfo, list):
                    self._connection = xml_etree.ElementTree(xml_etree.fromstring(' '.join(self._connectinfo)))
                else:
                    if isinstance(self._connectinfo, str) or isinstance(self._connectinfo, PurePath):
                        if str(self._connectinfo).startswith('http:') or str(self._connectinfo).startswith('file:'):
                            self._closer = urlopen(self._connectinfo)
                        else:
                            self._closer = open(self._connectinfo)
                    else:
                        self._closer = self._connectinfo
                    try:
                        self._connection = xml_etree.parse(self._closer)
                    except expat.ExpatError as err:
                        if expat.ErrorString(err.code) == expat.errors.XML_ERROR_SYNTAX:  # pylint: disable=E1101
                            raise DataError(DataError.BAD_URL, url=self._connectinfo)
                        raise
                self._source = self._connection.getroot()
                if self._source.tag != self.name:
                    raise DataError(DataError.BAD_ROOT, source_name=self._connectinfo, root_name=self._source.tag, expected=self.name)
                break

    def gettables(self):
        """Get all the tables from the data source.

        Returns:
            The list of table in the data source.
        """
        for case in switch(self.type):
            if case(self.SOURCE_TYPES.text):
                pass
            if case(self.SOURCE_TYPES.pickle):
                table_names = [t for t in self._source]
                break
            if case(self.SOURCE_TYPES.ini):
                table_names = [t for t in self._source.sections() if self.INI_ROW_TAG not in t]
                break
            if case(self.SOURCE_TYPES.xml_single):
                table_names = [self.name]
                break
            if case(self.SOURCE_TYPES.xml_flat):
                table_names = self._source.findall()
                break
            if case(self.SOURCE_TYPES.xml):
                table_names = [t.get(self._XML_TABLE_NAME_ATTRIBUTE) for t in self._source.iter(self._XML_TABLE_TAG)]
                break
        return [self.gettable(t) for t in table_names]

    def gettable(self, name):
        """Get the requested data table.

        Args:
            name: The name of the table to return.

        Returns:
            The requested data table.
            
        Raises:
            DataError.BAD_TABLE: If the requested table is not found.
        """
        table = None
        for case in switch(self.type):
            if case(self.SOURCE_TYPES.text):
                pass
            if case(self.SOURCE_TYPES.pickle):
                if name in self._source:
                    table = self._source[name]
                break
            if case(self.SOURCE_TYPES.ini):
                if self._source.has_section(name):
                    rowlist = self._source.get(name, self.INI_ROWLIST_OPT)
                    table = [int(r) for r in rowlist.split(',')] if rowlist else list()
                break
            if case(self.SOURCE_TYPES.xml_single):
                if name == self.name:
                    table = self._source
                break
            if case(self.SOURCE_TYPES.xml_flat):
                table = self._source.findall(name)
                break
            if case(self.SOURCE_TYPES.xml):
                for tmptable in self._source.iter(self._XML_TABLE_TAG):
                    if tmptable.get(self._XML_TABLE_NAME_ATTRIBUTE) == name:
                        table = tmptable
                        break
                break
        if table is None:
            raise DataError(DataError.BAD_TABLE, table_name=name, source_name=self.name)
        return DataTable(self.type, name, table, self._source)

    def hastable(self, name):
        """Determine if the named table exists in the data source.

        Args:
            name: The name of the table to search for.

        Returns:
            Returns True if the named table exists in the data source, False otherwise.
        """
        for case in switch(self.type):
            if case(self.SOURCE_TYPES.text):
                pass
            if case(self.SOURCE_TYPES.pickle):
                if name in self._source:
                    return True
                break
            if case(self.SOURCE_TYPES.ini):
                if self._source.has_section(name):
                    return True
                break
            if case(self.SOURCE_TYPES.xml_single):
                if name == self.name:
                    return True
                break
            if case(self.SOURCE_TYPES.xml_flat):
                return True
            if case(self.SOURCE_TYPES.xml):
                for tmptable in self._source.iter(self._XML_TABLE_TAG):
                    if tmptable.get(self._XML_TABLE_NAME_ATTRIBUTE) == name:
                        return True
                break
        return False

    def addtable(self, name):
        """Creates a new table with the specified name.

        Args:
            name: The name of the table to add.
            
        Returns:
            The created table.
            
        Raises:
            DataError.INVALID_OPERATION: If the data source type does not support adding a table.
        """
        for case in switch(self.type):
            if case(self.SOURCE_TYPES.text):
                pass
            if case(self.SOURCE_TYPES.pickle):
                self._source[name] = list()
                break
            if case(self.SOURCE_TYPES.ini):
                self._source.add_section(name)
                self._source.set(name, self.INI_ROWLIST_OPT, '')
                break
            if case(self.SOURCE_TYPES.xml_single):
                raise DataError(DataError.INVALID_OPERATION, function='addtable', source_type=self.type)
            if case(self.SOURCE_TYPES.xml_flat):
                break
            if case(self.SOURCE_TYPES.xml):
                table = xml_etree.SubElement(self._source, self._XML_TABLE_TAG)
                table.attrib[self._XML_TABLE_NAME_ATTRIBUTE] = name
                break
        return self.gettable(name)

    def commit(self):
        """Commit any changes in memory to the source.

        Returns:
            Nothing
        """
        for case in switch(self.type):
            if case(self.SOURCE_TYPES.text):
                self._connection = open(self._connectinfo, 'w')
                for (table_name, rows) in self._source.items():
                    self._connection.write(self._TEXT_TABLE_DELIMITER + table_name + '\n')
                    for row in rows:
                        self._connection.write(self._TEXT_TABLE_DELIMITER.join([f'{col}{self._TEXT_VAL_DELIMITER}{row[col]}' for col in row]) + '\n')
                self._connection.close()
                break
            if case(self.SOURCE_TYPES.pickle):
                self._connection = open(self._connectinfo, 'w')
                pickle_dump(self._source, self._connection)
                self._connection.close()
                break
            if case(self.SOURCE_TYPES.ini):
                self._connection = open(self._connectinfo, 'w')
                self._source.write(self._connection)
                self._connection.close()
                break
            if case(self.SOURCE_TYPES.xml_single):
                pass
            if case(self.SOURCE_TYPES.xml_flat):
                pass
            if case(self.SOURCE_TYPES.xml):
                self._connection.write(self._connectinfo, 'ISO-8859-1')
                break

    def close(self):
        """Closes the data source.

        Returns:
            Nothing
        """
        if self._closer:
            self._closer.close()
            self._connectinfo = self._closer = self._source = self._connection = None


class DataRow:
    """Class to create a universal abstract interface for a data row."""

    def __init__(self, data_type, raw, parent):
        """
        Args:
            data_type: The data source type.
            raw: The raw value of the row as read from the data source.
            parent: This is a reference to the table containing the row.

        Attributes:
            type: The value of the data_type argument.
            _parent: The value of the parent argument.
            _row: The value of the raw argument.
        """
        self.type = data_type
        self._row = raw
        self._parent = parent

    raw = property(lambda s: s._row, doc='A read-only property which returns the raw contents of the data row.')

    def __getattr__(self, attr):
        return self.getvalue(attr)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def delete(self):
        'TODO: Delete the data row'
        for case in switch(self.type):
            if case(DataSource.SOURCE_TYPES.ini):
                self._parent.remove_section(self._row)
                break
            if case():
                self._parent.remove(self._row)

    def hascol(self, col):
        'Checks if the row has the specified column.'
        for case in switch(self.type):
            if case(DataSource.SOURCE_TYPES.text):
                pass
            if case(DataSource.SOURCE_TYPES.pickle):
                return col in self._row
            if case(DataSource.SOURCE_TYPES.ini):
                return self._parent.has_option(self._row, col)
            if case(DataSource.SOURCE_TYPES.xml_single):
                if col == self._XML_SINGLE_COL_NAME:
                    return bool(self._row.get(col))
            if case(DataSource.SOURCE_TYPES.xml):
                if self._row.find(col) is not None:
                    return True
                return False
            if case(DataSource.SOURCE_TYPES.xml_flat):
                return bool(self._row.get(col))

    def getcolumns(self):
        'Returns all the columns from the row.'
        for case in switch(self.type):
            if case(DataSource.SOURCE_TYPES.text):
                pass
            if case(DataSource.SOURCE_TYPES.pickle):
                return list(self._row.keys())
            if case(DataSource.SOURCE_TYPES.ini):
                return self._parent.options(self._row)
            if case(DataSource.SOURCE_TYPES.xml_single):
                cols = [e.tag for e in self._row.getiterator()]
                if self._row.get(self._XML_SINGLE_COL_NAME):
                    cols.append(self._XML_SINGLE_COL_NAME)
                return cols
            if case(DataSource.SOURCE_TYPES.xml_flat):
                return list(self._row.attrib.keys())
            if case(DataSource.SOURCE_TYPES.xml):
                return [e.tag for e in list(self._row) if e.tag != self._XML_ROW_TAG]
        return None

    def delcolumn(self, col):
        'Deletes the named column from the row.'
        if not self.hascol(col):
            return

        for case in switch(self.type):
            if case(DataSource.SOURCE_TYPES.text):
                pass
            if case(DataSource.SOURCE_TYPES.pickle):
                del self._row[col]
                break
            if case(DataSource.SOURCE_TYPES.ini):
                self._parent.remove_option(col)
                break
            if case(DataSource.SOURCE_TYPES.xml_single):
                if col == self._XML_SINGLE_COL_NAME:
                    del self._row.attrib[col]
                    break
            if case(DataSource.SOURCE_TYPES.xml):
                self._row.remove(self._row.find(col))
                break
            if case(DataSource.SOURCE_TYPES.xml_flat):
                del self._row.attrib[col]
                break

    def getvalue(self, col):
        'Gets the value of the specified column.'
        for case in switch(self.type):
            if case(DataSource.SOURCE_TYPES.text):
                pass
            if case(DataSource.SOURCE_TYPES.pickle):
                if self.hascol(col):
                    return self._row[col]
                break
            if case(DataSource.SOURCE_TYPES.ini):
                if self.hascol(col):
                    return self._parent.get(self._row, col)
                break
            if case(DataSource.SOURCE_TYPES.xml_single):
                if col == self._XML_SINGLE_COL_NAME:
                    return self._row.get(col)
                break
            if case(DataSource.SOURCE_TYPES.xml_flat):
                return self._row.get(col)
            if case(DataSource.SOURCE_TYPES.xml):
                return self._row.findtext(col)
        return None

    def setvalue(self, col, value):
        'Sets the value of the specified column.'
        for case in switch(self.type):
            if case(DataSource.SOURCE_TYPES.text):
                pass
            if case(DataSource.SOURCE_TYPES.pickle):
                self._row[col] = value
                break
            if case(DataSource.SOURCE_TYPES.ini):
                self._parent.set(self._row, col, value)
                break
            if case(DataSource.SOURCE_TYPES.xml_single):
                if col == self._XML_SINGLE_COL_NAME:
                    self._row.attrib[col] = value
                    break
            if case(DataSource.SOURCE_TYPES.xml):
                colref = self._row.find(col)
                if colref is None:
                    colref = xml_etree.SubElement(self._row, col)
                colref.text = value
                break
            if case(DataSource.SOURCE_TYPES.xml_flat):
                self._row.attrib[col] = value
                break


class DataTable:
    """Class to create a universal abstract interface for a data table.

    The _parent meaning changes based on the source type:
        TEXT = absolute path to the data directory
        PICKLE = top level dictionary
        XML_* = the parent element

    Attributes:
        _INI_ROW_FORMAT: The format for an INI file row.
        _XML_ROW_TAG: The XML file tag to denote a row.
        _XML_SINGLE_ROW_TAG: The XML file tag to denote a row (xml_single data source).
    """
    _INI_ROW_FORMAT = f'%s{DataSource.INI_ROW_TAG}%d'
    _XML_ROW_TAG = 'ROW'
    _XML_SINGLE_ROW_TAG = 'environment'

    def __init__(self, data_type, name, raw, parent):
        """
        Args:
            data_type: The data source type.
            name: The table name.
            raw: The raw value of the table as read from the data source.
            parent: This is a reference to the data source containing the table.

        Attributes:
            name: The value of the name argument.
            type: The value of the data_type argument.
            _parent: The value of the parent argument.
            _table: The value of the raw argument.
        """
        self.type = data_type
        self.name = name
        self._parent = parent
        self._table = raw

    raw = property(lambda s: s._table, doc='A read-only property which returns the raw contents of the data table.')

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def _get_row_parent(self):
        for case in switch(self.type):
            if case(DataSource.SOURCE_TYPES.text):
                pass
            if case(DataSource.SOURCE_TYPES.pickle):
                pass
            if case(DataSource.SOURCE_TYPES.xml):
                return self._table
            if case(DataSource.SOURCE_TYPES.ini):
                pass
            if case(DataSource.SOURCE_TYPES.xml_single):
                pass
            if case(DataSource.SOURCE_TYPES.xml_flat):
                return self._parent

    def getrows(self, col=None, value=None):
        'return the data rows matching the specified selector'
        rowlist = self._table if self.type != DataSource.SOURCE_TYPES.ini else [self._INI_ROW_FORMAT % (self.name, r) for r in self._table]
        allrows = [DataRow(self.type, r, self._get_row_parent()) for r in rowlist]
        if (col is None) and (value is None):
            return allrows
        if value is None:
            return [r for r in allrows if r.hascol(col)]
        return [r for r in allrows if r.getvalue(col) == value]

    def addrow(self, **values):
        'creates a new data row with the specified values'
        for case in switch(self.type):
            if case(DataSource.SOURCE_TYPES.text):
                pass
            if case(DataSource.SOURCE_TYPES.pickle):
                pass
            if case(DataSource.SOURCE_TYPES.ini):
                row = (int(self._table[-1]) + 1) if self._table else 1
                self._parent.add_section(self._INI_ROW_FORMAT % (self.name, row))
                self._table.append(row)
                self._parent.set(self.name, DataSource.INI_ROWLIST_OPT, ','.join([str(r) for r in self._table]))
                row = self._INI_ROW_FORMAT % (self.name, row)
                break
            if case(DataSource.SOURCE_TYPES.xml_single):
                row = xml_etree.SubElement(self._parent, self._XML_SINGLE_ROW_TAG)
                break
            if case(DataSource.SOURCE_TYPES.xml_flat):
                row = xml_etree.SubElement(self._parent, self.name)
                break
            if case(DataSource.SOURCE_TYPES.xml):
                row = xml_etree.SubElement(self._table, self._XML_ROW_TAG)
                break
        row = DataRow(self.type, row, self._get_row_parent())
        for (var, val) in values.items():
            row.setvalue(var, val)
        return row

    def delrow(self, col, value):
        'deletes the rows with the specified column value'
        for row in self.getrows(col, value):
            row.delete()
