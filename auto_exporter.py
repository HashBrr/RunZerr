#!/usr/bin/env python3
"""
RunZerr - Auto Exporter V5 (Robust Full-History Extraction)
Extraction autonome et intégrale des 78 courses Huawei Santé,
avec protection anti-fermeture de l'historique et synchronisation continue.
"""

import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from collector import sync_all
except ImportError:
    sync_all = None


# Séances déjà extraites lors des passes précédentes (pour défilement rapide vers la suite)
PRELOADED_KEYS = {
    "25 octobre_08:44_21,41",
    "23 octobre_18:45_0,94",
    "18 octobre_16:34_9,08",
    "17 octobre_13:49_1,31",
    "13 octobre_15:58_8,03",
    "7 octobre_17:03_15,33",
    "6 octobre_16:55_10,11",
    "2 octobre_15:58_0,94",
    "1 octobre_18:40_5,07",
    "1 octobre_18:01_1,12",
    "27 septembre_17:42_10,02",
    "23 septembre_19:44_2,84",
    "22 septembre_18:44_8,01",
    "22 septembre_18:00_0,81",
    "22 septembre_17:30_0,43",
    "20 septembre_18:14_0,89",
    "18 septembre_18:42_6,01",
    "16 septembre_19:02_4,19",
}


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
    """Revient proprement à la liste en vérifiant l'écran et sans jamais sur-fermer l'activité."""
    for _ in range(5):
        focus = get_current_focus()
        if "SportHistoryActivity" in focus or "MainActivity" in focus:
            return True
        keyevent(4, sleep_after=1.2)
    return False


def ensure_history_activity():
    """Vérifie que l'écran actuel affiche bien la liste."""
    focus = get_current_focus()
    if "SportHistoryActivity" not in focus and "MainActivity" not in focus:
        return_to_list()


def get_visible_workouts() -> list[dict]:
    """Analyse l'arborescence UI et renvoie les séances visibles avec leurs coordonnées."""
    try:
        out = subprocess.check_output(
            ["adb", "exec-out", "uiautomator", "dump", "/dev/tty"],
            stderr=subprocess.DEVNULL,
            timeout=10,
        ).decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"⚠️ Erreur lors du dump uiautomator : {e}")
        return []

    xml_start = out.find("<?xml")
    xml_end = out.rfind("</hierarchy>") + len("</hierarchy>")
    if xml_start == -1 or xml_end == -1:
        return []

    try:
        root = ET.fromstring(out[xml_start:xml_end])
    except Exception:
        return []

    workouts = []
    for node in root.iter("node"):
        cid = node.attrib.get("resource-id", "")
        if cid.endswith(":id/hw_show_health_running_history_child_item_layout"):
            bounds = node.attrib.get("bounds", "")
            m = re.findall(r"\[(\d+),(\d+)\]", bounds)
            if len(m) == 2:
                y1, y2 = int(m[0][1]), int(m[1][1])
                # Éléments visibles entre la bannière et le bas
                if y1 >= 350 and y2 <= 2280:
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
                    workouts.append({
                        "key": key,
                        "date": date_txt,
                        "time": time_txt,
                        "dist": dist_txt,
                        "y": y_center,
                    })

    return workouts


def export_single_workout(y: int) -> bool:
    """Ouvre une séance, déclenche l'export de la fiche haute définition, et revient à la liste."""
    # 1. Clic sur la séance dans la liste
    tap(540, y, sleep_after=2.5)

    # 2. Clic sur l'icône Partager en haut à droite (bounds: [900,127][1044,271])
    tap(972, 199, sleep_after=3.0)

    # 3. Sur l'écran 'Aperçu', clic sur l'icône de partage (bounds: [852,127][1044,271])
    tap(948, 199, sleep_after=2.0)

    # 4. Clic sur le bouton 'Enregistrer' (bounds: [72,2103][516,2223])
    tap(294, 2163, sleep_after=2.5)

    # 5. Retour sécurisé à la liste
    return_to_list()
    return True


def scroll_list():
    """Fait défiler la liste vers le bas (swipe du bas vers le haut)"""
    run_adb(["shell", "input", "swipe", "540", "1950", "540", "1350", "400"])
    time.sleep(1.8)


def run_full_export(target_max: int = 100):
    print("=" * 65)
    print("🚀 RunZerr - Reprise & Finalisation de l'historique complet")
    print(f"🎯 Objectif : Récupérer les séances restantes sur les 78 au total")
    print("=" * 65)

    # Maintenir l'écran éveillé
    run_adb(["shell", "svc", "power", "stayon", "usb"])
    run_adb(["shell", "settings", "put", "system", "screen_off_timeout", "600000"])

    exported_keys = set(PRELOADED_KEYS)
    print(f"⚡ {len(exported_keys)} séances déjà connues ignorées (défilement rapide).")

    new_exported = 0
    stagnant_scrolls = 0

    while True:
        ensure_history_activity()
        visible = get_visible_workouts()

        if not visible:
            print("📜 Défilement...")
            scroll_list()
            time.sleep(1.5)
            stagnant_scrolls += 1
            if stagnant_scrolls >= 4:
                print("\n🏁 FIN DE L'HISTORIQUE ATTEINTE ! Toutes les séances ont été traitées.")
                break
            continue

        new_items = [w for w in visible if w["key"] not in exported_keys]

        if not new_items:
            # Toutes les séances visibles sont déjà exportées, on fait défiler rapidement
            print("⏩ Déjà traitées sur cette vue -> défilement rapide...")
            scroll_list()
            time.sleep(1.2)
            new_visible = get_visible_workouts()
            if [w["key"] for w in new_visible] == [w["key"] for w in visible]:
                stagnant_scrolls += 1
                if stagnant_scrolls >= 4:
                    print("\n🏁 FIN DE L'HISTORIQUE ATTEINTE ! Toutes les séances ont été traitées.")
                    break
            else:
                stagnant_scrolls = 0
            continue

        stagnant_scrolls = 0

        for w in new_items:
            new_exported += 1
            total_total = len(exported_keys) + 1
            print(f"▶️ [Nouvelle séance #{new_exported} | Total global : ~{total_total}/78] Export : {w['date']} ({w['dist']} km)...")
            try:
                export_single_workout(w["y"])
                exported_keys.add(w["key"])
                print(f"   ✅ Séance du {w['date']} ({w['dist']} km) enregistrée avec succès.")
            except Exception as e:
                print(f"   ⚠️ Erreur : {e}")
                ensure_history_activity()

            # Synchronisation intermédiaire toutes les 5 séances
            if new_exported % 5 == 0 and sync_all:
                print(f"💾 Synchronisation intermédiaire ({new_exported} nouvelles séances sauvegardées)...")
                sync_all()

            time.sleep(0.8)

    print("\n" + "=" * 65)
    print(f"🎉 MISSION ACCOMPLIE ! {new_exported} nouvelles séances exportées.")
    print("📥 Lancement de la synchronisation finale vers RunZerr/data/...")
    print("=" * 65)

    if sync_all:
        sync_all()


if __name__ == "__main__":
    run_full_export()
