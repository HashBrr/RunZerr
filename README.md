# RunZerr - Pipeline de Récupération des Données Huawei Santé (Watch GT 4)

Système autonome de collecte et d'indexation des données de course issues de **Huawei Santé** et de la **HUAWEI WATCH GT 4**.

---

## Structure du Projet

```text
RunZerr/
├── collector.py           # Collecteur ADB principal avec dédoublonnage MD5
├── auto_exporter.py       # Robot d'automatisation pour exporter l'historique sur le smartphone
├── sync.sh                # Raccourci d'exécution en 1 clic (./sync.sh)
├── sample_sporthealth.jpg # Échantillon réel haute définition (1080x13788px)
├── README.md              # Documentation
└── data/
    ├── raw_images/        # Fiches d'activités complètes téléchargées (.jpg)
    ├── tcx/               # Tracés GPS exportés (.tcx)
    └── manifest.json      # Index ordonné et hachages des données
```

---

## Guide d'Utilisation

### 1. Synchronisation rapide (Quotidienne ou après un export)
Quand votre téléphone est branché en USB avec le débogage activé :
```bash
./sync.sh
```
ou :
```bash
python3 collector.py
```
Le script rapatrie automatiquement les nouvelles fiches et met à jour `data/manifest.json`.

---

### 2. Exporter l'historique complet en masse (Robot ADB)
Pour ne pas avoir à ouvrir chaque course manuellement sur votre téléphone :
1. Déverrouillez votre smartphone et ouvrez l'écran **Historique des exercices** dans Huawei Santé.
2. Lancez le robot :
```bash
python3 auto_exporter.py
```
Le robot va automatiquement :
- Cliquer sur chaque séance.
- Cliquer sur *Partager ➔ Enregistrer l'image*.
- Revenir à la liste et passer à la suivante.

Dès que le robot a terminé, lancez `./sync.sh` pour tout rapatrier d'un coup dans `data/raw_images/` !

---

## Données disponibles dans chaque fiche (`data/raw_images/`)
Chaque capture (1080x13788px) contient :
- **Cardiofréquencemètre** : FC moyenne, FC max, courbe temporelle, 5 zones cardiaques.
- **Biomécanique GT 4** : Temps de contact pied/sol (ms), oscillation verticale (cm), équilibre G/D (%), cadence, longueur de foulée.
- **Physiologie & Récupération** : VO2Max (ml/kg/min), Training Effect, temps de récupération.
- **Allures & Splits** : Vitesse, allure moyenne, temps par kilomètre.

Toutes les données sont répertoriées dans `data/manifest.json` pour faciliter le traitement avec Claude Code.
