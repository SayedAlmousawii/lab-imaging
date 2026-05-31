@echo off
setlocal
cd /d "%~dp0"

echo Starting Lab Imaging...
echo.

if not exist "LabImaging.exe" (
  echo LabImaging.exe was not found in this folder.
  echo Make sure you are running this file from the LabImagingPortable folder.
  echo.
  pause
  exit /b 1
)

"%~dp0LabImaging.exe"
set EXITCODE=%ERRORLEVEL%

echo.
if not "%EXITCODE%"=="0" (
  echo Lab Imaging stopped with an error. The messages above may explain what happened.
) else (
  echo Lab Imaging has stopped.
)
echo.
pause
exit /b %EXITCODE%
