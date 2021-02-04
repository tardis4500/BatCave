"""This module provides utilities for managing file expansions.

An instantiation of this class will convert an XML into the procedure object::

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
from typing import cast, Any, Dict, List, Match, Optional, Sequence, Tuple, Union
from xml.etree.ElementTree import fromstringlist as xmlparse, Element

# Import BatCave packages
from .fileutil import slurp
from .lang import is_debug, str_to_pythonval, switch, BatCaveError, BatCaveException, PathName, WIN32

OutputFormat = Enum('OutputFormat', ('text', 'html', 'csv'))


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
        _LINK_PRELIM: The prefix to indicate a hyperlink during formatting.
    """
    _LINK_PRELIM = '{link:'

    def __init__(self, output_format: OutputFormat, /):
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
        self.keeper: List[Tuple[int, str]] = list()
        self.prefix = ''
        self.link_regex = re_compile(f'\\{self._LINK_PRELIM}(.+?)(\\|(.+))?\\}}')

        for case in switch(self.format):
            if case(OutputFormat.csv):
                pass
            if case(OutputFormat.text):
                self.bos = self.eos = self._bol = ''
                self.eol = '\n'
                break
            if case(OutputFormat.html):
                self.bos = '<ul>'
                self.eos = '</ul>'
                self._bol = '<h2><li>'
                self.eol = '</li></h2>'
                break
            if case():
                raise ProcedureError(ProcedureError.BAD_FORMAT, format=self.format)

    @property
    def bol(self) -> str:
        """A read-only property which returns the beginning of line formatting."""
        if self.level == 0:
            sep = ',' if (self.format == OutputFormat.csv) else '. '
            for case in switch(self.format):
                if case(OutputFormat.csv):
                    pass
                if case(OutputFormat.text):
                    return chr(64 + self.count) + sep
                if case(OutputFormat.html):
                    return self._bol
                raise ProcedureError(ProcedureError.BAD_FORMAT, format=self.format)
        else:
            if self.format == OutputFormat.csv:
                space = ''
                sep = ','
            else:
                space = '    ' * self.level
                sep = ': '
            return f'{self._bol}{space}{self.prefix}{self.count}{sep}'
        raise ProcedureError(ProcedureError.BAD_FORMAT, format=self.format)

    def format_hyperlinks(self, line: str, /) -> str:
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

        if not (match := self.link_regex.search(line)):
            raise ProcedureError(ProcedureError.BAD_FORMAT, format=self.format)
        replace_what = match.group(0)
        link = match.group(1)
        text = match.group(3) if (len(match.groups()) == 3) else ''
        replace_with = ''
        for case in switch(self.format):
            if case(OutputFormat.csv):
                replace_with = f'"=HYPERLINK(""{link}"", ""{text}"")"' if text else link
                break
            if case(OutputFormat.text):
                replace_with = f'{text} ({link})' if text else link
                break
            if case(OutputFormat.html):
                text = text if text else link
                replace_with = f'<a href="{link}">{text}</a>'
                break
            if case():
                raise ProcedureError(ProcedureError.BAD_FORMAT, format=self.format)
        return line.replace(replace_what, replace_with)

    def increment(self) -> None:
        """Increment the counter at the current indentation level.

        Returns:
            Nothing.
        """
        self.count += 1

    def indent(self) -> None:
        """Increment the indentation level.

        Returns:
            Nothing.
        """
        self.keeper.append((self.count, self.prefix))
        if self.level > 0:
            self.prefix = f'{self.keeper[-1][1]}{self.count}.'
        elif self.format == OutputFormat.html:
            self._bol = '<li style="color:white"><span style="color:black">'
            self.eol = '</span></li>'
        self.level += 1
        self.count = 1

    def outdent(self) -> None:
        """Decrement the indentation level.

        Returns:
            Nothing.
        """
        self.level -= 1
        (self.count, self.prefix) = self.keeper.pop()
        if self.level > 0:
            self.count += 1
        elif self.format == OutputFormat.html:
            self._bol = '<h2><li>'
            self.eol = '</li></h2>'


class Expander:
    """Class to handle interpolation of strings and files.

    Attributes:
        _PRELIM_DEFAULT: The prefix for a variable to be expanded.
        _POSTLIM_DEFAULT: The suffix for a variable to be expanded.
    """
    _PRELIM_DEFAULT = '{var:'
    _POSTLIM_DEFAULT = '}'

    def __init__(self, *, vardict: Optional[Dict[str, str]] = None, varprops: Any = None, prelim: str = _PRELIM_DEFAULT, postlim: str = _POSTLIM_DEFAULT):
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
        self.varprops = varprops if (isinstance(varprops, (list, tuple))) else [varprops]
        self.prelim = prelim
        self.postlim = postlim
        prelim_re = self.prelim
        postlim_re = self.postlim
        for spec in '.^$*+?|!/{}[]()<>:':
            prelim_re = prelim_re.replace(spec, '\\' + spec)
            postlim_re = postlim_re.replace(spec, '\\' + spec)
        self.re_var = re_compile(f'{prelim_re}([.a-zA-Z0-9_:]+){postlim_re}')

    def evaluate_expression(self, expression: str, /) -> bool:
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
            result = eval(expression, self.vardict)  # pylint: disable=eval-used
            if is_debug('EXPANDER'):
                print(f'Expanding (evaluated expression) "{result}"')
            if isinstance(result, str):
                result = str_to_pythonval(result)
            if is_debug('EXPANDER'):
                print(f'Returning: "{result}"')
        except NameError as err:
            raise ExpanderError(ExpanderError.NO_REPLACEMENT, var=str(err), thing=expression) from err
        return result

    def expand(self, thing: Any, /) -> Any:
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

        var = substr = replacer = ''
        while self.prelim in thing:
            try:
                var = cast(Match[str], self.re_var.search(thing)).group(1)
            except AttributeError as err:
                prelim_index = thing.index(self.prelim)
                substr = thing[prelim_index:prelim_index + 200]
                raise ExpanderError(ExpanderError.NO_POST_DELIMITER, substr=substr) from err

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

    def expand_directory(self, source_dir: PathName, /, target_dir: Optional[PathName] = None, *,
                         ignore_files: Sequence[str] = tuple(), no_expand_files: Sequence[str] = tuple(), err_if_exists: bool = True) -> None:
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
                        print(f'Expanding {source_file} to {target_file} ({root=})')
                    self.expand_file(source_file, target_file)

    def expand_file(self, in_file: PathName, out_file: PathName, /) -> None:
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


def file_expander(in_file: PathName, out_file: PathName, /, *, vardict: Optional[Dict[str, str]] = None, varprops: Any = None) -> None:
    """Quick function for one-time file expansion.

    Args:
        in_file: The input file.
        out_file: The output file.
        vardict (optional, default=None): If not None, provides a dictionary of expansion values.
        varprops (optional, default=None): If not None, provides an object with properties to be used as expansion values.

    Returns:
        Nothing.
    """
    Expander(vardict=vardict, varprops=varprops).expand_file(in_file, out_file)


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
    _COMMON_ENVIRONMENT = 'common'
    _DIRECTORIES_TAG = 'directories'
    _ENVIRONMENTS_TAG = 'environments'
    _ENVIRONMENT_VARIABLE = 'Environment'
    _FLAGS_TAG = 'flags'
    _HEADER_TAG = 'header'
    _LIBRARY_TAG = 'step-library'
    _REQUIRED_PROCEDURE_SCHEMA = 1
    _SCHEMA_ATTR = 'schema'
    _STEPS_TAG = 'steps'

    def __init__(self, procfile: PathName, /, *, output_format: OutputFormat = OutputFormat.html, variable_overrides: Optional[Dict[str, str]] = None):  # pylint: disable=too-many-locals
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
        self.formatter: Formatter
        self.expander: Expander

        if (schema := str_to_pythonval((xmlroot := xmlparse(slurp(procfile))).get(self._SCHEMA_ATTR, '0'))) != self._REQUIRED_PROCEDURE_SCHEMA:
            raise ProcedureError(ProcedureError.BAD_SCHEMA, schema=schema, expected=self._REQUIRED_PROCEDURE_SCHEMA)
        self.header = str(xmlroot.findtext(self._HEADER_TAG)) if xmlroot.findtext(self._HEADER_TAG) else ''
        flags = {f.tag: parse_flag(str(f.text)) for f in list(flags_element)} if (flags_element := xmlroot.find(self._FLAGS_TAG)) else dict()  # pylint: disable=used-before-assignment
        self.directories = [str(d.text) for d in list(directories_element)] if (directories_element := xmlroot.find(self._DIRECTORIES_TAG)) else list()  # pylint: disable=used-before-assignment
        self.steps = [Step(s) for s in list(steps_element)] if (steps_element := xmlroot.find(self._STEPS_TAG)) else list()  # pylint: disable=used-before-assignment
        self.library = {r.attrib[Step.NAME_ATTR]: Step(r) for r in list(library_element)} if (library_element := xmlroot.find(self._LIBRARY_TAG)) else dict()  # pylint: disable=used-before-assignment

        environments_element = xmlroot.find(self._ENVIRONMENTS_TAG)
        self.environments: Dict = {e.tag: {v.tag: (v.text if v.text else '') for v in list(e)} for e in list(environments_element)} if environments_element else dict()

        common_environment: Dict
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
            common_environment['Is' + env] = False

        # Update the environments with the common environment values and
        # set the Environment variable and
        # set IsEnvironment to True for that environment
        for env in self.environments:
            (env_dict := deepcopy(common_environment)).update(self.environments[env])
            if variable_overrides:
                env_dict.update(variable_overrides)
            self.environments[env] = env_dict
            if self._ENVIRONMENT_VARIABLE not in self.environments[env]:
                self.environments[env][self._ENVIRONMENT_VARIABLE] = env
            self.environments[env]['Is' + env] = True

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def dump(self) -> Dict[str, Union[str, Sequence, Dict]]:
        """Dump out the procedure contents.

        Returns:
            The contents of the procedure as an ordered dictionary.
        """
        result: Dict = odict()
        result[self._HEADER_TAG] = self.header
        result[self._DIRECTORIES_TAG] = self.directories
        result[self._ENVIRONMENTS_TAG] = {e: v for (e, v) in self.environments.items()}  # pylint: disable=unnecessary-comprehension
        result[self._LIBRARY_TAG] = {r: s.dump() for (r, s) in self.library.items()}
        result[self._STEPS_TAG] = [s.dump() for s in self.steps]
        return result

    def expand(self, text: str, /) -> str:
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
                raise ProcedureError(ProcedureError.EXPANSION_ERROR, err=str(err), text=text) from err
            raise

    def expand_directories(self, env: str, /, destination_root: PathName, *, source_root: PathName = Path(), err_if_exists: bool = True) -> None:
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
            if not (dirpath := Path(dirname)).is_absolute():
                dirpath = Path(source_root) / dirpath
            self.expander.expand_directory(dirpath, Path(destination_root, dirname), err_if_exists=err_if_exists)

    def format(self, text: str, /) -> str:
        """Format an output line including hyperlinks.

        Args:
            text: The line of text to format.

        Returns:
            The formatted output line.
        """
        return self.formatter.format_hyperlinks(self.expand(text))

    def realize(self, env: str, /) -> str:
        """Realize the procedure for the specified environments based on the variables.

        Args:
            env: The environment for which to realize the procedure.

        Returns:
            The realized procedure.

        Raises:
            ProcedureError.BAD_FORMAT: If the format type is not defined.
        """
        header = footer = ''
        self.formatter = Formatter(self.output_format)
        self.setup_expander(env)
        for case in switch(self.output_format):
            if case(OutputFormat.csv):
                header = f',{self.header.strip()} for {{var:Environment}}\n'
                footer = ''
                break
            if case(OutputFormat.text):
                header = f'{self.header.strip()} for {{var:Environment}}\n'
                footer = ''
                break
            if case(OutputFormat.html):
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

    def realize_step(self, step: 'Step', /) -> str:  # pylint: disable=too-many-branches
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
            (variable, values_as_str) = step.repeat.split('=')
            values = [v.strip() for v in self.expand(values_as_str).split(',')]
            step_copy = deepcopy(step)
            step_copy.repeat = ''
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
            if output := self.format(step.text):
                output = self.formatter.bol + output + self.formatter.eol
                self.formatter.increment()

        if expander_vars_keeper:
            self.expander.vardict = expander_vars_keeper
        return output

    def setup_expander(self, environment: str, /) -> None:
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
        self.expander = Expander(vardict=self.environments[environment])


class Step:  # pylint: disable=too-few-public-methods
    """Class to create a universal abstract interface for a procedure step.

    Attributes:
        NAME_ATTR: The XML attribute to indicate the step name.
        _CONDITION_ATTR: The XML attribute to indicate the step condition.
        _IMPORT_ATTR: The XML attribute to indicate the step import.
        _REPEAT_ATTR: The XML attribute to indicate the step repeat condition.
        _VARS_ATTR: The XML attribute to indicate the step variables.
    """
    _CONDITION_ATTR = 'condition'
    _IMPORT_ATTR = 'import'
    _REPEAT_ATTR = 'repeat'
    _VARS_ATTR = 'vars'

    NAME_ATTR = 'name'

    def __init__(self, step_def: Element, /):
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
        self.condition = step_def.get(self._CONDITION_ATTR, '')
        self.libimport = step_def.get(self._IMPORT_ATTR, '')
        self.name = step_def.get(self.NAME_ATTR, '')
        self.repeat = step_def.get(self._REPEAT_ATTR, '')
        self.text = step_def.text.strip() if step_def.text else ''
        self.substeps = [Step(s) for s in list(step_def)]
        self.vars = {v.split('=')[0].strip(): v.split('=')[1].strip() for v in var.split(',')} if (var := step_def.get(self._VARS_ATTR, '')) else dict()  # pylint: disable=used-before-assignment

    def dump(self) -> List:
        """Dump out the step contents.

        Returns:
            The contents of the step as an list.
        """
        return [f'{self.text}: import={self.libimport}: condition={self.condition}: repeat={self.repeat}: vars={self.vars}'] + [str(s.dump()) for s in self.substeps]


def parse_flag(flag: str, /) -> Any:
    """Evaluate a parsing flag.

    Args:
        flag: The flag to evaluate.

    Return:
        The evaluated value for the flag.

    Raises:
        ProcedureError.BAD_FLAG: If the evaluated flag is not of type bool.
    """
    if not isinstance(value := str_to_pythonval(flag.lower().replace('0', 'False').replace('1', 'True').replace('yes', 'True').replace('no', 'False')), bool):
        raise ProcedureError(ProcedureError.BAD_FLAG, value=flag)
    return value

# cSpell:ignore odict
