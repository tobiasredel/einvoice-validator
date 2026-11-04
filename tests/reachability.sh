#!/bin/sh
# Nachweis: Werden die Bibliotheken mit bekannten Schwachstellen beim Prüfen und Anzeigen überhaupt geladen?
# Protokolliert alle geladenen Java-Klassen je Engine. Aufruf: reachability.sh <image> <fixtures>
set -eu
docker run --rm --network none --read-only --tmpfs /tmp:size=512m --cap-drop ALL -v "$2":/f:ro --entrypoint sh "$1" -c '
cd /tmp
OPT=/opt/einvoice; K=$OPT/kosit-config
count() { echo "$1: Klassen gesamt $(grep -c "source:" "$2"), jackson $(grep -c "com.fasterxml.jackson" "$2"), assertj $(grep -c "org.assertj" "$2")"; }
for f in en16931-cii-valid.xml xrechnung-cii-invalid.xml zugferd-extended.pdf zugferd-sample.pdf credit-note-no-payment-info.xml; do
  java -verbose:class -Xmx768m -jar $OPT/mustang.jar --action validate --source /f/$f --disable-file-logging > /tmp/c.log 2>/dev/null || true
  count "Mustang validate $f" /tmp/c.log
done
java -verbose:class -Xmx512m -jar $OPT/mustang.jar --action visualize --language de --source /f/en16931-cii-valid.xml --out /tmp/v.html --disable-file-logging > /tmp/c.log 2>/dev/null || true
count "Mustang visualize" /tmp/c.log
java -verbose:class -Xmx512m -cp $OPT/mustang.jar net.sf.saxon.Transform -s:/f/en16931-cii-valid.xml -xsl:/app/src/viewer_driver.xsl -o:/tmp/w.html base=file://$OPT/viewer/xsl to=cii-xr.xsl lang=de > /tmp/c.log 2>/dev/null || true
count "Saxon Ansicht" /tmp/c.log
S=$(python -I -c "import json;print([s[\"file\"] for s in json.load(open(\"$K/scenario-index.json\")) if s[\"name\"]==\"EN16931 (CII)\"][0])")
mkdir -p /tmp/k; java -verbose:class -Xmx512m -jar $OPT/kosit.jar -s $K/$S -r $K -o /tmp/k /f/en16931-cii-valid.xml > /tmp/c.log 2>/dev/null || true
count "KoSIT" /tmp/c.log
'
