''' An instantiation of this class will convert an XML into the procedure object

    <procedure schema = "{schema-version}" >
        <header>HEADER</header>

        <flags>
            <FlagName question="Some Question">True|False, Yes|No,  1,0</FlagName>
        </flags>

        <environments>
            <common>
                <VariableName1>Variable Value 1</VariableName1>
            </common>
            <Environment1>
                <VariableName2>Variable Value 2</VariableName1>
            <Environment2
        </environments>

        <directories>
            <directory>Directory - Path</directory>
        </directories>

        <steps>
            <step condition="Optional Condition Expression" vars="var1=val1, var2=val2", repeat="var=val1, val2">
                "Multi-Step Text"
                <step>Step Text</step>
                <step import="Library Step Name">Alternate Step Text</step>
            </step>
        </steps>

        <step-library>
            <step name="Import Name" />
        </step-library>
    </procedure>
'''
# cSpell:ignore odict

# Import standard modules
from collections import OrderedDict as odict
from copy import deepcopy
from enum import Enum
from os import walk
from pathlib import Path
from re import compile as re_compile
from shutil import copyfile
from string import Template
from xml.etree.ElementTree import fromstringlist as xmlparse

# Import BatCave packages
from .fileutil import slurp
from .lang import is_debug, str_to_pythonval, switch, HALError, HALException, WIN32


class FormatterError(HALException):
    'Formatter Exceptions'
    BAD_FORMAT = HALError(1, Template('Unknown output format requested: $format'))


class ItemError(HALException):
    'Item Exceptions'
    MISSING_ATTRIBUTE = HALError(1, Template('$attr'))


class ExpanderError(HALException):
    'Expander Exceptions'
    NO_POST_DELIMITER = HALError(1, Template('No closing delimiter found in $substr'))
    NO_VARIABLE = HALError(2, Template('No replacement found for variable ($var) in: $thing'))


class ProcedureError(HALException):
    'Procedure Exceptions'
    WRONG_SCHEMA = HALError(1, Template('Procedure specified in wrong schema ($schema). Please use schema $expected.'))
    UNKNOWN_ENVIRONMENT = HALError(2, Template('Unknown environment requested: $env.'))
    UNKNOWN_LIBRARY = HALError(3, Template('Unable to locate import: $lib.'))
    BAD_FLAG = HALError(4, Template('Invalid value for flag: $value'))
    EXPANSION_ERROR = HALError(5, Template('$err\n  On line: $text'))


class Formatter:
    'Render formatting based on requested output format'
    OUTPUT_FORMATS = Enum('output_formats', ('text', 'html', 'csv'))
    _LINK_PRELIM = '{link:'

    def __init__(self, output_format):
        self.format = output_format
        self.level = 0
        self.count = 1
        self.keeper = list()
        self.prefix = ''
        self.link_regex = re_compile(f'\\{self._LINK_PRELIM}(.+?)(\\|(.+))?\\}}')

        for case in switch(self.format):
            if case(self.OUTPUT_FORMATS.csv):
                pass
            if case(self.OUTPUT_FORMATS.text):
                self.bos = self.eos = self._bol = ''
                self.eol = '\n'
                break
            if case(self.OUTPUT_FORMATS.html):
                self.bos = '<ul>'
                self.eos = '</ul>'
                self._bol = '<h2><li>'
                self.eol = '</li></h2>'
                break
            if case():
                raise FormatterError(FormatterError.BAD_FORMAT, format=self.format)

    @property
    def bol(self):
        'Gets the beginning of line formatting'
        if self.level == 0:
            sep = ',' if (self.format == self.OUTPUT_FORMATS.csv) else '. '
            for case in switch(self.format):
                if case(self.OUTPUT_FORMATS.csv):
                    pass
                if case(self.OUTPUT_FORMATS.text):
                    return chr(64+self.count) + sep
                if case(self.OUTPUT_FORMATS.html):
                    return self._bol
                if case():
                    raise FormatterError(FormatterError.BAD_FORMAT, format=self.format)
        else:
            if self.format == self.OUTPUT_FORMATS.csv:
                space = ''
                sep = ','
            else:
                space = '    ' * self.level
                sep = ': '
            return f'{self._bol}{space}{self.prefix}{self.count}{sep}'

    def increment(self):
        'Increment the current indentation counter'
        self.count += 1

    def indent(self):
        'Increment the indentation level'
        self.keeper.append((self.count, self.prefix))
        if self.level > 0:
            self.prefix = f'{self.keeper[-1][1]}{self.count}.'
        elif self.format == self.OUTPUT_FORMATS.html:
            self._bol = '<li style="color:white"><span style="color:black">'
            self.eol = '</span></li>'
        self.level += 1
        self.count = 1

    def outdent(self):
        'Decrement the indentation level'
        self.level -= 1
        (self.count, self.prefix) = self.keeper.pop()
        if self.level > 0:
            self.count += 1
        elif self.format == self.OUTPUT_FORMATS.html:
            self._bol = '<h2><li>'
            self.eol = '</li></h2>'

    def format_hyperlinks(self, line):
        'Formats hyperlinks in the output'
        if not line or (self._LINK_PRELIM not in line):
            return line

        match = self.link_regex.search(line)
        replace_what = match.group(0)
        link = match.group(1)
        text = match.group(3) if (len(match.groups()) == 3) else ''
        for case in switch(self.format):
            if case(self.OUTPUT_FORMATS.csv):
                replace_with = f'"=HYPERLINK(""{link}"", ""{text}"")"' if text else link
                break
            if case(self.OUTPUT_FORMATS.text):
                replace_with = f'{text} ({link})' if text else link
                break
            if case(self.OUTPUT_FORMATS.html):
                text = text if text else link
                replace_with = f'<a href="{link}">{text}</a>'
                break
            if case():
                raise FormatterError(FormatterError.BAD_FORMAT, format=self.format)
        return line.replace(replace_what, replace_with)


class Expander:
    'Class to handle expansion items'
    _PRELIM_DEFAULT = '{var:'
    _POSTLIM_DEFAULT = '}'

    def __init__(self, vardict=None, varprops=None, prelim=_PRELIM_DEFAULT, postlim=_POSTLIM_DEFAULT):
        self.vardict = vardict if vardict else dict()
        self.varprops = varprops if (isinstance(varprops, list) or isinstance(varprops, tuple)) else [varprops]
        self.prelim = prelim
        self.postlim = postlim
        prelim_re = self.prelim
        postlim_re = self.postlim
        for spec in '.^$*+?|!/{}[]()<>:':
            prelim_re = prelim_re.replace(spec, '\\' + spec)
            postlim_re = postlim_re.replace(spec, '\\' + spec)
        self.re_var = re_compile(f'{prelim_re}([.a-zA-Z0-9_:]+){postlim_re}')

    def expand(self, thing):
        'Performs an expansion on a Python object'
        if isinstance(thing, tuple):
            return {self.expand(i) for i in thing}

        if isinstance(thing, list):
            return [self.expand(i) for i in thing]

        if isinstance(thing, dict):
            return {self.expand(k): self.expand(v) for (k, v) in thing.items()}

        if (thing is None) or isinstance(thing, bool):
            return thing

        while self.prelim in thing:
            fail = False
            try:
                var = self.re_var.search(thing).group(1)
            except AttributeError:
                prelim_index = thing.index(self.prelim)
                substr = thing[prelim_index:prelim_index+200]
                fail = True
            if fail:
                raise ExpanderError(ExpanderError.NO_POST_DELIMITER, substr=substr)

            fail = True
            if var in self.vardict:
                replacer = self.vardict[var]
                fail = False
            else:
                for varprops in self.varprops:
                    if hasattr(varprops, var):
                        replacer = getattr(varprops, var)
                        fail = False
                        break

            if fail:
                raise ExpanderError(ExpanderError.NO_VARIABLE, var=var, thing=thing)

            thing = thing.replace(f'{self.prelim}{var}{self.postlim}', str(replacer))
        return thing

    def expand_file(self, in_file, out_file):
        'Expands an entire file'
        with open(in_file) as instream:
            Path(out_file).parent.mkdir(parents=True, exist_ok=True)
            with open(out_file, 'w') as outstream:
                for line in instream:
                    line = self.expand(line)
                    outstream.write(line)

    def expand_directory(self, source_dir, target_dir=None, ignore_files=tuple(), no_expand_files=tuple(), err_if_exists=True):
        'Recursively expands files in a directory tree'
        source_dir = Path(source_dir).resolve()
        target_dir = Path(target_dir).resolve() if target_dir else Path.cwd()
        if is_debug('EXPANDER'):
            print('Using source directory:', source_dir)
            print('Using target directory:', target_dir)
        target_dir.mkdir(parents=True, exist_ok=(not err_if_exists))
        for (root, dirs, files) in walk(source_dir):  # pylint: disable=W0612
            for file_name in files:
                if is_debug('EXPANDER'):
                    print('Checking', file_name, 'against', ignore_files)
                if file_name in ignore_files:
                    continue
                source_file = Path(root, file_name)
                target_file = target_dir / root.replace(str(source_dir), '').lstrip('\\' if WIN32 else '/') / file_name
                if file_name in no_expand_files:
                    if is_debug('EXPANDER'):
                        print(f'Copying {source_file} to {target_file} (root={root})')
                    copyfile(source_file, target_file)
                else:
                    if is_debug('EXPANDER'):
                        print(f'Expanding {source_file} to {target_file} (root={root})')
                    self.expand_file(source_file, target_file)

    def evaluate_expression(self, expression):
        'Evaluates an expression in the expansion'
        if is_debug('EXPANDER'):
            print(f'Expanding (raw expression) "{expression}"')

        if isinstance(expression, bool):
            return expression
        if not expression:
            return True

        expression = self.expand(expression)
        synonyms = {' not ': ('!', '-not'),
                    ' and ': ('&&', ',', '-and'),
                    ' or ': ('||', '-or')}
        for (operator, synlist) in synonyms.items():
            for synonym in synlist:
                expression = expression.replace(synonym, operator)
        try:
            if is_debug('EXPANDER'):
                print(f'Expanding (corrected expression) "{expression}"')
            result = eval(expression, self.vardict)  # pylint: disable=W0123
            if is_debug('EXPANDER'):
                print(f'Expanding (evaluated expression) "{result}"')
            if isinstance(result, str):
                result = str_to_pythonval(result)
            if is_debug('EXPANDER'):
                print(f'Returning: "{result}"')
            return result
        except NameError as err:
            badvar = str(err)
        raise ExpanderError(ExpanderError.NO_VARIABLE, var=badvar, thing=expression)


def file_expander(in_file, out_file, vardict=None, varprops=None):
    'Quick function for one-time file expansion'
    return Expander(vardict, varprops).expand_file(in_file, out_file)


class Procedure:
    'Class to represent a procedure'
    _SCHEMA_ATTR = 'schema'
    _REQUIRED_PROCEDURE_SCHEMA = 1

    _HEADER_TAG = 'header'
    _FLAGS_TAG = 'flags'
    _DIRECTORIES_TAG = 'directories'
    _ENVIRONMENTS_TAG = 'environments'
    _STEPS_TAG = 'steps'
    _LIBRARY_TAG = 'step-library'

    _COMMON_ENVIRONMENT = 'common'
    _ENVIRONMENT_VARIABLE = 'Environment'

    def __init__(self, procfile, output_format=Formatter.OUTPUT_FORMATS.html, variable_overrides=None):
        self.output_format = output_format
        self.formatter = None
        self.expander = None

        xmlroot = xmlparse(slurp(procfile))
        schema = str_to_pythonval(xmlroot.get(self._SCHEMA_ATTR, 0))
        if schema != self._REQUIRED_PROCEDURE_SCHEMA:
            raise ProcedureError(ProcedureError.WRONG_SCHEMA, schema=schema, expected=self._REQUIRED_PROCEDURE_SCHEMA)
        self.header = xmlroot.findtext(self._HEADER_TAG) if xmlroot.findtext(self._HEADER_TAG) else ''
        flags = {f.tag: self.parse_flag(f.text) for f in list(xmlroot.find(self._FLAGS_TAG))} if xmlroot.find(self._FLAGS_TAG) else dict()
        self.directories = [d.text for d in list(xmlroot.find(self._DIRECTORIES_TAG))] if xmlroot.find(self._DIRECTORIES_TAG) else list()
        self.steps = [Step(s) for s in list(xmlroot.find(self._STEPS_TAG))] if xmlroot.find(self._STEPS_TAG) else list()
        self.library = {r.attrib[Step.NAME_ATTR]: Step(r) for r in list(xmlroot.find(self._LIBRARY_TAG))} if xmlroot.find(self._LIBRARY_TAG) else dict()
        self.environments = {e.tag: {v.tag: (v.text if v.text else '') for v in list(e)} for e in list(xmlroot.find(self._ENVIRONMENTS_TAG))} if xmlroot.find(self._ENVIRONMENTS_TAG) else dict()

        if self._COMMON_ENVIRONMENT in self.environments:
            common_environment = self.environments[self._COMMON_ENVIRONMENT]
            del self.environments[self._COMMON_ENVIRONMENT]
        else:
            common_environment = dict()

        # Convert the flags to True/False variables in the common environment
        for (flag_name, flag_value) in flags.items():
            common_environment[flag_name] = flag_value

        # Create a default value of False for IsEnvironment of every environment
        for env in self.environments:
            common_environment['Is'+env] = False

        # Update the environments with the common environment values and
        # set the Environment variable and
        # set IsEnvironment to True for that environment
        for env in self.environments:
            env_dict = deepcopy(common_environment)
            env_dict.update(self.environments[env])
            if variable_overrides:
                env_dict.update(variable_overrides)
            self.environments[env] = env_dict
            if self._ENVIRONMENT_VARIABLE not in self.environments[env]:
                self.environments[env][self._ENVIRONMENT_VARIABLE] = env
            self.environments[env]['Is'+env] = True

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def dump(self):
        'Dump out the procedure contents'
        result = odict()
        result[self._HEADER_TAG] = self.header
        result[self._DIRECTORIES_TAG] = self.directories
        result[self._ENVIRONMENTS_TAG] = {e: v for (e, v) in self.environments.items()}
        result[self._LIBRARY_TAG] = {r: s.dump() for (r, s) in self.library.items()}
        result[self._STEPS_TAG] = [s.dump() for s in self.steps]
        return result

    def setup_expander(self, environment):
        'Setup the Expander for the requested environment'
        if environment not in self.environments:
            ProcedureError(ProcedureError.UNKNOWN_ENVIRONMENT, env=environment)
        self.expander = Expander(self.environments[environment])

    def expand(self, text):
        'Expand the Procedure'
        try:
            return self.expander.expand(text)
        except ExpanderError as err:
            if err.code == ExpanderError.NO_VARIABLE.code:
                raise ProcedureError(ProcedureError.EXPANSION_ERROR, err=str(err), text=text)
            raise

    def format(self, text):
        'Format an output line including hyperlinks'
        return self.formatter.format_hyperlinks(self.expand(text))

    def realize(self, env):
        'Realize the procedure for the specified environments based on the variables'
        self.formatter = Formatter(self.output_format)
        self.setup_expander(env)
        for case in switch(self.output_format):
            if case(Formatter.OUTPUT_FORMATS.csv):
                header = f',{self.header.strip()} for {{var:Environment}}\n'
                footer = ''
                break
            if case(Formatter.OUTPUT_FORMATS.text):
                header = f'{self.header.strip()} for {{var:Environment}}\n'
                footer = ''
                break
            if case(Formatter.OUTPUT_FORMATS.html):
                header = '<html><meta http-equiv="Content-Type" content="text/html;charset=utf-8"><body><center>'
                header += f'<h1>{self.header} for {{var:Environment}}</h1></center><ol type="A">'
                footer = '</ol></body></html>'
                break
            if case():
                raise FormatterError(FormatterError.BAD_FORMAT, format=self.output_format)

        content = ''
        for step in self.steps:
            text = self.realize_step(step)
            if text:
                content += self.formatter.eol + text
                self.formatter.increment()
        return self.format(header) + content + footer

    def realize_step(self, step):
        'Expand a step in the procedure'
        if not self.expander.evaluate_expression(step.condition):
            return ''

        expander_vars_keeper = None
        if step.vars:
            expander_vars_keeper = deepcopy(self.expander.vardict)
            self.expander.vardict.update(step.vars)

        if step.libimport:
            if step.libimport not in self.library:
                ProcedureError(ProcedureError.UNKNOWN_LIBRARY, lib=step.libimport)
            lib_step = deepcopy(self.library[step.libimport])
            lib_step.repeat = step.repeat
            lib_step.vars.update(step.vars)
            if step.text:
                lib_step.text = step.text
            elif not lib_step.text:
                lib_step.text = lib_step.name
            step = lib_step

        output = ''
        if step.repeat:
            (variable, values) = step.repeat.split('=')
            values = [v.strip() for v in self.expand(values).split(',')]
            step_copy = deepcopy(step)
            step_copy.repeat = False
            for value in values:
                step_copy.vars[variable] = value
                output += self.realize_step(step_copy)
        elif step.substeps:
            start_of_step = self.formatter.bol + self.format(step.text) + self.formatter.eol + self.formatter.bos
            self.formatter.indent()
            for substep in step.substeps:
                output += self.realize_step(substep)
            if output:
                output = start_of_step + output + self.formatter.eos
            self.formatter.outdent()
        else:
            output = self.format(step.text)
            if output:
                output = self.formatter.bol + output + self.formatter.eol
                self.formatter.increment()

        if expander_vars_keeper:
            self.expander.vardict = expander_vars_keeper
        return output

    def expand_directories(self, env, destination_root, source_root=None, err_if_exists=True):
        'Performs variable expansion on the directories'
        self.setup_expander(env)
        for dirname in self.directories:
            dirpath = Path(dirname)
            if not dirpath.is_absolute():
                dirpath = source_root / dirpath
            self.expander.expand_directory(dirpath, Path(destination_root, dirname), err_if_exists=err_if_exists)

    def parse_flag(self, flag):
        'Evaluate a parsing flag'
        value = str_to_pythonval(flag.lower().replace('0', 'False').replace('1', 'True').replace('yes', 'True').replace('no', 'False'))
        if not isinstance(value, bool):
            raise ProcedureError(ProcedureError.BAD_FLAG, value=flag)
        return value


class Step:
    'Represents an individual step in a Procedure'
    NAME_ATTR = 'name'

    _CONDITION_ATTR = 'condition'
    _IMPORT_ATTR = 'import'
    _REPEAT_ATTR = 'repeat'
    _VARS_ATTR = 'vars'

    def __init__(self, step_def):
        self.condition = step_def.get(self._CONDITION_ATTR)
        self.libimport = step_def.get(self._IMPORT_ATTR)
        self.name = step_def.get(self.NAME_ATTR)
        self.repeat = step_def.get(self._REPEAT_ATTR)
        self.text = step_def.text.strip() if step_def.text else ''
        self.substeps = [Step(s) for s in list(step_def)]
        var = step_def.get(self._VARS_ATTR)
        self.vars = {v.split('=')[0].strip(): v.split('=')[1].strip() for v in var.split(',')} if var else dict()

    def dump(self):
        'Dump out the step content'
        return [f'{self.text}: import={self.libimport}: condition={self.condition}: repeat={self.repeat}: vars={self.vars}'] + [s.dump() for s in self.substeps]
