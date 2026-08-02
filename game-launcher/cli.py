#!/usr/bin/env python3
"""CLI du launcher multi-store (GOG fonctionnel, autres stores en préparation).

Cette interface texte permet de valider toute la chaîne (auth, bibliothèque
en ligne, téléchargement, préfixe Proton, installation, lancement) avant de
construire l'interface graphique customtkinter par-dessus.
"""
from __future__ import annotations

import argparse
import sys

import install_manager
import library
import proton
from stores import make_all_stores


def cmd_stores(_args) -> None:
    for store in make_all_stores().values():
        status = "connecté" if store.is_authenticated() else "non connecté"
        print(f"- {store.store_id:12s} {store.display_name:20s} [{status}]")


def cmd_login(args) -> None:
    stores = make_all_stores()
    store = stores.get(args.store)
    if not store:
        print(f"Store inconnu : {args.store}", file=sys.stderr)
        sys.exit(1)
    store.login()


def cmd_library(args) -> None:
    stores = make_all_stores()
    store = stores.get(args.store)
    if not store:
        print(f"Store inconnu : {args.store}", file=sys.stderr)
        sys.exit(1)
    for game in store.list_owned_games():
        print(f"{game.id:12s} {game.title}")


def cmd_installed(_args) -> None:
    games = library.list_games()
    if not games:
        print("Aucun jeu installé.")
        return
    for g in games:
        print(f"- [{g.store}] {g.title}  (proton: {g.proton_version})")


def cmd_proton_versions(_args) -> None:
    versions = proton.find_proton_versions()
    if not versions:
        print("Aucune version Proton détectée. Utilisez 'install-ge'.")
        return
    for name in sorted(versions):
        print(f"- {name}")


def cmd_install_ge(args) -> None:
    tag = proton.install_latest_ge(force=args.force)
    print(f"GE-Proton {tag} prêt.")


def cmd_install_game(args) -> None:
    stores = make_all_stores()
    store = stores.get(args.store)
    if not store:
        print(f"Store inconnu : {args.store}", file=sys.stderr)
        sys.exit(1)

    game = install_manager.install_game(
        store=store,
        game_id=args.game_id,
        game_title=args.title,
        proton_version=args.proton,
        exe_relative_path=args.exe,
        silent=not args.no_silent,
    )
    print(f"'{game.title}' installé. Lancez-le avec : run {args.store} {args.game_id}")


def cmd_run(args) -> None:
    if args.store == "steam":
        stores = make_all_stores()
        stores["steam"].launch_game(args.game_id)
        return
    install_manager.launch_game(args.store, args.game_id)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cli.py", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("stores", help="Lister les stores et leur état de connexion").set_defaults(func=cmd_stores)

    p_login = sub.add_parser("login", help="Se connecter à un store")
    p_login.add_argument("store", help="ex: gog")
    p_login.set_defaults(func=cmd_login)

    p_lib = sub.add_parser("library", help="Lister les jeux possédés sur un store")
    p_lib.add_argument("store")
    p_lib.set_defaults(func=cmd_library)

    sub.add_parser("installed", help="Lister les jeux installés localement").set_defaults(func=cmd_installed)

    sub.add_parser("proton-versions", help="Lister les versions Proton détectées").set_defaults(func=cmd_proton_versions)

    p_ge = sub.add_parser("install-ge", help="Télécharger la dernière GE-Proton")
    p_ge.add_argument("--force", action="store_true")
    p_ge.set_defaults(func=cmd_install_ge)

    p_install = sub.add_parser("install-game", help="Installer un jeu depuis un store")
    p_install.add_argument("store")
    p_install.add_argument("game_id")
    p_install.add_argument("--title", required=True)
    p_install.add_argument("--proton", required=True)
    p_install.add_argument("--exe", required=True, help="Chemin relatif de l'exe une fois installé")
    p_install.add_argument("--no-silent", action="store_true", help="Ne pas passer /S à l'installateur")
    p_install.set_defaults(func=cmd_install_game)

    p_run = sub.add_parser("run", help="Lancer un jeu installé")
    p_run.add_argument("store")
    p_run.add_argument("game_id")
    p_run.set_defaults(func=cmd_run)

    return p


def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
