#!/usr/bin/env bash
set -eu

PRODUCT=batcave
export FLIT_ROOT_INSTALL: 1


unix_os=`uname`
if [ $unix_os = Darwin ]
then
    sw_vers
elif [ $unix_os = Linux ]
then
    cat /etc/os-release
else
    echo "Unsupported UNIX OS: $unix_os"
    exit 1
fi

function install-flit {
    pip install --upgrade --upgrade-strategy eager flit
    flit install -s --deps all
}

function install-pip-tools {
    pip install --upgrade --upgrade-strategy eager pip
    pip install --upgrade --upgrade-strategy eager setuptools wheel
}

python --version
install-pip-tools

pip install --upgrade --upgrade-strategy eager virtualenv
if [ ! -e $VIRTUAL_ENV ]; then virtualenv $VIRTUAL_ENV; fi
source $VIRTUAL_ENV/bin/activate
install-pip-tools

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
        git config user.name "$GIT_AUTHOR_NAME"
        git config user.email "$GIT_AUTHOR_EMAIL"
        bumpver update --tag-num ;;
    publish )
        install-flit
        bumpver update --tag final --tag-commit
        flit build
        eval $(bumpver show --env)
        gh release create $CURRENT_VERSION \
              --title="Release $CURRENT_VERSION" \
              --latest \
              --generate-notes
        bumpver update --patch --tag rc --tag-num ;;
esac

# cSpell:ignore virtualenv mypy xmlrunner bumpver batcave
