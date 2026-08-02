"""Orchestre l'installation d'un jeu : téléchargement de l'installateur via
le store, création du préfixe Proton, exécution silencieuse de l'installateur,
puis enregistrement dans la bibliothèque locale.

Ne sait pas trouver tout seul l'exécutable du jeu après installation (ça
dépend du jeu) : l'appelant doit fournir le chemin relatif de l'exe une fois
l'installation terminée (cf. --exe dans le CLI).
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

import library
import proton
from config import DOWNLOADS_DIR, INSTALL_DIR
from stores.base import StoreClient


def download_installer(store: StoreClient, game_id: str) -> Path:
    info = store.get_download_info(game_id)
    dest = DOWNLOADS_DIR / info.filename
    req = urllib.request.Request(info.url, headers=info.headers or {})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    return dest


def install_game(
    store: StoreClient,
    game_id: str,
    game_title: str,
    proton_version: str,
    exe_relative_path: str,
    silent: bool = True,
) -> library.InstalledGame:
    versions = proton.find_proton_versions()
    proton_bin = versions.get(proton_version)
    if not proton_bin:
        raise RuntimeError(f"Version Proton introuvable : {proton_version}")

    game_key = library.key_for(store.store_id, game_id)
    prefix = proton.prefix_path_for(game_key)
    proton.init_prefix(proton_bin, prefix)

    installer_path = download_installer(store, game_id)

    install_dir = INSTALL_DIR / game_key
    install_dir.mkdir(parents=True, exist_ok=True)
    # Convention "/S" (NSIS) ou "/silent" (InnoSetup) : varie par jeu, à
    # ajuster si l'installateur ne supporte pas le mode silencieux standard.
    silent_args = ["/S"] if silent else []
    proton.run_installer(proton_bin, prefix, installer_path, silent_args)

    exe_path = install_dir / exe_relative_path
    game = library.InstalledGame(
        store=store.store_id,
        id=game_id,
        title=game_title,
        proton_version=proton_version,
        prefix=str(prefix),
        exe_path=str(exe_path),
    )
    library.add_game(game)
    return game


def launch_game(store_id: str, game_id: str) -> None:
    game = library.get_game(store_id, game_id)
    if not game:
        raise RuntimeError(f"Jeu non installé : {store_id}:{game_id}")

    versions = proton.find_proton_versions()
    proton_bin = versions.get(game.proton_version)
    if not proton_bin:
        raise RuntimeError(f"Version Proton introuvable : {game.proton_version}")

    proton.run_game(proton_bin, Path(game.prefix), Path(game.exe_path))
