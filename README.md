# GML Edge Telematics - POC (mode offline)

Preuve de faisabilité de deux fonctions critiques portées par la tablette
durcie embarquée, exécutables localement sans réseau, sur matériel contraint
(Snapdragon 660, 150 Mo de RAM) :

1. **Moteur ZFE (Geo)** - détection d'entrée en Zone à Faibles Émissions sans réseau.
2. **Moteur Safety (Physics)** - détection de freinage violent depuis l'accéléromètre.

## 1. Arborescence

```
gml-edge-telematics-poc/
  data/
    lyon_polygon.json        polygone ZFE NON rectangulaire (6 sommets)
    truck_gps.json           trace GPS (5 points : approche + entrée)
    accelerometer_data.csv   10 échantillons (acc_x, acc_y, acc_z)
  src/
    main.py                  moteurs ZFE + Safety
  output/                    généré à l'exécution
    zfe_alerts.log
    daily_score.json
  run_all.py                 lance main.py PUIS run_tests.py (point d'entrée)
  run_tests.py               tests de non-régression (14 cas)
  requirements.txt
  README.md
```

## 2. Prérequis

Python 3.10 ou supérieur. Dépendance unique et optionnelle : `colorama`
(couleurs console sous PowerShell / CMD). Sans elle, le POC tourne en noir et
blanc, sans planter (repli automatique).

## 3. Exécution

### Sous Windows (PowerShell)

```powershell
# Aller dans le dossier du projet
cd C:\chemin\vers\gml-edge-telematics-poc

# Installer la dépendance optionnelle
pip install -r requirements.txt

# Nettoyer les sorties précédentes (optionnel, pour une démo propre)
if (Test-Path output) { Remove-Item output -Recurse -Force }

# Lancer le POC complet : moteurs + tests en une commande
python run_all.py
```

### Sous Linux / macOS

```bash
cd gml-edge-telematics-poc
pip install -r requirements.txt

# Nettoyer les sorties précédentes (optionnel)
rm -rf output

# Lancer le POC complet : moteurs + tests
python3 run_all.py
```

`run_all.py` exécute d'abord `src/main.py` (qui génère les sorties), puis
`run_tests.py` (qui vérifie les 14 cas). Les deux scripts restent lançables
séparément si besoin :

```
python run_all.py        # tout : moteurs + tests (recommandé)
python src/main.py       # moteurs seuls (génère output/)
python run_tests.py      # tests de non-régression seuls (doit afficher 14/14)
```

## 4. Sorties attendues

### Console (extrait de `python run_all.py`)

```
--- Moteur 1 : ZFE (Geo) -----------------------------------------
[ZFE] Bounding Box pre-filtre : lat[45.730,45.790] lon[4.800,4.880] (marge 500 m)
       point 1 | attendu=OUT | detecte=OUT | rejet O(1) (hors boite, distance non calculee)
       point 2 | attendu=OUT | detecte=OUT | rejet O(1) (hors boite, distance non calculee)
[PRE-ALERT ZFE] point=3 ts=08:00:20 approche zone (dist bord=454 m)
[ALERT ZFE] ENTREE point=4 ts=08:00:30 lat=45.76 lon=4.8357 (profondeur=2324 m)
[ALERT ZFE] PRESENCE point=5 ts=08:00:40 lat=45.75 lon=4.85 (profondeur=1027 m)
--- Moteur 2 : Safety (Physics) ----------------------------------
[HARSH_BRAKING] ts=1678880005 acc_y=-3.45 m/s2 (seuil -2.5)
   -> evenement freinage : pic=-3.45 m/s2 sur 1 echantillon(s) | severite=HIGH
--- Synthese -----------------------------------------------------
ZFE    : 1 entree(s), 1 pre-alerte(s) d'approche
Safety : 1 echantillon(s) sous seuil => 1 evenement(s) | score = 85/100
```

> Le bloc ci-dessus reproduit la sortie brute du terminal (sans accents, comme
> l'affiche la console). Les points 1 et 2 ne déclenchent **aucun calcul de
> distance** : ils sont rejetés en O(1) hors de la boîte englobante, ce qui est
> précisément le rôle de la Bounding Box. Seuls les points proches ou internes
> (3, 4, 5) déclenchent le calcul de distance et le ray casting.

### Fichiers générés

- `output/zfe_alerts.log` : pré-alerte point 3 (454 m du bord), entrée point 4
  (profondeur 2324 m), présence point 5 (profondeur 1027 m).
- `output/daily_score.json` : 1 échantillon sous seuil (acc_y = -3.45) regroupé
  en 1 événement HIGH, score 85/100.

### Tests

```
[PASS] Bilan : 14/14 tests passes - POC valide pour la demonstration
```

## 5. Ambiguïté de seuil (point critique de l'énoncé)

Seuil opérationnel retenu : `acc_y < -2.5 m/s²` (annexe). `2.5 G` vaudrait
environ 24,5 m/s², une décélération de quasi-collision jamais atteinte en
freinage de service : ce seuil rendrait le détecteur muet. La ligne
`acc_y = -3.45` est donc bien classée `HARSH_BRAKING`, ce que les tests confirment.

## 6. Choix techniques défendables en soutenance

**Bounding Box + Ray Casting réellement justifiés.** Le polygone est NON
rectangulaire. Les points 1 et 2 sont hors de la boîte englobante élargie
(marge de pré-alerte de 500 m) et sont rejetés en O(1) SANS calcul de distance
ni ray casting. Le calcul O(V) de distance et le ray casting n'ont lieu que pour
les points proches ou internes (points 3, 4, 5) : seul le ray casting permet de
distinguer un point proche du bord mais hors zone (point 3, en pré-alerte) d'un
point réellement à l'intérieur du polygone (points 4 et 5).

**Traitement en flux O(N).** L'accéléromètre est lu ligne par ligne, mémoire
constante. À 100 Hz sur 3 axes (plusieurs millions d'échantillons par jour et
par camion), un O(N²) serait intenable sur la cible.

**Score par événement, pas par échantillon.** À 100 Hz, un freinage peut couvrir
plusieurs échantillons consécutifs sous le seuil. Les compter individuellement
surpénaliserait un seul geste. Les échantillons consécutifs sont regroupés en un
événement, classé par son pic (HIGH si pic > -5 m/s², SEVERE sinon). Dans ce jeu
de données, un seul échantillon (acc_y = -3.45) franchit le seuil : il forme un
unique événement HIGH, d'où un score de 85/100.

**Détection d'entrée.** Le log distingue l'ENTRÉE (transition hors zone vers
zone) de la PRÉSENCE (points suivants déjà à l'intérieur), pour une boîte noire
auditable.

## 7. Limites assumées

Polygone et trace GPS synthétiques : à remplacer par la donnée ZFE officielle de
la collectivité (mise à jour OTA) avant tout usage réel. La trace GPS est
échantillonnée à faible fréquence pour la lisibilité du POC ; la précision de
détection d'entrée réelle est bornée par la fréquence GPS, pas par les 100 Hz de
l'accéléromètre. Le seuil unique ne distingue pas un freinage d'urgence légitime
d'une conduite agressive : enrichissement V1 (contexte vitesse, durée,
récurrence) à calibrer avec l'assureur.
