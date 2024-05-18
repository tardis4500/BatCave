
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

mkvirtualenv batcave
python -m pip install --upgrade pip
pip install --upgrade --upgrade-strategy eager setuptools wheel
pip install --upgrade --upgrade-strategy eager flit
flit install --deps all

# cSpell:ignore mkvirtualenv batcave
