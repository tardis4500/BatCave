"""This module provides utilities for working with files.

Attributes:
    ConversionMode (Enum): The conversion modes for the eol_convert function.
    PACKER_CLASSES (dict): A mapping of file compression extensions to the classes that create them.
    COMPRESSION_TYPE (dict): A mapping of file compression extensions to compression types.
"""

# Import standard modules
from bz2 import BZ2File
from enum import Enum
from errno import EACCES
from gzip import GzipFile
from lzma import LZMAFile
from os import walk
from pathlib import Path
from shutil import copy
from stat import S_IRWXU
from string import Template
from sys import stderr
from tarfile import open as tar_open
from time import time
from typing import Any, Dict, Iterable, List, Optional, Tuple
from zipfile import ZipFile, ZIP_DEFLATED

# Import internal modules
from .sysutil import popd, pushd, rmtree, rmtree_hard
from .lang import DEFAULT_ENCODING, BatCaveError, BatCaveException, PathName, xor


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

        pkg_file = tar_open(tar_name, 'w:' + compression)  # pylint: disable=consider-using-with
        adder = 'add'

    added = False
    for glob_item in [Path(i) for i in items]:
        for item in glob_item.parent.glob(glob_item.name):
            added = True
            if (adder == 'write') and item.is_dir():
                for (root, _unused_dirs, files) in walk(item):
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


def prune(directory: PathName, *, age: Optional[int] = None, count: Optional[int] = None, exts: Optional[List[str]] = None,  # pylint: disable=too-many-locals
          recurse: bool = False, force: bool = False, directories: bool = False, ignore_case: bool = False, quiet: bool = False) -> None:
    """Recursively prune a directory of files or directories based on age or count.

    Args:
        directory: The directory from which to prune files.
        Exactly one of these must be specified:
            age (optional): The number days after which to prune files.
            count (optional): The number of files to prune.
        directories (optional, default=False): If true, remove directories also.
        exts (optional, default=all): The extensions to prune.
        force (optional, default=False): If true, ignore permissions restricting removal.
        ignore_case (optional, default=False): If true, ignore case in extensions.
        quiet (optional, default=False): If true, print status during pruning.
        recurse (optional, default=False): If true, recurse into subdirectories.

    Returns:
        Nothing.

    Raises:
        ValueError: If exactly one of age or count are not specified.
    """
    if not xor(age, count):
        raise ValueError('Exactly one of age or count must be specified.')
    exts = ([e.lower() for e in exts] if ignore_case else exts) if exts else []
    age_from = time()

    if not quiet:
        info = f'{age} days' if (count is None) else f'a count of {count}'
        remove_what = 'directories' if directories else (('/'.join(exts) + ' files') if exts else 'all')
        remove_also = ' and subdirectories' if recurse else ''
        print(f'Removing {remove_what} in {directory}{remove_also} older than {info}')

    if recurse:
        for (dirpath, dirnames, filenames) in walk(directory, topdown=False):
            prune_in_directory(dirpath, [Path(f) for f in (dirnames + filenames)], age_from, age=age, count=count, exts=exts,
                               force=force, directories=directories, ignore_case=ignore_case, quiet=quiet)
    else:
        prune_in_directory(directory, list(Path(directory).iterdir()), age_from, age=age, count=count, exts=exts,
                           force=force, directories=directories, ignore_case=ignore_case, quiet=quiet)


def prune_in_directory(directory: PathName, items: List[PathName], age_from: float, *, age: Optional[int] = None, count: Optional[int] = None,  # pylint: disable=too-many-locals,too-many-branches
                       exts: Optional[List[str]] = None, force: bool = False, directories: bool = False, ignore_case: bool = False, quiet: bool = False) -> None:
    """Prune a directory of files or directories based on age or count.

    Args:
        directory: The directory from which to prune files.
        age_from: The date from which to prune.
        Exactly one of these must be specified:
            age (optional): The number days after which to prune files.
            count (optional): The number of files to prune.
        directories (optional, default=False): If true, remove directories also.
        exts (optional, default=all): The extensions to prune.
        force (optional, default=False): If true, ignore permissions restricting removal.
        ignore_case (optional, default=False): If true, ignore case in extensions.
        quiet (optional, default=False): If true, print status during pruning.

    Returns:
        Nothing.

    Raises:
        ValueError: If exactly one of age or count are not specified.
    """
    if not xor(age is not None, count is not None):
        raise ValueError('Exactly one of age or count must be specified.')
    directory = Path(directory)
    items_to_remove = []
    item_candidates: Dict[float, List[Path]] = {}
    for item in items:
        item_path = directory / item
        if not directories:
            if not item_path.is_file():
                continue
            item_ext = Path(item).suffix
            if ignore_case:
                item_ext = item_ext.lower()
            if not exts:
                exts = [item_ext]
            if item_ext not in exts:
                continue
        elif not item_path.is_dir():
            continue

        item_age = abs(int((age_from - item_path.stat().st_mtime) / 86400))
        if age is not None:
            if item_age > age:
                items_to_remove.append(item_path)
        else:
            if item_age not in item_candidates:
                item_candidates[item_age] = []
            item_candidates[item_age].append(item_path)

    if count is not None:
        for count_item in sorted(item_candidates.keys(), reverse=True)[count:]:
            items_to_remove += item_candidates[count_item]

    for item in items_to_remove:
        if not quiet:
            print(f"  removing {'directory' if directories else 'file'} {item.name} in {directory}...")
        try:
            if force:
                item.chmod(S_IRWXU)
            if item.is_dir():
                if force:
                    rmtree_hard(item)
                else:
                    rmtree(item)
            else:
                item.unlink()
        except OSError as err:
            if err.errno == EACCES:
                print('unable to remove: no permission', file=stderr)


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
