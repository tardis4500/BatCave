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

    vjer build

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

<!--- cSpell:ignore virtualenv vjer -->
