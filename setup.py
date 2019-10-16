'Setuptools setup script for BatCave'
# cSpell:ignore aarch, psutil pywin

from pathlib import Path
from setuptools import find_packages, setup  # Always prefer setuptools over distutils

import batcave
from batcave.fileutil import slurp
from batcave.platarch import Platform
from batcave.sysutil import chmod, S_775

# The files need to be writable
chmod(Path.cwd(), S_775, True)

# Platform specific dependencies
# p4python must be installed on Linux with additional arguments: --install-option="-ssl" --install-option="/usr/lib"
SYS_PLATFORM = Platform().batcave_run
DEPENDENCIES = ['docker >= 4.0', 'GitPython >= 3.0', 'google-cloud', 'psutil >= 5.6', 'requests >= 2.22', 'WMI >= 1.4']
if SYS_PLATFORM == 'win32':
    DEPENDENCIES += ['pywin32 >= 225']

if not SYS_PLATFORM.endswith('aarch64'):
    DEPENDENCIES += ['PyQt5 >= 5.13']

setup(
    name=batcave.__title__,
    version=batcave.__version__,

    description=batcave.__summary__,
    long_description=''.join(slurp(Path(__file__).parent / 'README.rst')),
    keywords='python programming utilities',

    author=batcave.__author__,
    author_email=batcave.__email__,
    license=batcave.__license__,

    url=batcave.__uri__,
    # project_urls={
    #     'Documentation': 'https://gitlab.com/arisilon/batcave/',
    # },

    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: MIT License',

        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.6',

        'Intended Audience :: Developers',
        'Topic :: Software Development',
        'Natural Language :: English',
    ],

    python_requires='>=3.6',
    packages=find_packages(),
    install_requires=DEPENDENCIES,
    extras_require={
        'dev': ['setuptools', 'twine', 'wheel', 'xmlrunner'],
        'test': [],
    }
)
