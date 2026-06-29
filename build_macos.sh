#!/bin/bash
# Build macOS de Sakura Launcher (.app + .dmg).
# À lancer SUR UN MAC, depuis ce dossier.
set -e

pip3 install -r requirements.txt

pyinstaller --noconfirm --windowed \
    --name "SakuraLauncher" \
    --icon "icon.icns" \
    --add-data "icon.png:." \
    --distpath "dist/macos" \
    sakura.py

echo "Build .app terminé : dist/macos/SakuraLauncher.app"

# Génère un .dmg installable (nécessite create-dmg : brew install create-dmg)
if command -v create-dmg >/dev/null 2>&1; then
    create-dmg \
        --volname "Sakura Launcher" \
        --window-size 500 300 \
        --icon-size 100 \
        --app-drop-link 380 120 \
        "dist/macos/SakuraLauncher.dmg" \
        "dist/macos/SakuraLauncher.app"
    echo "Build .dmg terminé : dist/macos/SakuraLauncher.dmg"
else
    echo "create-dmg non installé (brew install create-dmg) — .app généré, pas de .dmg"
fi
