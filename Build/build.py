#!/usr/bin/env python
'This programs drives the build and release automation'
# cSpell:ignore bdist, bldverfile, checkin, cibuild, sdist, syscmd

# Import standard modules
from datetime import datetime
from distutils.core import run_setup
from importlib import import_module, reload
from json import loads as json_parse
import os
from pathlib import Path
from random import randint
from shutil import copyfile
from stat import S_IWUSR
import sys
from unittest import defaultTestLoader

# Import third-party-modules
from requests import delete as rest_delete, post as rest_post
from twine.commands.upload import main as upload
from xmlrunner import XMLTestRunner

PROJECT_ROOT = Path(os.path.abspath(os.pardir))
sys.path.insert(0, str(PROJECT_ROOT))

# Import BatCave modules
from batcave.automation import Action  # noqa:E402, pylint: disable=wrong-import-position
from batcave.commander import Argument, Commander, SubParser  # noqa:E402, pylint: disable=wrong-import-position
from batcave.expander import file_expander  # noqa:E402, pylint: disable=wrong-import-position
from batcave.fileutil import slurp, spew  # noqa:E402, pylint: disable=wrong-import-position
from batcave.cms import Client  # noqa:E402, pylint: disable=wrong-import-position
from batcave.platarch import Platform  # noqa:E402, pylint: disable=wrong-import-position
from batcave.sysutil import pushd, popd, rmpath, SysCmdRunner  # noqa:E402, pylint: disable=wrong-import-position

PRODUCT_NAME = 'BatCave'

SOURCE_DIR = PROJECT_ROOT / 'batcave'
VERSION_FILE = SOURCE_DIR / '__init__.py'

BUILD_DIR = PROJECT_ROOT / 'Build'
ARTIFACTS_DIR = BUILD_DIR / 'artifacts'
UNIT_TEST_DIR = BUILD_DIR / 'unit_test_results'
CI_BUILD_FILE = PROJECT_ROOT / '.gitlab-ci.yml'

REQUIREMENTS_FILE = PROJECT_ROOT / 'requirements.txt'
FREEZE_FILE = PROJECT_ROOT / 'requirements-frozen.txt'

PYPI_TEST_URL = 'https://test.pypi.org/legacy/'
GITLAB_RELEASES_URL = 'https://gitlab.com/api/v4/projects/arisilon%2Fbatcave/releases'

MESSAGE_LOGGER = Action().log_message

pip = SysCmdRunner('pip').run  # pylint: disable=invalid-name


def main():
    'Main entry point'
    pypi_args = [Argument('pypi_password'), Argument('-u', '--pypi-user', default='__token__')]
    gitlab_args = [Argument('gitlab_user'), Argument('gitlab_password')]
    release_args = [Argument('release')] + gitlab_args
    publish_args = release_args + pypi_args
    Commander('BatCave builder', subparsers=[SubParser('devbuild', devbuild),
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


def devbuild(args):
    'Run a developer build'
    unit_tests(args)
    builder(args)


def unit_tests(_unused_args):
    'Run unit tests'
    MESSAGE_LOGGER('Running unit tests', True)
    remake_dir(UNIT_TEST_DIR, 'unit test')
    XMLTestRunner(output=str(UNIT_TEST_DIR)).run(defaultTestLoader.discover(PROJECT_ROOT))


def ci_build(args):
    'Run the build on the CI server'
    builder(args)


def builder(args):
    'Run setuptools build'
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


def publish_to_pypi(args):
    'Publish to the specified PyPi server'
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


def post_release_update(args):
    'Tag the source, update the release number, and create the release in GitLab'
    MESSAGE_LOGGER(f'Performing post-release updates', True)
    os.environ['GIT_WORK_TREE'] = str(PROJECT_ROOT)
    git_client = Client(Client.CLIENT_TYPES.git, 'release', create=False)

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


def freeze(_unused_args):
    'Create the requirement-freeze.txt file leaving out the development tools and adding platform specifiers.'
    requirements = {p.split(';')[0].strip() for p in slurp(REQUIREMENTS_FILE)}.union(['pip', 'setuptools', 'wheel'])
    dev_requirements = [p['name'] for p in json_parse(pip(None, 'list', '--format=json')[0]) if p['name'] not in requirements]
    pip('Uninstalling unlisted requirements', 'uninstall', '-y', '-qqq', *dev_requirements)
    pip('Re-installing requirements', 'install', '-qqq', '-U', '-r', REQUIREMENTS_FILE)
    spew(FREEZE_FILE, pip('Creating frozen requirements file', 'freeze'))
    freeze_file = [l.strip() for l in slurp(FREEZE_FILE)]
    with open(FREEZE_FILE, 'w') as updated_freeze_file:
        for line in freeze_file:
            if 'win32' in line:
                line += "; sys_platform == 'win32'"
            print(line, file=updated_freeze_file)


def get_build_info(args):
    'Return the build number and release'
    return (args.build_num if hasattr(args, 'build_num') else '0',
            args.release if hasattr(args, 'release') else '0.0.0')


def delete_release(args):
    'Delete a release from GitLab'
    MESSAGE_LOGGER(f'Deleting the GitLab release v{args.release}', True)
    response = rest_delete(f'{GITLAB_RELEASES_URL}/v{args.release}', headers={'Private-Token': args.gitlab_password})
    response.raise_for_status()


if __name__ == '__main__':
    main()
