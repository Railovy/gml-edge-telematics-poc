# GML Edge Telematics - POC (mode offline)

Preuve de faisabilite de deux fonctions critiques portees par la tablette
durcie embarquee, executables localement sans reseau, sur materiel contraint
(Snapdragon 660, 150 Mo de RAM) :

1. **Moteur ZFE (Geo)** - detection d'entree en Zone a Faibles Emissions sans reseau.
2. **Moteur Safety (Physics)** - detection de freinage violent depuis l'accelerometre.

## 1. Arborescence

```
gml-edge-telematics-poc/
  data/
    lyon_polygon.json        polygone ZFE NON rectangulaire (6 sommets)
    truck_gps.json           trace GPS (5 points : approche + entree)
    accelerometer_data.csv   10 echantillons (acc_x, acc_y, acc_z)
  src/
    main.py                  moteurs ZFE + Safety
  output/                    genere a l'execution
    zfe_alerts.log
    daily_score.json
  run_all.py                 lance main.py PUIS run_tests.py (point d'entree)
  run_tests.py               tests de non-regression (14 cas)
  requirements.txt
  README.md
```

## 2. Prerequis

Python 3.10 ou superieur. Dependance unique et optionnelle : `colorama`
(couleurs console sous PowerShell / CMD). Sans elle, le POC tourne en noir et
blanc, sans planter (repli automatique).

## 3. Execution

### Sous Windows (PowerShell)

```powershell
# Aller dans le dossier du projet
cd C:\chemin\vers\gml-edge-telematics-poc

# Installer la dependance optionnelle
pip install -r requirements.txt

# Nettoyer les sorties precedentes (optionnel, pour une demo propre)
if (Test-Path output) { Remove-Item output -Recurse -Force }

# Lancer le POC complet : moteurs + tests en une commande
python run_all.py
```

### Sous Linux / macOS

```bash
cd gml-edge-telematics-poc
pip install -r requirements.txt

# Nettoyer les sorties precedentes (optionnel)
rm -rf output

# Lancer le POC complet : moteurs + tests
python3 run_all.py
```

`run_all.py` execute d'abord `src/main.py` (qui genere les sorties), puis
`run_tests.py` (qui verifie les 14 cas). Les deux scripts restent lancables
separement si besoin :

```
python run_all.py        # tout : moteurs + tests (recommande)
python src/main.py       # moteurs seuls (genere output/)
python run_tests.py      # tests de non-regression seuls (doit afficher 14/14)
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

Points 1 et 2 : **aucune distance n'est calculee**, ils sont rejetes en O(1) hors
de la boite englobante (c'est le role de la Bounding Box). Seuls les points
proches ou internes (3, 4, 5) declenchent le calcul de distance et le ray casting.

### Fichiers generes

- `output/zfe_alerts.log` : pre-alerte point 3 (454 m du bord), entree point 4
  (profondeur 2324 m), presence point 5 (profondeur 1027 m).
- `output/daily_score.json` : 1 echantillon sous seuil (acc_y = -3.45) regroupe
  en 1 evenement HIGH, score 85/100.

### Tests

```
[PASS] Bilan : 14/14 tests passes - POC valide pour la demonstration
```

## 5. Ambiguite de seuil (point critique de l'enonce)

Seuil operationnel retenu : `acc_y < -2.5 m/s2` (annexe). `2.5 G` vaudrait
environ 24,5 m/s2, une deceleration de quasi-collision jamais atteinte en
freinage de service : ce seuil rendrait le detecteur muet. La ligne
`acc_y = -3.45` est donc bien classee `HARSH_BRAKING`, ce que les tests confirment.

## 6. Choix techniques defendables en soutenance

**Bounding Box + Ray Casting reellement justifies.** Le polygone est NON
rectangulaire. Les points 1 et 2 sont hors de la boite englobante elargie
(marge de pre-alerte de 500 m) et sont rejetes en O(1) SANS calcul de distance
ni ray casting. Le calcul O(V) de distance et le ray casting n'ont lieu que pour
les points proches ou internes (points 3, 4, 5) : seul le ray casting permet de
distinguer un point proche du bord mais hors zone (point 3, en pre-alerte) d'un
point reellement a l'interieur du polygone (points 4 et 5).

**Traitement en flux O(N).** L'accelerometre est lu ligne par ligne, memoire
constante. A 100 Hz sur 3 axes (plusieurs millions d'echantillons par jour et
par camion), un O(N^2) serait intenable sur la cible.

**Score par evenement, pas par echantillon.** A 100 Hz, un freinage peut couvrir
plusieurs echantillons consecutifs sous le seuil. Les compter individuellement
surpenaliserait un seul geste. Les echantillons consecutifs sont regroupes en un
evenement, classe par son pic (HIGH si pic > -5 m/s2, SEVERE sinon). Dans ce jeu
de donnees, un seul echantillon (acc_y = -3.45) franchit le seuil : il forme un
unique evenement HIGH, d'ou un score de 85/100.

**Detection d'entree.** Le log distingue l'ENTREE (transition hors zone vers
zone) de la PRESENCE (points suivants deja a l'interieur), pour une boite noire
auditable.

## 7. Limites assumees

Polygone et trace GPS synthetiques : a remplacer par la donnee ZFE officielle de
la collectivite (mise a jour OTA) avant tout usage reel. La trace GPS est
echantillonnee a faible frequence pour la lisibilite du POC ; la precision de
detection d'entree reelle est bornee par la frequence GPS, pas par les 100 Hz de
l'accelerometre. Le seuil unique ne distingue pas un freinage d'urgence legitime
d'une conduite agressive : enrichissement V1 (contexte vitesse, duree,
recurrence) a calibrer avec l'assureur.
