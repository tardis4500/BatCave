"""This module provides utilities for working with files.

Attributes:
    ConversionMode (Enum): The conversion modes for the eol_convert function.
    PACKER_CLASSES (dict): A mapping of file compression extensions to the classes that create them.
    COMPRESSION_TYPE (dict): A mapping of file compression extensions to compression types.
"""

# Import standard modules
from bz2 import BZ2File
from enum import Enum
from gzip import GzipFile
from logging import getLogger
from lzma import LZMAFile
from pathlib import Path
from shutil import copy
from stat import S_IRWXU
from string import Template
from tarfile import open as tar_open
from time import time
from typing import Any, Iterable, List, Optional, Tuple
from zipfile import ZipFile, ZIP_DEFLATED

# Import internal modules
from .sysutil import popd, pushd
from .lang import DEFAULT_ENCODING, BatCaveError, BatCaveException, PathName


class ConvertError(BatCaveException):
    """File Conversion Exceptions.

    Attributes:
        BACKUP_EXISTS: The backup file already exists.
    """
    BACKUP_EXISTS = BatCaveError(1, Template('File already exists: $file'))


class PackError(BatCaveException):
    """File Packing Exceptions.

    Attributes:
        INVALID_TYPE: An invalid archive type was specified.
        NO_FILES: No files were found to pack into the archive.
    """
    INVALID_TYPE = BatCaveError(1, Template('Unknown archive type: $arc_type'))
    NO_FILES = BatCaveError(2, 'No files to add')


COMPRESSION_TYPE = {'gz': 'gz', 'tgz': 'gz',
                    'bz': 'bz2', 'tbz': 'bz2', 'bz2': 'bz2',
                    'xz': 'xz', 'txz': 'xz'}
ConversionMode = Enum('ConversionMode', ('to_unix', 'to_dos'))


class CompressedFile:  # pylint: disable=too-few-public-methods
    """Class to add support for compressed file types which are missing some methods."""

    def __init__(self, filename: PathName, /, **_unused_attr):
        """
        Args:
            filename: The name of the compressed file.
            **attr: The list of attributes to pass to the base class.

        Attributes:
            _filename: The value of the filename argument.
        """
        self._filename = Path(filename)

    def namelist(self) -> Tuple[str]:
        """Return the name of the file as the first item in a tuple.

        Returns:
            The name of the file.
        """
        return (self._filename.stem,)


class BatCaveGzipFile(GzipFile, CompressedFile):  # pylint: disable=too-many-ancestors
    """Add CompressedFile class methods to the GzipFile class."""


class BatCaveBZ2File(BZ2File, CompressedFile):  # type: ignore[misc]  # pylint: disable=too-many-ancestors
    """Add CompressedFile class methods to the BZ2File class."""


PACKER_CLASSES = {'zip': ZipFile, 'gz': BatCaveGzipFile, 'bz2': BatCaveBZ2File, 'xz': LZMAFile}


def eol_convert(filename: PathName, mode: ConversionMode, /, *, backup: bool = True) -> None:
    """Perform end-of-line conversions from Windows to UNIX or vice versa.

    Attributes:
        filename: The file to convert.
        mode: The direction of the conversion. Must be a member of ConversionMode.
        backup (optional, default=True): If True, creates a backup of filename as filename.bak.

    Returns:
        Nothing.

    Raises:
        ConvertError.BACKUP_EXISTS: If backup is True and the backup file already exists.
    """
    filename = Path(filename)
    if backup:
        if (backup_file := filename.parent / f'{filename.name}.bak').exists():
            raise ConvertError(ConvertError.BACKUP_EXISTS, file=backup_file)
        copy(filename, backup_file)

    with open(filename, 'rb') as stream:
        data = stream.read().replace(b'\r\n', b'\n')

    if mode == ConversionMode.to_dos:
        data = data.replace(b'\n', b'\r\n')
    with open(filename, 'wb') as stream:
        stream.write(data)


def pack(archive_file: PathName, items: Iterable, /, item_location: Optional[PathName] = None, *,  # pylint: disable=too-many-locals,too-many-branches
         archive_type: str = '', ignore_empty: bool = True) -> None:
    """Create a compressed archive.

    Attributes:
        archive_file: The name of the archive file to create.
        items: The items to put in the archive.
        item_location (optional, default=None): The root location of the items. If None, the current directory
        archive_type (optional, default=None): the type of archive to create.
            If None, the type is derived from the archive_file extension.
        ignore_empty (optional, default=True): If True, allows creating an empty archive.

    Returns:
        Nothing.

    Raises:
        PackError.NO_FILES: If ignore_empty is False and there are no files to place in the archive.
    """
    archive = Path(archive_file)
    archive_type = archive.suffix.lstrip('.') if not archive_type else archive_type

    if item_location:
        pushd(item_location)

    tar_name = Path()
    tar_bug = False
    pkg_file = None
    if archive_type == 'zip':
        pkg_file = PACKER_CLASSES[archive_type](archive, 'w', ZIP_DEFLATED)
        adder = 'write'
    else:
        if compression := COMPRESSION_TYPE.get(archive_type, ''):
            tar_name = archive.with_suffix('.tar')
            tar_bug = True
        else:
            tar_name = archive

        pkg_file = tar_open(tar_name, mode='w:' + compression)  # type: ignore[call-overload]  # pylint: disable=consider-using-with
        adder = 'add'

    added = False
    for glob_item in [Path(i) for i in items]:
        for item in glob_item.parent.glob(glob_item.name):
            added = True
            if (adder == 'write') and item.is_dir():
                for (root, _unused_dirs, files) in item.walk():
                    for files_name in files:
                        getattr(pkg_file, adder)(Path(root, files_name))
            else:
                getattr(pkg_file, adder)(item)
    pkg_file.close()
    if (not ignore_empty) and (not added):
        raise PackError(PackError.NO_FILES)

    if tar_bug:
        if archive.exists():
            archive.unlink()
        tar_name.rename(archive)

    if item_location:
        popd()


def prune(directory: PathName, age: int, exts: Optional[Iterable[str]] = None,
          force: bool = False, ignore_case: bool = False, log_handle: Optional[str] = None) -> None:
    """Prune a directory of files or directories based on age or count.

    Args:
        age: The number days after which to prune files.
        directory: The directory from which to prune files.
        exts (optional, default=all): The extensions to prune.
        force (optional, default=False): If true, ignore permissions restricting removal.
        ignore_case (optional, default=False): If true, ignore case in extensions.
        log_handle (optional, default=None): If not None, status will be logged to the specified log handle.

    Returns:
        Nothing.
    """
    logger = getLogger(log_handle) if log_handle else None
    age_from = time()
    ext_list = [ext.lower() for ext in exts] if (exts and ignore_case) else exts
    target = Path(directory)
    if logger:
        logger.info('Removing %s in %s older than %d days',
                    ('/'.join(exts) + ' files') if exts else 'all', directory, age)
    if force:
        current_mode = target.stat().st_mode
        target.chmod(S_IRWXU)
    for item in target.iterdir():
        item_ext = item.suffix
        if ignore_case:
            item_ext = item_ext.lower()
        if (ext_list and (item_ext not in ext_list)) or not item.is_file():
            continue

        item_age = abs(int((age_from - item.stat().st_mtime) / 86400))
        if item_age > age:
            if logger:
                logger.info('  removing %s...', item.name)
            if force:
                item.chmod(S_IRWXU)
            item.unlink()
    if force:
        target.chmod(current_mode)


def slurp(filename: PathName, /) -> List[str]:
    """Return all the lines of a file as a list.

    Args:
        filename: The filename to return the lines from.

    Returns:
        The list of lines from the file.
    """
    return list(open(filename, encoding=DEFAULT_ENCODING))


def spew(filename: PathName, outlines: Iterable, /) -> None:
    """Write the list of lines to a file.

    Args:
        filename: The filename to which to write the lines.
        outlines: The lines to write.

    Returns:
        Nothing.
    """
    with open(filename, 'w', encoding=DEFAULT_ENCODING) as output_stream:
        output_stream.writelines(outlines)


def unpack(archive_file: PathName, dest: Optional[PathName] = None, /, *, archive_type: str = '') -> None:
    """Extract the contents of a compressed file.

    Attributes:
        archive_file: The name of the archive file
        dest (optional, default=None): The root location to which to extract. If None, the current directory
        archive_type (optional, default=None): the type of archive being extracted.
            If None, the type is derived from the archive_file extension.

    Returns:
        Nothing.

    Raises:
        PackError.INVALID_TYPE: If the archive_type is unknown.
    """
    archive = Path(archive_file).resolve()
    if not archive_type:
        archive_type = 'tar' if ('.tar.' in archive.name) else archive.suffix.lstrip('.')

    if dest:
        use_dest = Path(dest)
        use_dest.mkdir(parents=True, exist_ok=True)
        pushd(use_dest)

    lister = extractor = ''
    pkg_file: Any = None
    match archive_type:
        case 'bz2' | 'gz' | 'xz' | 'zip':
            pkg_file = PACKER_CLASSES[archive_type](archive)
            lister = 'namelist'
            extractor = 'read'
        case 'tar':
            pkg_file = tar_open(archive)  # pylint: disable=consider-using-with
            lister = 'getmembers'
            extractor = 'extract'
        case _:
            raise PackError(PackError.INVALID_TYPE, arc_type=archive_type)

    for member_info in getattr(pkg_file, lister)():
        member_path = Path(member_info.name if (archive_type == 'tar') else member_info)
        data = getattr(pkg_file, extractor)(member_info)
        if extractor == 'read':
            member_path.parent.mkdir(parents=True, exist_ok=True)
            if not (member_path.is_dir() or member_info.endswith('/')):
                with open(member_path, 'wb') as member_file:
                    member_file.write(data)
    pkg_file.close()

    if dest:
        popd()

# cSpell:ignore topdown
