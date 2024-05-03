$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

python -m pip install --upgrade pip
pip install --upgrade --upgrade-strategy eager setuptools wheel
pip freeze | %{$_.split('==')[0]} | %{pip install --upgrade $_}
flit install --deps all
