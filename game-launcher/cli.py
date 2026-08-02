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
        fs = "plein écran" if g.fullscreen else "fenêtré"
        print(f"- [{g.store}] {g.title}  (proton: {g.proton_version}, {fs})")


def cmd_configure_game(args) -> None:
    env_vars = None
    if args.env is not None:
        env_vars = {}
        for item in args.env:
            if "=" not in item:
                print(f"Variable d'environnement invalide (attendu KEY=VALEUR) : {item}", file=sys.stderr)
                sys.exit(1)
            key, value = item.split("=", 1)
            env_vars[key] = value

    fullscreen = None
    if args.fullscreen:
        fullscreen = True
    elif args.windowed:
        fullscreen = False

    game = install_manager.update_game_settings(
        store_id=args.store,
        game_id=args.game_id,
        proton_version=args.proton,
        launch_args=args.arg,
        env_vars=env_vars,
        fullscreen=fullscreen,
    )
    print(f"'{game.title}' mis à jour : proton={game.proton_version}, fullscreen={game.fullscreen}")


def cmd_uninstall_game(args) -> None:
    install_manager.uninstall_game(args.store, args.game_id, delete_prefix=not args.keep_prefix, delete_files=not args.keep_files)
    print("Jeu désinstallé.")


def cmd_check_updates(_args) -> None:
    stores = make_all_stores()
    updates = install_manager.check_all_updates(stores)
    if not updates:
        print("Tous les jeux sont à jour.")
        return
    for game, latest in updates:
        print(f"- [{game.store}] {game.title} : {game.version or '?'} -> {latest}")


def cmd_update_game(args) -> None:
    stores = make_all_stores()
    store = stores.get(args.store)
    if not store:
        print(f"Store inconnu : {args.store}", file=sys.stderr)
        sys.exit(1)
    game = library.get_game(args.store, args.game_id)
    if not game:
        print(f"Jeu non installé : {args.store}:{args.game_id}", file=sys.stderr)
        sys.exit(1)
    updated = install_manager.update_game(store, game)
    print(f"'{updated.title}' mis à jour vers la version disponible sur {store.display_name}.")


def cmd_update_all(_args) -> None:
    stores = make_all_stores()
    updates = install_manager.check_all_updates(stores)
    if not updates:
        print("Tous les jeux sont à jour.")
        return
    for game, latest in updates:
        print(f"Mise à jour de '{game.title}' ({game.version or '?'} -> {latest})…")
        install_manager.update_game(stores[game.store], game)
    print(f"{len(updates)} jeu(x) mis à jour.")


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
        fullscreen=not args.windowed,
    )
    print(f"'{game.title}' installé. Lancez-le avec : run {args.store} {args.game_id}")


def cmd_add_custom_game(args) -> None:
    env_vars = {}
    for item in args.env or []:
        if "=" not in item:
            print(f"Variable d'environnement invalide (attendu KEY=VALEUR) : {item}", file=sys.stderr)
            sys.exit(1)
        key, value = item.split("=", 1)
        env_vars[key] = value

    game = install_manager.add_custom_game(
        title=args.title,
        exe_path=args.exe,
        proton_version=args.proton,
        prefix_path=args.prefix,
        launch_args=args.arg or [],
        env_vars=env_vars,
        fullscreen=not args.windowed,
    )
    print(f"'{game.title}' ajouté. Lancez-le avec : run custom {game.id}")
    print(f"  préfixe : {game.prefix}")


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
    p_install.add_argument("--proton", default="auto", help="Version Proton, ou 'auto' pour télécharger/utiliser la dernière GE-Proton (défaut)")
    p_install.add_argument("--exe", required=True, help="Chemin relatif de l'exe une fois installé")
    p_install.add_argument("--no-silent", action="store_true", help="Ne pas passer /S à l'installateur")
    p_install.add_argument("--windowed", action="store_true", help="Ne pas forcer le plein écran (activé par défaut)")
    p_install.set_defaults(func=cmd_install_game)

    p_custom = sub.add_parser(
        "add-custom-game",
        help="Ajouter un jeu déjà installé (hors store) avec sa propre config Proton/Wine",
    )
    p_custom.add_argument("--title", required=True)
    p_custom.add_argument("--exe", required=True, help="Chemin complet vers l'exécutable")
    p_custom.add_argument("--proton", default="auto", help="Version Proton/Wine, ou 'auto' (défaut)")
    p_custom.add_argument("--prefix", help="Préfixe Wine existant à réutiliser (sinon un nouveau est créé)")
    p_custom.add_argument("--arg", action="append", help="Argument de lancement (répétable)")
    p_custom.add_argument("--env", action="append", help="Variable d'environnement KEY=VALEUR (répétable, ex: DXVK_HUD=1)")
    p_custom.add_argument("--windowed", action="store_true", help="Ne pas forcer le plein écran (activé par défaut)")
    p_custom.set_defaults(func=cmd_add_custom_game)

    p_configure = sub.add_parser("configure-game", help="Modifier la config Proton/lancement d'un jeu déjà installé")
    p_configure.add_argument("store")
    p_configure.add_argument("game_id")
    p_configure.add_argument("--proton", help="Nouvelle version Proton")
    p_configure.add_argument("--arg", action="append", dest="arg", help="Nouveaux arguments de lancement (répétable, remplace les anciens)")
    p_configure.add_argument("--env", action="append", help="Nouvelles variables d'environnement KEY=VALEUR (répétable, remplace les anciennes)")
    fs_group = p_configure.add_mutually_exclusive_group()
    fs_group.add_argument("--fullscreen", action="store_true")
    fs_group.add_argument("--windowed", action="store_true")
    p_configure.set_defaults(func=cmd_configure_game)

    p_uninstall = sub.add_parser("uninstall-game", help="Désinstaller un jeu")
    p_uninstall.add_argument("store")
    p_uninstall.add_argument("game_id")
    p_uninstall.add_argument("--keep-prefix", action="store_true", help="Garder le préfixe Wine")
    p_uninstall.add_argument("--keep-files", action="store_true", help="Garder les fichiers installés")
    p_uninstall.set_defaults(func=cmd_uninstall_game)

    sub.add_parser("check-updates", help="Lister les mises à jour disponibles").set_defaults(func=cmd_check_updates)

    p_update = sub.add_parser("update-game", help="Mettre à jour un jeu installé")
    p_update.add_argument("store")
    p_update.add_argument("game_id")
    p_update.set_defaults(func=cmd_update_game)

    sub.add_parser("update-all", help="Mettre à jour tous les jeux ayant une mise à jour disponible").set_defaults(func=cmd_update_all)

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
