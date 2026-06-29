@echo off
REM Build Windows de Sakura Launcher : "One Directory" + sans UPX, pour
REM réduire les faux positifs Windows Defender (voir discussion précédente).
REM A lancer depuis ce dossier, avec sakura.py présent à côté ou copié ici.

pip install -r requirements.txt
pyinstaller --noconfirm --onedir --windowed --noupx ^
    --name "SakuraLauncher" ^
    --distpath "dist\windows" ^
    sakura.py

echo.
echo Build termine : dist\windows\SakuraLauncher\
