@echo off
:: Run Never Sleep with Administrator privileges
:: This gives full protection against shutdown/restart

echo Requesting Administrator privileges...
powershell -Command "Start-Process cmd -ArgumentList '/c cd /d \"%~dp0\" && python fake_session.py %*' -Verb RunAs"
