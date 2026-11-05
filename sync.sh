#!/usr/bin/env bash
# RunZerr - Rapatriement rapide des données depuis le smartphone

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

echo "🏃 Lancement de la collecte RunZerr..."
python3 "$DIR/collector.py"
