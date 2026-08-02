"""Intégration EA App — pas encore implémentée.

EA App n'a pas d'API publique documentée. À implémenter en suivant le même
protocole StoreClient que gog.py une fois le flow d'auth reverse-ingénié
(voir des projets comme Nucleus/EA App reversing pour référence)."""
from __future__ import annotations

from stores.base import DownloadInfo, GameInfo, StoreClient, StoreNotImplementedError


class EaClient(StoreClient):
    store_id = "ea"
    display_name = "EA App"

    def is_authenticated(self) -> bool:
        return False

    def login(self) -> None:
        raise StoreNotImplementedError("L'intégration EA App n'est pas encore disponible.")

    def logout(self) -> None:
        pass

    def list_owned_games(self) -> list[GameInfo]:
        return []

    def get_download_info(self, game_id: str) -> DownloadInfo:
        raise StoreNotImplementedError("L'intégration EA App n'est pas encore disponible.")
