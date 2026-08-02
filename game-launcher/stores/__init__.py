"""Registre des stores disponibles. Ajouter un store = ajouter une entrée ici
après avoir écrit sa classe StoreClient dans un nouveau module."""
from __future__ import annotations

from stores.base import StoreClient
from stores.battlenet import BattleNetClient
from stores.ea import EaClient
from stores.epic import EpicClient
from stores.gog import GogClient
from stores.steam import SteamClient
from stores.ubisoft import UbisoftClient

STORE_CLASSES: list[type[StoreClient]] = [
    SteamClient,
    GogClient,
    EpicClient,
    EaClient,
    UbisoftClient,
    BattleNetClient,
]


def make_all_stores() -> dict[str, StoreClient]:
    return {cls.store_id: cls() for cls in STORE_CLASSES}
