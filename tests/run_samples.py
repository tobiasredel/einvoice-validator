#!/usr/bin/env python3
"""Schickt alle Dateien eines Ordners an den Validator und gibt je Datei Urteil, Engines und Fehler-IDs aus."""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = os.environ.get("BASE", "http://127.0.0.1:18147")


def check(path):
    with open(path, "rb") as f:
        data = f.read()
    t0 = time.time()
    req = urllib.request.Request(BASE + "/api/validate", data=data, headers={"Content-Type": "application/octet-stream"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        return {"file": os.path.basename(path), "http": e.code, "error": e.read().decode()[:120]}
    d = out["reports"]["de"]
    steps = {s["key"]: s["ok"] for s in d["steps"]}
    return {"file": os.path.basename(path), "verdict": d["verdict"], "kosit": steps.get("kosit", "-"),
            "conflict": bool(d.get("conflict")), "errors": [p["id"] for p in d["errors"]][:6], "warn": len(d["warnings"]),
            "untitled": [p["id"] for p in d["errors"] + d["warnings"] if not p.get("title")], "s": round(time.time() - t0, 1)}


if __name__ == "__main__":
    files = sorted(os.path.join(dp, n) for dp, _d, fs in os.walk(sys.argv[1]) for n in fs if n.lower().endswith((".pdf", ".xml")))
    with ThreadPoolExecutor(int(os.environ.get("WORKERS", "4"))) as pool:
        results = list(pool.map(check, files))
    for r in results:
        print(json.dumps(r, ensure_ascii=False))
    json.dump(results, open(sys.argv[2], "w"), ensure_ascii=False, indent=1) if len(sys.argv) > 2 else None
