"""Orchestre l'installation d'un jeu : téléchargement de l'installateur via
le store, création du préfixe Proton, exécution silencieuse de l'installateur,
puis enregistrement dans la bibliothèque locale.

Ne sait pas trouver tout seul l'exécutable du jeu après installation (ça
dépend du jeu) : l'appelant doit fournir le chemin relatif de l'exe une fois
l'installation terminée (cf. --exe dans le CLI).
"""
from __future__ import annotations

import re
import shutil
import urllib.request
from pathlib import Path

import library
import proton
from config import DOWNLOADS_DIR, INSTALL_DIR
from stores.base import StoreClient


def _resolve_proton_version(proton_version: str) -> tuple[str, Path]:
    """Résout un nom de version Proton, ou "auto" pour utiliser/télécharger
    automatiquement la dernière GE-Proton disponible."""
    if proton_version == "auto":
        proton_version = proton.ensure_proton_available()

    versions = proton.find_proton_versions()
    proton_bin = versions.get(proton_version)
    if not proton_bin:
        raise RuntimeError(f"Version Proton introuvable : {proton_version}")
    return proton_version, proton_bin


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
    fullscreen: bool = True,
) -> library.InstalledGame:
    proton_version, proton_bin = _resolve_proton_version(proton_version)

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

    version = ""
    get_latest_version = getattr(store, "get_latest_version", None)
    if get_latest_version:
        try:
            version = get_latest_version(game_id)
        except Exception:
            version = ""

    exe_path = install_dir / exe_relative_path
    game = library.InstalledGame(
        store=store.store_id,
        id=game_id,
        title=game_title,
        proton_version=proton_version,
        prefix=str(prefix),
        exe_path=str(exe_path),
        fullscreen=fullscreen,
        version=version,
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

    proton.run_game(
        proton_bin, Path(game.prefix), Path(game.exe_path),
        game.launch_args, game.env_vars, fullscreen=game.fullscreen,
    )


def update_game_settings(
    store_id: str,
    game_id: str,
    proton_version: str | None = None,
    launch_args: list[str] | None = None,
    env_vars: dict[str, str] | None = None,
    fullscreen: bool | None = None,
) -> library.InstalledGame:
    """Modifie la config (Proton, arguments, variables d'env, plein écran)
    d'un jeu déjà installé, sans le réinstaller."""
    game = library.get_game(store_id, game_id)
    if not game:
        raise RuntimeError(f"Jeu non installé : {store_id}:{game_id}")

    if proton_version is not None:
        if proton_version not in proton.find_proton_versions():
            raise RuntimeError(f"Version Proton introuvable : {proton_version}")
        game.proton_version = proton_version
    if launch_args is not None:
        game.launch_args = launch_args
    if env_vars is not None:
        game.env_vars = env_vars
    if fullscreen is not None:
        game.fullscreen = fullscreen

    library.add_game(game)
    return game


def uninstall_game(store_id: str, game_id: str, delete_prefix: bool = True, delete_files: bool = True) -> None:
    game = library.get_game(store_id, game_id)
    if not game:
        raise RuntimeError(f"Jeu non installé : {store_id}:{game_id}")

    if delete_prefix:
        prefix = Path(game.prefix)
        if prefix.exists():
            shutil.rmtree(prefix)

    if delete_files:
        install_dir = Path(game.exe_path).parent
        if install_dir.exists() and install_dir.is_relative_to(INSTALL_DIR):
            shutil.rmtree(install_dir)

    library.remove_game(store_id, game_id)


# ── Mises à jour ─────────────────────────────────────────────────────────

def check_for_update(store: StoreClient, game: library.InstalledGame) -> str | None:
    """Retourne la nouvelle version disponible si une mise à jour existe
    pour ce jeu, sinon None. Uniquement supporté par les stores qui
    exposent get_latest_version() (GOG pour l'instant)."""
    get_latest_version = getattr(store, "get_latest_version", None)
    if not get_latest_version:
        return None
    try:
        latest = get_latest_version(game.id)
    except Exception:
        return None
    if latest and latest != game.version:
        return latest
    return None


def check_all_updates(stores: dict[str, StoreClient]) -> list[tuple[library.InstalledGame, str]]:
    """Vérifie les mises à jour disponibles pour tous les jeux installés
    dont le store est connu (ignore silencieusement les stores absents ou
    non authentifiés, et 'custom' qui n'a pas de notion de mise à jour)."""
    updates = []
    for game in library.list_games():
        store = stores.get(game.store)
        if not store or not store.is_authenticated():
            continue
        latest = check_for_update(store, game)
        if latest:
            updates.append((game, latest))
    return updates


def update_game(store: StoreClient, game: library.InstalledGame) -> library.InstalledGame:
    """Réinstalle le jeu par-dessus l'existant (même préfixe, même config)
    pour appliquer la dernière version disponible côté store."""
    exe_relative_path = str(Path(game.exe_path).relative_to(INSTALL_DIR / library.key_for(game.store, game.id)))
    return install_game(
        store=store,
        game_id=game.id,
        game_title=game.title,
        proton_version=game.proton_version,
        exe_relative_path=exe_relative_path,
        fullscreen=game.fullscreen,
    )


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "jeu"


def add_custom_game(
    title: str,
    exe_path: str,
    proton_version: str,
    prefix_path: str | None = None,
    launch_args: list[str] | None = None,
    env_vars: dict[str, str] | None = None,
    game_id: str | None = None,
    fullscreen: bool = True,
) -> library.InstalledGame:
    """Enregistre un jeu déjà installé (hors store, ou déjà téléchargé
    manuellement) avec sa propre configuration Proton/Wine complète :
    version Proton, préfixe (nouveau ou existant), arguments de lancement,
    variables d'environnement (ex: DXVK_HUD=1, PROTON_LOG=1)."""
    proton_version, proton_bin = _resolve_proton_version(proton_version)

    exe = Path(exe_path).expanduser().resolve()
    if not exe.is_file():
        raise RuntimeError(f"Fichier introuvable : {exe}")

    game_id = game_id or _slugify(title)
    game_key = library.key_for("custom", game_id)
    prefix = Path(prefix_path).expanduser().resolve() if prefix_path else proton.prefix_path_for(game_key)

    if not prefix.exists():
        proton.init_prefix(proton_bin, prefix)

    game = library.InstalledGame(
        store="custom",
        id=game_id,
        title=title,
        proton_version=proton_version,
        prefix=str(prefix),
        exe_path=str(exe),
        launch_args=launch_args or [],
        env_vars=env_vars or {},
        fullscreen=fullscreen,
    )
    library.add_game(game)
    return game
