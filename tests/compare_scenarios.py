"""Vergleicht je XML-Datei Urteil und Regel-IDs: offizielle scenarios.xml gegen die gefilterte Einzelkonfiguration."""
import glob
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

CFG = "/opt/einvoice/kosit-config"
JAR = "/opt/einvoice/kosit.jar"
index = json.load(open(f"{CFG}/scenario-index.json"))
files = sorted(glob.glob(sys.argv[1] + "/**/*.xml", recursive=True))


def run(scenarios, paths):
    out = tempfile.mkdtemp()
    subprocess.run(["java", "-Xmx1g", "-XX:TieredStopAtLevel=1", "-jar", JAR, "-s", scenarios, "-r", CFG, "-o", out, *paths], capture_output=True, cwd=out)
    res = {}
    for f in glob.glob(out + "/*-report.xml"):
        root = ET.parse(f).getroot()
        assess = next((c for c in root if c.tag.endswith("}assessment")), None)
        scenario = next((c for c in root if c.tag.endswith("}scenarioMatched")), None)
        res[os.path.basename(f)[:-len("-report.xml")]] = {
            "accepted": assess is not None and any(c.tag.endswith("}accept") for c in assess),
            "matched": scenario is not None,
            "codes": sorted(e.get("code") or "" for e in root.iter() if e.tag.endswith("}message"))}
    return res


full = run(f"{CFG}/scenarios.xml", files)
def key(path):
    try:
        r = ET.parse(path).getroot()
    except ET.ParseError:
        return None
    tag = r.tag.rsplit("}", 1)[-1]
    ident = next((c.text for c in r if c.tag.endswith("}CustomizationID")), None)
    if tag == "CrossIndustryInvoice":
        ctx = next((c for c in r if c.tag.endswith("}ExchangedDocumentContext")), None)
        par = next((c for c in (ctx if ctx is not None else []) if c.tag.endswith("}GuidelineSpecifiedDocumentContextParameter")), None)
        ident = next((c.text for c in (par if par is not None else []) if c.tag.endswith("}ID")), None)
    return next((s for s in index if s["root"] == tag and s["id"] == (ident or "").strip()), None)

groups = {}
for f in files:
    s = key(f)
    if s:
        groups.setdefault(s["file"], []).append(f)
sub = {}
for file, paths in groups.items():
    sub.update(run(f"{CFG}/{file}", paths))
diff, same = [], 0
for name, r in sorted(full.items()):
    if not r["matched"]:
        if name in sub:
            diff.append((name, "App wählt Szenario, das Original keins"))
        continue
    if name not in sub:
        diff.append((name, "Original trifft Szenario, App keins"))
    elif sub[name] != r:
        diff.append((name, r["accepted"], sub[name]["accepted"]))
    else:
        same += 1
print(json.dumps({"files": len(files), "matched": same + len(diff), "identical": same, "differences": diff}, ensure_ascii=False, indent=1))
sys.exit(1 if diff else 0)
