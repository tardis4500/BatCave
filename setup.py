'Setuptools setup script for BatCave'
# cSpell:ignore aarch, psutil pywin

from pathlib import Path
from setuptools import find_packages, setup  # Always prefer setuptools over distutils

import batcave
from batcave.fileutil import slurp
from batcave.sysutil import chmod, S_775

# The files need to be writable
chmod(Path.cwd(), S_775, True)

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
    install_requires=['docker >= 4.0',
                      'GitPython >= 3.0',
                      'google-cloud',
                      'PyQt5 >= 5.13; platform_machine != "aarch64"',
                      'psutil >= 5.6',
                      'pywin32 >= 225; sys_platform == "win32"',
                      'requests >= 2.22',
                      'WMI >= 1.4'],
    extras_require={
        'dev': ['setuptools', 'twine', 'wheel', 'xmlrunner'],
        'test': [],
    }
)
