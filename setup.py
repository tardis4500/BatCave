"""Setuptools setup script for BatCave."""

# cSpell:ignore aarch, psutil pywin

from pathlib import Path
from setuptools import find_packages, setup  # Always prefer setuptools over distutils

import batcave
from batcave.fileutil import slurp
from batcave.sysutil import chmod, S_775

# The files need to be writable
chmod(Path.cwd(), S_775, recursive=True)

setup(
    name=batcave.__title__,
    version=batcave.__version__,

    description=batcave.__summary__,
    long_description=''.join(slurp(Path(__file__).parent / 'DOCUMENTATION.md')),
    long_description_content_type='text/markdown',
    keywords='python programming utilities',

    author=batcave.__author__,
    author_email=batcave.__email__,
    license=batcave.__license__,

    url=batcave.__uri__,
    project_urls={
        'Documentation': 'https://batcave.readthedocs.io',
    },

    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: MIT License',

        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.8',

        'Intended Audience :: Developers',
        'Topic :: Software Development',
        'Natural Language :: English',
    ],

    python_requires='~=3.8',
    packages=find_packages(),
    install_requires=['docker ~= 4.4',
                      'GitPython ~= 3.1',
                      'google-cloud',
                      'kubernetes ~= 12.0',
                      'requests ~= 2.25',
                      'pypiwin32 == 223; sys_platform == "win32"',
                      'pywin32 >= 227; sys_platform == "win32"',
                      'WMI ~= 1.5; sys_platform == "win32"',
                      'psutil ~= 5.8; platform_machine not in "arm arm64 armv6l armv7l armv8b armv8l"',
                      'PyQt5 ~= 5.15; platform_machine not in "aarch64 aarch64_be arm arm64 armv6l armv7l armv8b armv8l"'],
    extras_require={
        'dev': ['setuptools', 'twine', 'wheel', 'xmlrunner'],
        'test': []},
    package_data={'batcave': ['py.typed']}
)

# cSpell:ignore armv pypiwin
