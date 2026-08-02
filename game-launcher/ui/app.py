"""Interface graphique customtkinter du launcher.

Reste une couche fine au-dessus de cli.py / install_manager.py / stores/* :
aucune logique métier ici, uniquement de l'affichage et des appels aux
fonctions déjà testées en CLI.

Structure : barre latérale à gauche (Bibliothèque, un bouton par store,
Paramètres), panneau de contenu à droite qui change selon la sélection —
y compris un panneau de réglages par jeu (Proton, arguments, variables
d'environnement, plein écran).
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

import customtkinter as ctk

sys.path.insert(0, str(Path(__file__).parent.parent))

import install_manager
import library
import proton
from stores import make_all_stores

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class GameLauncherApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Sakura Game Launcher")
        self.geometry("1100x700")

        self.stores = make_all_stores()
        self._updates_cache: list[tuple[library.InstalledGame, str]] = []

        self.sidebar = ctk.CTkFrame(self, width=220)
        self.sidebar.pack(side="left", fill="y")

        self.content = ctk.CTkScrollableFrame(self)
        self.content.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        self.proton_status = ctk.CTkLabel(self.sidebar, text="Proton : vérification…", text_color="gray70", font=ctk.CTkFont(size=11))
        self.proton_status.pack(pady=(10, 0), padx=10, anchor="w")

        ctk.CTkButton(
            self.sidebar, text="📚 Bibliothèque", anchor="w",
            command=self.show_library,
        ).pack(fill="x", padx=10, pady=(10, 4))

        ctk.CTkButton(
            self.sidebar, text="+ Ajouter un jeu manuellement", anchor="w", fg_color="gray30",
            command=self._add_custom_game_dialog,
        ).pack(fill="x", padx=10, pady=4)

        ctk.CTkLabel(self.sidebar, text="Stores", font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(20, 6), padx=10, anchor="w")
        for store in self.stores.values():
            ctk.CTkButton(
                self.sidebar, text=store.display_name, anchor="w",
                command=lambda s=store: self.show_store(s),
            ).pack(fill="x", padx=10, pady=3)

        ctk.CTkButton(
            self.sidebar, text="⚙ Paramètres", anchor="w", fg_color="gray30",
            command=self.show_settings,
        ).pack(fill="x", padx=10, pady=(20, 4), side="bottom")

        self.show_library()
        threading.Thread(target=self._ensure_proton_at_startup, daemon=True).start()

    def _clear_content(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()

    # ── Démarrage : Proton/Wine auto ─────────────────────────────────────

    def _ensure_proton_at_startup(self) -> None:
        try:
            version = proton.ensure_proton_available()
            self.after(0, lambda: self.proton_status.configure(text=f"Proton : {version} ✓", text_color="lightgreen"))
        except Exception as e:
            self.after(0, lambda: self.proton_status.configure(text="Proton : échec du téléchargement auto", text_color="orange"))

    # ── Vue : bibliothèque (jeux installés) ──────────────────────────────

    def show_library(self) -> None:
        self._clear_content()
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(header, text="Bibliothèque", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkButton(header, text="Vérifier les mises à jour", width=180, command=self._check_updates).pack(side="right")

        games = library.list_games()
        if not games:
            ctk.CTkLabel(self.content, text="Aucun jeu installé pour le moment.").pack(anchor="w")
            return

        updates_by_key = {library.key_for(g.store, g.id): v for g, v in self._updates_cache}

        for g in games:
            row = ctk.CTkFrame(self.content)
            row.pack(fill="x", pady=4)

            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=10, pady=8)
            fs = "plein écran" if g.fullscreen else "fenêtré"
            ctk.CTkLabel(info, text=g.title, font=ctk.CTkFont(weight="bold")).pack(anchor="w")
            ctk.CTkLabel(info, text=f"{g.store} · {g.proton_version} · {fs}", text_color="gray70", font=ctk.CTkFont(size=11)).pack(anchor="w")

            key = library.key_for(g.store, g.id)
            if key in updates_by_key:
                ctk.CTkButton(row, text=f"Mettre à jour → {updates_by_key[key]}", width=160, fg_color="darkorange", command=lambda gg=g: self._update_game(gg)).pack(side="right", padx=6)

            ctk.CTkButton(row, text="Désinstaller", width=100, fg_color="darkred", command=lambda gg=g: self._uninstall(gg)).pack(side="right", padx=6)
            ctk.CTkButton(row, text="⚙", width=40, command=lambda gg=g: self.show_game_settings(gg)).pack(side="right", padx=6)
            ctk.CTkButton(row, text="Lancer", width=90, command=lambda gg=g: self._launch(gg)).pack(side="right", padx=6)

    def _launch(self, game: library.InstalledGame) -> None:
        def worker():
            try:
                install_manager.launch_game(game.store, game.id)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Erreur", str(e)))
        threading.Thread(target=worker, daemon=True).start()

    def _uninstall(self, game: library.InstalledGame) -> None:
        if not messagebox.askyesno("Désinstaller", f"Désinstaller '{game.title}' ? Le préfixe et les fichiers installés seront supprimés."):
            return

        def worker():
            try:
                install_manager.uninstall_game(game.store, game.id)
                self.after(0, self.show_library)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Erreur", str(e)))
        threading.Thread(target=worker, daemon=True).start()

    def _check_updates(self) -> None:
        def worker():
            updates = install_manager.check_all_updates(self.stores)
            self._updates_cache = updates
            if not updates:
                self.after(0, lambda: messagebox.showinfo("Mises à jour", "Tous les jeux sont à jour."))
            self.after(0, self.show_library)
        threading.Thread(target=worker, daemon=True).start()

    def _update_game(self, game: library.InstalledGame) -> None:
        store = self.stores.get(game.store)
        if not store:
            return

        def worker():
            try:
                install_manager.update_game(store, game)
                self._updates_cache = [(g, v) for g, v in self._updates_cache if g.id != game.id or g.store != game.store]
                self.after(0, lambda: messagebox.showinfo("Mise à jour", f"'{game.title}' mis à jour."))
                self.after(0, self.show_library)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Erreur", str(e)))
        threading.Thread(target=worker, daemon=True).start()

    # ── Vue : réglages d'un jeu ──────────────────────────────────────────

    def show_game_settings(self, game: library.InstalledGame) -> None:
        self._clear_content()
        ctk.CTkLabel(self.content, text=f"Réglages — {game.title}", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 20))

        versions = sorted(proton.find_proton_versions())
        ctk.CTkLabel(self.content, text="Version Proton/Wine").pack(anchor="w")
        proton_var = ctk.StringVar(value=game.proton_version)
        ctk.CTkOptionMenu(self.content, values=versions or [game.proton_version], variable=proton_var).pack(anchor="w", pady=(0, 15))

        ctk.CTkLabel(self.content, text="Arguments de lancement (séparés par des espaces)").pack(anchor="w")
        args_entry = ctk.CTkEntry(self.content, width=500)
        args_entry.insert(0, " ".join(game.launch_args))
        args_entry.pack(anchor="w", pady=(0, 15))

        ctk.CTkLabel(self.content, text="Variables d'environnement (KEY=VALEUR, séparées par des virgules)").pack(anchor="w")
        env_entry = ctk.CTkEntry(self.content, width=500)
        env_entry.insert(0, ",".join(f"{k}={v}" for k, v in game.env_vars.items()))
        env_entry.pack(anchor="w", pady=(0, 15))

        fullscreen_var = ctk.BooleanVar(value=game.fullscreen)
        ctk.CTkSwitch(self.content, text="Forcer le plein écran", variable=fullscreen_var).pack(anchor="w", pady=(0, 20))

        def save():
            args = args_entry.get().split()
            env_vars = {}
            for item in [e.strip() for e in env_entry.get().split(",") if e.strip()]:
                if "=" in item:
                    k, v = item.split("=", 1)
                    env_vars[k] = v
            try:
                install_manager.update_game_settings(
                    game.store, game.id,
                    proton_version=proton_var.get(),
                    launch_args=args,
                    env_vars=env_vars,
                    fullscreen=fullscreen_var.get(),
                )
                messagebox.showinfo("Réglages", "Enregistré.")
                self.show_library()
            except Exception as e:
                messagebox.showerror("Erreur", str(e))

        btns = ctk.CTkFrame(self.content, fg_color="transparent")
        btns.pack(anchor="w")
        ctk.CTkButton(btns, text="Enregistrer", command=save).pack(side="left", padx=(0, 10))
        ctk.CTkButton(btns, text="Retour", fg_color="gray30", command=self.show_library).pack(side="left")

    # ── Ajout manuel d'un jeu ────────────────────────────────────────────

    def _add_custom_game_dialog(self) -> None:
        versions = proton.find_proton_versions()
        if not versions:
            messagebox.showwarning("Proton requis", "Aucune version Proton détectée pour le moment (téléchargement automatique en cours au démarrage, réessayez dans un instant, ou passez par Paramètres).")
            return

        title = simpledialog.askstring("Ajouter un jeu", "Nom du jeu :")
        if not title:
            return

        exe = filedialog.askopenfilename(title="Sélectionnez l'exécutable (.exe)", filetypes=[("Exécutable Windows", "*.exe"), ("Tous les fichiers", "*.*")])
        if not exe:
            return

        proton_version = simpledialog.askstring(
            "Version Proton/Wine",
            f"Versions disponibles : {', '.join(sorted(versions))}\n\nQuelle version utiliser ?",
        )
        if not proton_version or proton_version not in versions:
            messagebox.showerror("Erreur", "Version Proton invalide.")
            return

        prefix = simpledialog.askstring(
            "Préfixe Wine",
            "Chemin d'un préfixe Wine existant à réutiliser (laisser vide pour en créer un nouveau) :",
        )

        args_raw = simpledialog.askstring("Arguments de lancement", "Arguments séparés par des espaces (laisser vide si aucun) :") or ""
        launch_args = args_raw.split() if args_raw else []

        env_raw = simpledialog.askstring(
            "Variables d'environnement",
            "Séparées par des virgules, ex: DXVK_HUD=1,PROTON_LOG=1 (laisser vide si aucune) :",
        ) or ""
        env_vars = {}
        for item in [e.strip() for e in env_raw.split(",") if e.strip()]:
            if "=" in item:
                k, v = item.split("=", 1)
                env_vars[k] = v

        fullscreen = messagebox.askyesno("Plein écran", "Forcer le lancement en plein écran ?", default="yes")

        def worker():
            try:
                install_manager.add_custom_game(
                    title=title, exe_path=exe, proton_version=proton_version,
                    prefix_path=prefix or None, launch_args=launch_args, env_vars=env_vars,
                    fullscreen=fullscreen,
                )
                self.after(0, lambda: messagebox.showinfo("Ajout", f"'{title}' ajouté à la bibliothèque."))
                self.after(0, self.show_library)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Erreur", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    # ── Vue : Paramètres ─────────────────────────────────────────────────

    def show_settings(self) -> None:
        self._clear_content()
        ctk.CTkLabel(self.content, text="Paramètres", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 20))

        ctk.CTkLabel(self.content, text="Versions Proton/Wine", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", pady=(0, 6))
        versions = proton.find_proton_versions()
        if not versions:
            ctk.CTkLabel(self.content, text="Aucune version détectée.").pack(anchor="w", pady=(0, 6))
        else:
            for name in sorted(versions):
                ctk.CTkLabel(self.content, text=f"- {name}").pack(anchor="w")
        ctk.CTkButton(self.content, text="Télécharger la dernière GE-Proton", command=self._install_ge).pack(anchor="w", pady=(10, 25))

        ctk.CTkLabel(self.content, text="Connexions aux stores", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", pady=(0, 6))
        for store in self.stores.values():
            row = ctk.CTkFrame(self.content, fg_color="transparent")
            row.pack(fill="x", pady=2)
            status = "connecté" if store.is_authenticated() else "non connecté"
            ctk.CTkLabel(row, text=f"{store.display_name} — {status}").pack(side="left")
            if store.is_authenticated():
                ctk.CTkButton(row, text="Déconnecter", width=100, fg_color="gray30", command=lambda s=store: self._logout(s)).pack(side="right")
            else:
                ctk.CTkButton(row, text="Se connecter", width=100, command=lambda s=store: self._login(s)).pack(side="right")

    def _logout(self, store) -> None:
        store.logout()
        self.show_settings()

    def _install_ge(self) -> None:
        def worker():
            try:
                tag = proton.install_latest_ge()
                self.after(0, lambda: messagebox.showinfo("Proton", f"GE-Proton {tag} installé."))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Erreur", str(e)))
            finally:
                self.after(0, self.show_settings)
        threading.Thread(target=worker, daemon=True).start()

    # ── Vue : bibliothèque d'un store ───────────────────────────────────

    def show_store(self, store) -> None:
        self._clear_content()
        ctk.CTkLabel(self.content, text=store.display_name, font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 10))

        if not store.is_authenticated():
            ctk.CTkButton(self.content, text="Se connecter", command=lambda: self._login(store)).pack(anchor="w")
            return

        ctk.CTkButton(self.content, text="Rafraîchir la bibliothèque", command=lambda: self._load_library(store)).pack(anchor="w", pady=(0, 10))
        self._games_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        self._games_frame.pack(fill="both", expand=True)

    def _login(self, store) -> None:
        if store.store_id == "steam":
            self._login_steam(store)
            return

        try:
            import webbrowser
            webbrowser.open(store.login_url())
        except Exception:
            pass
        pasted = simpledialog.askstring(
            "Connexion",
            f"Connectez-vous à {store.display_name} dans le navigateur, puis\n"
            "collez ici l'URL de redirection (ou le code) :",
        )
        if not pasted:
            return
        try:
            store.login_with_code(pasted)
            messagebox.showinfo("Connexion", f"Connecté à {store.display_name}.")
            self.show_store(store)
        except Exception as e:
            messagebox.showerror("Erreur de connexion", str(e))

    def _login_steam(self, store) -> None:
        api_key = simpledialog.askstring(
            "Connexion Steam",
            "Clé API Steam (https://steamcommunity.com/dev/apikey) :",
        )
        if not api_key:
            return
        steam_id = simpledialog.askstring(
            "Connexion Steam",
            "SteamID64 (steamcommunity.com/my -> Modifier le profil) :",
        )
        if not steam_id:
            return
        try:
            store.login_with_credentials(api_key, steam_id)
            messagebox.showinfo("Connexion", "Connecté à Steam.")
            self.show_store(store)
        except Exception as e:
            messagebox.showerror("Erreur de connexion", str(e))

    def _load_library(self, store) -> None:
        for child in self._games_frame.winfo_children():
            child.destroy()

        def worker():
            try:
                games = store.list_owned_games()
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Erreur", str(e)))
                return
            self.after(0, lambda: self._render_games(store, games))

        threading.Thread(target=worker, daemon=True).start()

    def _render_games(self, store, games) -> None:
        if not games:
            ctk.CTkLabel(self._games_frame, text="Aucun jeu trouvé.").pack(anchor="w")
            return
        for g in games:
            row = ctk.CTkFrame(self._games_frame)
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(row, text=g.title).pack(side="left", padx=10, pady=8)
            if store.store_id == "steam":
                # Steam gère lui-même l'installation et Proton : on ne fait
                # que déclencher le lancement via le client Steam.
                ctk.CTkButton(row, text="Lancer", width=100, command=lambda gg=g: self._launch_steam(store, gg)).pack(side="right", padx=10)
            else:
                ctk.CTkButton(row, text="Installer…", width=100, command=lambda gg=g: self._open_install_dialog(store, gg)).pack(side="right", padx=10)

    def _launch_steam(self, store, game) -> None:
        try:
            store.launch_game(game.id)
        except Exception as e:
            messagebox.showerror("Erreur", str(e))

    def _open_install_dialog(self, store, game) -> None:
        proton_version = "auto"
        fullscreen = messagebox.askyesno("Plein écran", "Forcer le lancement en plein écran ?", default="yes")
        exe = simpledialog.askstring("Exécutable", "Chemin relatif de l'exécutable après installation (ex: Game.exe) :")
        if not exe:
            return

        def worker():
            try:
                install_manager.install_game(store, game.id, game.title, proton_version, exe, fullscreen=fullscreen)
                self.after(0, lambda: messagebox.showinfo("Installation", f"'{game.title}' installé."))
                self.after(0, self.show_library)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Erreur d'installation", str(e)))

        threading.Thread(target=worker, daemon=True).start()


def main() -> None:
    app = GameLauncherApp()
    app.mainloop()


if __name__ == "__main__":
    main()
