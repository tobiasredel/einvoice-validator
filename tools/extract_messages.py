#!/usr/bin/env python3
"""Listet alle deutschen Quelltexte aus `_("...")`-Aufrufen im Backend (eine JSON-Liste auf stdout)."""
import ast
import glob
import json
import os
import sys


def extract(src_dir):
    found = []
    for path in sorted(glob.glob(os.path.join(src_dir, "*.py"))):
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_"
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                found.append(node.args[0].value)
    return list(dict.fromkeys(found))


if __name__ == "__main__":
    json.dump(extract(sys.argv[1]), sys.stdout, ensure_ascii=False, indent=0)
