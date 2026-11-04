"""Eigener, begrenzter Prozess zum Herauslösen der Rechnungs-XML aus einer PDF.

Läuft getrennt vom Server mit Speicher- und Zeitlimit, damit eine präparierte PDF (Entpack-Bombe)
höchstens diesen Prozess beendet. Aufruf: pdf_extract.py <pdf> <zieldatei>; gibt den Anhangnamen aus.
"""
import resource
import sys

EMBED_NAMES = ("factur-x.xml", "xrechnung.xml", "zugferd-invoice.xml", "zugferd_invoice.xml", "order-x.xml")
LIMIT = 1024 * 1024 * 1024


def main(src, dst):
    resource.setrlimit(resource.RLIMIT_AS, (LIMIT, LIMIT))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    from pypdf import PdfReader
    attachments = PdfReader(src).attachments
    lower = {n.lower(): (n, b) for n, b in attachments.items() if b}
    found = next((lower[n] for n in EMBED_NAMES if n in lower), None)
    if found is None:
        found = next(((n, b) for n, b in attachments.items() if n.lower().endswith(".xml") and b), None)
    if found is None:
        return 3
    with open(dst, "wb") as f:
        f.write(found[1][0])
    sys.stdout.write(found[0])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1], sys.argv[2]))
    except Exception:  # noqa: BLE001  Details bleiben bewusst ungeloggt
        sys.exit(2)
