@echo off
setlocal
set "APP_ROOT=%~dp0"
if exist "%APP_ROOT%runtime\python.exe" goto portable
set "BUNDLED_PY=C:\Users\Владимир\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%BUNDLED_PY%" (
  echo Не найден Python runtime. Используйте сборку portable или установите Python 3.12.
  pause
  exit /b 1
)
set "PYTHONPATH=%APP_ROOT%05_src"
"%BUNDLED_PY%" "%APP_ROOT%05_src\main.py"
goto done

:portable
for %%D in (K L M N P Q R S T U V W X Y Z) do if not exist %%D:\ goto use_drive_%%D
echo Нет свободной буквы диска для безопасного запуска из пути с кириллицей.
pause
exit /b 1
:use_drive_K
set "CP_DRIVE=K:"
goto mapped
:use_drive_L
set "CP_DRIVE=L:"
goto mapped
:use_drive_M
set "CP_DRIVE=M:"
goto mapped
:use_drive_N
set "CP_DRIVE=N:"
goto mapped
:use_drive_P
set "CP_DRIVE=P:"
goto mapped
:use_drive_Q
set "CP_DRIVE=Q:"
goto mapped
:use_drive_R
set "CP_DRIVE=R:"
goto mapped
:use_drive_S
set "CP_DRIVE=S:"
goto mapped
:use_drive_T
set "CP_DRIVE=T:"
goto mapped
:use_drive_U
set "CP_DRIVE=U:"
goto mapped
:use_drive_V
set "CP_DRIVE=V:"
goto mapped
:use_drive_W
set "CP_DRIVE=W:"
goto mapped
:use_drive_X
set "CP_DRIVE=X:"
goto mapped
:use_drive_Y
set "CP_DRIVE=Y:"
goto mapped
:use_drive_Z
set "CP_DRIVE=Z:"
:mapped
subst %CP_DRIVE% "%APP_ROOT%"
set "PYTHONPATH=%CP_DRIVE%\app\05_src"
"%CP_DRIVE%\runtime\python.exe" "%CP_DRIVE%\app\05_src\main.py"
subst %CP_DRIVE% /d
:done
endlocal
