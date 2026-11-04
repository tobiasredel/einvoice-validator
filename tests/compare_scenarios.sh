#!/bin/sh
# Nachweis: Die je Szenario gefilterte KoSIT-Konfiguration urteilt wie die offizielle Gesamtkonfiguration.
# Läuft im Image ohne Netz. Aufruf: compare_scenarios.sh <image> <xml-ordner> <ergebnisdatei>
set -eu
docker run --rm --network none --read-only --tmpfs /tmp:size=1g,mode=1777 --cap-drop ALL \
  -v "$2":/in:ro -v "$(dirname "$(readlink -f "$0")")/compare_scenarios.py":/compare.py:ro --entrypoint python "$1" -I /compare.py /in > "$3"
tail -3 "$3"
