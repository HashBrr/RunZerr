#!/usr/bin/env python3
"""
RunZerr - Full Autonomous Exporter
Parcourt l'intégralité de l'historique Huawei Santé, déplie tous les accordéons
de mois de 2025 et 2024, exporte chaque course et synchronise tout dans RunZerr.
100% autonome et sans interruption.
"""

import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

try:
    from collector import sync_all
except ImportError:
    sync_all = None


def run_adb(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["adb"] + cmd, capture_output=True, text=True, check=False)


def tap(x: int, y: int, sleep_after: float = 1.0):
    run_adb(["shell", "input", "tap", str(x), str(y)])
    time.sleep(sleep_after)


def keyevent(code: int, sleep_after: float = 1.0):
    run_adb(["shell", "input", "keyevent", str(code)])
    time.sleep(sleep_after)


def get_current_focus() -> str:
    res = run_adb(["shell", "dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'"])
    return res.stdout


def return_to_list():
    """Revient proprement à la liste en s'arrêtant dès qu'elle est atteinte."""
    for _ in range(6):
        focus = get_current_focus()
        if "SportHistoryActivity" in focus or "MainActivity" in focus:
            return True
        keyevent(4, sleep_after=1.2)
    return False


def ensure_history_activity():
    """Garantit que nous sommes bien sur l'écran d'historique."""
    focus = get_current_focus()
    if "SportHistoryActivity" not in focus and "MainActivity" not in focus:
        return_to_list()


def dump_ui():
    try:
        out = subprocess.check_output(
            ["adb", "exec-out", "uiautomator", "dump", "/dev/tty"],
            stderr=subprocess.DEVNULL,
            timeout=10,
        ).decode("utf-8", errors="ignore")
    except Exception:
        return None

    xml_start = out.find("<?xml")
    xml_end = out.rfind("</hierarchy>") + len("</hierarchy>")
    if xml_start == -1 or xml_end == -1:
        return None

    try:
        return ET.fromstring(out[xml_start:xml_end])
    except Exception:
        return None


def get_visible_elements(root):
    """Extrait les courses dépliées et les en-têtes de mois visibles."""
    courses = []
    month_headers = []

    if root is None:
        return courses, month_headers

    for node in root.iter("node"):
        cid = node.attrib.get("resource-id", "")
        bounds = node.attrib.get("bounds", "")
        m = re.findall(r"\[(\d+),(\d+)\]", bounds)
        if len(m) != 2:
            continue
        y1, y2 = int(m[0][1]), int(m[1][1])

        # 1. Détection des séances dépliées
        if cid.endswith(":id/hw_show_health_running_history_child_item_layout"):
            if y1 >= 320 and y2 <= 2280:
                date_txt = ""
                time_txt = ""
                dist_txt = ""
                for child in node.iter("node"):
                    ccid = child.attrib.get("resource-id", "")
                    ctxt = child.attrib.get("text", "")
                    if "date" in ccid and "left" not in ccid and ctxt:
                        date_txt = ctxt
                    elif "left_date" in ccid and ctxt:
                        time_txt = ctxt
                    elif "chief_sport_data_text" in ccid and ctxt:
                        dist_txt = ctxt
                y_center = (y1 + y2) // 2
                key = f"{date_txt}_{time_txt}_{dist_txt}"
                courses.append({
                    "key": key,
                    "date": date_txt,
                    "time": time_txt,
                    "dist": dist_txt,
                    "y": y_center,
                })

        # 2. Détection des en-têtes de mois
        elif cid.endswith(":id/first_item_title") or cid.endswith(":id/hw_show_health_data_running_history_father_date"):
            desc = node.attrib.get("content-desc", "")
            txt = node.attrib.get("text", "")
            name = desc or txt
            if name and any(y in name.lower() for y in ["2024", "2025", "2026"]):
                if y1 >= 280 and y2 <= 2280:
                    y_center = (y1 + y2) // 2
                    month_headers.append({
                        "name": name,
                        "y": y_center,
                    })

    return courses, month_headers


def export_single_workout(y: int) -> bool:
    """Cycle complet d'export d'une course en haute définition."""
    # 1. Clic sur la séance
    tap(540, y, sleep_after=2.5)

    # 2. Clic Partager (haut droite)
    tap(972, 199, sleep_after=3.0)

    # 3. Clic Partager sur Aperçu
    tap(948, 199, sleep_after=2.0)

    # 4. Clic Enregistrer image
    tap(294, 2163, sleep_after=2.5)

    # 5. Retour propre
    return_to_list()
    return True


def scroll_down():
    run_adb(["shell", "input", "swipe", "540", "1800", "540", "900", "400"])
    time.sleep(1.8)


def main():
    print("=" * 70)
    print("🚀 RunZerr - Exportation Totale Autonome (2024 - 2026)")
    print("=" * 70)

    run_adb(["shell", "svc", "power", "stayon", "usb"])
    run_adb(["shell", "settings", "put", "system", "screen_off_timeout", "600000"])

    exported_keys = set()
    # Initialiser avec ce qui a déjà été exporté en 2026
    preloaded = [
        "25 octobre_08:44_21,41", "23 octobre_18:45_0,94", "18 octobre_16:34_9,08",
        "17 octobre_13:49_1,31", "13 octobre_15:58_8,03", "7 octobre_17:03_15,33",
        "6 octobre_16:55_10,11", "2 octobre_15:58_0,94", "1 octobre_18:40_5,07",
        "1 octobre_18:01_1,12", "27 septembre_17:42_10,02", "23 septembre_19:44_2,84",
        "22 septembre_18:44_8,01", "22 septembre_18:00_0,81", "22 septembre_17:30_0,43",
        "20 septembre_18:14_0,89", "18 septembre_18:42_6,01", "16 septembre_19:02_4,19",
        "12 septembre_19:00_8,69", "12 septembre_18:30_0,63", "7 septembre_18:00_13,71",
    ]
    exported_keys.update(preloaded)

    expanded_months = set()
    # Octobre 2025 a été déplié lors du test
    expanded_months.add("OCTOBRE 2025")

    total_new = 0
    stagnant_cycles = 0

    while True:
        ensure_history_activity()
        root = dump_ui()
        courses, months = get_visible_elements(root)

        # 1. Vérifier s'il y a des courses dépliées non exportées
        unexported = [c for c in courses if c["key"] not in exported_keys]

        if unexported:
            stagnant_cycles = 0
            for c in unexported:
                total_new += 1
                print(f"▶️ [Séance #{total_new}] Export : {c['date']} ({c['dist']} km)...")
                try:
                    export_single_workout(c["y"])
                    exported_keys.add(c["key"])
                    print(f"   ✅ Séance du {c['date']} ({c['dist']} km) enregistrée avec succès.")
                except Exception as e:
                    print(f"   ⚠️ Erreur : {e}")
                    ensure_history_activity()

                if total_new % 5 == 0 and sync_all:
                    print(f"💾 Sauvegarde intermédiaire ({total_new} nouvelles séances)...")
                    sync_all()

                time.sleep(0.8)
            continue

        # 2. Si aucune course dépliée, chercher un en-tête de mois à déplier
        unexpanded_months = [m for m in months if m["name"].upper() not in expanded_months and not any(k in m["name"].upper() for k in ["OCTOBRE 2026", "SEPTEMBRE 2026"])]

        if unexpanded_months:
            stagnant_cycles = 0
            target_month = unexpanded_months[0]
            print(f"📂 Dépliage du mois : {target_month['name']} à y={target_month['y']}...")
            tap(540, target_month["y"], sleep_after=1.8)
            expanded_months.add(target_month["name"].upper())
            # Après dépliage, la boucle réanalysera l'écran pour trouver les courses
            continue

        # 3. Si tout sur l'écran actuel est déplié et exporté, défiler vers le bas
        print("📜 Défilement vers les mois suivants...")
        scroll_down()
        time.sleep(1.5)
        stagnant_cycles += 1

        if stagnant_cycles >= 5:
            print("\n🏁 FIN DE L'HISTORIQUE ATTEINTE ! Toutes les séances ont été traitées jusqu'à décembre 2024.")
            break

    print("\n" + "=" * 70)
    print(f"🎉 SUCCÈS TOTAL ! {total_new} séances de 2025 et 2024 ont été exportées.")
    print("📥 Lancement de la synchronisation finale vers RunZerr/data/...")
    print("=" * 70)

    if sync_all:
        sync_all()


if __name__ == "__main__":
    main()
