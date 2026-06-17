"""
GML Edge Telematics - Tests de non-regression
==============================================
Verifie que les sorties du POC sont conformes aux attendus.
Usage : python run_tests.py (depuis la racine du projet)
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from main import (ZFEEngine, SafetyEngine,
                  POLYGON_FILE, GPS_FILE, ACC_FILE,
                  c_sep, c_title, c_success, c_error, c_dim, c_safety,
                  c_alert, c_prealert, c_green, Fore, Style)

# ---------------------------------------------------------------------------
# Helpers couleurs specifiques aux tests
# ---------------------------------------------------------------------------
try:
    from colorama import Fore as _F, Style as _S
    def c_pass(text):  return _F.GREEN  + "  [PASS] " + text + _S.RESET_ALL
    def c_fail(text):  return _F.RED + _S.BRIGHT + "  [FAIL] " + text + _S.RESET_ALL
    def c_head(text):  return _F.CYAN  + text + _S.RESET_ALL
    def c_bilan_ok(text): return _F.GREEN + _S.BRIGHT + " " + text + _S.RESET_ALL
    def c_bilan_ko(text): return _F.RED  + _S.BRIGHT + " " + text + _S.RESET_ALL
except ImportError:
    def c_pass(text):     return "  [PASS] " + text
    def c_fail(text):     return "  [FAIL] " + text
    def c_head(text):     return text
    def c_bilan_ok(text): return " " + text
    def c_bilan_ko(text): return " " + text


# ===========================================================================
# RUNNER DE TESTS
# ===========================================================================

def check(name: str, passed: bool, detail: str, results: list) -> None:
    """Affiche [PASS] ou [FAIL] et enregistre le resultat."""
    if passed:
        print(c_pass(f"{name} ({detail})"))
    else:
        print(c_fail(f"{name} ({detail})"))
    results.append(passed)


def run_all_tests() -> bool:
    results = []
    os.makedirs("output", exist_ok=True)

    print(c_sep("=" * 60))
    print(c_title(" GML POC - Tests de non-regression"))
    print(c_sep("=" * 60))

    # ------------------------------------------------------------------
    # BLOC 1 : Moteur ZFE
    # ------------------------------------------------------------------
    print(c_head("\n[TEST] Moteur ZFE :"))
    try:
        engine = ZFEEngine(POLYGON_FILE)
        with open(GPS_FILE, "r", encoding="utf-8") as f:
            gps_data = json.load(f)

        statuses = {}
        for point in gps_data["points"]:
            r = engine.evaluate(
                point["id"], point["lat"], point["lon"],
                point["timestamp"], point.get("expected", "?"),
            )
            statuses[point["id"]] = r["status"]

        check("Point 1 = OUT",       statuses.get(1) == "OUT",       f"obtenu={statuses.get(1)}", results)
        check("Point 2 = OUT",       statuses.get(2) == "OUT",       f"obtenu={statuses.get(2)}", results)
        check("Point 3 = PRE_ALERT", statuses.get(3) == "PRE_ALERT", f"obtenu={statuses.get(3)}", results)
        check("Point 4 = IN",        statuses.get(4) == "IN",        f"obtenu={statuses.get(4)}", results)
        check("Point 5 = IN",        statuses.get(5) == "IN",        f"obtenu={statuses.get(5)}", results)

    except Exception as e:
        print(c_fail(f"Exception ZFE : {e}"))
        results.append(False)

    # ------------------------------------------------------------------
    # BLOC 2 : Moteur Safety
    # ------------------------------------------------------------------
    print(c_head("\n[TEST] Moteur Safety :"))
    try:
        engine_s = SafetyEngine()
        engine_s.process_csv(ACC_FILE)
        score_data   = engine_s.to_json()
        harsh_count  = len(engine_s.events)
        score        = score_data["daily_safety_score"]
        min_acc      = score_data["min_acc_y_ms2"]
        sev          = engine_s.events[0]["severity"] if engine_s.events else "N/A"

        check("1 freinage violent detecte",  harsh_count == 1,   f"obtenu={harsh_count}", results)
        check("Score conducteur = 85/100",   score == 85,        f"obtenu={score}",       results)
        check("Valeur min acc_y = -3.45",    min_acc == -3.45,   f"obtenu={min_acc}",     results)
        check("Severite = HIGH",             sev == "HIGH",      f"obtenu={sev}",         results)

    except Exception as e:
        print(c_fail(f"Exception Safety : {e}"))
        results.append(False)

    # ------------------------------------------------------------------
    # BLOC 3 : Fichiers de sortie
    # ------------------------------------------------------------------
    print(c_head("\n[TEST] Fichiers de sortie :"))
    check("output/zfe_alerts.log existe",   os.path.exists("output/zfe_alerts.log"),   "", results)
    check("output/daily_score.json existe", os.path.exists("output/daily_score.json"), "", results)

    # ------------------------------------------------------------------
    # BILAN
    # ------------------------------------------------------------------
    total   = len(results)
    nb_pass = sum(results)
    nb_fail = total - nb_pass

    print(c_sep(f"\n{'=' * 60}"))
    if nb_pass == total:
        print(c_bilan_ok(f"Bilan : {nb_pass}/{total} tests passes"))
        print(c_bilan_ok("SUCCES - POC valide pour la demonstration"))
    else:
        print(c_bilan_ko(f"Bilan : {nb_pass}/{total} passes, {nb_fail} echec(s)"))
        print(c_bilan_ko("ECHEC - Corriger avant depot"))
    print(c_sep("=" * 60))

    return nb_pass == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
