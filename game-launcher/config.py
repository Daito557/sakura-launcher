"""Chemins et constantes partagés par le launcher."""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "sakura-game-launcher"

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME

TOKENS_DIR = CONFIG_DIR / "tokens"          # un fichier json de tokens par store
LIBRARY_FILE = DATA_DIR / "library.json"    # jeux installés, tous stores confondus
INSTALL_DIR = DATA_DIR / "games"            # où les jeux sont installés par défaut
PREFIXES_DIR = DATA_DIR / "prefixes"        # préfixes Wine, un par jeu
DOWNLOADS_DIR = DATA_DIR / "downloads"      # installateurs téléchargés (temporaire)

for d in (CONFIG_DIR, TOKENS_DIR, DATA_DIR, INSTALL_DIR, PREFIXES_DIR, DOWNLOADS_DIR):
    d.mkdir(parents=True, exist_ok=True)
