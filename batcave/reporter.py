'''Module for creating generic reports
    The simplest usage would be:
        report = reporter.Report('REPORT HEADER', 'REPORT FOOTER')

    To add a line to the report
        line = reporter.Line('a line')
        report.add_line(line)

    To add a section
        section1 = reporter.Section('Section 1 Header', 'Section 1 Footer')
        report.add_section(section1)

    To add a link
        link = reporter.Link('Link Text', 'URL')
        report.register_link(link)
        report.add_line(reporter.Line(f'Line with a {link} in it'))

    To add a list of links
        links = reporter.LinkList({'link1': 'http://link1', 'link2': 'http://link2'})
        report.register_link(links)
        report.add_line(reporter.Line(f'Line with {links}s in it'))

    A table is a list of lists with each outer list a row
    To add a table:
        rows = [['11', '12'], ['21', '22']]
        table = reporter.Table(rows, 'Table Header', 'Table Footer')
        report.add_table(table)

    To embed a link in a table
        link = reporter.Link('Table Text', 'http://table')
        report.register_link(link)
        rows = [['11', '12'], ['21', link]]
        table = reporter.Table(rows, 'Table Header', 'Table Footer')
        report.add_table(table)

    A simple report can be output with
        print(report)
'''

# Import standard modules
from copy import deepcopy
from enum import Enum


class SimpleAttribute:
    'This class defines an attribute type which has a default value and a list of valid values'
    def __init__(self, default, *other):
        self._value = default
        self._valid = list(other)
        self._valid.append(default)

    @property
    def value(self):
        'Returns the attribute value'
        return self._value

    @value.setter
    def value(self, val):
        'Sets the attribute value'
        if not self.is_valid(val):
            raise ValueError('invalid value for SimpleAttribute: ' + val)
        self._value = val
    count = property(lambda s: len(s._valid))

    def is_valid(self, val):
        'Determines if the specified attribute is valid'
        return val in self._valid


class MetaAttribute:
    'This class defines an attribute type which returns a value based on the value of a SimpleAttribute'
    def __init__(self, attr, **valmap):
        self._attr = attr
        self._valuemap = valmap

    def get_value(self, val):
        'Returns the value of an attribute'
        return self._valuemap[val]

    def _set_values(self, valmap):
        self._valuemap = valmap
    values = property(fset=_set_values)
    simple_attr_name = property(lambda s: s._attr)

# Attribute naming convention
#   Each attribute is made up of what it affects and where that effect takes place.
#       i.e. PART_PIECE_WHERE
#
#   Part abbreviations:
#       rpt = report
#       sec = section
#       tbl = table
#       lin = line
#       lnk = link
#       lst = list
#   Piece abbreviations:
#       hdr = header
#       bdy = body
#       row = DUH!
#       cel = cell
#       ftr = footer
#   Where abbreviations:
#       ldr = leader
#       int = interstitial
#       trm = terminator
#
# The report/section structure is
#   sec_ldr - header - body - footer - sec_trm
# where
#   header = sec_hdr_ldr - HEADER - sec_hdr_trm
#   body = sec_bdy_ldr - BODY - sec_bdy_trm
#   footer = sec_ftr_ldr - FOOTER - sec_ftr_trm
#
# The table structure is
#   tbl_ldr - header - body - footer - tbl_trm
# where the body is
#   tbl_bdy_ldr - rows - tbl_bdr_trm
# and rows are
#   tbl_row_ldr - cell - tbl_row_trm
# and cells are
#   tbl_cel_ldr - data - tbl_cel_trm
#
# The general line structure is:
#   lin_ldr - LINE - lin_trm
#
# The general list structure is:
#   lst_ldr - ITEM - lst_int ITEM - lst_trm
#


OUTPUT_ATTR = 'output'
RPT_LDR_ATTR = 'rpt_ldr'
RPT_TRM_ATTR = 'rpt_trm'
RPT_HDR_LDR_ATTR = 'rpt_hdr_ldr'
RPT_HDR_TRM_ATTR = 'rpt_hdr_trm'
RPT_BDY_LDR_ATTR = 'rpt_bdy_ldr'
RPT_BDY_TRM_ATTR = 'rpt_bdy_trm'
RPT_FTR_LDR_ATTR = 'rpt_ftr_ldr'
RPT_FTR_TRM_ATTR = 'rpt_ftr_trm'
SEC_LDR_ATTR = 'sec_ldr'
SEC_TRM_ATTR = 'sec_trm'
SEC_HDR_LDR_ATTR = 'sec_hdr_ldr'
SEC_HDR_TRM_ATTR = 'sec_hdr_trm'
SEC_BDY_LDR_ATTR = 'sec_bdy_ldr'
SEC_BDY_TRM_ATTR = 'sec_bdy_trm'
SEC_FTR_LDR_ATTR = 'sec_ftr_ldr'
SEC_FTR_TRM_ATTR = 'sec_ftr_trm'
TBL_LDR_ATTR = 'tbl_ldr'
TBL_TRM_ATTR = 'tbl_trm'
TBL_HDR_LDR_ATTR = 'tbl_hdr_ldr'
TBL_HDR_TRM_ATTR = 'tbl_hdr_trm'
TBL_BDY_LDR_ATTR = 'tbl_bdy_ldr'
TBL_BDY_TRM_ATTR = 'tbl_bdy_trm'
TBL_ROW_LDR_ATTR = 'tbl_row_ldr'
TBL_ROW_TRM_ATTR = 'tbl_row_trm'
TBL_CEL_LDR_ATTR = 'tbl_cel_ldr'
TBL_CEL_TRM_ATTR = 'tbl_cel_trm'
TBL_FTR_LDR_ATTR = 'tbl_ftr_ldr'
TBL_FTR_TRM_ATTR = 'tbl_ftr_trm'
LIN_LDR_ATTR = 'lin_ldr'
LIN_TRM_ATTR = 'lin_trm'
LNK_LDR_ATTR = 'lnk_ldr'
LNK_TRM_ATTR = 'lnk_trm'
LST_LDR_ATTR = 'lst_ldr'
LST_INT_ATTR = 'lst_int'
LST_TRM_ATTR = 'lst_trm'
_ATTRIBUTES = {OUTPUT_ATTR: SimpleAttribute('html', 'text'),
               RPT_LDR_ATTR: MetaAttribute(OUTPUT_ATTR, text='\n', html='<html><meta http-equiv="Content-Type" content="text/html;charset=utf-8"><body><center>'),
               RPT_TRM_ATTR: MetaAttribute(OUTPUT_ATTR, text='\n', html='</center></body></html>'),
               RPT_HDR_LDR_ATTR: MetaAttribute(OUTPUT_ATTR, text=('-'*79)+'\n', html='<h1>'),
               RPT_HDR_TRM_ATTR: MetaAttribute(OUTPUT_ATTR, text=('-'*79)+'\n', html='</h1>'),
               RPT_BDY_LDR_ATTR: MetaAttribute(OUTPUT_ATTR, text='', html=''),
               RPT_BDY_TRM_ATTR: MetaAttribute(OUTPUT_ATTR, text='', html=''),
               RPT_FTR_LDR_ATTR: MetaAttribute(OUTPUT_ATTR, text=('-'*79)+'\n', html=''),
               RPT_FTR_TRM_ATTR: MetaAttribute(OUTPUT_ATTR, text=('-'*79)+'\n', html=''),
               SEC_LDR_ATTR: MetaAttribute(OUTPUT_ATTR, text='', html=''),
               SEC_TRM_ATTR: MetaAttribute(OUTPUT_ATTR, text=('='*79)+'\n', html=''),
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
    'A base class for report objects'
    def __init__(self, cont=None, **attrs):
        self._attributes = dict()
        for (attr, val) in attrs.items():
            self._set_attribute(attr, val)
        self.container = cont

    @property
    def depth(self):
        'Get the depth of this report object'
        if self.container:
            return self.container.depth + 1
        return 1

    def _get_attr_ref(self, attr):
        if attr in self._attributes:
            return self._attributes[attr]
        if self.container:
            return self.container._get_attr_ref(attr)  # pylint: disable=W0212
        if attr in _ATTRIBUTES:
            return _ATTRIBUTES[attr]
        raise AttributeError(f"'{type(self)}' object has no attribute '{attr}'")

    def _get_attribute(self, attr):
        attr_ref = self._get_attr_ref(attr)
        if isinstance(attr_ref, MetaAttribute):
            sub_attr_ref = self._get_attr_ref(attr_ref.simple_attr_name)
            return attr_ref.get_value(sub_attr_ref.value)
        else:
            return attr_ref.value

    def _set_attribute(self, attr, val):
        if attr not in self._attributes:
            attr_ref = self._get_attr_ref(attr)
            self._attributes[attr] = deepcopy(attr_ref)
            if isinstance(attr_ref, MetaAttribute):
                self._attributes[attr].values = val
            else:
                self._attributes[attr].value = val

    output = property(lambda s: s._get_attribute(OUTPUT_ATTR), lambda s, v: s._set_attribute(OUTPUT_ATTR, v))
    rpt_ldr = property(lambda s: s._get_attribute(RPT_LDR_ATTR), lambda s, v: s._set_attribute(RPT_LDR_ATTR, v))
    rpt_trm = property(lambda s: s._get_attribute(RPT_TRM_ATTR), lambda s, v: s._set_attribute(RPT_TRM_ATTR, v))
    rpt_hdr_ldr = property(lambda s: s._get_attribute(RPT_HDR_LDR_ATTR), lambda s, v: s._set_attribute(RPT_HDR_LDR_ATTR, v))
    rpt_hdr_trm = property(lambda s: s._get_attribute(RPT_HDR_TRM_ATTR), lambda s, v: s._set_attribute(RPT_HDR_TRM_ATTR, v))
    rpt_bdy_ldr = property(lambda s: s._get_attribute(RPT_BDY_LDR_ATTR), lambda s, v: s._set_attribute(RPT_BDY_LDR_ATTR, v))
    rpt_bdy_trm = property(lambda s: s._get_attribute(RPT_BDY_TRM_ATTR), lambda s, v: s._set_attribute(RPT_BDY_TRM_ATTR, v))
    rpt_ftr_ldr = property(lambda s: s._get_attribute(RPT_FTR_LDR_ATTR), lambda s, v: s._set_attribute(RPT_FTR_LDR_ATTR, v))
    rpt_ftr_trm = property(lambda s: s._get_attribute(RPT_FTR_TRM_ATTR), lambda s, v: s._set_attribute(RPT_FTR_TRM_ATTR, v))
    sec_ldr = property(lambda s: s._get_attribute(SEC_LDR_ATTR), lambda s, v: s._set_attribute(SEC_LDR_ATTR, v))
    sec_trm = property(lambda s: s._get_attribute(SEC_TRM_ATTR), lambda s, v: s._set_attribute(SEC_TRM_ATTR, v))
    sec_hdr_ldr = property(lambda s: s._get_attribute(SEC_HDR_LDR_ATTR), lambda s, v: s._set_attribute(SEC_HDR_LDR_ATTR, v))
    sec_hdr_trm = property(lambda s: s._get_attribute(SEC_HDR_TRM_ATTR), lambda s, v: s._set_attribute(SEC_HDR_TRM_ATTR, v))
    sec_bdy_ldr = property(lambda s: s._get_attribute(SEC_BDY_LDR_ATTR), lambda s, v: s._set_attribute(SEC_BDY_LDR_ATTR, v))
    sec_bdy_trm = property(lambda s: s._get_attribute(SEC_BDY_TRM_ATTR), lambda s, v: s._set_attribute(SEC_BDY_TRM_ATTR, v))
    sec_ftr_ldr = property(lambda s: s._get_attribute(SEC_FTR_LDR_ATTR), lambda s, v: s._set_attribute(SEC_FTR_LDR_ATTR, v))
    sec_ftr_trm = property(lambda s: s._get_attribute(SEC_FTR_TRM_ATTR), lambda s, v: s._set_attribute(SEC_FTR_TRM_ATTR, v))
    tbl_ldr = property(lambda s: s._get_attribute(TBL_LDR_ATTR), lambda s, v: s._set_attribute(TBL_LDR_ATTR, v))
    tbl_trm = property(lambda s: s._get_attribute(TBL_TRM_ATTR), lambda s, v: s._set_attribute(TBL_TRM_ATTR, v))
    tbl_hdr_ldr = property(lambda s: s._get_attribute(TBL_HDR_LDR_ATTR), lambda s, v: s._set_attribute(TBL_HDR_LDR_ATTR, v))
    tbl_hdr_trm = property(lambda s: s._get_attribute(TBL_HDR_TRM_ATTR), lambda s, v: s._set_attribute(TBL_HDR_TRM_ATTR, v))
    tbl_bdy_ldr = property(lambda s: s._get_attribute(TBL_BDY_LDR_ATTR), lambda s, v: s._set_attribute(TBL_BDY_LDR_ATTR, v))
    tbl_bdy_trm = property(lambda s: s._get_attribute(TBL_BDY_TRM_ATTR), lambda s, v: s._set_attribute(TBL_BDY_TRM_ATTR, v))
    tbl_row_ldr = property(lambda s: s._get_attribute(TBL_ROW_LDR_ATTR), lambda s, v: s._set_attribute(TBL_ROW_LDR_ATTR, v))
    tbl_row_trm = property(lambda s: s._get_attribute(TBL_ROW_TRM_ATTR), lambda s, v: s._set_attribute(TBL_ROW_TRM_ATTR, v))
    tbl_cel_ldr = property(lambda s: s._get_attribute(TBL_CEL_LDR_ATTR), lambda s, v: s._set_attribute(TBL_CEL_LDR_ATTR, v))
    tbl_cel_trm = property(lambda s: s._get_attribute(TBL_CEL_TRM_ATTR), lambda s, v: s._set_attribute(TBL_CEL_TRM_ATTR, v))
    tbl_ftr_ldr = property(lambda s: s._get_attribute(TBL_FTR_LDR_ATTR), lambda s, v: s._set_attribute(TBL_FTR_LDR_ATTR, v))
    tbl_ftr_trm = property(lambda s: s._get_attribute(TBL_FTR_TRM_ATTR), lambda s, v: s._set_attribute(TBL_FTR_TRM_ATTR, v))
    lin_ldr = property(lambda s: s._get_attribute(LIN_LDR_ATTR), lambda s, v: s._set_attribute(LIN_LDR_ATTR, v))
    lin_trm = property(lambda s: s._get_attribute(LIN_TRM_ATTR), lambda s, v: s._set_attribute(LIN_TRM_ATTR, v))
    lnk_ldr = property(lambda s: s._get_attribute(LNK_LDR_ATTR), lambda s, v: s._set_attribute(LNK_LDR_ATTR, v))
    lnk_trm = property(lambda s: s._get_attribute(LNK_TRM_ATTR), lambda s, v: s._set_attribute(LNK_TRM_ATTR, v))
    lst_ldr = property(lambda s: s._get_attribute(LST_LDR_ATTR), lambda s, v: s._set_attribute(LST_LDR_ATTR, v))
    lst_int = property(lambda s: s._get_attribute(LST_INT_ATTR), lambda s, v: s._set_attribute(LST_INT_ATTR, v))
    lst_trm = property(lambda s: s._get_attribute(LST_TRM_ATTR), lambda s, v: s._set_attribute(LST_TRM_ATTR, v))


class Section(ReportObject):
    'A report section'
    def __init__(self, header='', footer='', cont=None, **attr):
        super().__init__(cont, **attr)
        self.header = header
        self.footer = footer
        self._members = list()

    def __str__(self):
        the_str = self.sec_ldr
        if self.header:
            the_str += self.sec_hdr_ldr + str(Line(self.header, self)) + self.sec_hdr_trm
        the_str += self.sec_bdy_ldr + ''.join([str(part) for part in self._members]) + self.sec_bdy_trm
        if self.footer:
            the_str += self.sec_ftr_ldr + str(Line(self.footer, self)) + self.sec_ftr_trm
        return the_str + self.sec_trm

    def add_member(self, thing):
        'Add a member to the section'
        self._members.append(thing)
        thing.container = self

    def add_section(self, section):
        'Add a sub-section to the section'
        self.add_member(section)

    def add_table(self, table):
        'Add a table to the section'
        self.add_member(table)

    def add_line(self, line):
        'Add a line to the section'
        self.add_member(line)

    def register_link(self, link):
        'Register a hyperlink'
        link.container = self


class Report(Section):
    'Top-level report container'
    def __str__(self):
        the_str = self.rpt_ldr
        if self.header:
            the_str += self.rpt_hdr_ldr + str(Line(self.header, self)) + self.rpt_hdr_trm
        the_str += self.rpt_bdy_ldr + ''.join([str(part) for part in self._members]) + self.rpt_bdy_trm
        if self.footer:
            the_str += self.rpt_ftr_ldr + str(Line(self.footer, self)) + self.rpt_ftr_trm
        return the_str + self.rpt_trm


class Cell(ReportObject):
    'A single cell in a table'
    def __init__(self, data, cont=None, **attr):
        super().__init__(cont, **attr)
        self._data = data

    def __str__(self):
        datastr = self._data
        if isinstance(self._data, int) or isinstance(self._data, list) or isinstance(self._data, tuple) or \
           isinstance(self._data, Enum) or isinstance(self._data, LinkList) or isinstance(self._data, Link) or not self._data:
            datastr = str(self._data)
        return self.tbl_cel_ldr + datastr + self.tbl_cel_trm


class Table(ReportObject):
    'A table in a report section'
    def __init__(self, data, header='', footer='', **attr):
        super().__init__(**attr)
        self.header = header
        self.footer = footer
        self._data = data

    def __str__(self):
        if self.output == 'text':
            col_widths = list()
            for row in self._data:
                i = 0
                for col in row:
                    if (i+1) > len(col_widths):
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
                    colpad = ' ' * int((col_widths[i] - len(col))/2)
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
    'A single line in a report section'
    def __init__(self, text, cont=None, **attr):
        super().__init__(cont, **attr)
        self._text = text

    def __str__(self):
        return self.lin_ldr + self._text + self.lin_trm


class Link(ReportObject):
    'A hyperlink in a line or cell'
    def __init__(self, text, url=None, cont=None, **attr):
        super().__init__(cont, **attr)
        self._text = text
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
    'A link of links'
    def __init__(self, urls, cont=None, **attr):
        super().__init__(cont, **attr)
        self._list = list()
        for key in sorted(urls.keys()):
            link = Link(key, urls[key])
            self.register_link(link)
            self._list.append(link)

    def __str__(self):
        return self.lst_int.join([str(item) for item in self._list])
