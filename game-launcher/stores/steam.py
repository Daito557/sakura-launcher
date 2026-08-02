"""Intégration Steam.

Contrairement aux autres stores, Steam gère déjà lui-même le téléchargement
des jeux et sa propre intégration Proton : ce launcher ne réinstalle rien,
il se contente de lister la bibliothèque via la Steam Web API et de lancer
les jeux via le client Steam installé sur la machine (`steam steam://rungameid/<appid>`).

Connexion : la Steam Web API ne propose pas d'OAuth grand public, seulement
une clé API liée à un compte (https://steamcommunity.com/dev/apikey) plus le
SteamID64 du profil dont on veut lire la bibliothèque. C'est donc ces deux
informations qu'on demande à l'utilisateur, stockées localement.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import urllib.parse
import urllib.request

from config import TOKENS_DIR
from stores.base import DownloadInfo, GameInfo, StoreClient, StoreNotImplementedError

TOKENS_FILE = TOKENS_DIR / "steam.json"
OWNED_GAMES_URL = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"


def _http_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


class SteamClient(StoreClient):
    store_id = "steam"
    display_name = "Steam"

    def __init__(self) -> None:
        self._creds: dict = {}
        if TOKENS_FILE.exists():
            try:
                self._creds = json.loads(TOKENS_FILE.read_text("utf-8"))
            except Exception:
                self._creds = {}

    # ── Auth ────────────────────────────────────────────────────────────

    def is_authenticated(self) -> bool:
        return bool(self._creds.get("api_key") and self._creds.get("steam_id"))

    def login_with_credentials(self, api_key: str, steam_id: str) -> None:
        self._creds = {"api_key": api_key.strip(), "steam_id": steam_id.strip()}
        TOKENS_DIR.mkdir(parents=True, exist_ok=True)
        TOKENS_FILE.write_text(json.dumps(self._creds, indent=2), "utf-8")

    def login(self) -> None:
        print("Clé API Steam : https://steamcommunity.com/dev/apikey")
        api_key = input("Clé API Steam : ").strip()
        steam_id = input("SteamID64 (steamcommunity.com/my -> Modifier le profil) : ").strip()
        self.login_with_credentials(api_key, steam_id)
        print("Connecté à Steam.")

    def logout(self) -> None:
        self._creds = {}
        if TOKENS_FILE.exists():
            TOKENS_FILE.unlink()

    # ── Bibliothèque ────────────────────────────────────────────────────

    def list_owned_games(self) -> list[GameInfo]:
        if not self.is_authenticated():
            raise RuntimeError("Non connecté à Steam — appelez login() d'abord.")

        params = {
            "key": self._creds["api_key"],
            "steamid": self._creds["steam_id"],
            "include_appinfo": "true",
            "include_played_free_games": "true",
            "format": "json",
        }
        url = f"{OWNED_GAMES_URL}?{urllib.parse.urlencode(params)}"
        data = _http_json(url)
        games = data.get("response", {}).get("games", [])

        result = []
        for g in games:
            appid = g["appid"]
            icon_hash = g.get("img_icon_url")
            cover = (
                f"https://media.steampowered.com/steamcommunity/public/images/apps/{appid}/{icon_hash}.jpg"
                if icon_hash else None
            )
            result.append(GameInfo(store=self.store_id, id=str(appid), title=g.get("name", f"#{appid}"), cover_url=cover))
        return result

    # ── Téléchargement / lancement ──────────────────────────────────────

    def get_download_info(self, game_id: str) -> DownloadInfo:
        raise StoreNotImplementedError(
            "Steam gère lui-même le téléchargement de ses jeux : installez-les "
            "depuis le client Steam, puis utilisez launch_game() pour les lancer."
        )

    def launch_game(self, game_id: str) -> None:
        """Lance un jeu déjà installé via Steam (`steam steam://rungameid/<appid>`)."""
        steam_bin = shutil.which("steam")
        uri = f"steam://rungameid/{game_id}"
        if steam_bin:
            subprocess.Popen([steam_bin, uri])
        elif shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", uri])
        else:
            raise RuntimeError("Client Steam introuvable (ni 'steam' ni 'xdg-open' dans le PATH).")
