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

Gère enfin un classement (nombre de lancements par joueur) et un
système de trophées partagé : chaque launcher signale les trophées
débloqués par son joueur, et tout le monde peut voir les trophées des
autres (POST /trophy, GET /trophies, GET /leaderboard).

Les données (lancements + trophées) sont persistées dans
server_data.json à côté de ce script, pour survivre à un redémarrage.

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
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ONLINE_TIMEOUT = 30  # secondes sans heartbeat avant de considérer un joueur hors ligne
DATA_FILE = Path(__file__).parent / "server_data.json"

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
_launches = {}          # username -> nombre de lancements (classement)
_trophies = {}           # username -> {trophy_id: timestamp}


def _load_data():
    global _launches, _trophies, _all_users
    if DATA_FILE.exists():
        try:
            d = json.loads(DATA_FILE.read_text("utf-8"))
            _launches.update(d.get("launches", {}))
            _trophies.update(d.get("trophies", {}))
            _all_users.update(d.get("all_users", []))
        except Exception:
            pass


def _save_data():
    try:
        DATA_FILE.write_text(json.dumps({
            "launches": _launches,
            "trophies": _trophies,
            "all_users": sorted(_all_users),
        }, ensure_ascii=False, indent=2), "utf-8")
    except Exception:
        pass


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

        elif self.path == "/launch":
            data = self._read_json()
            username = str(data.get("username", "")).strip()
            if not username:
                self._send_json(400, {"ok": False, "error": "username manquant"})
                return
            with _lock:
                _launches[username] = _launches.get(username, 0) + 1
                _all_users.add(username)
                _save_data()
                count = _launches[username]
            self._send_json(200, {"ok": True, "launches": count})

        elif self.path == "/trophy":
            data = self._read_json()
            username = str(data.get("username", "")).strip()
            trophy_id = str(data.get("trophy_id", "")).strip()
            if not username or not trophy_id:
                self._send_json(400, {"ok": False, "error": "username/trophy_id manquant"})
                return
            with _lock:
                user_trophies = _trophies.setdefault(username, {})
                is_new = trophy_id not in user_trophies
                if is_new:
                    user_trophies[trophy_id] = time.time()
                    _save_data()
            self._send_json(200, {"ok": True, "new": is_new})

        elif self.path == "/trophy/sync":
            # Remplace l'ensemble des trophées "mc_*" (avancements Minecraft)
            # d'un joueur par la liste fournie, qui reflète son état RÉEL en
            # jeu à l'instant T (envoyée par le mod à chaque connexion). Les
            # avancements retirés via "/advancement revoke" en jeu sont donc
            # bien effacés ici aussi, ce qu'un simple POST /trophy ne permet
            # pas (lui ne fait qu'ajouter). Les trophées non-"mc_" (lancements,
            # admin, skin...) ne sont jamais touchés par cette route.
            data = self._read_json()
            username = str(data.get("username", "")).strip()
            current_ids = data.get("trophy_ids", [])
            if not username or not isinstance(current_ids, list):
                self._send_json(400, {"ok": False, "error": "username/trophy_ids manquant"})
                return
            current_set = {str(t) for t in current_ids if str(t).startswith("mc_")}
            with _lock:
                user_trophies = _trophies.setdefault(username, {})
                kept = {k: v for k, v in user_trophies.items() if not k.startswith("mc_")}
                for tid in current_set:
                    kept[tid] = user_trophies.get(tid, time.time())
                _trophies[username] = kept
                _save_data()
            self._send_json(200, {"ok": True, "count": len(current_set)})

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

        elif self.path == "/leaderboard":
            with _lock:
                rows = [
                    {"username": u, "launches": n, "trophies": len(_trophies.get(u, {}))}
                    for u, n in _launches.items()
                ]
            rows.sort(key=lambda r: (-r["launches"], r["username"].lower()))
            self._send_json(200, {"leaderboard": rows[:50]})

        elif self.path.startswith("/trophies"):
            qs = self.path.split("?", 1)[1] if "?" in self.path else ""
            params = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
            username = params.get("username", "")
            import urllib.parse
            username = urllib.parse.unquote(username)
            with _lock:
                data = dict(_trophies.get(username, {}))
            self._send_json(200, {"trophies": data})

        else:
            self._send_json(404, {"ok": False, "error": "route inconnue"})

    def log_message(self, fmt, *args):
        pass  # silence les logs HTTP par défaut


def main():
    _load_data()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Sakura presence server en écoute sur 0.0.0.0:{port}")
    print("Routes : POST /heartbeat {\"username\":...}  |  GET /online")
    print("         POST /announce  {\"username\":..., \"message\":...} (admin only)")
    print("         GET  /announcement")
    print("         POST /launch    {\"username\":...}")
    print("         POST /trophy    {\"username\":..., \"trophy_id\":...}")
    print("         GET  /trophies?username=...  |  GET /leaderboard")
    print(f"Admins configurés : {', '.join(sorted(ADMIN_USERS)) or '(aucun)'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
