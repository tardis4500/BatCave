# BatCave Python Module

A useful collection of tools for writing Python programs.

## Developing

Development is best accomplished using virtualenv or virtualenv-wrapper where a virtual environment can be generated:

    mkvirtualenv batcave
    python -m pip install --upgrade pip
    pip install --upgrade --upgrade-strategy eager setuptools wheel
    pip install --upgrade --upgrade-strategy eager flit
    Windows: flit install --deps all
    Linux: flit install -s --deps all

To update the current development environment

    python -m pip install --upgrade pip
    pip install --upgrade --upgrade-strategy eager setuptools wheel
    Windows: pip freeze | %{$_.split('==')[0]} | %{pip install --upgrade $_} && flit install --deps all
    Linux: pip freeze | grep -v '^\-e' | cut -d = -f 1 | xargs -n1 pip install --upgrade && flit install -s --deps all

## Testing

### Static Analysis

The static analysis test can be run with

    pylint batcave
    flake8 batcave
    mypy batcave

### Unit Tests

The unit tests can be run with

    python -m unittest -v [tests.test_suite[.test_class[.test_case]]]

## Building

The build can be run with

    flit build

## Publishing a Release

This is the procedure for releasing BatCave

1. Validate that all issues are "Ready for Release".
1. Update CHANGELOG.md.
1. Run the Publish workflow against the Production environment.
1. Validate the GitHub release and tag.
1. Validate PyPi was published properly.
1. Label the issues as res::complete and mark as "Closed".
1. Close the Milestone.
1. Update the source in Perforce.
1. If this was a release branch, merge to master.

<!--- cSpell:ignore virtualenv mkvirtualenv batcave stest mypy xmlrunner utest -->
