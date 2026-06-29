#!/bin/bash
# Build Linux de Sakura Launcher : binaire "One Directory" + AppImage.
# À lancer SUR LINUX, depuis ce dossier.
set -e

pip3 install -r requirements.txt

pyinstaller --noconfirm --onedir \
    --name "SakuraLauncher" \
    --icon "icon.png" \
    --add-data "icon.png:." \
    --distpath "dist/linux" \
    sakura.py

echo "Build binaire terminé : dist/linux/SakuraLauncher/"

# Génère un AppImage si appimagetool est dispo
# (télécharger : https://github.com/AppImage/AppImageKit/releases)
if command -v appimagetool >/dev/null 2>&1; then
    APPDIR="dist/linux/SakuraLauncher.AppDir"
    rm -rf "$APPDIR"
    mkdir -p "$APPDIR/usr/bin"
    cp -r dist/linux/SakuraLauncher/* "$APPDIR/usr/bin/"

    cat > "$APPDIR/SakuraLauncher.desktop" <<EOF
[Desktop Entry]
Name=Sakura Launcher
Exec=SakuraLauncher
Icon=sakura
Type=Application
Categories=Game;
EOF

    cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "${0}")")"
exec "${HERE}/usr/bin/SakuraLauncher" "$@"
EOF
    chmod +x "$APPDIR/AppRun"

    cp "icon.png" "$APPDIR/sakura.png"

    appimagetool "$APPDIR" "dist/linux/SakuraLauncher-x86_64.AppImage"
    echo "AppImage terminé : dist/linux/SakuraLauncher-x86_64.AppImage"
else
    echo "appimagetool non trouvé — binaire seul généré, pas d'AppImage"
    echo "Télécharge-le ici : https://github.com/AppImage/AppImageKit/releases"
fi
