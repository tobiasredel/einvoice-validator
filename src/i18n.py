"""Zweisprachigkeit des Backends (DE/EN).

Quelltexte sind deutsch; `_("Text {x}", x=1)` liefert in der aktiven Sprache den Eintrag aus
data/messages_en.json. Die Sprache gilt je Thread, weil ein Bericht nacheinander in beiden
Sprachen gebaut wird. tests/test_unit.py prüft, dass jeder `_()`-Text übersetzt ist.
"""
import json
import os
import threading

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
LANGS = ("de", "en")
_state = threading.local()


def _load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


MESSAGES_EN = _load("messages_en.json")
RULES = {lang: _load(f"rules_{lang}.json") for lang in LANGS}
NAMES = {lang: _load(f"names_{lang}.json") for lang in LANGS}


def set_lang(lang):
    _state.lang = lang if lang in LANGS else "de"


def lang():
    return getattr(_state, "lang", "de")


def _(text, **kw):
    if lang() == "en":
        text = MESSAGES_EN.get(text, text)
    return text.format(**kw) if kw else text


def rule(rule_id):
    return RULES[lang()].get(rule_id)


def names():
    return NAMES[lang()]
