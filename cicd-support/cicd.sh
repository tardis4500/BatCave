#!/usr/bin/env bash
set -eu

unix_os=`uname`
if [ $unix_os = Darwin ]
then
    sw_vers
elif [ $unix_os = Linux ]
then
    cat /etc/os-release
else
    echo "Unsupported UNIX OS: $unix_os"
fi

python --version
pip install --upgrade --upgrade-strategy eager pip
pip install --upgrade --upgrade-strategy eager setuptools wheel

# apt-get -y -qq update
# apt-get -y -qq --no-install-recommends install curl git

# pip install -U virtualenv
# if [ ! -e $VIRTUAL_ENV ]; then virtualenv $VIRTUAL_ENV; fi
# source $VIRTUAL_ENV/bin/activate
# pip install --upgrade --upgrade-strategy eager pip
# pip install --upgrade --upgrade-strategy eager setuptools wheel
# git remote add $GIT_REMOTE https://${{ github.actor }}:$GITLAB_USER_TOKEN@${{ github.server_url }}/${{ github.repository_owner }}/${{ github.event.repository.name }}.git

function install-flit {
    pip install --upgrade --upgrade-strategy eager flit
    flit install -s --deps all
}

case $1 in
    static-analysis )
        install-flit
        pylint $PRODUCT
        flake8 $PRODUCT
        mypy $PRODUCT ;;
    unit-tests )
        install-flit
        python -m xmlrunner discover -o $UNIT_TEST_DIR ;;
    build )
        install-flit
        flit build ;;
    install-test )
        pip install $ARTIFACTS_DIR/*.tar.gz ;;
    publish-test )
        install-flit
        twine upload --config-file $PYPIRC -r $PYPI_REPO $ARTIFACTS_DIR/*
        bumpver update $BUMP_ARGS
esac

# cSpell:ignore virtualenv mypy xmlrunner pypirc pypi bumpver
