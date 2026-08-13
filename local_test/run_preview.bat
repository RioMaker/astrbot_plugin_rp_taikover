@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
python local_test\preview.py
if errorlevel 1 (
  echo.
  echo 预览生成失败，请确认已安装 requirements.txt 中的依赖。
) else (
  echo.
  echo 图片位于 local_test\output 文件夹。
)
pause
