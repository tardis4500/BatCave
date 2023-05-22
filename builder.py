#!/usr/bin/env python
"""This programs drives the BatCave build and release automation."""

# Import standard modules
from argparse import Namespace
import os
from pathlib import Path

# Import third-party-modules
from requests import delete as rest_delete, post as rest_post
from twine.commands.upload import main as upload  # type: ignore[missing-imports] # pylint: disable=import-error

# Import BatCave modules
from batcave.automation import Action
from batcave.commander import Argument, Commander, SubParser
from batcave.fileutil import slurp, spew
from batcave.cms import Client, ClientType
from batcave.sysutil import SysCmdRunner

PROJECT_ROOT = Path().cwd()
PRODUCT_NAME = 'BatCave'

MODULE_NAME = 'batcave'
SOURCE_DIR = PROJECT_ROOT / MODULE_NAME
VERSION_FILES = [PROJECT_ROOT / 'pyproject.toml', SOURCE_DIR / '__init__.py']

ARTIFACTS_DIR = PROJECT_ROOT / 'dist'
CI_BUILD_FILE = PROJECT_ROOT / '.gitlab-ci.yml'

GITLAB_RELEASES_URL = 'https://gitlab.com/api/v4/projects/arisilon%2Fbatcave/releases'

pip = SysCmdRunner('pip', show_cmd=False, show_stdout=False, syscmd_args={'ignore_stderr': True}).run


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
    Commander('BatCave builder', subparsers=[SubParser('publish', publish_to_pypi, publish_args),
                                             SubParser('post_release_update', post_release_update,
                                                       [Argument('-i', '--increment-release', action='store_true'),
                                                        Argument('-t', '--tag-source', action='store_true'),
                                                        Argument('-r', '--create-release', action='store_true'),
                                                        Argument('-c', '--checkin', action='store_true')] + release_args),
                                             SubParser('delete_release', delete_release, release_args)]).execute()


def publish_to_pypi(args: Namespace) -> None:
    """Publish to the specified PyPi server."""
    MESSAGE_LOGGER('Publishing to PyPi', True)
    upload([f'--user={args.pypi_user}', f'--password={args.pypi_password}', f'{ARTIFACTS_DIR}/*'])
    args.increment_release = args.tag_source = args.create_release = args.checkin = True
    post_release_update(args)


def post_release_update(args: Namespace) -> None:
    """Tag the source, update the release number, and create the release in GitLab."""
    MESSAGE_LOGGER('Performing post-release updates', True)
    os.environ['GIT_WORK_TREE'] = str(PROJECT_ROOT)
    git_client = Client(ClientType.git, 'release', create=False)

    if args.increment_release:
        gitlab_ci_config = slurp(CI_BUILD_FILE)
        new_config = []
        new_release = ''
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
        git_client.add_label(f'v{args.release}', f'version {args.release}', exists_ok=True)
    if args.checkin:
        git_client.checkin_files('Automated pipeline checking', remote='user_origin', tags=True)

    if args.create_release:
        MESSAGE_LOGGER(f'Creating the GitLab release v{args.release}')
        response = rest_post(GITLAB_RELEASES_URL, timeout=60,
                             headers={'Content-Type': 'application/json', 'Private-Token': args.gitlab_password},
                             json={'name': f'Release {args.release}', 'tag_name': f'v{args.release}', 'description': f'Release {args.release}', 'milestones': [f'Release {args.release}']})
        response.raise_for_status()


def delete_release(args: Namespace) -> None:
    """Delete a release from GitLab."""
    MESSAGE_LOGGER(f'Deleting the GitLab release v{args.release}', True)
    response = rest_delete(f'{GITLAB_RELEASES_URL}/v{args.release}', headers={'Private-Token': args.gitlab_password}, timeout=60)
    response.raise_for_status()


if __name__ == '__main__':
    main()

# cSpell:ignore batcave fileutil syscmd checkin
