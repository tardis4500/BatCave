"""This module provides utilities for managing file expansions.

An instantiation of this class will convert an XML into the procedure object

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
"""

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
from .lang import is_debug, str_to_pythonval, switch, BatCaveError, BatCaveException, WIN32


class ExpanderError(BatCaveException):
    """Expansion Exceptions.

    Attributes:
        NO_POST_DELIMITER: No postfix delimiter was found.
        NO_REPLACEMENT: No replacement was found for the specified variable
    """
    NO_POST_DELIMITER = BatCaveError(1, Template('No closing delimiter found in $substr'))
    NO_REPLACEMENT = BatCaveError(2, Template('No replacement found for variable ($var) in: $thing'))


class ProcedureError(BatCaveException):
    """Procedure Exceptions.

    Attributes:
        BAD_ENVIRONMENT: The requested environment is not valid.
        BAD_FLAG: The specified flag value is not value.
        BAD_FORMAT: The requested output format is not valid.
        BAD_LIBRARY: The requested library is not valid.
        BAD_SCHEMA: The procedure schema is not supported.
        EXPANSION_ERROR: The was an unspecified error during expansion.
    """
    BAD_ENVIRONMENT = BatCaveError(1, Template('Unknown environment requested: $env.'))
    BAD_FLAG = BatCaveError(2, Template('Invalid value for flag: $value'))
    BAD_FORMAT = BatCaveError(3, Template('Unknown output format requested: $format'))
    BAD_LIBRARY = BatCaveError(4, Template('Unable to locate import: $lib.'))
    BAD_SCHEMA = BatCaveError(5, Template('Procedure specified in wrong schema ($schema). Please use schema $expected.'))
    EXPANSION_ERROR = BatCaveError(6, Template('$err\n  On line: $text'))


class Formatter:
    """Class to hold formatting information.

    Attributes:
        OUTPUT_FORMATS: The valid output formats.
        _LINK_PRELIM: The prefix to indicate a hyperlink during formatting.
    """
    OUTPUT_FORMATS = Enum('output_formats', ('text', 'html', 'csv'))
    _LINK_PRELIM = '{link:'

    def __init__(self, output_format):
        """
        Args:
            output_format: The output format.

        Attributes:
            format: The value of the name argument.
            count: This current character count on the line.
            keeper: The indentation stack
            level: The current indentation level.
            link_regex: The regular expression to locate a hyperlink.
            prefix: The line prefix for the current line.

        Raises:
            ProcedureError.BAD_FORMAT: If the requested output format is invlid.
        """
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
                raise ProcedureError(ProcedureError.BAD_FORMAT, format=self.format)

    @property
    def bol(self):
        """A read-only property which returns the beginning of line formatting."""
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
                    raise ProcedureError(ProcedureError.BAD_FORMAT, format=self.format)
        else:
            if self.format == self.OUTPUT_FORMATS.csv:
                space = ''
                sep = ','
            else:
                space = '    ' * self.level
                sep = ': '
            return f'{self._bol}{space}{self.prefix}{self.count}{sep}'

    def increment(self):
        """Increment the counter at the current indentation level.

        Returns:
            Nothing.
        """
        self.count += 1

    def indent(self):
        """Increment the indentation level.

        Returns:
            Nothing.
        """
        self.keeper.append((self.count, self.prefix))
        if self.level > 0:
            self.prefix = f'{self.keeper[-1][1]}{self.count}.'
        elif self.format == self.OUTPUT_FORMATS.html:
            self._bol = '<li style="color:white"><span style="color:black">'
            self.eol = '</span></li>'
        self.level += 1
        self.count = 1

    def outdent(self):
        """Decrement the indentation level.

        Returns:
            Nothing.
        """
        self.level -= 1
        (self.count, self.prefix) = self.keeper.pop()
        if self.level > 0:
            self.count += 1
        elif self.format == self.OUTPUT_FORMATS.html:
            self._bol = '<h2><li>'
            self.eol = '</li></h2>'

    def format_hyperlinks(self, line):
        """Format the hyperlinks in a line.

        Args:
            line: The line for which to format hyperlinks.

        Returns:
            The formatted line.

        Raises:
            ProcedureError.BAD_FORMAT: If the requested format is not valid.
        """
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
                raise ProcedureError(ProcedureError.BAD_FORMAT, format=self.format)
        return line.replace(replace_what, replace_with)


class Expander:
    """Class to handle interpolation of strings and files.

    Attributes:
        _PRELIM_DEFAULT: The prefix for a variable to be expanded.
        _POSTLIM_DEFAULT: The suffix for a variable to be expanded.
    """
    _PRELIM_DEFAULT = '{var:'
    _POSTLIM_DEFAULT = '}'

    def __init__(self, vardict=None, varprops=None, prelim=_PRELIM_DEFAULT, postlim=_POSTLIM_DEFAULT):
        """
        Args:
            vardict: A dictionary of expansion variables.
            varprop: An object with properties that resolve variables.
            prelim: The leading string to identify an expansion.
            postlim: The training string to identify an expansion.

        Attributes:
            postlim: The value of the postlim argument.
            prelim: The value of the prelim argument.
            re_var: The regular expression to identify a variable to expand.
            vardict: The value of the vardict argument.
            varprop: The value of the varprop argument.
        """
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
        """Perform an expansion on a Python object.

        Args:
            thing: The object on which to perform an expansion.

        Returns:
            The object with expansions performed.

        Raises:
            ExpanderError.NO_POST_DELIMITER: If the closing delimiter was not found.
            ExpanderError.NO_REPLACEMENT: If no replacement was found for the requested expansion variable.
        """
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
                raise ExpanderError(ExpanderError.NO_REPLACEMENT, var=var, thing=thing)

            thing = thing.replace(f'{self.prelim}{var}{self.postlim}', str(replacer))
        return thing

    def expand_file(self, in_file, out_file):
        """Perform an expansion on an entire file.

        Args:
            in_file: The name of the file on which to perform the expansions.
            out_file: The name of the output file for the expansion results.

        Returns:
            Nothing.
        """
        with open(in_file) as instream:
            Path(out_file).parent.mkdir(parents=True, exist_ok=True)
            with open(out_file, 'w') as outstream:
                for line in instream:
                    line = self.expand(line)
                    outstream.write(line)

    def expand_directory(self, source_dir, target_dir=None, ignore_files=tuple(), no_expand_files=tuple(), err_if_exists=True):
        """Perform an expansion on an entire directory tree.

        Args:
            source_dir: The name of the directory on which to perform the expansions.
            target_dir (optional, default=None): The name of the output directory for the expansion results if not None,
                otherwise the current directory is used.
            ignore_files (optional, default=None): A list of files for which should be ignored and will not be in the output directory.
            no_expand_files (optional, default=None): A list of files which expansion should not be performed but which will be copied to the output directory.
            err_if_exists (optional, default=True): If True, raise an error if the output directory exists.

        Returns:
            Nothing.
        """
        source_dir = Path(source_dir).resolve()
        target_dir = Path(target_dir).resolve() if target_dir else Path.cwd()
        if is_debug('EXPANDER'):
            print('Using source directory:', source_dir)
            print('Using target directory:', target_dir)
        target_dir.mkdir(parents=True, exist_ok=(not err_if_exists))
        for (root, _unused_dirs, files) in walk(source_dir):
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
        """Evaluate an expression in the expansion.

        Args:
            expression: The expression to evaluate.

        Returns:
            The evaluated expression.

        Raises:
            ExpanderError.NO_REPLACEMENT: If no replacement was found for the requested expansion variable.
        """
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
        raise ExpanderError(ExpanderError.NO_REPLACEMENT, var=badvar, thing=expression)


def file_expander(in_file, out_file, vardict=None, varprops=None):
    """Quick function for one-time file expansion.

    Args:
        in_file: The input file.
        out_file: The output file.
        vardict (optional, default=None): If not None, provides a dictionary of expansion values.
        varprops (optional, default=None): If not None, provides an object with properties to be used as expansion values.

    Returns:
        Nothing.
    """
    Expander(vardict, varprops).expand_file(in_file, out_file)


class Procedure:
    """Class to create a universal abstract interface for a procedure.

    Attributes:
        _SCHEMA_ATTR: The XML tag which contains the schema version.
        _REQUIRED_PROCEDURE_SCHEMA: The schema supported by this class.

        _HEADER_TAG: The XML tag which indicates the procedure header.
        _FLAGS_TAG: The XML tag which indicates the procedure flags.
        _DIRECTORIES_TAG: The XML tag which indicates the procedure directories.
        _ENVIRONMENTS_TAG: The XML tag which indicates the procedure environments.
        _STEPS_TAG: The XML tag which indicates the procedure steps.
        _LIBRARY_TAG: The XML tag which indicates the procedure step library.

        _COMMON_ENVIRONMENT: The XML tag which indicates the procedure common environment.
        _ENVIRONMENT_VARIABLE: The XML tag which indicates an environment variable.
    """
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
        """
        Args:
            procfile: The procedure file.
            output_format: The output format.
            variable_overrides: A dictionary of values used to override values defined in the procedure file.

        Attributes:
            directories: The list of directories defined in the procedure file.
            environments: The dictionary of directories defined in the procedure file.
            expander: The expander object used to expand the procedure file.
            formatter: The formatter object used to format the output.
            header: The header of the output.
            library: The list of step libraries defined in the procedure file.
            output_format: The value of the output_format argument.
            steps: The list of steps defined in the procedure file.

        Raises:
            ProcedureError.BAD_SCHEMA: If the schema of the procedure file is not supported.
        """
        self.output_format = output_format
        self.formatter = None
        self.expander = None

        xmlroot = xmlparse(slurp(procfile))
        schema = str_to_pythonval(xmlroot.get(self._SCHEMA_ATTR, 0))
        if schema != self._REQUIRED_PROCEDURE_SCHEMA:
            raise ProcedureError(ProcedureError.BAD_SCHEMA, schema=schema, expected=self._REQUIRED_PROCEDURE_SCHEMA)
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
        """Dump out the procedure contents.

        Returns:
            The contents of the procedure as an ordered dictionary.
        """
        result = odict()
        result[self._HEADER_TAG] = self.header
        result[self._DIRECTORIES_TAG] = self.directories
        result[self._ENVIRONMENTS_TAG] = {e: v for (e, v) in self.environments.items()}
        result[self._LIBRARY_TAG] = {r: s.dump() for (r, s) in self.library.items()}
        result[self._STEPS_TAG] = [s.dump() for s in self.steps]
        return result

    def setup_expander(self, environment):
        """Setup the Expander for the requested environment.

        Args:
            environment: The environment for which to setup the expander.

        Returns:
            Nothing.

        Raises:
            ProcedureError.BAD_ENVIRONMENT: If the requested environment is not defined.
        """
        if environment not in self.environments:
            ProcedureError(ProcedureError.BAD_ENVIRONMENT, env=environment)
        self.expander = Expander(self.environments[environment])

    def expand(self, text):
        """Expand the Procedure.

        Args:
            text: The text of the procedure.

        Returns:
            The expanded procedure.

        Raises:
            ProcedureError.EXPANSION_ERROR: If there is an missing value expansion error.
        """
        try:
            return self.expander.expand(text)
        except ExpanderError as err:
            if err.code == ExpanderError.NO_REPLACEMENT.code:
                raise ProcedureError(ProcedureError.EXPANSION_ERROR, err=str(err), text=text)
            raise

    def format(self, text):
        """Format an output line including hyperlinks.

        Args:
            text: The line of text to format.

        Returns:
            The formatted output line.
        """
        return self.formatter.format_hyperlinks(self.expand(text))

    def realize(self, env):
        """Realize the procedure for the specified environments based on the variables.

        Args:
            env: The environment for which to realize the procedure.

        Returns:
            The realized procedure.

        Raises:
            ProcedureError.BAD_FORMAT: If the format type is not defined.
        """
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
                raise ProcedureError(ProcedureError.BAD_FORMAT, format=self.output_format)

        content = ''
        for step in self.steps:
            text = self.realize_step(step)
            if text:
                content += self.formatter.eol + text
                self.formatter.increment()
        return self.format(header) + content + footer

    def realize_step(self, step):
        """Realize a step in the procedure.

        Args:
            step: The step to realize.

        Returns:
            The realized step.

        Raises:
            ProcedureError.BAD_LIBRARY: If the step specifies a library that is not defined.
        """
        if not self.expander.evaluate_expression(step.condition):
            return ''

        expander_vars_keeper = None
        if step.vars:
            expander_vars_keeper = deepcopy(self.expander.vardict)
            self.expander.vardict.update(step.vars)

        if step.libimport:
            if step.libimport not in self.library:
                ProcedureError(ProcedureError.BAD_LIBRARY, lib=step.libimport)
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
        """Perform variable expansion on the directories defined in the procedure.

        Args:
            env: The environment for which to expand the directories.
            destination_root: That destination directory for the expansion.
            source_root (optional, default=None): Defined for recursion.
            err_if_exists (optional, default=True): If True, raise an error if destination_root exists.

        Returns:
            Nothing.
        """
        self.setup_expander(env)
        for dirname in self.directories:
            dirpath = Path(dirname)
            if not dirpath.is_absolute():
                dirpath = source_root / dirpath
            self.expander.expand_directory(dirpath, Path(destination_root, dirname), err_if_exists=err_if_exists)

    def parse_flag(self, flag):
        """Evaluate a parsing flag.

        Args:
            flag: The flag to evaluate.

        Return:
            The evaluated value for the flag.

        Raises:
            ProcedureError.BAD_FLAG: If the evaluated flag is not of type bool.
        """
        value = str_to_pythonval(flag.lower().replace('0', 'False').replace('1', 'True').replace('yes', 'True').replace('no', 'False'))
        if not isinstance(value, bool):
            raise ProcedureError(ProcedureError.BAD_FLAG, value=flag)
        return value


class Step:
    """Class to create a universal abstract interface for a procedure step.

    Attributes:
        NAME_ATTR: The XML attribute to indicate the step name.
        _CONDITION_ATTR: The XML attribute to indicate the step condition.
        _IMPORT_ATTR: The XML attribute to indicate the step import.
        _REPEAT_ATTR: The XML attribute to indicate the step repeat condition.
        _VARS_ATTR: The XML attribute to indicate the step variables.
    """
    NAME_ATTR = 'name'

    _CONDITION_ATTR = 'condition'
    _IMPORT_ATTR = 'import'
    _REPEAT_ATTR = 'repeat'
    _VARS_ATTR = 'vars'

    def __init__(self, step_def):
        """
        Args:
            step_def: The dictionary which defined the step.

        Attributes:
            condition: The condition the determines if the step is emitted.
            libimport: The library that is imported for the step.
            name: The step name.
            repeat: The repeat parameters for the step.
            substeps: The list of substeps for the step.
            text: The text emitted for the step.
            vars: The dictionary of variables defined for the step.
        """
        self.condition = step_def.get(self._CONDITION_ATTR)
        self.libimport = step_def.get(self._IMPORT_ATTR)
        self.name = step_def.get(self.NAME_ATTR)
        self.repeat = step_def.get(self._REPEAT_ATTR)
        self.text = step_def.text.strip() if step_def.text else ''
        self.substeps = [Step(s) for s in list(step_def)]
        var = step_def.get(self._VARS_ATTR)
        self.vars = {v.split('=')[0].strip(): v.split('=')[1].strip() for v in var.split(',')} if var else dict()

    def dump(self):
        """Dump out the step contents.

        Returns:
            The contents of the step as an list.
        """
        return [f'{self.text}: import={self.libimport}: condition={self.condition}: repeat={self.repeat}: vars={self.vars}'] + [s.dump() for s in self.substeps]

# cSpell:ignore odict
