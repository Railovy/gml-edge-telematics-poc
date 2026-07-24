<div align="center">

<img src="assets/banner.svg" alt="GML Edge Telematics" width="100%"/>

<br/>

**Preuve de concept d'une telematique embarquee qui decide en local, sans reseau.**
Detection d'entree en Zone a Faibles Emissions et detection de freinage violent,
executees sur tablette durcie a bord du camion, meme en zone blanche.

<br/>

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Tests](https://img.shields.io/badge/tests-48%2F48%20passed-35D04F)
![Score](https://img.shields.io/badge/safety%20score-85%2F100-F4C430)
![Dependencies](https://img.shields.io/badge/deps-colorama%20(optionnel)-5BC8C8)
![Offline](https://img.shields.io/badge/mode-offline--first-0d2a3f)
![License](https://img.shields.io/badge/usage-academique-8fb8c9)

<br/>

[Contexte](#-contexte) · [Architecture](#-architecture) · [Demarrage](#-demarrage-rapide) · [Resultats](#-resultats-attendus) · [Choix techniques](#-choix-techniques) · [Limites](#-limites-assumees)

</div>

<br/>

```
░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
```

## 📍 Contexte

Un poids lourd entre dans la ZFE de Lyon via le tunnel de Fourviere. La 4G tombe,
la carte ZFE ne se charge pas, aucune alerte : **375 EUR d'amende**. En parallele,
l'assureur refuse un bonus faute de preuve comportementale, car le chronotachygraphe
ne mesure ni freinage, ni virage, ni acceleration tri-axiale.

Ce POC demontre la reponse : **deplacer la decision critique dans le camion**. Deux
moteurs tournent en local sur materiel contraint (Snapdragon 660, 150 Mo de RAM),
sans dependre du cloud.

| Moteur | Role | Entree | Sortie |
|---|---|---|---|
| **ZFE (Geo)** | Detecter l'entree en zone sans reseau | Trace GPS + polygone ZFE | Pre-alerte, entree, presence |
| **Safety (Physics)** | Detecter le freinage violent | Accelerometre 3 axes | Evenement HIGH/SEVERE, score |

<br/>

```
░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
```

## 🏗 Architecture

```mermaid
flowchart LR
    GPS[Trace GPS] --> BB{Bounding Box<br/>O(1)}
    BB -->|hors boite| REJECT[Rejet immediat<br/>points 1, 2]
    BB -->|dans boite elargie| RC[Ray Casting<br/>O(V)]
    RC --> CLASS[Classification<br/>OUT / PRE-ALERT / ON_BOUNDARY / IN]
    ACC[Accelerometre 100 Hz] --> STREAM[Lecture en flux<br/>O(N)]
    STREAM --> GROUP[Regroupement<br/>par evenement]
    GROUP --> SCORE[Score 0-100]
    CLASS --> LOG[(zfe_alerts.log)]
    SCORE --> JSON[(daily_score.json)]

    style BB fill:#0d2a3f,stroke:#5BC8C8,color:#fff
    style RC fill:#0d2a3f,stroke:#35D04F,color:#fff
    style REJECT fill:#12283a,stroke:#89929e,color:#fff
    style SCORE fill:#0d2a3f,stroke:#F4C430,color:#fff
```

Le filtrage a deux etages est le coeur du POC : la **Bounding Box rejette en temps
constant** les positions lointaines (points 1 et 2, sans aucun calcul de distance),
et le **Ray Casting O(V) ne s'execute que** pour les positions candidates (points 3,
4, 5). C'est ce qui rend le calcul tenable sur materiel embarque.

<br/>

```
░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
```

## 📂 Structure

```
gml-edge-telematics-poc/
├── data/
│   ├── lyon_polygon.json         polygone ZFE non rectangulaire (5 sommets)
│   ├── truck_gps.json            trace GPS (5 points : approche + entree)
│   └── accelerometer_data.csv    10 echantillons (acc_x, acc_y, acc_z)
├── src/
│   └── main.py                   moteurs ZFE + Safety
├── output/                       genere a l'execution
│   ├── zfe_alerts.log
│   └── daily_score.json
├── run_all.py                    point d'entree : main.py PUIS run_tests.py
├── run_tests.py                  tests de non-regression (48 cas)
├── run_all_gui.py                lanceur graphique optionnel (fenetre macOS)
├── requirements.txt
└── README.md
```

<br/>

```
░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
```

## 🚀 Demarrage rapide

**Prerequis :** Python 3.10 ou superieur. Dependance unique et optionnelle :
`colorama` (couleurs console). Sans elle, le POC tourne en noir et blanc, sans planter.

<table>
<tr>
<td width="50%" valign="top">

**Windows (PowerShell)**

```powershell
cd gml-edge-telematics-poc
pip install -r requirements.txt

# demo propre (optionnel)
if (Test-Path output) {
  Remove-Item output -Recurse -Force
}

python run_all.py
```

</td>
<td width="50%" valign="top">

**Linux / macOS**

```bash
cd gml-edge-telematics-poc
pip install -r requirements.txt

# demo propre (optionnel)
rm -rf output

python3 run_all.py
```

</td>
</tr>
</table>

`run_all.py` execute d'abord `src/main.py` (qui genere les sorties), puis
`run_tests.py` (qui verifie les 48 cas). Les scripts restent lancables separement :

```bash
python run_all.py        # tout : moteurs + tests (recommande)
python src/main.py       # moteurs seuls (genere output/)
python run_tests.py      # tests seuls (doit afficher 48/48)
```

<br/>

```
░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
```

## 📊 Resultats attendus

Sortie brute du terminal (sans accents, telle que l'affiche la console) :

```
--- Moteur 1 : ZFE (Geo) -----------------------------------------
[ZFE] Bounding Box stricte : lat[45.730,45.790] lon[4.800,4.880] | marge approche 500 m
       point 1 | attendu=OUT | detecte=OUT | rejet O(1)
       point 2 | attendu=OUT | detecte=OUT | rejet O(1)
[PRE-ALERT ZFE] point=3 ts=08:00:20 approche zone (dist bord=451 m)
[ALERT ZFE] ENTREE point=4 ts=08:00:30 lat=45.76 lon=4.8357 (profondeur=2284 m)
[ALERT ZFE] PRESENCE point=5 ts=08:00:40 lat=45.75 lon=4.85 (profondeur=1004 m)
--- Moteur 2 : Safety (Physics) ----------------------------------
[HARSH_BRAKING] ts=1678880005 acc_y=-3.45 m/s2 (seuil -2.5)
   -> evenement freinage : pic=-3.45 m/s2 sur 1 echantillon(s) | severite=HIGH
--- Synthese -----------------------------------------------------
ZFE    : 1 entree(s), 1 pre-alerte(s), 0 bordure(s)
Safety : 1 echantillon(s) sous seuil => 1 evenement(s) | score = 85/100
```

> **Note.** Les points 1 et 2 ne declenchent aucun calcul de distance : rejetes en
> O(1) hors de la boite englobante. Seuls les points 3, 4, 5 declenchent le ray
> casting. Ce bloc terminal est volontairement sans accents, comme la console.

**Fichiers generes**

| Fichier | Contenu |
|---|---|
| `output/zfe_alerts.log` | pre-alerte point 3 (451 m du bord), entree point 4 (2284 m), presence point 5 (1004 m) |
| `output/daily_score.json` | 1 echantillon sous seuil (acc_y = -3.45) regroupe en 1 evenement HIGH, score 85/100 |

**Tests**

```
[PASS] Bilan : 48/48 tests passes - POC robuste valide pour la demonstration
```

Les 48 tests couvrent les cas nominaux **et** 8 cas de robustesse : fichier absent,
JSON malforme, colonne `acc_y` manquante, valeur non numerique, classification
exacte des 5 sommets et des 5 milieux d'aretes (`ON_BOUNDARY`), precontrole des
entrees avant ecriture.

<br/>

```
░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
```

## 🎬 Demonstration filmee (optionnel)

Le script `run_all_gui.py` ouvre une fenetre facon macOS (trois boutons rouge,
jaune, vert) et **execute le vrai `run_all.py` en direct**, en affichant sa sortie
colorisee ligne par ligne. Aucune valeur n'est recopiee : tout provient de
l'execution reelle. Les scripts existants ne sont pas modifies.

```bash
pip install PySide6
python3 run_all_gui.py
```

Si PySide6 est absent, `run_all_gui.py` bascule automatiquement sur l'execution
terminal de `run_all.py`.

<br/>

```
░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
```

## 🧠 Choix techniques

<details>
<summary><b>Bounding Box + Ray Casting reellement justifies</b></summary>

<br/>

Le polygone est **non rectangulaire**. Les points 1 et 2 sont hors de la boite
englobante elargie (marge de pre-alerte de 500 m) et rejetes en O(1) sans calcul de
distance ni ray casting. Le statut `ON_BOUNDARY` est traite par distance metrique
avant le ray casting, afin de stabiliser sommets et aretes. Le calcul O(V) n'a lieu
que pour les points proches ou internes (3, 4, 5) : seul le ray casting distingue un
point proche du bord mais hors zone (point 3, pre-alerte a 451 m) d'un point
reellement interieur (points 4 et 5).

</details>

<details>
<summary><b>Traitement en flux O(N)</b></summary>

<br/>

L'accelerometre est lu ligne par ligne, en memoire constante. A 100 Hz sur 3 axes
(plusieurs millions d'echantillons par jour et par camion), un O(N²) serait
intenable sur la cible embarquee.

</details>

<details>
<summary><b>Score par evenement, pas par echantillon</b></summary>

<br/>

A 100 Hz, un freinage couvre plusieurs echantillons consecutifs sous le seuil. Les
compter un a un surpenaliserait un seul geste. Les echantillons consecutifs sont
regroupes en un evenement, classe par son pic (HIGH si pic > -5 m/s², SEVERE sinon).
Ici, un seul echantillon (acc_y = -3.45) franchit le seuil : un unique evenement
HIGH, d'ou le score de 85/100.

</details>

<details>
<summary><b>Ambiguite de seuil (point critique de l'enonce)</b></summary>

<br/>

Seuil operationnel retenu : `acc_y < -2.5 m/s²`. Un seuil de `2.5 G` vaudrait
environ 24,5 m/s², une deceleration de quasi-collision jamais atteinte en freinage
de service : le detecteur serait muet. La ligne `acc_y = -3.45` est donc bien classee
`HARSH_BRAKING`, ce que les tests confirment.

</details>

<br/>

```
░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
```

## ⚠️ Limites assumees

Polygone et trace GPS **synthetiques** : a remplacer par la donnee ZFE officielle de
la collectivite (mise a jour OTA) avant tout usage reel. La trace GPS est
echantillonnee a faible frequence pour la lisibilite ; la precision de detection
d'entree reelle est bornee par la frequence GPS, pas par les 100 Hz de
l'accelerometre. Le seuil unique ne distingue pas un freinage d'urgence legitime
d'une conduite agressive : enrichissement V1 (contexte vitesse, duree, recurrence) a
calibrer avec l'assureur. Le POC valide la **faisabilite algorithmique** ; la
compatibilite avec la Zebra ET40 reste a confirmer par un benchmark sur appareil reel.

<br/>

<div align="center">

```
░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
```

**MBA Big Data & IA · Bloc 2 · GreenMove Logistics**

*Preuve de concept academique. Chiffres reproductibles par `python3 run_all.py`.*

</div>
