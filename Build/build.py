#!/usr/bin/env python
'This programs drives the build and release automation'
# cSpell:ignore bdist, bldverfile, sdist

# Import standard modules
from datetime import datetime
from distutils.core import run_setup
from importlib import import_module, reload
import os
from pathlib import Path
from shutil import copyfile
from stat import S_IWUSR
import sys
from unittest import defaultTestLoader

# Import third-party-modules
from twine.commands.upload import main as upload
from xmlrunner import XMLTestRunner

PROJECT_ROOT = Path(os.path.abspath(os.pardir))
sys.path.insert(0, str(PROJECT_ROOT))

# Import BatCave modules
from batcave.automation import Action  # noqa:E402, pylint: disable=wrong-import-position
from batcave.commander import Argument, Commander  # noqa:E402, pylint: disable=wrong-import-position
from batcave.expander import file_expander  # noqa:E402, pylint: disable=wrong-import-position
from batcave.fileutil import slurp, spew  # noqa:E402, pylint: disable=wrong-import-position
from batcave.platarch import Platform  # noqa:E402, pylint: disable=wrong-import-position
from batcave.sysutil import pushd, popd, rmpath  # noqa:E402, pylint: disable=wrong-import-position

PRODUCT_NAME = 'BatCave'
BUILD_DIR = PROJECT_ROOT / 'Build'
SOURCE_DIR = PROJECT_ROOT / 'batcave'
ARTIFACTS_DIR = BUILD_DIR / 'artifacts'
UNIT_TEST_DIR = BUILD_DIR / 'unit_test_results'
UNIT_TEST_FILE = UNIT_TEST_DIR / 'junit.xml'
VERSION_FILE = SOURCE_DIR / '__init__.py'
BUILD_INFO_FILE = BUILD_DIR / 'build_info.txt'


def main():
    'Main entry point'
    args = Commander('BatCave builder', [Argument('-u', '--user'),
                                         Argument('-r', '--release'),
                                         {'options': {},
                                          'args': [Argument('-t', '--test-publish', action='store_true'),
                                                   Argument('-p', '--publish', action='store_true')]}]).parse_args()

    build_info = dict()
    if args.test_publish or args.publish:
        for line in slurp(BUILD_INFO_FILE):
            (var, val) = line.strip().split('=')
            build_info[var] = val
    else:
        build_info['build_num'] = 'devbuild'
        build_info['release'] = '0.0.0'
    use_release = args.release if (args.release and not args.publish) else build_info['release']

    release_list = use_release.split('.')
    build_vars = {'product': PRODUCT_NAME,
                  'build_date': str(datetime.now()),
                  'build_name': f'{PRODUCT_NAME}_{use_release}_{build_info["build_num"]}',
                  'build_num': build_info['build_num'],
                  'platform': Platform().bart,
                  'release': use_release,
                  'major_version': release_list[0],
                  'minor_version': release_list[1],
                  'patch_version': release_list[2]}

    log_message = Action().log_message
    log_message('Building BatCave', True, None)
    log_message('Running unit tests', True)
    remake_dir(UNIT_TEST_DIR, 'unit test')
    XMLTestRunner(output=str(UNIT_TEST_FILE)).run(defaultTestLoader.discover(PROJECT_ROOT))

    log_message(f'Running setuptools build', True)
    pushd(PROJECT_ROOT)
    remake_dir(ARTIFACTS_DIR, 'artifacts')
    try:
        update_version_file(build_vars)
        batcave_module = import_module('batcave')
        reload(batcave_module)
        run_setup('setup.py', ['sdist', f'--dist-dir={ARTIFACTS_DIR}', 'bdist_wheel', f'--dist-dir={ARTIFACTS_DIR}']).run_commands()
    finally:
        popd()
        update_version_file(reset=True)

    if args.test_publish or args.publish:
        repo_arg = ['--repository-url', 'https://test.pypi.org/legacy/'] if args.test_publish else list()
        user_arg = ['--user', args.user] if args.user else list()
        upload(repo_arg + user_arg + [f'{ARTIFACTS_DIR}/*'])
        build_info['build_num'] = int(build_info['build_num']) + 1
        if args.publish:
            build_info['release'] = f'{release_list[0]}.{release_list[1]}.{int(release_list[2])+1}'
        spew(BUILD_INFO_FILE, [f'{var}={val}\n' for (var, val) in build_info.items()])


def remake_dir(dir_path, info_str):
    'Remove and recreate directory'
    log_message = Action().log_message
    if dir_path.exists():
        log_message(f'Removing old {info_str} directory')
        rmpath(dir_path)
    log_message(f'Creating {info_str} directory')
    dir_path.mkdir()


def update_version_file(build_vars=None, reset=False):
    'Updates the version file for the project'
    log_message = Action().log_message
    verb = 'Resetting' if reset else 'Updating'
    log_message(f'{verb} version file: {VERSION_FILE}', True)
    file_orig = Path(str(VERSION_FILE) + '.orig')
    if reset:
        if VERSION_FILE.exists():
            VERSION_FILE.unlink()
        file_orig.rename(VERSION_FILE)
    else:
        VERSION_FILE.chmod(VERSION_FILE.stat().st_mode | S_IWUSR)
        copyfile(VERSION_FILE, file_orig)
        file_expander(file_orig, VERSION_FILE, build_vars)
        replacers = {'title': PRODUCT_NAME, 'version': build_vars['release']}
        file_update = list()
        for line in slurp(VERSION_FILE):
            for (var, val) in replacers.items():
                if line.startswith(f'__{var}__'):
                    line = f"__{var}__ = '{val}'\n"
            file_update.append(line)
        spew(VERSION_FILE, file_update)


if __name__ == '__main__':
    main()
