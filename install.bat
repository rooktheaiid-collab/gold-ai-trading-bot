@echo off
REM ============================================================
REM  Gold AI Trading Bot - Installer (Windows)
REM  Klik 2x atau jalankan:  install.bat
REM ============================================================
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Gold AI Trading Bot - Installer (Windows)
echo ============================================================

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python tidak ditemukan. Install Python 3.10+ dari python.org
  echo         dan centang "Add Python to PATH".
  pause & exit /b 1
)

for /f "tokens=2" %%v in ('python --version') do echo [OK] Python %%v

if not exist venv (
  echo [..] Membuat virtualenv venv ...
  python -m venv venv
)
call venv\Scripts\activate.bat
echo [OK] venv aktif.

echo [..] Upgrade pip + build tools ...
REM setuptools+wheel WAJIB: pandas-ta dibangun dari sdist (butuh setuptools.build_meta)
python -m pip install --upgrade pip setuptools wheel >nul
echo [..] Install dependencies (1-3 menit) ...
pip install -r requirements.txt
if errorlevel 1 ( echo [ERROR] Install dependency gagal. & pause & exit /b 1 )

if not exist .env (
  copy .env.example .env >nul
  echo [OK] Dibuat .env dari template. WAJIB isi API key kamu.
) else (
  echo [INFO] .env sudah ada - tidak ditimpa.
)

python -c "import config, data_fetcher, technical_analysis, llm_brain, trade_engine, main; print('[OK] semua modul inti import OK')"

echo.
echo ============================================================
echo   Instalasi selesai!
echo   Langkah berikutnya:
echo     1) venv\Scripts\activate.bat
echo     2) python setup.py --guided   (wizard konfigurasi terpandu)
echo     3) python main.py             (jalankan bot)
echo   Default PAPER_TRADING=True (simulasi, AMAN).
echo ============================================================
pause
