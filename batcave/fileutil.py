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
from lzma import LZMAFile
from os import walk
from pathlib import Path
from shutil import copy
from string import Template
from tarfile import open as tar_open
from typing import Any, Iterable, List, Optional, Tuple
from zipfile import ZipFile, ZIP_DEFLATED

# Import internal modules
from .sysutil import popd, pushd
from .lang import switch, BatCaveError, BatCaveException, PathName


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
    INVALID_TYPE = BatCaveError(1, Template('Unknown archive type: $arctype'))
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
        if (backupfile := filename.parent / f'{filename.name}.bak').exists():
            raise ConvertError(ConvertError.BACKUP_EXISTS, file=backupfile)
        copy(filename, backupfile)

    with open(filename, 'rb') as stream:
        data = stream.read().replace(b'\r\n', b'\n')

    if mode == ConversionMode.to_dos:
        data = data.replace(b'\n', b'\r\n')
    with open(filename, 'wb') as stream:
        stream.write(data)


def pack(arcfile: PathName, items: Iterable, /, itemloc: Optional[PathName] = None, *, arctype: str = '', ignore_empty: bool = True) -> None:  # pylint: disable=too-many-locals,too-many-branches
    """Create a compressed archive.

    Attributes:
        arcfile: The name of the archive file to create.
        items: The items to put in the archive.
        itemloc (optional, default=None): The root location of the items. If None, the current directory
        arctype (optional, default=None): the type of archive to create.
            If None, the type is dervied from the arcfile extension.
        ignore_empty (optional, default=True): If True, allows creating an empty archive.

    Returns:
        Nothing.

    Raises:
        PackError.NO_FILES: If ignore_empty is False and there are no files to place in the archive.
    """
    archive = Path(arcfile)
    arctype = archive.suffix.lstrip('.') if not arctype else arctype

    if itemloc:
        pushd(itemloc)

    tar_name = Path()
    tarbug = False
    pkgfile = None
    if arctype == 'zip':
        pkgfile = PACKER_CLASSES[arctype](archive, 'w', ZIP_DEFLATED)
        adder = 'write'
    else:
        if compression := COMPRESSION_TYPE.get(arctype, ''):
            tar_name = archive.with_suffix('.tar')
            tarbug = True
        else:
            tar_name = archive

        pkgfile = tar_open(tar_name, 'w:' + compression)
        adder = 'add'

    added = False
    for glob_item in [Path(i) for i in items]:
        for item in glob_item.parent.glob(glob_item.name):
            added = True
            if (adder == 'write') and item.is_dir():
                for (root, _unused_dirs, files) in walk(item):
                    for files_name in files:
                        getattr(pkgfile, adder)(Path(root, files_name))
            else:
                getattr(pkgfile, adder)(item)
    pkgfile.close()
    if (not ignore_empty) and (not added):
        raise PackError(PackError.NO_FILES)

    if tarbug:
        if archive.exists():
            archive.unlink()
        tar_name.rename(archive)

    if itemloc:
        popd()


def slurp(filename: PathName, /) -> List[str]:
    """Return all the lines of a file as a list.

    Args:
        filename: The filename to return the lines from.

    Returns:
        The list of lines from the file.
    """
    return [line for line in open(filename)]  # pylint: disable=unnecessary-comprehension


def spew(filename: PathName, outlines: Iterable, /) -> None:
    """Write the list of lines to a file.

    Args:
        filename: The filename to which to write the lines.
        outlines: The lines to write.

    Returns:
        Nothing.
    """
    open(filename, 'w').writelines(outlines)


def unpack(arcfile: PathName, dest: Optional[PathName] = None, /, *, arctype: str = '') -> None:
    """Extract the contents of a compressed file.

    Attributes:
        arcfile: The name of the archive file
        dest (optional, default=None): The root location to which to extract. If None, the current directory
        arctype (optional, default=None): the type of archive being extracted.
            If None, the type is dervied from the arcfile extension.

    Returns:
        Nothing.

    Raises:
        PackError.INVALID_TYPE: If the arctype is unknown.
    """
    archive = Path(arcfile).resolve()
    if not arctype:
        arctype = 'tar' if ('.tar.' in archive.name) else archive.suffix.lstrip('.')

    if dest:
        use_dest = Path(dest)
        use_dest.mkdir(parents=True, exist_ok=True)
        pushd(use_dest)

    lister = extractor = ''
    pkgfile: Any = None
    for case in switch(arctype):
        if case('bz2', 'gz', 'xz', 'zip'):
            pkgfile = PACKER_CLASSES[arctype](archive)
            lister = 'namelist'
            extractor = 'read'
            break
        if case('tar'):
            pkgfile = tar_open(archive)
            lister = 'getmembers'
            extractor = 'extract'
            break
        if case():
            raise PackError(PackError.INVALID_TYPE, arctype=arctype)

    for member_info in getattr(pkgfile, lister)():
        member_path = Path(member_info.name if (arctype == 'tar') else member_info)
        data = getattr(pkgfile, extractor)(member_info)
        if extractor == 'read':
            member_path.parent.mkdir(parents=True, exist_ok=True)
            if not (member_path.is_dir() or member_info.endswith('/')):
                with open(member_path, 'wb') as member_file:
                    member_file.write(data)
    pkgfile.close()

    if dest:
        popd()
