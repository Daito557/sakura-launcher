# Proton Manager

Outil en ligne de commande, indépendant de Sakura Launcher, pour gérer des
versions de Proton/GE-Proton, créer des préfixes Wine par jeu, et lancer des
exécutables Windows (`.exe`) sous Linux.

Aucune intégration de store (Steam/GOG/Epic/etc.) — uniquement la couche
Proton/Wine.

## Prérequis

- Python 3.9+
- Linux avec Steam installé (pour les versions Proton officielles) et/ou
  `winetricks` si vous voulez l'utiliser
- Accès réseau pour télécharger GE-Proton depuis GitHub

## Utilisation

```bash
# Lister les versions Proton détectées (Steam + GE-Proton installées par cet outil)
python3 proton_manager.py list-versions

# Télécharger la dernière GE-Proton
python3 proton_manager.py install-ge

# Créer un préfixe Wine pour un jeu avec une version Proton donnée
python3 proton_manager.py create-prefix "Mon Jeu" --proton GE-Proton9-20

# Associer un exécutable à un jeu
python3 proton_manager.py add-game "Mon Jeu" /chemin/vers/setup.exe --proton GE-Proton9-20

# Lister les jeux configurés
python3 proton_manager.py list-games

# Lancer un jeu
python3 proton_manager.py run "Mon Jeu"

# Installer des dépendances Windows courantes via winetricks
python3 proton_manager.py winetricks "Mon Jeu" corefonts vcrun2019

# Supprimer le préfixe d'un jeu
python3 proton_manager.py delete-prefix "Mon Jeu"
```

## Emplacement des données

- Config : `~/.config/proton-manager/config.json`
- Versions GE-Proton téléchargées : `~/.local/share/proton-manager/versions/`
- Préfixes Wine : `~/.local/share/proton-manager/prefixes/<jeu>/`

## Limites connues

- Pas de gestion multi-store (Steam/GOG/Epic/Ubisoft/Battle.net) — c'est un
  autre chantier, volontairement hors périmètre ici.
- Pas d'interface graphique (CLI uniquement).
- Détection Proton limitée aux emplacements standards Steam
  (`compatibilitytools.d`, `steamapps/common`) et au dossier de cet outil.
