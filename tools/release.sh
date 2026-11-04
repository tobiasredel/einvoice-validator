#!/bin/sh
# Baut das Lieferpaket in dist/<version>: Image-Archiv, Vorlagen, SBOM, Schwachstellenbericht, Lizenzen, Doku, Prüfnachweise.
# Voraussetzung: tests/test_image.py lief gegen dieselbe Version (tests/out/security-evidence.md).
set -eu
VERSION=${1:?Version fehlt}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT="$ROOT/dist/$VERSION"
IMAGE="einvoice-validator:$VERSION"
TAR="einvoice-validator-$VERSION-amd64.tar"
mkdir -p "$OUT"
cd "$ROOT"
docker build -q -f docker/Dockerfile --build-arg APP_VERSION="$VERSION" -t "$IMAGE" .
docker save "$IMAGE" -o "$OUT/$TAR"
docker run --rm -v "$OUT":/d:ro -v "$OUT":/o anchore/syft:v1.33.0 "docker-archive:/d/$TAR" -o "cyclonedx-json=/o/sbom.cdx.json" -q
docker run --rm -v "$OUT":/d:ro -v "$OUT":/o -e TRIVY_CACHE_DIR=/tmp/trivy aquasec/trivy:0.67.2 image --input "/d/$TAR" --scanners vuln --format table --output /o/trivy-report.txt --quiet
docker run --rm -v "$OUT":/d:ro -v "$OUT":/o -e TRIVY_CACHE_DIR=/tmp/trivy aquasec/trivy:0.67.2 image --input "/d/$TAR" --scanners vuln --format json --output /o/trivy-report.json --quiet
docker run --rm --network none --read-only --tmpfs /tmp -v "$ROOT/tools/collect_notices.py":/collect.py:ro --entrypoint python "$IMAGE" -I /collect.py /opt/einvoice/mustang.jar /opt/einvoice/kosit.jar > "$OUT/third-party-notices.txt"
[ -s "$OUT/third-party-notices.txt" ] || { echo "Notices leer"; exit 1; }
gzip -f -9 "$OUT/$TAR"
cp deploy/compose.yml deploy/nginx.conf deploy/k8s.yaml LICENSE NOTICE THIRD-PARTY-LICENSES.md "$OUT/"
cp -r docs "$OUT/docs"
cp README.md README.de.md "$OUT/"
[ -d tests/out ] && cp -r tests/out "$OUT/nachweise"
( cd "$OUT" && find . -type f ! -name SHA256SUMS | sort | xargs sha256sum > SHA256SUMS )
du -sh "$OUT"
