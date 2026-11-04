# Third-party components

The image bundles these components unmodified, each under its own license. The complete, version-exact list
is the SBOM (`sbom.cdx.json`) delivered with every release.

| Component | Version | Use | License |
|---|---|---|---|
| Mustang (mustangproject) | 2.26.0 | Validation of PDF/A-3, labelling, schema, EN 16931, arithmetic | Apache-2.0 |
| veraPDF (inside Mustang) | 1.30.2 | PDF/A check | GPL-3.0-or-later or MPL-2.0, used under MPL-2.0 |
| Saxon-HE (inside Mustang and KoSIT) | see SBOM | XSLT processing | MPL-2.0 |
| Apache FOP and further Java libraries (inside Mustang) | see SBOM | Dependencies of Mustang | see SBOM and `third-party-notices.txt` |
| KoSIT Validator | 1.6.3 | Reference validation | Apache-2.0 |
| KoSIT validator configuration XRechnung | 2026-08-31 | Official rules | Apache-2.0 |
| KoSIT XRechnung visualization | 2026-10-13 | Invoice view | Apache-2.0 |
| pypdf | 6.21.4 | Extraction of the embedded XML | BSD-3-Clause |
| waitress | 3.0.2 | HTTP server | ZPL-2.1 |
| Eclipse Temurin JRE | 21 | Java runtime | GPL-2.0 with Classpath Exception |
| Python, Ubuntu packages | see SBOM | Base system | see SBOM |

Sources: https://github.com/ZUGFeRD/mustangproject · https://github.com/itplr-kosit/validator ·
https://github.com/itplr-kosit/validator-configuration-xrechnung · https://github.com/itplr-kosit/xrechnung-visualization
