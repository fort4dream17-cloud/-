@echo off
setlocal
rem Run once in the registered runner folder, or pass its full path as argument.
rem Adds a current-user startup entry only; no password, policy or admin changes.
set "FLOW_RUNNER_DIR=%~1"
if not defined FLOW_RUNNER_DIR set "FLOW_RUNNER_DIR=%CD%"
if not exist "%FLOW_RUNNER_DIR%\run.cmd" (
  echo ERROR: run.cmd missing. Run this from your registered actions-runner folder.
  exit /b 1
)
if not exist "%FLOW_RUNNER_DIR%\.runner" (
  echo ERROR: This folder is not a configured GitHub runner.
  exit /b 1
)
set "FLOW_STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\CoverageFlowRunner.cmd"
> "%FLOW_STARTUP%" echo @echo off
>> "%FLOW_STARTUP%" echo cd /d "%FLOW_RUNNER_DIR%"
>> "%FLOW_STARTUP%" echo call run.cmd
echo Installed startup entry for the current Windows user.
echo The runner starts after Windows sign-in. PC must be on and network IP registered.
echo If a runner console is already running, keep it. Otherwise run run.cmd now.
echo Undo: delete "%FLOW_STARTUP%"
