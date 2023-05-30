# BatCave Python Module

A useful collection of tools for writing Python programs.

## Developing

Development is best accomplished using virtualenv or virtualenv-wrapper where a virtual environment can be generated:

    mkvirtualenv batcave
    python -m pip install -U pip
    pip install -U setuptools wheel
    pip install -U flit
    flit install -s --deps all (on Windows omit the -s)

## Testing

### Static Analysis

The static analysis test can be run with

    pylint batcave
    flake8 batcave
    mypy batcave

### Unit Tests

The unit tests can be run with

    python -m xmlrunner discover -o unit_test_results

## Building

The build can be run with

    flit build

## Publishing a Release

This is the procedure for releasing BatCave

1. Validate all issues are "Ready for Release"
1. Update CHANGELOG.rst
1. Run publish job
1. Validate GitHub release
1. Validate PyPi
1. Move issues to "Closed"
1. Close Milestone

<!--- cSpell:ignore virtualenv mkvirtualenv batcave stest mypy xmlrunner utest -->
