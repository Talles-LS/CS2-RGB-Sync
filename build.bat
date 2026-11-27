@echo off
setlocal enabledelayedexpansion

echo === CS2 RGB Sync - Build Completo ===

set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo [ERRO] Ambiente virtual .venv nao encontrado.
    exit /b 1
)

echo [1/5] Executando testes automatizados (pytest)...
set "QT_QPA_PLATFORM=offscreen"
"%PYTHON_EXE%" -m pytest -v
if errorlevel 1 (
    echo [ERRO] Testes falharam. Build abortado.
    exit /b 1
)

echo [2/5] Gerando icones e MANUAL_INSTALACAO.pdf...
"%PYTHON_EXE%" tools\generate_icon.py
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" tools\generate_manual_pdf.py
if errorlevel 1 exit /b 1

echo [3/5] Compilando versao onedir (PyInstaller)...
"%PYTHON_EXE%" -m PyInstaller --noconfirm --clean CS2RGBSync.spec
if errorlevel 1 exit /b 1

echo [4/5] Compilando versao onefile em release\CS2RGBSync.exe...
if not exist "release" mkdir release
"%PYTHON_EXE%" -m PyInstaller --noconfirm --clean --distpath release CS2RGBSync_onefile.spec
if errorlevel 1 exit /b 1

echo [5/5] Compilando instalador Inno Setup...
set "ISCC_EXE=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "%ISCC_EXE%" goto :run_iscc
set "ISCC_EXE=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ISCC_EXE%" goto :run_iscc
echo [ERRO] Inno Setup 6 ISCC.exe nao encontrado.
exit /b 1

:run_iscc
"%ISCC_EXE%" installer\CS2RGBSync.iss
if errorlevel 1 exit /b 1

echo.
echo [CONCLUIDO] Artefatos gerados:
echo   - dist\CS2RGBSync\CS2RGBSync.exe (onedir)
echo   - release\CS2RGBSync.exe (onefile)
echo   - dist\CS2RGBSync_Setup.exe (instalador)
echo   - MANUAL_INSTALACAO.pdf
exit /b 0
