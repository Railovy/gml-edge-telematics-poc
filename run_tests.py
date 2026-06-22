"""
GML Edge Telematics - Tests de non-regression
==============================================
Verifie que les sorties du POC restent conformes aux attendus.
Usage : python run_tests.py (depuis la racine du projet)
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from main import (ZFEEngine, SafetyEngine,
                  POLYGON_FILE, GPS_FILE, ACC_FILE,
                  c_sep, c_title, Fore, Style)

try:
    from colorama import Fore as _F, Style as _S
    def c_pass(t): return _F.GREEN + "  [PASS] " + t + _S.RESET_ALL
    def c_fail(t): return _F.RED + _S.BRIGHT + "  [FAIL] " + t + _S.RESET_ALL
    def c_head(t): return _F.CYAN + t + _S.RESET_ALL
except ImportError:
    def c_pass(t): return "  [PASS] " + t
    def c_fail(t): return "  [FAIL] " + t
    def c_head(t): return t


def check(name, passed, detail, results):
    print(c_pass(f"{name} ({detail})") if passed else c_fail(f"{name} ({detail})"))
    results.append(passed)


def run_all_tests():
    results = []
    os.makedirs("output", exist_ok=True)

    print(c_sep("=" * 60))
    print(c_title(" GML POC - Tests de non-regression"))
    print(c_sep("=" * 60))

    # ---- Moteur ZFE ----
    print(c_head("\n[TEST] Moteur ZFE :"))
    engine = ZFEEngine(POLYGON_FILE)
    with open(GPS_FILE, "r", encoding="utf-8") as f:
        gps = json.load(f)
    res = {p["id"]: engine.evaluate(p["id"], p["lat"], p["lon"],
                                    p["timestamp"], p.get("expected", "?"))
           for p in gps["points"]}

    check("Point 1 = OUT",       res[1]["status"] == "OUT",       f"obtenu={res[1]['status']}", results)
    check("Point 2 = OUT",       res[2]["status"] == "OUT",       f"obtenu={res[2]['status']}", results)
    check("Point 3 = PRE_ALERT", res[3]["status"] == "PRE_ALERT", f"obtenu={res[3]['status']}", results)
    check("Point 4 = IN",        res[4]["status"] == "IN",        f"obtenu={res[4]['status']}", results)
    check("Point 5 = IN",        res[5]["status"] == "IN",        f"obtenu={res[5]['status']}", results)

    # ---- Optimisation : la boite rejette en O(1) sans calculer la distance ----
    print(c_head("\n[TEST] Optimisation Bounding Box :"))
    check("Point 1 : distance non calculee (rejet O(1))", res[1]["dist_m"] is None,
          f"dist_m={res[1]['dist_m']}", results)
    check("Point 4 : entree detectee (transition)", res[4]["is_entry"] is True,
          f"is_entry={res[4]['is_entry']}", results)
    check("Point 5 : presence, pas une nouvelle entree", res[5]["is_entry"] is False,
          f"is_entry={res[5]['is_entry']}", results)

    # ---- Moteur Safety ----
    print(c_head("\n[TEST] Moteur Safety (regroupement en evenements) :"))
    safety = SafetyEngine()
    safety.process_csv(ACC_FILE)
    data = safety.to_json()

    check("1 echantillon sous seuil",        data["harsh_braking_samples"] == 1, f"obtenu={data['harsh_braking_samples']}", results)
    check("1 evenement (regroupement)",       data["harsh_braking_events"] == 1,  f"obtenu={data['harsh_braking_events']}",  results)
    check("Ligne -3.45 detectee (min)",       data["min_acc_y_ms2"] == -3.45 and any(e["peak_acc_y"] == -3.45 for e in safety.events),
          f"min={data['min_acc_y_ms2']}", results)
    check("Evenement 1 = HIGH",               safety.events[0]["severity"] == "HIGH",   f"obtenu={safety.events[0]['severity']}",   results)
    check("Score = 85/100",                   data["daily_safety_score"] == 85, f"obtenu={data['daily_safety_score']}", results)

    # ---- Fichiers de sortie ----
    print(c_head("\n[TEST] Fichiers de sortie :"))
    with open("output/daily_score.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    check("output/daily_score.json existe", os.path.exists("output/daily_score.json"), "", results)

    # ---- Bilan ----
    total, ok = len(results), sum(results)
    print(c_sep("\n" + "=" * 60))
    if ok == total:
        print(c_pass(f"Bilan : {ok}/{total} tests passes - POC valide pour la demonstration"))
    else:
        print(c_fail(f"Bilan : {ok}/{total} passes - corriger avant depot"))
    print(c_sep("=" * 60))
    return ok == total


if __name__ == "__main__":
    sys.exit(0 if run_all_tests() else 1)
