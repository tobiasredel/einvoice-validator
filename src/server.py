"""HTTP-Schicht (WSGI über waitress). Hält keine Rechnungsdaten: nichts wird gespeichert, geloggt oder zwischengespeichert.

Der Dateiname wird nicht übertragen, er bleibt im Browser. Protokolliert werden nur Pfad, Status und Dauer.
"""
import base64
import json
import mimetypes
import os
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import engine
import i18n
import report
import viewer
from i18n import _

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web")
MAX_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "25")) * 1024 * 1024
MAX_BATCH = int(os.environ.get("MAX_BATCH", "200"))
PARALLEL = max(1, int(os.environ.get("PARALLEL", "2")))
MAX_WAITING = int(os.environ.get("MAX_QUEUE", str(PARALLEL * 4)))
RETRY_AFTER = "5"
VERSIONS = {"mustang": os.environ.get("MUSTANG_VERSION", ""), "kosit": os.environ.get("KOSIT_VERSION", ""),
            "kosit_config": os.environ.get("KOSIT_CONFIG_VERSION", ""), "viewer": os.environ.get("VIEWER_VERSION", "")}
APP_VERSION = os.environ.get("APP_VERSION", "dev")

_slots = threading.BoundedSemaphore(PARALLEL)
_waiting = 0
_waiting_lock = threading.Lock()

CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
       "frame-src 'self' blob:; object-src blob:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
SECURITY_HEADERS = [
    ("Content-Security-Policy", CSP), ("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"), ("Cross-Origin-Opener-Policy", "same-origin"),
    ("Cross-Origin-Resource-Policy", "same-origin"), ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
]


class Busy(Exception):
    pass


class Slot:
    """Prüfplatz; ist die Warteschlange voll, kommt sofort 503 mit Retry-After statt unbegrenztem Warten."""

    def __enter__(self):
        global _waiting
        with _waiting_lock:
            if _waiting >= MAX_WAITING:
                raise Busy()
            _waiting += 1
        _slots.acquire()
        with _waiting_lock:
            _waiting -= 1

    def __exit__(self, *exc):
        _slots.release()


def is_pdf(data):
    return b"%PDF" in data[:1024]


def both_languages(build):
    out = {}
    for lang in i18n.LANGS:
        i18n.set_lang(lang)
        out[lang] = build()
    return out


def rejected_report(reason):
    def build():
        if reason == "doctype":
            return report.simple_report(_("Aus Sicherheitsgründen nicht geprüft"),
                                        _("Die Datei enthält eine DOCTYPE-Deklaration. E-Rechnungen brauchen keine, sie ist aber ein bekanntes Einfallstor für Angriffe auf XML-Parser. Die Datei wurde deshalb nicht verarbeitet."))
        return report.simple_report(_("Aus Sicherheitsgründen nicht geprüft"),
                                    _("Die Datei verwendet eine Zeichenkodierung, die für E-Rechnungen nicht vorgesehen ist. Erlaubt sind UTF-8, UTF-16 und ISO-8859-1."))
    return {"reports": both_languages(build)}


def validate(data):
    pdf = is_pdf(data)
    if not pdf and b"<" not in data[:200].replace(b"\x00", b""):
        return {"reports": both_languages(lambda: report.simple_report(
            _("Keine PDF- oder XML-Datei"), _("Bitte eine Rechnung als PDF (ZUGFeRD/Factur-X) oder als XML-Datei (XRechnung, CII, UBL) hochladen.")))}
    with engine.Job() as job:
        path = job.path("invoice.pdf" if pdf else "invoice.xml")
        with open(path, "wb") as f:
            f.write(data)
        t0 = time.time()
        xml_name, xml_bytes = engine.extract_xml(job, path) if pdf else (None, data)
        try:
            if xml_bytes:
                engine.preflight_xml(xml_bytes)
        except engine.Rejected as e:
            return rejected_report(e.reason)
        xml_path = path
        if pdf and xml_bytes:
            xml_path = job.path("embedded.xml")
        try:
            root = ET.fromstring(xml_bytes) if xml_bytes else None
        except ET.ParseError:
            root = None
        scenario = engine.scenario_for(root)
        with ThreadPoolExecutor(max_workers=2) as pool:
            mustang = pool.submit(engine.run_mustang, job, path)
            kosit = pool.submit(engine.run_kosit, job, xml_path, scenario) if scenario else None
            mustang_report = mustang.result()
            kosit_result = None
            if kosit is not None:
                try:
                    kosit_result = kosit.result()
                except Exception as e:  # noqa: BLE001  Mustang-Ergebnis bleibt gültig, der Schritt zeigt den Ausfall
                    print(f"[engine] kosit {type(e).__name__}", flush=True)
                    kosit_result = report.KOSIT_TECHNICAL
        duration = time.time() - t0
        out = {"reports": both_languages(lambda: report.build_report(mustang_report, xml_bytes, pdf, duration, kosit_result))}
        out["versions"] = VERSIONS
        if xml_bytes:
            out["xml"] = {"embedded": xml_name or "", "size": len(xml_bytes), "b64": base64.b64encode(xml_bytes).decode("ascii")}
        return out


def visualize(data, lang):
    pdf = is_pdf(data)
    with engine.Job() as job:
        path = job.path("invoice.pdf" if pdf else "invoice.xml")
        with open(path, "wb") as f:
            f.write(data)
        xml_bytes = engine.extract_xml(job, path)[1] if pdf else data
        if not xml_bytes:
            return None
        engine.preflight_xml(xml_bytes)
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError:
            return None
        tag = root.tag.rsplit("}", 1)[-1]
        if tag not in engine.VIEWER_INPUT:
            return None
        xml_path = job.path("embedded.xml") if pdf else path
        return viewer.sanitize(engine.run_viewer(job, xml_path, tag, lang))


def respond(start_response, status, body, ctype, extra=(), cache="no-store"):
    start_response(status, [("Content-Type", ctype), ("Content-Length", str(len(body))), ("Cache-Control", cache),
                            *SECURITY_HEADERS, *extra])
    return [body]


def as_json(start_response, status, obj, extra=()):
    return respond(start_response, status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", extra)


def error(start_response, status, de, en, extra=()):
    return as_json(start_response, status, {"error": {"de": de, "en": en}}, extra)


def read_body(environ):
    length = int(environ.get("CONTENT_LENGTH") or 0)
    return environ["wsgi.input"].read(length) if 0 < length <= MAX_BYTES else length


STATIC = {"/": "index.html", "/app.js": "app.js", "/app.css": "app.css", "/i18n.js": "i18n.js", "/icon.png": "icon.png"}


def app(environ, start_response):
    method, path = environ["REQUEST_METHOD"], environ.get("PATH_INFO", "/")
    t0 = time.time()
    status = ["000"]

    def sr(s, h):
        status[0] = s[:3]
        return start_response(s, h)

    try:
        return route(method, path, environ, sr)
    except Exception as e:  # noqa: BLE001  Exception-Texte können Rechnungsdaten enthalten, darum nur der Typ
        print(f"[error] {path} {type(e).__name__}", flush=True)
        return error(sr, "500 Internal Server Error", "Die Datei konnte nicht geprüft werden.", "The file could not be checked.")
    finally:
        if path.startswith("/api/") and path != "/api/config":
            print(f"[req] {path} {status[0]} {int((time.time() - t0) * 1000)}ms", flush=True)


def route(method, path, environ, sr):
    if method == "GET":
        if path == "/healthz":
            return respond(sr, "200 OK", b"ok", "text/plain")
        if path == "/api/config":
            return as_json(sr, "200 OK", {"languages": list(i18n.LANGS), "maxBytes": MAX_BYTES, "maxBatch": MAX_BATCH,
                                          "parallel": PARALLEL, "versions": VERSIONS, "version": APP_VERSION})
        name = STATIC.get(path)
        if name:
            with open(os.path.join(WEB, name), "rb") as f:
                body = f.read()
            ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            return respond(sr, "200 OK", body, ctype, cache="no-cache")
        return respond(sr, "404 Not Found", b"not found", "text/plain")
    if method != "POST" or path not in ("/api/validate", "/api/visualize"):
        return respond(sr, "404 Not Found", b"not found", "text/plain")

    data = read_body(environ)
    if isinstance(data, int):
        if data <= 0:
            return error(sr, "400 Bad Request", "Leere Datei.", "Empty file.")
        return error(sr, "413 Payload Too Large", f"Die Datei ist größer als {MAX_BYTES // 1048576} MB.", f"The file is larger than {MAX_BYTES // 1048576} MB.")
    busy = [("Retry-After", RETRY_AFTER)]
    try:
        with Slot():
            if path == "/api/validate":
                return as_json(sr, "200 OK", validate(data))
            lang = environ.get("QUERY_STRING", "")[5:] if environ.get("QUERY_STRING", "").startswith("lang=") else "de"
            html = visualize(data, lang if lang in i18n.LANGS else "de")
            if html is None:
                return error(sr, "422 Unprocessable Entity", "Für diese Datei gibt es keine Darstellung (keine Rechnungsdaten oder ZUGFeRD 1.0).",
                             "This file cannot be displayed (no invoice data, or ZUGFeRD 1.0).")
            return respond(sr, "200 OK", html.encode("utf-8"), "text/html; charset=utf-8")
    except Busy:
        return error(sr, "503 Service Unavailable", "Der Dienst ist gerade ausgelastet.", "The service is busy right now.", busy)
    except engine.Rejected:
        return error(sr, "422 Unprocessable Entity", "Die Datei wurde aus Sicherheitsgründen nicht verarbeitet.", "The file was not processed for security reasons.")
    except subprocess.TimeoutExpired:
        return error(sr, "504 Gateway Timeout", "Die Prüfung hat zu lange gedauert. Bitte erneut versuchen.", "The check took too long. Please try again.")


def main():
    from waitress import serve
    engine.sweep()
    port = int(os.environ.get("PORT", "8000"))
    print(f"einvoice-validator {APP_VERSION} on :{port} parallel={PARALLEL}", flush=True)
    serve(app, host="0.0.0.0", port=port, threads=PARALLEL + MAX_WAITING + 2, max_request_body_size=MAX_BYTES + 1024,
          channel_timeout=300, connection_limit=200, ident=None, expose_tracebacks=False, clear_untrusted_proxy_headers=True)


if __name__ == "__main__":
    main()
