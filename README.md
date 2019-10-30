# BatCave Python Module

A useful collection of tools for writing Python programs.

## Developing

Development is best accomplished using virutalenv or virtualenv-wrapper where a virtual environment can be generated:

    pip install -r requirements.txt

Useful tools for development can be installed with:

    pip install -r requirements-dev.txt

## Building

Building is performed by changing to the Build directory and running the build.py script which will perform two actions

1. run the unit tests and place the results in Build/unit_test_results/junit.xml
1. run the setup.py to create a PyPi distribution in Build/artifacts

## Publishing a Release

This is the procedure for releasing BatCave

1. Validate all issues are "Ready for Release"
1. Update CHANGELOG.rst
1. Run publish job
1. Validate GitHub release
1. Validate PyPi
1. Move issues to "Closed"
1. Close Milestone

<!--- cSpell:ignore virtualenv -->
