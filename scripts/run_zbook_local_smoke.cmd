@echo off
setlocal EnableExtensions DisableDelayedExpansion
title H.E.R.B.I.E. and Baby Vision - Local Ollama Smoke Test

echo ==========================================================
echo  H.E.R.B.I.E. AI Network - ZBook Local Smoke Test (V0.2d)
echo ==========================================================
echo This uses reviewed GitHub branches and localhost only.
echo No merges, deployments, paid services, or remote listeners.
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo BLOCKED: Git for Windows is not installed or is not on PATH.
  goto :blocked
)
where py >nul 2>&1
if errorlevel 1 (
  echo BLOCKED: The Python launcher is not available.
  goto :blocked
)
py -3.12 --version >nul 2>&1
if errorlevel 1 (
  echo BLOCKED: Python 3.12 is unavailable.
  goto :blocked
)
where ollama >nul 2>&1
if errorlevel 1 (
  echo BLOCKED: Ollama CLI is unavailable.
  goto :blocked
)

set "WORK=%USERPROFILE%\AI-Network-Review-%RANDOM%-%RANDOM%"
if exist "%WORK%" (
  echo BLOCKED: A review folder with this name already exists. Run the file again.
  goto :blocked
)
mkdir "%WORK%"
if errorlevel 1 (
  echo BLOCKED: Could not create a review folder.
  goto :blocked
)

echo Cloning the unified H.E.R.B.I.E. integration candidate and Baby Vision worker branch...
git clone --quiet --depth 1 --single-branch --branch codex/v02d-real-ollama-local-smoke "https://github.com/jimedusot-beep/Herbie-Baby-Vision.git" "%WORK%\BabyVision"
if errorlevel 1 (
  echo BLOCKED: Could not clone the Baby Vision review branch.
  goto :blocked
)
git clone --quiet --depth 1 --single-branch --branch integration/herbie-engineering-20261031 "https://github.com/jimedusot-beep/Herbie.git" "%WORK%\HerbieGateway"
if errorlevel 1 (
  echo BLOCKED: Could not clone the H.E.R.B.I.E. review branch.
  goto :blocked
)

echo Verifying exact reviewed Git source blobs...
set "CLIENT_SHA="
set "SMOKE_SHA="
set "GATEWAY_SHA="
for /f "delims=" %%H in ('git -C "%WORK%\BabyVision" rev-parse HEAD:agents/herbie_gateway_client.py') do set "CLIENT_SHA=%%H"
for /f "delims=" %%H in ('git -C "%WORK%\BabyVision" rev-parse HEAD:integration/live_ollama_smoke.py') do set "SMOKE_SHA=%%H"
for /f "delims=" %%H in ('git -C "%WORK%\HerbieGateway" rev-parse HEAD:socratic-agent/socratic_agent/worker_gateway.py') do set "GATEWAY_SHA=%%H"

if /I not "%CLIENT_SHA%"=="96056a3aed2328f4a55b1030788672de61c04235" (
  echo BLOCKED: Baby Vision client has changed since review. Do not bypass verification.
  goto :blocked
)
if /I not "%SMOKE_SHA%"=="173210caba7350dae0d5ce80b3d704580cc46fbe" (
  echo BLOCKED: Smoke-test harness has changed since review. Do not bypass verification.
  goto :blocked
)
if /I not "%GATEWAY_SHA%"=="2a591120c01815698d9a0c7d4c7e3a1005b75936" (
  echo BLOCKED: H.E.R.B.I.E. gateway has changed since review. Do not bypass verification.
  goto :blocked
)

echo.
echo Checking installed local Ollama models...
ollama list
if errorlevel 1 (
  echo BLOCKED: Ollama is not responding on this laptop.
  goto :blocked
)

echo.
echo Running real local inference AND one bounded coding task on a generated trusted fixture...
py -3.12 "%WORK%\BabyVision\integration\live_ollama_smoke.py" --run-live --run-fixture-task --model gemma3:1b --gateway-file "%WORK%\HerbieGateway\socratic-agent\socratic_agent\worker_gateway.py"
if errorlevel 1 (
  echo.
  echo The model test was BLOCKED or failed. See the reason code above.
  goto :blocked
)

echo.
echo SUCCESS: Authenticated local inference and bounded worker fixture completed.
echo This does not prove remote networking, merged code, or production safety.
echo Review copies: "%WORK%"
echo Copy only the sanitized JSON result above into ChatGPT.
echo.
pause
exit /b 0

:blocked
echo.
echo No deployment or merge was performed.
if defined WORK echo Review copies, if created: "%WORK%"
echo Share only the sanitized error or reason code. Do not share credentials.
echo.
pause
exit /b 1
