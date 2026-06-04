@echo off
git add -A
git commit -m "Refactor app.py with error handling, remove temporary files" -m "- Updated create-job route with try/except and logging to fix 500 error" -m "- Added traceback import and improved supabase_request error handling" -m "- Removed 100+ temporary debug files" -m "- Added cleanup.py utility"
