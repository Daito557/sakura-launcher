"""Intégration Epic Games Store — pas encore implémentée.

Contrairement à GOG, Epic n'a pas d'API publique officielle : les outils
existants (Legendary, Heroic) émulent le client officiel via une API non
documentée qui change régulièrement. À implémenter dans un second temps en
suivant le même protocole StoreClient que gog.py.
"""
from __future__ import annotations

from stores.base import DownloadInfo, GameInfo, StoreClient, StoreNotImplementedError


class EpicClient(StoreClient):
    store_id = "epic"
    display_name = "Epic Games Store"

    def is_authenticated(self) -> bool:
        return False

    def login(self) -> None:
        raise StoreNotImplementedError("L'intégration Epic Games Store n'est pas encore disponible.")

    def logout(self) -> None:
        pass

    def list_owned_games(self) -> list[GameInfo]:
        return []

    def get_download_info(self, game_id: str) -> DownloadInfo:
        raise StoreNotImplementedError("L'intégration Epic Games Store n'est pas encore disponible.")
