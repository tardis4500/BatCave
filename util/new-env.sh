#!/usr/bin/env bash
set -eu

mkvirtualenv vjer
python -m pip install --upgrade pip
pip install --upgrade --upgrade-strategy eager setuptools wheel
pip install --upgrade --upgrade-strategy eager flit
flit install -s --deps all

# cSpell:ignore mkvirtualenv vjer
