#!/usr/bin/env python3
"""
RunZerr - Fast Data Organizer & Classifier
Extrait, nettoie, dédoublonne et classe chronologiquement l'ensemble des courses
dans des formats structurés (JSON, CSV, Markdown) prêts pour n'importe quel modèle d'IA.
"""

import csv
import json
import os
import re
import shutil
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from PIL import Image
import pytesseract

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_IMAGES_DIR = DATA_DIR / "raw_images"
RUNS_DIR = DATA_DIR / "runs"
JSON_OUTPUT = DATA_DIR / "athlete_dataset.json"
CSV_OUTPUT = DATA_DIR / "athlete_dataset.csv"
SUMMARY_OUTPUT = DATA_DIR / "summary_runs.md"


def clean_int(val_str: str) -> int:
    if not val_str:
        return 0
    digits = re.sub(r"[^\d]", "", val_str)
    return int(digits) if digits else 0


def clean_float(val_str: str) -> float | None:
    if not val_str:
        return None
    val_str = val_str.replace(",", ".")
    m = re.search(r"\d+(\.\d+)?", val_str)
    return float(m.group(0)) if m else None


def parse_duration_to_seconds(dur_str: str) -> int:
    if not dur_str:
        return 0
    parts = dur_str.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return 0


def parse_pace_to_seconds(pace_str: str) -> int:
    if not pace_str:
        return 0
    m = re.search(r"(\d+)['\"’°](\d{2})", pace_str)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return 0


def parse_single_card(img_path: str) -> dict | None:
    try:
        im = Image.open(img_path)
    except Exception as e:
        print(f"⚠️ Erreur ouverture {os.path.basename(img_path)}: {e}")
        return None

    # Section 1: En-tête et métriques générales (0 à 2500 px)
    crop1 = im.crop((0, 0, 1080, min(2500, im.height)))
    txt1 = pytesseract.image_to_string(crop1, lang="fra")

    # Date & Heure : JJ/MM/AAAA HH:MM
    m_date = re.search(r"(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2})", txt1)
    if not m_date:
        return None

    day, month, year, hour, minute = m_date.groups()
    run_date = f"{year}-{month}-{day}"
    run_time = f"{hour}:{minute}"
    run_id = f"{run_date}_{hour}-{minute}"

    # Durée : HH:MM:SS ou MM:SS
    m_dur = re.search(r"(?:(\d{2}):)?(\d{2}):(\d{2})", txt1)
    dur_str = m_dur.group(0) if m_dur else ""
    dur_sec = parse_duration_to_seconds(dur_str)

    # Allure : M'SS" ou M°SS"
    m_pace = re.search(r"(\d+)[\'\"’°](\d{2})[\'\"’]?", txt1)
    pace_str = f"{m_pace.group(1)}'{m_pace.group(2)}\"" if m_pace else ""
    pace_sec = parse_pace_to_seconds(pace_str)

    # Vitesse : X,XX km/h
    m_speed = re.search(r"(\d+[\.,]\d+)\s*km/h", txt1)
    speed_kmh = float(m_speed.group(1).replace(",", ".")) if m_speed else 0.0

    # Calories : XXX kcal
    m_cal = re.search(r"(\d+[\s\d]*)\s*kcal", txt1)
    calories = clean_int(m_cal.group(1)) if m_cal else 0

    # Cadence : XXX pas/min
    m_cad = re.search(r"(\d{2,3})\s*pas/min", txt1)
    cadence = clean_int(m_cad.group(1)) if m_cad else 0

    # Longueur de foulée : XX cm
    m_stride = re.search(r"(\d{2,3})\s*cm", txt1)
    stride_cm = clean_int(m_stride.group(1)) if m_stride else 0

    # Calcul précis de la distance (km)
    dist_km = 0.0
    if dur_sec > 0 and pace_sec > 0:
        dist_km = round(dur_sec / pace_sec, 2)
    elif speed_kmh > 0 and dur_sec > 0:
        dist_km = round((speed_kmh * dur_sec) / 3600, 2)
    else:
        m_dist = re.search(r"(\d+[\.,\s]\d+)\s*(?:km|Course)", txt1)
        if m_dist:
            dist_val = clean_float(m_dist.group(1))
            dist_km = dist_val if dist_val else 0.0

    # Section 2: Cardio, Dénivelé & Biomécanique (2500 à 4800 px)
    crop2 = im.crop((0, 2500, 1080, min(4800, im.height)))
    txt2 = pytesseract.image_to_string(crop2, lang="fra")

    # Temps de contact sol : XXX ms
    m_gct = re.search(r"(\d{3})\s*ms", txt2)
    gct_ms = clean_int(m_gct.group(1)) if m_gct else None

    # Équilibre G/D : Gauche : XX,X % - Droite : XX,X %
    m_bal = re.search(r"Gauche\s*:\s*(\d+[\.,]\d+)\s*%.*?Droite\s*:\s*(\d+[\.,]\d+)\s*%", txt2, re.DOTALL)
    bal_l = clean_float(m_bal.group(1)) if m_bal else None
    bal_r = clean_float(m_bal.group(2)) if m_bal else None

    # Oscillation verticale : X,X cm ou XX cm
    m_vo = re.search(r"Oscillation.*?(\d+[\.,]?\d*)\s*cm", txt2, re.DOTALL)
    vo_cm = None
    if m_vo:
        raw_vo = clean_float(m_vo.group(1))
        if raw_vo:
            vo_cm = raw_vo if raw_vo < 20 else round(raw_vo / 10, 1)

    # Fréquence cardiaque moyenne et max
    m_hr = re.search(r"Rythme cardiaque \(bpm\)\s*.*?(?:Moyenne|M\))\s*.*?(?:Maximum)?\s*(\d{2,3})\s+(\d{2,3})", txt2, re.DOTALL)
    hr_avg = clean_int(m_hr.group(1)) if m_hr else None
    hr_max = clean_int(m_hr.group(2)) if m_hr else None
    if not hr_avg:
        m_hr_alt = re.search(r"cardiaque.*?moyen.*?(\d{2,3})\s*bpm", txt2, re.DOTALL | re.IGNORECASE)
        if m_hr_alt:
            hr_avg = clean_int(m_hr_alt.group(1))

    # Dénivelé
    m_elev = re.search(r"Montée totale\s*.*?(\d+[\.,]\d+)\s*m", txt2, re.DOTALL)
    elev_gain = clean_float(m_elev.group(1)) if m_elev else None

    return {
        "id": run_id,
        "date": run_date,
        "time": run_time,
        "datetime": f"{run_date}T{run_time}:00",
        "distance_km": dist_km,
        "duration": dur_str,
        "duration_seconds": dur_sec,
        "pace_avg": pace_str,
        "pace_seconds_per_km": pace_sec,
        "speed_kmh": speed_kmh,
        "calories_kcal": calories,
        "cadence_spm": cadence,
        "stride_length_cm": stride_cm,
        "heart_rate_avg_bpm": hr_avg,
        "heart_rate_max_bpm": hr_max,
        "ground_contact_time_ms": gct_ms,
        "vertical_oscillation_cm": vo_cm,
        "balance_left_pct": bal_l,
        "balance_right_pct": bal_r,
        "elevation_gain_m": elev_gain,
        "source_image": os.path.basename(img_path),
    }


def main():
    print("=" * 65)
    print("🏃 RunZerr - Structuration & Classification des Courses")
    print("=" * 65)

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    images = sorted(RAW_IMAGES_DIR.glob("*.jpg"))
    print(f"📂 Fiches d'activité brutes détectées : {len(images)}")
    print(f"⚙️  Extraction OCR optimisée en parallèle ({os.cpu_count()} cœurs CPU)...")

    start_time = time.time()
    results = []
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
        for res in executor.map(parse_single_card, [str(p) for p in images]):
            if res:
                results.append(res)

    elapsed = time.time() - start_time
    print(f"✅ Extraction terminée en {elapsed:.1f} secondes ({len(results)} séances analysées).")

    # Dédoublonnage par ID (date + heure)
    unique_runs = {}
    for r in results:
        rid = r["id"]
        if rid not in unique_runs:
            unique_runs[rid] = r
        else:
            existing_fields = sum(1 for v in unique_runs[rid].values() if v is not None)
            new_fields = sum(1 for v in r.values() if v is not None)
            if new_fields > existing_fields:
                unique_runs[rid] = r

    # Tri chronologique strict (du plus ancien au plus récent)
    sorted_runs = sorted(unique_runs.values(), key=lambda x: x["datetime"])
    print(f"📊 Séances uniques identifiées après dédoublonnage : {len(sorted_runs)}")

    # 1. Sauvegarde des JSON individuels dans data/runs/
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    for r in sorted_runs:
        json_path = RUNS_DIR / f"{r['id']}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(r, f, indent=2, ensure_ascii=False)

    # 2. Sauvegarde du fichier maître JSON
    with open(JSON_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(sorted_runs, f, indent=2, ensure_ascii=False)
    print(f"💾 Fichier maître JSON généré : {JSON_OUTPUT.relative_to(BASE_DIR)}")

    # 3. Sauvegarde du fichier tabulaire CSV
    fieldnames = [
        "id", "date", "time", "datetime", "distance_km", "duration", "duration_seconds",
        "pace_avg", "pace_seconds_per_km", "speed_kmh", "calories_kcal", "cadence_spm",
        "stride_length_cm", "heart_rate_avg_bpm", "heart_rate_max_bpm", "ground_contact_time_ms",
        "vertical_oscillation_cm", "balance_left_pct", "balance_right_pct",
        "elevation_gain_m", "source_image"
    ]
    with open(CSV_OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in sorted_runs:
            writer.writerow(r)
    print(f"📊 Fichier tabulaire CSV généré : {CSV_OUTPUT.relative_to(BASE_DIR)}")

    # 4. Génération du document de synthèse Markdown
    total_dist = sum(r["distance_km"] for r in sorted_runs)
    total_time_s = sum(r["duration_seconds"] for r in sorted_runs)
    total_cal = sum(r["calories_kcal"] for r in sorted_runs)
    avg_hr = [r["heart_rate_avg_bpm"] for r in sorted_runs if r["heart_rate_avg_bpm"]]
    avg_hr_val = round(sum(avg_hr) / len(avg_hr)) if avg_hr else 0
    longest_run = max(sorted_runs, key=lambda x: x["distance_km"]) if sorted_runs else None
    valid_paces = [r for r in sorted_runs if r["pace_seconds_per_km"] > 180 and r["distance_km"] >= 3.0]
    fastest_pace = min(valid_paces, key=lambda x: x["pace_seconds_per_km"], default=None)

    with open(SUMMARY_OUTPUT, "w", encoding="utf-8") as f:
        f.write("# Dataset Athlète : Historique Complet des Courses Classées\n\n")
        f.write(f"Ce document récapitule l'intégralité des **{len(sorted_runs)} courses à pied uniques** extraites de Huawei Santé, classées par ordre chronologique.\n\n")
        f.write("## 1. Vue d'Ensemble & Records\n\n")
        f.write(f"- **Nombre total de courses uniques** : {len(sorted_runs)} séances\n")
        f.write(f"- **Distance totale cumulée** : {total_dist:.2f} km\n")
        f.write(f"- **Durée totale cumulée** : {total_time_s // 3600}h {(total_time_s % 3600) // 60}min\n")
        f.write(f"- **Calories totales dépensées** : {total_cal:,} kcal\n")
        f.write(f"- **Fréquence cardiaque moyenne globale** : {avg_hr_val} bpm\n")
        if longest_run:
            f.write(f"- **Plus longue sortie (Record)** : **{longest_run['distance_km']} km** le {longest_run['date']} ({longest_run['duration']} à {longest_run['pace_avg']})\n")
        if fastest_pace:
            f.write(f"- **Meilleure allure moyenne (≥ 3 km)** : **{fastest_pace['pace_avg']}/km** sur {fastest_pace['distance_km']} km le {fastest_pace['date']}\n\n")

        f.write("## 2. Tableau Chronologique Complet de Vos Courses\n\n")
        f.write("| # | Date & Heure | Distance | Durée | Allure | Vitesse | Cadence | FC Moy | Contact Sol | Foulée | Calories |\n")
        f.write("| :-: | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
        for i, r in enumerate(sorted_runs, 1):
            f.write(
                f"| {i} | **{r['date']}** {r['time']} | {r['distance_km']:.2f} km | {r['duration']} | {r['pace_avg']} | "
                f"{r['speed_kmh']} km/h | {r['cadence_spm']} spm | {r['heart_rate_avg_bpm'] or '-'} bpm | "
                f"{r['ground_contact_time_ms'] or '-'} ms | {r['stride_length_cm'] or '-'} cm | {r['calories_kcal']} kcal |\n"
            )

        f.write("\n## 3. Prêt pour l'Analyse par IA\n\n")
        f.write("Fichiers exploitables directement :\n")
        f.write("- **Format JSON structuré** : `data/athlete_dataset.json`\n")
        f.write("- **Format CSV tabulaire** : `data/athlete_dataset.csv`\n")
        f.write("- **Fichiers JSON individuels** : `data/runs/*.json`\n")

    print(f"📝 Document de synthèse généré : {SUMMARY_OUTPUT.relative_to(BASE_DIR)}")

    # Dupliquer également dans TempRun pour que tout soit accessible partout
    temprun_dir = Path("/home/whoami/DevApps/TempRun/data")
    if temprun_dir.exists():
        try:
            shutil.copy(JSON_OUTPUT, temprun_dir / "athlete_dataset.json")
            shutil.copy(CSV_OUTPUT, temprun_dir / "athlete_dataset.csv")
            shutil.copy(SUMMARY_OUTPUT, temprun_dir / "summary_runs.md")
            shutil.copytree(RUNS_DIR, temprun_dir / "runs", dirs_exist_ok=True)
            print("🔄 Synchronisation effectuée avec succès vers DevApps/TempRun/data/")
        except Exception as e:
            print(f"Note: {e}")

    print("=" * 65)
    print("🎉 SUCCÈS : Vos données de course sont parfaitement classées et structurées !")
    print("=" * 65)


if __name__ == "__main__":
    main()
