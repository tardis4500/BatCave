"""This module provides utilities for creating reports.

Examples:
    The simplest usage would be::

        report = reporter.Report('REPORT HEADER', 'REPORT FOOTER')

    To add a line to the report::

        line = reporter.Line('a line')
        report.add_line(line)

    To add a section::

        section1 = reporter.Section('Section 1 Header', 'Section 1 Footer')
        report.add_section(section1)

    To add a link::

        link = reporter.Link('Link Text', 'URL')
        report.register_link(link)
        report.add_line(reporter.Line(f'Line with a {link} in it'))

    To add a list of links::

        links = reporter.LinkList({'link1': 'http://link1', 'link2': 'http://link2'})
        report.register_link(links)
        report.add_line(reporter.Line(f'Line with {links}s in it'))

    A table is a list of lists with each outer list a row

    To add a table::

        rows = [['11', '12'], ['21', '22']]
        table = reporter.Table(rows, 'Table Header', 'Table Footer')
        report.add_table(table)

    To embed a link in a table::

        link = reporter.Link('Table Text', 'http://table')
        report.register_link(link)
        rows = [['11', '12'], ['21', link]]
        table = reporter.Table(rows, 'Table Header', 'Table Footer')
        report.add_table(table)

    A simple report can be output with::

        print(report)

Attributes:
    Each attribute is made up of what it affects and where that effect takes place.
        i.e. PART_PIECE_WHERE

    Part abbreviations:
        rpt = report
        sec = section
        tbl = table
        lin = line
        lnk = link
        lst = list
    Piece abbreviations:
        hdr = header
        bdy = body
        row = DUH!
        cel = cell
        ftr = footer
    Where abbreviations:
        ldr = leader
        int = interstitial
        trm = terminator

    The report/section structure is
    sec_ldr - header - body - footer - sec_trm
    where
    header = sec_hdr_ldr - HEADER - sec_hdr_trm
    body = sec_bdy_ldr - BODY - sec_bdy_trm
    footer = sec_ftr_ldr - FOOTER - sec_ftr_trm

    The table structure is
    tbl_ldr - header - body - footer - tbl_trm
    where the body is
    tbl_bdy_ldr - rows - tbl_bdr_trm
    and rows are
    tbl_row_ldr - cell - tbl_row_trm
    and cells are
    tbl_cel_ldr - data - tbl_cel_trm

    The general line structure is:
    lin_ldr - LINE - lin_trm

    The general list structure is:
    lst_ldr - ITEM - lst_int ITEM - lst_trm
"""

# Import standard modules
from copy import deepcopy
from enum import Enum
from typing import cast, Dict, List, Optional, Type, Union

LIN_LDR_ATTR = 'lin_ldr'
LIN_TRM_ATTR = 'lin_trm'
LNK_LDR_ATTR = 'lnk_ldr'
LNK_TRM_ATTR = 'lnk_trm'
LST_INT_ATTR = 'lst_int'
LST_LDR_ATTR = 'lst_ldr'
LST_TRM_ATTR = 'lst_trm'
OUTPUT_ATTR = 'output'
RPT_BDY_LDR_ATTR = 'rpt_bdy_ldr'
RPT_BDY_TRM_ATTR = 'rpt_bdy_trm'
RPT_FTR_LDR_ATTR = 'rpt_ftr_ldr'
RPT_FTR_TRM_ATTR = 'rpt_ftr_trm'
RPT_HDR_LDR_ATTR = 'rpt_hdr_ldr'
RPT_HDR_TRM_ATTR = 'rpt_hdr_trm'
RPT_LDR_ATTR = 'rpt_ldr'
RPT_TRM_ATTR = 'rpt_trm'
SEC_BDY_LDR_ATTR = 'sec_bdy_ldr'
SEC_BDY_TRM_ATTR = 'sec_bdy_trm'
SEC_FTR_LDR_ATTR = 'sec_ftr_ldr'
SEC_FTR_TRM_ATTR = 'sec_ftr_trm'
SEC_HDR_LDR_ATTR = 'sec_hdr_ldr'
SEC_HDR_TRM_ATTR = 'sec_hdr_trm'
SEC_LDR_ATTR = 'sec_ldr'
SEC_TRM_ATTR = 'sec_trm'
TBL_BDY_LDR_ATTR = 'tbl_bdy_ldr'
TBL_BDY_TRM_ATTR = 'tbl_bdy_trm'
TBL_CEL_LDR_ATTR = 'tbl_cel_ldr'
TBL_CEL_TRM_ATTR = 'tbl_cel_trm'
TBL_FTR_LDR_ATTR = 'tbl_ftr_ldr'
TBL_FTR_TRM_ATTR = 'tbl_ftr_trm'
TBL_HDR_LDR_ATTR = 'tbl_hdr_ldr'
TBL_HDR_TRM_ATTR = 'tbl_hdr_trm'
TBL_LDR_ATTR = 'tbl_ldr'
TBL_TRM_ATTR = 'tbl_trm'
TBL_ROW_LDR_ATTR = 'tbl_row_ldr'
TBL_ROW_TRM_ATTR = 'tbl_row_trm'


class SimpleAttribute:
    """Class to create a universal abstract interface for a report attribute which has a default value and a list of valid values."""

    def __init__(self, default: str, /, *other):
        """
        Args:
            default: The default value of the attribute.
            other (optional): a list of other allowed values.

        Attributes:
            _valid: The value of the other argument with default appended to the list.
            _value: The value of the default argument.
        """
        self._value = default
        self._valid = list(other)
        self._valid.append(default)

    count = property(lambda s: len(s._valid), doc='A read-only property which returns the number of valid attribute values.')

    @property
    def value(self) -> str:
        """A read-write property which returns and sets the value of the attribute."""
        return self._value

    @value.setter
    def value(self, val: str, /) -> None:
        if not self.is_valid(val):
            raise ValueError('invalid value for SimpleAttribute: ' + val)
        self._value = val

    def is_valid(self, attr: str, /) -> bool:
        """Determine if the specified attribute is valid.

        Args:
            attr: The attribute to validate.

        Returns:
            True if the attribute it valid, False otherwise.
        """
        return attr in self._valid


class MetaAttribute:
    """Class to create a universal abstract interface for a report attribute which returns a value based on the value of a SimpleAttribute."""

    def __init__(self, attr: str, /, **valmap):
        """
        Args:
            attr: The attribute.
            valmap (optional): a dictionary of other allowed values.

        Attributes:
            _attr: The value of the attr argument.
            _valuemap: The value of the valmap argument.
        """
        self._attr = attr
        self._valuemap = valmap

    def _set_values(self, valmap: Dict[str, str], /) -> None:
        """Set the value of a collection of attributes.

        Args:
            valmap: The collection of attributes to set.

        Returns:
            Nothing.
        """
        self._valuemap = valmap

    simple_attr_name = property(lambda s: s._attr, doc='A read-only property which returns the simple attribute name.')
    values = property(fset=_set_values, doc='A read-only property which returns the values of the attribute as a dictionary.')

    def get_value(self, attr: str, /) -> str:
        """Get the value of an attribute.

        Args:
            attr: The attribute for which to return the value.

        Returns:
            The value of the attribute.
        """
        return self._valuemap[attr]


Attribute = Union[SimpleAttribute, MetaAttribute]

_ATTRIBUTES = {OUTPUT_ATTR: SimpleAttribute('html', 'text'),
               RPT_LDR_ATTR: MetaAttribute(OUTPUT_ATTR, text='\n', html='<html><meta http-equiv="Content-Type" content="text/html;charset=utf-8"><body><center>'),
               RPT_TRM_ATTR: MetaAttribute(OUTPUT_ATTR, text='\n', html='</center></body></html>'),
               RPT_HDR_LDR_ATTR: MetaAttribute(OUTPUT_ATTR, text=('-' * 79) + '\n', html='<h1>'),
               RPT_HDR_TRM_ATTR: MetaAttribute(OUTPUT_ATTR, text=('-' * 79) + '\n', html='</h1>'),
               RPT_BDY_LDR_ATTR: MetaAttribute(OUTPUT_ATTR, text='', html=''),
               RPT_BDY_TRM_ATTR: MetaAttribute(OUTPUT_ATTR, text='', html=''),
               RPT_FTR_LDR_ATTR: MetaAttribute(OUTPUT_ATTR, text=('-' * 79) + '\n', html=''),
               RPT_FTR_TRM_ATTR: MetaAttribute(OUTPUT_ATTR, text=('-' * 79) + '\n', html=''),
               SEC_LDR_ATTR: MetaAttribute(OUTPUT_ATTR, text='', html=''),
               SEC_TRM_ATTR: MetaAttribute(OUTPUT_ATTR, text=('=' * 79) + '\n', html=''),
               SEC_HDR_LDR_ATTR: MetaAttribute(OUTPUT_ATTR, text='', html='<h2>'),
               SEC_HDR_TRM_ATTR: MetaAttribute(OUTPUT_ATTR, text='', html='</h2>'),
               SEC_BDY_LDR_ATTR: MetaAttribute(OUTPUT_ATTR, text='', html=''),
               SEC_BDY_TRM_ATTR: MetaAttribute(OUTPUT_ATTR, text='', html=''),
               SEC_FTR_LDR_ATTR: MetaAttribute(OUTPUT_ATTR, text='', html=''),
               SEC_FTR_TRM_ATTR: MetaAttribute(OUTPUT_ATTR, text='', html=''),
               TBL_LDR_ATTR: MetaAttribute(OUTPUT_ATTR, text='', html='<table border="1">'),
               TBL_TRM_ATTR: MetaAttribute(OUTPUT_ATTR, text='', html='</table><br>'),
               TBL_HDR_LDR_ATTR: MetaAttribute(OUTPUT_ATTR, text='', html='<td colspan="2" align="center"><h2>'),
               TBL_HDR_TRM_ATTR: MetaAttribute(OUTPUT_ATTR, text='\n', html='</h2></td>'),
               TBL_BDY_LDR_ATTR: MetaAttribute(OUTPUT_ATTR, text='', html=''),
               TBL_BDY_TRM_ATTR: MetaAttribute(OUTPUT_ATTR, text='', html=''),
               TBL_ROW_LDR_ATTR: MetaAttribute(OUTPUT_ATTR, text='|', html='<tr>'),
               TBL_ROW_TRM_ATTR: MetaAttribute(OUTPUT_ATTR, text='\n', html='</tr>'),
               TBL_CEL_LDR_ATTR: MetaAttribute(OUTPUT_ATTR, text=' ', html='<td>'),
               TBL_CEL_TRM_ATTR: MetaAttribute(OUTPUT_ATTR, text=' |', html='</td>'),
               TBL_FTR_LDR_ATTR: MetaAttribute(OUTPUT_ATTR, text='', html='<td colspan="2" align="center"><h2>'),
               TBL_FTR_TRM_ATTR: MetaAttribute(OUTPUT_ATTR, text='\n', html='</h2></td>'),
               LIN_LDR_ATTR: MetaAttribute(OUTPUT_ATTR, text='', html=''),
               LIN_TRM_ATTR: MetaAttribute(OUTPUT_ATTR, text='\n', html='<br>'),
               LNK_LDR_ATTR: MetaAttribute(OUTPUT_ATTR, text='', html='<a href="%s">'),
               LNK_TRM_ATTR: MetaAttribute(OUTPUT_ATTR, text='', html='</a>'),
               LST_LDR_ATTR: MetaAttribute(OUTPUT_ATTR, text='', html=''),
               LST_INT_ATTR: MetaAttribute(OUTPUT_ATTR, text=', ', html=', '),
               LST_TRM_ATTR: MetaAttribute(OUTPUT_ATTR, text='', html='')}


class ReportObject:
    """Class to create a universal abstract interface for a report object."""

    def __init__(self, container: Optional[Type['ReportObject']] = None, /, **attributes):
        """
        Args:
            container: The container for this object.
            **attributes (optional): A dictionary of attributes for the object.

        Attributes:
            container: The value of the container argument.
            _attributes: A dictionary of attributes for this object as initialized by the attr argument.
        """
        self._attributes: Dict[str, Attribute] = dict()
        for (attr, val) in attributes.items():
            self._set_attribute(attr, val)
        self.container: Optional[Type[ReportObject]] = container

    def _get_attr_ref(self, attr: str, /) -> Attribute:
        """Get a reference to the requested attributes.

        Args:
            attr: The attribute for which to return the reference.

        Returns:
            A reference to the requested attribute.

        Raises:
            AttributeError: If the requested attribute is not found.
        """
        if attr in self._attributes:
            return self._attributes[attr]
        if self.container:
            return cast('ReportObject', self.container)._get_attr_ref(attr)  # pylint: disable=protected-access
        if attr in _ATTRIBUTES:
            return cast(Attribute, _ATTRIBUTES[attr])
        raise AttributeError(f"'{type(self)}' object has no attribute '{attr}'")

    def _get_attribute(self, attr: str, /) -> str:
        """Get the value of the requested attributes.

        Args:
            attr: The attribute for which to return the value.

        Returns:
            A value of the requested attribute.
        """
        if isinstance((attr_ref := self._get_attr_ref(attr)), MetaAttribute):
            sub_attr_ref = cast(SimpleAttribute, self._get_attr_ref(attr_ref.simple_attr_name))
            return attr_ref.get_value(sub_attr_ref.value)
        return attr_ref.value

    def _set_attribute(self, attr: str, val: str, /) -> None:
        """Set the value of the requested attributes.

        Args:
            attr: The attribute for which to set the value.
            val: The value to which to set the attribute.

        Returns:
            Nothing.
        """
        if attr not in self._attributes:
            self._attributes[attr] = deepcopy(self._get_attr_ref(attr))
            if isinstance(self._attributes[attr], MetaAttribute):
                cast(MetaAttribute, self._attributes[attr]).values = val
            else:
                cast(SimpleAttribute, self._attributes[attr]).value = val

    lin_ldr = property(lambda s: s._get_attribute(LIN_LDR_ATTR), lambda s, v: s._set_attribute(LIN_LDR_ATTR, v), doc='A read-write property for the line leader attribute.')
    lin_trm = property(lambda s: s._get_attribute(LIN_TRM_ATTR), lambda s, v: s._set_attribute(LIN_TRM_ATTR, v), doc='A read-write property for the line terminator attribute.')
    lnk_ldr = property(lambda s: s._get_attribute(LNK_LDR_ATTR), lambda s, v: s._set_attribute(LNK_LDR_ATTR, v), doc='A read-write property for the link leader attribute.')
    lnk_trm = property(lambda s: s._get_attribute(LNK_TRM_ATTR), lambda s, v: s._set_attribute(LNK_TRM_ATTR, v), doc='A read-write property for the link terminator attribute.')
    lst_int = property(lambda s: s._get_attribute(LST_INT_ATTR), lambda s, v: s._set_attribute(LST_INT_ATTR, v), doc='A read-write property for the list separator attribute.')
    lst_ldr = property(lambda s: s._get_attribute(LST_LDR_ATTR), lambda s, v: s._set_attribute(LST_LDR_ATTR, v), doc='A read-write property for the list leader attribute.')
    lst_trm = property(lambda s: s._get_attribute(LST_TRM_ATTR), lambda s, v: s._set_attribute(LST_TRM_ATTR, v), doc='A read-write property for the list terminator attribute.')
    output = property(lambda s: s._get_attribute(OUTPUT_ATTR), lambda s, v: s._set_attribute(OUTPUT_ATTR, v), doc='A read-write property for the output attribute.')
    rpt_bdy_ldr = property(lambda s: s._get_attribute(RPT_BDY_LDR_ATTR), lambda s, v: s._set_attribute(RPT_BDY_LDR_ATTR, v), doc='A read-write property for the report body leader attribute.')
    rpt_bdy_trm = property(lambda s: s._get_attribute(RPT_BDY_TRM_ATTR), lambda s, v: s._set_attribute(RPT_BDY_TRM_ATTR, v), doc='A read-write property for the report body terminator attribute.')
    rpt_ftr_ldr = property(lambda s: s._get_attribute(RPT_FTR_LDR_ATTR), lambda s, v: s._set_attribute(RPT_FTR_LDR_ATTR, v), doc='A read-write property for the report footer leader attribute.')
    rpt_ftr_trm = property(lambda s: s._get_attribute(RPT_FTR_TRM_ATTR), lambda s, v: s._set_attribute(RPT_FTR_TRM_ATTR, v), doc='A read-write property for the report footer terminator attribute.')
    rpt_hdr_ldr = property(lambda s: s._get_attribute(RPT_HDR_LDR_ATTR), lambda s, v: s._set_attribute(RPT_HDR_LDR_ATTR, v), doc='A read-write property for the report header leader attribute.')
    rpt_hdr_trm = property(lambda s: s._get_attribute(RPT_HDR_TRM_ATTR), lambda s, v: s._set_attribute(RPT_HDR_TRM_ATTR, v), doc='A read-write property for the report header terminator attribute.')
    rpt_ldr = property(lambda s: s._get_attribute(RPT_LDR_ATTR), lambda s, v: s._set_attribute(RPT_LDR_ATTR, v), doc='A read-write property for the report leader attribute.')
    rpt_trm = property(lambda s: s._get_attribute(RPT_TRM_ATTR), lambda s, v: s._set_attribute(RPT_TRM_ATTR, v), doc='A read-write property for the report terminator attribute.')
    sec_bdy_ldr = property(lambda s: s._get_attribute(SEC_BDY_LDR_ATTR), lambda s, v: s._set_attribute(SEC_BDY_LDR_ATTR, v), doc='A read-write property for the section body leader attribute.')
    sec_bdy_trm = property(lambda s: s._get_attribute(SEC_BDY_TRM_ATTR), lambda s, v: s._set_attribute(SEC_BDY_TRM_ATTR, v), doc='A read-write property for the section body terminator attribute.')
    sec_ftr_ldr = property(lambda s: s._get_attribute(SEC_FTR_LDR_ATTR), lambda s, v: s._set_attribute(SEC_FTR_LDR_ATTR, v), doc='A read-write property for the section footer leader attribute.')
    sec_ftr_trm = property(lambda s: s._get_attribute(SEC_FTR_TRM_ATTR), lambda s, v: s._set_attribute(SEC_FTR_TRM_ATTR, v), doc='A read-write property for the section footer terminator attribute.')
    sec_hdr_ldr = property(lambda s: s._get_attribute(SEC_HDR_LDR_ATTR), lambda s, v: s._set_attribute(SEC_HDR_LDR_ATTR, v), doc='A read-write property for the section header leader attribute.')
    sec_hdr_trm = property(lambda s: s._get_attribute(SEC_HDR_TRM_ATTR), lambda s, v: s._set_attribute(SEC_HDR_TRM_ATTR, v), doc='A read-write property for the section header terminator attribute.')
    sec_ldr = property(lambda s: s._get_attribute(SEC_LDR_ATTR), lambda s, v: s._set_attribute(SEC_LDR_ATTR, v), doc='A read-write property for the section leader attribute.')
    sec_trm = property(lambda s: s._get_attribute(SEC_TRM_ATTR), lambda s, v: s._set_attribute(SEC_TRM_ATTR, v), doc='A read-write property for the section terminator attribute.')
    tbl_bdy_ldr = property(lambda s: s._get_attribute(TBL_BDY_LDR_ATTR), lambda s, v: s._set_attribute(TBL_BDY_LDR_ATTR, v), doc='A read-write property for the table body leader attribute.')
    tbl_bdy_trm = property(lambda s: s._get_attribute(TBL_BDY_TRM_ATTR), lambda s, v: s._set_attribute(TBL_BDY_TRM_ATTR, v), doc='A read-write property for the table body terminator attribute.')
    tbl_cel_ldr = property(lambda s: s._get_attribute(TBL_CEL_LDR_ATTR), lambda s, v: s._set_attribute(TBL_CEL_LDR_ATTR, v), doc='A read-write property for the table cell leader attribute.')
    tbl_cel_trm = property(lambda s: s._get_attribute(TBL_CEL_TRM_ATTR), lambda s, v: s._set_attribute(TBL_CEL_TRM_ATTR, v), doc='A read-write property for the table cell terminator attribute.')
    tbl_ftr_ldr = property(lambda s: s._get_attribute(TBL_FTR_LDR_ATTR), lambda s, v: s._set_attribute(TBL_FTR_LDR_ATTR, v), doc='A read-write property for the table footer leader attribute.')
    tbl_ftr_trm = property(lambda s: s._get_attribute(TBL_FTR_TRM_ATTR), lambda s, v: s._set_attribute(TBL_FTR_TRM_ATTR, v), doc='A read-write property for the table footer terminator attribute.')
    tbl_hdr_ldr = property(lambda s: s._get_attribute(TBL_HDR_LDR_ATTR), lambda s, v: s._set_attribute(TBL_HDR_LDR_ATTR, v), doc='A read-write property for the table header leader attribute.')
    tbl_hdr_trm = property(lambda s: s._get_attribute(TBL_HDR_TRM_ATTR), lambda s, v: s._set_attribute(TBL_HDR_TRM_ATTR, v), doc='A read-write property for the table header terminator attribute.')
    tbl_ldr = property(lambda s: s._get_attribute(TBL_LDR_ATTR), lambda s, v: s._set_attribute(TBL_LDR_ATTR, v), doc='A read-write property for the table leader attribute.')
    tbl_trm = property(lambda s: s._get_attribute(TBL_TRM_ATTR), lambda s, v: s._set_attribute(TBL_TRM_ATTR, v), doc='A read-write property for the table terminator attribute.')
    tbl_row_ldr = property(lambda s: s._get_attribute(TBL_ROW_LDR_ATTR), lambda s, v: s._set_attribute(TBL_ROW_LDR_ATTR, v), doc='A read-write property for the table row leader attribute.')
    tbl_row_trm = property(lambda s: s._get_attribute(TBL_ROW_TRM_ATTR), lambda s, v: s._set_attribute(TBL_ROW_TRM_ATTR, v), doc='A read-write property for the table row terminator attribute.')

    @property
    def depth(self) -> int:
        """A read-only property which returns the report depth of this object."""
        if self.container:
            return cast(ReportObject, self.container).depth + 1
        return 1


class Section(ReportObject):
    """Class to create a universal abstract interface for a report section."""

    def __init__(self, /, *, header: str = '', footer: str = '', cont: Optional[Type[ReportObject]] = None, **attr):
        """
        Args:
            header (optional, default=''): The section header.
            footer (optional, default=''): The section footer.
            cont: The container for this section.
            attr (optional): A dictionary of attributes for the section.

        Attributes:
            footer: The value of the footer argument.
            header: The value of the header argument.
            _members: A list of objects contained in this section.
        """
        super().__init__(cont, **attr)
        self.header = header
        self.footer = footer
        self._members: List[Type[ReportObject]] = list()

    def __str__(self):
        the_str = self.sec_ldr
        if self.header:
            the_str += self.sec_hdr_ldr + str(Line(self.header, self)) + self.sec_hdr_trm
        the_str += self.sec_bdy_ldr + ''.join([str(part) for part in self._members]) + self.sec_bdy_trm
        if self.footer:
            the_str += self.sec_ftr_ldr + str(Line(self.footer, self)) + self.sec_ftr_trm
        return the_str + self.sec_trm

    def add_line(self, line: Type['Line'], /) -> None:
        """Add a line to the section.

        Args:
            line: The line to add to the section.

        Returns:
            Nothing.
        """
        self.add_member(line)

    def add_member(self, thing: Type[ReportObject], /) -> None:
        """Add a member to the section.

        Args:
            thing: The member to add to the section.

        Returns:
            Nothing.
        """
        self._members.append(thing)
        thing.container = cast(Type[ReportObject], self)

    def add_section(self, section: Type['Section'], /) -> None:
        """Add a sub-section to the section.

        Args:
            setion: The sub-section to add to the section.

        Returns:
            Nothing.
        """
        self.add_member(section)

    def add_table(self, table: Type['Table'], /) -> None:
        """Add a table to the section.

        Args:
            table: The table to add to the section.

        Returns:
            Nothing.
        """
        self.add_member(table)

    def register_link(self, link: 'Link', /) -> None:
        """Register a hyperlink in the section.

        Args:
            link: The hyperlink to register.

        Returns:
            Nothing.
        """
        link.container = cast(Type[ReportObject], self)


class Report(Section):
    """Class to create a universal abstract interface for a report."""

    def __str__(self):
        the_str = self.rpt_ldr
        if self.header:
            the_str += self.rpt_hdr_ldr + str(Line(self.header, self)) + self.rpt_hdr_trm
        the_str += self.rpt_bdy_ldr + ''.join([str(part) for part in self._members]) + self.rpt_bdy_trm
        if self.footer:
            the_str += self.rpt_ftr_ldr + str(Line(self.footer, self)) + self.rpt_ftr_trm
        return the_str + self.rpt_trm


class Cell(ReportObject):
    """Class to create a universal abstract interface for a cell in a table in a report."""

    def __init__(self, data: str, cont: Optional[Type[ReportObject]] = None, /, **attr):
        """
        Args:
            data: The cell data.
            cont (optional, default=None): The container for this cell.
            attr (optional): A dictionary of attributes for the cell.

        Attributes:
            _data: The value of the data argument.
        """
        super().__init__(cont, **attr)
        self._data = data

    def __str__(self):
        datastr = self._data
        if isinstance(self._data, (int, list, tuple, Enum, LinkList, Link)) or not self._data:
            datastr = str(self._data)
        return self.tbl_cel_ldr + datastr + self.tbl_cel_trm


class Table(ReportObject):
    """Class to create a universal abstract interface for a report section table."""

    def __init__(self, data: str, /, *, header: str = '', footer: str = '', **attr):
        """
        Args:
            data: The table data.
            header (optional, default=''): The table header.
            footer (optional, default=''): The table footer.
            attr (optional): A dictionary of attributes for the table.

        Attributes:
            footer: The value of the footer argument.
            header: The value of the header argument.
            _data: The value of the data argument.
        """
        super().__init__(**attr)
        self.header = header
        self.footer = footer
        self._data = data

    def __str__(self):
        col_widths = list()
        if self.output == 'text':
            for row in self._data:
                i = 0
                for col in row:
                    if (i + 1) > len(col_widths):
                        col_widths.append(0)
                    col_widths[i] = max(col_widths[i], len(col))
                    i += 1

        the_str = self.tbl_ldr
        if self.header:
            the_str += self.tbl_hdr_ldr + self.header + self.tbl_hdr_trm
        the_str += self.tbl_bdy_ldr
        for row in self._data:
            the_str += self.tbl_row_ldr
            i = 0
            for col in row:
                if self.output == 'text':
                    colpad = ' ' * int((col_widths[i] - len(col)) / 2)
                    col_str = colpad + col + colpad
                    col_str += ' ' * (col_widths[i] - len(col_str))
                else:
                    col_str = col
                the_str += str(Cell(col_str, self))
                i += 1
            the_str += self.tbl_row_trm
        the_str += self.tbl_bdy_trm
        if self.footer:
            the_str += self.tbl_ftr_ldr + self.footer + self.tbl_ftr_trm
        return the_str + self.tbl_trm


class Line(ReportObject):
    """Class to create a universal abstract interface for a report section line."""

    def __init__(self, text: str, cont: Optional[Type[ReportObject]] = None, /, **attr):
        """
        Args:
            text: The line text.
            cont (optional, default=None): The container for this line.
            attr (optional): A dictionary of attributes for the line.

        Attributes:
            _text: The value of the text argument.
        """
        super().__init__(cont, **attr)
        self._text = text

    def __str__(self):
        return self.lin_ldr + self._text + self.lin_trm


class Link(Line):
    """Class to create a universal abstract interface for a report hyperlink."""

    def __init__(self, text: str, /, url: str = '', cont: Optional[Type[ReportObject]] = None, **attr):
        """
        Args:
            text: The link text.
            url (optional, default=None): The link URL.
            cont (optional, default=None): The container for this link.
            attr (optional): A dictionary of attributes for the link.

        Attributes:
            _url: The value of the url argument.
        """
        super().__init__(text, cont, **attr)
        self._url = url

    def __str__(self):
        try:
            url = (self.lnk_ldr % self._url)
        except TypeError as err:
            if 'not all arguments converted during string formatting' not in str(err):
                raise
            url = self.lnk_ldr
        return url + self._text + self.lnk_trm


class LinkList(Section):
    """Class to create a universal abstract interface for a list of hyperlinks in a report."""

    def __init__(self, urls: Dict[str, str], cont: Optional[Type[ReportObject]] = None, /, **attr):
        """
        Args:
            urls: The list of URLs the section.
            cont (optional, default=None): The container for this section.
            attr (optional): A dictionary of attributes for the section.

        Attributes:
            _list: The value of the urls argument converted into links.
        """
        super().__init__(cont=cont, **attr)
        self._list = list()
        for key in sorted(urls.keys()):
            self.register_link(link := Link(key, urls[key]))
            self._list.append(link)

    def __str__(self):
        return self.lst_int.join([str(item) for item in self._list])
