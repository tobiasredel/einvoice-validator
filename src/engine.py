"""Prüf-Engines: Mustang (PDF/A, Kennzeichnung, Schema, EN 16931, Rechnen) und KoSIT (Referenzprüfung).

Jede Prüfung läuft in einem eigenen Temp-Ordner auf tmpfs. Jede Engine ist ein eigener, kurzlebiger
Java-Prozess: Mit seinem Ende ist auch der Arbeitsspeicher mit den Rechnungsdaten weg.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

OPT = os.environ.get("EV_OPT", "/opt/einvoice")
MUSTANG_JAR = os.path.join(OPT, "mustang.jar")
KOSIT_JAR = os.path.join(OPT, "kosit.jar")
KOSIT_CFG = os.path.join(OPT, "kosit-config")
VIEWER_XSL = os.path.join(OPT, "viewer", "xsl")
DRIVER_XSL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "viewer_driver.xsl")
EXTRACTOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pdf_extract.py")
TIMEOUT = int(os.environ.get("ENGINE_TIMEOUT", "120"))
JOB_PREFIX = "ev-job-"
XML_ENCODINGS = {"utf-8", "utf8", "utf-16", "utf16", "iso-8859-1", "latin1", "us-ascii", "ascii"}


class Rejected(Exception):
    """Die Datei wird aus Sicherheitsgründen nicht verarbeitet (`.reason`: doctype | encoding)."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class Job:
    """Temp-Ordner einer Prüfung (0700), wird in jedem Fall wieder gelöscht."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix=JOB_PREFIX)
        return self

    def __exit__(self, *exc):
        shutil.rmtree(self.dir, ignore_errors=True)

    def path(self, name):
        return os.path.join(self.dir, name)


def sweep():
    """Beim Start: Reste eines abgebrochenen Prozesses entfernen."""
    tmp = tempfile.gettempdir()
    for name in os.listdir(tmp):
        if name.startswith(JOB_PREFIX):
            shutil.rmtree(os.path.join(tmp, name), ignore_errors=True)


def _java(job, heap):
    return ["java", f"-Xmx{heap}", "-XX:TieredStopAtLevel=1", "-XX:+UseSerialGC", "-XX:-UsePerfData",
            "-XX:-CreateCoredumpOnCrash", "-XX:-HeapDumpOnOutOfMemoryError", "-XX:+ExitOnOutOfMemoryError",
            "-XX:+DisableAttachMechanism", f"-XX:ErrorFile={job.path('hs_err.log')}",
            f"-Djava.io.tmpdir={job.dir}", f"-Duser.home={job.dir}", "-Djava.awt.headless=true",
            "-Djavax.xml.accessExternalDTD=", "-Djavax.xml.accessExternalStylesheet=file,jar,jrt"]


def _run(job, cmd):
    """Führt eine Engine aus. stdout und stderr bleiben im Prozess und landen in keinem Log."""
    return subprocess.run(cmd, cwd=job.dir, capture_output=True, timeout=TIMEOUT,
                          env={"PATH": os.environ.get("PATH", ""), "HOME": job.dir, "TMPDIR": job.dir,
                               "LANG": "C.UTF-8"})


def preflight_xml(data):
    """Rechnungs-XML braucht keine DTD. Mit dem Verbot entfallen XXE und Entity-Bomben schon vor den Parsern."""
    if re.search(rb"<!\s*DOCTYPE", data.replace(b"\x00", b""), re.I):
        raise Rejected("doctype")
    head = data[:400].replace(b"\x00", b"")
    m = re.search(rb"""<\?xml[^>]*?encoding\s*=\s*["']([^"']+)["']""", head)
    if m and m.group(1).decode("ascii", "replace").lower() not in XML_ENCODINGS:
        raise Rejected("encoding")
    start = data.lstrip(b"\xef\xbb\xbf\xff\xfe \t\r\n\x00")[:1]
    if start and start != b"<":
        raise Rejected("encoding")


def extract_xml(job, pdf_path):
    """(Anhangname, Bytes) der eingebetteten XML; (None, None), wenn es keine gibt oder die PDF nicht lesbar ist."""
    dst = job.path("embedded.xml")
    try:
        proc = subprocess.run([sys.executable, "-I", EXTRACTOR, pdf_path, dst], cwd=job.dir, capture_output=True,
                              timeout=60, env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"})
    except subprocess.TimeoutExpired:
        return None, None
    if proc.returncode != 0 or not os.path.exists(dst):
        return None, None
    with open(dst, "rb") as f:
        return proc.stdout.decode("utf-8", "replace"), f.read()


def run_mustang(job, path):
    proc = _run(job, _java(job, "768m") + ["-jar", MUSTANG_JAR, "--action", "validate", "--source", path,
                                           "--disable-file-logging"])
    out = proc.stdout.decode("utf-8", "replace")
    start, end = out.find("<validation"), out.rfind("</validation>")
    if start < 0 or end < 0:
        raise RuntimeError("no report")
    return ET.fromstring(out[start:end + len("</validation>")].encode("utf-8"))


# ---------------------------------------------------------------- KoSIT

try:
    with open(os.path.join(KOSIT_CFG, "scenario-index.json"), encoding="utf-8") as _f:
        SCENARIOS = json.load(_f)
except FileNotFoundError:
    SCENARIOS = []


def scenario_for(xml_root):
    """Passendes Szenario der offiziellen Konfiguration oder None. Die Trefferregeln sind dieselben wie in
    scenarios.xml; je Szenario liegt eine eigene Konfiguration bereit, das spart rund 5 s Start je Datei."""
    if xml_root is None:
        return None
    tag = xml_root.tag.rsplit("}", 1)[-1]
    ns = xml_root.tag[1:].split("}")[0] if xml_root.tag.startswith("{") else ""
    if tag == "CrossIndustryInvoice":
        ident = next((e.text for e in xml_root.iter() if e.tag.endswith("}ID") and e.text
                      and any(c is e for p in xml_root.iter() if p.tag.endswith("}GuidelineSpecifiedDocumentContextParameter") for c in p)), None)
    else:
        ident = next((c.text for c in xml_root if c.tag.endswith("}CustomizationID")), None)
    ident = (ident or "").strip()
    for s in SCENARIOS:
        if s["root"] == tag and s["ns"] == ns and s["id"] == ident:
            return s
    return None


def run_kosit(job, xml_path, scenario):
    """→ {valid, scenario, messages: [{code, level, text, location}]}; wirft bei technischem Fehler."""
    out_dir = job.path("kosit")
    os.makedirs(out_dir, mode=0o700, exist_ok=True)
    _run(job, _java(job, "512m") + ["-jar", KOSIT_JAR, "-s", os.path.join(KOSIT_CFG, scenario["file"]), "-r", KOSIT_CFG,
                                    "-o", out_dir, xml_path])
    reports = [n for n in os.listdir(out_dir) if n.endswith("-report.xml")]
    if not reports:
        raise RuntimeError("no report")
    root = ET.parse(os.path.join(out_dir, reports[0])).getroot()
    messages = []
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1] == "message":
            messages.append({"code": el.get("code") or "", "level": el.get("level") or "error",
                             "text": re.sub(r"\s+", " ", el.text or "").strip(), "location": el.get("xpathLocation") or ""})
    # Maßgeblich ist die Bewertung (assessment/accept), nicht das Attribut @valid: Das ist auch bei reinen Warnungen "false".
    assessment = next((c for c in root if c.tag.endswith("}assessment")), None)
    accepted = assessment is not None and any(c.tag.endswith("}accept") for c in assessment)
    return {"valid": accepted, "scenario": scenario["name"], "messages": messages}


# ---------------------------------------------------------------- Viewer

VIEWER_INPUT = {"CrossIndustryInvoice": "cii-xr.xsl", "Invoice": "ubl-invoice-xr.xsl", "CreditNote": "ubl-creditnote-xr.xsl"}


def run_viewer(job, xml_path, root_tag, lang):
    """KoSIT-Visualisierung über Saxon-HE (aus dem Mustang-Jar) → HTML-Text."""
    out = job.path("view.html")
    proc = _run(job, _java(job, "512m") + ["-cp", MUSTANG_JAR, "net.sf.saxon.Transform", f"-s:{xml_path}", f"-xsl:{DRIVER_XSL}",
                                           f"-o:{out}", f"base=file://{VIEWER_XSL}", f"to={VIEWER_INPUT[root_tag]}", f"lang={lang}"])
    if proc.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) == 0:
        # Die aktuelle KoSIT-Ansicht scheitert an manchen EXTENDED-Rechnungen (z. B. mehrere Preisnachlässe je Position).
        # Mustang bringt eine eigene, duldsamere Kopie mit.
        _run(job, _java(job, "512m") + ["-jar", MUSTANG_JAR, "--action", "visualize", "--language", lang, "--source", xml_path,
                                        "--out", out, "--disable-file-logging"])
    if not os.path.exists(out) or os.path.getsize(out) == 0:
        raise RuntimeError("no view")
    with open(out, encoding="utf-8") as f:
        return f.read()


