'Version interface'
# cSpell:ignore pyqt

# Import standard modules
from enum import Enum
from sys import version as sys_version

# Import internal modules
from . import __title__, __version__, __builddate__, __buildname__
from .lang import COPYRIGHT
from .platarch import Platform

VERSION_STYLES = Enum('version_styles', ('full', 'brief', 'oneline', 'aboutbox'))


# Import third-party modules
try:
    import PyQt5.QtCore as pyqt
except ImportError:
    PYQT_LOADED = False
else:
    PYQT_LOADED = pyqt.__dict__['PYQT_VERSION_STR']


def get_version_info(style=VERSION_STYLES.full, plattype='batcave_run', extra_info=''):
    'Returns the version information about the currently running application'
    plat = getattr(Platform(), plattype)
    if style == VERSION_STYLES.brief:
        return f'{__title__} {__version__}{extra_info} on {plat}'
    if style == VERSION_STYLES.oneline:
        return f'{__title__} {__version__}{extra_info} (Build: {__buildname__}) [{__builddate__}] on {plat}'

    info = ['' if (style == VERSION_STYLES.aboutbox) else f'{__title__} {__version__}',
            'Build: ' + __buildname__,
            'Date: ' + __builddate__,
            'Platform: ' + plat,
            'Python Version: ' + sys_version]
    if PYQT_LOADED:
        info.append('PyQt Version: ' + PYQT_LOADED)
    from . import cms
    if cms.P4_LOADED or cms.GIT_LOADED:
        info.append('CMS Support:')
        if cms.P4_LOADED:
            info.append('    P4Python: ' + cms.P4_LOADED)
        if cms.GIT_LOADED:
            info.append('    GitPython API: ' + cms.GIT_LOADED)
    if extra_info:
        info += [extra_info]
    info.append(COPYRIGHT)
    return '\n'.join(info)
