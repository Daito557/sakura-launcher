"""Intégration Battle.net — pas encore implémentée. Battle.net utilise le
protocole propriétaire Blizzard Agent/CASC ; l'intégration la plus réaliste
consisterait à s'appuyer sur des outils existants (ex: wine-battlenet
projects) plutôt que reverse-ingénier CASC from scratch. À faire suivre le
même modèle StoreClient que gog.py une fois cette décision prise."""
from __future__ import annotations

from stores.base import DownloadInfo, GameInfo, StoreClient, StoreNotImplementedError


class BattleNetClient(StoreClient):
    store_id = "battlenet"
    display_name = "Battle.net"

    def is_authenticated(self) -> bool:
        return False

    def login(self) -> None:
        raise StoreNotImplementedError("L'intégration Battle.net n'est pas encore disponible.")

    def logout(self) -> None:
        pass

    def list_owned_games(self) -> list[GameInfo]:
        return []

    def get_download_info(self, game_id: str) -> DownloadInfo:
        raise StoreNotImplementedError("L'intégration Battle.net n'est pas encore disponible.")
