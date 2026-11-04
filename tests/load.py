#!/usr/bin/env python3
"""Lasttest: N Dateien wie der Browser mit PARALLEL Workern, misst Dauer, Fehler und Spitzenspeicher. Aufruf: load.py <container> <base> <fixtures> <n> <workers>"""
import glob
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

name, base, fix, n, workers = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
files = [open(f, "rb").read() for f in sorted(glob.glob(fix + "/*")) if f.endswith((".pdf", ".xml")) and "viewer-" not in f]
codes, durs = [], []
peak, stop = [0], threading.Event()


def sample():
    while not stop.wait(1):
        out = subprocess.run(["docker", "exec", name, "cat", "/sys/fs/cgroup/memory.peak"], capture_output=True).stdout.strip()
        if out:
            peak[0] = max(peak[0], int(out))


def one(i):
    t0 = time.time()
    while True:
        try:
            with urllib.request.urlopen(urllib.request.Request(base + "/api/validate", data=files[i % len(files)], headers={"Content-Type": "application/octet-stream"}), timeout=600) as r:
                r.read()
                codes.append(r.status)
                break
        except urllib.error.HTTPError as e:
            if e.code == 503:
                time.sleep(1)
                continue
            codes.append(e.code)
            break
    durs.append(time.time() - t0)


threading.Thread(target=sample, daemon=True).start()
t0 = time.time()
with ThreadPoolExecutor(workers) as pool:
    list(pool.map(one, range(n)))
total = time.time() - t0
stop.set()
durs.sort()
state = json.loads(subprocess.run(["docker", "inspect", name], capture_output=True).stdout)[0]["State"]
tmp = subprocess.run(["docker", "exec", name, "sh", "-c", "find /tmp -mindepth 1 ! -path '/tmp/hsperfdata*' | wc -l"], capture_output=True).stdout.decode().strip()
print(json.dumps({"files": n, "workers": workers, "total_s": round(total), "per_file_s": round(total / n, 2), "median_s": round(durs[len(durs) // 2], 1), "max_s": round(durs[-1], 1),
                  "codes": {c: codes.count(c) for c in set(codes)}, "peak_mem_gb": round(peak[0] / 1024 ** 3, 2), "oom": state["OOMKilled"], "tmp_left": tmp, "cpus": os.cpu_count()}))
