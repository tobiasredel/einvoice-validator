# Betrieb

## Lieferumfang

| Datei | Inhalt |
|---|---|
| `einvoice-validator-<version>-amd64.tar.gz` | Image-Archiv für `docker load` |
| `compose.yml`, `nginx.conf` | Vorlage für Docker mit internem Netz |
| `k8s.yaml` | Vorlage für Kubernetes mit NetworkPolicy (nicht auf einem Cluster getestet, bitte im eigenen Umfeld prüfen) |
| `sbom.cdx.json`, `trivy-report.txt` | Komponentenliste und Schwachstellenbericht, Bewertung in `docs/SCHWACHSTELLEN.md` |
| `third-party-notices.txt` | Lizenz- und NOTICE-Texte der mitgelieferten Bibliotheken |
| `nachweise/` | Testergebnisse zu diesem Stand |
| `SHA256SUMS` | Prüfsummen aller Dateien |

## Installation

```sh
sha256sum -c SHA256SUMS
gunzip -c einvoice-validator-<version>-amd64.tar.gz | docker load
docker compose -f compose.yml up -d
curl http://127.0.0.1:8080/healthz
```

Statt des Archivs lässt sich das Image auch aus GHCR ziehen (`docker pull ghcr.io/tobiasredel/einvoice-validator:<version>`); dann in `compose.yml` nichts ändern. Für das geladene Archiv `EV_IMAGE=einvoice-validator:<version>` setzen.

Das Image braucht zur Laufzeit keinen Internetzugang. Für eine Registry genügt `docker tag` und `docker push`.

## Anforderungen an den Proxy

Das Tool hat **keine Benutzerverwaltung und kein TLS**. Beides muss der vorgelagerte Proxy leisten. Ohne Anmeldung am Proxy kann jeder, der die Adresse erreicht, das Tool nutzen. Ergebnisse anderer sieht dabei niemand, weil nichts gespeichert wird.

| Einstellung | Wert | Grund |
|---|---|---|
| TLS | erforderlich | Rechnungen enthalten personenbezogene Daten |
| Anmeldung (SSO) | erforderlich | das Tool selbst prüft keine Identität |
| Request-Body-Logging | aus | sonst landen Rechnungen im Log |
| Response-Body-Logging, Caching | aus | die Antworten enthalten Rechnungsdaten |
| Request-Buffering auf Platte | aus | sonst liegen Rechnungen zeitweise auf der Proxy-Platte |
| Maximale Upload-Größe | mindestens 26 MB | Standardlimit des Tools: 25 MB |
| Lese-Timeout | mindestens 300 s | Warteschlange bei voller Auslastung |

`nginx.conf` zeigt das am Beispiel von nginx.

## Konfiguration

| Variable | Standard | Bedeutung |
|---|---|---|
| `PARALLEL` | `2` | gleichzeitige Prüfungen |
| `MAX_QUEUE` | `PARALLEL × 4` | wartende Anfragen, darüber antwortet der Dienst mit 503 und `Retry-After` |
| `MAX_UPLOAD_MB` | `25` | maximale Dateigröße |
| `MAX_BATCH` | `200` | maximale Dateien pro Lauf im Browser |
| `ENGINE_TIMEOUT` | `120` | Zeitlimit je Engine in Sekunden |
| `PORT` | `8000` | Port im Container |

## Sizing

Gemessen mit 200 gemischten Beispielrechnungen (XML und PDF), `PARALLEL=4`, auf 6 CPU-Kernen. Die Spanne stammt aus zwei Läufen, der langsamere lief bei Nebenlast auf dem Testrechner:

| Messwert | Ergebnis |
|---|---|
| Gesamtdauer | 258 bis 526 s, also 1,3 bis 2,6 s pro Datei im Mittel |
| Einzelne Prüfung | Median 4,4 bis 8,9 s, maximal 18 s |
| Spitzenspeicher des Containers | 0,9 bis 1,3 GB |
| Abbrüche | keine |

Empfehlung: **4 CPU-Kerne und 6 GB RAM für `PARALLEL=4`**. Das Speicherlimit ist höher als der Messwert, weil die Java-Prozesse bei großen PDFs bis zu 1,3 GB je Prüfung belegen dürfen. Jede Prüfung startet bis zu zwei Java-Prozesse, Dauer und CPU-Last hängen deshalb vor allem an den Kernen. Das Tool läuft zustandslos und lässt sich horizontal skalieren.

## Logs

Protokolliert werden nur Pfad, Status und Dauer, zum Beispiel `[req] /api/validate 200 8123ms`. Bei Fehlern kommt der Exception-Typ dazu, nie sein Text.

## Updates

Prüfregeln ändern sich: KoSIT veröffentlicht neue Konfigurationen meist zweimal im Jahr, Mustang öfter. **Der Stand im Image bleibt, bis ein neues Image gebaut wird.** Neuer Stand:

1. In `docker/Dockerfile` Version und SHA-256 der Komponente ändern und die Versions-Variablen anpassen.
2. `make test` und `tests/ui.mjs` ausführen.
3. Regel-IDs abgleichen: Neue IDs ohne Klartext erscheinen weiter korrekt, aber mit der englischen Originalmeldung. Texte in `src/data/rules_*.json` ergänzen.
4. `make release VERSION=<neu>`.

Die Versionen im Betrieb zeigt `GET /api/config` und die Startseite.
