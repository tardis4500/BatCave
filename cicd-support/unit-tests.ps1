$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion"
$PSVersionTable
python --version
pip install --upgrade --upgrade-strategy eager pip
pip install --upgrade --upgrade-strategy eager setuptools wheel
pip install --upgrade --upgrade-strategy eager flit
flit install --deps all
python -m xmlrunner discover -o $env:UNIT_TEST_DIR

# cSpell:ignore hklm xmlrunner
