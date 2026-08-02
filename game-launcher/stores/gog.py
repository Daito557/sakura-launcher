"""Intégration GOG : la plateforme sans DRM, API publique la plus simple à
utiliser sans accord commercial. Le couple client_id/client_secret ci-dessous
est celui utilisé publiquement par les outils open source gogdl/Heroic/Lutris
pour émuler le client officiel GOG Galaxy — ce n'est pas un secret privé.

Flow de connexion (OAuth "code" manuel, car GOG n'expose pas de device-code
flow) :
  1. On affiche une URL de login GOG.
  2. L'utilisateur se connecte dans son navigateur, est redirigé vers une
     page qui échoue à charger (embed.gog.com/on_login_success) mais dont
     l'URL contient ?code=XXXX.
  3. L'utilisateur colle cette URL (ou juste le code) dans le launcher.
  4. On échange ce code contre un access_token + refresh_token, sauvegardés
     localement pour les prochaines sessions.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

from config import TOKENS_DIR
from stores.base import DownloadInfo, GameInfo, StoreClient

CLIENT_ID = "46899977096215655"
CLIENT_SECRET = "9d85c43b1482497dbbce61f6e4aa173a433796eeae2ca6ec5a17e0a5e6b3900"
REDIRECT_URI = "https://embed.gog.com/on_login_success?origin=client"

AUTH_URL = (
    "https://auth.gog.com/auth"
    f"?client_id={CLIENT_ID}&redirect_uri={urllib.parse.quote(REDIRECT_URI, safe='')}"
    "&response_type=code&layout=client2"
)
TOKEN_URL = "https://auth.gog.com/token"
TOKENS_FILE = TOKENS_DIR / "gog.json"


def _http_json(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


class GogClient(StoreClient):
    store_id = "gog"
    display_name = "GOG"

    def __init__(self) -> None:
        self._tokens: dict = {}
        if TOKENS_FILE.exists():
            try:
                self._tokens = json.loads(TOKENS_FILE.read_text("utf-8"))
            except Exception:
                self._tokens = {}

    # ── Auth ────────────────────────────────────────────────────────────

    def is_authenticated(self) -> bool:
        return bool(self._tokens.get("refresh_token"))

    def login_url(self) -> str:
        return AUTH_URL

    def login_with_code(self, code: str) -> None:
        """Échange un code d'autorisation (ou l'URL de redirection complète
        dont on extrait ?code=) contre des tokens."""
        if "code=" in code:
            code = urllib.parse.parse_qs(urllib.parse.urlparse(code).query)["code"][0]

        params = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        }
        url = f"{TOKEN_URL}?{urllib.parse.urlencode(params)}"
        self._tokens = _http_json(url)
        self._tokens["obtained_at"] = time.time()
        self._save_tokens()

    def login(self) -> None:
        print("Ouvrez cette URL, connectez-vous à GOG, puis collez l'URL de")
        print("redirection (ou juste le paramètre 'code') ici :\n")
        print(self.login_url())
        pasted = input("\nURL ou code : ").strip()
        self.login_with_code(pasted)
        print("Connecté à GOG.")

    def logout(self) -> None:
        self._tokens = {}
        if TOKENS_FILE.exists():
            TOKENS_FILE.unlink()

    def _save_tokens(self) -> None:
        TOKENS_FILE.write_text(json.dumps(self._tokens, indent=2), "utf-8")

    def _access_token(self) -> str:
        if not self._tokens.get("refresh_token"):
            raise RuntimeError("Non connecté à GOG — appelez login() d'abord.")

        obtained_at = self._tokens.get("obtained_at", 0)
        expires_in = self._tokens.get("expires_in", 0)
        if time.time() < obtained_at + expires_in - 60:
            return self._tokens["access_token"]

        params = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": self._tokens["refresh_token"],
        }
        url = f"{TOKEN_URL}?{urllib.parse.urlencode(params)}"
        self._tokens = _http_json(url)
        self._tokens["obtained_at"] = time.time()
        self._save_tokens()
        return self._tokens["access_token"]

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token()}"}

    # ── Bibliothèque ────────────────────────────────────────────────────

    def list_owned_games(self) -> list[GameInfo]:
        data = _http_json("https://embed.gog.com/user/data/games", self._auth_headers())
        game_ids = data.get("owned", [])

        games: list[GameInfo] = []
        for game_id in game_ids:
            try:
                info = _http_json(f"https://api.gog.com/products/{game_id}?expand=images")
            except Exception:
                continue
            cover = info.get("images", {}).get("logo2x")
            games.append(GameInfo(store=self.store_id, id=str(game_id), title=info.get("title", f"#{game_id}"), cover_url=cover))
        return games

    # ── Téléchargement ──────────────────────────────────────────────────

    def get_download_info(self, game_id: str) -> DownloadInfo:
        info = _http_json(f"https://api.gog.com/products/{game_id}?expand=downloads")
        installers = info.get("downloads", {}).get("installers", [])
        windows_installer = next((i for i in installers if i.get("os") == "windows"), None)
        if not windows_installer or not windows_installer.get("files"):
            raise RuntimeError(f"Aucun installateur Windows trouvé pour le jeu {game_id}.")

        manual_url = windows_installer["files"][0]["downlink"]
        resolved = _http_json(manual_url, self._auth_headers())
        download_url = resolved["downlink"]

        filename = urllib.parse.unquote(_filename_from_url(download_url))
        return DownloadInfo(url=download_url, filename=filename)

    # ── Mises à jour ─────────────────────────────────────────────────────

    def get_latest_version(self, game_id: str) -> str:
        """Version de l'installateur Windows actuellement publiée par GOG,
        utilisée pour détecter si une mise à jour est disponible."""
        info = _http_json(f"https://api.gog.com/products/{game_id}?expand=downloads")
        installers = info.get("downloads", {}).get("installers", [])
        windows_installer = next((i for i in installers if i.get("os") == "windows"), None)
        if not windows_installer:
            return ""
        return str(windows_installer.get("version", ""))


def _filename_from_url(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    return path.rsplit("/", 1)[-1] or "installer.exe"
