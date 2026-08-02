"""Interface commune que chaque store (GOG, Epic, EA, Ubisoft, Battle.net…)
doit implémenter. Un nouveau store = une nouvelle sous-classe de StoreClient,
sans rien changer au reste du launcher (bibliothèque, installation, Proton).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class GameInfo:
    store: str          # id du store, ex: "gog"
    id: str              # id du jeu chez ce store
    title: str
    cover_url: str | None = None


@dataclass
class DownloadInfo:
    url: str
    filename: str
    headers: dict | None = None   # en-têtes éventuels requis pour le téléchargement


class StoreNotImplementedError(NotImplementedError):
    """Levée par les stores pas encore intégrés (Epic, EA, Ubisoft, Battle.net…)."""


class StoreClient(ABC):
    store_id: str = "base"
    display_name: str = "Store"

    @abstractmethod
    def is_authenticated(self) -> bool:
        ...

    @abstractmethod
    def login(self) -> None:
        """Flow de connexion interactif (imprime une URL, demande un code…)."""

    @abstractmethod
    def logout(self) -> None:
        ...

    @abstractmethod
    def list_owned_games(self) -> list[GameInfo]:
        ...

    @abstractmethod
    def get_download_info(self, game_id: str) -> DownloadInfo:
        """Retourne l'URL (et en-têtes) pour télécharger l'installateur Windows du jeu."""
