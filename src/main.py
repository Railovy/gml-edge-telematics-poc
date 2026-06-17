"""
GML Edge Telematics - POC (mode offline)
=========================================
Preuve de faisabilite, executable localement sans reseau, sur materiel contraint
(Snapdragon 660, 150 Mo RAM) :

  1. Moteur ZFE   : detection d'entree en zone (Bounding Box + Ray Casting).
  2. Moteur Safety: detection de freinage violent depuis l'accelerometre.

Choix de conception (defendables en soutenance) :
  - aucune dependance lourde (stdlib + colorama optionnel) ;
  - traitement en flux : memoire constante, complexite O(N), jamais O(N^2) ;
  - la bounding box rejette les points lointains en O(1) AVANT tout calcul de
    distance (le calcul O(N) n'a lieu que pour les points proches ou internes) ;
  - le polygone est NON rectangulaire : le ray casting tranche les points
    situes dans la boite mais hors de la vraie zone ;
  - le score penalise un EVENEMENT de freinage, pas chaque echantillon, ce qui
    reste juste a 100 Hz ou un seul freinage couvre des dizaines d'echantillons.

Dependance : colorama (pip install colorama). Absente => fonctionne sans couleur.
Usage : python src/main.py
"""

import json
import csv
import math
import os

# ---------------------------------------------------------------------------
# COULEURS - colorama (Windows PowerShell / CMD), fallback sans plantage
# ---------------------------------------------------------------------------
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    COLOR_OK = True
except ImportError:
    COLOR_OK = False
    class _Dummy:
        def __getattr__(self, _): return ""
    Fore = Style = _Dummy()


def c_sep(t):      return Fore.CYAN + t + Style.RESET_ALL
def c_title(t):    return Fore.CYAN + Style.BRIGHT + t + Style.RESET_ALL
def c_dim(t):      return Style.DIM + t + Style.RESET_ALL
def c_green(t):    return Fore.GREEN + t + Style.RESET_ALL
def c_success(t):  return Fore.GREEN + Style.BRIGHT + t + Style.RESET_ALL
def c_prealert(t): return Fore.YELLOW + Style.BRIGHT + t + Style.RESET_ALL
def c_safety(t):   return Fore.YELLOW + t + Style.RESET_ALL
def c_alert(t):    return Fore.RED + Style.BRIGHT + t + Style.RESET_ALL
def c_severe(t):   return Fore.MAGENTA + Style.BRIGHT + t + Style.RESET_ALL
def c_error(t):    return Fore.RED + Style.BRIGHT + "[ERREUR] " + t + Style.RESET_ALL


# ---------------------------------------------------------------------------
# CHEMINS ET PARAMETRES
# ---------------------------------------------------------------------------
POLYGON_FILE = "data/lyon_polygon.json"
GPS_FILE     = "data/truck_gps.json"
ACC_FILE     = "data/accelerometer_data.csv"

PRE_ALERT_DISTANCE_M    = 500.0   # marge poids lourd a 90 km/h (~20 s d'anticipation)
HARSH_BRAKING_THRESHOLD = -2.5    # m/s2 axe Y : seuil de l'annexe (leve l'ambiguite 2.5G)
SEVERE_THRESHOLD        = -5.0    # m/s2 : au-dela, freinage severe
EARTH_RADIUS_M          = 6_371_000.0


# ===========================================================================
# GEOMETRIE
# ===========================================================================
def haversine_m(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi    = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def compute_bounding_box(polygon):
    lats = [p["lat"] for p in polygon]
    lons = [p["lon"] for p in polygon]
    return min(lats), max(lats), min(lons), max(lons)


def point_in_bbox(lat, lon, bbox, margin_deg=0.0):
    lat_min, lat_max, lon_min, lon_max = bbox
    return (lat_min - margin_deg <= lat <= lat_max + margin_deg and
            lon_min - margin_deg <= lon <= lon_max + margin_deg)


def ray_casting(lat, lon, polygon):
    """Point-dans-polygone (pair/impair). O(V) sur le nombre de sommets V."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]["lon"], polygon[i]["lat"]
        xj, yj = polygon[j]["lon"], polygon[j]["lat"]
        if ((yi > lat) != (yj > lat)) and \
           (lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def distance_to_polygon_m(lat, lon, polygon):
    """Distance au bord le plus proche, en metres. O(V)."""
    min_dist = float("inf")
    n = len(polygon)
    j = n - 1
    for i in range(n):
        ax, ay = polygon[j]["lon"], polygon[j]["lat"]
        bx, by = polygon[i]["lon"], polygon[i]["lat"]
        dx, dy = bx - ax, by - ay
        len2 = dx * dx + dy * dy
        if len2 == 0:
            dist = haversine_m(lat, lon, ay, ax)
        else:
            t = max(0.0, min(1.0, ((lon - ax) * dx + (lat - ay) * dy) / len2))
            dist = haversine_m(lat, lon, ay + t * dy, ax + t * dx)
        min_dist = min(min_dist, dist)
        j = i
    return min_dist


# ===========================================================================
# MOTEUR 1 : ZFE
# ===========================================================================
class ZFEEngine:
    def __init__(self, polygon_path):
        with open(polygon_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.polygon = data["polygon"]
        self.zone_name = data.get("zone_name", "ZFE")
        self.bbox = compute_bounding_box(self.polygon)
        # marge de la boite ~ distance de pre-alerte convertie en degres
        self.margin_deg = PRE_ALERT_DISTANCE_M / 111_320.0
        self.was_inside = False
        lo = self.bbox
        print(c_green(
            f"[ZFE] Bounding Box pre-filtre : lat[{lo[0]:.3f},{lo[1]:.3f}] "
            f"lon[{lo[2]:.3f},{lo[3]:.3f}] (marge {PRE_ALERT_DISTANCE_M:.0f} m)"
        ))

    def evaluate(self, point_id, lat, lon, timestamp, expected="?"):
        # 1) REJET O(1) : hors boite elargie => aucun calcul de distance
        if not point_in_bbox(lat, lon, self.bbox, self.margin_deg):
            print(c_dim(f"       point {point_id} | attendu={expected} "
                        f"| detecte=OUT | rejet O(1) (hors boite, distance non calculee)"))
            self.was_inside = False
            return {"point_id": point_id, "status": "OUT", "dist_m": None,
                    "is_entry": False, "lat": lat, "lon": lon, "timestamp": timestamp}

        # 2) DETECTION PRECISE O(V) seulement pour les points proches/internes
        inside = ray_casting(lat, lon, self.polygon)
        dist_m = distance_to_polygon_m(lat, lon, self.polygon)

        if inside:
            is_entry = not self.was_inside
            self.was_inside = True
            status = "IN"
            tag = "ENTREE" if is_entry else "PRESENCE"
            print(c_alert(f"[ALERT ZFE] {tag} point={point_id} ts={timestamp} "
                          f"lat={lat} lon={lon} (profondeur={dist_m:.0f} m)"))
            return {"point_id": point_id, "status": status, "dist_m": dist_m,
                    "is_entry": is_entry, "lat": lat, "lon": lon, "timestamp": timestamp}

        self.was_inside = False
        if dist_m <= PRE_ALERT_DISTANCE_M:
            print(c_prealert(f"[PRE-ALERT ZFE] point={point_id} ts={timestamp} "
                             f"approche zone (dist bord={dist_m:.0f} m)"))
            return {"point_id": point_id, "status": "PRE_ALERT", "dist_m": dist_m,
                    "is_entry": False, "lat": lat, "lon": lon, "timestamp": timestamp}

        print(c_dim(f"       point {point_id} | attendu={expected} "
                    f"| detecte=OUT | dans boite, hors polygone (dist bord={dist_m:.0f} m)"))
        return {"point_id": point_id, "status": "OUT", "dist_m": dist_m,
                "is_entry": False, "lat": lat, "lon": lon, "timestamp": timestamp}


# ===========================================================================
# MOTEUR 2 : Safety (avec regroupement en evenements)
# ===========================================================================
class SafetyEngine:
    PENALTY = {"HIGH": 15, "SEVERE": 25}

    def __init__(self):
        self.events = []
        self.sample_count = 0
        self.harsh_sample_count = 0
        self.min_acc_y = float("inf")

    @staticmethod
    def severity(peak):
        return "SEVERE" if peak <= SEVERE_THRESHOLD else "HIGH"

    def process_csv(self, csv_path):
        in_event = False
        cur = None
        with open(csv_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                self.sample_count += 1
                try:
                    acc_y = float(row["acc_y"])
                except (ValueError, KeyError):
                    continue  # ligne malformee ignoree sans planter
                self.min_acc_y = min(self.min_acc_y, acc_y)
                if acc_y < HARSH_BRAKING_THRESHOLD:
                    self.harsh_sample_count += 1
                    print(c_safety(f"[HARSH_BRAKING] ts={row.get('timestamp','N/A')} "
                                   f"acc_y={acc_y} m/s2 (seuil {HARSH_BRAKING_THRESHOLD})"))
                    if not in_event:
                        cur = {"start_ts": row.get("timestamp", "N/A"),
                               "peak_acc_y": acc_y, "samples": 1}
                        in_event = True
                    else:
                        cur["peak_acc_y"] = min(cur["peak_acc_y"], acc_y)
                        cur["samples"] += 1
                else:
                    if in_event:
                        self._close(cur)
                        in_event = False
        if in_event:
            self._close(cur)

    def _close(self, ev):
        ev["severity"] = self.severity(ev["peak_acc_y"])
        self.events.append(ev)
        col = c_severe if ev["severity"] == "SEVERE" else c_prealert
        print(col(f"   -> evenement freinage : pic={ev['peak_acc_y']} m/s2 "
                  f"sur {ev['samples']} echantillon(s) | severite={ev['severity']}"))

    def score(self):
        return max(0, 100 - sum(self.PENALTY.get(e["severity"], 0) for e in self.events))

    def to_json(self, date="2026-06-06", vehicle_id="GML_TRUCK_001",
                driver_id="DEMO_DRIVER"):
        return {
            "driver_id": driver_id,
            "vehicle_id": vehicle_id,
            "date": date,
            "sample_count": self.sample_count,
            "harsh_braking_samples": self.harsh_sample_count,
            "harsh_braking_events": len(self.events),
            "min_acc_y_ms2": self.min_acc_y if self.min_acc_y != float("inf") else None,
            "threshold_ms2": HARSH_BRAKING_THRESHOLD,
            "scoring_rule": "100 - 15*HIGH - 25*SEVERE (par evenement, borne a 0)",
            "daily_safety_score": self.score(),
            "events": self.events,
        }


# ===========================================================================
# POINT D'ENTREE
# ===========================================================================
def main():
    print(c_sep("=" * 66))
    print(c_title(" GML EDGE TELEMATICS - POC (mode offline)"))
    print(c_sep("=" * 66))
    os.makedirs("output", exist_ok=True)

    # --- Moteur ZFE ---
    print(c_sep("--- Moteur 1 : ZFE (Geo) " + "-" * 41))
    try:
        zfe = ZFEEngine(POLYGON_FILE)
        with open(GPS_FILE, "r", encoding="utf-8") as f:
            gps = json.load(f)
    except FileNotFoundError as e:
        print(c_error(str(e))); return

    alerts = []
    for p in gps["points"]:
        r = zfe.evaluate(p["id"], p["lat"], p["lon"], p["timestamp"],
                         p.get("expected", "?"))
        if r["status"] in ("IN", "PRE_ALERT"):
            alerts.append(r)

    with open("output/zfe_alerts.log", "w", encoding="utf-8") as f:
        f.write("timestamp,point_id,status,event,lat,lon,dist_m\n")
        for a in alerts:
            ev = "ENTREE" if a["is_entry"] else ("PRESENCE" if a["status"] == "IN" else "APPROCHE")
            f.write(f"{a['timestamp']},{a['point_id']},{a['status']},{ev},"
                    f"{a['lat']},{a['lon']},{a['dist_m']:.0f}\n")

    # --- Moteur Safety ---
    print(c_sep("--- Moteur 2 : Safety (Physics) " + "-" * 34))
    try:
        safety = SafetyEngine()
        safety.process_csv(ACC_FILE)
    except FileNotFoundError as e:
        print(c_error(str(e))); return

    score = safety.to_json()
    with open("output/daily_score.json", "w", encoding="utf-8") as f:
        json.dump(score, f, indent=2, ensure_ascii=False)

    # --- Synthese ---
    in_zone = [a for a in alerts if a["status"] == "IN" and a["is_entry"]]
    pre = [a for a in alerts if a["status"] == "PRE_ALERT"]
    print(c_sep("--- Synthese " + "-" * 53))
    print(c_success(f"ZFE    : {len(in_zone)} entree(s), {len(pre)} pre-alerte(s) d'approche"))
    print(c_success(f"Safety : {safety.harsh_sample_count} echantillon(s) sous seuil "
                    f"=> {len(safety.events)} evenement(s) | score = {score['daily_safety_score']}/100"))
    print(c_dim("Fichiers : output/zfe_alerts.log | output/daily_score.json"))
    print(c_sep("=" * 66))


if __name__ == "__main__":
    main()
