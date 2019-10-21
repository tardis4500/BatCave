#!/usr/bin/env python
'This programs drives the build and release automation'
# cSpell:ignore bdist, bldverfile, cibuild, sdist

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
from batcave.commander import Argument, Commander, SubParser  # noqa:E402, pylint: disable=wrong-import-position
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

MESSAGE_LOGGER = Action().log_message


def main():
    'Main entry point'
    Commander('BatCave builder', subparsers=[SubParser('devbuild', devbuild),
                                             SubParser('unit_tests', unit_tests),
                                             SubParser('ci_build', ci_build),
                                             SubParser('publish_test', publish_test, [Argument('user')]),
                                             SubParser('publish', publish, [Argument('user')])], default=devbuild).execute()


def devbuild(args):
    'Run a developer build'
    unit_tests(args)
    builder(args)


def unit_tests(args):  # pylint: disable=unused-argument
    'Run unit tests'
    MESSAGE_LOGGER('Running unit tests', True)
    remake_dir(UNIT_TEST_DIR, 'unit test')
    XMLTestRunner(output=str(UNIT_TEST_FILE)).run(defaultTestLoader.discover(PROJECT_ROOT))


def ci_build(args):
    'Run the build on the CI server'
    builder(args, False)


def builder(args, is_devbuild=True):  # pylint: disable=unused-argument
    'Run setuptools build'
    build_vars = get_build_info(is_devbuild)

    MESSAGE_LOGGER(f'Running setuptools build', True)
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


def publish_test(args):
    'Publish to the PyPi test server'
    publish_to_pypi(args, 'https://test.pypi.org/legacy/')


def publish(args):
    'Publish to the PyPi production server'
    publish_to_pypi(args)


def publish_to_pypi(args, repo=None):
    'Publish to the specified PyPi server'
    build_vars = get_build_info(False)
    repo_arg = ['--repository-url', 'https://test.pypi.org/legacy/'] if repo else list()
    upload(repo_arg + ['--user', args.user, f'{ARTIFACTS_DIR}/*'])
    build_vars['build_num'] = int(build_vars['build_num']) + 1
    if not repo:
        build_vars['release'] = f'{build_vars["major_version"]}.{build_vars["minor_version"]}.{int(build_vars["patch_version"])+1}'
    spew(BUILD_INFO_FILE, [f'release={build_vars["release"]}\n', f'build_num={build_vars["build_num"]}\n'])


def get_build_info(is_devbuild):
    'Get the build information'
    if is_devbuild:
        build_info = {'build_num': 'devbuild', 'release': '0.0.0'}
    else:
        build_info = dict()
        for line in slurp(BUILD_INFO_FILE):
            (var, val) = line.strip().split('=')
            build_info[var] = val

    release_list = build_info['release'].split('.')
    build_vars = {'product': PRODUCT_NAME,
                  'build_date': str(datetime.now()),
                  'build_name': f'{PRODUCT_NAME}_{build_info["release"]}_{build_info["build_num"]}',
                  'build_num': build_info['build_num'],
                  'platform': Platform().bart,
                  'release': build_info['release'],
                  'major_version': release_list[0],
                  'minor_version': release_list[1],
                  'patch_version': release_list[2]}
    return build_vars


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
