# BatCave Python Module

A useful collection of tools for writing Python programs.

## Developing

Development is best accomplished using virtualenv or virtualenv-wrapper where a virtual environment can be generated:

    UNIX: util/new-env.sh
    Windows: util\New-Env.ps1

To update the current development environment

    UNIX: util/update-env.sh
    Windows: util\Update-Env.ps1

## Testing

### Static Analysis

The static analysis test can be run with

    vjer test

### Unit Tests

The unit tests can be run with

    python -m unittest -v [tests.test_suite[.test_class[.test_case]]]

## Building

The build can be run with

    flit build

## Publishing a Release

This is the procedure for releasing BatCave

1. Validate all issues are "Ready for Release"
1. Update CHANGELOG.md
1. Run the publish workflow against the Production environment
1. Validate GitHub release
1. Validate PyPi
1. Move issues to "Closed" and label res::complete
1. Close Milestone
1. Update source in Perforce

<!--- cSpell:ignore virtualenv mkvirtualenv batcave stest mypy xmlrunner utest vjer -->
