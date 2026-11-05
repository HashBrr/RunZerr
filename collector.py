#!/usr/bin/env python3
"""
RunZerr - Data Collector
Synchronise proprement les fiches d'activités (sporthealth-*.jpg) et les traces (.tcx / .kml)
depuis le smartphone Android connecté en ADB.
"""

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_IMAGES_DIR = DATA_DIR / "raw_images"
TCX_DIR = DATA_DIR / "tcx"
MANIFEST_PATH = DATA_DIR / "manifest.json"


def run_adb(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["adb"] + cmd, capture_output=True, text=True, check=False)


def get_connected_device() -> str | None:
    res = run_adb(["devices"])
    lines = res.stdout.strip().splitlines()
    for line in lines[1:]:
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1] == "device":
            return parts[0]
    return None


def calculate_md5(file_path: Path) -> str:
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"updated_at": None, "device_id": None, "images": [], "tcx": []}


def save_manifest(manifest: dict):
    manifest["updated_at"] = datetime.now().isoformat()
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def collect_images(device_id: str, manifest: dict) -> int:
    RAW_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    existing_hashes = {item["md5"]: item for item in manifest.get("images", [])}
    
    # 1. Scanner les fichiers locaux existants dans data/raw_images/
    local_count = 0
    for local_file in RAW_IMAGES_DIR.glob("*.jpg"):
        f_md5 = calculate_md5(local_file)
        if f_md5 not in existing_hashes:
            item = {
                "filename": local_file.name,
                "local_path": str(local_file.relative_to(BASE_DIR)),
                "remote_path": "local",
                "size_bytes": local_file.stat().st_size,
                "md5": f_md5,
                "collected_at": datetime.now().isoformat(),
            }
            manifest["images"].append(item)
            existing_hashes[f_md5] = item
            local_count += 1

    # 2. Scanner les fichiers distants sur le téléphone (Pictures et Corbeille)
    cmd = "find /sdcard/Pictures/ /sdcard/Android/.Trash/ -iname 'sporthealth-*.jpg' 2>/dev/null"
    res = run_adb(["shell", cmd])
    remote_files = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]

    new_count = 0
    print(f"🔍 Fiches d'activité trouvées sur l'appareil : {len(remote_files)}")

    for remote_path in remote_files:
        filename = os.path.basename(remote_path)
        local_path = RAW_IMAGES_DIR / filename

        # Télécharger si pas présent
        if not local_path.exists():
            print(f"  📥 Téléchargement de {filename}...")
            pull_res = run_adb(["pull", remote_path, str(local_path)])
            if pull_res.returncode != 0:
                print(f"  ⚠️ Erreur lors du pull de {filename}")
                continue
            new_count += 1

        file_md5 = calculate_md5(local_path)
        file_size = local_path.stat().st_size

        if file_md5 not in existing_hashes:
            item = {
                "filename": filename,
                "local_path": str(local_path.relative_to(BASE_DIR)),
                "remote_path": remote_path,
                "size_bytes": file_size,
                "md5": file_md5,
                "collected_at": datetime.now().isoformat(),
            }
            manifest["images"].append(item)
            existing_hashes[file_md5] = item

    return new_count + local_count


def collect_tcx(device_id: str, manifest: dict) -> int:
    TCX_DIR.mkdir(parents=True, exist_ok=True)
    existing_hashes = {item["md5"]: item for item in manifest.get("tcx", [])}

    # Scanner les fichiers locaux
    local_count = 0
    for local_file in TCX_DIR.glob("*.tcx"):
        f_md5 = calculate_md5(local_file)
        if f_md5 not in existing_hashes:
            item = {
                "filename": local_file.name,
                "local_path": str(local_file.relative_to(BASE_DIR)),
                "remote_path": "local",
                "size_bytes": local_file.stat().st_size,
                "md5": f_md5,
                "collected_at": datetime.now().isoformat(),
            }
            manifest["tcx"].append(item)
            existing_hashes[f_md5] = item
            local_count += 1

    res = run_adb(["shell", "find /sdcard/Android/data/com.huawei.health/files/Tracks/Export/ -iname '*.tcx' 2>/dev/null"])
    remote_files = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]

    new_count = 0
    print(f"🔍 Fichiers TCX trouvés sur l'appareil : {len(remote_files)}")

    for remote_path in remote_files:
        filename = os.path.basename(remote_path)
        local_path = TCX_DIR / filename

        if not local_path.exists():
            print(f"  📥 Téléchargement de {filename}...")
            pull_res = run_adb(["pull", remote_path, str(local_path)])
            if pull_res.returncode != 0:
                print(f"  ⚠️ Erreur lors du pull de {filename}")
                continue
            new_count += 1

        file_md5 = calculate_md5(local_path)
        file_size = local_path.stat().st_size

        if file_md5 not in existing_hashes:
            item = {
                "filename": filename,
                "local_path": str(local_path.relative_to(BASE_DIR)),
                "remote_path": remote_path,
                "size_bytes": file_size,
                "md5": file_md5,
                "collected_at": datetime.now().isoformat(),
            }
            manifest["tcx"].append(item)
            existing_hashes[file_md5] = item

    return new_count + local_count


def sync_all():
    print("=" * 60)
    print("🏃 RunZerr - Synchronisation des données Huawei Santé (ADB)")
    print("=" * 60)

    device_id = get_connected_device()
    if not device_id:
        print("❌ Aucun smartphone connecté et autorisé via ADB !")
        print("   Vérifiez le câble USB et l'autorisation de débogage sur l'écran.")
        sys.exit(1)

    print(f"📱 Smartphone connecté : {device_id}")

    manifest = load_manifest()
    manifest["device_id"] = device_id

    new_images = collect_images(device_id, manifest)
    new_tcx = collect_tcx(device_id, manifest)

    save_manifest(manifest)

    print("-" * 60)
    print("✅ Synchronisation terminée avec succès !")
    print(f"   • Fiches d'activité enregistrées : {len(manifest['images'])}")
    for img in manifest["images"]:
        print(f"     📁 {img['filename']} ({img['size_bytes'] / 1024:.1f} Ko)")
    print(f"   • Fichiers TCX enregistrés : {len(manifest['tcx'])}")
    for tcx in manifest["tcx"]:
        print(f"     📍 {tcx['filename']} ({tcx['size_bytes'] / 1024:.1f} Ko)")
    print(f"   • Manifeste à jour : {MANIFEST_PATH.relative_to(BASE_DIR)}")
    print("=" * 60)


if __name__ == "__main__":
    sync_all()
