'Setuptools setup script for BatCave'
# cSpell:ignore aarch, bldverfile, cxfreeze, psutil, pyodbc, pywin

from distutils.version import LooseVersion  # pylint: disable=import-error,no-name-in-module
from pathlib import Path
from sys import version_info

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
PYTHON_VERSION = LooseVersion('.'.join([str(i) for i in version_info]))
CXFREEZE_MAX_WIN_VERSION = LooseVersion('3.7')

DEPENDENCIES = ['docker==4.0.2', 'GitPython==3.0.2', 'google-cloud==0.34.0', 'psutil==5.6.3', 'pyodbc==4.0.27',
                'requests==2.22.0', 'setuptools==41.2.0', 'unittest-xml-reporting==2.5.1', 'WMI==1.4.9']
if SYS_PLATFORM == 'win32':
    DEPENDENCIES += ['pywin32==225']

if (SYS_PLATFORM != 'win32') or (PYTHON_VERSION < CXFREEZE_MAX_WIN_VERSION):
    DEPENDENCIES += ['cx-Freeze==6.0']

if not SYS_PLATFORM.endswith('aarch64'):
    DEPENDENCIES += ['PyQt5==5.13.1']

setup(
    name=batcave.__title__,

    # Versions should comply with PEP440.  For a discussion on single-sourcing
    # the version across setup.py and the project code, see
    # https://packaging.python.org/en/latest/single_source_version.html
    version=batcave.__version__,

    description=batcave.__summary__,
    long_description=''.join(slurp(Path(__file__).parent / 'README.rst')),
    long_description_content_type='text/markdown',

    # The project's main homepage.
    url=batcave.__uri__,

    # Author details
    author=batcave.__author__,
    author_email=batcave.__email__,

    # Choose your license
    license=batcave.__license__,

    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        # How mature is this project? Common values are
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        'Development Status :: 5 - Production/Stable',

        # Indicate who your project is intended for
        'Intended Audience :: Developers',
        'Topic :: Software Development',
        'Natural Language :: English',
        'Operating System :: OS Independent',

        # Pick your license as you wish (should match "license" above)
        'License :: OSI Approved :: MIT License',

        # Specify the Python versions you support here. In particular, ensure
        # that you indicate whether you support Python 2, Python 3 or both.
        'Programming Language :: Python :: 3.6',
    ],

    # What does your project relate to?
    keywords='python programming utilities',

    # You can just specify the packages manually here if your project is
    # simple. Or you can use find_packages().
    packages=find_packages(),

    # List run-time dependencies here.  These will be installed by pip when your
    # project is installed. For an analysis of "install_requires" vs pip's
    # requirements files see:
    # https://packaging.python.org/en/latest/requirements.html
    install_requires=DEPENDENCIES,
    python_requires='>=3.6',

    # List additional groups of dependencies here (e.g. development dependencies).
    # You can install these using the following syntax, for example:
    # $ pip install -e .[dev,test]
    extras_require={
        'dev': ['xmlrunner', 'wheel', 'twine'],
        'test': [],
    },

    # If there are data files included in your packages that need to be
    # installed, specify them here.  If using Python 2.6 or less, then these
    # have to be included in MANIFEST.in as well.
    package_data={},

    # Although 'package_data' is the preferred approach, in some case you may
    # need to place data files outside of your packages.
    # see http://docs.python.org/3.4/distutils/setupscript.html#installing-additional-files
    # In this case, 'data_file' will be installed into '<sys.prefix>/my_data'
    data_files=[],

    # To provide executable scripts, use entry points in preference to the
    # "scripts" keyword. Entry points provide cross-platform support and allow
    # pip to create the appropriate form of executable for the target platform.
    entry_points={}
)
