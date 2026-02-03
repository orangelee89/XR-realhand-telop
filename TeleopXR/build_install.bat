@echo off
set JAVA_HOME=C:\Program Files\Android\Android Studio\jbr
set PATH=%JAVA_HOME%\bin;C:\Users\Orang\AppData\Local\Android\Sdk\platform-tools;%PATH%
cd /d C:\Users\Orang\teleop_ws\src\TeleopXR
call gradlew.bat assembleDebug
if %ERRORLEVEL% EQU 0 (
    echo Build successful, installing...
    adb install -r app\build\outputs\apk\debug\app-debug.apk
) else (
    echo Build failed!
)
