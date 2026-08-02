"""Interface graphique customtkinter du launcher.

Reste une couche fine au-dessus de cli.py / install_manager.py / stores/* :
aucune logique métier ici, uniquement de l'affichage et des appels aux
fonctions déjà testées en CLI.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path
from tkinter import messagebox, simpledialog

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
        self.geometry("1000x650")

        self.stores = make_all_stores()

        self.sidebar = ctk.CTkFrame(self, width=200)
        self.sidebar.pack(side="left", fill="y")

        self.content = ctk.CTkScrollableFrame(self)
        self.content.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(self.sidebar, text="Stores", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(20, 10))
        for store in self.stores.values():
            ctk.CTkButton(
                self.sidebar, text=store.display_name,
                command=lambda s=store: self.show_store(s),
            ).pack(fill="x", padx=10, pady=4)

        ctk.CTkButton(
            self.sidebar, text="Jeux installés", fg_color="gray30",
            command=self.show_installed,
        ).pack(fill="x", padx=10, pady=(20, 4))

        ctk.CTkButton(
            self.sidebar, text="Versions Proton", fg_color="gray30",
            command=self.show_proton,
        ).pack(fill="x", padx=10, pady=4)

        self.show_installed()

    def _clear_content(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()

    # ── Vue : jeux installés ────────────────────────────────────────────

    def show_installed(self) -> None:
        self._clear_content()
        ctk.CTkLabel(self.content, text="Jeux installés", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 10))

        games = library.list_games()
        if not games:
            ctk.CTkLabel(self.content, text="Aucun jeu installé pour le moment.").pack(anchor="w")
            return

        for g in games:
            row = ctk.CTkFrame(self.content)
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(row, text=f"{g.title}  ({g.store}, {g.proton_version})").pack(side="left", padx=10, pady=8)
            ctk.CTkButton(row, text="Lancer", width=100, command=lambda gg=g: self._launch(gg)).pack(side="right", padx=10)

    def _launch(self, game: library.InstalledGame) -> None:
        def worker():
            try:
                install_manager.launch_game(game.store, game.id)
            except Exception as e:
                messagebox.showerror("Erreur", str(e))
        threading.Thread(target=worker, daemon=True).start()

    # ── Vue : versions Proton ───────────────────────────────────────────

    def show_proton(self) -> None:
        self._clear_content()
        ctk.CTkLabel(self.content, text="Versions Proton", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", pady=(0, 10))

        versions = proton.find_proton_versions()
        if not versions:
            ctk.CTkLabel(self.content, text="Aucune version détectée.").pack(anchor="w", pady=(0, 10))
        else:
            for name in sorted(versions):
                ctk.CTkLabel(self.content, text=f"- {name}").pack(anchor="w")

        ctk.CTkButton(self.content, text="Télécharger la dernière GE-Proton", command=self._install_ge).pack(anchor="w", pady=20)

    def _install_ge(self) -> None:
        def worker():
            try:
                tag = proton.install_latest_ge()
                messagebox.showinfo("Proton", f"GE-Proton {tag} installé.")
            except Exception as e:
                messagebox.showerror("Erreur", str(e))
            finally:
                self.after(0, self.show_proton)
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
        versions = proton.find_proton_versions()
        if not versions:
            messagebox.showwarning("Proton requis", "Installez d'abord une version de Proton (menu Versions Proton).")
            return
        proton_version = simpledialog.askstring("Version Proton", f"Versions disponibles : {', '.join(sorted(versions))}\n\nQuelle version utiliser ?")
        if not proton_version or proton_version not in versions:
            return
        exe = simpledialog.askstring("Exécutable", "Chemin relatif de l'exécutable après installation (ex: Game.exe) :")
        if not exe:
            return

        def worker():
            try:
                install_manager.install_game(store, game.id, game.title, proton_version, exe)
                self.after(0, lambda: messagebox.showinfo("Installation", f"'{game.title}' installé."))
                self.after(0, self.show_installed)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Erreur d'installation", str(e)))

        threading.Thread(target=worker, daemon=True).start()


def main() -> None:
    app = GameLauncherApp()
    app.mainloop()


if __name__ == "__main__":
    main()
