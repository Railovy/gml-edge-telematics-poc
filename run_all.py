#!/usr/bin/env python3
"""
run_all.py - Point d'entrée unique du POC GreenMove Edge Telematics.
Appelle le moteur principal (ZFE + Safety) puis les tests de non-régression.

Usage :
    python3 run_all.py
"""
import subprocess, sys, os

BASE = os.path.dirname(os.path.abspath(__file__))

def run(cmd, label):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    result = subprocess.run([sys.executable] + cmd, cwd=BASE)
    if result.returncode != 0:
        print(f"\nERREUR : '{label}' a échoué (code {result.returncode})")
        sys.exit(result.returncode)

if __name__ == "__main__":
    run(["src/main.py"],  "ETAPE 1/2 : Moteurs ZFE + Safety (src/main.py)")
    run(["run_tests.py"], "ETAPE 2/2 : Tests de non-régression (run_tests.py)")
    print("\n✓ run_all.py terminé avec succès.\n")
