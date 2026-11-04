#!/usr/bin/env python3
"""Vollständigkeit der Übersetzungen (ohne Docker). Aufruf: python3 -I tests/test_unit.py"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from extract_messages import extract  # noqa: E402

DATA = os.path.join(ROOT, "src", "data")
load = lambda n: json.load(open(os.path.join(DATA, n), encoding="utf-8"))
ph = lambda s: sorted(re.findall(r"\{\w+\}", s))
fails = []

en = load("messages_en.json")
for s in extract(os.path.join(ROOT, "src")):
    if s not in en:
        fails.append(f"Backend-Text ohne EN: {s[:70]}")
    elif ph(s) != ph(en[s]):
        fails.append(f"Platzhalter weichen ab: {s[:70]}")

de_rules, en_rules = load("rules_de.json"), load("rules_en.json")
if set(de_rules) != set(en_rules):
    fails.append(f"Regel-IDs ungleich: {sorted(set(de_rules) ^ set(en_rules))[:8]}")
for k in de_rules:
    if set(de_rules[k]) != set(en_rules.get(k, {})):
        fails.append(f"Regel-Felder ungleich: {k}")
    if re.search("[äöüßÄÖÜ]", " ".join(en_rules.get(k, {}).values())):
        fails.append(f"Umlaut in EN-Regel: {k}")
if set(load("names_de.json")) != set(load("names_en.json")):
    fails.append("Feldnamen ungleich")

js = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
i18n = open(os.path.join(ROOT, "web", "i18n.js"), encoding="utf-8").read()
for key in set(re.findall(r'\bt\("((?:[^"\\]|\\.)*)"', js) + re.findall(r'data-i18n="([^"]+)"', html)):
    if f'"{key}":' not in i18n:
        fails.append(f"UI-Text ohne EN: {key[:70]}")
if re.search(r"\son[a-z]+=", html) or "<script>" in html or re.search(r'on(click|change)="', js):
    fails.append("Inline-Handler oder Inline-Skript gefunden (verletzt die CSP)")

print(f"{len(de_rules)} Regeln, {len(en)} Backend-Texte geprüft")
for f in fails:
    print("FEHLER", f)
sys.exit(1 if fails else 0)
