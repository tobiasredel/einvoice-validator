# E-Invoice Validator & Viewer

[English](README.md) · Deutsch

Prüft und zeigt E-Rechnungen (ZUGFeRD, Factur-X, XRechnung, UBL, CII), einzeln oder bis zu 200 auf einmal. Läuft selbst gehostet als ein Docker-Image, ohne Datenbank, ohne Volume und ohne Internetzugang. Rechnungen werden nicht gespeichert.

- **Zwei Prüf-Engines:** Mustang (PDF/A-3, PDF-Kennzeichnung, Schema, EN 16931, Rechnen) und der offizielle KoSIT-Validator mit der XRechnung-Konfiguration (auch für reine EN-16931-Rechnungen).
- **Bericht in Klartext:** erklärt je Befund, was falsch ist und wie es behoben wird, auf Deutsch und Englisch.
- **Rechnungsansicht:** offizielle KoSIT-Visualisierung, Felder mit Befunden sind farbig markiert, das PDF lässt sich daneben anzeigen.
- **Mehrere Rechnungen:** Gesamtübersicht, Problemfälle oben, ZIP mit Excel-Bericht.

## Schnellstart

```sh
docker run -d --name einvoice -p 127.0.0.1:8000:8000 \
  --read-only --tmpfs /tmp:size=1g,mode=1777,noexec,nosuid,nodev \
  --cap-drop ALL --security-opt no-new-privileges \
  ghcr.io/tobiasredel/einvoice-validator:latest
# erreichbar unter http://127.0.0.1:8000
```

Für den Betrieb hinter einem Proxy gibt es Vorlagen in [deploy/](deploy/) (`compose.yml`, `nginx.conf`, `k8s.yaml`).

## Dokumentation

| Für | Dokument |
|---|---|
| Betrieb und IT | [docs/BETRIEB.md](docs/BETRIEB.md) |
| Datenschutz und IT-Sicherheit | [docs/DATENSCHUTZ-SICHERHEIT.md](docs/DATENSCHUTZ-SICHERHEIT.md) |
| IT-Sicherheit: bekannte Schwachstellen | [docs/SCHWACHSTELLEN.md](docs/SCHWACHSTELLEN.md) |
| Anwender | [docs/NUTZUNG.md](docs/NUTZUNG.md) |

## Entwicklung

```sh
make build VERSION=dev      # Image bauen
make test VERSION=dev       # Übersetzungen, Datenschutz, Härtung, Angriffe
make release VERSION=1.0.0  # Lieferpaket in dist/
```

`tests/ui.mjs` (Playwright) prüft die Oberfläche, `tests/compare_scenarios.sh` die Gleichwertigkeit der KoSIT-Konfiguration.

## Lizenz

Apache-2.0, siehe [LICENSE](LICENSE). Die mitgelieferten Komponenten behalten ihre eigenen Lizenzen: [THIRD-PARTY-LICENSES.md](THIRD-PARTY-LICENSES.md).
