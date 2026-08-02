# Sakura Game Launcher

Launcher multi-store pour Linux (style Heroic Games Launcher), indépendant de
Sakura Launcher (dédié à Minecraft). Objectif : centraliser vos jeux
GOG / Epic / EA / Ubisoft Connect / Battle.net et les lancer via Proton, avec
une installation simple.

## État actuel

| Store            | Statut                                                        |
|------------------|----------------------------------------------------------------|
| GOG              | ✅ Fonctionnel : login, bibliothèque, téléchargement, install, run |
| Steam            | ✅ Fonctionnel : login (clé API), bibliothèque, lancement (Steam gère le téléchargement/Proton lui-même) |
| Epic Games Store | 🚧 Stub — pas d'API publique, à reverse-ingénier                |
| EA App           | 🚧 Stub                                                         |
| Ubisoft Connect  | 🚧 Stub                                                         |
| Battle.net       | 🚧 Stub                                                         |

Chaque store est une classe `StoreClient` (voir `stores/base.py`) : ajouter
un store ne touche à rien d'autre — bibliothèque, installation et gestion
Proton sont génériques.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Utilisation en ligne de commande (`cli.py`)

```bash
python3 cli.py stores                    # état de connexion par store
python3 cli.py login gog                 # se connecter à GOG
python3 cli.py login steam               # se connecter à Steam (clé API + SteamID64)
python3 cli.py library steam             # lister les jeux possédés sur Steam
python3 cli.py run steam <appid>         # lancer un jeu Steam déjà installé
python3 cli.py library gog               # lister les jeux possédés sur GOG
python3 cli.py install-ge                # télécharger la dernière GE-Proton
python3 cli.py proton-versions           # versions Proton détectées

python3 cli.py install-game gog 1234567890 \
    --title "Mon Jeu" --proton GE-Proton9-20 --exe "Game.exe"

python3 cli.py run gog 1234567890        # lancer le jeu installé
python3 cli.py installed                 # lister les jeux installés localement

# Ajouter un jeu déjà installé (hors store), avec sa propre config Proton/Wine
python3 cli.py add-custom-game \
    --title "Mon Jeu Itch.io" \
    --exe "/home/user/Jeux/MonJeu/game.exe" \
    --proton GE-Proton9-20 \
    --arg "-windowed" \
    --env "DXVK_HUD=fps" --env "PROTON_LOG=1"
    # --prefix /chemin/vers/prefixe-existant   (optionnel, sinon un nouveau préfixe est créé)

python3 cli.py run custom mon-jeu-itchio  # id auto-généré depuis le titre (slug)
```

## Interface graphique

```bash
python3 ui/app.py
```

Mêmes fonctionnalités que le CLI (connexion par store, bibliothèque en
ligne, installation guidée, versions Proton, lancement) dans une interface
customtkinter, plus un bouton "+ Ajouter un jeu manuellement" pour un jeu
hors store avec sa propre config Proton/Wine (exe, version, préfixe,
arguments de lancement, variables d'environnement).

## Architecture

```
config.py           chemins (~/.config, ~/.local/share)
proton.py            détection/téléchargement Proton, lancement des jeux
library.py           bibliothèque locale des jeux installés (JSON)
install_manager.py   orchestration : téléchargement -> préfixe -> install -> run
stores/
  base.py             interface StoreClient (à implémenter par store)
  gog.py              implémentation GOG (fonctionnelle)
  steam.py            implémentation Steam (fonctionnelle, lecture seule + lancement)
  epic.py, ea.py, ubisoft.py, battlenet.py   stubs
cli.py                interface en ligne de commande
ui/app.py             interface graphique customtkinter
```

## Limites connues

- L'installation silencieuse suppose un installateur NSIS (`/S`) ; certains
  jeux GOG utilisent InnoSetup ou un autre format et nécessiteront un ajustement
  des arguments dans `install_manager.py`.
- Il faut indiquer manuellement le chemin de l'exécutable après installation
  (`--exe`), le launcher ne le détecte pas automatiquement.
- Epic/EA/Ubisoft/Battle.net ne sont pas encore implémentés : pas d'API
  publique documentée, contrairement à GOG.
- Steam est en lecture seule côté launcher (bibliothèque + lancement) : les
  installations/mises à jour de jeux passent toujours par le client Steam,
  qui gère déjà très bien Proton nativement.
