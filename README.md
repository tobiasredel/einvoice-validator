# E-Invoice Validator & Viewer

English · [Deutsch](README.de.md)

Validates and displays e-invoices (ZUGFeRD, Factur-X, XRechnung, UBL, CII), one at a time or up to 200 at once. It runs self-hosted as a single Docker image, with no database, no volume and no internet access. **Invoices are not stored.**

- **Two validation engines:** [Mustang](https://github.com/ZUGFeRD/mustangproject) (PDF/A-3, PDF labelling, schema, EN 16931, arithmetic) and the official [KoSIT validator](https://github.com/itplr-kosit/validator) with the XRechnung configuration (also used for plain EN 16931 invoices).
- **Plain-language report:** explains for each finding what is wrong and how to fix it, in German and English.
- **Invoice view:** the official KoSIT visualization, with fields that have findings highlighted. The PDF can be shown alongside.
- **Several invoices at once:** overview with problem cases first, plus a ZIP with an Excel report.

## Quick start

```sh
docker run -d --name einvoice -p 127.0.0.1:8000:8000 \
  --read-only --tmpfs /tmp:size=1g,mode=1777,noexec,nosuid,nodev \
  --cap-drop ALL --security-opt no-new-privileges \
  ghcr.io/tobiasredel/einvoice-validator:latest
# open http://127.0.0.1:8000
```

The image has no user management and no TLS. For a shared deployment put it behind a reverse proxy that provides both. Templates for Docker Compose with nginx and for Kubernetes are in [deploy/](deploy/).

Images are published to `ghcr.io/tobiasredel/einvoice-validator`: `latest` and version tags (`1.0.0`, `1.0`, `1`) for releases, `edge` for the current `main`.

## Privacy by design

- Files exist only in a RAM-backed temp folder during the check and are deleted afterwards, also on errors and timeouts.
- Read-only root file system, no volume, non-root user, no capabilities, no outbound network needed.
- Logs contain only path, status and duration. File names never leave the browser.
- `DOCTYPE` in XML is rejected before any parser sees it (XXE, entity bombs). The invoice view runs without scripts in a sandboxed frame.

Details and limits: [docs/DATENSCHUTZ-SICHERHEIT.md](docs/DATENSCHUTZ-SICHERHEIT.md) (German). Known vulnerabilities in bundled libraries and their assessment: [docs/SCHWACHSTELLEN.md](docs/SCHWACHSTELLEN.md) (German).

## Documentation (German)

| Topic | Document |
|---|---|
| Operation, proxy requirements, sizing, updates | [docs/BETRIEB.md](docs/BETRIEB.md) |
| Privacy and security | [docs/DATENSCHUTZ-SICHERHEIT.md](docs/DATENSCHUTZ-SICHERHEIT.md) |
| Known vulnerabilities | [docs/SCHWACHSTELLEN.md](docs/SCHWACHSTELLEN.md) |
| Usage (German and English) | [docs/NUTZUNG.md](docs/NUTZUNG.md) |

## Development

```sh
make build VERSION=dev      # build the image
make test VERSION=dev       # translations, privacy, hardening and attack tests
make release VERSION=1.0.0  # delivery package in dist/
```

`tests/ui.mjs` (Playwright) checks the user interface, `tests/compare_scenarios.sh` the equivalence of the per-scenario KoSIT configuration.

## What this is not

A technical check against the standards, not a tax or legal assessment. It does not compare the PDF with the embedded data automatically. One check goes beyond the official rule sets: BR-CO-25 (a payable amount needs a due date or payment terms) is verified by this tool itself, see the privacy and security document.

## License

Apache-2.0, see [LICENSE](LICENSE). Bundled components keep their own licenses: [THIRD-PARTY-LICENSES.md](THIRD-PARTY-LICENSES.md).
