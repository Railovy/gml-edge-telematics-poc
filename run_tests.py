"""Tests de non-regression du POC GreenMove Edge Telematics.

Cette suite renforce la version B avec les apports de robustesse de la version A :
- statut metier ON_BOUNDARY ;
- tests explicites sur les sommets et milieux d'aretes ;
- distance metrique locale ;
- precontrole des entrees avant sortie partielle ;
- verification des ecritures atomiques et des erreurs controlees.
"""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
os.chdir(PROJECT_ROOT)
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from main import (  # noqa: E402
    ACC_FILE,
    BOUNDARY_TOLERANCE_M,
    GPS_FILE,
    HARSH_BRAKING_THRESHOLD,
    POLYGON_FILE,
    PRE_ALERT_DISTANCE_M,
    PocDataError,
    SafetyEngine,
    ZFEEngine,
    c_sep,
    c_title,
    classify_point,
    compute_bounding_box,
    distance_to_polygon_m,
    expanded_bbox,
    load_json_strict,
    main as app_main,
    normalize_polygon,
    prevalidate_inputs,
    ray_casting,
    validate_gps_points,
)

try:
    from colorama import Fore as _F, Style as _S
    def c_pass(text): return _F.GREEN + "  [PASS] " + text + _S.RESET_ALL
    def c_fail(text): return _F.RED + _S.BRIGHT + "  [FAIL] " + text + _S.RESET_ALL
    def c_head(text): return _F.CYAN + text + _S.RESET_ALL
except ImportError:
    def c_pass(text): return "  [PASS] " + text
    def c_fail(text): return "  [FAIL] " + text
    def c_head(text): return text


def check(name, passed, detail, results):
    line = f"{name} ({detail})" if detail else name
    print(c_pass(line) if passed else c_fail(line))
    results.append(bool(passed))


def expect_poc_data_error(name, fn, results):
    try:
        fn()
        check(name, False, "aucune erreur levee", results)
    except PocDataError as exc:
        check(name, True, str(exc)[:90], results)
    except Exception as exc:
        check(name, False, f"exception brute : {type(exc).__name__}", results)


def load_polygon_and_points():
    polygon, points = prevalidate_inputs()
    return polygon, points


def near(value, expected, tolerance):
    return abs(float(value) - float(expected)) <= tolerance


def offset_from_edge(edge_start, edge_end, meters):
    """Cree un point a une distance metrique donnee du milieu d'une arete."""
    ref_lat = (edge_start["lat"] + edge_end["lat"]) / 2.0
    scale_lon = 111_320.0 * math.cos(math.radians(ref_lat))
    scale_lat = 111_320.0
    ax, ay = edge_start["lon"] * scale_lon, edge_start["lat"] * scale_lat
    bx, by = edge_end["lon"] * scale_lon, edge_end["lat"] * scale_lat
    mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    nx, ny = -dy / length, dx / length
    x, y = mx + nx * meters, my + ny * meters
    return {"lat": y / scale_lat, "lon": x / scale_lon}


def run_all_tests():
    results = []
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(exist_ok=True)

    print(c_sep("=" * 66))
    print(c_title(" GML POC robuste - Tests de non-regression"))
    print(c_sep("=" * 66))

    # ------------------------------------------------------------------
    # 1. Moteur ZFE nominal
    # ------------------------------------------------------------------
    print(c_head("\n[TEST] Moteur ZFE nominal :"))
    polygon, gps_points = load_polygon_and_points()
    engine = ZFEEngine(polygon)
    res = {p["id"]: engine.evaluate(p["id"], p["lat"], p["lon"], p["timestamp"], p.get("expected", "?")) for p in gps_points}

    check("Point 1 = OUT", res[1]["status"] == "OUT", f"obtenu={res[1]['status']}", results)
    check("Point 2 = OUT", res[2]["status"] == "OUT", f"obtenu={res[2]['status']}", results)
    check("Point 3 = PRE_ALERT", res[3]["status"] == "PRE_ALERT", f"obtenu={res[3]['status']}", results)
    check("Point 4 = IN", res[4]["status"] == "IN", f"obtenu={res[4]['status']}", results)
    check("Point 5 = IN", res[5]["status"] == "IN", f"obtenu={res[5]['status']}", results)
    check("Point 3 distance ~= 451 m", near(res[3]["dist_m"], 451, 2), f"dist={res[3]['dist_m']:.1f}", results)
    check("Point 4 profondeur ~= 2284 m", near(res[4]["dist_m"], 2284, 5), f"dist={res[4]['dist_m']:.1f}", results)
    check("Point 5 profondeur ~= 1004 m", near(res[5]["dist_m"], 1004, 5), f"dist={res[5]['dist_m']:.1f}", results)

    print(c_head("\n[TEST] Optimisation Bounding Box :"))
    check("Point 1 : distance non calculee (rejet O(1))", res[1]["dist_m"] is None, f"dist_m={res[1]['dist_m']}", results)
    check("Point 4 : entree detectee", res[4]["is_entry"] is True, f"is_entry={res[4]['is_entry']}", results)
    check("Point 5 : presence, pas nouvelle entree", res[5]["is_entry"] is False, f"is_entry={res[5]['is_entry']}", results)

    # ------------------------------------------------------------------
    # 2. Frontieres explicites
    # ------------------------------------------------------------------
    print(c_head("\n[TEST] Frontieres ON_BOUNDARY :"))
    bbox = compute_bounding_box(polygon)
    approach_bbox = expanded_bbox(bbox, PRE_ALERT_DISTANCE_M)
    vertices = polygon[:-1]
    for idx, vertex in enumerate(vertices, start=1):
        status, dist = classify_point(vertex["lat"], vertex["lon"], polygon, bbox, approach_bbox)
        check(f"Sommet {idx} = ON_BOUNDARY", status == "ON_BOUNDARY" and dist == 0.0, f"status={status}, dist={dist}", results)
    for idx in range(len(vertices)):
        a = polygon[idx]
        b = polygon[(idx + 1) % len(vertices)]
        mid_lat, mid_lon = (a["lat"] + b["lat"]) / 2.0, (a["lon"] + b["lon"]) / 2.0
        status, dist = classify_point(mid_lat, mid_lon, polygon, bbox, approach_bbox)
        check(f"Milieu arete {idx + 1} = ON_BOUNDARY", status == "ON_BOUNDARY" and dist == 0.0, f"status={status}, dist={dist}", results)
    close_p = offset_from_edge(vertices[0], vertices[1], 0.5)
    far_p = offset_from_edge(vertices[0], vertices[1], 1.5)
    close_status, close_dist = classify_point(close_p["lat"], close_p["lon"], polygon, bbox, approach_bbox)
    far_status, far_dist = classify_point(far_p["lat"], far_p["lon"], polygon, bbox, approach_bbox)
    check("Point a 0,5 m de la frontiere = ON_BOUNDARY", close_status == "ON_BOUNDARY", f"status={close_status}, dist={close_dist}", results)
    check("Point a 1,5 m de la frontiere != ON_BOUNDARY", far_status != "ON_BOUNDARY" and far_dist > BOUNDARY_TOLERANCE_M, f"status={far_status}, dist={far_dist:.2f}", results)

    # Le Ray Casting natif reste booleen, mais le statut metier ne s'appuie pas sur lui pour la frontiere.
    raw_vertex = ray_casting(vertices[0]["lat"], vertices[0]["lon"], polygon)
    raw_edge = ray_casting((vertices[0]["lat"] + vertices[1]["lat"]) / 2, (vertices[0]["lon"] + vertices[1]["lon"]) / 2, polygon)
    check("Ray Casting brut retourne un booleen au sommet", isinstance(raw_vertex, bool), f"resultat={raw_vertex}", results)
    check("Ray Casting brut retourne un booleen sur arete", isinstance(raw_edge, bool), f"resultat={raw_edge}", results)

    # ------------------------------------------------------------------
    # 3. Moteur Safety
    # ------------------------------------------------------------------
    print(c_head("\n[TEST] Moteur Safety :"))
    safety = SafetyEngine()
    safety.process_csv(ACC_FILE)
    data = safety.to_json()
    check("1 echantillon sous seuil", data["harsh_braking_samples"] == 1, f"obtenu={data['harsh_braking_samples']}", results)
    check("1 evenement regroupe", data["harsh_braking_events"] == 1, f"obtenu={data['harsh_braking_events']}", results)
    check("Pic -3.45 detecte", data["min_acc_y_ms2"] == -3.45 and safety.events[0]["peak_acc_y"] == -3.45, f"min={data['min_acc_y_ms2']}", results)
    check("Evenement = HIGH", safety.events[0]["severity"] == "HIGH", f"obtenu={safety.events[0]['severity']}", results)
    check("Score = 85/100", data["daily_safety_score"] == 85, f"obtenu={data['daily_safety_score']}", results)

    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
        tmp.write("timestamp,acc_x,acc_y,acc_z\n1,0.1,-2.49,9.8\n2,0.1,-2.40,9.8\n")
        no_fp = tmp.name
    try:
        s_no_fp = SafetyEngine()
        s_no_fp.process_csv(no_fp)
        check("Pas de faux positif a -2.49 m/s2", len(s_no_fp.events) == 0, f"events={len(s_no_fp.events)}", results)
    finally:
        os.unlink(no_fp)

    # ------------------------------------------------------------------
    # 4. Sorties et ecriture atomique
    # ------------------------------------------------------------------
    print(c_head("\n[TEST] Fichiers de sortie :"))
    code = app_main()
    check("src/main.py termine en code 0", code == 0, f"code={code}", results)
    check("output/daily_score.json existe", (output_dir / "daily_score.json").exists(), "", results)
    check("output/zfe_alerts.log existe", (output_dir / "zfe_alerts.log").exists(), "", results)
    log_txt = (output_dir / "zfe_alerts.log").read_text(encoding="utf-8")
    check("zfe_alerts.log contient APPROCHE + ENTREE + PRESENCE", all(tag in log_txt for tag in ("APPROCHE", "ENTREE", "PRESENCE")), "", results)
    score_json = json.loads((output_dir / "daily_score.json").read_text(encoding="utf-8"))
    check("daily_score.json contient score 85", score_json.get("daily_safety_score") == 85, f"score={score_json.get('daily_safety_score')}", results)
    tmp_left = list(output_dir.glob("*.tmp"))
    check("Aucun fichier temporaire atomique residuel", len(tmp_left) == 0, f"tmp={tmp_left}", results)

    # ------------------------------------------------------------------
    # 5. Robustesse : erreurs de donnees controlees
    # ------------------------------------------------------------------
    print(c_head("\n[TEST] Robustesse (cas negatifs) :"))
    expect_poc_data_error("Fichier absent => erreur controlee", lambda: load_json_strict("data/inexistant.json", "polygon"), results)

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        tmp.write('{"broken": [')
        bad_json = tmp.name
    try:
        expect_poc_data_error("JSON malforme => erreur controlee", lambda: load_json_strict(bad_json, "polygon"), results)
    finally:
        os.unlink(bad_json)

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        tmp.write('{"autre_cle": []}')
        no_key = tmp.name
    try:
        expect_poc_data_error("Cle polygon absente => erreur controlee", lambda: load_json_strict(no_key, "polygon"), results)
    finally:
        os.unlink(no_key)

    expect_poc_data_error("Polygone trop court => erreur controlee", lambda: normalize_polygon([{"lat": 1, "lon": 1}, {"lat": 2, "lon": 2}]), results)
    expect_poc_data_error("Latitude invalide => erreur controlee", lambda: validate_gps_points([{"lat": 145, "lon": 4.8, "timestamp": "x"}]), results)

    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
        tmp.write("timestamp,acc_x,acc_z\n1,0.1,9.8\n")
        no_col = tmp.name
    try:
        expect_poc_data_error("Colonne acc_y absente => erreur controlee", lambda: SafetyEngine().process_csv(no_col), results)
    finally:
        os.unlink(no_col)

    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
        tmp.write("timestamp,acc_x,acc_y,acc_z\n1,0.1,abc,9.8\n2,0.1,-3.0,9.8\n")
        bad_val = tmp.name
    try:
        s_bad = SafetyEngine()
        s_bad.process_csv(bad_val)
        check("Valeur non numerique => ligne ignoree avec avertissement", s_bad.skipped_rows == 1 and len(s_bad.events) == 1, f"ignorees={s_bad.skipped_rows}, events={len(s_bad.events)}", results)
    finally:
        os.unlink(bad_val)

    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
        tmp.write("")
        empty_csv = tmp.name
    try:
        expect_poc_data_error("CSV vide => erreur controlee", lambda: SafetyEngine().process_csv(empty_csv), results)
    finally:
        os.unlink(empty_csv)

    # ------------------------------------------------------------------
    # 6. Bout-en-bout : corruption d'une entree => code 1 sans sortie partielle
    # ------------------------------------------------------------------
    print(c_head("\n[TEST] Bout-en-bout et precontrole :"))
    polygon_path = PROJECT_ROOT / POLYGON_FILE
    backup_path = polygon_path.with_suffix(".json.bak")
    shutil.copy(polygon_path, backup_path)
    try:
        # On supprime les anciennes sorties pour verifier qu'une erreur de precontrole
        # ne produit pas de fichier partiel.
        for candidate in (output_dir / "zfe_alerts.log", output_dir / "daily_score.json"):
            if candidate.exists():
                candidate.unlink()
        polygon_path.write_text('{"broken": [', encoding="utf-8")
        proc = subprocess.run([sys.executable, "-S", "src/main.py"], capture_output=True, text=True)
        combined = proc.stdout + proc.stderr
        check("main.py + JSON corrompu => code 1 sans stack trace", proc.returncode == 1 and "JSON malforme" in combined and "Traceback" not in combined, f"code={proc.returncode}", results)
        check("Erreur de precontrole => pas de zfe_alerts.log partiel", not (output_dir / "zfe_alerts.log").exists(), "", results)
        check("Erreur de precontrole => pas de daily_score.json partiel", not (output_dir / "daily_score.json").exists(), "", results)
    finally:
        shutil.move(backup_path, polygon_path)
        app_main()  # restore outputs for demonstration

    # ------------------------------------------------------------------
    # 7. Bilan final
    # ------------------------------------------------------------------
    total = len(results)
    ok = sum(results)
    print(c_sep("\n" + "=" * 66))
    if ok == total:
        print(c_pass(f"Bilan : {ok}/{total} tests passes - POC robuste valide pour la demonstration"))
    else:
        print(c_fail(f"Bilan : {ok}/{total} passes - corriger avant depot"))
    print(c_sep("=" * 66))
    return ok == total


if __name__ == "__main__":
    sys.exit(0 if run_all_tests() else 1)
