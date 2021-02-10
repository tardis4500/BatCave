"""This module provides a simplified interface to the standard platform module."""
# pylint: disable-all

# Import standard modules
from enum import Enum
from pathlib import Path
from platform import uname
from sys import version_info

# Import internal modules
from .lang import switch

OsType = Enum('OsType', ('linux', 'windows'))


class Platform:
    """A class to provide a simplified interface to the platform and sys.version_info standard modules."""

    def __getattr__(self, attr: str) -> str:
        """Get the platform type formatted for the requested subtype."""
        sys_info = uname()
        batcave_os = bart_os = sys_info.system.replace('-', '')
        batcave_version = batcave_arch = ''
        bart_version = bartarch = ''
        p4ver = p4_arch = du_os = build = ''
        for case in switch(batcave_os):
            if case('AIX'):
                batcave_version = bart_version = sys_info.version + sys_info.release
                batcave_arch = bartarch = 'ppc'
                build = f'{sys_info.system} {sys_info.version}.{sys_info.release} PowerPC'
                p4ver = batcave_version
                break

            if case('HPUX'):
                os_major = sys_info.release.split('.')[1]
                os_minor = sys_info.release.split('.')[2]
                batcave_version = bart_version = os_major + os_minor
                batcave_arch = bartarch = sys_info.machine.split('/')[0]
                build = f'{sys_info.system} {sys_info.release} {sys_info.machine}'
                p4ver = os_major
                break

            if case('Linux'):
                batcave_version = bart_version = sys_info.release.split('.')[0] + sys_info.release.split('.')[1]
                bartarch = sys_info.machine
                if sys_info.machine == 'x86_64':
                    batcave_arch = 'i686'
                else:
                    batcave_arch = sys_info.machine
                try:
                    build = open([f for f in Path('/etc').glob('*-release')][0]).readline().strip()
                except IndexError:
                    build = 'unknown'

                p4ver = batcave_version
                if (p4_arch := sys_info.processor.replace(' ', '_')) in ('i686', 'i386', 'athalon'):
                    p4_arch = 'x86'
                break

            if case('Darwin'):
                batcave_version = bart_version = sys_info.release.split('.')[0] + sys_info.release.split('.')[1]
                batcave_arch = bartarch = sys_info.machine
                build = f'{sys_info.system} {sys_info.release} {sys_info.machine}'
                p4ver = '80'
                if (p4_arch := sys_info.processor.replace(' ', '_')) in ('i686', 'i386', 'athalon'):
                    p4_arch = 'x86'
                break

            if case('Windows'):
                (batcave_version, batcave_arch, p4ver, bart_version, bartarch) = ('',) * 5
                batcave_os = 'win32'
                du_os = 'win'
                if sys_info.machine.endswith('64'):
                    p4_arch = 'x64'
                    bart_os = 'win64'
                else:
                    p4_arch = 'x86'
                    bart_os = 'win32'
                build = f'{sys_info.system} {sys_info.release} {p4_arch[1:]}-bit ({sys_info.version})'
                break

        for case in switch(attr):
            if case('bart'):
                return bart_os + bart_version + bartarch
            if case('distutils'):
                return '%s-%s-%s' % (du_os, uname().machine.lower(), '.'.join([str(i) for i in version_info[:2]]))
            if case('batcave_run'):
                return batcave_os + batcave_version + batcave_arch
            if case('batcave_build'):
                return build
            if case('p4'):
                return '%s%s%s' % (batcave_os.lower().replace('windows', 'nt'), p4ver, p4_arch)
        raise AttributeError(f'Unknown platform type: {attr}')
