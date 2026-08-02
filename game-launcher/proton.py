"""Détection des versions Proton et lancement des jeux à travers elles.

Repris du module autonome proton-manager (mêmes conventions de préfixes),
pour que la logique Proton reste cohérente entre les deux outils sans que
l'un dépende de l'autre.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

from config import DATA_DIR, PREFIXES_DIR

VERSIONS_DIR = DATA_DIR / "proton-versions"

STEAM_COMPAT_TOOLS_DIRS = [
    Path.home() / ".steam" / "steam" / "compatibilitytools.d",
    Path.home() / ".local" / "share" / "Steam" / "compatibilitytools.d",
]
STEAM_COMMON_DIRS = [
    Path.home() / ".steam" / "steam" / "steamapps" / "common",
    Path.home() / ".local" / "share" / "Steam" / "steamapps" / "common",
]

GE_PROTON_API = "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases/latest"


def find_proton_versions() -> dict[str, Path]:
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


def install_latest_ge(force: bool = False) -> str:
    req = urllib.request.Request(GE_PROTON_API, headers={"User-Agent": "sakura-game-launcher"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        release = json.loads(resp.read().decode("utf-8"))

    tag = release.get("tag_name", "unknown")
    asset = next((a for a in release.get("assets", []) if a["name"].endswith(".tar.gz")), None)
    if not asset:
        raise RuntimeError("Impossible de trouver l'archive .tar.gz dans la release GE-Proton.")

    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    dest_dir = VERSIONS_DIR / tag
    if dest_dir.exists() and not force:
        return tag

    archive_path = VERSIONS_DIR / asset["name"]
    urllib.request.urlretrieve(asset["browser_download_url"], archive_path)
    with tarfile.open(archive_path) as tar:
        tar.extractall(VERSIONS_DIR)
    archive_path.unlink()
    return tag


def prefix_path_for(game_key: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in game_key)
    return PREFIXES_DIR / safe


def _env_for_prefix(prefix: Path) -> dict:
    env = os.environ.copy()
    env["STEAM_COMPAT_DATA_PATH"] = str(prefix)
    compat_client = env.get("STEAM_COMPAT_CLIENT_INSTALL_PATH") or str(DATA_DIR / "compat-client")
    Path(compat_client).mkdir(parents=True, exist_ok=True)
    env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = compat_client
    return env


def init_prefix(proton_bin: Path, prefix: Path) -> None:
    prefix.mkdir(parents=True, exist_ok=True)
    env = _env_for_prefix(prefix)
    subprocess.run([str(proton_bin), "run", "wineboot", "--init"], env=env, check=True)


def run_installer(proton_bin: Path, prefix: Path, installer_path: Path, silent_args: list[str]) -> None:
    """Lance un installateur Windows (.exe) dans le préfixe donné."""
    env = _env_for_prefix(prefix)
    subprocess.run(
        [str(proton_bin), "waitforexitandrun", str(installer_path), *silent_args],
        env=env,
        check=True,
    )


def run_game(
    proton_bin: Path,
    prefix: Path,
    exe_path: Path,
    extra_args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
) -> None:
    env = _env_for_prefix(prefix)
    env.update(extra_env or {})
    subprocess.run(
        [str(proton_bin), "waitforexitandrun", str(exe_path), *(extra_args or [])],
        env=env,
    )
