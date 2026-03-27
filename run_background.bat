@echo off
:: Run Never Sleep in background (hidden window)
:: To stop: open Task Manager and end "python.exe" process

echo Starting Never Sleep in background...
start /min "" pythonw "%~dp0fake_session.py" --background --log
echo Never Sleep is running in background.
echo Check never_sleep.log for activity.
echo To stop: open Task Manager ^> End "pythonw.exe"
timeout /t 3
