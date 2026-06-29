# Build multi-OS de Sakura Launcher

## Option recommandée : GitHub Actions (pas besoin de posséder un Mac/Linux)

1. Pousse ce projet (avec `sakura.py` à la racine et ce dossier `output/`) sur un repo GitHub.
2. Le fichier `.github/workflows/build.yml` doit être à la racine du repo (déplace-le de `output/.github/` vers `.github/` à la racine si besoin — GitHub Actions ne lit que `.github/workflows/` à la racine).
3. Crée un tag de version et pousse-le :
   ```
   git tag v2.1.0
   git push origin v2.1.0
   ```
4. Va dans l'onglet **Actions** du repo GitHub : 3 builds tournent en parallèle (Windows, macOS, Linux), chacun sur une vraie machine de cet OS.
5. Une fois terminé, télécharge les 3 artefacts (`SakuraLauncher-windows`, `SakuraLauncher-macos`, `SakuraLauncher-linux`) directement depuis la page du run.

Tu peux aussi déclencher un build manuellement sans tag, via "Run workflow" dans l'onglet Actions (`workflow_dispatch`).

## Option locale (si tu as accès aux machines)

- **Windows** (ce que tu fais déjà) : `build_windows.bat`
- **macOS** : copie ce dossier sur un Mac, lance `bash build_macos.sh`
- **Linux** : copie ce dossier sur une machine Linux, lance `bash build_linux.sh`

Chaque script installe ses dépendances (`requirements.txt`) puis lance PyInstaller avec les bons réglages pour cet OS.

## Notes

- Le `.dmg` macOS nécessite `create-dmg` (`brew install create-dmg`), sinon seul le `.app` est généré.
- L'AppImage Linux nécessite `appimagetool` téléchargé à part, sinon seul le binaire `.AppDir` est généré.
- `windnd` (glisser-déposer de mods) ne s'installe que sur Windows (`requirements.txt` le gère via le marqueur `sys_platform == "win32"`) — sur Mac/Linux, le launcher continue de fonctionner sans cette fonctionnalité (déjà géré dans le code).
