@echo off
cd /d %~dp0
if exist instance\loja_flex_final.db del /f /q instance\loja_flex_final.db
if exist app\static\uploads\qr rmdir /s /q app\static\uploads\qr
mkdir app\static\uploads\qr
