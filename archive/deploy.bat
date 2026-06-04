@echo off
echo [1/2] Pulling latest changes from GitHub...
git pull origin main

echo.
echo [2/2] Reloading PythonAnywhere webapp...
python reload_pa.py

echo.
echo Done!
