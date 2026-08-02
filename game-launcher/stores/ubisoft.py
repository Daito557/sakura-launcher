"""Intégration Ubisoft Connect — pas encore implémentée. Même remarque que
pour EA : pas d'API publique, protocole à reverse-ingénier avant de suivre
le même modèle StoreClient que gog.py."""
from __future__ import annotations

from stores.base import DownloadInfo, GameInfo, StoreClient, StoreNotImplementedError


class UbisoftClient(StoreClient):
    store_id = "ubisoft"
    display_name = "Ubisoft Connect"

    def is_authenticated(self) -> bool:
        return False

    def login(self) -> None:
        raise StoreNotImplementedError("L'intégration Ubisoft Connect n'est pas encore disponible.")

    def logout(self) -> None:
        pass

    def list_owned_games(self) -> list[GameInfo]:
        return []

    def get_download_info(self, game_id: str) -> DownloadInfo:
        raise StoreNotImplementedError("L'intégration Ubisoft Connect n'est pas encore disponible.")
