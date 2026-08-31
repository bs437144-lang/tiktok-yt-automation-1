@echo off
title YouTube Automation Status App
echo ===================================================
echo   YOUTUBE AUTOMATION - LIVE CHANNEL STATUS APP
echo ===================================================
echo.
echo Updating real-time live channel stats...
python src\status_tracker.py
echo.
echo Launching Interactive Live Dashboard...
start "" "public\index.html"
exit
