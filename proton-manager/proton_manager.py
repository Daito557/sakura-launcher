#!/usr/bin/env python3
"""Proton Manager — outil CLI pour gérer des versions de Proton/GE-Proton,
créer des préfixes Wine par jeu, et lancer des exécutables Windows sous Linux.

Indépendant de Sakura Launcher (sakura.py) : ce module ne l'importe pas et
n'en dépend pas.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

APP_NAME = "proton-manager"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.json"
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME
VERSIONS_DIR = DATA_DIR / "versions"          # GE-Proton téléchargés par cet outil
PREFIXES_DIR = DATA_DIR / "prefixes"           # préfixes Wine, un par jeu

STEAM_COMPAT_TOOLS_DIRS = [
    Path.home() / ".steam" / "steam" / "compatibilitytools.d",
    Path.home() / ".local" / "share" / "Steam" / "compatibilitytools.d",
]
STEAM_COMMON_DIRS = [
    Path.home() / ".steam" / "steam" / "steamapps" / "common",
    Path.home() / ".local" / "share" / "Steam" / "steamapps" / "common",
]

GE_PROTON_API = "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases/latest"


# ── Config ─────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text("utf-8"))
        except Exception:
            pass
    return {"games": {}}


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")


# ── Détection des versions Proton disponibles ─────────────────────────────

def find_proton_versions() -> dict[str, Path]:
    """Retourne {nom_version: chemin_du_binaire_proton}."""
    found: dict[str, Path] = {}

    for d in STEAM_COMPAT_TOOLS_DIRS + [VERSIONS_DIR]:
        if not d.is_dir():
            continue
        for entry in d.iterdir():
            proton_bin = entry / "proton"
            if entry.is_dir() and proton_bin.is_file():
                found[entry.name] = proton_bin

    for d in STEAM_COMMON_DIRS:
        if not d.is_dir():
            continue
        for entry in d.iterdir():
            if entry.is_dir() and entry.name.lower().startswith("proton"):
                proton_bin = entry / "proton"
                if proton_bin.is_file():
                    found.setdefault(entry.name, proton_bin)

    return found


def cmd_list_versions(_args) -> None:
    versions = find_proton_versions()
    if not versions:
        print("Aucune version de Proton trouvée.")
        print("Utilisez 'proton_manager.py install-ge' pour télécharger la dernière GE-Proton.")
        return
    print("Versions Proton disponibles :")
    for name, path in sorted(versions.items()):
        print(f"  - {name}  ({path})")


# ── Installation de GE-Proton ──────────────────────────────────────────────

def cmd_install_ge(args) -> None:
    print("Récupération des infos de la dernière release GE-Proton…")
    req = urllib.request.Request(GE_PROTON_API, headers={"User-Agent": APP_NAME})
    with urllib.request.urlopen(req, timeout=30) as resp:
        release = json.loads(resp.read().decode("utf-8"))

    tag = release.get("tag_name", "unknown")
    asset = next(
        (a for a in release.get("assets", []) if a["name"].endswith(".tar.gz")),
        None,
    )
    if not asset:
        print("Impossible de trouver l'archive .tar.gz dans la release.", file=sys.stderr)
        sys.exit(1)

    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    dest_dir = VERSIONS_DIR / tag
    if dest_dir.exists() and not args.force:
        print(f"{tag} est déjà installé (utilisez --force pour réinstaller).")
        return

    archive_path = VERSIONS_DIR / asset["name"]
    print(f"Téléchargement de {asset['name']} ({asset['size'] / 1e6:.1f} Mo)…")
    urllib.request.urlretrieve(asset["browser_download_url"], archive_path)

    print("Extraction…")
    with tarfile.open(archive_path) as tar:
        tar.extractall(VERSIONS_DIR)
    archive_path.unlink()

    print(f"GE-Proton {tag} installé dans {dest_dir}")


# ── Gestion des préfixes ────────────────────────────────────────────────────

def prefix_path_for(game: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in game)
    return PREFIXES_DIR / safe


def env_for_prefix(proton_bin: Path, prefix: Path) -> dict:
    env = os.environ.copy()
    env["STEAM_COMPAT_DATA_PATH"] = str(prefix)
    # requis par Proton même sans Steam installé ; un dossier vide suffit
    compat_client = env.get("STEAM_COMPAT_CLIENT_INSTALL_PATH") or str(DATA_DIR / "compat-client")
    Path(compat_client).mkdir(parents=True, exist_ok=True)
    env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = compat_client
    return env


def cmd_create_prefix(args) -> None:
    versions = find_proton_versions()
    proton_bin = versions.get(args.proton)
    if not proton_bin:
        print(f"Version Proton inconnue : {args.proton}", file=sys.stderr)
        print("Voir 'list-versions' pour les versions disponibles.", file=sys.stderr)
        sys.exit(1)

    prefix = prefix_path_for(args.game)
    if prefix.exists() and not args.force:
        print(f"Le préfixe pour '{args.game}' existe déjà ({prefix}).")
        return
    prefix.mkdir(parents=True, exist_ok=True)

    env = env_for_prefix(proton_bin, prefix)
    print(f"Initialisation du préfixe Wine pour '{args.game}' avec {args.proton}…")
    subprocess.run([str(proton_bin), "run", "wineboot", "--init"], env=env, check=True)

    cfg = load_config()
    cfg["games"].setdefault(args.game, {})
    cfg["games"][args.game]["proton"] = args.proton
    cfg["games"][args.game]["prefix"] = str(prefix)
    save_config(cfg)
    print(f"Préfixe créé : {prefix}")


def cmd_delete_prefix(args) -> None:
    cfg = load_config()
    prefix = Path(cfg["games"].get(args.game, {}).get("prefix", "")) or prefix_path_for(args.game)
    if not prefix.exists():
        print(f"Aucun préfixe trouvé pour '{args.game}'.")
        return
    if not args.yes:
        confirm = input(f"Supprimer définitivement {prefix} ? [y/N] ").strip().lower()
        if confirm != "y":
            print("Annulé.")
            return
    shutil.rmtree(prefix)
    cfg["games"].pop(args.game, None)
    save_config(cfg)
    print(f"Préfixe supprimé pour '{args.game}'.")


# ── Association jeu -> exécutable / version ────────────────────────────────

def cmd_add_game(args) -> None:
    exe = Path(args.exe).expanduser().resolve()
    if not exe.is_file():
        print(f"Fichier introuvable : {exe}", file=sys.stderr)
        sys.exit(1)

    cfg = load_config()
    entry = cfg["games"].setdefault(args.game, {})
    entry["exe"] = str(exe)
    if args.proton:
        entry["proton"] = args.proton
    entry.setdefault("prefix", str(prefix_path_for(args.game)))
    save_config(cfg)
    print(f"Jeu '{args.game}' enregistré -> {exe}")


def cmd_list_games(_args) -> None:
    cfg = load_config()
    if not cfg["games"]:
        print("Aucun jeu configuré.")
        return
    for name, entry in cfg["games"].items():
        print(f"- {name}")
        print(f"    exe:    {entry.get('exe', '?')}")
        print(f"    proton: {entry.get('proton', '?')}")
        print(f"    prefix: {entry.get('prefix', '?')}")


# ── Lancement ────────────────────────────────────────────────────────────

def cmd_run(args) -> None:
    cfg = load_config()
    entry = cfg["games"].get(args.game)
    if not entry or "exe" not in entry:
        print(f"Jeu inconnu ou sans exécutable configuré : {args.game}", file=sys.stderr)
        print("Utilisez 'add-game' d'abord.", file=sys.stderr)
        sys.exit(1)

    proton_name = args.proton or entry.get("proton")
    if not proton_name:
        print("Aucune version Proton spécifiée (ni --proton, ni dans la config).", file=sys.stderr)
        sys.exit(1)

    versions = find_proton_versions()
    proton_bin = versions.get(proton_name)
    if not proton_bin:
        print(f"Version Proton introuvable : {proton_name}", file=sys.stderr)
        sys.exit(1)

    prefix = Path(entry.get("prefix") or prefix_path_for(args.game))
    prefix.mkdir(parents=True, exist_ok=True)

    env = env_for_prefix(proton_bin, prefix)
    exe = entry["exe"]
    print(f"Lancement de '{args.game}' via {proton_name}…")
    subprocess.run([str(proton_bin), "waitforexitandrun", exe, *args.extra], env=env)


def cmd_winetricks(args) -> None:
    cfg = load_config()
    entry = cfg["games"].get(args.game)
    if not entry:
        print(f"Jeu inconnu : {args.game}", file=sys.stderr)
        sys.exit(1)
    if not shutil.which("winetricks"):
        print("winetricks n'est pas installé sur ce système.", file=sys.stderr)
        sys.exit(1)

    prefix = Path(entry.get("prefix") or prefix_path_for(args.game))
    env = os.environ.copy()
    env["WINEPREFIX"] = str(prefix)
    subprocess.run(["winetricks", *args.verbs], env=env, check=True)


# ── CLI ──────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="proton_manager.py", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("list-versions", help="Lister les versions Proton détectées").set_defaults(func=cmd_list_versions)

    p_install = sub.add_parser("install-ge", help="Télécharger et installer la dernière GE-Proton")
    p_install.add_argument("--force", action="store_true", help="Réinstaller même si déjà présent")
    p_install.set_defaults(func=cmd_install_ge)

    p_prefix = sub.add_parser("create-prefix", help="Créer un préfixe Wine pour un jeu")
    p_prefix.add_argument("game", help="Nom du jeu")
    p_prefix.add_argument("--proton", required=True, help="Version Proton à utiliser")
    p_prefix.add_argument("--force", action="store_true", help="Recréer même si le préfixe existe")
    p_prefix.set_defaults(func=cmd_create_prefix)

    p_delprefix = sub.add_parser("delete-prefix", help="Supprimer le préfixe d'un jeu")
    p_delprefix.add_argument("game")
    p_delprefix.add_argument("-y", "--yes", action="store_true", help="Ne pas demander de confirmation")
    p_delprefix.set_defaults(func=cmd_delete_prefix)

    p_add = sub.add_parser("add-game", help="Associer un exécutable Windows à un nom de jeu")
    p_add.add_argument("game")
    p_add.add_argument("exe", help="Chemin vers le .exe")
    p_add.add_argument("--proton", help="Version Proton par défaut pour ce jeu")
    p_add.set_defaults(func=cmd_add_game)

    sub.add_parser("list-games", help="Lister les jeux configurés").set_defaults(func=cmd_list_games)

    p_run = sub.add_parser("run", help="Lancer un jeu configuré")
    p_run.add_argument("game")
    p_run.add_argument("--proton", help="Surcharger la version Proton du jeu")
    p_run.add_argument("extra", nargs="*", help="Arguments supplémentaires passés au jeu")
    p_run.set_defaults(func=cmd_run)

    p_wt = sub.add_parser("winetricks", help="Exécuter winetricks dans le préfixe d'un jeu")
    p_wt.add_argument("game")
    p_wt.add_argument("verbs", nargs="+", help="Verbes winetricks, ex: corefonts vcrun2019")
    p_wt.set_defaults(func=cmd_winetricks)

    return p


def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
