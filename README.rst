BatCave Python Module
=====================
A useful collection of tools for writing Python programs.

Developing
----------
Development is best accomplished using pipenv where a virtual environment can be generated from the Pipfile using::

    pipenv install --dev

Building
--------
Building is performed by changing to the Build directory and running the build.py script which will perform two actions

1. run the unit tests and place the results in Build/unit_test_results/junit.xml
1. run the setup.py to create a PyPi distribution in Build/artifacts

Test Publish
------------
A test can be published to the PyPi test site with::

    build.py --test-publish

This will use twine to publish which will prompt for the username and password.
If you create a password with keyring you can specify the username on the command line with the "--user username" argument.
If you need to test publish with a new version number you can use the "--release number" argument

Publishing a Release
--------------------
After updating Changelog.rst A release can be published to PyPi with::

    build.py --publish
