"""Bereitet die KoSIT-HTML-Ansicht so auf, dass sie ohne JavaScript im abgeschotteten iframe läuft.

Skripte, Event-Attribute und Link-Ziele werden entfernt, die Tabs laufen nur über CSS, Anlagen werden zu
Download-Links mit neutralem Dateityp. Das iframe in der Oberfläche hat zusätzlich kein allow-scripts.
"""
import re

CSP = ("default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
       "base-uri 'none'; form-action 'none'")

TABS = ("uebersicht", "details", "zusaetze", "anlagen", "laufzettel")

# Tabs nur mit CSS. Links wie href="#details" scheiden aus: In einem srcdoc-iframe lösen sie gegen die URL der Elternseite auf.
TABS_CSS = (".ev-tab{position:absolute;opacity:0;width:0;height:0}"
            + "".join(f"#{t}{{display:none!important}}body:has(#t-{t}:checked) #{t}{{display:block!important}}" for t in TABS)
            + "label.tab{display:inline-block;cursor:pointer;font-family:Arial,Helvetica,sans-serif;font-size:18px;line-height:50px;height:50px;padding:0 12px;box-sizing:border-box}"
            + "@media(max-width:600px){label.tab{font-size:14px;line-height:36px;height:36px;padding:0 7px}}"
            + "".join(f"body:has(#t-{t}:checked) label[for=t-{t}]{{font-weight:700;border-bottom:3px solid currentColor}}" for t in TABS)
            + ".ev-tab:focus-visible{outline:none}")
RADIOS = "".join(f'<input class="ev-tab" type="radio" name="ev-tabs" id="t-{t}"{" checked" if t == TABS[0] else ""} aria-label="{t}">' for t in TABS)

_BUTTON = re.compile(r'<button\b[^>]*?\bid="menue(\w+)"[^>]*>(.*?)</button>', re.S)
_ATTACH = re.compile(
    r'<a href="#download-[^"]*"[^>]*>(.*?)</a>\s*<div id="download-[^"]*"(?=[^>]*data-download-filename="([^"]*)")[^>]*>([^<]*)</div>',
    re.S | re.I)
_EVENT = re.compile(r"""\s+on[a-z]+\s*=\s*(?:"[^"]*"|'[^']*')""", re.I)
_NOSCRIPT = re.compile(r"<noscript\b.*?</noscript\s*>", re.S | re.I)
_SCRIPT = re.compile(r"<script\b.*?</script\s*>", re.S | re.I)
_LINK = re.compile(r"""(<a\b[^>]*?)\s+href\s*=\s*(?:"(?!data:application/octet-stream)[^"]*"|'[^']*')""", re.I)


def _attachment(m):
    label, name, payload = m.group(1), m.group(2), re.sub(r"\s+", "", m.group(3))
    if not re.fullmatch(r"[A-Za-z0-9+/=]*", payload):
        return label
    safe = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", name)[:120] or "attachment"
    return f'<a download="{safe}" href="data:application/octet-stream;base64,{payload}">{label}</a>'


def sanitize(html):
    html = _SCRIPT.sub("", html)
    html = _NOSCRIPT.sub("", html)   # Der Hinweis „ohne JavaScript eingeschränkt“ trifft hier nicht zu
    html = _ATTACH.sub(_attachment, html)
    html = _BUTTON.sub(lambda m: f'<label class="tab" for="t-{m.group(1).lower()}">{m.group(2)}</label>', html)
    html = _EVENT.sub("", html)
    html = _LINK.sub(r"\1", html)   # keine Navigation aus der Ansicht heraus; nur Anlagen-Downloads bleiben Links
    html = re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + RADIOS, html, count=1, flags=re.I)
    head = f'<meta http-equiv="Content-Security-Policy" content="{CSP}"><style>{TABS_CSS}</style>'
    if re.search(r"<head[^>]*>", html, re.I):
        return re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + head, html, count=1, flags=re.I)
    return head + html
