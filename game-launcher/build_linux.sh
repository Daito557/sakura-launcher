#!/bin/bash
# Build Linux de Sakura Game Launcher : binaire GUI (onedir) + CLI (onefile).
# À lancer SUR LINUX, depuis ce dossier.
set -e

pip3 install -r requirements.txt pyinstaller

HIDDEN_IMPORTS=(
    --hidden-import stores.gog
    --hidden-import stores.steam
    --hidden-import stores.epic
    --hidden-import stores.ea
    --hidden-import stores.ubisoft
    --hidden-import stores.battlenet
)

pyinstaller --noconfirm --onedir \
    --name "SakuraGameLauncher" \
    --paths . \
    "${HIDDEN_IMPORTS[@]}" \
    --distpath "dist/linux" \
    ui/app.py

pyinstaller --noconfirm --onefile \
    --name "sakura-game-launcher-cli" \
    --paths . \
    "${HIDDEN_IMPORTS[@]}" \
    --distpath "dist/linux" \
    cli.py

echo "Build terminé :"
echo "  GUI : dist/linux/SakuraGameLauncher/SakuraGameLauncher"
echo "  CLI : dist/linux/sakura-game-launcher-cli"
