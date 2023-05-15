"""This module provides utilities for working with versions.

Attributes:
    PYQT_LOADED (bool/str): If not False then it is the string version of the PyQt API.
    VersionStyle (Enum): The version output styles.
"""

# Import standard modules
from enum import Enum
from sys import version as sys_version

# Import third-party modules
try:
    import PyQt5.QtCore as pyqt
except ImportError:
    PYQT_LOADED = ''
else:
    PYQT_LOADED = pyqt.__dict__['PYQT_VERSION_STR']

# Import internal modules
from . import __copyright__, __title__, __version__, __build_date__, __build_name__
from .platarch import Platform

VersionStyle = Enum('VersionStyle', ('full', 'brief', 'one_line', 'about_box'))


def get_version_info(style: VersionStyle = VersionStyle.full, /, plattype: str = 'batcave_run', extra_info: str = '') -> str:
    """Get the version information about the currently running application.

    Args:
        style (optional, default=full): The format for the version string to be returned.
        plattype (optional, default='batcave_run'): The platform type for the architecture information in the version string.
        extra_info (optional, default=''): A line to append after the version info but before the copyright.

    Returns:
        Returns the version string.
    """
    plat = getattr(Platform(), plattype)
    if style == VersionStyle.brief:
        return f'{__title__} {__version__}{extra_info} on {plat}'
    if style == VersionStyle.one_line:
        return f'{__title__} {__version__}{extra_info} (Build: {__build_name__}) [{__build_date__}] on {plat}'

    info = ['' if (style == VersionStyle.about_box) else f'{__title__} {__version__}',
            'Build: ' + __build_name__,
            'Date: ' + __build_date__,
            'Platform: ' + plat,
            'Python Version: ' + sys_version]
    if PYQT_LOADED:
        info.append('PyQt Version: ' + PYQT_LOADED)
    from . import cms  # pylint: disable=import-outside-toplevel
    if cms.P4_LOADED or cms.GIT_LOADED:
        info.append('CMS Support:')
        if cms.P4_LOADED:
            info.append('    P4Python: ' + cms.P4_LOADED)
        if cms.GIT_LOADED:
            info.append('    GitPython API: ' + cms.GIT_LOADED)
    if extra_info:
        info += [extra_info]
    info.append(__copyright__)
    return '\n'.join(info)

# cSpell:ignore pyqt batcave platarch plattype
