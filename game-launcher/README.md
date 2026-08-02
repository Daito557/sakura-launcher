# Sakura Game Launcher

Launcher multi-store pour Linux (style Heroic Games Launcher), indépendant de
Sakura Launcher (dédié à Minecraft). Objectif : centraliser vos jeux
GOG / Steam / Epic / EA / Ubisoft Connect / Battle.net, les lancer via Proton
avec une installation simple, des réglages par jeu, un plein écran forcé et
des mises à jour automatiques.

## État actuel

| Store            | Statut                                                        |
|------------------|----------------------------------------------------------------|
| GOG              | ✅ Fonctionnel : login, bibliothèque, téléchargement, install, run, mises à jour |
| Steam            | ✅ Fonctionnel : login (clé API), bibliothèque, lancement (Steam gère le téléchargement/Proton lui-même) |
| Jeux personnalisés | ✅ Fonctionnel : n'importe quel exécutable Windows, config Proton/Wine complète |
| Epic Games Store | 🚧 Stub — pas d'API publique, à reverse-ingénier                |
| EA App           | 🚧 Stub                                                         |
| Ubisoft Connect  | 🚧 Stub                                                         |
| Battle.net       | 🚧 Stub                                                         |

Chaque store est une classe `StoreClient` (voir `stores/base.py`) : ajouter
un store ne touche à rien d'autre — bibliothèque, installation et gestion
Proton sont génériques.

## Fonctionnalités

- **Proton/Wine automatique** : au démarrage, si aucune version n'est
  détectée, la dernière GE-Proton est téléchargée automatiquement
  (`proton.ensure_proton_available()`). `--proton auto` fait de même en CLI.
- **Plein écran forcé** : activé par défaut sur chaque jeu. Si `gamescope`
  est installé, il est utilisé comme compositeur plein écran dédié (même
  approche que Heroic/Lutris) ; sinon un argument `-fullscreen` best-effort
  est ajouté. Désactivable par jeu.
- **Réglages par jeu** : version Proton, arguments de lancement, variables
  d'environnement (`DXVK_HUD`, `PROTON_LOG`, etc.), plein écran — modifiables
  après installation, sans réinstaller.
- **Mises à jour** : `check-updates`/`update-game`/`update-all` en CLI,
  bouton "Vérifier les mises à jour" en GUI. Compare la version installée à
  la dernière version publiée par le store (GOG pour l'instant).
- **Désinstallation** propre (préfixe Wine + fichiers installés).

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
python3 cli.py library gog               # lister les jeux possédés sur GOG
python3 cli.py library steam             # lister les jeux possédés sur Steam
python3 cli.py proton-versions           # versions Proton détectées
python3 cli.py install-ge                # forcer le téléchargement de la dernière GE-Proton

# --proton auto : télécharge/utilise automatiquement la dernière GE-Proton
python3 cli.py install-game gog 1234567890 \
    --title "Mon Jeu" --proton auto --exe "Game.exe"
    # --windowed pour désactiver le plein écran forcé

python3 cli.py run gog 1234567890        # lancer le jeu installé
python3 cli.py run steam <appid>         # lancer un jeu Steam déjà installé
python3 cli.py installed                 # lister les jeux installés localement

# Ajouter un jeu déjà installé (hors store), avec sa propre config Proton/Wine
python3 cli.py add-custom-game \
    --title "Mon Jeu Itch.io" \
    --exe "/home/user/Jeux/MonJeu/game.exe" \
    --proton auto \
    --arg "-windowed" \
    --env "DXVK_HUD=fps" --env "PROTON_LOG=1"
    # --prefix /chemin/vers/prefixe-existant   (optionnel, sinon un nouveau préfixe est créé)

python3 cli.py run custom mon-jeu-itchio  # id auto-généré depuis le titre (slug)

# Modifier la config d'un jeu déjà installé, sans le réinstaller
python3 cli.py configure-game gog 1234567890 --proton GE-Proton9-22 --windowed

# Désinstaller (supprime préfixe + fichiers par défaut)
python3 cli.py uninstall-game gog 1234567890

# Mises à jour
python3 cli.py check-updates             # liste les jeux avec une mise à jour dispo
python3 cli.py update-game gog 1234567890
python3 cli.py update-all                # met à jour tout ce qui peut l'être
```

## Interface graphique

```bash
python3 ui/app.py
```

Barre latérale à gauche : **Bibliothèque** (jeux installés, avec boutons
Lancer/⚙ Réglages/Désinstaller et badge de mise à jour), un bouton par
**store**, et **⚙ Paramètres** (versions Proton, connexions aux stores) en
bas. Le panneau de droite affiche le contenu sélectionné, y compris un
panneau de réglages dédié par jeu (Proton, arguments, variables
d'environnement, interrupteur plein écran).

Au démarrage, le launcher vérifie/télécharge automatiquement une version de
Proton en arrière-plan (statut affiché en haut de la barre latérale).

## Architecture

```
config.py            chemins (~/.config, ~/.local/share)
proton.py             détection/téléchargement Proton, lancement des jeux (plein écran via gamescope)
library.py            bibliothèque locale des jeux installés (JSON)
install_manager.py    orchestration : téléchargement -> préfixe -> install -> run -> update -> uninstall
stores/
  base.py              interface StoreClient (à implémenter par store)
  gog.py               implémentation GOG (fonctionnelle, avec détection de version pour les mises à jour)
  steam.py             implémentation Steam (fonctionnelle, lecture seule + lancement)
  epic.py, ea.py, ubisoft.py, battlenet.py   stubs
cli.py                 interface en ligne de commande
ui/app.py              interface graphique customtkinter (Bibliothèque / Stores / Paramètres)
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
- Le plein écran "forcé" dépend de `gamescope` pour être garanti ; sans lui,
  c'est un best-effort (argument `-fullscreen`) qui ne fonctionne pas avec
  tous les moteurs de jeu.
- La détection de mise à jour ne fonctionne que pour GOG pour l'instant
  (seul store exposant une notion de version côté API).
