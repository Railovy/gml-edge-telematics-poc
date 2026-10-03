"""
GML Edge Telematics - POC robuste (mode offline)
=================================================
Preuve de faisabilite executable localement sans reseau, sur materiel contraint.

Moteurs :
  1. ZFE    : Bounding Box O(1), distance metrique locale, Ray Casting O(V),
              statut stable ON_BOUNDARY.
  2. Safety : detection et regroupement d'un freinage violent, score par evenement.

Renforcements integres :
  - precontrole des trois fichiers d'entree avant tout calcul ;
  - distance point-segment en projection locale corrigee par cos(latitude) ;
  - frontiere testee avant le Ray Casting ;
  - sorties atomiques via os.replace() ;
  - erreurs metier controlees avec code retour 1 ;
  - erreurs techniques inattendues avec code retour 2.

Dependance : colorama optionnel. Absente => fonctionnement sans couleur.
Usage : python src/main.py
"""

from __future__ import annotations

import csv
import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


class PocDataError(Exception):
    """Erreur de donnees d'entree : message controle, jamais de stack trace."""


# ---------------------------------------------------------------------------
# COULEURS - colorama (Windows PowerShell / CMD), fallback sans plantage
# ---------------------------------------------------------------------------
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
except ImportError:  # pragma: no cover - fallback console
    class _Dummy:
        def __getattr__(self, _):
            return ""
    Fore = Style = _Dummy()


def c_sep(t):      return Fore.CYAN + t + Style.RESET_ALL
def c_title(t):    return Fore.CYAN + Style.BRIGHT + t + Style.RESET_ALL
def c_dim(t):      return Style.DIM + t + Style.RESET_ALL
def c_green(t):    return Fore.GREEN + t + Style.RESET_ALL
def c_success(t):  return Fore.GREEN + Style.BRIGHT + t + Style.RESET_ALL
def c_prealert(t): return Fore.YELLOW + Style.BRIGHT + t + Style.RESET_ALL
def c_alert(t):    return Fore.RED + Style.BRIGHT + t + Style.RESET_ALL
def c_severe(t):   return Fore.MAGENTA + Style.BRIGHT + t + Style.RESET_ALL
def c_error(t):    return Fore.RED + Style.BRIGHT + "[ERREUR] " + t + Style.RESET_ALL


# ---------------------------------------------------------------------------
# CHEMINS ET PARAMETRES
# ---------------------------------------------------------------------------
POLYGON_FILE = "data/lyon_polygon.json"
GPS_FILE     = "data/truck_gps.json"
ACC_FILE     = "data/accelerometer_data.csv"

PRE_ALERT_DISTANCE_M    = 500.0
BOUNDARY_TOLERANCE_M    = 1.0
HARSH_BRAKING_THRESHOLD = -2.5
SEVERE_THRESHOLD        = -5.0
DEG_LAT_TO_M            = 111_320.0


# ==========================================================================
# UTILITAIRES ROBUSTES
# ==========================================================================
def atomic_write_text(path: str | Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def atomic_write_json(path: str | Path, data: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def load_json_strict(path: str | Path, required_key: str) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise PocDataError(f"fichier absent : {path}")
    except json.JSONDecodeError as e:
        raise PocDataError(f"JSON malforme : {path} ({e.msg}, ligne {e.lineno})")
    if isinstance(data, list):
        data = {required_key: data}  # format brut de l'enonce (tableau JSON nu)
    if not isinstance(data, dict) or required_key not in data:
        raise PocDataError(f"cle '{required_key}' absente dans {path}")
    return data


def _as_float(value: Any, field: str) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise PocDataError(f"valeur non numerique pour {field} : {value!r}")
    if not math.isfinite(v):
        raise PocDataError(f"valeur non finie pour {field} : {value!r}")
    return v


def validate_lat_lon(lat: float, lon: float) -> None:
    if not (-90.0 <= lat <= 90.0):
        raise PocDataError(f"latitude invalide : {lat}")
    if not (-180.0 <= lon <= 180.0):
        raise PocDataError(f"longitude invalide : {lon}")


def normalize_polygon(raw_polygon: list[dict[str, Any]]) -> list[dict[str, float]]:
    if not isinstance(raw_polygon, list) or len(raw_polygon) < 4:
        raise PocDataError("polygone invalide : au moins 4 points attendus, fermeture incluse")
    polygon: list[dict[str, float]] = []
    for idx, item in enumerate(raw_polygon, start=1):
        if not isinstance(item, dict):
            raise PocDataError(f"sommet {idx} invalide")
        lat = _as_float(item.get("lat"), f"polygon[{idx}].lat")
        lon = _as_float(item.get("lon"), f"polygon[{idx}].lon")
        validate_lat_lon(lat, lon)
        polygon.append({"lat": lat, "lon": lon})
    if polygon[0] != polygon[-1]:
        polygon.append(dict(polygon[0]))
    if len(polygon) < 4:
        raise PocDataError("polygone invalide apres fermeture")
    return polygon


def validate_gps_points(raw_points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(raw_points, list) or not raw_points:
        raise PocDataError("trace GPS invalide : liste non vide attendue")
    points = []
    for idx, item in enumerate(raw_points, start=1):
        if not isinstance(item, dict):
            raise PocDataError(f"point GPS {idx} invalide")
        lat = _as_float(item.get("lat"), f"points[{idx}].lat")
        lon = _as_float(item.get("lon"), f"points[{idx}].lon")
        validate_lat_lon(lat, lon)
        points.append({
            "id": item.get("id", idx),
            "lat": lat,
            "lon": lon,
            "timestamp": str(item.get("timestamp", "")),
            "expected": item.get("expected", "?"),
        })
    return points


def validate_csv_header(path: str | Path) -> None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise PocDataError(f"CSV vide ou sans en-tete : {path}")
            if "acc_y" not in reader.fieldnames:
                raise PocDataError(
                    f"colonne 'acc_y' absente de {path} (colonnes trouvees : {reader.fieldnames})")
    except FileNotFoundError:
        raise PocDataError(f"fichier absent : {path}")


def prevalidate_inputs() -> tuple[list[dict[str, float]], list[dict[str, Any]]]:
    polygon_data = load_json_strict(POLYGON_FILE, "polygon")
    gps_data = load_json_strict(GPS_FILE, "points")
    polygon = normalize_polygon(polygon_data["polygon"])
    points = validate_gps_points(gps_data["points"])
    validate_csv_header(ACC_FILE)
    return polygon, points


# ==========================================================================
# GEOMETRIE
# ==========================================================================
def _local_scale(reference_lat_deg: float) -> tuple[float, float]:
    return (DEG_LAT_TO_M * math.cos(math.radians(reference_lat_deg)), DEG_LAT_TO_M)


def _project(lat: float, lon: float, ref_lat: float) -> tuple[float, float]:
    scale_lon, scale_lat = _local_scale(ref_lat)
    return lon * scale_lon, lat * scale_lat


def compute_bounding_box(polygon: list[dict[str, float]]) -> tuple[float, float, float, float]:
    lats = [p["lat"] for p in polygon]
    lons = [p["lon"] for p in polygon]
    return min(lats), max(lats), min(lons), max(lons)


def expanded_bbox(bbox: tuple[float, float, float, float], margin_m: float) -> tuple[float, float, float, float]:
    lat_min, lat_max, lon_min, lon_max = bbox
    margin_lat = margin_m / DEG_LAT_TO_M
    lat_mid = (lat_min + lat_max) / 2.0
    margin_lon = margin_m / (DEG_LAT_TO_M * max(math.cos(math.radians(lat_mid)), 1e-9))
    return lat_min - margin_lat, lat_max + margin_lat, lon_min - margin_lon, lon_max + margin_lon


def point_in_bbox(lat: float, lon: float, bbox: tuple[float, float, float, float]) -> bool:
    lat_min, lat_max, lon_min, lon_max = bbox
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def ray_casting(lat: float, lon: float, polygon: list[dict[str, float]]) -> bool:
    """Point-dans-polygone pair/impair, O(V). La frontiere est traitee ailleurs."""
    vertices = polygon[:-1] if polygon[0] == polygon[-1] else polygon
    inside = False
    j = len(vertices) - 1
    for i in range(len(vertices)):
        xi, yi = vertices[i]["lon"], vertices[i]["lat"]
        xj, yj = vertices[j]["lon"], vertices[j]["lat"]
        if ((yi > lat) != (yj > lat)):
            x_intersect = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_intersect:
                inside = not inside
        j = i
    return inside


def _distance_to_segment_projected(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def distance_to_polygon_m(lat: float, lon: float, polygon: list[dict[str, float]]) -> float:
    """Distance a la frontiere par projection locale metrique, O(V)."""
    ref_lat = lat
    px, py = _project(lat, lon, ref_lat)
    distances = []
    for i in range(len(polygon) - 1):
        ax, ay = _project(polygon[i]["lat"], polygon[i]["lon"], ref_lat)
        bx, by = _project(polygon[i + 1]["lat"], polygon[i + 1]["lon"], ref_lat)
        distances.append(_distance_to_segment_projected(px, py, ax, ay, bx, by))
    return min(distances)


def classify_point(lat: float, lon: float, polygon: list[dict[str, float]], bbox: tuple[float, float, float, float], approach_bbox: tuple[float, float, float, float]) -> tuple[str, float | None]:
    if not point_in_bbox(lat, lon, approach_bbox):
        return "OUT", None
    dist_m = distance_to_polygon_m(lat, lon, polygon)
    if dist_m <= BOUNDARY_TOLERANCE_M:
        return "ON_BOUNDARY", 0.0
    if ray_casting(lat, lon, polygon):
        return "IN", dist_m
    if dist_m <= PRE_ALERT_DISTANCE_M:
        return "PRE_ALERT", dist_m
    return "OUT", dist_m


# ==========================================================================
# MOTEUR 1 : ZFE
# ==========================================================================
class ZFEEngine:
    def __init__(self, polygon: list[dict[str, float]]):
        self.polygon = polygon
        self.bbox = compute_bounding_box(self.polygon)
        self.approach_bbox = expanded_bbox(self.bbox, PRE_ALERT_DISTANCE_M)
        self.was_inside = False
        lo = self.bbox
        print(c_green(
            f"[ZFE] Bounding Box stricte : lat[{lo[0]:.3f},{lo[1]:.3f}] "
            f"lon[{lo[2]:.3f},{lo[3]:.3f}] | marge approche {PRE_ALERT_DISTANCE_M:.0f} m"
        ))

    def evaluate(self, point_id, lat, lon, timestamp, expected="?"):
        status, dist_m = classify_point(lat, lon, self.polygon, self.bbox, self.approach_bbox)
        if status == "OUT" and dist_m is None:
            print(c_dim(f"       point {point_id} | attendu={expected} | detecte=OUT | rejet O(1)"))
            self.was_inside = False
            return {"point_id": point_id, "status": "OUT", "dist_m": None, "is_entry": False, "lat": lat, "lon": lon, "timestamp": timestamp}
        if status == "ON_BOUNDARY":
            self.was_inside = True
            print(c_prealert(f"[BOUNDARY ZFE] point={point_id} ts={timestamp} sur frontiere (dist bord=0 m)"))
            return {"point_id": point_id, "status": "ON_BOUNDARY", "dist_m": 0.0, "is_entry": False, "lat": lat, "lon": lon, "timestamp": timestamp}
        if status == "IN":
            is_entry = not self.was_inside
            self.was_inside = True
            tag = "ENTREE" if is_entry else "PRESENCE"
            print(c_alert(f"[ALERT ZFE] {tag} point={point_id} ts={timestamp} lat={lat} lon={lon} (profondeur={dist_m:.0f} m)"))
            return {"point_id": point_id, "status": "IN", "dist_m": dist_m, "is_entry": is_entry, "lat": lat, "lon": lon, "timestamp": timestamp}
        self.was_inside = False
        if status == "PRE_ALERT":
            print(c_prealert(f"[PRE-ALERT ZFE] point={point_id} ts={timestamp} approche zone (dist bord={dist_m:.0f} m)"))
        else:
            print(c_dim(f"       point {point_id} | attendu={expected} | detecte=OUT | dans boite, hors polygone (dist bord={dist_m:.0f} m)"))
        return {"point_id": point_id, "status": status, "dist_m": dist_m, "is_entry": False, "lat": lat, "lon": lon, "timestamp": timestamp}


# ==========================================================================
# MOTEUR 2 : Safety
# ==========================================================================
class SafetyEngine:
    PENALTY = {"HIGH": 15, "SEVERE": 25}

    def __init__(self):
        self.events: list[dict[str, Any]] = []
        self.sample_count = 0
        self.harsh_sample_count = 0
        self.skipped_rows = 0
        self.min_acc_y = float("inf")

    @staticmethod
    def severity(peak: float) -> str:
        return "SEVERE" if peak <= SEVERE_THRESHOLD else "HIGH"

    def process_csv(self, csv_path: str | Path) -> None:
        in_event = False
        cur: dict[str, Any] | None = None
        try:
            f = open(csv_path, "r", encoding="utf-8")
        except FileNotFoundError:
            raise PocDataError(f"fichier absent : {csv_path}")
        with f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise PocDataError(f"CSV vide ou sans en-tete : {csv_path}")
            if "acc_y" not in reader.fieldnames:
                raise PocDataError(f"colonne 'acc_y' absente de {csv_path} (colonnes trouvees : {reader.fieldnames})")
            for row_number, row in enumerate(reader, start=1):
                self.sample_count += 1
                try:
                    acc_y = float(row["acc_y"])
                except (TypeError, ValueError):
                    self.skipped_rows += 1
                    print(c_error(f"ligne {row_number} ignoree : acc_y non numerique ({row.get('acc_y')!r})"))
                    continue
                if not math.isfinite(acc_y):
                    self.skipped_rows += 1
                    print(c_error(f"ligne {row_number} ignoree : acc_y non finie ({row.get('acc_y')!r})"))
                    continue
                self.min_acc_y = min(self.min_acc_y, acc_y)
                ts = row.get("timestamp", str(row_number))
                if acc_y < HARSH_BRAKING_THRESHOLD:
                    self.harsh_sample_count += 1
                    print(c_alert(f"[HARSH_BRAKING] ts={ts} acc_y={acc_y:.2f} m/s2 (seuil {HARSH_BRAKING_THRESHOLD})"))
                    if not in_event:
                        cur = {"start_ts": ts, "end_ts": ts, "peak_acc_y": acc_y, "samples": 1}
                        in_event = True
                    else:
                        assert cur is not None
                        cur["end_ts"] = ts
                        cur["samples"] += 1
                        cur["peak_acc_y"] = min(cur["peak_acc_y"], acc_y)
                else:
                    if in_event and cur is not None:
                        self._close(cur)
                    in_event = False
                    cur = None
        if in_event and cur is not None:
            self._close(cur)

    def _close(self, ev: dict[str, Any]) -> None:
        ev["severity"] = self.severity(float(ev["peak_acc_y"]))
        self.events.append(ev)
        col = c_severe if ev["severity"] == "SEVERE" else c_prealert
        print(col(f"   -> evenement freinage : pic={ev['peak_acc_y']} m/s2 sur {ev['samples']} echantillon(s) | severite={ev['severity']}"))

    def score(self) -> int | None:
        if self.sample_count - self.skipped_rows == 0:
            return None  # aucune mesure valide : pas de score, jamais 100 par defaut
        return max(0, 100 - sum(self.PENALTY.get(e["severity"], 0) for e in self.events))

    def to_json(self, date="2026-06-06", vehicle_id="GML_TRUCK_001", driver_id="DEMO_DRIVER") -> dict[str, Any]:
        return {
            "driver_id": driver_id,
            "vehicle_id": vehicle_id,
            "date": date,
            "sample_count": self.sample_count,
            "skipped_rows": self.skipped_rows,
            "harsh_braking_samples": self.harsh_sample_count,
            "harsh_braking_events": len(self.events),
            "min_acc_y_ms2": self.min_acc_y if self.min_acc_y != float("inf") else None,
            "threshold_ms2": HARSH_BRAKING_THRESHOLD,
            "scoring_rule": "100 - 15*HIGH - 25*SEVERE (par evenement, borne a 0)",
            "daily_safety_score": self.score(),
            "events": self.events,
        }


# ==========================================================================
# POINT D'ENTREE
# ==========================================================================
def main() -> int:
    try:
        print(c_sep("=" * 66))
        print(c_title(" GML EDGE TELEMATICS - POC robuste (mode offline)"))
        print(c_sep("=" * 66))

        # Precontrole bloquant : pas de sortie partielle si une entree est invalide.
        polygon, gps_points = prevalidate_inputs()
        os.makedirs("output", exist_ok=True)

        # --- Moteur ZFE ---
        print(c_sep("--- Moteur 1 : ZFE (Geo) " + "-" * 41))
        zfe = ZFEEngine(polygon)
        alerts = []
        replay_s = float(os.environ.get("GML_REPLAY_S", "0") or 0)  # 0 = mode normal (tests)
        for p in gps_points:
            if replay_s > 0:
                time.sleep(replay_s)  # rejeu de la trace GPS, point par point, pour la demo
            r = zfe.evaluate(p["id"], p["lat"], p["lon"], p["timestamp"], p.get("expected", "?"))
            if r["status"] in ("IN", "PRE_ALERT", "ON_BOUNDARY"):
                alerts.append(r)

        lines = ["timestamp,point_id,status,event,lat,lon,dist_m"]
        for a in alerts:
            ev = "ENTREE" if a["is_entry"] else ("PRESENCE" if a["status"] == "IN" else ("BORDURE" if a["status"] == "ON_BOUNDARY" else "APPROCHE"))
            dist_txt = "" if a["dist_m"] is None else f"{a['dist_m']:.0f}"
            lines.append(f"{a['timestamp']},{a['point_id']},{a['status']},{ev},{a['lat']},{a['lon']},{dist_txt}")
        atomic_write_text("output/zfe_alerts.log", "\n".join(lines) + "\n")

        # --- Moteur Safety ---
        print(c_sep("--- Moteur 2 : Safety (Physics) " + "-" * 34))
        safety = SafetyEngine()
        safety.process_csv(ACC_FILE)
        score = safety.to_json()
        atomic_write_json("output/daily_score.json", score)

        # --- Synthese ---
        in_zone = [a for a in alerts if a["status"] == "IN" and a["is_entry"]]
        pre = [a for a in alerts if a["status"] == "PRE_ALERT"]
        boundary = [a for a in alerts if a["status"] == "ON_BOUNDARY"]
        print(c_sep("--- Synthese " + "-" * 53))
        print(c_success(f"ZFE    : {len(in_zone)} entree(s), {len(pre)} pre-alerte(s), {len(boundary)} bordure(s)"))
        print(c_success(f"Safety : {safety.harsh_sample_count} echantillon(s) sous seuil => {len(safety.events)} evenement(s) | score = {score['daily_safety_score'] if score['daily_safety_score'] is not None else 'N/A (aucune mesure valide)'}{'/100' if score['daily_safety_score'] is not None else ''}"))
        print(c_dim("Fichiers : output/zfe_alerts.log | output/daily_score.json"))
        print(c_sep("=" * 66))
        return 0
    except PocDataError as e:
        print(c_error(str(e)))
        return 1
    except Exception as e:  # pragma: no cover - securite demo
        print(c_error(f"erreur technique inattendue : {type(e).__name__} - {e}"))
        return 2


if __name__ == "__main__":
    sys.exit(main())
