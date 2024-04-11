"""BatCave Utilities module.

This module provides utilities for making it easier to write Python programs.

The exported modules fall into several categories:

Modules that provide simplified interfaces to standard modules:
    * commander - argparse
    * platarch - platform

Modules that provide simplified interfaces to third-party modules:
    * gui - PyQt5
    * k8s - kubernetes

Modules that provide Pythonic interfaces to external systems:
    * cloudmgr - cloud resources
    * cms - code management systems
    * data - data sources
    * iispy - Internet Information Server
    * netutil - network services
    * qbpy - QuickBuild
    * servermgr - OS-independent servers
    * sysutil - system utilities
    * tcpy - TeamCity

Modules that provide utilities for accomplishing specific programming tasks:
    * automation - building automation
    * configmgr - managing configurations
    * expander - working with string expansion
    * fileutil - working with files
    * lang - Python language utilities
    * menu - creating command line menus
    * statemachine - a simple state machine
    * reporter - creating reports
    * version - reporting version information
"""

__all__ = ('__title__', '__summary__', '__uri__',
           '__version__', '__build_name__', '__build_date__',
           '__author__', '__email__',
           '__license__', '__copyright__')

__title__ = 'BatCave'
__summary__ = 'Python Programming Toolkit'
__uri__ = 'https://github.com/tardis4500/batcave/'

__version__ = '43.2.3'
__build_name__ = '{var:build_name}'
__build_date__ = '{var:build_date}'

__author__ = 'Jeffery G. Smith'
__email__ = 'web@pobox.com'

__license__ = 'MIT'
__copyright__ = 'Copyright (c) 2023 Jeffery G. Smith'

# cSpell:ignore iispy netutil qbpy tcpy platarch cloudmgr servermgr configmgr fileutil statemachine
