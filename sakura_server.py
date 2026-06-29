"""Serveur de présence pour Sakura Launcher.

Très léger (stdlib uniquement, aucune dépendance à installer). Chaque
launcher envoie un "heartbeat" périodique avec son pseudo ; ce serveur
garde en mémoire le dernier "vu à" de chaque pseudo et expose qui est
en ligne maintenant (heartbeat reçu dans les ONLINE_TIMEOUT dernières
secondes).

Gère aussi un système d'admins simple : une liste de pseudos codée en
dur ci-dessous (ADMIN_USERS). Pas de vraie connexion OAuth Discord —
c'est juste la liste des personnes (identifiées par leur pseudo
Minecraft) que tu considères comme admins de ton Discord/communauté.
Un admin peut diffuser une annonce visible par tous les launchers
connectés.

Lancement :
    python sakura_server.py [port]      (port par défaut : 8765)

Le launcher doit ensuite pointer vers ce serveur via son adresse, ex :
    http://IP_OU_DOMAINE:8765
dans Paramètres > Serveur de présence.
"""
import json
import sys
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ONLINE_TIMEOUT = 30  # secondes sans heartbeat avant de considérer un joueur hors ligne

# Pseudos Minecraft des admins (édite cette liste avec les tiens).
# Un admin peut diffuser une annonce visible par tous les launchers connectés.
ADMIN_USERS = {"xNakz", "xLeyko", "Lauriana"}

# Édite ces deux valeurs à chaque fois que tu sors une nouvelle version du
# launcher : les clients connectés verront un badge de mise à jour s'afficher.
LATEST_VERSION = "2.1.0"
DOWNLOAD_URL = "https://discord.gg/zqw8KGKWJ"

_lock = threading.Lock()
_last_seen = {}        # username -> timestamp du dernier heartbeat
_all_users = set()      # tous les pseudos jamais vus (compteur cumulé)
_announcement = None    # {"message": str, "by": str, "at": float} ou None


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return {}

    def do_POST(self):
        global _announcement
        if self.path == "/heartbeat":
            data = self._read_json()
            username = str(data.get("username", "")).strip()
            if not username:
                self._send_json(400, {"ok": False, "error": "username manquant"})
                return
            with _lock:
                _last_seen[username] = time.time()
                _all_users.add(username)
            self._send_json(200, {"ok": True})

        elif self.path == "/announce":
            data = self._read_json()
            username = str(data.get("username", "")).strip()
            message = str(data.get("message", "")).strip()
            if username not in ADMIN_USERS:
                self._send_json(403, {"ok": False, "error": "pas admin"})
                return
            with _lock:
                if message:
                    _announcement = {"message": message, "by": username, "at": time.time()}
                else:
                    _announcement = None  # message vide = efface l'annonce
            self._send_json(200, {"ok": True})

        else:
            self._send_json(404, {"ok": False, "error": "route inconnue"})

    def do_GET(self):
        if self.path == "/online":
            now = time.time()
            with _lock:
                online = [u for u, t in _last_seen.items() if now - t <= ONLINE_TIMEOUT]
                total_members = len(_all_users)
                admins_online = [u for u in online if u in ADMIN_USERS]
            self._send_json(200, {
                "online": sorted(online, key=str.lower),
                "count": len(online),
                "members_total": total_members,
                "admins": sorted(admins_online, key=str.lower),
            })

        elif self.path == "/announcement":
            with _lock:
                data = dict(_announcement) if _announcement else None
            self._send_json(200, {"announcement": data})

        elif self.path == "/version":
            self._send_json(200, {"latest": LATEST_VERSION, "url": DOWNLOAD_URL})

        else:
            self._send_json(404, {"ok": False, "error": "route inconnue"})

    def log_message(self, fmt, *args):
        pass  # silence les logs HTTP par défaut


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Sakura presence server en écoute sur 0.0.0.0:{port}")
    print("Routes : POST /heartbeat {\"username\":...}  |  GET /online")
    print("         POST /announce  {\"username\":..., \"message\":...} (admin only)")
    print("         GET  /announcement")
    print(f"Admins configurés : {', '.join(sorted(ADMIN_USERS)) or '(aucun)'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
