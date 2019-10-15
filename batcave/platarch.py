'module to return information about platforms and architectures'

# Import standard modules
from pathlib import Path
from platform import uname
from sys import version_info

# Import internal modules
from .lang import switch


class Platform:
    'A class from which information about the platform can be queried'
    def __getattr__(self, attr):
        'Get the platform type formatted for the requested subtype'
        sys_info = uname()
        hal_os = bart_os = sys_info.system.replace('-', '')
        p4_arch = du_os = ''
        for case in switch(hal_os):
            if case('AIX'):
                hal_version = bart_version = sys_info.version + sys_info.release
                halarch = bartarch = 'ppc'
                build = f'{sys_info.system} {sys_info.version}.{sys_info.release} PowerPC'
                p4ver = hal_version
                break

            if case('HPUX'):
                os_major = sys_info.release.split('.')[1]
                os_minor = sys_info.release.split('.')[2]
                hal_version = bart_version = os_major + os_minor
                halarch = bartarch = sys_info.machine.split('/')[0]
                build = f'{sys_info.system} {sys_info.release} {sys_info.machine}'
                p4ver = os_major
                break

            if case('Linux'):
                hal_version = bart_version = sys_info.release.split('.')[0] + sys_info.release.split('.')[1]
                bartarch = sys_info.machine
                if sys_info.machine == 'x86_64':
                    halarch = 'i686'
                else:
                    halarch = sys_info.machine
                try:
                    build = open([f for f in Path('/etc').glob('*-release')][0]).readline().strip()
                except IndexError:
                    build = 'unknown'

                p4ver = hal_version
                p4_arch = sys_info.processor.replace(' ', '_')
                if p4_arch in ('i686', 'i386', 'athalon'):
                    p4_arch = 'x86'
                break

            if case('Darwin'):
                hal_version = bart_version = sys_info.release.split('.')[0] + sys_info.release.split('.')[1]
                halarch = bartarch = sys_info.machine
                build = f'{sys_info.system} {sys_info.release} {sys_info.machine}'
                p4ver = '80'
                p4_arch = sys_info.processor.replace(' ', '_')
                if p4_arch in ('i686', 'i386', 'athalon'):
                    p4_arch = 'x86'
                break

            if case('Windows'):
                (hal_version, halarch, p4ver, bart_version, bartarch) = ('',) * 5
                hal_os = 'win32'
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
                return hal_os + hal_version + halarch
            if case('batcave_build'):
                return build
            if case('p4'):
                return '%s%s%s' % (hal_os.lower().replace('windows', 'nt'), p4ver, p4_arch)
