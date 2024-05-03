#!/usr/bin/env bash
set -eu

python -m pip install --upgrade pip
pip install --upgrade --upgrade-strategy eager setuptools wheel
pip freeze | grep -v '^\-e' | cut -d = -f 1 | xargs -n1 pip install --upgrade
flit install -s --deps all
