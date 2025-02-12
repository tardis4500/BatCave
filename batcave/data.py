"""This module provides utilities for managing data sources.

Data source definitions:
    TEXT
        source - a text file with '>NAME' delimiting tables
        table - a list of rows
        row - a line of the format column1:value1|column2:value2
        column - delimited part of the line

    INI
        source - an ini file

        table - an ini section of the form::
            [TABLENAME]
            ROWS: 1,...,N

        row - an ini section of the form::
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

        row - an XML element of the form::
            <environment name=COL-NAME-VALUE>
            COLUMNS
            </environment>

        column - an XML element of the form::
            <COL-NAME>COL-VALUE</COL-NAME>

    XML_FLAT
        source - an XML file with the top level element the name of the datasource
        table - a collection of XML elements

        row - an XML element of the form::
            <TABLE-NAME COL-NAME="COL-VAL" />

        column - an XML element attribute

    XML
        source - an XML file with the top level element the name of the datasource

        table - an XML element of the form::
            <TABLE name="TABLE-NAME">
            ROWS
            </TABLE>

        row - an XML element of the form::
            <ROW>
            COLUMNS
            </ROW>

        column - an XML element of the form::
            <COL-NAME>COL-VALUE</COL-NAME>

Attributes:
    SourceType (Enum): The source providers supported by the DataSource class.
"""

# Import standard modules
from configparser import RawConfigParser
from enum import Enum
from pathlib import PurePath
from pickle import dump as pickle_dump, load as pickle_load
from string import Template
from typing import cast, Any, IO, List, Optional
from urllib.request import urlopen
from xml.parsers import expat
from xml.etree.ElementTree import ElementTree
import xml.etree.ElementTree as xml_etree

# Import internal modules
from .lang import DEFAULT_ENCODING, BatCaveError, BatCaveException, PathName

SourceType = Enum('SourceType', ('text', 'ini', 'pickle', 'xml'))


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
    FILE_OPEN = BatCaveError(6, Template('Unable to open file: $err_msg'))
    INVALID_OPERATION = BatCaveError(7, Template('Function "$function" not supported for source type "$source_type"'))
    INVALID_TYPE = BatCaveError(8, 'Invalid data source type. Must be one of: ' + str([t.name for t in SourceType]))


class DataSource:
    """Class to create a universal abstract interface for a data source.

    Attributes:
        INFO_TABLE: The table in the data source which has info about the source.
        _SCHEMA_DATA: The row which contains the schema version.

        INI_ROW_LIST_OPT: The INI file section which contains the rows.
        INI_ROW_TAG: The INI file tag to mark a row.

        _TEXT_TABLE_DELIMITER: The table delimiter for a text file.
        _TEXT_VAL_DELIMITER: The value delimiter for a text file.

        _XML_TABLE_TAG: The XML file tag to denote a table.
        _XML_TABLE_NAME_ATTRIBUTE: The XML file attribute to denote a table name.
        _XML_SINGLE_COL_NAME: The XML file attribute to denote a column name.
    """
    _SCHEMA_DATA = 'schema'
    _TEXT_TABLE_DELIMITER = '>'
    _TEXT_VAL_DELIMITER = ':'
    _XML_TABLE_TAG = 'TABLE'
    _XML_TABLE_NAME_ATTRIBUTE = 'name'
    _XML_SINGLE_COL_NAME = 'name'

    INFO_TABLE = 'DataSourceInfo'
    INI_ROW_TAG = ' ROW '
    INI_ROW_LIST_OPT = 'ROWS'

    def __init__(self, data_type: SourceType, connect_info: PathName, /, name: str, *, schema: int, create: bool = False):
        """
        Args:
            data_type: The data source type.
            connect_info: The data source file name.
            name: The data source name.
            schema: The schema version of the data source.
            create (optional, default=False): If True, the data source will be created if it does not exist.

        Attributes:
            _closer: This is the method used to close the data source.
            _connect_info: The value of the connect_info argument.
            _connection: For XML_* data source types, this it the parsed XML tree,
                otherwise it is a temporary file object.
            _name: The value of the name argument.
            _schema: The value of the schema argument.
            _source: The value depends on the data source type.
                TEXT: the file contents
                PICKLE: the top dictionary
                INI: The RawConfigParser object from the INI file
                XML_*: The XML root of the file
            _type: The value of the data_type argument.

        Raises:
            DataError.FILE_OPEN: If the data source file is already open.
        """
        self._name = name
        self._schema = schema
        self._source: Any = None
        self._type = data_type
        self._connect_info = connect_info
        self._connection: Optional[IO | ElementTree] = None
        self._closer: Optional[IO] = None
        self._validate_type()
        try:
            self._load()
            self._validate_schema()
        except IOError as ioe:
            if create and (ioe.errno == 2):
                self._create()
            else:
                raise DataError(DataError.FILE_OPEN, err_msg=str(ioe)) from ioe

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False

    def _create(self) -> None:
        """Create the data source.

        Returns:
            Nothing.
        """
        match self.type:
            case SourceType.text | SourceType.pickle:
                self._source = {}
            case SourceType.ini:
                self._source = RawConfigParser()
            case SourceType.xml:
                self._source = xml_etree.Element(self.name)
                self._connection = xml_etree.ElementTree(self._source)
        self.add_table(self.INFO_TABLE).add_row(schema=str(self._schema))
        self.commit()

    def _load(self) -> None:  # pylint: disable=too-many-branches
        """Load the data source.

        Returns:
            Nothing.

        Raises:
            DataError.BAD_COLUMN: If a text type data source has a column with no value.
            DataError.BAD_ROOT: If the root of the data source does not match the name.
            DataError.BAD_URL: If the data source is specified as a malformed URL.
        """
        match self.type:
            case SourceType.text:
                self._source = {}
                table_name: str = ''
                with open(self._connect_info, encoding=DEFAULT_ENCODING) as data_source:
                    for raw_line in data_source:
                        if (line := raw_line.strip()).startswith(self._TEXT_TABLE_DELIMITER):
                            self._source[(table_name := line.lstrip(self._TEXT_TABLE_DELIMITER))] = []
                            continue
                        row = {}
                        for pair in line.split(self._TEXT_TABLE_DELIMITER):
                            try:
                                (col, val) = pair.split(self._TEXT_VAL_DELIMITER)
                            except ValueError as err:
                                raise DataError(DataError.BAD_COLUMN, col=pair, line=line) from err
                            row[col] = val
                        self._source[table_name].append(row)
            case SourceType.pickle:
                with open(self._connect_info, encoding=DEFAULT_ENCODING) as data_source:
                    self._source = pickle_load(cast(IO[bytes], data_source))
            case SourceType.ini:
                self._source = RawConfigParser()
                with open(self._connect_info, encoding=DEFAULT_ENCODING) as ini_tmp:
                    self._source.read_file(ini_tmp)
            case SourceType.xml:
                if isinstance(self._connect_info, list):
                    self._connection = xml_etree.ElementTree(xml_etree.fromstring(' '.join(self._connect_info)))
                else:
                    if isinstance(self._connect_info, (str, PurePath)):
                        if str(self._connect_info).startswith('http:') or str(self._connect_info).startswith('file:'):
                            self._closer = urlopen(cast(str, self._connect_info))  # pylint: disable=consider-using-with
                        else:
                            self._closer = open(self._connect_info, encoding=DEFAULT_ENCODING)  # pylint: disable=consider-using-with
                    else:
                        self._closer = self._connect_info
                    try:
                        self._connection = xml_etree.parse(cast(bytes, self._closer))
                    except expat.ExpatError as err:
                        if expat.ErrorString(err.code) == expat.errors.XML_ERROR_SYNTAX:  # pylint: disable=no-member
                            raise DataError(DataError.BAD_URL, url=self._connect_info) from err
                        raise
                self._source = self._connection.getroot()
                if self._source.tag != self.name:
                    raise DataError(DataError.BAD_ROOT, source_name=self._connect_info, root_name=self._source.tag, expected=self.name)

    def _validate_schema(self) -> None:
        """Determine if the data source schema is valid.

        Returns:
            Nothing.

        Raises:
            DataError.BAD_SCHEMA: If the data source schema is invalid.
        """
        if self._schema != self.schema:
            raise DataError(DataError.BAD_SCHEMA, schema=self._schema, found=self.schema)

    def _validate_type(self) -> None:
        """Determine if the specified data source type is valid.

        Returns:
            Nothing.

        Raises:
            DataError.INVALID_TYPE: If the data source type is invalid.
        """
        if self.type not in SourceType:
            raise DataError(DataError.INVALID_TYPE)

    filename = property(lambda s: s._connect_info, doc='A read-only property which returns the file name of the data source.')
    name = property(lambda s: s._name, doc='A read-only property which returns the name of the data source.')
    type = property(lambda s: s._type, doc='A read-only property which returns the type of the data source.')

    @property
    def dict_repr(self) -> dict:
        """A read-only property which returns a the data source as a dictionary."""
        dict_repr = {}
        for table in self.get_tables():
            with table.get_rows()[0] as row:
                dict_repr[table.name] = {c: row.get_value(c) for c in row.get_columns()}
        return dict_repr

    @property
    def schema(self) -> int:
        """A read-only property which returns the schema value of the data source."""
        try:
            return int(self.get_table(self.INFO_TABLE).get_rows(col=self._SCHEMA_DATA)[0].get_value(self._SCHEMA_DATA))
        except IndexError:
            return 0
        except DataError as err:
            if err.code != DataError.BAD_TABLE.code:
                raise
            return 0

    def add_table(self, name: str, /) -> 'DataTable':
        """Create a new table with the specified name.

        Args:
            name: The name of the table to add.

        Returns:
            The created table.

        Raises:
            DataError.INVALID_OPERATION: If the data source type does not support adding a table.
        """
        match self.type:
            case SourceType.text | SourceType.pickle:
                self._source[name] = []
            case SourceType.ini:
                self._source.add_section(name)
                self._source.set(name, self.INI_ROW_LIST_OPT, '')
            case SourceType.xml:
                table = xml_etree.SubElement(self._source, self._XML_TABLE_TAG)
                table.attrib[self._XML_TABLE_NAME_ATTRIBUTE] = name
        return self.get_table(name)

    def close(self) -> None:
        """Close the data source.

        Returns:
            Nothing.
        """
        if self._closer:
            self._closer.close()
            self._connect_info = ''
            self._closer = self._source = self._connection = None

    def commit(self) -> None:
        """Commit any changes in memory to the source.

        Returns:
            Nothing.
        """
        match self.type:
            case SourceType.text:
                self._connection = open(self._connect_info, 'w', encoding=DEFAULT_ENCODING)  # pylint: disable=consider-using-with
                for (table_name, rows) in self._source.items():
                    self._connection.write(self._TEXT_TABLE_DELIMITER + table_name + '\n')
                    for row in rows:
                        self._connection.write(self._TEXT_TABLE_DELIMITER.join([f'{col}{self._TEXT_VAL_DELIMITER}{row[col]}' for col in row]) + '\n')
                self._connection.close()
            case SourceType.pickle:
                self._connection = open(self._connect_info, 'w', encoding=DEFAULT_ENCODING)  # pylint: disable=consider-using-with
                pickle_dump(self._source, cast(IO, self._connection))
                self._connection.close()
            case SourceType.ini:
                self._connection = open(self._connect_info, 'w', encoding=DEFAULT_ENCODING)  # pylint: disable=consider-using-with
                self._source.write(self._connection)
                self._connection.close()
            case SourceType.xml:
                cast(ElementTree, self._connection).write(cast(str, self._connect_info), 'ISO-8859-1')

    def get_table(self, name: str, /) -> 'DataTable':  # pylint: disable=too-many-branches
        """Get the requested data table.

        Args:
            name: The name of the table to return.

        Returns:
            The requested data table.

        Raises:
            DataError.BAD_TABLE: If the requested table is not found.
        """
        table = None
        match self.type:
            case SourceType.text | SourceType.pickle:
                if name in self._source:
                    table = self._source[name]
            case SourceType.ini:
                if self._source.has_section(name):
                    row_list = self._source.get(name, self.INI_ROW_LIST_OPT)
                    table = [int(r) for r in row_list.split(',')] if row_list else []
            case SourceType.xml:
                for tmp_table in self._source.iter(self._XML_TABLE_TAG):
                    if tmp_table.get(self._XML_TABLE_NAME_ATTRIBUTE) == name:
                        table = tmp_table
                        break
        if table is None:
            raise DataError(DataError.BAD_TABLE, table_name=name, source_name=self.name)
        return DataTable(self.type, name, table, self._source)

    def get_tables(self) -> List['DataTable']:
        """Get all the tables from the data source.

        Returns:
            The list of table in the data source.
        """
        table_names: List[str] = []
        match self.type:
            case SourceType.text | SourceType.pickle:
                table_names = [t for t in self._source]  # pylint: disable=unnecessary-comprehension
            case SourceType.ini:
                table_names = [t for t in self._source.sections() if self.INI_ROW_TAG not in t]
            case SourceType.xml:
                table_names = [t.get(self._XML_TABLE_NAME_ATTRIBUTE) for t in self._source.iter(self._XML_TABLE_TAG)]
        return [self.get_table(t) for t in table_names]

    def has_table(self, name: str, /) -> bool:
        """Determine if the named table exists in the data source.

        Args:
            name: The name of the table to search for.

        Returns:
            Returns True if the named table exists in the data source, False otherwise.
        """
        match self.type:
            case SourceType.text | SourceType.pickle:
                if name in self._source:
                    return True
            case SourceType.ini:
                if self._source.has_section(name):
                    return True
            case SourceType.xml:
                for tmp_table in self._source.iter(self._XML_TABLE_TAG):
                    if tmp_table.get(self._XML_TABLE_NAME_ATTRIBUTE) == name:
                        return True
        return False


class DataRow:
    """Class to create a universal abstract interface for a data row."""

    def __init__(self, data_type: SourceType, raw: Any, parent: Any, /):
        """
        Args:
            data_type: The data source type.
            raw: The raw value of the row as read from the data source.
            parent: This is a reference to the table containing the row.

        Attributes:
            _parent: The value of the parent argument.
            _row: The value of the raw argument.
            _type: The value of the data_type argument.
        """
        self._row = raw
        self._parent = parent
        self._type = data_type

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def __getattr__(self, attr: str) -> str:
        return self.get_value(attr)

    raw = property(lambda s: s._row, doc='A read-only property which returns the raw contents of the data row.')
    type = property(lambda s: s._type, doc='A read-only property which returns the type of the data source.')

    def del_column(self, col: str, ) -> None:
        """Delete the named column from the row.

        Args:
            col: The name of the column to delete.

        Returns:
            Nothing.
        """
        if not self.has_col(col):
            return

        match self.type:
            case SourceType.text | SourceType.pickle:
                del self._row[col]
            case SourceType.ini:
                self._parent.remove_option(col)
            case SourceType.xml:
                self._row.remove(self._row.find(col))

    def delete(self) -> None:
        """Delete this data row.

        Returns:
            Nothing.
        """
        match self.type:
            case SourceType.ini:
                self._parent.remove_section(self._row)
            case _:
                self._parent.remove(self._row)

    def get_columns(self) -> List[str]:
        """Get all the columns from the row.

        Returns:
            The list of columns in the data row.
        """
        match self.type:
            case SourceType.text | SourceType.pickle:
                return list(self._row.keys())
            case SourceType.ini:
                return self._parent.options(self._row)
            case SourceType.xml:
                return [e.tag for e in list(self._row) if e.tag != self._XML_ROW_TAG]
        return []

    def get_value(self, col: str, /) -> str:
        """Get the value of the specified column.

        Args:
            col: The name of the column from which to retrieve the value.

        Returns:
            The value of the column.
        """
        match self.type:
            case SourceType.text | SourceType.pickle:
                if self.has_col(col):
                    return self._row[col]
            case SourceType.ini:
                if self.has_col(col):
                    return self._parent.get(self._row, col)
            case SourceType.xml:
                return self._row.findtext(col)
        return ''

    def has_col(self, col: str, /) -> bool:  # pylint: disable=too-many-return-statements
        """Determine if the named column exists in the row.

        Args:
            col: The name of the column to search for.

        Returns:
            Returns True if the named column exists in the data source, False otherwise.
        """
        match self.type:
            case SourceType.text | SourceType.pickle:
                return col in self._row
            case SourceType.ini:
                return self._parent.has_option(self._row, col)
            case SourceType.xml:
                if self._row.find(col) is not None:
                    return True
                return False
        return False

    def setvalue(self, col: str, value: str, /) -> None:
        """Set the value of the specified column.

        Args:
            col: The name of the column for which to set the value.
            value: The value to set for the column.

        Returns:
            Nothing.
        """
        match self.type:
            case SourceType.text | SourceType.pickle:
                self._row[col] = value
            case SourceType.ini:
                self._parent.set(self._row, col, value)
            case SourceType.xml:
                col_ref = self._row.find(col)
                if col_ref is None:
                    col_ref = xml_etree.SubElement(self._row, col)
                col_ref.text = value


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

    def __init__(self, data_type: SourceType, name: str, raw: Any, parent: Any, /):
        """
        Args:
            data_type: The data source type.
            name: The table name.
            raw: The raw value of the table as read from the data source.
            parent: This is a reference to the data source containing the table.

        Attributes:
            _name: The value of the name argument.
            _parent: The value of the parent argument.
            _table: The value of the raw argument.
            _type: The value of the data_type argument.
        """
        self._name = name
        self._parent = parent
        self._table = raw
        self._type = data_type

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def _get_row_parent(self) -> Any:
        """Get the parent of a row in this table.

        Returns:
            The parent of a row in this table.
        """
        match self.type:
            case SourceType.text | SourceType.pickle | SourceType.xml:
                return self._table
            case SourceType.ini:
                return self._parent
        raise DataError(DataError.INVALID_TYPE)

    name = property(lambda s: s._name, doc='A read-only property which returns the name of the data table.')
    raw = property(lambda s: s._table, doc='A read-only property which returns the raw contents of the data table.')
    type = property(lambda s: s._type, doc='A read-only property which returns the type of the data source.')

    def add_row(self, **values) -> DataRow:
        """Create a new row with the specified values.

        Args:
            **values: A dictionary of the value to add.

        Returns:
            Nothing.
        """
        raw_row: Any = None
        match self.type:
            case SourceType.text | SourceType.pickle | SourceType.xml:
                row_num = (int(self._table[-1]) + 1) if self._table else 1
                self._parent.add_section(self._INI_ROW_FORMAT % (self.name, row_num))
                self._table.append(row_num)
                self._parent.set(self.name, DataSource.INI_ROW_LIST_OPT, ','.join([str(r) for r in self._table]))
                raw_row = self._INI_ROW_FORMAT % (self.name, row_num)
            case SourceType.xml:
                raw_row = xml_etree.SubElement(self._table, self._XML_ROW_TAG)
        row = DataRow(self.type, raw_row, self._get_row_parent())
        for (var, val) in values.items():
            row.setvalue(var, val)
        return row

    def del_row(self, col: str, value: str, /) -> None:
        """Delete the rows with the specified column value.

        Args:
            col: The column to select for.
            value: The column value to select for.

        Returns:
            Nothing.
        """
        for row in self.get_rows(col, value):
            row.delete()

    def get_rows(self, col: Optional[str] = None, value: Optional[str] = None) -> List[DataRow]:
        """Get all the rows matching the specified selector.

        Args:
            col (optional, default=None): The column to select for if not None.
            value (optional, default=None): The column value to select for if not None.

        Returns:
            The list of rows matching the specified selector.
        """
        row_list = self._table if self.type != SourceType.ini else [self._INI_ROW_FORMAT % (self.name, r) for r in self._table]
        all_rows = [DataRow(self.type, r, self._get_row_parent()) for r in row_list]
        if (col is None) and (value is None):
            return all_rows
        if value is None:
            return [r for r in all_rows if r.has_col(str(col))]
        return [r for r in all_rows if r.get_value(str(col)) == value]

# cSpell:ignore getiterator
