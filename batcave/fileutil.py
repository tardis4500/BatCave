'Module with file utilities.'
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
from zipfile import ZipFile, ZIP_DEFLATED

# Import internal modules
from .sysutil import popd, pushd
from .lang import switch, HALError, HALException


class ConvertError(HALException):
    'Error class for conversion errors'
    BACKUP_EXISTS = HALError(1, Template('$file already exists'))


class PackError(HALException):
    'Error class for packing errors'
    NO_FILES = HALError(1, 'No files to add')
    UNKNOWN_ARCHIVE = HALError(2, Template('Unknown archive type: $arctype'))


CONVERSION_MODES = Enum('conversion_modes', ('to_unix', 'to_dos'))


def eol_convert(filename, mode, backup=True):
    'Performs end-of-line conversion.'
    if backup:
        backupfile = Path(filename + '.bak')
        if backupfile.exists():
            raise ConvertError(ConvertError.BACKUP_EXISTS, file=backupfile)
        copy(filename, backupfile)

    with open(filename, 'rb') as stream:
        data = stream.read().replace(b'\r\n', b'\n')

    if mode == CONVERSION_MODES.to_dos:
        data = data.replace(b'\n', b'\r\n')
    with open(filename, 'wb') as stream:
        stream.write(data)


class CompressedFile:
    'Class to wrap the different compression file types'
    def __init__(self, filename, **attr):
        super().__init__(filename, **attr)
        self._filename = Path(filename)

    def namelist(self):
        'Returns the name of the file as the first item in a tuple.'
        return (self._filename.stem,)


class BatCaveGzipFile(GzipFile, CompressedFile):
    'Class to support gzip file'


class BatCaveBZ2File(BZ2File, CompressedFile):
    'Class to support bzip2 file'


PACKER_CLASSES = {'zip': ZipFile, 'gz': BatCaveGzipFile, 'bz2': BatCaveBZ2File, 'xz': LZMAFile}
COMPRESSION_TYPE = {'gz': 'gz', 'tgz': 'gz',
                    'bz': 'bz2', 'tbz': 'bz2', 'bz2': 'bz2',
                    'xz': 'xz', 'txz': 'xz'}


def pack(arcfile, items, itemloc=None, arctype=None, ignore_empty=True):
    'Creates a compressed archive.'
    archive = Path(arcfile)
    arctype = archive.suffix.lstrip('.') if not arctype else arctype

    if itemloc:
        pushd(itemloc)

    tarbug = False
    pkgfile = None
    if arctype == 'zip':
        pkgfile = PACKER_CLASSES[arctype](archive, 'w', ZIP_DEFLATED)
        adder = 'write'
    else:
        compression = COMPRESSION_TYPE.get(arctype, '')

        if compression:
            tar_name = archive.with_suffix('.tar')
            tarbug = True
        else:
            tar_name = archive

        pkgfile = tar_open(tar_name, 'w:'+compression)
        adder = 'add'

    added = False
    for glob_item in [Path(i) for i in items]:
        for item in glob_item.parent.glob(glob_item.name):
            added = True
            if (adder == 'write') and item.is_dir():
                for (root, dirs, files) in walk(item):  # pylint: disable=W0612
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


def unpack(arcfile, dest=None, arctype=None):
    'Extracts the contents of a compressed file.'
    archive = Path(arcfile).resolve() if isinstance(arcfile, str) else arcfile
    if dest:
        dest = Path(dest)
    if not arctype:
        arctype = 'tar' if ('.tar.' in archive.name) else archive.suffix.lstrip('.')

    if dest:
        dest.mkdir(parents=True, exist_ok=True)
        pushd(dest)

    pkgfile = None
    for case in switch(arctype):
        if case('bz2', 'gz', 'xz', 'zip'):
            pkgfile = PACKER_CLASSES[arctype](archive)
            lister = 'namelist'
            extractor = 'read'
            break
        if case('tar'):
            pkgfile = tar_open(archive) if isinstance(archive, Path) else tar_open(fileobj=archive)
            lister = 'getmembers'
            extractor = 'extract'
            break
        if case():
            raise PackError(PackError.UNKNOWN_ARCHIVE, arctype=arctype)

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


def slurp(filename):
    'Return all the lines of a file as a list.'
    return [l for l in open(filename)]


def spew(filename, outlines):
    'Write the list of lines to a file.'
    open(filename, 'w').writelines(outlines)
