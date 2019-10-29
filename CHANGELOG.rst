Change Log
==========
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/).

.. cSpell:ignore platarch, cmds, psutil, servermgr, pywin, sqlscript, verfiles, cloudmgr, qbpy, pkgtype, unittest, recopytree, pathlib, pypiwin, pythonval, fileutil
.. cSpell:ignore hallog, cmsclient, civars, chmodtree, sysutl, cmdspec, webapp, virtualwrapper, configmgr, buildname, vsver, hasapp, useshell, GNUC, envcfg, pipenv
.. cSpell:ignore statemachine, psexec, getattr, contextlib, logname, xmltodict, ignorestderr, USERPROFILE, netutil, assemblyinfo, setattr, iispy, virtualenv, prdb, syscmd

[37.1.2] - 2019-10-29
---------------------
- Changed
    - Fixed kubectl issue. (GitLab #22)


Release History
---------------

[37.1.1] - 2019-10-28
---------------------
- Added
    - Added missing Kubernetes module requirement. (GitLab #21)

[37.1.0] - 2019-10-28
---------------------
- Added
    - Added initial Kubernetes support module. (GitLab #17)

- Changed
    - Fix installation on Android. (GitLab #10)
    - Use cmd.Client for git interactions in build.py. (GitLab #16)
    - Need to pass the release number in when publishing. (GitLab #18)
    - Converted from pipenv to standard pip requirements file. (GitLab #19)
    - Improved logging in build.py.

[37.0.1] - 2019-10-24
---------------------
- Added
    - Added project links to setup.py. (GitLab #3)
    - Added GitLab CI/CD file. (GitLab #7, #14)
    - Create GitLab release at release time in build.py. (GitLab #9)

- Changed
    - Made dependencies less restrictive. (GitLab #2)
    - Cleaned up setup.py. (GitLab #3)
    - Downgraded build environment to Python 3.7 since psutil not built for 3.8 yet. (GitLab #4)
    - Added GitLab CI/CD support to build.py. (GitLab #7)
    - Fixed switch for Python 3.7 StopIteration behavior.

- Removed
    - Removed build related dependencies. (GitLab #3)
    - Removed old dependencies. (GitLab #3, #11)

[37.0.0] - 2019-10-15
---------------------
- Added
    - Added support for publishing to PyPi.

- Changed
    - Updated build.py to not rely on build and prdb modules.

- Removed
    - Moved build and prdb modules to a separate project.


[36.3.2] - 2019-09-26
---------------------
- Changed
    - Fix update_cfg_list rename to updater.

[36.3.1] - 2019-09-26
---------------------
- Changed
    - Convert Path to str before passing to COM handler.

[36.3.0] - 2019-09-19
---------------------
- Changed
    - Allow multiple property holders in Expander.
    - Fix lang.flatten() and add lang.flatten_string_list().
    - Allow bypass of nuget restore in MSBuildBuilder.
    - Make sure the results is a Path() in MSTestUnitTester.
    - Add support for dashboards to the qbpy module.
    - Fix build when docker authentication fails.
    - Upgrade cx_Freeze to 5.1.1.
    - Upgrade GitPython to 3.0.2.
    - Upgrade pyodbc to 4.0.27.
    - Upgrade PyQt5 to 5.13.1.
    - Upgrade setuptools to 41.2.0.

[36.2.0] - 2019-07-25
---------------------
- Added
    - Added build.DotCoverTester().
    - Added build.NUnitTester().
    - Added support for command arguments on servermgr.Server().create_scheduled_task().

[36.1.1] - 2019-07-15
---------------------
- Changed
    - Fix servermgr.ScheduledTask().TASK_PATH definition on Linux.

[36.1.0] - 2019-07-12
---------------------
- Added
    - Added start_in and disable arguments to servermgr.Server().create_scheduled_task().

- Changed
    - Fix servermgr.Server().create_scheduled_task() issue when spaces in task executable path.

[36.0.0] - 2019-07-05
---------------------
- Changed
    - Improved options for servermgr.Server().create_scheduled_task().
    - Upgraded docker to 4.0.2.
    - Upgraded PyQt to 5.13.0.

[35.1.0] - 2019-06-17
---------------------
- Added
    - Add servermgr.Server create_service() and remove_service() methods.

- Changed
    - Don't perform a remote appcmd call on the local host in iispy.
    - Upgraded docker to 4.0.1.
    - Upgraded psutil to 5.6.3.
    - Upgraded PyQt to 5.12.2.
    - Upgraded requests to 2.22.0.


[35.0.0] - 2019-05-08
---------------------
- Changed
    - Allow ConfigCollection to take a pathlib.Path object.
    - Fix error in qbpy.QuickBuildCfg._get_id().
    - Fix configmgr parent/include processing.
    - Upgraded psutil to 5.6.2.
    - Upgraded setuptools to 41.0.1.

[34.0.0] - 2019-04-25
---------------------
- Added
    - Added CopyBuilder and CopyProduct to build module.
    - Added option to both publish and extract files from docker container.
    - Added __setattr__(), enable(), and disable() to qbpy.QuickBuildCfg.
    - Added qbpy.QuickBuildBuild class to support wait flag in QuickBuildCfg.disable().

[33.1.0] - 2019-04-17
---------------------
- Added
    - Added redirect_output argument to build.MSBuildBuilder.
    - Added Server.get_scheduled_task_list() method.
    - Added Server.get_service_list() method.

- Changed
    - Fixed issues with C-Sharp version files and created Builder.update_cs_assemblyinfo().
    - Upgraded docker to 3.7.2.
    - Upgraded setuptools to 41.0.0.
    - Upgraded unittest-xml-reporting to 2.5.1.
    - Fixed lang.str_to_pythonval() to convert None.

[33.0.2] - 2019-03-26
---------------------
- Changed
    - Upgraded docker to 3.7.1.
    - Upgraded psutil to 5.6.1.
    - Upgraded PyQt5 to 5.12.1.

[33.0.1] - 2019-03-22
---------------------
- Changed
    - Replace use of property decorator when getter has optional arguments.

[33.0.0] - 2019-03-05
---------------------
- Added
    - Added support for extracting build artifacts from container builds.

- Changed
    - Use property decorator.
    - Fix bad use of self.
    - Don't install cx_Freeze if Python > 3.6.
    - Upgraded psutil to 5.5.1.
    - Upgraded pyodbc to 4.0.26.

- Removed
    - Removed virtualenv.

[32.0.0] - 2019-02-14
---------------------
- Added
    - Added support for nested configurations.
    - Added build.ConfigurationBuilder() argument ignore_configs.
    - Added start and stop methods to iispy.IISInstance.
    - Added ignore_files and no_expand_files to build.ConfigurationBuilder and expander.Expander.expand_directory().
    - Added prdb.Product.children property.

- Changed
    - Server().get_iis_instance() should return local reference.
    - Made all names more Pythonic.
    - Made module constants into class member variables where possible.
    - Fixed usage of configure and make in GNUBuilder.
    - Upgraded psutil to 5.5.0.
    - Upgraded pyQt to 5.12.
    - Upgraded setuptools to 40.8.0.

[31.0.0] - 2019-01-11
---------------------
- Added
    - Added qbpy.QuickBuildCfg.remove() method.

- Changed
    - Fix git errors on push not throwing catch-able exceptions.
    - Updated PRDB schema to use good python naming convention.
    - Make sure iispy module does not cause an import failure on Linux.
    - Provide proper iteration on groups, classes, and properties in prdb module.
    - Provide interface for adding a property class.
    - Upgraded docker to 3.7.0.
    - Upgraded p4python to 2018.2.1743033.
    - Upgraded pyodbc to 4.0.25.
    - Upgraded unittest-xml-reporting to 2.2.1.

[30.0.3] - 2019-01-09
---------------------
- Changed
    - Fix expander.Expander.evaluate_expression().

[30.0.2] - 2018-12-18
---------------------
- Changed
    - Fix build.EUPBuilder commander.Commander variable handling.

[30.0.1] - 2018-12-17
---------------------
- Changed
    - Revert inadvertent PRDB schema change.

[30.0.0] - 2018-12-13
---------------------
- Changed
    - Improved platarch.Platform().
    - Use commander.Commander() to parse build arguments.
    - Improved cx_Freeze package creation logic.
    - Moved cmds functions to sysutil.
    - Renamed cmds module to commander.
    - Upgraded docker to to 3.6.0.
    - Upgraded psutil to to 5.4.8.
    - Upgraded requests to 2.21.0.
    - Upgraded setuptools to 40.6.3.
    - Final Pylint cleanup.

- Removed
    - Moved BaRT specific support module to BaRT.

[29.1.1] - 2018-11-29
---------------------
- Changed
    - Fixed remote_powershell member of iispy.IISInstance.

[29.1.0] - 2018-11-27
---------------------
- Added
    - Added no_powershell option to iispy.IISInstance.

[29.0.2] - 2018-11-20
---------------------
- Changed
    - Fix double remote option sent to syscmd by iispy.appcmd().

[29.1.0] - 2018-11-02
---------------------
- Changed
    - User the docker client to manage Google registry images.
    - Upgraded setuptools to 40.5.0.

[29.0.1] - 2018-10-24
---------------------
- Changed
    - Fixed servermgr.Service.get_service() on Windows.

[29.0.0] - 2018-10-22
---------------------
- Added
    - Added servermgr.LoadBalancer support for adding a VIP.
    - Added upstart support to servermgr.Service().

- Changed
    - Fixed SysV service management in servermgr.LinuxService.
    - Upgraded docker to to 3.5.1.
    - Upgraded requests to 2.20.0.

[28.0.3] - 2018-10-10
---------------------
- Changed
    - Fixed service servermgr service detection on non-systemctl Linux systems.

[28.0.3] - 2018-10-08
---------------------
- Changed
    - Pass credentials on remote command in servermgr.Server.run_command().

[28.0.2] - 2018-10-04
---------------------
- Changed
    - Upgraded PyQt to to 5.11.3.
    - Upgraded pywin32 to 224.

[28.0.1] - 2018-10-02
---------------------
- Changed
    - Fixed issue with servermgr.LinuxService.status failing on Linux2.

[28.0.0] - 2018-09-26
---------------------
- Added
    - Added support for running remote commands using PowerShell from Windows to Windows.

- Changed
    - Pylint cleanup of servermgr module.

- Removed
    - Removed sqlscript module.

[27.3.0] - 2018-09-24
---------------------
- Added
    - Added virtual directory support to iispy.IISObject management.

- Changed
    - Improved appcmd handling in iispy module.
    - Upgraded setuptools to 40.4.3.
    - Pylint cleanup of setup.py.

[27.2.0] - 2018-09-19
---------------------
- Added
    - Added start/stop support to iispy.IISObject management.

- Changed
    - Upgraded setuptools to 40.4.1.
    - Pylint cleanup in iispy module.

[27.1.0] - 2018-09-07
---------------------
- Changed
    - Improved cms.Client.merge().

[27.0.0] - 2018-08-24
---------------------
- Added
    - Added cms.Client.chmod_files().

- Changed
    - Fix build.DockerDotNetCoreProduct() default for verfiles.
    - Return AttributeError to fix hasattr() usage.
    - Fixed issue with cms.Client.switch() creating existing branch.
    - Convert cms to use arg list rather than requiring lists.
    - Upgraded docker to 3.5.0.
    - Upgraded google-cloud to 0.34.0.
    - Upgraded psutil to 5.4.7.
    - Upgraded pyodbc to 4.0.24.
    - Upgraded setuptools to 40.2.0.
    - Pylint cleanup on cms module.

[26.4.3] - 2018-08-08
---------------------
- Changed
    - Ignoring stderr in cloudmgr.Image.manage().

[26.4.2] - 2018-08-08
---------------------
- Changed
    - Ignoring stderr in cloudmgr.Image.tag().
    - Pylint cleanup on cloudmgr module.

[26.4.1] - 2018-08-08
---------------------
- Changed
    - Fixed issue with cmds.SysCmdRunner keeping keys from last run.
    - Fix expander.Expander.expand_file() failure when intermediate empty directories don't exist.
    - expander.Expander.expand_directory() double recurses into directories.
    - Pylint cleanup on expander module.

[26.4.0] - 2018-08-01
---------------------
- Added
    - Added build.DockerNodeProduct() and build.DockerDotNetCoreProduct().

- Changed
    - Fix qbpy issues.
    - Upgraded GitPython to 2.1.11.
    - Upgraded setuptools to 40.0.0.

[26.3.0] - 2018-07-13
---------------------
- Added
    - Added timeout parameter to servermgr.Process.manage().

- Changed
    - Fixed timeout checks in servermgr.

[26.2.0] - 2018-07-12
---------------------
- Added
    - Added timeout parameter to servermgr.Service.manage().

- Changed
    - sysutil.syscmd(): Add an extra -t to ssh on remote calls to prevent blocking in some situations.

[26.1.3] - 2018-07-11
---------------------
- Changed
    - Re-enable remove service management for Linux.

[26.1.2] - 2018-07-09
---------------------
- Changed
    - Missed case compare change when running on Windows.

[26.1.1] - 2018-07-09
---------------------
- Changed
    - Ignore case on Windows when running command drivers.

[26.1.0] - 2018-07-05
---------------------
- Added
    - Added pyodbc module at version 4.0.23.

- Changed
    - Upgraded docker to 3.4.1.
    - Upgraded PyQt5 to 5.11.2.

[26.0.1] - 2018-06-29
---------------------
    - Fixed issues where servermgr.Server().get_service() thrown an error rather than None if the service is not found on CentOS 6.9.

[26.0.0] - 2018-06-29
---------------------
- Added
    - Added support for Linux processes in servermgr.
    - Added EUPBuilder and EUPProduct.

- Changed
    - Fixed issues with servermgr.ServerPath when Server is local.
    - Improved servermgr.ServerPath.copy() logic when remote is local.
    - Upgraded requests to 2.19.1.
    - Upgraded docker to 3.4.0.

[25.0.1] - 2018-06-06
---------------------
- Changed
    - Fix issue setting default verfiles for MSBuild DB projects.

[25.0.0] - 2018-06-06
---------------------
- Changed
    - Remove product definition defaults except for name from prdb.ProductDB.add_product().

[24.1.0] - 2018-06-05
---------------------
- Added
    - Added support for new code roll parameters to prdb.ProductDB.add_product().

[24.0.1] - 2018-06-05
---------------------
- Changed
    - Fix version calculations in build module.

[24.0.0] - 2018-06-05
---------------------
- Added
    - Added pkgtype arg to build.MavenBuilder class.
    - Added ant support.
    - Added support for creating, switching and merging git branches.

- Changed
    - Pass release argument to maven in build.MavenBuilder.
    - Moved argument processing from build execution to Product instantiation.
    - Converted initializers to use tuple() instead of None guard.
    - Accept default args in ActionCommandRunner.
    - Improved git branch management.
    - Upgraded google-cloud to 0.33.1.
    - Upgraded GitPython to 2.1.10.
    - Upgraded setuptools to 39.2.0.
    - Upgraded unittest-xml-reporting to 2.2.0.

[23.0.0] - 2018-05-01
---------------------
- Changed
    - Upgraded docker to 3.3.0.
    - Upgraded setuptools to 39.1.0.

- Removed
    - Removed sysutil.recopytree().

[22.2.2] - 2018-04-25
---------------------
- Changed
    - Remove Google Cloud login on every command.

[22.2.1] - 2018-04-25
---------------------
- Changed
    - Need to login to Google Cloud instance before every command.

[22.2.0] - 2018-04-24
---------------------
- Added
    - Added lang.flatten() and flatten_output argument to sysutil.syscmd().

- Changed
    - GitPython doesn't handle pathlib.Path objects.

[22.1.5] - 2018-04-18
---------------------
- Changed
    - Fixed issue where fileutil.unpack does not work if dest argument is used.

[22.1.4] - 2018-04-17
---------------------
- Changed
    - Fixed minor_version calculation for single word versions.

[22.1.3] - 2018-04-17
---------------------
- Changed
    - Fixed minor_version calculation for single word versions.

[22.1.2] - 2018-04-16
---------------------
- Removed
    - Removed pypiwin32 since docker specifies a fixed version.

[22.1.1] - 2018-04-16
---------------------
- Added
    - Added pypiwin32 back as it is used by some other package.

- Changed
    - Fix minor issues with maven builds.

[22.1.0] - 2018-04-13
---------------------
- Added
    - Added build.VisualStudioDatabase product type.
    - Added build.MavenBuilder and MavenProduct.
    - Added ability to parse python data types in lang.str_to_pythonval().
    - Added append_stderr option to sysutil.syscmd().

- Changed
    - Fix fileutil.unpack to work with pathlib.Path objects.
    - Upgrade docker to 3.2.1.
    - Improved SQLScript.execute().

[22.0.0] - 2018-03-30
---------------------
- Added
    - Added cmds.SysCmdRunner as a generalized replacement of build.run_build_command.
    - Added cloudmgr module.
    - Added support for adding and removing IIS sites, apps, and pools.
    - Added support for adding and removing servermgr.ScheduledTask.

- Changed
    - Added ability to use hallog.Logger without writing to a file.
    - Make sure npm calls fail when returning a non-zero error code.
    - Fixed issue with setting a null list of version files on MSBuildBuilder.
    - Update docker to 3.1.4.
    - Update GitPython to 2.1.9.

[21.0.0] - 2018-03-19
---------------------
- Added
    - Added artifact archive support to base Builder class.

- Changed
    - Fix Windows to Windows remote file copy in servermgr.ServerPath().copy().
    - Fix build.ConfigurationBuilder use of verfiles.
    - Update docker to 3.1.3.

- Removed
    - Removed automated post-build expansion of config files in build.Builder.execute().
    - Removed arch argument to build.Builder.

[20.0.0] - 2018-03-19
---------------------
-Changed
    - Overhaul servermgr.ServerPath() to subclass pathlib.PurePath().
    - Update setuptools to 39.0.1.

[19.0.2] - 2018-03-16
---------------------
-Changed
    - Fixed use of walk with Path().

[19.0.1] - 2018-03-14
---------------------
-Changed
    - Use the --pull option on docker builds.

[19.0.0] - 2018-03-13
---------------------
- Added
    - Added branch and environment information to PRDB.
    - Added support for .Net Core versioning in .csproj files.

-Changed
    - Changed from os.path usage to pathlib.Path.
    - Update docker to 3.1.1
    - Update PyQt5 to 5.10.1
    - Update pywin32 to 223
    - Update setuptools to 38.5.2

- Removed
    - Removed the PRDB build, release, and revision information.
    - Removed workspace and cmsclient support.

[18.0.0] - 2018-02-21
---------------------
- Added
    - Added build.DockerUnitTester for extracting test results run during Docker image build.

- Changed
    - Use Docker Python API instead of Docker CLI.

- Removed
    - Removed the civars.txt file.

[17.1.3] - 2018-02-19
---------------------
- Added
    - Added Docker Python API.

- Changed
    - Fixed servermgr module use of sysutil.syscmd.

[17.1.2] - 2018-02-13
---------------------
- Changed
    - Improved menu.SimpleMenu implementation.
    - Update setuptools to 38.5.1
    - Update unittest-xml-reporting to 2.1.1
    - Update p4python to 2017.2.1615960

[17.1.1] - 2018-02-01
---------------------
- Changed
    - Fixed issue using both lists and tuples.

[17.1.0] - 2018-01-30
---------------------
- Added
    - Added extra_vars argument to build.ConfigurationBuilder.

[17.0.0] - 2018-01-29
---------------------
- Changed
    - Update pypiwin32 to 222.
    - Update PyQt5 to 5.10.
    - Changed the repo reference file name.
    - Always publish repo references in artifacts directory for Docker builds.

- Removed
    - Removed slacker dependency.
    - Removed obsolete static variable.

[16.1.0] - 2018-01-18
---------------------
- Added
    - Added support for Docker images push to Google Cloud registry.

[16.0.1] - 2018-01-11
---------------------
- Changed
    - Fixed build.VisualStudioApplication to work with MSBuildBuilder changes.

[16.0.0] - 2018-01-10
---------------------
- Added
    - Added netutil.download.
    - Added support for enabling/disabling system services.
    - Added to sysutil: create_user, create_groups.

- Changed
    - Replace sysutil.chmodtree with chmod/chown with recursive parameter.
    - Make Cmd driver processing case-sensitive.
    - Update sysutl.syscmd to take command, arg1, arg2 rather than cmdspec.
    - Updated internal version number to three digits.
    - Fixed error with unpacking compressed tar files.
    - Update setuptools to 38.4.0.

[15.4.0] - 2017-12-19
---------------------
- Added
    - Improved MSTest support.
    - Build completed successfully message.

- Changed
    - Update default version file for webapp project type.
    - Update setuptools to 38.2.4.
    - Update virtualwrapper-win to 1.2.5.
    - Update GitPython to 2.1.8.
    - Update cx_Freeze to 5.1.1.

[15.3.0] - 2017-12-07
---------------------
- Added
    - Added VisualStudioWebsite and VisualStudioWebapp.

- Changed
    - Improve product and builder argument handling.
    - Added leader to build messages.
    - Change Docker tag to be just the buildname.

- Removed
    -Removed vsver argument to Visual Studio products and builders.

[15.2.0] - 2017-11-30
---------------------
- Added
    - Added create_package argument to CxFreezeBuilder.

- Changed
    - Don't require packages which aren't available in Docker Alpine containers.
    - Don't install PyQt5 on unsupported Linux distributions.
    - Improve Linux build OS determination in platarch.get_type.

[15.1.1] - 2017-11-29
---------------------
- Changed
    - Make sure all __getattr__ calls raise AttributeError on failure.

[15.1.0] - 2017-11-28
---------------------
- Added
    - Added VisualStudioWebapp product type.
    - Added hasapp option to VisualStudioWebsite product type.

- Changed
    - Update setuptools to 38.2.3.

[15.0.5] - 2017-11-27
---------------------
- Changed
    - Update setuptools to 38.2.1.
    - Update PyQt5 to 5.9.2.

[15.0.4] - 2017-11-22
---------------------
- Changed
    - Updated multi-server build config file handling.
    - Update setuptools to 37.0.0.
    - Update virtualwrapper-win to 1.2.4.
    - Update PyQt5 to 5.9.1 on Linux.

[15.0.3] - 2017-11-16
---------------------
- Changed
    - Fix multi-server build config file handling.

[15.0.2] - 2017-11-15
---------------------
- Changed
    - Fix build config file handling.

[15.0.1] - 2017-11-13
---------------------
- Changed
    - PyQt5 downgraded to 5.9 on Linux since 5.9.1 is not available.

[15.0.0] - 2017-11-13
---------------------
- Changed
    - Improve the way build arguments are passed to the build through the command line.
    - Allow more control of docker registry push.
    - Don't print debugging output unless environment variable set.
    - Updated dependencies: setuptools to 36.7.1, PyQt5 to 5.9.1.

[14.0.4] - 2017-11-08
---------------------
- Changed
    - Add more ignore strings to npm build.

[14.0.3] - 2017-11-06
---------------------
- Changed
    - PROG_FILES should have the same data type on Linux as Windows.

[14.0.2] - 2017-11-06
---------------------
- Changed
    - Fixed issue with PROG_FILES import on Linux.

[14.0.1] - 2017-11-06
---------------------
- Changed
    - Fixed issue with PROG_FILES import on Linux.

[14.0.0] - 2017-11-06
---------------------
- Added
    - Added VisualStudioBuilder and VisualStudioWebsite.
    - Added MSTestUnitTester.
    - Added support for running remote commands on a different OS.
    - Add cross-platform support to servermgr module.
    - Moved Procedure classes from HAL to new expander module.

- Changed
    - Moved Expander from fileutil to new expander module.
    - Fix Node build on Windows.
    - Allow servermgr.Server() usage to default to localhost.
    - Renamed all Exceptions to Errors.
    - Update setuptools to 36.6.0.
    - Update virtualwrapper-win to 1.2.3.

- Remove
    - netutil.remote_copy replaced by servermgr.ServerPath.copy.

[13.2.3] - 2017-10-09
---------------------
- Changed
    - Fix Node build on Windows.

[13.2.2] - 2017-10-03
---------------------
- Changed
    - Update GitPython to 2.1.7.

[13.2.1] - 2017-09-28
---------------------
- Changed
    - Add more strings to ignore during npm commands.

[13.2.0] - 2017-09-26
---------------------
- Changed
    - Improve Node.js builds.
    - Update GitPython to 2.1.6.

[13.1.4] - 2017-09-25
---------------------
- Changed
    - Inhibit un-checkout on PRDB close for Git.

[13.1.3] - 2017-09-21
---------------------
- Changed
    - Speed up Git info clients by cloning to depth 1.

[13.1.2] - 2017-09-21
---------------------
- Removed
    - IMPORT_GIT and IMPORT_PERFORCE don't work as expected.

[13.1.1] - 2017-09-21
---------------------
- Added
    - IMPORT_GIT control flag.

[13.1.0] - 2017-09-21
---------------------
- Added
    - Added support for Docker builds.
    - Added Git support.

- Changed
    - Update setuptools to 36.5.0.
    - Update virtualwrapper-win to 1.2.2.

[13.0.2] - 2017-08-28
---------------------
- Changed
    - Update requests to 2.18.4.
    - Update setuptools to 36.3.0.
    - Update slacker to 0.9.60.

[13.0.1] - 2017-08-24
---------------------
- Changed
    - Removed extraneous period in package creation.
    - Create the package using LZMA compression.
    - Update chmod usage for better UNIX support.

[13.0.0] - 2017-08-22
---------------------
- Added
    - Added build.GNUProduct class.

- Changed
    - Improved build.GNUBuilder.

[12.2.0] - 2017-08-18
---------------------
- Added
    - SERVICE_SIGNALS.restart for use with servermgr.Service on Linux.
    - More debugging output from sysutil.syscmd.

- Changed
    - Throw away output on Linux when remotely managing a service to avoid intermittent hang.

[12.1.2] - 2017-08-17
---------------------
- Changed
    - Protect cms against fake git import.

[12.1.1] - 2017-08-14
---------------------
- Changed
    - Add -t argument to ssh on remote Linux commands to prevent hangs.

[12.1.0] - 2017-08-11
---------------------
- Added
    - Add Linux support to build.CxFreezeBuilder.
    - Added LZMA (xz) creation support to fileutil.pack.

- Removed
    - Remove workaround for Python 3.6.0 bug from build.CxFreezeBuilder.

[12.0.0] - 2017-08-08
---------------------
- Added
    - Linux support for servermgr.Service and sysutil.syscmd with remote=True.

[11.1.0] - 2017-08-07
---------------------
- Added
    - Added config property to configmgr.ConfigCollection.
    - Added build.ConfigurationBuilder and build.ConfigurationProduct classes.

- Changed
    - Update requests to 2.18.3.
    - Update setuptools to 36.2.7.

[11.0.3] - 2017-07-12
---------------------
- Changed
    - Improve symlink handing in build.NodeJSBuilder.
    - Update p4python to 2017.1.1526044.
    - Update PyQt5 to 5.9.

[11.0.2] - 2017-07-05
---------------------
- Changed
    - Protect sysutil.syscmd against spaces in commands and argument names when using the shell.
    - Minor NodeJSBuilder improvements.
    - Improve lang.str_to_pythonval algorithm.
    - Fix missing import.

[11.0.1] - 2017-06-20
---------------------
- Changed
    - Add is_local property to servermgr.Server.
    - Improve error checking on robocopy in servermgr.ServerPath.copy method.

[11.0.0] - 2017-06-19
---------------------
- Changed
    - The handling of build information the build module has been overhauled to remove reliance on the command line and PRDB.
    - Update requests to 2.18.1 and setuptools to 36.0.1.

[10.0.3] - 2017-06-15
---------------------
- Changed
    - When sysutil.syscmd is run with useshell, pass the command and args as a string to Popen as suggested by the documentation.

[10.0.2] - 2017-06-14
---------------------
- Changed
    - Catch any PyQt load failure in version module to protect against missing GNUC libs.
    - Determine users home directory in a cross-platform way.
    - Rename some variables from 'hal.'

[10.0.1] - 2017-06-09
---------------------
- Changed
    - The node npm command needs to be run by the shell.

[10.0.0] - 2017-06-01
---------------------
- Added
    - Converted the envcfg module to configmgr.
    - Added Linux support.
    - Added GNUBuilder.
    - Added statemachine.StateMachine.reset method.
    - Added statemachine.StateMachine.start method to facilitate crash recovery.

- Changed
    - Update error related to Linux support.
    - The servermgr.Server.run_command method should not run the command remotely if the server is local.
    - Add more files ignored when build.NodeBuilder publishes.
    - Updated dependencies: cx-Freeze to 5.0.2, requests to 2.17.3, slacker to 0.9.50.

[9.0.0] - 2017-05-16
--------------------
- Added
    - Added support for using the node package.json file as a version file.

- Changed
    - Change WMIObject type to a string to allow grabbing any available.

[8.0.1] - 2017-05-08
--------------------
- Added
    - Added dependency on P4Python.
    - Add privileged run option to psexec in sysutil.syscmd.

- Changed
    - Upgrade setuptools to 35.0.2.
    - Ignore more robocopy codes that indicate success in servermgr.ServerPath.copy.
    - Fix issue with LoadBalancer management of a Server without DNS name resolution available.

[8.0.0] - 2017-04-26
--------------------
- Changed
    - Raise ServerObjectManagementException on all COM and WMI connection errors.

[7.1.0] - 2017-04-24
--------------------
- Changed
    - Improved build.MochaTest.

[7.0.0] - 2017-04-24
--------------------
- Added
    - Require the unittest-xml-reporting package.
    - build.PythonUnitTester.
    - build.MochaTester.

- Changed
    - Updated build for new build.Product definition.

[6.0.1] - 2017-04-21
--------------------
- Changed
    - Update build.run_system_command for new syscmd usage.

[6.0.0] - 2017-04-20
--------------------
- Added
    - servermgr.LoadBalancer.get_cache_content_group and flush_cache_content.

- Changed
    - Changed servermgr.Server wmi_connect arg to defer_wmi.
    - Let servermgr.Server make WMI connection when needed.
    - Fixed statemachine unit tests.
    - Update iispy.IISConfigurationSection to be more section generic.
    - Upgrade setuptools to 35.0.1.

[5.0.0] - 2017-04-17
--------------------
- Added
    - servermgr.Server.remove_directory method.
    - ServerPath object for better remote file management.

- Changed
    - servermgr.Server.run_remote_command method change to run_command.
    - Allow servermgr.Server.run_command to take a string or list argument.
    - Fixed issue with statemachine rollback.
    - Allow the IP Address to be passed in to Server to get around lack of name resolution.
    - Fix problems with LoadBalancer usage of Server objects.
    - Provide enum for Service states.
    - Delete WMI object reference before refreshing to prevent locking the WMI interface.
    - Increase the wait time for service state checks.
    - Return result from send in netutil.send_email.

[4.4.0] - 2017-04-05
--------------------
- Added
    - Ability to pass credentials to sysutil.syscmd when running remotely.
    - Ability to inhibit WMI connection on servermgr.Server instantiation.
    - servermgr.Server.run_remote_command method.
    - Provide servermgr.COMObject.disconnect() method.

- Changed
    - Improve servermgr.ServerObjectManagementException.REMOTE_PERMISSION_ERROR wording.
    - Allow servermgr.COMObject to be initialized with a win32com client object.

[4.3.1] - 2017-04-03
--------------------
- Added
    - Provide log_filename property for hallog.Logger.
    - Fix system command call in sqlscript.

- Changed
    - Pin requirements to specific versions.

[4.3.0] - 2017-03-31
--------------------
- Added
    - New envcfg module.

- Changed
    - Fixed sqlscript usage of syscmd.

[4.2.0] - 2017-03-29
--------------------
- Added
    - Authorization parameter to SQLScript.
    - Authorization parameter to servermgr objects.
    - Process management to servermgr.
    - Ability to redirect output to a Qt widget.
    - Added COM support to server mgr.
    - Added IIS support to servermgr.Server.
    - Check for server existence in servermgr.Server.
    - Provide iispy.IISInstance.exists property.
    - Default cmds.Commander option of --quiet.
    - cmds.Commander --raise-on-error parameter to throw errors when parser problem.
    - Ability to get current hallog.Logger.level.

- Changed
    - Use closing and suppress from contextlib.
    - Fix sys module usage.
    - Allow SQLScript to be used in a with statement.
    - Return output from iispy.IISInstance.reset.

[4.1.1] - 2017-03-21
--------------------
- Changed
    - Updated DEFAULT_PRODUCT_DB.
    - Make Logger logname argument required.

[4.1.0] - 2017-03-20
--------------------
- Added
    - Added rollback method to StateMachine.
    - Added exist property to Service.

- Changed
    - Convert possible string to server object in LoadBalancer method.

[4.0.0] - 2017-03-17
--------------------
- Added
    - Added the statemachine module.
    - Added the servermgr module.
    - Added requirement for slacker module.
    - Added requirement for WMI module.

- Changed
    - Update setuptools to 34.3.2.
    - Throw RaiseAttribute when appropriate.

- Removed
    - Removed the singleton implementations since those can be handled with global instances in Python.

[3.0.0] - 2017-03-09
--------------------
- Changed
    - Allow fileutil.Expander use non-strings for replacement.
    - Fix issue with use of variable named 'path' in sysutil module.
    - Rename home directory variable.
    - Update PyQt to 5.8.1.1.
    - Update setuptools to 34.3.1.

[2.0.1] - 2017-03-07
--------------------
- Changed
    - Fixed crash when the command is not in the driver.
    - Fixed problem in fileutil.Expander.expand_directory() where it did not popd().

[2.0.0] - 2017-03-03
--------------------
- Changed
    - Improve expansion condition evaluation when the condition contains a variable.
    - Cleanup expression condition exception handling.
    - Fix issue with Perforce integration.
    - Rename iispy member function to be consistent.

[1.0.1] - 2017-02-27
--------------------
- Changed
    - Fixed issues with XML parsing.
    - Upgrade setuptools to 34.3.0.

[1.0.0] - 2017-02-21
--------------------
- Changed
    - Fixed bad imports.
    - Fixed bad return in str_to_pythonval.
    - Change xml parser to standard in xml module.
    - Rename constant in data module to uppercase.
    - Fix issue in data module when returning columns in XML table.
    - Upgrade PyQt5 to 5.8.
    - Upgrade setuptools to 34.2.0.

[0.12] - 2017-02-09
-------------------
- Changed
    - Improved Cmd error handling.
    - Fixed import issue.

[0.11] - 2017-02-09
-------------------
- Added
    - Created fileutil module from file-related init functions.

- Changed
    - Moved system-related init functions to sysutil.
    - Convert expander to a class.
    - Don't raise custom exceptions inside standard ones.
    - Fix typo in str_to_pythonval().
    - Cleanup fileutil.spew().

- Removed
    - Move procedure module to HAL.

[0.10] - 2017-02-07
-------------------
- Changed
    - Update setup.py to include all required modules.

[0.9] - 2017-02-06
------------------
- Changed
    - Update CxFreezeBuilder to handle Python 3.6.0 issue with process module.

[0.8] - 2017-02-06
------------------
- Added
    - sysutil.is_user_administrator()

[0.7] - 2017-02-03
------------------
- Added
    - Support for building Python applications using cx_Freeze.
    - Support for debugging output during syscmd execution.
    - Module for remote IIS administration.
    - bool_to_str().
    - Support for running commands on remote systems.
    - Created netutil and sysutil modules.
    - Require xmltodict (for new iispy module).
    - Modules for network and system utilities created from __init__ functions.

- Changed
    - Upgraded requests module.
    - Moved is_debug from module initialization to lang submodule.
    - Rename debug environment variable from HAL_DEBUG.
    - Use new Python 3 super().
    - Update syscmd to use new Python 3 subprocess module features.
    - Cleanup imports.
    - Inhibit return of stderr lines when ignorestderr is set in syscmd.

-Removed
    - Serialization support from syscmd.

[0.6] - 2017-01-27
------------------
- Changed
    - Use USERPROFILE for default PRDB database.

[0.5] - 2017-01-27
------------------
- Added
    - CHANGELOG.rst.

- Changed
    - Allow the command line parser to be passed in.
    - Update the location of the default product database.

[0.4] - 2017-01-25
------------------
- Added
    - Unit tests.

- Changed
    - When an application calls get_version_info(), return info for the app and not this module.
    - Improved get_version_info() output format.

[0.3] - 2017-01-17
------------------
- Added
    - Support for deployment automation.

[0.2] - 2017-01-16
------------------
- Added
    - Support for building Node.js applications.

- Changed
    - Improved output during automation.

[0.1] - 2017-01-12
------------------
- Initial release.
