#!/usr/bin/env python3
"""Prüft das fertige Image auf Datenschutz, Härtung und Angriffe. Ergebnis als Nachweis in tests/out/security-evidence.md.

Aufruf: python3 -I tests/test_image.py <image>

Optional: EV_FORBIDDEN_PATTERN="<regex>" prüft zusätzlich, dass Image und Quellcode keine bestimmten Begriffe enthalten
(z. B. Kundennamen). Das Muster steht bewusst nicht im Repo; ohne die Variable wird dieser Check übersprungen.
"""
import io
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zlib

IMAGE = sys.argv[1] if len(sys.argv) > 1 else "einvoice-validator:dev"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures")
PORT = 18148
BASE = f"http://127.0.0.1:{PORT}"
NAME = "einvoice-sec"
CANARY = "CANARY7F3AX"
HARDEN = ["--read-only", "--tmpfs", "/tmp:size=1g,mode=1777,noexec,nosuid,nodev", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
          "--pids-limit", "512", "--ulimit", "core=0", "--memory", "5g"]
results = []


def sh(*cmd, input=None, check=False):
    return subprocess.run(cmd, input=input, capture_output=True, check=check)


def record(group, name, ok, detail=""):
    """ok=True bestanden, False nicht bestanden, None übersprungen."""
    results.append((group, name, None if ok is None else bool(ok), str(detail)[:300]))
    label = "SKIP" if ok is None else "OK  " if ok else "FAIL"
    print(f"{label} [{group}] {name}{' — ' + str(detail)[:160] if detail and not ok else ''}", flush=True)


def start(name=NAME, port=PORT, env=(), net=None):
    sh("docker", "rm", "-f", name)
    cmd = ["docker", "run", "-d", "--name", name, *HARDEN, "-e", "PARALLEL=2"]
    for e in env:
        cmd += ["-e", e]
    cmd += ["--network", net] if net else ["-p", f"127.0.0.1:{port}:8000"]
    sh(*cmd, IMAGE, check=True)
    if net:
        time.sleep(4)
        return
    for _ in range(40):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2)
            return
        except Exception:
            time.sleep(0.5)
    raise SystemExit("Container startet nicht")


def post(path, data, base=BASE, timeout=240):
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/octet-stream"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def fixture(n):
    with open(os.path.join(FIX, n), "rb") as f:
        return f.read()


def tmp_files():
    return sh("docker", "exec", NAME, "sh", "-c", "find /tmp -mindepth 1 ! -path '/tmp/hsperfdata*' | wc -l").stdout.decode().strip()


def verdict(body, lang="de"):
    return json.loads(body)["reports"][lang]


def pdf_with_stream(payload, flate):
    """Minimale PDF mit einem Anhang factur-x.xml. flate=True: payload ist bereits komprimiert."""
    filt = b"/Filter /FlateDecode " if flate else b""
    objs = [b"<< /Type /Catalog /Pages 2 0 R /Names << /EmbeddedFiles << /Names [(factur-x.xml) 4 0 R] >> >> >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>", b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>",
            b"<< /Type /Filespec /F (factur-x.xml) /EF << /F 5 0 R >> >>",
            b"<< /Type /EmbeddedFile " + filt + b"/Length " + str(len(payload)).encode() + b" >>\nstream\n" + payload + b"\nendstream"]
    out = io.BytesIO(b"%PDF-1.7\n")
    out.seek(0, 2)
    off = []
    for i, o in enumerate(objs, 1):
        off.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + o + b"\nendobj\n")
    x = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for o in off:
        out.write(f"{o:010d} 00000 n \n".encode())
    out.write(f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode())
    return out.getvalue()


# ---------------------------------------------------------------- Container

start()
base_xml = fixture("en16931-cii-valid.xml")
canary_xml = re.sub(rb"(<ram:SellerTradeParty>.*?<ram:Name>)[^<]*", lambda m: m.group(1) + CANARY.encode(), base_xml, count=1, flags=re.S)
assert CANARY.encode() in canary_xml

uid = sh("docker", "exec", NAME, "id", "-u").stdout.decode().strip()
record("Härtung", "läuft nicht als root", uid not in ("", "0"), uid)
record("Härtung", "Dateisystem schreibgeschützt", sh("docker", "exec", NAME, "sh", "-c", "touch /app/x").returncode != 0)
record("Härtung", "kein Schreiben ins Programmverzeichnis", sh("docker", "exec", NAME, "sh", "-c", "touch /opt/einvoice/x").returncode != 0)
caps = sh("docker", "exec", NAME, "sh", "-c", "grep CapEff /proc/1/status").stdout.decode()
record("Härtung", "keine Linux-Capabilities", caps.strip().endswith("0000000000000000"), caps)

# ---------------------------------------------------------------- Keine Spuren

status, headers, body = post("/api/validate", canary_xml)
record("Spuren", "Prüfung mit Canary funktioniert", status == 200 and verdict(body)["invoice"]["seller"] == CANARY, status)
record("Spuren", "API-Antwort: Cache-Control no-store", headers.get("Cache-Control") == "no-store", headers.get("Cache-Control"))
status, headers, html = post("/api/visualize?lang=en", canary_xml)
record("Spuren", "Ansicht mit Canary funktioniert", status == 200 and CANARY.encode() in html, status)
record("Spuren", "Ansicht: Cache-Control no-store", headers.get("Cache-Control") == "no-store")
broken = canary_xml[: len(canary_xml) // 2]
status, _h, body = post("/api/validate", broken)
record("Spuren", "abgeschnittene XML führt zu Bericht statt Absturz", status == 200 and verdict(body)["verdict"] == "fail", status)
post("/api/validate", b"<x>" + CANARY.encode())
post("/api/visualize", b"<x>" + CANARY.encode())

# JVM während der Prüfung hart beenden
result = {}
t = threading.Thread(target=lambda: result.update(r=post("/api/validate", canary_xml)))
t.start()
time.sleep(1.5)
sh("docker", "exec", NAME, "sh", "-c", "for p in /proc/[0-9]*; do if tr '\\0' ' ' < $p/cmdline 2>/dev/null | grep -q 'java.*jar'; then kill -9 ${p#/proc/}; fi; done")
t.join()
record("Spuren", "kill -9 der JVM: Fehlerantwort statt Hänger", result["r"][0] in (200, 500), result["r"][0])
time.sleep(1)
record("Spuren", "tmpfs danach leer", tmp_files() == "0", tmp_files())
diff = sh("docker", "diff", NAME).stdout.decode().strip()
record("Spuren", "docker diff leer (nichts auf der Platte)", diff == "", diff)
logs = sh("docker", "logs", NAME)
text = logs.stdout + logs.stderr
record("Spuren", "Canary nicht in den Logs", CANARY.encode() not in text)
lines = [l for l in text.decode("utf-8", "replace").splitlines() if l.strip()]
allowed = re.compile(r"^(\[req\] /api/\w+ \d{3} \d+ms|\[engine\] \w+ \w+|\[error\] /api/\w+ \w+|einvoice-validator .* on :\d+ parallel=\d+)$")
bad = [l for l in lines if not allowed.match(l)]
record("Spuren", "Logs enthalten nur Pfad, Status, Dauer", not bad, bad[:3])
mem = sh("docker", "exec", NAME, "sh", "-c", f"grep -rl {CANARY} /tmp /app /opt/einvoice 2>/dev/null | wc -l").stdout.decode().strip()
record("Spuren", "Canary in keiner Datei im Container", mem == "0", mem)
ps = sh("docker", "exec", NAME, "sh", "-c", "for p in /proc/[0-9]*; do tr '\\0' ' ' < $p/cmdline 2>/dev/null | grep -c '[j]ava' ; done | paste -sd+ | sed 's/$/+0/'").stdout.decode().strip()
record("Spuren", "keine Java-Prozesse bleiben zurück", eval(ps or "0") == 0, ps)

# Dateiname wird nicht übertragen: statische Prüfung des Frontends
js = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
record("Spuren", "Frontend überträgt keinen Dateinamen", "X-Filename" not in js and "FormData" not in js)

# ---------------------------------------------------------------- HTTP-Header

req = urllib.request.urlopen(BASE + "/")
h = dict(req.headers)
csp = h.get("Content-Security-Policy", "")
record("Header", "CSP gesetzt, script-src nur 'self'", "script-src 'self'" in csp and "script-src 'self' 'unsafe" not in csp, csp)
record("Header", "connect-src nur 'self' (kein Abfluss aus dem Browser)", "connect-src 'self'" in csp)
record("Header", "nosniff, DENY, no-referrer", h.get("X-Content-Type-Options") == "nosniff" and h.get("X-Frame-Options") == "DENY" and h.get("Referrer-Policy") == "no-referrer")
record("Header", "kein Server-Banner", "Server" not in h, h.get("Server"))
index = urllib.request.urlopen(BASE + "/").read().decode()
record("Header", "Seite lädt nichts von außen", not re.search(r"""(src|href)=["']https?://""", index))

# ---------------------------------------------------------------- XML-Angriffe

xxe = b'<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"><a>&xxe;</a></rsm:CrossIndustryInvoice>'
laugh = b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;"><!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;"><!ENTITY d "&c;&c;&c;&c;&c;&c;&c;&c;&c;&c;">]><l>&d;</l>'
for label, payload in (("XXE", xxe), ("Billion Laughs", laugh), ("DOCTYPE in UTF-16", xxe.decode().encode("utf-16"))):
    status, _h, body = post("/api/validate", payload)
    rep = verdict(body) if status == 200 else {}
    record("Angriff", f"{label} abgelehnt", status == 200 and "Sicherheit" in rep.get("headline", "") and b"root:" not in body, status)
    status, _h, body = post("/api/visualize", payload)
    record("Angriff", f"{label} auch in der Ansicht abgelehnt", status == 422, status)
ebcdic = '<?xml version="1.0" encoding="IBM037"?><!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><a>&x;</a>'
status, _h, body = post("/api/validate", ebcdic.encode("cp037"))
record("Angriff", "EBCDIC-Kodierung umgeht die Prüfung nicht", b"root:" not in body and status in (200, 422), status)
status, _h, body = post("/api/validate", b'<?xml version="1.0" encoding="IBM037"?><a/>')
record("Angriff", "unbekannte Kodierung abgelehnt", status == 200 and "Sicherheit" in verdict(body)["headline"], status)
status, _h, body = post("/api/validate", pdf_with_stream(xxe, False))
record("Angriff", "XXE in eingebetteter XML einer PDF abgelehnt", status == 200 and "Sicherheit" in verdict(body)["headline"] and b"root:" not in body, status)

# ---------------------------------------------------------------- Überlast und kaputte Dateien

bomb = pdf_with_stream(zlib.compress(b"\0" * (3 * 1024 ** 3), 9), True)
t0 = time.time()
status, _h, body = post("/api/validate", bomb)
record("Angriff", f"Entpack-Bombe (3 GB → {len(bomb) // 1024} KB) wird abgefangen", status in (200, 500, 504), f"{status} in {time.time() - t0:.0f}s")
inspect = json.loads(sh("docker", "inspect", NAME).stdout)[0]["State"]
record("Angriff", "Container überlebt die Bombe", inspect["Running"] and inspect["OOMKilled"] is False, inspect)
status, _h, _b = post("/api/validate", b"%PDF-1.7\n" + os.urandom(2048))
record("Angriff", "kaputte PDF führt nicht zum Absturz", status in (200, 500), status)
status, _h, _b = post("/api/validate", b"")
record("Limit", "leere Datei: 400", status == 400, status)
try:
    status = post("/api/validate", b"x" * (26 * 1024 * 1024))[0]
except (urllib.error.URLError, ConnectionError, socket.timeout) as e:
    status = type(e).__name__
record("Limit", "Datei über 25 MB abgewiesen", status in (413, 400, "URLError", "ConnectionResetError", "BrokenPipeError"), status)

socks = []
for _ in range(50):
    s = socket.create_connection(("127.0.0.1", PORT), timeout=5)
    s.send(b"POST /api/validate HTTP/1.1\r\nHost: x\r\nContent-Length: 1000000\r\n\r\nabc")
    socks.append(s)
t0 = time.time()
ok = urllib.request.urlopen(BASE + "/healthz", timeout=5).status == 200
record("Limit", "50 langsame Verbindungen blockieren den Dienst nicht", ok, f"{time.time() - t0:.2f}s")
status, _h, _b = post("/api/validate", base_xml)
record("Limit", "Prüfung läuft währenddessen", status == 200, status)
for s in socks:
    s.close()

codes, lock = [], threading.Lock()
retry = []
def burst():
    st, hd, _ = post("/api/validate", base_xml, timeout=300)
    with lock:
        codes.append(st)
        if st == 503:
            retry.append(hd.get("Retry-After"))
threads = [threading.Thread(target=burst) for _ in range(30)]
[t.start() for t in threads]
[t.join() for t in threads]
record("Limit", "Überlast: 200 oder 503 mit Retry-After, sonst nichts", set(codes) <= {200, 503} and all(retry), {c: codes.count(c) for c in set(codes)})
time.sleep(2)
record("Spuren", "tmpfs nach allen Tests leer", tmp_files() == "0", tmp_files())
logs = sh("docker", "logs", NAME)
record("Spuren", "Canary auch am Ende nicht in den Logs", CANARY.encode() not in logs.stdout + logs.stderr)

# ---------------------------------------------------------------- Fachlich: Lücke von Mustang wird geschlossen

no_terms = re.sub(rb"<ram:SpecifiedTradePaymentTerms>.*?</ram:SpecifiedTradePaymentTerms>", b"", base_xml, flags=re.S)
status, _h, body = post("/api/validate", no_terms)
d = verdict(body) if status == 200 else {"errors": []}
ids = {p["id"]: p["sources"] for p in d["errors"]}
record("Fachlich", "fehlende Zahlungsbedingungen: BR-CO-25 wird gemeldet", "BR-CO-25" in ids, ids)
record("Fachlich", "BR-CO-25: Widerspruch zu den Engines wird offen ausgewiesen", bool(d.get("conflict")) and "BR-CO-25" in d.get("conflict", ""), d.get("conflict"))
en = verdict(body, "en") if status == 200 else {}
record("Fachlich", "Bericht liegt auch auf Englisch vor", not re.search("[äöüß]", " ".join(p.get("title", "") + p.get("text", "") for p in en.get("errors", []))))
status, _h, cn = post("/api/validate", fixture("credit-note-no-payment-info.xml"))
cd = verdict(cn) if status == 200 else {"warnings": [], "verdict": ""}
record("Fachlich", "Gutschrift ohne Zahlungsangaben: nur Hinweis", cd["verdict"] == "warn" and any(p["id"] == "BR-CO-25" for p in cd["warnings"]), cd["verdict"])
sh("docker", "rm", "-f", NAME)

# ---------------------------------------------------------------- Zeitlimit

start(env=("ENGINE_TIMEOUT=1",))
status, _h, _b = post("/api/validate", base_xml)
record("Limit", "Zeitlimit greift: 504", status == 504, status)
time.sleep(1)
record("Spuren", "Temp-Ordner nach Zeitüberschreitung entfernt", tmp_files() == "0", tmp_files())
sh("docker", "rm", "-f", NAME)

# ---------------------------------------------------------------- Ohne Netz

start(net="none")
probe = """
import json,sys,urllib.request as u
d=sys.stdin.buffer.read()
o=json.load(u.urlopen(u.Request('http://127.0.0.1:8000/api/validate',data=d),timeout=120))
r=o['reports']['de']; s={x['key']:x['ok'] for x in r['steps']}
h=u.urlopen(u.Request('http://127.0.0.1:8000/api/visualize',data=d),timeout=120).read()
print(json.dumps({'verdict':r['verdict'],'kosit':s.get('kosit'),'view':len(h)}))
"""
for name in ("en16931-cii-valid.xml", "xrechnung-cii-valid.xml", "zugferd-extended.pdf"):
    out = sh("docker", "exec", "-i", NAME, "python", "-I", "-c", probe, input=fixture(name))
    try:
        r = json.loads(out.stdout)
    except ValueError:
        r = {"err": out.stderr.decode()[:200]}
    record("Netz", f"läuft komplett ohne Netz: {name}", r.get("view", 0) > 1000 and r.get("verdict") in ("ok", "warn"), r)
sh("docker", "rm", "-f", NAME)

# ---------------------------------------------------------------- Neutralität und Unabhängigkeit

pat = os.environ.get("EV_FORBIDDEN_PATTERN", "")
if pat:
    hits = sh("docker", "run", "--rm", "--entrypoint", "sh", IMAGE, "-c",
              f"grep -rIliE {shlex.quote(pat)} /app /opt/einvoice/kosit-config /opt/einvoice/viewer 2>/dev/null | wc -l").stdout.decode().strip()
    record("Neutral", "keine verbotenen Begriffe im Image", hits == "0", hits)
    tree = sh("grep", "-rIliE", pat, *[os.path.join(ROOT, d) for d in ("src", "web", "docker", "tools", "docs", "deploy")]).stdout.decode().strip()
    record("Neutral", "keine verbotenen Begriffe im Quellcode und in der Doku", tree == "", tree)
else:
    record("Neutral", "Prüfung auf verbotene Begriffe (EV_FORBIDDEN_PATTERN nicht gesetzt)", None)

# ---------------------------------------------------------------- Bericht

failed = [r for r in results if r[2] is False]
skipped = [r for r in results if r[2] is None]
checked = len(results) - len(skipped)
os.makedirs(os.path.join(ROOT, "tests", "out"), exist_ok=True)
with open(os.path.join(ROOT, "tests", "out", "security-evidence.md"), "w", encoding="utf-8") as f:
    f.write(f"# Prüfnachweis Datenschutz und Sicherheit\n\nImage: `{IMAGE}`  \nErstellt: {time.strftime('%Y-%m-%d %H:%M')}  \nErgebnis: {checked - len(failed)} von {checked} bestanden{f', {len(skipped)} übersprungen' if skipped else ''}\n\n")
    f.write("| Bereich | Prüfung | Ergebnis |\n|---|---|---|\n")
    for g, n, ok, _d in results:
        f.write(f"| {g} | {n} | {'übersprungen' if ok is None else 'bestanden' if ok else 'NICHT BESTANDEN'} |\n")
print(f"\n{checked - len(failed)} von {checked} bestanden" + (f", {len(skipped)} übersprungen" if skipped else ""))
sys.exit(1 if failed else 0)
