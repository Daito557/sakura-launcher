@echo off
REM Build Windows de Sakura Launcher : "One File" — un seul .exe autonome.
REM Note : --onefile augmente le risque de faux positif Windows Defender
REM (vs --onedir) car l'exe se decompresse en memoire au lancement, ce qui
REM ressemble au comportement de packers malveillants. Choix assume.
REM A lancer depuis ce dossier, avec sakura.py present a cote ou copie ici.

pip install -r requirements.txt
pyinstaller --noconfirm --onefile --windowed --noupx ^
    --name "SakuraLauncher" ^
    --distpath "dist\windows" ^
    sakura.py

echo.
echo Build termine : dist\windows\SakuraLauncher.exe
