#!/usr/bin/env python3
"""Zerlegt die offizielle scenarios.xml in eine Konfiguration je Szenario.

Der KoSIT-Validator kompiliert beim Start die Regeln aller Szenarien (rund 8 s). Mit nur dem passenden Szenario
sind es rund 2,5 s. Regeln und Trefferbedingung bleiben unverändert: kopiert wird der Originalblock. Die Trefferbedingung
landet zusätzlich in scenario-index.json, damit die App das richtige Szenario wählen kann.
"""
import json
import os
import re
import sys

CII = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
ROOTS = (("/invoice:Invoice", "Invoice", "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"),
         ("/creditnote:CreditNote", "CreditNote", "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"),
         ("/rsm:CrossIndustryInvoice", "CrossIndustryInvoice", CII))


def main(cfg):
    with open(os.path.join(cfg, "scenarios.xml"), encoding="utf-8") as f:
        src = f.read()
    blocks = list(re.finditer(r"[ \t]*<scenario>.*?</scenario>\s*", src, re.S))
    if not blocks:
        raise SystemExit("keine Szenarien gefunden")
    index = []
    for i, b in enumerate(blocks):
        block = b.group(0)
        name = re.search(r"<name>(.*?)</name>", block).group(1)
        match = re.search(r"<match>(.*?)</match>", block, re.S).group(1)
        root = next((r for r in ROOTS if r[0] in match), None)
        ident = re.search(r"'(urn:[^']+)'", match)
        if root is None or ident is None:
            raise SystemExit(f"Trefferbedingung nicht erkannt: {name}")
        file = f"scenario-{i:02d}.xml"
        with open(os.path.join(cfg, file), "w", encoding="utf-8") as f:
            f.write(src[:blocks[0].start()] + block + src[blocks[-1].end():])
        index.append({"name": name, "root": root[1], "ns": root[2], "id": ident.group(1), "file": file})
    with open(os.path.join(cfg, "scenario-index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, indent=1)
    print(f"{len(index)} Szenarien")


if __name__ == "__main__":
    main(sys.argv[1])
