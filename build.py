#!/usr/bin/env python
"""This programs drives the BatCave build and release automation."""

# Import standard modules
from argparse import Namespace
from datetime import datetime
from distutils.core import run_setup
from importlib import import_module, reload
from json import loads as json_parse
import os
from pathlib import Path
from random import randint
from shutil import copyfile
from stat import S_IWUSR
from typing import Dict, Optional, Tuple
from unittest import defaultTestLoader

# Import third-party-modules
from requests import delete as rest_delete, post as rest_post
from twine.commands.upload import main as upload
from xmlrunner import XMLTestRunner

# Import BatCave modules
from batcave.automation import Action
from batcave.commander import Argument, Commander, SubParser
from batcave.expander import file_expander
from batcave.fileutil import slurp, spew
from batcave.cms import Client, ClientType
from batcave.platarch import Platform
from batcave.sysutil import pushd, popd, rmpath, SysCmdRunner

PROJECT_ROOT = Path().cwd()
PRODUCT_NAME = 'BatCave'

MODULE_NAME = 'batcave'
SOURCE_DIR = PROJECT_ROOT / MODULE_NAME
VERSION_FILE = SOURCE_DIR / '__init__.py'

BUILD_DIR = PROJECT_ROOT / 'build'
ARTIFACTS_DIR = BUILD_DIR / 'artifacts'
UNIT_TEST_DIR = BUILD_DIR / 'unit_test_results'
CI_BUILD_FILE = PROJECT_ROOT / '.gitlab-ci.yml'

REQUIREMENTS_FILE = PROJECT_ROOT / 'requirements.txt'
FREEZE_FILE = PROJECT_ROOT / 'requirements-frozen.txt'

PYPI_TEST_URL = 'https://test.pypi.org/legacy/'
GITLAB_RELEASES_URL = 'https://gitlab.com/api/v4/projects/arisilon%2Fbatcave/releases'

pip = SysCmdRunner('pip').run  # pylint: disable=invalid-name


class ActionLogger(Action):
    """Stub class to get Action logger."""
    def _execute(self) -> None:
        pass


MESSAGE_LOGGER = ActionLogger().log_message


def main() -> None:
    """The main entry point."""
    pypi_args = [Argument('pypi_password'), Argument('-u', '--pypi-user', default='__token__')]
    gitlab_args = [Argument('gitlab_user'), Argument('gitlab_password')]
    release_args = [Argument('release')] + gitlab_args
    publish_args = release_args + pypi_args
    Commander('BatCave builder', subparsers=[SubParser('devbuild', devbuild),
                                             SubParser('static_analysis', static_analysis),
                                             SubParser('unit_tests', unit_tests),
                                             SubParser('ci_build', ci_build, [Argument('release'), Argument('build-num')]),
                                             SubParser('publish_test', publish_to_pypi, publish_args),
                                             SubParser('publish', publish_to_pypi, publish_args),
                                             SubParser('freeze', freeze),
                                             SubParser('post_release_update', post_release_update,
                                                       [Argument('-i', '--increment-release', action='store_true'),
                                                        Argument('-t', '--tag-source', action='store_true'),
                                                        Argument('-r', '--create-release', action='store_true'),
                                                        Argument('-c', '--checkin', action='store_true')] + release_args),
                                             SubParser('delete_release', delete_release, release_args)], default=devbuild).execute()


def devbuild(args: Namespace) -> None:
    """Run a developer build."""
    unit_tests(args)
    builder(args)


def static_analysis(_unused_args: Namespace) -> None:
    """Run pylint."""
    SysCmdRunner('pylint', show_stdout=True).run('Running pylint', '--max-line-length=200', '--max-attributes=10', '--disable=duplicate-code,fixme', MODULE_NAME)
    SysCmdRunner('flake8', show_stdout=True).run('Running flake8', '--max-line-length=200', '--ignore=ANN002,ANN003,ANN101,ANN204', MODULE_NAME)
    SysCmdRunner('mypy', show_stdout=True).run('Running mypy', MODULE_NAME)


def unit_tests(_unused_args: Namespace) -> None:
    """Run unit tests."""
    MESSAGE_LOGGER('Running unit tests', True)
    remake_dir(UNIT_TEST_DIR, 'unit test')
    XMLTestRunner(output=str(UNIT_TEST_DIR)).run(defaultTestLoader.discover(str(PROJECT_ROOT)))


def ci_build(args: Namespace) -> None:
    """Run the build on the CI server."""
    builder(args)


def builder(args: Namespace) -> None:
    """Run setuptools build."""
    (build_num, release) = get_build_info(args)
    release_list = release.split('.')
    build_vars = {'product': PRODUCT_NAME,
                  'build_date': str(datetime.now()),
                  'build_name': f'{PRODUCT_NAME}_{release}_{build_num}',
                  'build_num': build_num,
                  'platform': Platform().bart,
                  'release': release,
                  'major_version': release_list[0],
                  'minor_version': release_list[1],
                  'patch_version': release_list[2]}

    MESSAGE_LOGGER('Running setuptools build', True)
    pushd(PROJECT_ROOT)
    remake_dir(ARTIFACTS_DIR, 'artifacts')
    try:
        update_version_file(build_vars)
        batcave_module = import_module('batcave')
        reload(batcave_module)
        run_setup('setup.py', ['sdist', f'--dist-dir={ARTIFACTS_DIR}', 'bdist_wheel', f'--dist-dir={ARTIFACTS_DIR}']).run_commands()  # type: ignore
    finally:
        popd()
        update_version_file(reset=True)


def publish_to_pypi(args: Namespace) -> None:
    """Publish to the specified PyPi server."""
    message = 'Publishing to PyPi'
    if args.release == 'test':
        message += ' Test'
    MESSAGE_LOGGER(message, True)
    upload_args = [f'--user={args.pypi_user}', f'--password={args.pypi_password}', f'{ARTIFACTS_DIR}/*']
    if args.release == 'test':
        upload_args += ['--repository-url', PYPI_TEST_URL]
        for artifact in ARTIFACTS_DIR.iterdir():
            if artifact.suffix == '.gz':
                artifact.unlink()
            else:
                artifact.rename(ARTIFACTS_DIR / f'{PRODUCT_NAME}-{randint(1, 1000)}-py3-none-any.whl')
    upload(upload_args)
    if args.release != 'test':
        args.increment_release = args.tag_source = args.create_release = args.checkin = True
        post_release_update(args)


def post_release_update(args: Namespace) -> None:
    """Tag the source, update the release number, and create the release in GitLab."""
    MESSAGE_LOGGER('Performing post-release updates', True)
    os.environ['GIT_WORK_TREE'] = str(PROJECT_ROOT)
    git_client = Client(ClientType.git, 'release', create=False)

    if args.increment_release:
        gitlab_ci_config = slurp(CI_BUILD_FILE)
        new_config = list()
        for line in gitlab_ci_config:
            if 'RELEASE:' in line:
                release = args.release.split('.')
                release[2] = str(int(release[-1]) + 1)
                new_release = '.'.join(release)
                line = f'  RELEASE: {new_release}\n'
            new_config.append(line)
        MESSAGE_LOGGER(f'Incrementing release to v{new_release}')
        spew(CI_BUILD_FILE, new_config)
        git_client.add_files(CI_BUILD_FILE)

    if args.tag_source:
        MESSAGE_LOGGER(f'Tagging the source with v{args.release}')
        git_client.add_remote_ref('user_origin', f'https://{args.gitlab_user}:{args.gitlab_password}@gitlab.com/arisilon/batcave.git', exists_ok=True)
        git_client.add_label(f'v{args.release}', exists_ok=True)
    if args.checkin:
        git_client.checkin_files('Automated pipeline checking', remote='user_origin', tags=True)

    if args.create_release:
        MESSAGE_LOGGER(f'Creating the GitLab release v{args.release}')
        response = rest_post(GITLAB_RELEASES_URL,
                             headers={'Content-Type': 'application/json', 'Private-Token': args.gitlab_password},
                             json={'name': f'Release {args.release}', 'tag_name': f'v{args.release}', 'description': f'Release {args.release}', 'milestones': [f'Release {args.release}']})
        response.raise_for_status()


def remake_dir(dir_path: Path, info_str: str) -> None:
    """Remove and recreate directory."""
    if dir_path.exists():
        MESSAGE_LOGGER(f'Removing old {info_str} directory')
        rmpath(dir_path)
    MESSAGE_LOGGER(f'Creating {info_str} directory')
    dir_path.mkdir(parents=True)


def update_version_file(build_vars: Optional[Dict[str, str]] = None, reset: bool = False) -> None:
    """Updates the version file for the project."""
    use_vars = build_vars if build_vars else dict()
    verb = 'Resetting' if reset else 'Updating'
    MESSAGE_LOGGER(f'{verb} version file: {VERSION_FILE}', True)
    file_orig = Path(str(VERSION_FILE) + '.orig')
    if reset:
        if VERSION_FILE.exists():
            VERSION_FILE.unlink()
        file_orig.rename(VERSION_FILE)
    else:
        VERSION_FILE.chmod(VERSION_FILE.stat().st_mode | S_IWUSR)
        copyfile(VERSION_FILE, file_orig)
        file_expander(file_orig, VERSION_FILE, use_vars)
        replacers = {'title': PRODUCT_NAME, 'version': use_vars['release']}
        file_update = list()
        for line in slurp(VERSION_FILE):
            for (var, val) in replacers.items():
                if line.startswith(f'__{var}__'):
                    line = f"__{var}__ = '{val}'\n"
            file_update.append(line)
        spew(VERSION_FILE, file_update)


def freeze(_unused_args: Namespace) -> None:
    """Create the requirement-freeze.txt file leaving out the development tools and adding platform specifiers."""
    requirements = {p.split(';')[0].strip() for p in slurp(REQUIREMENTS_FILE)}.union({'pip', 'setuptools'})
    dev_requirements = set()
    for pip_module in json_parse(pip('', 'list', '--format=json')[0]):
        if (pip_module['name'] not in requirements) and ('PyQt5' not in pip_module['name']) and ('pywin32' not in pip_module['name']):
            dev_requirements.add(pip_module['name'])
    pip('Uninstalling development requirements', 'uninstall', '-y', '-qqq', *dev_requirements)
    pip('Re-installing requirements', 'install', '-qqq', '--upgrade', '--upgrade-strategy', 'eager', '-r', REQUIREMENTS_FILE)
    spew(FREEZE_FILE, pip('Creating frozen requirements file', 'freeze'))
    freeze_file = [line.strip() for line in slurp(FREEZE_FILE)]
    with open(FREEZE_FILE, 'w') as updated_freeze_file:
        for line in freeze_file:
            if 'win32' in line:
                line += "; sys_platform == 'win32'"
            if 'systemd' in line:
                line += "; sys_platform != 'win32'"
            print(line, file=updated_freeze_file)


def get_build_info(args: Namespace) -> Tuple[str, str]:
    """Return the build number and release."""
    return (args.build_num if hasattr(args, 'build_num') else '0',
            args.release if hasattr(args, 'release') else '0.0.0')


def delete_release(args: Namespace) -> None:
    """Delete a release from GitLab."""
    MESSAGE_LOGGER(f'Deleting the GitLab release v{args.release}', True)
    response = rest_delete(f'{GITLAB_RELEASES_URL}/v{args.release}', headers={'Private-Token': args.gitlab_password})
    response.raise_for_status()


if __name__ == '__main__':
    main()

# cSpell:ignore bdist, bldverfile, checkin, cibuild, pywin, sdist, syscmd
