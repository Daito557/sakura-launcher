"""Bibliothèque locale des jeux installés (tous stores confondus)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from config import LIBRARY_FILE


@dataclass
class InstalledGame:
    store: str
    id: str
    title: str
    proton_version: str
    prefix: str
    exe_path: str
    launch_args: list[str] = field(default_factory=list)
    env_vars: dict[str, str] = field(default_factory=dict)
    fullscreen: bool = True
    version: str = ""


def _load() -> dict:
    if LIBRARY_FILE.exists():
        try:
            return json.loads(LIBRARY_FILE.read_text("utf-8"))
        except Exception:
            pass
    return {"games": {}}


def _save(data: dict) -> None:
    LIBRARY_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")


def key_for(store: str, game_id: str) -> str:
    return f"{store}:{game_id}"


def add_game(game: InstalledGame) -> None:
    data = _load()
    data["games"][key_for(game.store, game.id)] = asdict(game)
    _save(data)


def remove_game(store: str, game_id: str) -> None:
    data = _load()
    data["games"].pop(key_for(store, game_id), None)
    _save(data)


def get_game(store: str, game_id: str) -> InstalledGame | None:
    data = _load()
    raw = data["games"].get(key_for(store, game_id))
    return InstalledGame(**raw) if raw else None


def list_games() -> list[InstalledGame]:
    data = _load()
    return [InstalledGame(**raw) for raw in data["games"].values()]
