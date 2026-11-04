#!/usr/bin/env python3
"""Sammelt Lizenz- und NOTICE-Texte aus den mitgelieferten Jars (stdout). Läuft im Image."""
import re
import sys
import zipfile

PATTERN = re.compile(r"(^|/)(LICENSE|LICENCE|NOTICE|COPYING)[^/]*$", re.I)
for jar in sys.argv[1:]:
    with zipfile.ZipFile(jar) as z:
        for name in sorted(z.namelist()):
            if name.endswith("/") or not PATTERN.search(name):
                continue
            text = z.read(name).decode("utf-8", "replace")
            print(f"\n===== {jar.rsplit('/', 1)[-1]}: {name} =====\n{text}")
