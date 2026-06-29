import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
import customtkinter as ctk
import subprocess, threading, sys, json, shutil
import datetime, traceback, urllib.request, os, socket, time
from pathlib import Path
import minecraft_launcher_lib

try:
    import windnd  # glisser-déposer de fichiers natif Windows (optionnel)
    HAS_DND = True
except ImportError:
    HAS_DND = False

APP_VERSION = "2.1.0"

# ── PyInstaller-safe base dir ─────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent.resolve()
else:
    BASE_DIR = Path(__file__).parent.resolve()

def resource_path(name):
    """Chemin vers un fichier embarqué (ex: icon.png) qui marche aussi bien
    en script qu'en exe PyInstaller --onefile : dans ce dernier cas les
    ressources sont extraites dans un dossier temporaire (sys._MEIPASS),
    pas à côté de l'exe (contrairement à BASE_DIR)."""
    base = Path(getattr(sys, "_MEIPASS", BASE_DIR))
    return base / name

MC_DIR     = BASE_DIR / "minecraft"
MODS_DIR   = MC_DIR  / "mods"
LOG_FILE   = BASE_DIR / "crash_log.txt"
STATS_FILE = BASE_DIR / "users_stats.json"
MC_DIR.mkdir(exist_ok=True)
MODS_DIR.mkdir(exist_ok=True)

# ── Statistiques d'utilisation (compteur local d'utilisateurs du panel) ──────
# Remarque : ce compteur est local à cette installation du launcher (pas de
# serveur central), il compte les pseudos distincts qui ont lancé le jeu et
# le nombre total de lancements depuis ce poste.

def load_stats():
    try:
        if STATS_FILE.exists():
            d = json.loads(STATS_FILE.read_text("utf-8"))
            d.setdefault("users", [])
            d.setdefault("launches", 0)
            return d
    except Exception:
        pass
    return {"users": [], "launches": 0}

def save_stats(d):
    try:
        STATS_FILE.write_text(json.dumps(d, indent=2, ensure_ascii=False), "utf-8")
    except Exception:
        pass

def record_launch(username):
    d = load_stats()
    if username and username not in d["users"]:
        d["users"].append(username)
    d["launches"] = d.get("launches", 0) + 1
    save_stats(d)
    return d

# ── Trophées (système partagé via le serveur de présence) ────────────────────
# Catalogue fixe : id -> (icône, nom, description). L'ordre ici est l'ordre
# d'affichage dans la page Classement.
TROPHIES = {
    "first_launch":   ("🎮", "Premier pas",       "Lancer Minecraft pour la première fois"),
    "launches_10":    ("🔥", "Habitué",            "10 lancements depuis ce launcher"),
    "launches_50":    ("⭐", "Vétéran",            "50 lancements depuis ce launcher"),
    "launches_200":   ("👑", "Légende",            "200 lancements depuis ce launcher"),
    "skin_custom":    ("🎨", "Stylé",              "Appliquer un skin personnalisé"),
    "mod_dropper":    ("🧩", "Bricoleur",          "Installer un mod par glisser-déposer"),
    "shader_installed": ("✨", "Esthète",          "Installer un shaderpack"),
    "admin":          ("🛡", "Modérateur",         "Devenir admin du serveur de présence"),
}

TROPHIES_FILE = BASE_DIR / "trophies.json"

def load_trophies():
    try:
        if TROPHIES_FILE.exists():
            return json.loads(TROPHIES_FILE.read_text("utf-8"))
    except Exception:
        pass
    return {}

def save_trophies(d):
    try:
        TROPHIES_FILE.write_text(json.dumps(d, indent=2, ensure_ascii=False), "utf-8")
    except Exception:
        pass

def offline_uuid(username):
    """UUID offline déterministe basé sur le pseudo, même algo que le
    Minecraft vanilla — utilisé à la fois au lancement (compte non-MS) et
    pour retrouver le fichier d'avancements du joueur dans saves/."""
    import hashlib as _hl
    raw = _hl.md5(("OfflinePlayer:" + username).encode()).digest()
    b = bytearray(raw)
    b[6] = (b[6] & 0x0f) | 0x30
    b[8] = (b[8] & 0x3f) | 0x80
    return "{:08x}-{:04x}-{:04x}-{:04x}-{:012x}".format(
        int.from_bytes(b[0:4], 'big'), int.from_bytes(b[4:6], 'big'),
        int.from_bytes(b[6:8], 'big'), int.from_bytes(b[8:10], 'big'),
        int.from_bytes(b[10:16], 'big'))

# ── Succès Minecraft (advancements) à intégrer comme trophées ────────────────
# Sous-ensemble des succès vanilla les plus connus. clé = id d'avancement
# Minecraft (sans le namespace "minecraft:"), valeur = (icône, nom, desc).
MC_ADVANCEMENTS = {
    "story/mine_stone":      ("⛏", "Pierre angulaire",      "Miner de la pierre avec une pioche en bois"),
    "story/smelt_iron":      ("🔧", "Acquisition de fer",     "Fondre un lingot de fer"),
    "story/obtain_armor":    ("🪖", "Habillé pour l'occasion", "Porter une pièce d'armure en fer"),
    "story/mine_diamond":    ("💎", "Diamants !",             "Obtenir un diamant"),
    "story/enter_the_nether": ("🔥", "Nous devons creuser plus profond", "Construire, allumer et entrer dans un portail du Nether"),
    "story/enter_the_end":   ("🌌", "La fin ?",               "Entrer dans le portail de l'End"),
    "end/kill_dragon":       ("🐉", "Libérer la fin",         "Tuer le dragon de l'End"),
    "nether/find_fortress":  ("🏰", "Une terrible fortresse", "Trouver une forteresse du Nether"),
    "husbandry/balanced_diet": ("🍗", "Régime équilibré",     "Manger tous les aliments du jeu"),
    "adventure/kill_a_mob":  ("⚔", "Monstre Hunter",          "Tuer une créature hostile"),
    "story/follow_ender_eye": ("👁", "Voyage vers l'End",     "Suivre un œil de l'Ender"),
}
TROPHIES.update({f"mc_{k}": v for k, v in MC_ADVANCEMENTS.items()})

DISCORD_SUPPORT_URL = "https://discord.gg/zqw8KGKWJ"

NEOFORGE_API = "https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge"
NEOFORGE_JAR = "https://maven.neoforged.net/releases/net/neoforged/neoforge/{ver}/neoforge-{ver}-installer.jar"

# Connexion compte Microsoft/Xbox réel (flux OAuth officiel, légitime).
# Pour fonctionner, il faut enregistrer une application Azure gratuite
# (https://portal.azure.com -> App registrations) et coller son Client ID ici.
# Sans ce client ID, la connexion au vrai compte Minecraft est impossible :
# il n'existe aucun moyen légitime de se connecter "à la place" de Microsoft.
MS_CLIENT_ID    = "ENTER_YOUR_AZURE_CLIENT_ID"
MS_REDIRECT_URI = "https://login.microsoftonline.com/common/oauth2/nativeclient"

# ── Palette ───────────────────────────────────────────────────────────────────
BG      = "#0d0d1a"
SIDE    = "#0f0f28"
CARD    = "#161630"
CARD2   = "#1c1c3a"
ACCENT  = "#7c3aed"
ACCENT2 = "#a855f7"
ACT_BG  = "#2a1a5e"
GREEN   = "#10b981"
RED_C   = "#ef4444"
ORANGE  = "#f59e0b"
CYAN    = "#06b6d4"
TEXT    = "#e2e8f0"
TEXT2   = "#94a3b8"
TEXT3   = "#475569"
BORDER  = "#2d2d5a"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Correction du zoom Windows ───────────────────────────────────────────────
# Sans ça, Tkinter/CTk ignore le scaling DPI de Windows et le système agrandit
# l'image bitmap résultante (interface floue et "trop zoomée" sur écrans
# >100% d'échelle). On déclare l'appli "DPI aware" puis on aligne le scaling
# CTk sur le scaling réel de l'écran pour avoir une taille nette et correcte.
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
# On laisse CustomTkinter détecter automatiquement l'échelle Windows de
# chaque PC (100%, 125%, 150%...) maintenant que l'appli est DPI aware —
# forcer une valeur fixe ici rendait l'interface trop petite ou trop grande
# selon l'échelle d'affichage configurée chez l'utilisateur.


# ── Helpers ───────────────────────────────────────────────────────────────────

def write_log(tag, _=None):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.datetime.now()}] {tag}\n")
        f.write(traceback.format_exc())
        f.write("=" * 80 + "\n\n")

def installed_ids():
    d = MC_DIR / "versions"
    if not d.exists(): return set()
    return {x.name for x in d.iterdir() if x.is_dir() and (x/f"{x.name}.json").exists()}

def open_in_file_manager(path):
    """Ouvre un dossier dans l'explorateur de fichiers natif, quel que soit
    l'OS (Windows/macOS/Linux) — auparavant codé en dur avec 'explorer',
    qui ne fonctionne que sous Windows."""
    p = str(path)
    try:
        if sys.platform == "win32":
            subprocess.Popen(f'explorer "{p}"')
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            subprocess.Popen(["xdg-open", p])
    except Exception as e:
        write_log("Ouverture dossier", e)

def ensure_profiles():
    p = MC_DIR / "launcher_profiles.json"
    if not p.exists():
        p.write_text(json.dumps({"profiles":{}, "settings":{}, "version":3}, indent=2), "utf-8")

def make_cb(bar, lbl, root):
    _m = [100]
    def ss(t): root.after(0, lambda: lbl.configure(text=t))
    def sp(v): root.after(0, lambda: bar.set(v/_m[0] if _m[0] else 0))
    def sm(m): _m[0] = m if m>0 else 1
    return {"setStatus":ss,"setProgress":sp,"setMax":sm}

def ping_host(host="1.1.1.1", port=53, timeout=1):
    try:
        t = datetime.datetime.now()
        socket.setdefaulttimeout(timeout)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, port)); s.close()
        return int((datetime.datetime.now()-t).total_seconds()*1000)
    except: return None

def aikar_jvm_flags(ram_mb):
    """Flags JVM 'Aikar' — référence dans la communauté Minecraft pour
    réduire les freezes/lags liés au garbage collector, adaptés à la RAM
    allouée (en dessous de 12 Go le G1 region size est plus petit).

    Deux ajustements par rapport aux flags Aikar "stricts", pour que le jeu
    démarre vite sans pénaliser le jeu une fois lancé :
    - Xms plus petit que Xmx : la JVM alloue/commit un tas réduit au
      démarrage et grandit ensuite à la demande, au lieu de réserver tout
      le tas (ex. 12 Go) avant même de charger Minecraft.
    - Pas d'AlwaysPreTouch : ce flag force la JVM à toucher (mettre à zéro)
      chaque page mémoire du tas dès le lancement — avec une grosse RAM
      allouée ça ajoute plusieurs secondes avant que le jeu démarre. On
      perd un peu de perf en tout début de partie (premiers GC) contre un
      lancement nettement plus rapide.
    """
    region   = "4M" if ram_mb < 12288 else "8M"
    xms_mb   = min(2048, max(1024, ram_mb // 4))
    return [
        f"-Xms{xms_mb}m", f"-Xmx{ram_mb}m",
        "-XX:+UseG1GC", "-XX:+ParallelRefProcEnabled",
        "-XX:MaxGCPauseMillis=200", "-XX:+UnlockExperimentalVMOptions",
        "-XX:+DisableExplicitGC",
        "-XX:G1NewSizePercent=30", "-XX:G1MaxNewSizePercent=40",
        "-XX:G1HeapRegionSize=" + region, "-XX:G1ReservePercent=20",
        "-XX:G1HeapWastePercent=5", "-XX:G1MixedGCCountTarget=4",
        "-XX:InitiatingHeapOccupancyPercent=15",
        "-XX:G1MixedGCLiveThresholdPercent=90",
        "-XX:G1RSetUpdatingPauseTimePercent=5",
        "-XX:SurvivorRatio=32", "-XX:MaxTenuringThreshold=1",
        "-XX:CICompilerCount=2",
        "-Dusing.aikars.flags=https://mcflags.emc.gs",
        "-Dfile.encoding=UTF-8",
    ]

def boost_process_priority(pid, level="high"):
    """Donne au process Minecraft une priorité CPU plus élevée que les
    autres applications, pour réduire les micro-freezes pendant le jeu."""
    try:
        import psutil
        p = psutil.Process(pid)
        if sys.platform == "win32":
            cls = {
                "high": psutil.HIGH_PRIORITY_CLASS,
                "above": psutil.ABOVE_NORMAL_PRIORITY_CLASS,
                "normal": psutil.NORMAL_PRIORITY_CLASS,
            }.get(level, psutil.HIGH_PRIORITY_CLASS)
            p.nice(cls)
        else:
            p.nice({"high": -10, "above": -5}.get(level, 0))
        return True
    except Exception:
        return False

def trim_own_memory():
    """Libère la mémoire inutilisée du process DU LAUNCHER lui-même (jamais
    celle d'un autre process, donc sans risque pour le jeu ou le système).
    Sur Windows, SetProcessWorkingSetSize(-1,...) ne s'applique qu'au
    process appelant — c'est l'équivalent d'un "trim" mémoire local."""
    try:
        import gc
        gc.collect()
        if sys.platform == "win32":
            import ctypes
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            ctypes.windll.psapi.EmptyWorkingSet(handle)
        return True
    except Exception:
        return False


def get_ram_usage():
    try:
        import psutil
        m = psutil.virtual_memory()
        return round(m.used/1e9,1), round(m.total/1e9,1)
    except:
        return None, None


# ── Custom widgets ────────────────────────────────────────────────────────────

class NavBtn(ctk.CTkButton):
    def __init__(self, parent, text, icon="", command=None, **kw):
        super().__init__(parent,
            text=f"  {icon}  {text}",
            anchor="w", height=40, corner_radius=8,
            fg_color="transparent", hover_color=ACT_BG,
            text_color=TEXT2, font=ctk.CTkFont(size=14),
            command=command, **kw)
        self._active = False

    def set_active(self, active):
        self._active = active
        if active:
            self.configure(fg_color=ACT_BG, text_color=TEXT,
                           font=ctk.CTkFont(size=14, weight="bold"))
        else:
            self.configure(fg_color="transparent", text_color=TEXT2,
                           font=ctk.CTkFont(size=14))

class Card(ctk.CTkFrame):
    def __init__(self, parent, title="", **kw):
        super().__init__(parent, fg_color=CARD, corner_radius=10,
                         border_width=1, border_color=BORDER, **kw)
        if title:
            ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=TEXT2).pack(anchor="w", padx=12, pady=(10,4))

class StatusDot(ctk.CTkLabel):
    def __init__(self, parent, text, color=GREEN):
        super().__init__(parent, text=f"● {text}",
                         text_color=color, font=ctk.CTkFont(size=12))

class StatRow(ctk.CTkFrame):
    def __init__(self, parent, label, value="--", color=TEXT):
        super().__init__(parent, fg_color="transparent")
        ctk.CTkLabel(self, text=label, text_color=TEXT2,
                     font=ctk.CTkFont(size=12)).pack(side="left")
        self._val = ctk.CTkLabel(self, text=value, text_color=color,
                                  font=ctk.CTkFont(size=12, weight="bold"))
        self._val.pack(side="right")
    def set(self, v, color=None):
        self._val.configure(text=str(v))
        if color: self._val.configure(text_color=color)


# ══════════════════════════════════════════════════════════════════════════════
# Main App
# ══════════════════════════════════════════════════════════════════════════════

class SakuraLauncher:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("Sakura Launcher")
        self._set_window_icon()
        self.root.geometry("1280x780")
        self.root.minsize(1100, 680)
        self.root.configure(fg_color=BG)
        self.root.resizable(True, True)
        # Ouvre maximisé pour que tout le contenu (nouveaux onglets inclus)
        # soit visible sans avoir à agrandir manuellement la fenêtre.
        try:
            if sys.platform == "win32":
                self.root.state("zoomed")
            else:
                self.root.attributes("-zoomed", True)
        except Exception:
            pass

        self._cfg          = self._load_config()
        self.username      = tk.StringVar(value=self._cfg.get("username", ""))
        self._skin_path    = tk.StringVar(value=self._cfg.get("skin_path", ""))
        self.ram_mb        = tk.IntVar(value=6144)
        self.selected_id   = tk.StringVar(value="")
        self.loader_var    = tk.StringVar(value="Fabric")
        self.loader_mc     = tk.StringVar(value="1.21.1")
        self.loader_ver    = tk.StringVar(value="(dernière stable)")
        self.neo_mc        = tk.StringVar(value="1.21.1")
        self.neo_ver       = tk.StringVar(value="")
        self.boost_active  = tk.BooleanVar(value=True)
        self.auto_opt      = tk.BooleanVar(value=True)
        self.close_on_launch = tk.BooleanVar(value=False)
        self.check_updates = tk.BooleanVar(value=True)
        self.server_url    = tk.StringVar(value=self._cfg.get("server_url",""))
        self._all_versions = []
        self._installed    = set()
        self._logs         = []
        self._nav_btns     = {}
        self._pages        = {}
        self._current_page = ""
        self._skin_angle   = 0
        self._auto_rotate  = False
        self._auto_rotate_id = None

        self._rpc = None
        self._rpc_start = int(time.time())
        self._mc_pid       = None
        self._is_admin     = False
        self._announcement_seen_at = 0.0
        self._is_minimized = False
        self._stats        = load_stats()
        self._trophies      = load_trophies()
        self._ms_account    = self._cfg.get("ms_account")  # {name, uuid, access_token, refresh_token}
        self._build_ui()
        self._show_page("accueil")
        # Coupe les sondages réseau non essentiels (liste des joueurs en
        # ligne, vérif de mise à jour, annonces) quand la fenêtre est
        # minimisée : personne ne les regarde à ce moment, ça économise du
        # CPU/réseau en continu sans rien changer de visible. Le heartbeat
        # (pour que les autres te voient toujours en ligne) continue.
        self.root.bind("<Unmap>", self._on_window_state_change)
        self.root.bind("<Map>", self._on_window_state_change)
        self._load_versions()
        self._start_stat_loop()
        self._init_rpc()
        self._start_presence_loops()
        self._start_background_optimizer()
        self.root.after(3000, self._scan_minecraft_advancements)
        self.username.trace_add("write", lambda *_: self._save_config())
        self.server_url.trace_add("write", lambda *_: self._save_config())

    def _set_window_icon(self):
        """Icône de fenêtre/taskbar, cross-platform via icon.png (PhotoImage
        marche partout, contrairement à iconbitmap qui n'accepte un .ico
        que sur Windows). Échec silencieux si le fichier n'est pas trouvé
        (ex: build sans l'icône embarquée) — pas bloquant pour l'app."""
        try:
            from PIL import Image, ImageTk
            png_path = resource_path("icon.png")
            if png_path.exists():
                img = Image.open(png_path)
                self._icon_photo = ImageTk.PhotoImage(img)  # garder une réf
                self.root.iconphoto(True, self._icon_photo)
        except Exception:
            pass

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Sidebar
        self._sidebar = ctk.CTkFrame(self.root, width=220, fg_color=SIDE,
                                      corner_radius=0)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)
        self._build_sidebar()

        # Main
        self._main = ctk.CTkFrame(self.root, fg_color=BG, corner_radius=0)
        self._main.pack(side="right", fill="both", expand=True)

        # Construction paresseuse : seule la page "accueil" est construite
        # immédiatement (premier affichage). Les autres ne sont construites
        # qu'à la première visite — ça évite de payer le coût de 9 pages
        # (rendu skin PIL, listing mods, etc.) au démarrage sur les PC lents.
        self._page_builders = {
            "accueil":      self._page_accueil,
            "jouer":        self._page_jouer,
            "mods":         self._page_mods,
            "ressource":    self._page_ressource,
            "shaders":      self._page_shaders,
            "classement":   self._page_classement,
            "optimisation": self._page_optimisation,
            "reseau":       self._page_reseau,
            "parametres":   self._page_parametres,
            "skin":         self._page_skin,
            "logs":         self._page_logs,
        }
        self._ensure_page_built("accueil")

    def _ensure_page_built(self, name):
        if name in self._pages:
            return self._pages[name]
        f = ctk.CTkFrame(self._main, fg_color=BG, corner_radius=0)
        f.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._page_builders[name](f)
        self._pages[name] = f
        return f

    def _build_sidebar(self):
        # Logo
        logo = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        logo.pack(fill="x", padx=16, pady=(20,8))
        ctk.CTkFrame(logo, width=36, height=36, corner_radius=8,
                     fg_color=ACCENT).pack(side="left")
        txt = ctk.CTkFrame(logo, fg_color="transparent")
        txt.pack(side="left", padx=10)
        ctk.CTkLabel(txt, text="Sakura", font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(txt, text="LAUNCHER", font=ctk.CTkFont(size=10),
                     text_color=TEXT2).pack(anchor="w")
        ctk.CTkLabel(self._sidebar, text="NEOFORGE EDITION",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=ACCENT).pack(anchor="w", padx=16, pady=(0,2))
        ctk.CTkLabel(self._sidebar, text=f"v{APP_VERSION}",
                     font=ctk.CTkFont(size=9),
                     text_color=TEXT3).pack(anchor="w", padx=16, pady=(0,16))

        ctk.CTkFrame(self._sidebar, height=1, fg_color=BORDER).pack(fill="x", padx=12)

        nav_items = [
            ("accueil",      "⌂",  "Accueil"),
            ("jouer",        "▶",  "Jouer"),
            ("mods",         "⚙",  "Mods"),
            ("ressource",    "🖼", "Ressource Packs"),
            ("shaders",      "✨", "Shaderpacks"),
            ("classement",   "🏆", "Classement"),
            ("optimisation", "⚡", "Optimisation"),
            ("reseau",       "🌐", "Réseau"),
            ("parametres",   "⚙",  "Paramètres"),
            ("skin",         "👤", "Skin & Profil"),
            ("logs",         "📋", "Logs"),
        ]
        nav_frame = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        nav_frame.pack(fill="x", padx=8, pady=8)
        for key, icon, label in nav_items:
            btn = NavBtn(nav_frame, label, icon,
                         command=lambda k=key: self._show_page(k))
            btn.pack(fill="x", pady=2)
            self._nav_btns[key] = btn

        # Bloc bas (système / boost / utilisateurs / discord) dans une zone
        # scrollable : sur un petit écran ou une fenêtre non maximisée, rien
        # n'est jamais coupé ou invisible — on peut toujours faire défiler.
        bottom = ctk.CTkScrollableFrame(self._sidebar, fg_color="transparent",
                                         scrollbar_button_color=CARD2)
        bottom.pack(fill="both", expand=True)

        # System info
        ctk.CTkFrame(bottom, height=1, fg_color=BORDER).pack(fill="x", padx=4)
        sys_frame = ctk.CTkFrame(bottom, fg_color="transparent")
        sys_frame.pack(fill="x", padx=10, pady=12)
        ctk.CTkLabel(sys_frame, text="SYSTÈME", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=TEXT3).pack(anchor="w")
        import platform
        ram_total = "?"
        try:
            import psutil; ram_total = f"{round(psutil.virtual_memory().total/1e9)} GB"
        except: pass
        self._sys_val_lbls = {}
        for label, val in [
            ("CPU", platform.processor()[:20] or "..."),
            ("RAM", ram_total),
            ("OS",  platform.system()+" "+platform.release()),
        ]:
            r = ctk.CTkFrame(sys_frame, fg_color="transparent")
            r.pack(fill="x", pady=1)
            ctk.CTkLabel(r, text=label, text_color=TEXT3,
                         font=ctk.CTkFont(size=11)).pack(side="left")
            vl = ctk.CTkLabel(r, text=val, text_color=TEXT2,
                               font=ctk.CTkFont(size=11))
            vl.pack(side="right")
            self._sys_val_lbls[label] = vl

        # cpuinfo.get_cpu_info() lance un sous-process (WMIC sur Windows) qui
        # peut prendre 1-2 secondes : on l'exécute en arrière-plan pour ne
        # jamais retarder l'affichage de la fenêtre au démarrage.
        def fetch_cpu_name():
            try:
                import cpuinfo
                name = cpuinfo.get_cpu_info().get("brand_raw", "")[:22]
                if name:
                    self.root.after(0, lambda: self._sys_val_lbls["CPU"].configure(text=name[:20]))
            except Exception:
                pass
        threading.Thread(target=fetch_cpu_name, daemon=True).start()

        # Boost
        ctk.CTkFrame(bottom, height=1, fg_color=BORDER).pack(fill="x", padx=4)
        boost = ctk.CTkFrame(bottom, fg_color="transparent")
        boost.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(boost, text="BOOST STATUS", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=TEXT3).pack(anchor="w")
        self._boost_lbl = StatusDot(boost, "Sakura Mode: ACTIVÉ", GREEN)
        self._boost_lbl.pack(anchor="w", pady=2)
        ctk.CTkButton(boost, text="Désactiver le Boost", height=28,
                      fg_color=CARD2, hover_color=CARD,
                      text_color=TEXT2, font=ctk.CTkFont(size=11),
                      command=self._toggle_boost).pack(fill="x", pady=4)

        # Compteur d'utilisateurs du panel (local à ce poste)
        ctk.CTkFrame(bottom, height=1, fg_color=BORDER).pack(fill="x", padx=4)
        users_frame = ctk.CTkFrame(bottom, fg_color="transparent")
        users_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(users_frame, text="UTILISATEURS DU PANEL",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=TEXT3).pack(anchor="w")
        self._users_count_lbl = ctk.CTkLabel(
            users_frame,
            text=f"👤 {len(self._stats['users'])} joueur(s) · {self._stats['launches']} lancement(s)",
            font=ctk.CTkFont(size=11), text_color=ACCENT2, wraplength=170, justify="left")
        self._users_count_lbl.pack(anchor="w", pady=2)

        # Badge de mise à jour disponible (caché par défaut, affiché par
        # _update_version_check_ui si le serveur de présence annonce une
        # version plus récente que APP_VERSION).
        self._update_badge = ctk.CTkButton(
            users_frame, text="", height=26, fg_color=ORANGE, hover_color="#c98000",
            text_color="#1a1200", font=ctk.CTkFont(size=11, weight="bold"),
            command=self._open_update_url)
        self._update_download_url = None

        # Support Discord
        ctk.CTkFrame(bottom, height=1, fg_color=BORDER).pack(fill="x", padx=4)
        disc_frame = ctk.CTkFrame(bottom, fg_color="transparent")
        disc_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(disc_frame, text="💬  Support Discord", height=32,
                      fg_color="#5865F2", hover_color="#4752c4",
                      font=ctk.CTkFont(size=12, weight="bold"),
                      command=self._open_discord_support).pack(fill="x")

    def _open_discord_support(self):
        import webbrowser
        webbrowser.open(DISCORD_SUPPORT_URL)
        self._add_log("Lien Discord support ouvert")

    def _show_page(self, key):
        self._ensure_page_built(key)
        for k, f in self._pages.items():
            f.lower()
        self._pages[key].lift()
        for k, b in self._nav_btns.items():
            b.set_active(k == key)
        self._current_page = key

    def _on_window_state_change(self, event):
        if event.widget is not self.root:
            return  # <Unmap>/<Map> se propagent aussi depuis des widgets enfants
        try:
            self._is_minimized = bool(self.root.state() == "iconic")
        except Exception:
            pass

    def _toggle_boost(self):
        self.boost_active.set(not self.boost_active.get())
        if self.boost_active.get():
            self._boost_lbl.configure(text="● Sakura Mode: ACTIVÉ", text_color=GREEN)
        else:
            self._boost_lbl.configure(text="● Sakura Mode: DÉSACTIVÉ", text_color=RED_C)
        self._add_log("Boost " + ("activé" if self.boost_active.get() else "désactivé"))

    # ── ACCUEIL ───────────────────────────────────────────────────────────────

    def _page_accueil(self, f):
        scroll = ctk.CTkScrollableFrame(f, fg_color=BG, scrollbar_button_color=CARD2)
        scroll.pack(fill="both", expand=True)

        # Bannière d'annonce admin (cachée par défaut, affichée par
        # _update_announcement_ui si un admin diffuse un message via
        # /announce sur le serveur de présence).
        self._announcement_banner = ctk.CTkLabel(
            scroll, text="", fg_color=ACT_BG, corner_radius=8,
            text_color=TEXT, font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w", height=36)

        # Hero
        hero = ctk.CTkFrame(scroll, fg_color="#0a0814", corner_radius=14,
                             border_width=1, border_color=BORDER, height=190)
        hero.pack(fill="x", padx=20, pady=(16,10))
        hero.pack_propagate(False)
        self._accueil_hero = hero

        # Stars decoration on hero
        stars = ctk.CTkCanvas(hero, bg="#0a0814", highlightthickness=0, height=190)
        stars.place(relx=0, rely=0, relwidth=1, relheight=1)
        import random; random.seed(42)
        for _ in range(80):
            x = random.randint(0,1000); y = random.randint(0,190)
            r = random.choice([1,1,1,2])
            stars.create_oval(x,y,x+r,y+r, fill="#c8b8ff", outline="")
        # Castle silhouettes
        for cx, h in [(180,60),(210,80),(240,65),(300,55),(330,75),(350,58),(410,62),(440,80)]:
            stars.create_rectangle(cx, 190-h, cx+10, 190, fill="#110f2a", outline="")
            stars.create_rectangle(cx-2, 190-h-6, cx+12, 190-h, fill="#14122e", outline="")
        # Fog
        stars.create_rectangle(0,160,1000,190, fill="#0c0a1e", outline="", stipple="gray50")

        hero_txt = ctk.CTkFrame(hero, fg_color="transparent")
        hero_txt.place(x=28, y=28)
        ctk.CTkLabel(hero_txt, text="Bienvenue dans",
                     font=ctk.CTkFont(size=15), text_color=TEXT2).pack(anchor="w")
        ctk.CTkLabel(hero_txt, text="Sakura Launcher",
                     font=ctk.CTkFont(size=32, weight="bold"),
                     text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(hero_txt, text="Sakura — Le launcher ultime pour NeoForge, Fabric, Quilt et Forge.",
                     font=ctk.CTkFont(size=12), text_color=TEXT3).pack(anchor="w", pady=(2,10))
        ctk.CTkButton(hero_txt, text="▶  Jouer à Minecraft", height=38, width=180,
                      fg_color=ACCENT, hover_color="#6d28d9",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=self._launch_current).pack(anchor="w")

        # Version selector (top-right of hero)
        ver_sel = ctk.CTkFrame(hero, fg_color=CARD2, corner_radius=8)
        ver_sel.place(relx=1, rely=1, x=-16, y=-16, anchor="se")
        ctk.CTkLabel(ver_sel, text="Version sélectionnée",
                     font=ctk.CTkFont(size=10), text_color=TEXT3).pack(padx=12, pady=(6,2))
        self._hero_ver_combo = ctk.CTkComboBox(ver_sel, variable=self.selected_id,
                                                values=["Chargement..."], width=180,
                                                fg_color=CARD, border_color=BORDER,
                                                button_color=ACCENT,
                                                font=ctk.CTkFont(size=12))
        self._hero_ver_combo.pack(padx=10, pady=(0,8))

        # Quick tools + realtime row
        row1 = ctk.CTkFrame(scroll, fg_color="transparent")
        row1.pack(fill="x", padx=20, pady=(0,8))

        # Outils rapides
        tools_card = Card(row1, "OUTILS RAPIDES")
        tools_card.pack(side="left", fill="both", expand=True, padx=(0,8))
        t_row = ctk.CTkFrame(tools_card, fg_color="transparent")
        t_row.pack(padx=10, pady=(0,12))
        for icon, label, cmd in [
            ("⚡","Optimisation", lambda: self._show_page("optimisation")),
            ("🗑","Nettoyer\nle Cache", self._clear_cache),
            ("⚙","Générateur\nJVM", lambda: self._show_page("optimisation")),
            ("📁","Ouvrir le\nDossier", self._open_mods),
        ]:
            b = ctk.CTkFrame(t_row, fg_color=CARD2, corner_radius=10, width=90, height=72)
            b.pack(side="left", padx=5)
            b.pack_propagate(False)
            ctk.CTkLabel(b, text=icon, font=ctk.CTkFont(size=22)).pack(pady=(10,2))
            ctk.CTkLabel(b, text=label, font=ctk.CTkFont(size=10),
                         text_color=TEXT2, justify="center").pack()
            b.bind("<Button-1>", lambda e, c=cmd: c())
            b.bind("<Enter>",    lambda e, w=b: w.configure(fg_color=ACT_BG))
            b.bind("<Leave>",    lambda e, w=b: w.configure(fg_color=CARD2))

        # Statut temps réel
        rt_card = Card(row1, "STATUT EN TEMPS RÉEL")
        rt_card.pack(side="right", fill="y", ipadx=6)
        self._stat_fps  = StatRow(rt_card, "FPS");         self._stat_fps.pack(fill="x", padx=12, pady=2)
        self._stat_ram  = StatRow(rt_card, "RAM Utilisée"); self._stat_ram.pack(fill="x", padx=12, pady=2)
        self._stat_ping = StatRow(rt_card, "Ping", color=GREEN); self._stat_ping.pack(fill="x", padx=12, pady=2)
        self._stat_tps  = StatRow(rt_card, "TPS (Serveur)"); self._stat_tps.pack(fill="x", padx=12, pady=(2,12))

        # Big row: Optimisation / JVM / Réseau / Mods
        row2 = ctk.CTkFrame(scroll, fg_color="transparent")
        row2.pack(fill="x", padx=20, pady=(0,8))

        # Optimisation système
        opt_c = Card(row2, "OPTIMISATION SYSTÈME")
        opt_c.pack(side="left", fill="both", expand=True, padx=(0,6))
        self._opt_rows = {}
        for lbl, val, col in [
            ("Mode Performance","Activé", GREEN),
            ("Priorité CPU","Haute", GREEN),
            ("Nettoyage RAM","Activé", GREEN),
            ("Optimisation Réseau","Activé", GREEN),
            ("Réduction Latence","Activé", GREEN),
            ("Boost GPU","Activé", GREEN),
        ]:
            r = StatRow(opt_c, lbl, val, col)
            r.pack(fill="x", padx=12, pady=1)
            self._opt_rows[lbl] = r
        ctk.CTkButton(opt_c, text="Tout Optimiser", height=32, fg_color=GREEN,
                      hover_color="#059669", text_color="#000",
                      font=ctk.CTkFont(size=12, weight="bold"),
                      command=self._do_optimize).pack(fill="x", padx=12, pady=10)

        # Générateur JVM
        jvm_c = Card(row2, "GÉNÉRATEUR JVM")
        jvm_c.pack(side="left", fill="both", expand=True, padx=(0,6))
        ctk.CTkLabel(jvm_c, text="RAM Allouée :", text_color=TEXT2,
                     font=ctk.CTkFont(size=12)).pack(anchor="w", padx=12)
        self._ram_lbl = ctk.CTkLabel(jvm_c, text=f"{self.ram_mb.get()} MB",
                                      font=ctk.CTkFont(size=13, weight="bold"),
                                      text_color=ACCENT)
        self._ram_lbl.pack(anchor="w", padx=12)
        sl = ctk.CTkSlider(jvm_c, from_=1024, to=16384, variable=self.ram_mb,
                           progress_color=ACCENT, button_color=ACCENT2,
                           command=lambda v: self._ram_lbl.configure(text=f"{int(v)} MB"))
        sl.pack(fill="x", padx=12, pady=4)
        row_sl = ctk.CTkFrame(jvm_c, fg_color="transparent")
        row_sl.pack(fill="x", padx=12)
        ctk.CTkLabel(row_sl, text="1024 MB", text_color=TEXT3, font=ctk.CTkFont(size=10)).pack(side="left")
        ctk.CTkLabel(row_sl, text="16384 MB", text_color=TEXT3, font=ctk.CTkFont(size=10)).pack(side="right")
        ctk.CTkLabel(jvm_c, text="Aperçu JVM :", text_color=TEXT2,
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12, pady=(6,2))
        self._jvm_preview = ctk.CTkLabel(jvm_c,
            text="-Xms2048m -Xmx6144m\n-XX:+UseG1GC\n-XX:+UnlockExperimentalVMOptions\n-XX:+ParallelRefProcEnabled",
            font=ctk.CTkFont(size=10, family="Courier"),
            text_color=CYAN, justify="left")
        self._jvm_preview.pack(anchor="w", padx=12, pady=(0,4))
        ctk.CTkButton(jvm_c, text="Appliquer", height=32, fg_color=ACCENT,
                      hover_color="#6d28d9", font=ctk.CTkFont(size=12),
                      command=self._apply_jvm).pack(fill="x", padx=12, pady=8)

        # Réseau
        net_c = Card(row2, "RÉSEAU")
        net_c.pack(side="left", fill="both", expand=True, padx=(0,6))
        ctk.CTkLabel(net_c, text="DNS Actuel", text_color=TEXT2,
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12)
        self._dns_lbl = ctk.CTkLabel(net_c, text="Cloudflare (1.1.1.1)",
                                      text_color=GREEN, font=ctk.CTkFont(size=12, weight="bold"))
        self._dns_lbl.pack(anchor="w", padx=12, pady=(0,6))
        ctk.CTkLabel(net_c, text="Changer de DNS", text_color=TEXT2,
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12)
        self._dns_combo = ctk.CTkComboBox(net_c,
            values=["Cloudflare (1.1.1.1)","Google (8.8.8.8)","OpenDNS (208.67.222.222)"],
            fg_color=CARD2, border_color=BORDER, button_color=ACCENT, width=200)
        self._dns_combo.pack(padx=12, pady=4)
        ctk.CTkButton(net_c, text="Appliquer", height=28, fg_color=ACCENT,
                      hover_color="#6d28d9", font=ctk.CTkFont(size=11),
                      command=self._apply_dns).pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(net_c, text="Ping du Serveur", text_color=TEXT2,
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12, pady=(8,2))
        ping_row = ctk.CTkFrame(net_c, fg_color="transparent")
        ping_row.pack(fill="x", padx=12)
        self._ping_entry = ctk.CTkEntry(ping_row, placeholder_text="play.example.com",
                                         width=130, height=28, fg_color=CARD2, border_color=BORDER)
        self._ping_entry.pack(side="left", padx=(0,4))
        ctk.CTkButton(ping_row, text="Tester", height=28, width=70, fg_color=CARD2,
                      border_color=BORDER, border_width=1, text_color=TEXT2,
                      command=self._test_ping).pack(side="left")
        self._ping_result = ctk.CTkLabel(net_c, text="", text_color=GREEN,
                                          font=ctk.CTkFont(size=11))
        self._ping_result.pack(anchor="w", padx=12, pady=4)

        # Mods NeoForge
        mods_c = Card(row2, "MODS NEOFORGE")
        mods_c.pack(side="right", fill="both", expand=True)
        self._mod_search = ctk.CTkEntry(mods_c, placeholder_text="Rechercher un mod...",
                                         height=28, fg_color=CARD2, border_color=BORDER)
        self._mod_search.pack(fill="x", padx=12, pady=4)
        self._mod_search.bind("<KeyRelease>", lambda e: self._refresh_mods_list())
        self._mods_scroll = ctk.CTkScrollableFrame(mods_c, fg_color="transparent", height=110)
        self._mods_scroll.pack(fill="x", padx=12)
        self._refresh_mods_list()
        mod_btn_row = ctk.CTkFrame(mods_c, fg_color="transparent")
        mod_btn_row.pack(fill="x", padx=12, pady=6)
        ctk.CTkButton(mod_btn_row, text="Ouvrir Dossier Mods", height=28, width=140,
                      fg_color=CARD2, border_color=BORDER, border_width=1,
                      text_color=TEXT2, font=ctk.CTkFont(size=11),
                      command=self._open_mods).pack(side="left", padx=(0,4))
        ctk.CTkButton(mod_btn_row, text="Actualiser", height=28, width=90,
                      fg_color=CARD2, border_color=BORDER, border_width=1,
                      text_color=TEXT2, font=ctk.CTkFont(size=11),
                      command=self._refresh_mods_list).pack(side="left")

        # Bottom row: Logs / Options de lancement / Sakura Mode
        row3 = ctk.CTkFrame(scroll, fg_color="transparent")
        row3.pack(fill="x", padx=20, pady=(0,16))

        logs_c = Card(row3, "DERNIERS LOGS")
        logs_c.pack(side="left", fill="both", expand=True, padx=(0,8))
        self._accueil_log = ctk.CTkTextbox(logs_c, height=100, fg_color=CARD2,
                                            text_color=CYAN, font=ctk.CTkFont(size=11, family="Courier"),
                                            state="disabled")
        self._accueil_log.pack(fill="x", padx=12, pady=(0,10))

        opt_launch = Card(row3, "OPTIONS DE LANCEMENT")
        opt_launch.pack(side="left", fill="y", padx=(0,8))
        for text, var in [
            ("Lancer après optimisation", self.auto_opt),
            ("Fermer launcher au lancement", self.close_on_launch),
            ("Vérifier les mises à jour", self.check_updates),
        ]:
            ctk.CTkSwitch(opt_launch, text=text, variable=var,
                          progress_color=ACCENT, button_color=ACCENT2,
                          font=ctk.CTkFont(size=12), text_color=TEXT2).pack(
                          anchor="w", padx=12, pady=3)
        ctk.CTkFrame(opt_launch, fg_color="transparent", height=8).pack()

        # Sakura mode card
        ss_card = Card(row3)
        ss_card.pack(side="right", fill="y")
        ctk.CTkLabel(ss_card, text="⚡", font=ctk.CTkFont(size=30)).pack(pady=(14,2))
        ctk.CTkLabel(ss_card, text="SUPERSONIC MODE",
                     font=ctk.CTkFont(size=12, weight="bold"), text_color=TEXT2).pack()
        self._ss_mode_lbl = ctk.CTkLabel(ss_card, text="ACTIVÉ",
                                          font=ctk.CTkFont(size=20, weight="bold"),
                                          text_color=GREEN)
        self._ss_mode_lbl.pack()
        ctk.CTkLabel(ss_card, text="Ton expérience est optimisée au maximum !",
                     font=ctk.CTkFont(size=10), text_color=TEXT3, wraplength=160).pack(pady=(2,14))

    # ── JOUER ─────────────────────────────────────────────────────────────────

    def _page_jouer(self, f):
        ctk.CTkLabel(f, text="Jouer", font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=24, pady=(18,4))

        main = ctk.CTkFrame(f, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=24, pady=8)

        # Left: version list
        left = ctk.CTkFrame(main, fg_color=CARD, corner_radius=10,
                            border_width=1, border_color=BORDER, width=320)
        left.pack(side="left", fill="y", padx=(0,12))
        left.pack_propagate(False)

        tp = ctk.CTkFrame(left, fg_color="transparent")
        tp.pack(fill="x", padx=10, pady=8)
        self._jver_count = ctk.CTkLabel(tp, text="Chargement...",
                                         font=ctk.CTkFont(size=14, weight="bold"), text_color=TEXT)
        self._jver_count.pack(side="left")
        ctk.CTkButton(tp, text="⟳", width=28, height=28, fg_color=CARD2,
                      command=self._load_versions).pack(side="right")

        se = ctk.CTkEntry(left, placeholder_text="Rechercher...", height=30,
                          fg_color=CARD2, border_color=BORDER)
        se.pack(fill="x", padx=10, pady=(0,4))
        self._jsearch = se
        se.bind("<KeyRelease>", lambda e: self._pop_versions())

        fr = ctk.CTkFrame(left, fg_color="transparent")
        fr.pack(fill="x", padx=10, pady=(0,4))
        self._jshow_rel  = tk.BooleanVar(value=True)
        self._jshow_snap = tk.BooleanVar(value=False)
        self._jshow_old  = tk.BooleanVar(value=False)
        for t, v in [("Release",self._jshow_rel),("Snapshot",self._jshow_snap),("Ancien",self._jshow_old)]:
            ctk.CTkCheckBox(fr, text=t, variable=v, command=self._pop_versions,
                            width=76, height=22, font=ctk.CTkFont(size=11),
                            checkmark_color=TEXT, fg_color=ACCENT).pack(side="left")

        self._jver_scroll = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self._jver_scroll.pack(fill="both", expand=True, padx=10, pady=(0,10))

        # Right: launch panel (scrollable so nothing is hidden on small screens)
        right_wrap = ctk.CTkFrame(main, fg_color="transparent")
        right_wrap.pack(side="right", fill="both", expand=True)
        right = ctk.CTkScrollableFrame(right_wrap, fg_color="transparent")
        right.pack(fill="both", expand=True)

        sel_card = Card(right)
        sel_card.pack(fill="x", pady=(0,10))
        ctk.CTkLabel(sel_card, text="Version sélectionnée",
                     text_color=TEXT2, font=ctk.CTkFont(size=12)).pack(pady=(14,2))
        ctk.CTkLabel(sel_card, textvariable=self.selected_id,
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=ACCENT).pack(pady=(0,14))

        cfg = Card(right)
        cfg.pack(fill="x", pady=(0,10))
        r1 = ctk.CTkFrame(cfg, fg_color="transparent")
        r1.pack(fill="x", padx=14, pady=8)
        ctk.CTkLabel(r1, text="Pseudo :", font=ctk.CTkFont(size=14), text_color=TEXT2).pack(side="left")
        ctk.CTkEntry(r1, textvariable=self.username, width=180, height=32,
                     fg_color=CARD2, border_color=BORDER).pack(side="right")

        r2 = ctk.CTkFrame(cfg, fg_color="transparent")
        r2.pack(fill="x", padx=14, pady=(0,10))
        ctk.CTkLabel(r2, text="RAM :", font=ctk.CTkFont(size=14), text_color=TEXT2).pack(side="left")
        ctk.CTkComboBox(r2, values=["2048","4096","6144","8192","12288","16384"],
                        variable=tk.StringVar(value=str(self.ram_mb.get())),
                        width=120, fg_color=CARD2, border_color=BORDER,
                        button_color=ACCENT).pack(side="right")

        self._jlaunch_bar = ctk.CTkProgressBar(right, height=14, progress_color=ACCENT)
        self._jlaunch_bar.pack(fill="x", pady=4)
        self._jlaunch_bar.set(0)
        self._jlaunch_st = ctk.CTkLabel(right, text="", text_color=GREEN,
                                         font=ctk.CTkFont(size=12))
        self._jlaunch_st.pack()

        btn_row = ctk.CTkFrame(right, fg_color="transparent")
        btn_row.pack(pady=10)
        ctk.CTkButton(btn_row, text="⬇  Installer", width=140, height=44,
                      fg_color=CARD2, border_color=BORDER, border_width=1,
                      text_color=TEXT, font=ctk.CTkFont(size=13),
                      command=lambda: self._install_ver(self._jlaunch_bar, self._jlaunch_st)
                      ).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="▶  JOUER", width=160, height=44,
                      fg_color=ACCENT, hover_color="#6d28d9",
                      font=ctk.CTkFont(size=15, weight="bold"),
                      command=self._launch_current).pack(side="left", padx=6)

        # Loader install section
        ld_card = Card(right, "INSTALLER UN LOADER")
        ld_card.pack(fill="x", pady=(0,10))
        lr = ctk.CTkFrame(ld_card, fg_color="transparent")
        lr.pack(fill="x", padx=12, pady=6)
        for nm in ["Fabric","Quilt","Forge"]:
            ctk.CTkRadioButton(lr, text=nm, variable=self.loader_var, value=nm,
                               command=self._refresh_loader_vers,
                               fg_color=ACCENT, font=ctk.CTkFont(size=12)
                               ).pack(side="left", padx=10)
        mc_row = ctk.CTkFrame(ld_card, fg_color="transparent")
        mc_row.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(mc_row, text="MC Version :", text_color=TEXT2,
                     font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkEntry(mc_row, textvariable=self.loader_mc, width=100, height=28,
                     fg_color=CARD2, border_color=BORDER).pack(side="left", padx=6)
        ctk.CTkButton(mc_row, text="🔄", width=32, height=28, fg_color=CARD2,
                      command=self._refresh_loader_vers).pack(side="left")
        self._loader_combo = ctk.CTkComboBox(ld_card, variable=self.loader_ver,
                                              values=["(dernière stable)"], width=260,
                                              fg_color=CARD2, border_color=BORDER, button_color=ACCENT)
        self._loader_combo.pack(padx=12, pady=4)
        self._ld_bar = ctk.CTkProgressBar(ld_card, height=12, progress_color=ACCENT)
        self._ld_bar.pack(fill="x", padx=12, pady=2); self._ld_bar.set(0)
        self._ld_st = ctk.CTkLabel(ld_card, text="", text_color=GREEN, font=ctk.CTkFont(size=11))
        self._ld_st.pack()
        ctk.CTkButton(ld_card, text="⬇  Installer le Loader", height=36, width=200,
                      fg_color="#0055cc", hover_color="#0044aa",
                      command=self._install_loader).pack(pady=8)

        # NeoForge section
        neo_c = Card(right, "NEOFORGE — TÉLÉCHARGEMENT AUTO")
        neo_c.pack(fill="x", pady=(0,16))
        nr1 = ctk.CTkFrame(neo_c, fg_color="transparent")
        nr1.pack(fill="x", padx=12, pady=6)
        ctk.CTkLabel(nr1, text="MC :", text_color=TEXT2, font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkEntry(nr1, textvariable=self.neo_mc, width=90, height=28,
                     fg_color=CARD2, border_color=BORDER).pack(side="left", padx=4)
        ctk.CTkButton(nr1, text="🔄 Versions", width=110, height=28, fg_color=CARD2,
                      command=self._load_neo_versions).pack(side="left", padx=4)
        self._neo_combo = ctk.CTkComboBox(neo_c, variable=self.neo_ver,
                                           values=["Clique 🔄 pour charger"], width=260,
                                           fg_color=CARD2, border_color=BORDER, button_color="#cc2222")
        self._neo_combo.pack(padx=12, pady=4)
        self._neo_bar = ctk.CTkProgressBar(neo_c, height=12, progress_color="#cc2222")
        self._neo_bar.pack(fill="x", padx=12, pady=2); self._neo_bar.set(0)
        self._neo_st = ctk.CTkLabel(neo_c, text="", text_color=GREEN, font=ctk.CTkFont(size=11))
        self._neo_st.pack()
        ctk.CTkButton(neo_c, text="⬇  Télécharger et installer NeoForge",
                      height=36, width=270, fg_color="#cc2222", hover_color="#aa1111",
                      font=ctk.CTkFont(size=12, weight="bold"),
                      command=self._install_neoforge).pack(pady=8)

    # ── Helpers glisser-déposer (partagés mods / resourcepacks / shaders) ──────

    def _copy_dropped_files(self, files, dest_dir, exts):
        """Copie dans dest_dir les fichiers déposés dont l'extension est dans
        exts (set, ex {'.jar'}). Retourne (nb_copiés, nb_ignorés)."""
        added, skipped = 0, 0
        for raw in files:
            try:
                path = Path(raw.decode(sys.getfilesystemencoding())) if isinstance(raw, bytes) else Path(raw)
            except Exception:
                path = Path(os.fsdecode(raw))
            if path.suffix.lower() not in exts:
                skipped += 1
                continue
            try:
                shutil.copy2(path, dest_dir / path.name)
                added += 1
            except Exception as e:
                write_log("Drop fichier", e)
                skipped += 1
        return added, skipped

    def _build_drop_label(self, card, kind_desc):
        """Crée le label d'invite (ou d'avertissement, selon dispo de windnd
        et l'OS) au-dessus d'une zone de glisser-déposer."""
        if HAS_DND:
            text, color = f"📥 Glisse des fichiers {kind_desc} ici pour les installer", TEXT2
        elif sys.platform == "win32":
            text = ("⚠ Glisser-déposer indisponible : installe le module avec "
                     "\"pip install windnd\" puis relance le launcher")
            color = ORANGE
        else:
            text = ("⚠ Glisser-déposer indisponible sur cet OS — utilise "
                     "\"📁 Ouvrir dossier\" pour ajouter des fichiers manuellement")
            color = ORANGE
        lbl = ctk.CTkLabel(card, text=text, text_color=color, font=ctk.CTkFont(size=12))
        lbl.pack(anchor="w", padx=12, pady=(0,6))
        return lbl

    def _hook_drop_targets(self, targets, dest_dir, exts, on_complete, kind_label, trophy_id=None):
        """Accroche windnd sur les widgets `targets` : tout fichier déposé
        dont l'extension matche `exts` est copié dans dest_dir, puis
        on_complete() est appelé pour rafraîchir l'UI. Ne fait rien si
        windnd n'est pas dispo (HAS_DND False, ex: hors Windows). Si
        trophy_id est fourni, débloque ce trophée au premier drop réussi."""
        if not HAS_DND:
            return
        def handler(files):
            added, skipped = self._copy_dropped_files(files, dest_dir, exts)
            def upd():
                on_complete()
                msg = f"{added} {kind_label}(s) ajouté(s) par glisser-déposer"
                if skipped: msg += f" ({skipped} fichier(s) ignoré(s))"
                self._add_log(msg)
                if added > 0 and trophy_id:
                    self._unlock_trophy(trophy_id)
            self.root.after(0, upd)
        for t in targets:
            try:
                windnd.hook_dropfiles(t, func=handler)
            except Exception:
                pass

    # ── MODS ──────────────────────────────────────────────────────────────────

    def _page_mods(self, f):
        ctk.CTkLabel(f, text="Mods", font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=24, pady=(18,8))
        card = Card(f)
        card.pack(fill="both", expand=True, padx=24, pady=(0,20))
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=8)
        ctk.CTkButton(top, text="📁 Ouvrir dossier", height=30, width=140,
                      fg_color=CARD2, border_color=BORDER, border_width=1,
                      text_color=TEXT2, command=self._open_mods).pack(side="left", padx=4)
        ctk.CTkButton(top, text="🔄 Actualiser", height=30, width=110,
                      fg_color=CARD2, border_color=BORDER, border_width=1,
                      text_color=TEXT2, command=self._refresh_mods_page).pack(side="left")

        # Zone de glisser-déposer : dépose un ou plusieurs .jar n'importe où
        # dans le cadre ci-dessous pour les copier dans le dossier mods/.
        self._build_drop_label(card, ".jar")

        self._mods_page_scroll = ctk.CTkScrollableFrame(card, fg_color="transparent")
        self._mods_page_scroll.pack(fill="both", expand=True, padx=12, pady=(0,12))
        self._refresh_mods_page()

        self._hook_drop_targets(
            (card, self._mods_page_scroll), MODS_DIR, {".jar"},
            lambda: (self._refresh_mods_page(), self._refresh_mods_list()), "mod",
            trophy_id="mod_dropper")

    def _refresh_mods_page(self):
        for w in self._mods_page_scroll.winfo_children(): w.destroy()
        mods = list(MODS_DIR.glob("*.jar"))
        if not mods:
            ctk.CTkLabel(self._mods_page_scroll,
                         text="Aucun mod trouvé dans le dossier mods/",
                         text_color=TEXT3, font=ctk.CTkFont(size=13)).pack(pady=20)
            return
        for mod in sorted(mods):
            r = ctk.CTkFrame(self._mods_page_scroll, fg_color=CARD2, corner_radius=8)
            r.pack(fill="x", pady=3)
            ctk.CTkLabel(r, text="📦", font=ctk.CTkFont(size=16)).pack(side="left", padx=10, pady=8)
            ctk.CTkLabel(r, text=mod.name, text_color=TEXT,
                         font=ctk.CTkFont(size=13)).pack(side="left")
            size = f"{round(mod.stat().st_size/1024)} KB"
            ctk.CTkLabel(r, text=size, text_color=TEXT3,
                         font=ctk.CTkFont(size=11)).pack(side="right", padx=12)

    # ── RESSOURCE PACKS ───────────────────────────────────────────────────────

    def _page_ressource(self, f):
        ctk.CTkLabel(f, text="Ressource Packs", font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=24, pady=(18,8))
        rp_dir = MC_DIR / "resourcepacks"
        rp_dir.mkdir(exist_ok=True)
        self._rp_dir = rp_dir
        card = Card(f)
        card.pack(fill="both", expand=True, padx=24, pady=(0,20))
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=8)
        ctk.CTkButton(top, text="📁 Ouvrir dossier", height=30, width=140,
                      fg_color=CARD2, border_color=BORDER, border_width=1, text_color=TEXT2,
                      command=lambda: open_in_file_manager(rp_dir)).pack(side="left", padx=4)
        ctk.CTkButton(top, text="🔄 Actualiser", height=30, width=110,
                      fg_color=CARD2, border_color=BORDER, border_width=1,
                      text_color=TEXT2, command=self._refresh_resource_page).pack(side="left")

        self._build_drop_label(card, ".zip")

        self._rp_scroll = ctk.CTkScrollableFrame(card, fg_color="transparent")
        self._rp_scroll.pack(fill="both", expand=True, padx=12, pady=(0,12))
        self._refresh_resource_page()

        self._hook_drop_targets(
            (card, self._rp_scroll), rp_dir, {".zip"},
            self._refresh_resource_page, "resource pack")

    def _refresh_resource_page(self):
        for w in self._rp_scroll.winfo_children(): w.destroy()
        packs = list(self._rp_dir.glob("*.zip")) + list(self._rp_dir.glob("*.jar"))
        if not packs:
            ctk.CTkLabel(self._rp_scroll, text="Aucun resource pack trouvé.",
                         text_color=TEXT3, font=ctk.CTkFont(size=13)).pack(pady=20)
            return
        for p in sorted(packs):
            r = ctk.CTkFrame(self._rp_scroll, fg_color=CARD2, corner_radius=8)
            r.pack(fill="x", pady=3)
            ctk.CTkLabel(r, text="🖼", font=ctk.CTkFont(size=16)).pack(side="left", padx=10, pady=8)
            ctk.CTkLabel(r, text=p.name, text_color=TEXT, font=ctk.CTkFont(size=13)).pack(side="left")
            size = f"{round(p.stat().st_size/1024)} KB"
            ctk.CTkLabel(r, text=size, text_color=TEXT3,
                         font=ctk.CTkFont(size=11)).pack(side="right", padx=12)

    # ── SHADERPACKS ───────────────────────────────────────────────────────────

    def _page_shaders(self, f):
        ctk.CTkLabel(f, text="Shaderpacks", font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=24, pady=(18,8))
        sh_dir = MC_DIR / "shaderpacks"
        sh_dir.mkdir(exist_ok=True)
        self._sh_dir = sh_dir
        card = Card(f)
        card.pack(fill="both", expand=True, padx=24, pady=(0,20))
        ctk.CTkLabel(
            card,
            text="Nécessite un mod de shaders (Iris, OculusShaders, ou Sodium+Iris) "
                 "déjà installé dans Mods pour fonctionner en jeu.",
            text_color=TEXT3, font=ctk.CTkFont(size=11), justify="left"
        ).pack(anchor="w", padx=12, pady=(8,4))
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=4)
        ctk.CTkButton(top, text="📁 Ouvrir dossier", height=30, width=140,
                      fg_color=CARD2, border_color=BORDER, border_width=1, text_color=TEXT2,
                      command=lambda: open_in_file_manager(sh_dir)).pack(side="left", padx=4)
        ctk.CTkButton(top, text="🔄 Actualiser", height=30, width=110,
                      fg_color=CARD2, border_color=BORDER, border_width=1,
                      text_color=TEXT2, command=self._refresh_shaders_page).pack(side="left")

        self._build_drop_label(card, ".zip")

        self._sh_scroll = ctk.CTkScrollableFrame(card, fg_color="transparent")
        self._sh_scroll.pack(fill="both", expand=True, padx=12, pady=(0,12))
        self._refresh_shaders_page()

        self._hook_drop_targets(
            (card, self._sh_scroll), sh_dir, {".zip"},
            self._refresh_shaders_page, "shaderpack",
            trophy_id="shader_installed")

    def _refresh_shaders_page(self):
        for w in self._sh_scroll.winfo_children(): w.destroy()
        packs = list(self._sh_dir.glob("*.zip"))
        if not packs:
            ctk.CTkLabel(self._sh_scroll, text="Aucun shaderpack trouvé.",
                         text_color=TEXT3, font=ctk.CTkFont(size=13)).pack(pady=20)
            return
        for p in sorted(packs):
            r = ctk.CTkFrame(self._sh_scroll, fg_color=CARD2, corner_radius=8)
            r.pack(fill="x", pady=3)
            ctk.CTkLabel(r, text="✨", font=ctk.CTkFont(size=16)).pack(side="left", padx=10, pady=8)
            ctk.CTkLabel(r, text=p.name, text_color=TEXT, font=ctk.CTkFont(size=13)).pack(side="left")
            size = f"{round(p.stat().st_size/1024)} KB"
            ctk.CTkLabel(r, text=size, text_color=TEXT3,
                         font=ctk.CTkFont(size=11)).pack(side="right", padx=12)

    # ── CLASSEMENT & TROPHÉES ────────────────────────────────────────────────

    def _page_classement(self, f):
        ctk.CTkLabel(f, text="Classement", font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=24, pady=(18,8))
        scroll = ctk.CTkScrollableFrame(f, fg_color=BG, scrollbar_button_color=CARD2)
        scroll.pack(fill="both", expand=True, padx=24, pady=(0,20))

        row = ctk.CTkFrame(scroll, fg_color="transparent")
        row.pack(fill="x", pady=(0,16))

        # ── Tableau de classement (par nombre de lancements, tous postes) ──
        lb_c = Card(row, "TABLEAU DE CLASSEMENT")
        lb_c.pack(side="left", fill="both", expand=True, padx=(0,8))
        ctk.CTkLabel(
            lb_c, text="Classé par nombre de lancements, via le serveur de présence.",
            text_color=TEXT3, font=ctk.CTkFont(size=10)).pack(anchor="w", padx=12, pady=(2,6))
        self._lb_scroll = ctk.CTkScrollableFrame(lb_c, fg_color=CARD2, height=320)
        self._lb_scroll.pack(fill="both", expand=True, padx=12, pady=(0,8))
        ctk.CTkButton(lb_c, text="🔄 Actualiser", height=30,
                      fg_color=CARD2, border_color=BORDER, border_width=1,
                      text_color=TEXT2, font=ctk.CTkFont(size=11),
                      command=self._refresh_leaderboard).pack(fill="x", padx=12, pady=(0,12))

        # ── Mes trophées ─────────────────────────────────────────────────
        tr_c = Card(row, "MES TROPHÉES")
        tr_c.pack(side="right", fill="both", expand=True)
        ctk.CTkButton(tr_c, text="🏆 Vérifier mes succès Minecraft", height=30,
                      fg_color=CARD2, border_color=BORDER, border_width=1,
                      text_color=TEXT2, font=ctk.CTkFont(size=11),
                      command=self._scan_minecraft_advancements).pack(
                      fill="x", padx=12, pady=(2,6))
        self._trophy_grid = ctk.CTkFrame(tr_c, fg_color="transparent")
        self._trophy_grid.pack(fill="both", expand=True, padx=12, pady=(0,12))
        self._refresh_trophy_grid()

        self._refresh_leaderboard()

    def _refresh_trophy_grid(self):
        for w in self._trophy_grid.winfo_children(): w.destroy()
        unlocked_count = 0
        for i, (tid, (icon, name, desc)) in enumerate(TROPHIES.items()):
            unlocked = tid in self._trophies
            if unlocked: unlocked_count += 1
            r = ctk.CTkFrame(self._trophy_grid, fg_color=CARD2 if unlocked else "transparent",
                              corner_radius=8, border_width=1,
                              border_color=ACCENT if unlocked else BORDER)
            r.pack(fill="x", pady=3)
            ctk.CTkLabel(r, text=icon if unlocked else "🔒",
                         font=ctk.CTkFont(size=18),
                         text_color=TEXT if unlocked else TEXT3).pack(side="left", padx=10, pady=8)
            txt = ctk.CTkFrame(r, fg_color="transparent")
            txt.pack(side="left", fill="x", expand=True, pady=6)
            ctk.CTkLabel(txt, text=name, text_color=TEXT if unlocked else TEXT3,
                         font=ctk.CTkFont(size=12, weight="bold"), anchor="w").pack(fill="x")
            ctk.CTkLabel(txt, text=desc, text_color=TEXT3,
                         font=ctk.CTkFont(size=10), anchor="w").pack(fill="x")
        ctk.CTkLabel(self._trophy_grid,
                     text=f"{unlocked_count}/{len(TROPHIES)} trophées débloqués",
                     text_color=ACCENT2, font=ctk.CTkFont(size=11, weight="bold")
                     ).pack(anchor="w", pady=(8,0))

    def _refresh_leaderboard(self):
        for w in self._lb_scroll.winfo_children(): w.destroy()
        url = self.server_url.get().strip()
        if not url:
            ctk.CTkLabel(self._lb_scroll,
                         text="Configure le serveur de présence dans Paramètres\npour voir le classement.",
                         text_color=TEXT3, font=ctk.CTkFont(size=11), justify="left").pack(pady=10)
            return
        ctk.CTkLabel(self._lb_scroll, text="Chargement...",
                     text_color=TEXT3, font=ctk.CTkFont(size=11)).pack(pady=10)
        def run():
            try:
                req = urllib.request.Request(url.rstrip("/") + "/leaderboard", method="GET")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                rows = data.get("leaderboard", [])
            except Exception:
                rows = None
            self.root.after(0, lambda: self._render_leaderboard(rows))
        threading.Thread(target=run, daemon=True).start()

    def _render_leaderboard(self, rows):
        for w in self._lb_scroll.winfo_children(): w.destroy()
        if rows is None:
            ctk.CTkLabel(self._lb_scroll, text="Serveur inaccessible.",
                         text_color=RED_C, font=ctk.CTkFont(size=11)).pack(pady=10)
            return
        if not rows:
            ctk.CTkLabel(self._lb_scroll, text="Personne n'a encore de lancement enregistré.",
                         text_color=TEXT3, font=ctk.CTkFont(size=11)).pack(pady=10)
            return
        current = self.username.get().strip()
        medals = {0: "🥇", 1: "🥈", 2: "🥉"}
        for i, row in enumerate(rows):
            name = row.get("username", "?")
            r = ctk.CTkFrame(self._lb_scroll,
                              fg_color=ACT_BG if name == current else "transparent")
            r.pack(fill="x", pady=2)
            rank_txt = medals.get(i, f"#{i+1}")
            ctk.CTkLabel(r, text=rank_txt, width=36,
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=ACCENT2 if i < 3 else TEXT3).pack(side="left", padx=(8,4))
            ctk.CTkLabel(r, text=name + (" (vous)" if name == current else ""),
                         text_color=TEXT, font=ctk.CTkFont(size=12,
                         weight="bold" if name == current else "normal")).pack(side="left")
            ctk.CTkLabel(r, text=f"{row.get('launches',0)} lancements · 🏆 {row.get('trophies',0)}",
                         text_color=TEXT3, font=ctk.CTkFont(size=11)).pack(side="right", padx=10)

    # ── OPTIMISATION ──────────────────────────────────────────────────────────

    def _page_optimisation(self, f):
        ctk.CTkLabel(f, text="Optimisation", font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=24, pady=(18,8))
        scroll = ctk.CTkScrollableFrame(f, fg_color=BG)
        scroll.pack(fill="both", expand=True, padx=24)
        row = ctk.CTkFrame(scroll, fg_color="transparent")
        row.pack(fill="x", pady=(0,10))
        # JVM card
        jc = Card(row, "GÉNÉRATEUR JVM AVANCÉ")
        jc.pack(side="left", fill="both", expand=True, padx=(0,8))
        ctk.CTkLabel(jc, text="RAM allouée à Minecraft :", text_color=TEXT2,
                     font=ctk.CTkFont(size=13)).pack(anchor="w", padx=14, pady=(4,0))
        lbl = ctk.CTkLabel(jc, text=f"{self.ram_mb.get()} MB",
                           font=ctk.CTkFont(size=16, weight="bold"), text_color=ACCENT)
        lbl.pack(anchor="w", padx=14)
        sl2 = ctk.CTkSlider(jc, from_=1024, to=16384, variable=self.ram_mb,
                            progress_color=ACCENT, button_color=ACCENT2,
                            command=lambda v: lbl.configure(text=f"{int(v)} MB"))
        sl2.pack(fill="x", padx=14, pady=6)
        flags_txt = ctk.CTkTextbox(jc, height=120, fg_color=CARD2, border_color=BORDER,
                                    text_color=CYAN, font=ctk.CTkFont(size=11, family="Courier"))
        flags_txt.pack(fill="x", padx=14, pady=4)
        flags_txt.insert("end",
            "-Xms2048m -Xmx{RAM}m\n-XX:+UseG1GC\n-XX:+UnlockExperimentalVMOptions\n"
            "-XX:+ParallelRefProcEnabled\n-XX:MaxGCPauseMillis=200\n"
            "-XX:+DisableExplicitGC\n-XX:G1NewSizePercent=30\n-XX:G1MaxNewSizePercent=40")
        ctk.CTkButton(jc, text="Appliquer JVM", height=34, fg_color=ACCENT,
                      hover_color="#6d28d9", command=self._apply_jvm).pack(
                      fill="x", padx=14, pady=8)
        # Perf card
        pc = Card(row, "PERFORMANCE")
        pc.pack(side="right", fill="both", expand=True)
        for lbl2, desc in [
            ("Mode Performance","Priorise Minecraft sur les autres processus"),
            ("Boost GPU","Optimise les shaders et le rendu OpenGL"),
            ("Réduction Latence","Réduit le ping réseau en jeu"),
            ("Nettoyage RAM auto","Libère la mémoire avant le lancement"),
        ]:
            r = ctk.CTkFrame(pc, fg_color="transparent")
            r.pack(fill="x", padx=12, pady=4)
            v = tk.BooleanVar(value=True)
            ctk.CTkSwitch(r, text=lbl2, variable=v, progress_color=ACCENT,
                          button_color=ACCENT2, font=ctk.CTkFont(size=13),
                          text_color=TEXT).pack(side="left")
            ctk.CTkLabel(r, text=desc, text_color=TEXT3,
                         font=ctk.CTkFont(size=10)).pack(side="right")
        ctk.CTkButton(pc, text="⚡ Tout Optimiser", height=34, fg_color=GREEN,
                      hover_color="#059669", text_color="#000",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=self._do_optimize).pack(fill="x", padx=12, pady=10)

    # ── RÉSEAU ────────────────────────────────────────────────────────────────

    def _page_reseau(self, f):
        ctk.CTkLabel(f, text="Réseau", font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=24, pady=(18,8))
        scroll = ctk.CTkScrollableFrame(f, fg_color=BG, scrollbar_button_color=CARD2)
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        row = ctk.CTkFrame(scroll, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=8)
        dc = Card(row, "DNS")
        dc.pack(side="left", fill="both", expand=True, padx=(0,8))
        for name, ip in [("Cloudflare","1.1.1.1"),("Google","8.8.8.8"),("OpenDNS","208.67.222.222")]:
            r = ctk.CTkFrame(dc, fg_color=CARD2, corner_radius=8)
            r.pack(fill="x", padx=12, pady=3)
            ctk.CTkLabel(r, text=f"{name} ({ip})", text_color=TEXT,
                         font=ctk.CTkFont(size=13)).pack(side="left", padx=10, pady=8)
            ctk.CTkButton(r, text="Appliquer", height=26, width=80, fg_color=ACCENT,
                          hover_color="#6d28d9", font=ctk.CTkFont(size=11),
                          command=lambda i=ip: self._dns_lbl.configure(text=f"Actif: {i}")
                          ).pack(side="right", padx=8)
        pc = Card(row, "PING SERVEUR")
        pc.pack(side="right", fill="both", expand=True)
        ctk.CTkLabel(pc, text="Adresse du serveur :", text_color=TEXT2,
                     font=ctk.CTkFont(size=12)).pack(anchor="w", padx=12, pady=(4,2))
        self._ping2_entry = ctk.CTkEntry(pc, placeholder_text="play.example.com",
                                          height=32, fg_color=CARD2, border_color=BORDER)
        self._ping2_entry.pack(fill="x", padx=12, pady=2)
        self._ping2_result = ctk.CTkLabel(pc, text="", text_color=GREEN,
                                           font=ctk.CTkFont(size=13, weight="bold"))
        self._ping2_result.pack(padx=12, pady=4)
        ctk.CTkButton(pc, text="Tester le Ping", height=34, fg_color=ACCENT,
                      hover_color="#6d28d9",
                      command=lambda: self._do_ping(
                          self._ping2_entry.get(), self._ping2_result)
                      ).pack(fill="x", padx=12, pady=6)

        # ── Stabilité du réseau (mesure réelle : latence, jitter, perte) ────
        row2 = ctk.CTkFrame(scroll, fg_color="transparent")
        row2.pack(fill="x", padx=24, pady=(0,8))

        stab_c = Card(row2, "STABILITÉ DU RÉSEAU")
        stab_c.pack(side="left", fill="both", expand=True, padx=(0,8))
        self._stab_dot = StatusDot(stab_c, "Mesure en cours...", TEXT2)
        self._stab_dot.pack(anchor="w", padx=12, pady=(2,8))
        self._stab_latency = StatRow(stab_c, "Latence moyenne"); self._stab_latency.pack(fill="x", padx=12, pady=2)
        self._stab_jitter  = StatRow(stab_c, "Jitter (variation)"); self._stab_jitter.pack(fill="x", padx=12, pady=2)
        self._stab_loss    = StatRow(stab_c, "Paquets perdus"); self._stab_loss.pack(fill="x", padx=12, pady=(2,10))
        ctk.CTkButton(stab_c, text="🔄 Retester maintenant", height=30,
                      fg_color=CARD2, border_color=BORDER, border_width=1,
                      text_color=TEXT2, font=ctk.CTkFont(size=11),
                      command=self._test_network_stability).pack(fill="x", padx=12, pady=(0,12))

        row3 = ctk.CTkFrame(scroll, fg_color="transparent")
        row3.pack(fill="x", padx=24, pady=(0,16))

        # ── Joueurs en ligne maintenant (temps réel, multi-launchers) ───────
        online_c = Card(row3, "EN LIGNE MAINTENANT (TEMPS RÉEL)")
        online_c.pack(side="left", fill="both", expand=True, padx=(0,8))
        dot_row = ctk.CTkFrame(online_c, fg_color="transparent")
        dot_row.pack(fill="x", padx=12, pady=(2,4))
        self._online_dot = StatusDot(dot_row, "Serveur non configuré", TEXT2)
        self._online_dot.pack(side="left")
        self._admin_badge_lbl = ctk.CTkLabel(
            dot_row, text="🛡 Admin" if self._is_admin else "",
            text_color=ORANGE, font=ctk.CTkFont(size=11, weight="bold"))
        self._admin_badge_lbl.pack(side="right")
        self._online_count_lbl = ctk.CTkLabel(
            online_c, text="", font=ctk.CTkFont(size=13, weight="bold"), text_color=ACCENT2)
        self._online_count_lbl.pack(anchor="w", padx=12, pady=(0,6))
        self._online_scroll = ctk.CTkScrollableFrame(online_c, fg_color=CARD2, height=140)
        self._online_scroll.pack(fill="both", expand=True, padx=12, pady=(0,8))
        ctk.CTkLabel(
            online_c,
            text="Configure l'adresse du serveur dans Paramètres pour voir\n"
                 "tous les joueurs connectés depuis n'importe quel poste.",
            text_color=TEXT3, font=ctk.CTkFont(size=10), justify="left"
        ).pack(anchor="w", padx=12, pady=(0,12))

        # ── Membres ayant utilisé ce launcher (compteur local, fonctionnel) ─
        mem_c = Card(row3, "MEMBRES DU LAUNCHER")
        mem_c.pack(side="right", fill="both", expand=True)
        ctk.CTkLabel(
            mem_c,
            text="Compteur local à ce poste (pas de serveur central) : pseudos\n"
                 "distincts ayant réellement lancé le jeu depuis ce launcher.",
            text_color=TEXT3, font=ctk.CTkFont(size=10), justify="left"
        ).pack(anchor="w", padx=12, pady=(2,6))
        self._mem_count_lbl = ctk.CTkLabel(
            mem_c, text="", font=ctk.CTkFont(size=13, weight="bold"), text_color=ACCENT2)
        self._mem_count_lbl.pack(anchor="w", padx=12, pady=(0,6))
        self._mem_list_scroll = ctk.CTkScrollableFrame(mem_c, fg_color=CARD2, height=140)
        self._mem_list_scroll.pack(fill="both", expand=True, padx=12, pady=(0,8))
        ctk.CTkButton(mem_c, text="🔄 Actualiser la liste", height=30,
                      fg_color=CARD2, border_color=BORDER, border_width=1,
                      text_color=TEXT2, font=ctk.CTkFont(size=11),
                      command=self._refresh_members_list).pack(fill="x", padx=12, pady=(0,12))

        # ── Panel admin : diffuser une annonce à tous les launchers ────────
        # Visible pour tout le monde (le serveur vérifie le pseudo côté
        # serveur via ADMIN_USERS et refuse si tu n'es pas admin), pour ne
        # pas avoir à recharger l'UI dynamiquement selon le statut admin.
        row4 = ctk.CTkFrame(scroll, fg_color="transparent")
        row4.pack(fill="x", padx=24, pady=(0,16))
        admin_c = Card(row4, "PANEL ADMIN — DIFFUSER UNE ANNONCE")
        admin_c.pack(fill="x")
        ctk.CTkLabel(
            admin_c,
            text="Réservé aux pseudos listés comme admins sur le serveur de\n"
                 "présence (ADMIN_USERS dans sakura_server.py). Le message\n"
                 "s'affiche en bannière sur l'Accueil de tous les launchers connectés.",
            text_color=TEXT3, font=ctk.CTkFont(size=10), justify="left"
        ).pack(anchor="w", padx=12, pady=(2,6))
        self._announce_entry = ctk.CTkEntry(
            admin_c, placeholder_text="Message à diffuser...",
            height=32, fg_color=CARD2, border_color=BORDER)
        self._announce_entry.pack(fill="x", padx=12, pady=4)
        ab_row = ctk.CTkFrame(admin_c, fg_color="transparent")
        ab_row.pack(fill="x", padx=12, pady=(4,12))
        ctk.CTkButton(ab_row, text="📢 Diffuser", height=32, fg_color=ACCENT,
                      hover_color="#6d28d9", font=ctk.CTkFont(size=12, weight="bold"),
                      command=lambda: self._send_announcement(self._announce_entry.get().strip())
                      ).pack(side="left", padx=(0,6))
        ctk.CTkButton(ab_row, text="Effacer l'annonce", height=32,
                      fg_color=CARD2, border_color=BORDER, border_width=1,
                      text_color=TEXT2, command=lambda: self._send_announcement("")
                      ).pack(side="left")

        self._refresh_members_list()
        self._test_network_stability()

    # ── PARAMÈTRES ────────────────────────────────────────────────────────────

    def _page_parametres(self, f):
        ctk.CTkLabel(f, text="Paramètres", font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=24, pady=(18,8))
        card = Card(f)
        card.pack(fill="x", padx=24, pady=8)
        for label, var, ph in [
            ("Pseudo Minecraft", self.username, "Votre pseudo..."),
            ("Serveur de présence (multi-launchers)", self.server_url, "http://IP_OU_DOMAINE:8765"),
        ]:
            r = ctk.CTkFrame(card, fg_color="transparent")
            r.pack(fill="x", padx=16, pady=6)
            ctk.CTkLabel(r, text=label, text_color=TEXT2,
                         font=ctk.CTkFont(size=14)).pack(anchor="w")
            ctk.CTkEntry(r, textvariable=var, placeholder_text=ph,
                         height=34, fg_color=CARD2, border_color=BORDER).pack(fill="x", pady=4)
        ctk.CTkLabel(card, text=f"Dossier Minecraft : {MC_DIR}",
                     text_color=TEXT3, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=4)
        ctk.CTkButton(card, text="📁 Ouvrir dossier Minecraft", height=32, width=200,
                      fg_color=CARD2, border_color=BORDER, border_width=1, text_color=TEXT2,
                      command=lambda: open_in_file_manager(MC_DIR)
                      ).pack(anchor="w", padx=16, pady=(0,4))
        ctk.CTkLabel(card, text=f"Version du launcher : {APP_VERSION}",
                     text_color=TEXT3, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(0,12))

        # Compte Microsoft / Xbox réel (compte premium Minecraft)
        ms_card = Card(f, "COMPTE MICROSOFT (MINECRAFT PREMIUM)")
        ms_card.pack(fill="x", padx=24, pady=8)
        ctk.CTkLabel(ms_card,
            text="Connecte ton vrai compte Microsoft pour jouer avec ta version achetée\n"
                 "de Minecraft (skins, multijoueur sur serveurs premium, etc.).",
            text_color=TEXT3, font=ctk.CTkFont(size=11), justify="left").pack(
            anchor="w", padx=12, pady=(4,8))
        if self._ms_account:
            self._ms_status_lbl = StatusDot(
                ms_card, f"Connecté : {self._ms_account.get('name','?')}", GREEN)
        else:
            self._ms_status_lbl = StatusDot(ms_card, "Non connecté", RED_C)
        self._ms_status_lbl.pack(anchor="w", padx=12, pady=(0,8))
        ms_btn_row = ctk.CTkFrame(ms_card, fg_color="transparent")
        ms_btn_row.pack(fill="x", padx=12, pady=(0,12))
        ctk.CTkButton(ms_btn_row, text="🔑 Se connecter avec Microsoft", height=34,
                      fg_color=ACCENT, hover_color="#6d28d9",
                      font=ctk.CTkFont(size=12, weight="bold"),
                      command=self._ms_login).pack(side="left", padx=(0,6))
        ctk.CTkButton(ms_btn_row, text="Se déconnecter", height=34,
                      fg_color=CARD2, border_width=1, border_color=BORDER,
                      text_color=TEXT2, command=self._ms_logout).pack(side="left")

    # ── LOGS ──────────────────────────────────────────────────────────────────

    def _page_logs(self, f):
        ctk.CTkLabel(f, text="Logs", font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=24, pady=(18,8))
        card = Card(f)
        card.pack(fill="both", expand=True, padx=24, pady=(0,20))
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=6)
        ctk.CTkButton(top, text="Effacer", height=28, width=80,
                      fg_color=RED_C, hover_color="#dc2626",
                      font=ctk.CTkFont(size=11),
                      command=self._clear_logs).pack(side="right")
        self._log_box = ctk.CTkTextbox(card, fg_color=CARD2, text_color=CYAN,
                                        font=ctk.CTkFont(size=11, family="Courier"),
                                        state="disabled")
        self._log_box.pack(fill="both", expand=True, padx=12, pady=(0,12))

    # ── SKIN & PROFIL ─────────────────────────────────────────────────────────

    def _page_skin(self, f):
        ctk.CTkLabel(f, text="Skin & Profil",
                     font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=24, pady=(18,8))

        main = ctk.CTkFrame(f, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=24, pady=4)

        # ── Left : Aperçu 3D ──────────────────────────────────────────────
        left = Card(main, "APERÇU 3D DU SKIN")
        left.pack(side="left", fill="y", padx=(0,12), ipadx=6)

        self._skin_canvas = tk.Canvas(left, width=210, height=310,
                                       bg="#0a0814", highlightthickness=0)
        self._skin_canvas.pack(padx=12, pady=(4,8))

        rot_row = ctk.CTkFrame(left, fg_color="transparent")
        rot_row.pack(pady=(0,10))
        ctk.CTkButton(rot_row, text="◀", width=36, height=30,
                      fg_color=CARD2, hover_color=ACCENT,
                      command=lambda: self._rotate_skin(-1)).pack(side="left", padx=3)
        self._rotate_btn = ctk.CTkButton(rot_row, text="▶▶ Auto", width=82, height=30,
                                          fg_color=ACCENT, hover_color="#6d28d9",
                                          command=self._toggle_auto_rotate)
        self._rotate_btn.pack(side="left", padx=3)
        ctk.CTkButton(rot_row, text="▶", width=36, height=30,
                      fg_color=CARD2, hover_color=ACCENT,
                      command=lambda: self._rotate_skin(1)).pack(side="left", padx=3)

        # ── Right : options ───────────────────────────────────────────────
        right = ctk.CTkScrollableFrame(main, fg_color="transparent",
                                        scrollbar_button_color=CARD2)
        right.pack(side="right", fill="both", expand=True)

        # Choisir un skin
        up_card = Card(right, "CHOISIR UN SKIN")
        up_card.pack(fill="x", pady=(0,10))
        ctk.CTkLabel(up_card, text="Fichier skin PNG (64×64) :",
                     text_color=TEXT2, font=ctk.CTkFont(size=12)).pack(anchor="w", padx=12, pady=(4,0))
        sk_row = ctk.CTkFrame(up_card, fg_color="transparent")
        sk_row.pack(fill="x", padx=12, pady=4)
        self._skin_entry = ctk.CTkEntry(sk_row, textvariable=self._skin_path,
                                         placeholder_text="Chemin vers skin.png...",
                                         height=30, fg_color=CARD2, border_color=BORDER)
        self._skin_entry.pack(side="left", fill="x", expand=True, padx=(0,4))
        ctk.CTkButton(sk_row, text="📁", width=34, height=30,
                      fg_color=CARD2, border_color=BORDER, border_width=1,
                      command=self._browse_skin).pack(side="left")
        ctk.CTkButton(up_card, text="✅ Appliquer le Skin", height=34,
                      fg_color=ACCENT, hover_color="#6d28d9",
                      font=ctk.CTkFont(size=12, weight="bold"),
                      command=self._apply_skin).pack(fill="x", padx=12, pady=(0,10))

        # Carte de profil
        prof_card = Card(right, "CARTE DE PROFIL")
        prof_card.pack(fill="x", pady=(0,10))
        prof_inner = ctk.CTkFrame(prof_card, fg_color=CARD2, corner_radius=8)
        prof_inner.pack(fill="x", padx=12, pady=8)

        self._avatar_canvas = tk.Canvas(prof_inner, width=48, height=48,
                                         bg=CARD2, highlightthickness=0)
        self._avatar_canvas.pack(side="left", padx=10, pady=8)

        pinfo = ctk.CTkFrame(prof_inner, fg_color="transparent")
        pinfo.pack(side="left", fill="x", expand=True, padx=(0,10))
        ctk.CTkLabel(pinfo, text="PSEUDO", text_color=TEXT3,
                     font=ctk.CTkFont(size=9, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(pinfo, textvariable=self.username,
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=TEXT).pack(anchor="w")
        StatusDot(pinfo, "En ligne (Hors Ligne)", GREEN).pack(anchor="w")

        # Skins prédéfinis
        pre_card = Card(right, "SKINS PRÉDÉFINIS")
        pre_card.pack(fill="x", pady=(0,16))
        pre_row = ctk.CTkFrame(pre_card, fg_color="transparent")
        pre_row.pack(fill="x", padx=12, pady=10)
        presets = [
            ("Steve",  "#6B8CFF", "#0d1a40"),
            ("Alex",   "#5CBA7B", "#0a2810"),
            ("Ender",  "#a855f7", "#1a0a30"),
            ("Zombie", "#3D8B3D", "#0a1a0a"),
        ]
        for name, fg_col, bg_col in presets:
            b = ctk.CTkFrame(pre_row, fg_color=bg_col, corner_radius=10,
                             width=66, height=72, border_width=1, border_color=fg_col)
            b.pack(side="left", padx=5)
            b.pack_propagate(False)
            ctk.CTkLabel(b, text="👤", font=ctk.CTkFont(size=22)).pack(pady=(8,0))
            ctk.CTkLabel(b, text=name, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="white").pack()
            for w in [b] + b.winfo_children():
                w.bind("<Button-1>", lambda e, n=name: self._load_preset_skin(n))
            b.bind("<Enter>", lambda e, w=b, c=fg_col: w.configure(fg_color=c))
            b.bind("<Leave>", lambda e, w=b, c=bg_col: w.configure(fg_color=c))

        # Init
        self.root.after(100, self._render_skin)
        self.root.after(120, self._render_avatar)

    # ── Skin rendering helpers ────────────────────────────────────────────────

    def _make_default_skin(self):
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            return None
        skin = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(skin)
        FACE  = (198, 160, 120, 255)
        HAIR  = (90,  60,  30,  255)
        EYE   = (50,  50,  220, 255)
        SHIRT = (100, 130, 200, 255)
        PANT  = (50,  50,  160, 255)
        ARM   = (178, 140, 100, 255)
        # Head top/sides/front/back
        d.rectangle([8, 0, 15, 7],  fill=HAIR)
        d.rectangle([0, 8, 7,  15], fill=FACE)
        d.rectangle([8, 8, 15, 15], fill=FACE)
        d.rectangle([16, 8, 23, 15], fill=FACE)
        d.rectangle([24, 8, 31, 15], fill=HAIR)
        # Eyes
        for ex in (9, 13):
            d.point((ex, 10), fill=EYE); d.point((ex, 11), fill=EYE)
        # Hair fringe
        d.rectangle([8, 8, 15, 8], fill=HAIR)
        # Body
        d.rectangle([16, 20, 19, 31], fill=(80,110,180,255))
        d.rectangle([20, 20, 27, 31], fill=SHIRT)
        d.rectangle([28, 20, 31, 31], fill=(80,110,180,255))
        d.rectangle([32, 20, 39, 31], fill=(70,100,160,255))
        # Right arm
        d.rectangle([40, 20, 43, 31], fill=ARM)
        d.rectangle([44, 20, 47, 31], fill=FACE)
        d.rectangle([48, 20, 51, 31], fill=ARM)
        d.rectangle([52, 20, 55, 31], fill=ARM)
        # Left arm (new format)
        d.rectangle([32, 52, 35, 63], fill=ARM)
        d.rectangle([36, 52, 39, 63], fill=FACE)
        # Right leg
        d.rectangle([0,  20, 3,  31], fill=(40,40,140,255))
        d.rectangle([4,  20, 7,  31], fill=PANT)
        d.rectangle([8,  20, 11, 31], fill=(40,40,140,255))
        d.rectangle([12, 20, 15, 31], fill=(30,30,120,255))
        # Left leg (new format)
        d.rectangle([16, 52, 19, 63], fill=(40,40,140,255))
        d.rectangle([20, 52, 23, 63], fill=PANT)
        return skin

    def _render_skin(self):
        try:
            canvas = self._skin_canvas
        except AttributeError:
            return
        W, H = 210, 310
        canvas.delete("all")
        # Fond étoilé
        import random as _r
        rng = _r.Random(42)
        for _ in range(55):
            x = rng.randint(0, W); y = rng.randint(0, H)
            canvas.create_oval(x, y, x+1, y+1, fill="#c8b8ff", outline="")

        try:
            from PIL import Image, ImageTk, ImageEnhance
        except ImportError:
            canvas.create_text(W//2, H//2-10,
                               text="pip install pillow\npour l'aperçu 3D",
                               fill="#94a3b8", font=("Courier", 10), justify="center")
            return

        # Cache des 4 angles déjà rendus pour ce skin : évite de refaire tout
        # le travail PIL (crop/resize/compositing) à chaque rotation — utile
        # surtout en auto-rotate (toutes les 1.1s) qui boucle sur les 4
        # mêmes angles encore et encore.
        path = self._skin_path.get()
        try:
            mtime = Path(path).stat().st_mtime if path and Path(path).exists() else 0
        except Exception:
            mtime = 0
        cache_key = (path, mtime, self._skin_angle % 4)
        cache = getattr(self, "_skin_render_cache", None)
        if cache is None or cache.get("_id") != (path, mtime):
            cache = {"_id": (path, mtime)}
            self._skin_render_cache = cache
        cached_photo = cache.get(cache_key)
        if cached_photo is not None:
            canvas._photo = cached_photo
            canvas.create_image(W//2, 0, image=cached_photo, anchor="n")
            return

        if path and Path(path).exists():
            try:
                skin = Image.open(path).convert("RGBA")
            except Exception:
                skin = self._make_default_skin()
        else:
            skin = self._make_default_skin()
        if skin is None:
            return
        if skin.size == (64, 32):
            ns = Image.new("RGBA", (64, 64), (0,0,0,0))
            ns.paste(skin, (0,0)); skin = ns
        elif skin.size != (64, 64):
            skin = skin.resize((64, 64), Image.NEAREST)

        angle = self._skin_angle % 4

        def c(x, y, w, h): return skin.crop((x, y, x+w, y+h))

        if angle == 0:    # Front
            head_f, head_top, head_s = c(8,8,8,8), c(8,0,8,8), c(16,8,8,8)
            head_ov = c(40,8,8,8); bw=8
            body    = c(20,20,bw,12)
            r_arm, l_arm = c(44,20,4,12), c(36,52,4,12)
            r_leg, l_leg = c(4,20,4,12),  c(20,52,4,12)
        elif angle == 1:  # Right
            head_f, head_top, head_s = c(16,8,8,8), c(8,0,8,8), c(24,8,8,8)
            head_ov = c(48,8,8,8); bw=4
            body    = c(28,20,bw,12)
            r_arm, l_arm = c(48,20,4,12), c(40,52,4,12)
            r_leg, l_leg = c(8,20,4,12),  c(24,52,4,12)
        elif angle == 2:  # Back
            head_f, head_top, head_s = c(24,8,8,8), c(8,0,8,8), c(0,8,8,8)
            head_ov = c(56,8,8,8); bw=8
            body    = c(32,20,bw,12)
            r_arm, l_arm = c(52,20,4,12), c(44,52,4,12)
            r_leg, l_leg = c(12,20,4,12), c(28,52,4,12)
        else:             # Left
            head_f, head_top, head_s = c(0,8,8,8), c(8,0,8,8), c(8,8,8,8)
            head_ov = c(32,8,8,8); bw=4
            body    = c(16,20,bw,12)
            r_arm, l_arm = c(40,20,4,12), c(32,52,4,12)
            r_leg, l_leg = c(0,20,4,12),  c(16,52,4,12)

        HS = 13; S = 10
        HW = 8*HS; BW = bw*S; AW = 4*S
        iso_h = HS*3; side_w = HS*2

        def sc(img, w, h): return img.resize((w, h), Image.NEAREST)
        head_sc = sc(head_f, HW, HW)
        top_sc  = ImageEnhance.Brightness(sc(head_top, HW, iso_h)).enhance(0.72)
        side_sc = ImageEnhance.Brightness(sc(head_s, side_w, HW)).enhance(0.55)
        ov_sc   = sc(head_ov, HW, HW)
        body_sc = sc(body, BW, 12*S)
        ra_sc   = sc(r_arm, AW, 12*S)
        la_sc   = sc(l_arm, AW, 12*S)
        rl_sc   = sc(r_leg, AW, 12*S)
        ll_sc   = sc(l_leg, AW, 12*S)

        scene = Image.new("RGBA", (W, H), (0,0,0,0))
        cx = W // 2
        offset = side_w // 2
        head_x = cx - HW//2 - offset
        body_x = cx - BW//2 - offset
        top_pad = 8
        head_y = top_pad + iso_h
        body_y = head_y + HW + 2
        leg_y  = body_y + 12*S + 2
        is_side = angle in (1, 3)

        if not is_side:
            scene.paste(ra_sc, (body_x - AW - 2, body_y), ra_sc)
            scene.paste(la_sc, (body_x + BW + 2,  body_y), la_sc)
        else:
            scene.paste(ra_sc, (body_x + BW + 2, body_y), ra_sc)
        scene.paste(rl_sc,   (body_x,      leg_y), rl_sc)
        scene.paste(ll_sc,   (body_x + AW, leg_y), ll_sc)
        scene.paste(body_sc, (body_x, body_y), body_sc)
        scene.paste(top_sc,  (head_x, head_y - iso_h), top_sc)
        scene.paste(head_sc, (head_x, head_y), head_sc)
        scene.paste(ov_sc,   (head_x, head_y), ov_sc)
        scene.paste(side_sc, (head_x + HW, head_y), side_sc)

        photo = ImageTk.PhotoImage(scene)
        canvas._photo = photo
        cache[cache_key] = photo
        canvas.create_image(W//2, 0, image=photo, anchor="n")

    def _render_avatar(self):
        try:
            canvas = self._avatar_canvas
        except AttributeError:
            return
        canvas.delete("all")
        try:
            from PIL import Image, ImageTk
        except ImportError:
            canvas.create_text(24, 24, text="?", fill=TEXT2, font=("Courier", 14))
            return
        path = self._skin_path.get()
        if path and Path(path).exists():
            try:
                skin = Image.open(path).convert("RGBA")
            except Exception:
                skin = self._make_default_skin()
        else:
            skin = self._make_default_skin()
        if skin is None:
            return
        if skin.size != (64, 64):
            skin = skin.resize((64, 64), Image.NEAREST)
        face    = skin.crop((8,8,16,16)).resize((48,48), Image.NEAREST)
        overlay = skin.crop((40,8,48,16)).resize((48,48), Image.NEAREST)
        face.paste(overlay, (0,0), overlay)
        photo = ImageTk.PhotoImage(face)
        canvas._photo = photo
        canvas.create_image(0, 0, image=photo, anchor="nw")

    def _browse_skin(self):
        path = filedialog.askopenfilename(
            title="Choisir un skin Minecraft",
            filetypes=[("Images PNG", "*.png"), ("Tous les fichiers", "*.*")])
        if path:
            self._skin_path.set(path)

    def _apply_skin(self):
        self._render_skin()
        self._render_avatar()
        path = self._skin_path.get()
        name = Path(path).name if path else "Défaut"
        if path and Path(path).exists():
            self._install_skin_files(path)
            self._unlock_trophy("skin_custom")
        self._save_config()
        self._add_log(f"Skin appliqué : {name}")

    def _install_skin_files(self, skin_path):
        """Copie le skin + configure CustomSkinLoader pour les fichiers locaux."""
        import hashlib, shutil as _sh
        src = Path(skin_path)
        if not src.exists():
            return
        uname = self.username.get() or "Player"

        # 1) Cache Minecraft vanilla
        skin_bytes = src.read_bytes()
        sha1 = hashlib.sha1(skin_bytes).hexdigest()
        cache_dir = MC_DIR / "assets" / "skins"
        cache_dir.mkdir(parents=True, exist_ok=True)
        _sh.copy2(src, cache_dir / sha1)

        # 2) CustomSkinLoader — dossiers LocalSkin (les deux chemins possibles selon version)
        csl_dirs = [
            MC_DIR / "CustomSkinLoader" / "LocalSkin",
            MC_DIR / "config" / "customskinloader" / "LocalSkin",
        ]
        for csl_dir in csl_dirs:
            csl_dir.mkdir(parents=True, exist_ok=True)
            _sh.copy2(src, csl_dir / f"{uname}.png")

        # 3) Config CustomSkinLoader : priorité aux fichiers locaux
        csl_cfg_paths = [
            MC_DIR / "CustomSkinLoader" / "CustomSkinLoader.json",
            MC_DIR / "config" / "customskinloader" / "CustomSkinLoader.json",
        ]
        csl_config = {
            "enable": True,
            "loadlist": [
                {
                    "name": "LocalSkin",
                    "type": "LocalSkin",
                    "checkList": [
                        f"LocalSkin/{uname}.png",
                        "LocalSkin/{username}.png",
                    ]
                },
                {
                    "name": "Mojang",
                    "type": "MojangAPI"
                }
            ]
        }
        for cfg_path in csl_cfg_paths:
            if cfg_path.parent.exists():
                cfg_path.write_text(
                    json.dumps(csl_config, indent=2, ensure_ascii=False), "utf-8")

        # 4) Copie de référence
        _sh.copy2(src, MC_DIR / "active_skin.png")
        self._skin_sha1 = sha1

    def _rotate_skin(self, direction):
        self._skin_angle = (self._skin_angle + direction) % 4
        self._render_skin()

    def _toggle_auto_rotate(self):
        self._auto_rotate = not self._auto_rotate
        if self._auto_rotate:
            self._rotate_btn.configure(text="⏸ Stop", fg_color=RED_C, hover_color="#dc2626")
            self._auto_rotate_step()
        else:
            self._rotate_btn.configure(text="▶▶ Auto", fg_color=ACCENT, hover_color="#6d28d9")
            if self._auto_rotate_id:
                self.root.after_cancel(self._auto_rotate_id)
                self._auto_rotate_id = None

    def _auto_rotate_step(self):
        if not self._auto_rotate:
            return
        self._skin_angle = (self._skin_angle + 1) % 4
        self._render_skin()
        self._auto_rotate_id = self.root.after(1100, self._auto_rotate_step)

    def _load_preset_skin(self, name):
        self._skin_path.set("")
        self._skin_angle = 0
        self._render_skin()
        self._render_avatar()
        self._add_log(f"Preset chargé : {name}")


    # ─────────────────────────────────────────────────────────────────────────
    # Version loading
    # ─────────────────────────────────────────────────────────────────────────

    def _load_versions(self):
        try: self._jver_count.configure(text="Chargement...", text_color=ORANGE)
        except: pass
        def load():
            try:
                remote = minecraft_launcher_lib.utils.get_version_list()
                self._all_versions = remote
                self._installed    = installed_ids()
                inst_list = sorted(self._installed) + \
                            [v["id"] for v in remote if v.get("type")=="release"]
                seen = set(); dedup = []
                for i in inst_list:
                    if i not in seen: seen.add(i); dedup.append(i)
                def update_ui():
                    w = getattr(self, "_jver_count", None)
                    if w is not None:
                        try: w.configure(text=f"{len(remote)} versions", text_color=GREEN)
                        except Exception: pass
                    combo = getattr(self, "_hero_ver_combo", None)
                    if combo is not None:
                        try:
                            combo.configure(values=dedup[:80])
                            if dedup: combo.set(dedup[0])
                        except Exception: pass
                self.root.after(0, self._pop_versions)
                self.root.after(0, update_ui)
            except Exception as e:
                write_log("Load versions", e)
                w = getattr(self, "_jver_count", None)
                if w is not None:
                    self.root.after(0, lambda: w.configure(text="Erreur réseau", text_color=RED_C))
        threading.Thread(target=load, daemon=True).start()

    def _pop_versions(self):
        try: sc = self._jver_scroll
        except: return
        for w in sc.winfo_children(): w.destroy()
        try: filt = self._jsearch.get().lower()
        except: filt = ""
        allowed = set()
        if self._jshow_rel.get():  allowed.add("release")
        if self._jshow_snap.get(): allowed.add("snapshot")
        if self._jshow_old.get():  allowed.update({"old_alpha","old_beta"})
        if not allowed: allowed.add("release")
        remote_ids = {v["id"] for v in self._all_versions}
        # Limite le nombre de boutons créés : sans filtre, la liste complète
        # (snapshots + anciennes versions) peut dépasser le millier d'entrées
        # et chaque CTkButton est coûteux à instancier (rendu canvas) — ça
        # fait ramer/geler l'UI sur les PC peu puissants. On affiche un cap
        # raisonnable et on invite à affiner la recherche pour aller au-delà.
        MAX_BUTTONS = 150
        shown = 0

        def add_btn(vid, label, fg, hover):
            nonlocal shown
            ctk.CTkButton(sc, text=label, anchor="w", height=34,
                          fg_color=fg, hover_color=hover,
                          font=ctk.CTkFont(size=12), text_color=TEXT,
                          command=lambda i=vid: self._sel_ver(i)).pack(fill="x", pady=1)
            shown += 1

        # Installed modded first (blue)
        for vid in sorted(self._installed - remote_ids):
            if shown >= MAX_BUTTONS: break
            if filt and filt not in vid.lower(): continue
            add_btn(vid, "✔ "+vid, "#1a2a3a", "#2a3a4a")
        for v in self._all_versions:
            if shown >= MAX_BUTTONS: break
            vt = v.get("type","")
            if vt not in allowed: continue
            vid = v["id"]
            if filt and filt not in vid.lower(): continue
            is_i = vid in self._installed
            label = ("✔ " if is_i else "") + vid
            if vt=="snapshot": label+=" (Snapshot)"
            add_btn(vid, label, "#1a3a1a" if is_i else CARD2, "#2a4a2a" if is_i else CARD)
        if shown >= MAX_BUTTONS:
            ctk.CTkLabel(sc, text=f"… plus de {MAX_BUTTONS} versions : affine la recherche",
                         text_color=TEXT3, font=ctk.CTkFont(size=11)).pack(pady=6)

    def _sel_ver(self, vid):
        self.selected_id.set(vid)
        import re
        if re.match(r"^\d+\.\d+", vid):
            self.loader_mc.set(vid); self.neo_mc.set(vid)
        self._show_page("jouer")

    # ─────────────────────────────────────────────────────────────────────────
    # Launch / Install
    # ─────────────────────────────────────────────────────────────────────────

    def _patch_json(self, vid):
        p = MC_DIR/"versions"/vid/f"{vid}.json"
        if not p.exists(): return
        try:
            data = json.loads(p.read_text("utf-8"))
            changed = False
            for key in ("game","jvm"):
                lst = data.get("arguments",{}).get(key,[])
                fixed = []
                for a in lst:
                    if isinstance(a,dict) and "values" in a and "value" not in a:
                        a=dict(a); raw=a.pop("values")
                        a["value"]=raw if isinstance(raw,list) else [raw]; changed=True
                    fixed.append(a)
                if key in data.get("arguments",{}): data["arguments"][key]=fixed
            if changed: p.write_text(json.dumps(data,indent=2),"utf-8")
        except Exception as e: write_log("Patch JSON",e)

    def _launch_current(self):
        vid = self.selected_id.get()
        if not vid:
            messagebox.showwarning("Attention","Sélectionne une version !"); return
        if vid not in installed_ids():
            if messagebox.askyesno("Non installé", f"{vid} n'est pas installé. L'installer ?"):
                self._install_ver(self._jlaunch_bar, self._jlaunch_st)
            return
        bar = self._jlaunch_bar; st = self._jlaunch_st
        try: bar.set(0)
        except: pass
        try: st.configure(text=f"Lancement de {vid}...", text_color=ORANGE)
        except: pass
        self._add_log(f"Lancement de {vid}")
        def run():
            try:
                self._patch_json(vid)
                # Installe le skin avant le lancement
                skin_path = self._skin_path.get()
                if skin_path and Path(skin_path).exists():
                    try: self._install_skin_files(skin_path)
                    except Exception: pass

                if self._ms_account:
                    # Vrai compte Microsoft : token + UUID réels (entitlements
                    # et version achetée par le joueur, jeu en ligne possible)
                    uname = self._ms_account.get("name") or self.username.get() or "Player"
                    uid   = self._ms_account.get("id") or self._ms_account.get("uuid")
                    token = self._ms_account.get("access_token", "none")
                else:
                    # UUID offline basé sur le pseudo (même algo que Minecraft vanilla)
                    uname = self.username.get() or "Player"
                    uid   = offline_uuid(uname)
                    token = "none"

                ram_xmx = int(self.ram_mb.get())
                jvm_args = aikar_jvm_flags(ram_xmx)

                # Pointe vers le skin local pour CustomSkinLoader si dispo
                active_skin = MC_DIR / "active_skin.png"
                if active_skin.exists():
                    jvm_args.append(
                        f"-Dcustomskinloader.skin={active_skin.as_uri()}")

                options = {
                    "username":         uname,
                    "uuid":             uid,
                    "token":            token,
                    "gameDirectory":    str(MC_DIR),
                    "jvmArguments":     jvm_args,
                    "launcherName":     "SakuraLauncher",
                    "launcherVersion":  APP_VERSION,
                    "nativesDirectory": str(MC_DIR/"versions"/vid/"natives"),
                }
                cmd = minecraft_launcher_lib.command.get_minecraft_command(
                    version=vid, minecraft_directory=str(MC_DIR), options=options)
                flags = subprocess.CREATE_NO_WINDOW if sys.platform=="win32" else 0
                proc = subprocess.Popen(cmd, creationflags=flags)
                if self.boost_active.get():
                    # "above" (ABOVE_NORMAL) et non "high" : HIGH_PRIORITY_CLASS
                    # est trop agressif et peut affamer le CPU de tout le reste
                    # du système (launcher inclus, qui passe alors en "Ne répond
                    # pas") pendant les pics de charge du jeu (chargement de
                    # chunks, génération de monde...).
                    boost_process_priority(proc.pid, "above")
                    self._add_log("Priorité CPU du jeu augmentée (Sakura Mode)")
                self._mc_pid = proc.pid
                self._priority_boost_failed = False
                self.root.after(0, lambda: st.configure(text="Jeu lancé ! 🎮", text_color=GREEN))
                self.root.after(0, lambda: bar.set(1))
                self._add_log(f"{vid} lancé avec succès")
                self._stats = record_launch(uname)
                self.root.after(0, self._refresh_users_count_label)
                self.root.after(0, self._safe_refresh_members_list)
                self.root.after(0, lambda n=self._stats["launches"]: self._check_launch_trophies(n))
                self._report_launch_to_server(uname)
                self._rpc_update(state=f"En train de jouer {vid} — {uname}")
                if self.close_on_launch.get():
                    self.root.after(2000, self.root.destroy)
            except Exception as e:
                write_log("Lancement",e); msg=str(e)
                self.root.after(0, lambda: st.configure(text="Erreur",text_color=RED_C))
                self.root.after(0, lambda: messagebox.showerror("Erreur de lancement",msg))
        threading.Thread(target=run, daemon=True).start()

    def _install_ver(self, bar, st):
        vid = self.selected_id.get()
        if not vid: messagebox.showwarning("Attention","Sélectionne une version !"); return
        st.configure(text=f"Installation de {vid}...", text_color=ORANGE); bar.set(0)
        cb = make_cb(bar, st, self.root)
        self._add_log(f"Installation de {vid}")
        def run():
            try:
                minecraft_launcher_lib.install.install_minecraft_version(
                    vid, str(MC_DIR), callback=cb)
                self._installed = installed_ids()
                self.root.after(0, lambda: bar.set(1))
                self.root.after(0, lambda: st.configure(
                    text=f"✅ {vid} installé !", text_color=GREEN))
                self.root.after(0, self._pop_versions)
                self._add_log(f"{vid} installé")
            except Exception as e:
                write_log("Install",e); msg=str(e)
                self.root.after(0, lambda: messagebox.showerror("Erreur",msg))
        threading.Thread(target=run, daemon=True).start()

    # ─────────────────────────────────────────────────────────────────────────
    # Loaders
    # ─────────────────────────────────────────────────────────────────────────

    def _refresh_loader_vers(self):
        loader=self.loader_var.get(); mc=self.loader_mc.get().strip()
        self._loader_combo.configure(values=["Chargement..."])
        self.loader_ver.set("Chargement...")
        def fetch():
            try:
                vers=[]
                if loader=="Fabric":
                    raw=minecraft_launcher_lib.fabric.get_all_loader_versions()
                    for v in raw:
                        ldr=v.get("loader") if isinstance(v,dict) else None
                        ver=(ldr.get("version") if isinstance(ldr,dict) else None) or \
                            (v.get("version") if isinstance(v,dict) else None)
                        if ver: vers.append(str(ver))
                elif loader=="Quilt":
                    raw=minecraft_launcher_lib.quilt.get_all_loader_versions()
                    for v in raw:
                        ldr=v.get("loader") if isinstance(v,dict) else None
                        ver=(ldr.get("version") if isinstance(ldr,dict) else None) or \
                            (v.get("version") if isinstance(v,dict) else None)
                        if ver: vers.append(str(ver))
                elif loader=="Forge":
                    all_f=minecraft_launcher_lib.forge.list_forge_versions()
                    vers=[v for v in all_f if v.startswith(mc+"-")] if mc else all_f[:50]
                if not vers: vers=["(aucune)"]
                self.root.after(0,lambda: self._loader_combo.configure(values=vers))
                self.root.after(0,lambda: self.loader_ver.set(vers[0]))
            except Exception as e:
                write_log("Refresh loader",e)
                self.root.after(0,lambda: self.loader_ver.set("Erreur"))
        threading.Thread(target=fetch,daemon=True).start()

    def _install_loader(self):
        loader=self.loader_var.get(); mc=self.loader_mc.get().strip()
        lv=self.loader_ver.get().strip()
        if not mc: messagebox.showwarning("Attention","Indique la version Minecraft"); return
        if lv in ("Chargement...","Erreur","(aucune)","(dernière stable)",""): lv=None
        self._ld_st.configure(text=f"Installation {loader} {mc}...",text_color=ORANGE)
        self._ld_bar.set(0); cb=make_cb(self._ld_bar,self._ld_st,self.root)
        self._add_log(f"Installation {loader} pour {mc}")
        def run():
            try:
                minecraft_launcher_lib.install.install_minecraft_version(mc,str(MC_DIR),callback=cb)
                if loader=="Fabric":
                    kw={"loader_version":lv} if lv else {}
                    minecraft_launcher_lib.fabric.install_fabric(mc,str(MC_DIR),callback=cb,**kw)
                elif loader=="Quilt":
                    kw={"loader_version":lv} if lv else {}
                    minecraft_launcher_lib.quilt.install_quilt(mc,str(MC_DIR),callback=cb,**kw)
                elif loader=="Forge":
                    fv=lv or minecraft_launcher_lib.forge.find_forge_version(mc)
                    if not fv: raise RuntimeError(f"Aucune version Forge pour {mc}")
                    minecraft_launcher_lib.forge.install_forge_version(fv,str(MC_DIR),callback=cb)
                self._installed=installed_ids()
                self.root.after(0,lambda: self._ld_bar.set(1))
                self.root.after(0,lambda: self._ld_st.configure(
                    text=f"✅ {loader} installé !",text_color=GREEN))
                self.root.after(500,self._pop_versions)
                self._add_log(f"{loader} installé pour {mc}")
            except Exception as e:
                write_log(f"Install {loader}",e); msg=str(e)
                self.root.after(0,lambda: self._ld_st.configure(text="Erreur",text_color=RED_C))
                self.root.after(0,lambda: messagebox.showerror("Erreur",msg))
        threading.Thread(target=run,daemon=True).start()

    # ─────────────────────────────────────────────────────────────────────────
    # NeoForge
    # ─────────────────────────────────────────────────────────────────────────

    def _load_neo_versions(self):
        mc=self.neo_mc.get().strip()
        self._neo_combo.configure(values=["Chargement..."])
        self.neo_ver.set("Chargement...")
        def fetch():
            try:
                req=urllib.request.Request(NEOFORGE_API,headers={"User-Agent":"SakuraLauncher/2"})
                with urllib.request.urlopen(req,timeout=15) as r:
                    data=json.loads(r.read())
                all_v=data.get("versions",data) if isinstance(data,dict) else data
                if mc:
                    pfx=mc.lstrip("1.") if mc.startswith("1.") else mc
                    filtered=[v for v in all_v if str(v).startswith(pfx+".")]
                    if not filtered: filtered=list(all_v)
                else: filtered=list(all_v)
                filtered=list(reversed(filtered))
                if not filtered: filtered=["(aucune)"]
                self.root.after(0,lambda: self._neo_combo.configure(values=filtered))
                self.root.after(0,lambda: self.neo_ver.set(filtered[0]))
                self.root.after(0,lambda: self._neo_st.configure(
                    text=f"{len(filtered)} versions ✓",text_color=GREEN))
            except Exception as e:
                write_log("Load NeoForge versions",e)
                self.root.after(0,lambda: self._neo_st.configure(text="Erreur réseau",text_color=RED_C))
        threading.Thread(target=fetch,daemon=True).start()

    def _install_neoforge(self):
        nv=self.neo_ver.get().strip(); mc=self.neo_mc.get().strip()
        if not nv or nv in ("Chargement...","Erreur","(aucune)",""):
            messagebox.showwarning("Attention","Clique 🔄 pour charger les versions NeoForge !"); return
        jar_url=NEOFORGE_JAR.format(ver=nv)
        jar_tmp=BASE_DIR/f"neoforge-{nv}-installer.jar"
        self._neo_st.configure(text=f"Téléchargement NeoForge {nv}...",text_color=ORANGE)
        self._neo_bar.set(0); self._add_log(f"Installation NeoForge {nv}")
        def run():
            try:
                ensure_profiles()
                def hook(c,b,t):
                    if t>0: self.root.after(0,lambda: self._neo_bar.set(min(c*b/t*0.4,0.4)))
                urllib.request.urlretrieve(jar_url,str(jar_tmp),hook)
                self.root.after(0,lambda: self._neo_bar.set(0.4))
                if mc:
                    self.root.after(0,lambda: self._neo_st.configure(
                        text=f"Installation Minecraft {mc}...",text_color=ORANGE))
                    minecraft_launcher_lib.install.install_minecraft_version(mc,str(MC_DIR))
                self.root.after(0,lambda: self._neo_bar.set(0.6))
                self.root.after(0,lambda: self._neo_st.configure(
                    text="Installation NeoForge...",text_color=ORANGE))
                res=subprocess.run(["java","-jar",str(jar_tmp),"--install-client",str(MC_DIR)],
                    capture_output=True,text=True,timeout=300)
                if res.returncode!=0 and "unrecognized" in (res.stderr or "").lower():
                    res=subprocess.run(["java","-jar",str(jar_tmp),"--install-client"],
                        capture_output=True,text=True,timeout=300)
                jar_tmp.unlink(missing_ok=True)
                if res.returncode!=0:
                    raise RuntimeError((res.stderr or res.stdout or "Erreur")[:600])
                self._installed=installed_ids()
                self.root.after(0,lambda: self._neo_bar.set(1))
                self.root.after(0,lambda: self._neo_st.configure(
                    text=f"✅ NeoForge {nv} installé !",text_color=GREEN))
                self.root.after(500,self._pop_versions)
                self._add_log(f"NeoForge {nv} installé")
            except FileNotFoundError:
                jar_tmp.unlink(missing_ok=True)
                self.root.after(0,lambda: messagebox.showerror("Java introuvable",
                    "Java n'est pas dans le PATH.\nInstalle-le depuis java.com"))
            except Exception as e:
                jar_tmp.unlink(missing_ok=True)
                write_log("Install NeoForge",e); msg=str(e)
                self.root.after(0,lambda: self._neo_st.configure(text="Erreur",text_color=RED_C))
                self.root.after(0,lambda: messagebox.showerror("Erreur NeoForge",msg))
        threading.Thread(target=run,daemon=True).start()

    # ─────────────────────────────────────────────────────────────────────────
    # Misc actions
    # ─────────────────────────────────────────────────────────────────────────

    def _open_mods(self):
        open_in_file_manager(MODS_DIR)

    def _refresh_mods_list(self):
        try: sc=self._mods_scroll
        except: return
        for w in sc.winfo_children(): w.destroy()
        filt=""
        try: filt=self._mod_search.get().lower()
        except: pass
        mods=list(MODS_DIR.glob("*.jar"))
        if not mods:
            ctk.CTkLabel(sc,text="Aucun mod",text_color=TEXT3,
                         font=ctk.CTkFont(size=11)).pack(pady=6); return
        for mod in sorted(mods):
            if filt and filt not in mod.name.lower(): continue
            r=ctk.CTkFrame(sc,fg_color="transparent")
            r.pack(fill="x",pady=1)
            v=tk.BooleanVar(value=True)
            ctk.CTkCheckBox(r,text=mod.stem[:22],variable=v,
                            fg_color=ACCENT,checkmark_color=TEXT,
                            font=ctk.CTkFont(size=11),text_color=TEXT,
                            width=20).pack(side="left")
            sw=ctk.CTkSwitch(r,text="",variable=v,width=40,
                              progress_color=GREEN,button_color=ACCENT2)
            sw.pack(side="right")

    def _clear_cache(self):
        """Supprime les fichiers temporaires sans danger pour le jeu :
        installeurs téléchargés laissés en place après une erreur, vieux
        crash logs, et les .jar/.tmp orphelins dans le dossier du launcher.
        N'efface jamais assets/objects (ça forcerait un retéléchargement)."""
        try:
            freed = 0
            patterns = ["*-installer.jar", "*.tmp", "*.part"]
            for pat in patterns:
                for fp in BASE_DIR.glob(pat):
                    try:
                        freed += fp.stat().st_size
                        fp.unlink()
                    except Exception:
                        pass
            old_logs = MC_DIR / "logs"
            if old_logs.exists():
                cutoff = time.time() - 7*24*3600
                for fp in old_logs.glob("*.log.gz"):
                    try:
                        if fp.stat().st_mtime < cutoff:
                            freed += fp.stat().st_size
                            fp.unlink()
                    except Exception:
                        pass
            mb = round(freed/1e6, 1)
            self._add_log(f"Cache nettoyé : {mb} Mo libérés")
            messagebox.showinfo("Cache", f"Nettoyage terminé : {mb} Mo libérés.")
        except Exception as e:
            messagebox.showerror("Erreur", str(e))

    def _do_optimize(self):
        """Applique de vraies optimisations système avant de lancer le jeu :
        nettoyage du cache et purge DNS. On NE touche plus à la priorité du
        launcher lui-même : l'abaisser (BELOW_NORMAL) faisait que Windows le
        considérait "Ne répond pas" dès que Minecraft (boosté en priorité
        HAUTE séparément, voir boost_process_priority) sature le CPU — le
        launcher n'avait plus assez de temps CPU pour traiter ses propres
        messages de fenêtre. Le jeu a déjà son boost dédié, pas besoin de
        pénaliser le launcher pour ça."""
        actions = []
        self._clear_cache()
        actions.append("Cache nettoyé")
        if sys.platform == "win32":
            try:
                subprocess.run(["ipconfig", "/flushdns"], capture_output=True,
                                creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
                actions.append("Cache DNS vidé (latence serveur)")
            except Exception:
                pass
        self._add_log("Optimisation système : " + " · ".join(actions))
        messagebox.showinfo("Optimisation", "Optimisé !\n\n- " + "\n- ".join(actions))

    def _apply_jvm(self):
        ram = self.ram_mb.get()
        self._add_log(f"JVM appliqué (flags Aikar) : Xmx{ram}m")
        try:
            flags = aikar_jvm_flags(ram)
            self._jvm_preview.configure(text=" ".join(flags[:5]) + " ...")
        except Exception:
            pass

    def _apply_dns(self):
        dns=self._dns_combo.get()
        self._dns_lbl.configure(text=dns)
        self._add_log(f"DNS changé pour {dns}")

    def _test_ping(self):
        host=self._ping_entry.get().strip() or "1.1.1.1"
        self._do_ping(host, self._ping_result)

    def _do_ping(self, host, label):
        def run():
            ms=ping_host(host)
            if ms is not None:
                col=GREEN if ms<100 else ORANGE if ms<200 else RED_C
                self.root.after(0,lambda: label.configure(
                    text=f"Résultat : {ms} ms",text_color=col))
                self._add_log(f"Ping {host} : {ms}ms")
            else:
                self.root.after(0,lambda: label.configure(
                    text="Hôte inaccessible",text_color=RED_C))
        threading.Thread(target=run,daemon=True).start()

    def _test_network_stability(self, host="1.1.1.1", samples=8):
        """Mesure réelle de la stabilité réseau : envoie plusieurs sondes TCP
        successives et calcule latence moyenne, jitter (écart entre sondes)
        et taux de perte, pour donner un statut fiable (pas juste un ping)."""
        try:
            self._stab_dot.configure(text="● Mesure en cours...", text_color=TEXT2)
        except Exception:
            pass

        def run():
            results = []
            for _ in range(samples):
                ms = ping_host(host, timeout=1)
                results.append(ms)
                time.sleep(0.2)
            ok = [m for m in results if m is not None]
            loss_pct = round(100 * (samples - len(ok)) / samples)
            if ok:
                avg = round(sum(ok) / len(ok))
                jitter = round(max(ok) - min(ok)) if len(ok) > 1 else 0
            else:
                avg, jitter = None, None

            if not ok or loss_pct >= 50:
                status, color = "Hors ligne / instable", RED_C
            elif loss_pct > 0 or jitter is not None and jitter > 80 or avg is not None and avg > 200:
                status, color = "Instable", ORANGE
            elif avg is not None and avg < 80 and jitter is not None and jitter < 40:
                status, color = "Excellente", GREEN
            else:
                status, color = "Bonne", GREEN

            def upd():
                self._stab_dot.configure(text=f"● {status}", text_color=color)
                self._stab_latency.set(f"{avg} ms" if avg is not None else "--",
                                        GREEN if avg is not None and avg < 100 else ORANGE if avg is not None else RED_C)
                self._stab_jitter.set(f"{jitter} ms" if jitter is not None else "--")
                self._stab_loss.set(f"{loss_pct}%", GREEN if loss_pct == 0 else ORANGE if loss_pct < 50 else RED_C)
                self._add_log(f"Stabilité réseau : {status} (latence {avg}ms, jitter {jitter}ms, perte {loss_pct}%)")
            self.root.after(0, upd)
        threading.Thread(target=run, daemon=True).start()

    def _refresh_members_list(self):
        """Affiche la liste réelle des pseudos ayant lancé le jeu depuis ce
        launcher, en lisant le fichier de stats local (users_stats.json)."""
        self._stats = load_stats()
        users = self._stats.get("users", [])
        launches = self._stats.get("launches", 0)
        self._mem_count_lbl.configure(
            text=f"👤 {len(users)} membre(s) · {launches} lancement(s) au total")
        for w in self._mem_list_scroll.winfo_children():
            w.destroy()
        if not users:
            ctk.CTkLabel(self._mem_list_scroll, text="Aucun membre n'a encore lancé le jeu.",
                         text_color=TEXT3, font=ctk.CTkFont(size=11)).pack(pady=10)
            return
        current = self.username.get()
        for name in sorted(users, key=str.lower):
            r = ctk.CTkFrame(self._mem_list_scroll, fg_color="transparent")
            r.pack(fill="x", pady=2)
            ctk.CTkLabel(r, text=f"👤 {name}", text_color=TEXT,
                         font=ctk.CTkFont(size=12, weight="bold" if name == current else "normal")
                         ).pack(side="left", padx=4)
            if name == current:
                ctk.CTkLabel(r, text="(vous)", text_color=ACCENT2,
                             font=ctk.CTkFont(size=10)).pack(side="right", padx=6)

    def _start_background_optimizer(self):
        """Optimisation continue en arrière-plan, volontairement prudente :
        - ne libère JAMAIS que la mémoire du process du launcher lui-même
          (trim_own_memory), jamais celle du jeu ni du système
        - revérifie juste que le jeu garde bien sa priorité CPU "above
          normal" (au cas où un autre outil la remettrait à zéro), sans
          jamais monter plus haut (pas de HIGH/REALTIME, ça peut geler le PC)
        - ne touche à rien d'autre : pas de kill de process, pas de purge de
          cache système, pas de modification de services Windows
        Tourne toutes les 20s, seulement si le Sakura Mode est activé."""
        def loop():
            while True:
                time.sleep(20)
                if not self.boost_active.get():
                    continue
                try:
                    used, total = get_ram_usage()
                    if used and total and used / total > 0.90:
                        if trim_own_memory():
                            self._add_log(
                                f"RAM système élevée ({used}/{total} GB) : "
                                "mémoire du launcher libérée")
                except Exception:
                    pass
                pid = self._mc_pid
                if pid:
                    try:
                        import psutil
                        p = psutil.Process(pid)
                        if not p.is_running():
                            self._mc_pid = None
                            self._priority_boost_failed = False
                        elif sys.platform == "win32" and \
                                p.nice() != psutil.ABOVE_NORMAL_PRIORITY_CLASS:
                            # On ne retente qu'une fois après un échec : sinon,
                            # si le boost échoue en silence (ex: permissions),
                            # on spamme cette tentative + ce log toutes les
                            # 20s indéfiniment pendant toute la partie, pour
                            # rien — vu en pratique avec "Priorité CPU du jeu
                            # rétablie" répété en boucle dans les logs.
                            if not getattr(self, "_priority_boost_failed", False):
                                if boost_process_priority(pid, "above"):
                                    self._add_log("Priorité CPU du jeu rétablie (Sakura Mode)")
                                else:
                                    self._priority_boost_failed = True
                                    self._add_log(
                                        "Boost de priorité du jeu impossible "
                                        "(permissions ?) — abandon pour cette partie")
                    except Exception:
                        self._mc_pid = None
        threading.Thread(target=loop, daemon=True).start()

    def _start_presence_loops(self):
        """Lance en arrière-plan le heartbeat (envoi du pseudo au serveur de
        présence) et le polling de /online, pour afficher en temps réel les
        joueurs connectés depuis n'importe quel poste utilisant ce launcher."""
        def heartbeat_loop():
            while True:
                url = self.server_url.get().strip()
                uname = self.username.get().strip()
                if url and uname:
                    try:
                        req = urllib.request.Request(
                            url.rstrip("/") + "/heartbeat",
                            data=json.dumps({"username": uname}).encode("utf-8"),
                            headers={"Content-Type": "application/json"},
                            method="POST")
                        urllib.request.urlopen(req, timeout=3).read()
                    except Exception:
                        pass
                time.sleep(10)

        def poll_loop():
            while True:
                if self._is_minimized:
                    time.sleep(5)
                    continue
                url = self.server_url.get().strip()
                if url:
                    try:
                        req = urllib.request.Request(url.rstrip("/") + "/online", method="GET")
                        with urllib.request.urlopen(req, timeout=3) as resp:
                            data = json.loads(resp.read().decode("utf-8"))
                        self.root.after(0, lambda d=data: self._update_online_ui(d, True))
                    except Exception:
                        self.root.after(0, lambda: self._update_online_ui(None, False))
                else:
                    self.root.after(0, lambda: self._update_online_ui(None, None))
                time.sleep(5)

        def announcement_loop():
            while True:
                if self._is_minimized:
                    time.sleep(15)
                    continue
                url = self.server_url.get().strip()
                if url:
                    try:
                        req = urllib.request.Request(url.rstrip("/") + "/announcement", method="GET")
                        with urllib.request.urlopen(req, timeout=3) as resp:
                            data = json.loads(resp.read().decode("utf-8"))
                        self.root.after(0, lambda d=data: self._update_announcement_ui(d.get("announcement")))
                    except Exception:
                        pass
                time.sleep(15)

        def version_check_loop():
            # Vérifie au démarrage puis toutes les 30 min : si tu sors une
            # nouvelle version (en éditant LATEST_VERSION côté serveur), un
            # badge cliquable apparaît dans la sidebar, sous le compteur de
            # joueurs. Désactivable via le switch "Vérifier les mises à jour".
            while True:
                url = self.server_url.get().strip()
                if url and self.check_updates.get():
                    try:
                        req = urllib.request.Request(url.rstrip("/") + "/version", method="GET")
                        with urllib.request.urlopen(req, timeout=5) as resp:
                            data = json.loads(resp.read().decode("utf-8"))
                        self.root.after(0, lambda d=data: self._update_version_check_ui(d))
                    except Exception:
                        pass
                time.sleep(1800)

        threading.Thread(target=heartbeat_loop, daemon=True).start()
        threading.Thread(target=poll_loop, daemon=True).start()
        threading.Thread(target=announcement_loop, daemon=True).start()
        threading.Thread(target=version_check_loop, daemon=True).start()

    def _send_announcement(self, message):
        url = self.server_url.get().strip()
        uname = self.username.get().strip()
        if not url:
            messagebox.showwarning("Serveur non configuré", "Configure le serveur de présence dans Paramètres.")
            return
        def run():
            try:
                req = urllib.request.Request(
                    url.rstrip("/") + "/announce",
                    data=json.dumps({"username": uname, "message": message}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    ok = resp.status == 200
                if ok:
                    self.root.after(0, lambda: self._add_log(
                        "Annonce diffusée" if message else "Annonce effacée"))
                else:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Refusé", "Le serveur a refusé : tu n'es pas dans la liste des admins."))
            except urllib.error.HTTPError as e:
                if e.code == 403:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Refusé", "Tu n'es pas admin sur ce serveur de présence."))
                else:
                    self.root.after(0, lambda: messagebox.showerror("Erreur", str(e)))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Erreur", str(e)))
        threading.Thread(target=run, daemon=True).start()

    def _update_online_ui(self, data, connected):
        try:
            if connected is None:
                self._online_dot.configure(text="● Serveur non configuré", text_color=TEXT2)
                self._online_count_lbl.configure(text="")
                for w in self._online_scroll.winfo_children(): w.destroy()
                self._online_count, self._online_users = None, []
                return
            if not connected:
                self._online_dot.configure(text="● Serveur inaccessible", text_color=RED_C)
                self._online_count, self._online_users = None, []
                return
            users = data.get("online", [])
            admins = set(data.get("admins", []))
            current = self.username.get().strip()
            self._is_admin = current in admins
            if self._is_admin:
                self._unlock_trophy("admin")
            prev_count = self._online_count
            self._online_count, self._online_users = len(users), users
            self._online_dot.configure(text="● Connecté", text_color=GREEN)
            self._online_count_lbl.configure(text=f"🟢 {len(users)} joueur(s) en ligne")
            admin_badge = getattr(self, "_admin_badge_lbl", None)
            if admin_badge is not None:
                admin_badge.configure(text="🛡 Admin" if self._is_admin else "")
            for w in self._online_scroll.winfo_children(): w.destroy()
            if not users:
                ctk.CTkLabel(self._online_scroll, text="Personne en ligne actuellement.",
                             text_color=TEXT3, font=ctk.CTkFont(size=11)).pack(pady=10)
            else:
                for name in users:
                    tag = " (vous)" if name == current else ""
                    tag += " 🛡" if name in admins else ""
                    ctk.CTkLabel(self._online_scroll, text=f"🟢 {name}{tag}",
                                 text_color=TEXT, font=ctk.CTkFont(size=12,
                                 weight="bold" if name == current else "normal")
                                 ).pack(anchor="w", padx=4, pady=2)
            # Reflète le nombre réel de joueurs en ligne dans la Rich Presence
            # Discord (et pas juste quand on lance le jeu) dès qu'il change.
            if self._online_count != prev_count:
                self._rpc_update()
        except Exception:
            pass

    def _update_version_check_ui(self, data):
        """Affiche un badge cliquable dans la sidebar si la version annoncée
        par le serveur de présence (LATEST_VERSION) est plus récente que
        celle de ce launcher (APP_VERSION)."""
        badge = getattr(self, "_update_badge", None)
        if badge is None:
            return
        try:
            latest = str(data.get("latest", "")).strip()
            url = data.get("url") or None
            if not latest or not self._version_is_newer(latest, APP_VERSION):
                badge.pack_forget()
                return
            self._update_download_url = url
            badge.configure(text=f"⬆ Mise à jour v{latest} disponible")
            if not badge.winfo_ismapped():
                badge.pack(fill="x", pady=(6,0))
        except Exception:
            pass

    @staticmethod
    def _version_is_newer(remote, local):
        def parts(v):
            out = []
            for p in v.split("."):
                try: out.append(int(p))
                except ValueError: out.append(0)
            return out
        a, b = parts(remote), parts(local)
        n = max(len(a), len(b))
        a += [0]*(n-len(a)); b += [0]*(n-len(b))
        return a > b

    def _open_update_url(self):
        import webbrowser
        if self._update_download_url:
            webbrowser.open(self._update_download_url)
            self._add_log("Lien de mise à jour ouvert")
        else:
            messagebox.showinfo("Mise à jour", "Aucun lien de téléchargement fourni par le serveur.")

    def _update_announcement_ui(self, ann):
        """Affiche/masque la bannière d'annonce diffusée par un admin, sur la
        page Accueil. ann est None (pas d'annonce) ou {"message","by","at"}."""
        banner = getattr(self, "_announcement_banner", None)
        hero = getattr(self, "_accueil_hero", None)
        if banner is None or hero is None:
            return
        try:
            if not ann:
                banner.pack_forget()
                return
            banner.configure(text=f"📢 {ann.get('message','')}  —  par {ann.get('by','?')}")
            if not banner.winfo_ismapped():
                banner.pack(fill="x", padx=20, pady=(16,0), before=hero)
            self._announcement_seen_at = ann.get("at", self._announcement_seen_at)
        except Exception:
            pass

    def _report_launch_to_server(self, username):
        """Signale un lancement au serveur de présence pour le classement
        (nombre de lancements par joueur, toutes machines confondues)."""
        url = self.server_url.get().strip()
        if not url or not username:
            return
        def run():
            try:
                req = urllib.request.Request(
                    url.rstrip("/") + "/launch",
                    data=json.dumps({"username": username}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST")
                urllib.request.urlopen(req, timeout=5).read()
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()

    def _unlock_trophy(self, trophy_id):
        """Débloque un trophée localement (persisté dans trophies.json) et
        le signale au serveur de présence pour qu'il soit visible par les
        autres (classement, profil). Affiche un popup uniquement si c'est
        un VRAI premier déblocage (pas à chaque relance du launcher)."""
        if trophy_id in self._trophies:
            return  # déjà débloqué localement, rien à refaire
        if trophy_id not in TROPHIES:
            return
        self._trophies[trophy_id] = time.time()
        save_trophies(self._trophies)
        icon, name, desc = TROPHIES[trophy_id]
        self._add_log(f"Trophée débloqué : {icon} {name} — {desc}")
        self._show_trophy_popup(icon, name)
        grid = getattr(self, "_trophy_grid", None)
        if grid is not None:
            try: self._refresh_trophy_grid()
            except Exception: pass

        url = self.server_url.get().strip()
        uname = self.username.get().strip()
        if url and uname:
            def run():
                try:
                    req = urllib.request.Request(
                        url.rstrip("/") + "/trophy",
                        data=json.dumps({"username": uname, "trophy_id": trophy_id}).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST")
                    urllib.request.urlopen(req, timeout=5).read()
                except Exception:
                    pass
            threading.Thread(target=run, daemon=True).start()

    def _show_trophy_popup(self, icon, name):
        """Petit popup façon "succès débloqué" (Steam-like), en bas à droite
        de l'écran, qui disparaît seul après quelques secondes."""
        try:
            popup = tk.Toplevel(self.root)
            popup.overrideredirect(True)
            popup.attributes("-topmost", True)
            try:
                popup.attributes("-alpha", 0.96)
            except Exception:
                pass
            frame = ctk.CTkFrame(popup, fg_color=CARD, corner_radius=10,
                                  border_width=2, border_color=ACCENT)
            frame.pack(fill="both", expand=True)
            ctk.CTkLabel(frame, text=icon, font=ctk.CTkFont(size=28)).pack(
                side="left", padx=(14,8), pady=12)
            txt = ctk.CTkFrame(frame, fg_color="transparent")
            txt.pack(side="left", padx=(0,16), pady=12)
            ctk.CTkLabel(txt, text="Trophée débloqué !", text_color=ACCENT2,
                         font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w")
            ctk.CTkLabel(txt, text=name, text_color=TEXT,
                         font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w")

            self.root.update_idletasks()
            w, h = 280, 64
            x = self.root.winfo_x() + self.root.winfo_width() - w - 24
            y = self.root.winfo_y() + self.root.winfo_height() - h - 24
            popup.geometry(f"{w}x{h}+{x}+{y}")
            popup.after(4000, popup.destroy)
        except Exception:
            pass

    def _check_launch_trophies(self, launches_count):
        self._unlock_trophy("first_launch")
        if launches_count >= 10: self._unlock_trophy("launches_10")
        if launches_count >= 50: self._unlock_trophy("launches_50")
        if launches_count >= 200: self._unlock_trophy("launches_200")

    def _scan_minecraft_advancements(self):
        """Lit les fichiers de succès (advancements) de toutes les sauvegardes
        locales pour le pseudo/UUID courant, et débloque les trophées Sakura
        correspondants (préfixe mc_) pour ceux marqués "done": true. Lancé en
        arrière-plan (lecture disque), le déblocage lui-même revient sur le
        thread principal via _unlock_trophy (sûr à appeler depuis after())."""
        uname = self.username.get().strip()
        if not uname:
            return
        uid = (self._ms_account.get("id") if self._ms_account else None) or offline_uuid(uname)

        def run():
            found = set()
            saves_dir = MC_DIR / "saves"
            try:
                worlds = list(saves_dir.iterdir()) if saves_dir.exists() else []
            except Exception:
                worlds = []
            for world in worlds:
                adv_file = world / "advancements" / f"{uid}.json"
                try:
                    if adv_file.exists():
                        data = json.loads(adv_file.read_text("utf-8"))
                        for adv_id, info in data.items():
                            if isinstance(info, dict) and info.get("done") and adv_id.startswith("minecraft:"):
                                found.add(adv_id[len("minecraft:"):])
                except Exception:
                    continue
            matched = [k for k in MC_ADVANCEMENTS if k in found]
            if matched:
                self.root.after(0, lambda: [self._unlock_trophy(f"mc_{k}") for k in matched])
            else:
                self.root.after(0, lambda: self._add_log(
                    "Aucun nouveau succès Minecraft détecté dans les sauvegardes locales"))
        threading.Thread(target=run, daemon=True).start()

    def _add_log(self, msg):
        ts=datetime.datetime.now().strftime("%H:%M:%S")
        line=f"[{ts}] [INFO] {msg}"
        self._logs.append(line)
        if len(self._logs)>200: self._logs=self._logs[-200:]
        def upd():
            try:
                self._accueil_log.configure(state="normal")
                self._accueil_log.insert("end",line+"\n")
                self._accueil_log.see("end")
                self._accueil_log.configure(state="disabled")
            except: pass
            try:
                self._log_box.configure(state="normal")
                self._log_box.insert("end",line+"\n")
                self._log_box.see("end")
                self._log_box.configure(state="disabled")
            except: pass
        self.root.after(0,upd)

    def _clear_logs(self):
        self._logs=[]
        for w in [self._log_box, self._accueil_log]:
            try:
                w.configure(state="normal"); w.delete("1.0","end")
                w.configure(state="disabled")
            except: pass

    # ─────────────────────────────────────────────────────────────────────────
    # Real-time stats loop
    # ─────────────────────────────────────────────────────────────────────────

    def _start_stat_loop(self):
        self._add_log("Sakura Launcher démarré")
        self._add_log(f"Dossier Minecraft : {MC_DIR}")
        self._add_log("Prêt à lancer Minecraft")
        self._update_stats()

    def _update_stats(self):
        """Boucle persistante (un seul thread qui dort en interne) au lieu
        de créer un thread neuf toutes les 10s — moins d'overhead CPU sur
        toute la durée d'une session de jeu. Met aussi en pause le ping
        réseau quand la fenêtre est minimisée (personne ne regarde ces
        stats à ce moment-là), pour économiser CPU/réseau en arrière-plan
        sans rien changer de visible pour l'utilisateur."""
        def loop():
            while True:
                if getattr(self, "_is_minimized", False):
                    time.sleep(10)
                    continue
                used, total = get_ram_usage()
                ms = ping_host("1.1.1.1")
                def upd():
                    if used and total:
                        self._stat_ram.set(f"{used} / {total} GB")
                    ms_str = f"{ms} ms" if ms else "--"
                    col = GREEN if ms and ms<80 else ORANGE if ms and ms<200 else RED_C
                    self._stat_ping.set(ms_str, col)
                    self._stat_fps.set("-- (en jeu)")
                    self._stat_tps.set("20.0")
                self.root.after(0, upd)
                time.sleep(10)
        threading.Thread(target=loop, daemon=True).start()

    # ── Config persistence ────────────────────────────────────────────────────

    def _load_config(self) -> dict:
        try:
            cfg_path = BASE_DIR / "config.json"
            if cfg_path.exists():
                return json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save_config(self):
        try:
            cfg = self._cfg.copy()
            cfg["username"]   = self.username.get()
            cfg["skin_path"]  = self._skin_path.get()
            cfg["server_url"] = self.server_url.get()
            if self._ms_account: cfg["ms_account"] = self._ms_account
            (BASE_DIR / "config.json").write_text(
                json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self._cfg = cfg
        except Exception:
            pass

    # ── Compte Microsoft réel (OAuth officiel) ───────────────────────────────────

    def _ms_login(self):
        if MS_CLIENT_ID in ("", "ENTER_YOUR_AZURE_CLIENT_ID"):
            messagebox.showwarning(
                "Configuration requise",
                "Pour connecter un vrai compte Microsoft, un développeur doit "
                "enregistrer une application gratuite sur portal.azure.com et "
                "renseigner MS_CLIENT_ID dans sakura.py.\n\n"
                "Il n'existe aucun moyen légitime de contourner cette étape : "
                "c'est Microsoft qui authentifie le joueur, jamais le launcher.")
            return
        try:
            import webbrowser
            from minecraft_launcher_lib.microsoft_account import (
                get_login_url, get_auth_code_from_url, complete_login)
        except Exception as e:
            messagebox.showerror("Erreur", f"Module manquant : {e}"); return
        url = get_login_url(MS_CLIENT_ID, MS_REDIRECT_URI)
        webbrowser.open(url)
        pasted = simpledialog.askstring(
            "Connexion Microsoft",
            "Connecte-toi dans le navigateur, puis colle ici l'URL complète\n"
            "de la page de redirection (elle contient '?code=...') :")
        if not pasted:
            return
        try:
            code = get_auth_code_from_url(pasted)
            data = complete_login(MS_CLIENT_ID, None, MS_REDIRECT_URI, code)
        except Exception as e:
            write_log("MS login", e)
            messagebox.showerror("Connexion échouée", str(e)); return
        self._ms_account = data
        self._cfg["ms_account"] = data
        self.username.set(data.get("name", self.username.get()))
        self._save_config()
        try:
            self._ms_status_lbl.configure(
                text=f"● Connecté : {data.get('name','?')}", text_color=GREEN)
        except Exception: pass
        self._add_log(f"Compte Microsoft connecté : {data.get('name','?')}")

    def _ms_logout(self):
        self._ms_account = None
        self._cfg.pop("ms_account", None)
        self._save_config()
        try:
            self._ms_status_lbl.configure(text="● Non connecté", text_color=RED_C)
        except Exception: pass
        self._add_log("Compte Microsoft déconnecté")

    # ── Discord Rich Presence ─────────────────────────────────────────────────

    def _init_rpc(self):
        self._rpc = None
        self._rpc_start = int(time.time())
        self._rpc_last_state = "Au menu principal"
        self._online_count = None
        self._online_users = []
        def connect():
            try:
                from pypresence import Presence
                # Remplace par ton Application ID Discord (discord.com/developers)
                CLIENT_ID = "1519773031617007686"
                rpc = Presence(1519773031617007686)
                rpc.connect()
                self._rpc = rpc
                self._rpc_update("Au menu principal")
            except Exception as e:
                self._add_log(f"Discord RPC non disponible : {e}")
        threading.Thread(target=connect, daemon=True).start()

    def _rpc_update(self, state: str = None, details: str = None):
        """Met à jour la Rich Presence Discord. Affiche le nombre de joueurs
        RÉELLEMENT EN LIGNE maintenant (via le serveur de présence, si
        configuré) plutôt que le compteur local cumulé — ça reflète qui
        utilise vraiment Sakura à l'instant, pas juste l'historique de ce
        poste. Se replie sur le compteur local si aucun serveur n'est
        configuré ou injoignable."""
        if state is not None:
            self._rpc_last_state = state
        state = self._rpc_last_state
        if self._rpc is None:
            return
        live = self._online_count
        if live is not None:
            n_users = live
            label = "en ligne maintenant"
        else:
            n_users = len(self._stats["users"])
            label = "ont utilisé Sakura"
        if details is None:
            details = f"👤 {n_users} joueur(s) {label}"
        def upd():
            try:
                self._rpc.update(
                    state=state,
                    details=details,
                    large_image="sakura_logo",
                    large_text="Sakura Launcher",
                    small_text=f"{n_users} joueur(s) {label}",
                    party_id="sakura-launcher-panel",
                    party_size=[n_users, max(n_users, 99)],
                    start=self._rpc_start,
                )
            except Exception:
                pass
        threading.Thread(target=upd, daemon=True).start()

    def _safe_refresh_members_list(self):
        try:
            self._refresh_members_list()
        except Exception:
            pass

    def _refresh_users_count_label(self):
        try:
            self._users_count_lbl.configure(
                text=f"👤 {len(self._stats['users'])} joueur(s) · {self._stats['launches']} lancement(s)")
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


def _acquire_single_instance_lock():
    """Empêche deux instances du launcher de tourner en même temps : si une
    instance freeze ("Ne répond pas") et que l'utilisateur relance l'app, ça
    crée un 2e process qui se bat avec le 1er pour les mêmes fichiers
    (config.json, crash_log.txt, heartbeat vers le serveur de présence...),
    ce qui peut elle-même provoquer des blocages. On se réserve un port TCP
    local fixe : si le bind échoue, une instance tourne déjà.
    Le socket est gardé ouvert (référence module-level) tout le run pour que
    le verrou tienne jusqu'à la fermeture du process."""
    global _instance_lock_socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        s.bind(("127.0.0.1", 47821))
        s.listen(1)
        _instance_lock_socket = s
        return True
    except OSError:
        return False


if __name__ == "__main__":
    if not _acquire_single_instance_lock():
        try:
            root = tk.Tk(); root.withdraw()
            messagebox.showwarning(
                "Sakura Launcher déjà ouvert",
                "Une instance de Sakura Launcher est déjà en cours d'exécution.\n"
                "Ferme-la avant d'en relancer une nouvelle (vérifie aussi la barre "
                "des tâches/gestionnaire de tâches si tu ne vois aucune fenêtre).")
        except Exception:
            pass
        sys.exit(0)
    SakuraLauncher().run()
