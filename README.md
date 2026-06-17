# GML Edge Telematics — POC

**MBA Big Data & IA — Bloc 2 — GreenMove Logistics**
Role : CTO | Flotte : 50 camions | Python 3.10+

---

## Objectif

Prouver localement la faisabilite de deux fonctionnalites critiques du pivot Edge Computing :

1. **Moteur ZFE** — Detection d'entree en Zone a Faibles Emissions sans reseau (mode offline)
2. **Moteur Safety** — Detection de freinage violent depuis les donnees accelerometre

---

## Prerequis

- Python 3.10 ou superieur
- colorama (affichage couleur dans PowerShell / CMD)

```bash
pip install colorama
```

Aucune autre dependance externe. Bibliotheque standard Python uniquement.

---

## Structure du projet

```
gml-edge-telematics-poc/
├── src/
│   └── main.py                   # Moteurs ZFE et Safety (avec couleurs)
├── data/
│   ├── lyon_polygon.json          # Polygone ZFE Lyon (4 sommets)
│   ├── truck_gps.json             # Trace GPS de test (5 points)
│   └── accelerometer_data.csv     # Donnees capteur 100 Hz (10 echantillons)
├── output/                        # Genere a l'execution (vide au depart)
│   ├── zfe_alerts.log             # Alertes ZFE horodatees
│   └── daily_score.json           # Score conducteur + evenements Safety
├── docs/
│   └── poc_screens/               # Captures d'ecran de la demonstration
├── run_tests.py                   # Tests de non-regression (11/11 PASS)
└── README.md                      # Ce fichier
```

---

## Execution

### Sous Windows (PowerShell)

```powershell
# Aller dans le dossier du projet
cd C:\chemin\vers\gml-edge-telematics-poc

# Nettoyer les sorties precedentes (optionnel)
Remove-Item output\*.log, output\*.json -ErrorAction SilentlyContinue

# Lancer le POC
python src/main.py

# Lancer les tests de non-regression
python run_tests.py
```

### Sous Linux / macOS

```bash
cd gml-edge-telematics-poc
rm -f output/*.log output/*.json
python src/main.py
python run_tests.py
```

---

## Sorties attendues

### Console (python src/main.py)

```
================================================================
 GML EDGE TELEMATICS - POC (mode offline)
================================================================
--- Moteur 1 : ZFE (Geo) -------------------------------------
[ZFE] Bounding Box pre-filtre : lat[45.73,45.79] lon[4.80,4.88]
       point 1 | attendu=OUT | detecte=OUT | dist bord=5560 m
       point 2 | attendu=OUT | detecte=OUT | dist bord=3336 m
[PRE-ALERT ZFE] point=3 ts=08:00:20 approche zone (dist bord=389 m)
[ALERT ZFE] point=4 ts=08:00:30 lat=45.76 lon=4.8357 (dist bord=2769 m)
[ALERT ZFE] point=5 ts=08:00:40 lat=45.75 lon=4.85 (dist bord=2224 m)
--- Moteur 2 : Safety (Physics) ------------------------------
[SAFETY] Freinage violent : ts=1678880005 acc_y=-3.45 m/s2 (seuil -2.5) severite=HIGH
--- Synthese --------------------------------------------------
ZFE   : 2 entree(s) en zone, 1 pre-alerte(s) d'approche
Safety: 1 freinage(s) violent(s) | score conducteur = 85/100
================================================================
```

### Tests de non-regression (python run_tests.py)

```
============================================================
 GML POC - Tests de non-regression
============================================================
[TEST] Moteur ZFE :
  [PASS] Point 1 = OUT
  [PASS] Point 2 = OUT
  [PASS] Point 3 = PRE_ALERT
  [PASS] Point 4 = IN
  [PASS] Point 5 = IN
[TEST] Moteur Safety :
  [PASS] 1 freinage violent detecte
  [PASS] Score conducteur = 85/100
  [PASS] Valeur min acc_y = -3.45
  [PASS] Severite = HIGH
[TEST] Fichiers de sortie :
  [PASS] output/zfe_alerts.log existe
  [PASS] output/daily_score.json existe
============================================================
 Bilan : 11/11 tests passes
 SUCCES - POC valide pour la demonstration
============================================================
```

---

## Algorithmes

### Moteur ZFE

| Etape | Algorithme | Complexite | Role |
|---|---|---|---|
| 1 | Bounding Box | O(1) | Rejet rapide des positions hors rectangle |
| 2 | Ray Casting | O(N) | Detection precise dans le polygone |
| 3 | Distance au bord | O(N) | Pre-alerte a moins de 500m de la frontiere |

### Moteur Safety

- Seuil : -2.5 m/s2 sur l'axe Y longitudinal
- Note : l'enonce indique 2.5G = 24.5 m/s2, impossible pour un camion. Le CSV est en m/s2.
- Severite HIGH (-15 pts) si -5.0 < acc_y <= -2.5
- Severite SEVERE (-25 pts) si acc_y <= -5.0
- Score final = max(0, 100 - penalites)

---

## Ambiguites de l'enonce traitees

**Seuil de freinage** : L'enonce indique "> 2.5G". 2.5G = 24.5 m/s2, valeur physiquement
impossible pour un camion (max reel : 0.7 a 0.9G = 7 a 9 m/s2). Le CSV contient des m/s2.
Seuil retenu : -2.5 m/s2.

**Point GPS 3 (bordure)** : Annote "IN (Bordure)" dans l'enonce mais geometriquement situe
a 389m au nord du polygone. Le moteur retourne la verite geometrique (hors zone) et declenche
une PRE_ALERT via la bande des 500m. Comportement metier correct : alerter AVANT la frontiere.

---

## Limites du POC

- Donnees simulees, non issues d'une vraie tablette Zebra ET40
- Bruit capteur non modelise (en production : filtre Kalman ou moyenne mobile)
- Pas de persistance SQLite (en production : base embarquee pour le flux 100 Hz)
- Pas de chiffrement local (en production : AES-256 + MDM)
- Pas de synchronisation 4G differee (en production : upload des agregats au retour reseau)

---

## Contexte business

| Indicateur | Valeur |
|---|---|
| Investissement CAPEX | 35 000 EUR |
| Mois de rentabilite | Mois 7 |
| Gain net 36 mois (scenario central) | 279 100 EUR |
| ROI | 384 % |
| Reduction transmission 4G | Facteur > 1 000 |

---

## Auteur

GreenMove Logistics — CTO  
MBA Big Data & IA — STUDI — Bloc 2 — 2025/2026
