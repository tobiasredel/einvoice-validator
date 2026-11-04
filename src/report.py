"""Baut aus den Ergebnissen von Mustang und KoSIT einen verständlichen Bericht in der aktiven Sprache."""
import re
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

import schema_explain
from engine import MUSTANG_JAR
from i18n import _, lang, names, rule


def lname(tag):
    return tag.rsplit("}", 1)[-1]


def child(el, *path):
    for n in path:
        if el is None:
            return None
        el = next((c for c in el if lname(c.tag) == n), None)
    return el


def text(el, *path):
    el = child(el, *path) if path else el
    return el.text.strip() if el is not None and el.text else ""


# ---------------------------------------------------------------- Eckdaten

def profiles():
    return [
        ("crossindustrydocument:invoice:1p0", "ZUGFeRD 1.0", _("Veraltete erste Version von ZUGFeRD.")),
        ("xrechnung", "XRechnung", _("Standard für Rechnungen an Behörden in Deutschland.")),
        ("extended", "EXTENDED", _("Erweitertes Profil mit zusätzlichen Angaben.")),
        ("basicwl", "BASIC WL", _("Nur Kopf- und Summendaten, keine Positionen.")),
        ("minimum", "MINIMUM", _("Nur die allernötigsten Daten.")),
        ("1p0:basic", "BASIC", _("Rechnungsdaten mit einfachen Positionen.")),
        ("en16931", "EN 16931 (Comfort)", _("Vollständige europäische Norm-Rechnung.")),
        ("peppol", "Peppol BIS", _("Format des europäischen Peppol-Netzes.")),
    ]


def doc_type(code):
    return {
        "380": _("Rechnung"), "381": _("Gutschrift"), "384": _("Korrekturrechnung"),
        "389": _("Gutschrift (vom Kunden ausgestellt)"), "326": _("Teilrechnung"),
        "875": _("Abschlagsrechnung"), "876": _("Abschlagsrechnung"), "877": _("Schlussrechnung"),
        "386": _("Vorauszahlungsrechnung"), "261": _("Stornorechnung"), "751": _("Rechnungsinformation"),
        "220": _("Bestellung"), "231": _("Bestellbestätigung"), "351": _("Lieferavis"),
    }.get(code, code)


def profile_of(guideline):
    g = (guideline or "").lower()
    for key, name, desc in profiles():
        if key in g:
            return name, desc
    if g:
        return _("Unbekannt"), _("Die Profil-Kennung ist keiner bekannten Variante zuzuordnen.")
    return "", ""


def fmt_money(value, cur):
    try:
        d = Decimal(value)
    except (InvalidOperation, TypeError):
        return value
    s = f"{d:,.2f}"
    if lang() == "de":
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    sym = {"EUR": "€", "USD": "$", "GBP": "£", "CHF": "CHF"}.get(cur, cur)
    return f"{s} {sym}".strip()


def fmt_date(raw):
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", raw or "") or re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", raw or "")
    if not m:
        return raw or ""
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)}" if lang() == "de" else f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def summarize(root):
    s = {}
    if root is None:
        return s
    kind = lname(root.tag)
    money = lambda el, tag, cur: fmt_money(text(el, tag), cur) if text(el, tag) else ""
    if kind == "CrossIndustryInvoice":
        doc = child(root, "ExchangedDocument")
        tx = child(root, "SupplyChainTradeTransaction")
        agr = child(tx, "ApplicableHeaderTradeAgreement")
        stl = child(tx, "ApplicableHeaderTradeSettlement")
        cur = text(stl, "InvoiceCurrencyCode")
        summ = child(stl, "SpecifiedTradeSettlementHeaderMonetarySummation")
        s.update(syntax="CII", guideline=text(child(root, "ExchangedDocumentContext"), "GuidelineSpecifiedDocumentContextParameter", "ID"),
                 number=text(doc, "ID"), type=doc_type(text(doc, "TypeCode")), date=fmt_date(text(doc, "IssueDateTime", "DateTimeString")),
                 seller=text(agr, "SellerTradeParty", "Name"), buyer=text(agr, "BuyerTradeParty", "Name"),
                 net=money(summ, "TaxBasisTotalAmount", cur), total=money(summ, "GrandTotalAmount", cur), due=money(summ, "DuePayableAmount", cur),
                 lines=sum(1 for c in (tx if tx is not None else []) if lname(c.tag) == "IncludedSupplyChainTradeLineItem"),
                 leitweg=text(agr, "BuyerReference"))
    elif kind == "CrossIndustryDocument":  # ZUGFeRD 1.0
        doc = child(root, "HeaderExchangedDocument")
        tx = child(root, "SpecifiedSupplyChainTradeTransaction")
        agr = child(tx, "ApplicableSupplyChainTradeAgreement")
        stl = child(tx, "ApplicableSupplyChainTradeSettlement")
        cur = text(stl, "InvoiceCurrencyCode")
        summ = child(stl, "SpecifiedTradeSettlementMonetarySummation")
        s.update(syntax="CII", guideline=text(root, "SpecifiedExchangedDocumentContext", "GuidelineSpecifiedDocumentContextParameter", "ID"),
                 number=text(doc, "ID"), type=doc_type(text(doc, "TypeCode")), date=fmt_date(text(doc, "IssueDateTime", "DateTimeString")),
                 seller=text(agr, "SellerTradeParty", "Name"), buyer=text(agr, "BuyerTradeParty", "Name"),
                 total=money(summ, "GrandTotalAmount", cur), due=money(summ, "DuePayableAmount", cur))
    elif kind in ("Invoice", "CreditNote"):
        cur = text(root, "DocumentCurrencyCode")
        lmt = child(root, "LegalMonetaryTotal")
        party = lambda side: text(root, side, "Party", "PartyLegalEntity", "RegistrationName") or text(root, side, "Party", "PartyName", "Name")
        s.update(syntax="UBL", guideline=text(root, "CustomizationID"), number=text(root, "ID"),
                 type=_("Gutschrift") if kind == "CreditNote" else doc_type(text(root, "InvoiceTypeCode")) or _("Rechnung"),
                 date=fmt_date(text(root, "IssueDate")), seller=party("AccountingSupplierParty"), buyer=party("AccountingCustomerParty"),
                 net=money(lmt, "TaxExclusiveAmount", cur), total=money(lmt, "TaxInclusiveAmount", cur), due=money(lmt, "PayableAmount", cur),
                 leitweg=text(root, "BuyerReference"))
    s["profile"], s["profile_desc"] = profile_of(s.get("guideline"))
    return s


def money_overview(root):
    if root is None or lname(root.tag) != "CrossIndustryInvoice":
        return ""
    stl = child(root, "SupplyChainTradeTransaction", "ApplicableHeaderTradeSettlement")
    cur = text(stl, "InvoiceCurrencyCode")
    summ = child(stl, "SpecifiedTradeSettlementHeaderMonetarySummation")
    if summ is None:
        return ""
    parts = []
    for tag, label in (("LineTotalAmount", _("Summe Positionen")), ("AllowanceTotalAmount", _("Rabatte")),
                       ("ChargeTotalAmount", _("Zuschläge")), ("TaxBasisTotalAmount", _("Netto")),
                       ("TaxTotalAmount", _("USt")), ("GrandTotalAmount", _("Brutto")),
                       ("TotalPrepaidAmount", _("Bereits gezahlt")), ("DuePayableAmount", _("Zahlbetrag"))):
        v = text(summ, tag)
        if v and tag in ("AllowanceTotalAmount", "ChargeTotalAmount", "TotalPrepaidAmount"):
            try:
                if Decimal(v) == 0:
                    continue
            except InvalidOperation:
                pass
        if v:
            parts.append(f"{label} {fmt_money(v, cur)}")
    return " · ".join(parts)


# ---------------------------------------------------------------- Fundstellen

STEP_RE = re.compile(r"(@?)(?:Q\{[^}]*\}|\*:|[A-Za-z]+:)?([A-Za-z0-9_]+)(?:\[namespace-uri\(\)='[^']*'\])?(?:\[(\d+)\])?")


def parse_location(loc):
    steps = []
    for part in re.split(r"/(?![^{]*\})", (loc or "").strip("/")):
        m = STEP_RE.fullmatch(part.strip())
        if m:
            steps.append((m.group(1) == "@", m.group(2), int(m.group(3) or 1)))
    return steps


def resolve(root, steps):
    if root is None or not steps or lname(root.tag) != steps[0][1]:
        return None
    el = root
    for is_attr, name, idx in steps[1:]:
        if is_attr:
            return next((v for k, v in el.attrib.items() if lname(k) == name), None)
        matches = [c for c in el if lname(c.tag) == name]
        if len(matches) < idx:
            return None
        el = matches[idx - 1]
    return None if len(el) else (el.text or "").strip()


def field_label(steps):
    parts, line = [], None
    nm = names()
    for is_attr, name, idx in steps[1:]:
        if name in ("IncludedSupplyChainTradeLineItem", "InvoiceLine", "CreditNoteLine"):
            line = idx
            continue
        label = nm.get(("@" if is_attr else "") + name, nm.get(name))
        if label is None:
            label = re.sub(r"(?<!^)(?=[A-Z])", " ", name)
        if label and (not parts or parts[-1] != label):
            parts.append(label)
    label = " › ".join(parts[-3:])
    if line:
        pos = _("Position {n}", n=line)
        label = f"{pos} › {label}" if label else pos
    return label


# ---------------------------------------------------------------- Mustang-Befunde

def verapdf_hints():
    return [
        (r"font|glyph|Font", _("Eine Schriftart ist nicht vollständig in die PDF eingebettet.")),
        (r"OutputIntent|ICC|DeviceRGB|DeviceCMYK|DeviceGray|colou?r space", _("Für die Farben fehlt ein eingebettetes Farbprofil.")),
        (r"[Tt]ransparen|SMask|blend", _("Die PDF verwendet Transparenz, die im Archivformat nicht erlaubt ist.")),
        (r"XMP|[Mm]etadata|document information dictionary|pdfaid", _("Die Dokument-Eigenschaften (Titel, Autor, Datum …) sind widersprüchlich oder fehlen.")),
        (r"[Ee]ncrypt", _("Die PDF ist verschlüsselt bzw. passwortgeschützt.")),
        (r"JavaScript|Action|Launch", _("Die PDF enthält Skripte oder Aktionen, die nicht erlaubt sind.")),
        (r"EmbeddedFile|AFRelationship|/AF ", _("Die angehängte Rechnungsdatei ist nicht korrekt mit der PDF verknüpft.")),
        (r"version|header", _("Die PDF-Version oder der Dateikopf entspricht nicht dem Archivformat.")),
    ]


def verapdf_findings(pdf_el):
    raw = (pdf_el.text or "") if pdf_el is not None else ""
    found = [(m.group(1), m.group(3)) for m in re.finditer(r"clause=([\d.]+), testNumber=(\d+)\], status=failed, message=(.*?), location=", raw)]
    plain, tech, seen = [], [], set()
    hints = verapdf_hints()
    for clause, msg in found:
        tech.append(f"ISO 19005 §{clause}: {msg}")
        for pat, de in hints:
            if re.search(pat, msg):
                if de not in seen:
                    seen.add(de)
                    plain.append(de)
                break
    m = re.search(r"flavour=(\w+)", raw)
    return plain, list(dict.fromkeys(tech))[:12], (m.group(1) if m else "")


SCHEMA = schema_explain.Schema(MUSTANG_JAR, resolve)


def guideline_of(root):
    return text(child(root, "ExchangedDocumentContext"), "GuidelineSpecifiedDocumentContextParameter", "ID") if root is not None else ""


def bts_of(message):
    return sorted(set(re.findall(r"\bBT-\d+\b", message or "")), key=lambda b: int(b[3:]))


def apply_rule(out, rule_id):
    r = rule(rule_id) if rule_id else None
    if r:
        out.update(title=r.get("t", ""), text=r.get("e", ""), fix=r.get("f", ""))
    return bool(r)


def fx_generic(out, t):
    """Generische Factur-X-Schemaregeln (FX-SCH-*)."""
    name = out["field"] or _("eine Angabe")
    nm = names()
    if "is not allowed" in t:
        out.update(title=_("Unzulässiger Wert"),
                   text=_("Im Feld „{name}“ steht ein Wert, der hier nicht erlaubt ist – meist ein Code, der nicht in der festgelegten Liste steht, oder eine Angabe, die das gewählte Profil nicht kennt.", name=name),
                   fix=_("Den Wert im Rechnungsprogramm korrigieren – erlaubt sind nur genormte Codes, z. B. „EUR“ für Euro, „DE“ für Deutschland oder „H87“ für Stück."))
    elif "must occur exactly 1" in t or "must occur at least" in t:
        out.update(title=_("Pflichtangabe fehlt"), text=_("Die Angabe „{name}“ fehlt, ist aber vorgeschrieben.", name=name),
                   fix=_("Die fehlende Angabe im Rechnungsprogramm ergänzen."))
        ms = re.search(r"Element '(?:\w+:)?(\w+)'", t)
        if ms:
            out["text"] = _("Die Angabe „{sub}“ fehlt (Bereich: {name}), ist aber vorgeschrieben – oder sie kommt mehr als einmal vor.",
                            sub=nm.get(ms.group(1)) or ms.group(1), name=name)
    elif "at maximum" in t:
        ms = re.search(r"'(?:\w+:)?(\w+)'", t)
        sub = (nm.get(ms.group(1)) or ms.group(1)) if ms else name
        out.update(title=_("Angabe kommt zu oft vor"), text=_("„{sub}“ steht mehrfach in der Rechnung, erlaubt ist hier nur ein Eintrag (Bereich: {name}).", sub=sub, name=name),
                   fix=_("Doppelte Angabe im Rechnungsprogramm entfernen."))
    elif "Attribute" in t:
        ms = re.search(r"Attribute '@?(\w+)'", t)
        sub = (nm.get("@" + ms.group(1)) or ms.group(1)) if ms else _("Zusatzangabe")
        out.update(title=_("Zusatzangabe fehlt"), text=_("Beim Feld „{name}“ fehlt die Zusatzangabe „{sub}“ (z. B. Währung oder Art der Kennung).", name=name, sub=sub),
                   fix=_("Das Rechnungsprogramm muss diese Zusatzangabe mitschreiben – ggf. beim Hersteller melden."))
    return "title" in out


def generic_syntax(out, code):
    """Rund 1.200 gleichartige Syntaxregeln („Feld X soll nicht vorkommen“) bekommen einen gemeinsamen Text."""
    if not re.match(r"(UBL-CR|CII-SR|CII-DT)-", code or ""):
        return False
    out.update(title=_("Feld ist im Standard nicht vorgesehen"),
               text=_("Die Rechnung enthält eine Angabe, die die Norm EN 16931 an dieser Stelle nicht vorsieht. Sie führt nicht zur Ablehnung, wird von Empfängern aber meist ignoriert."),
               fix=_("Die Angabe weglassen oder an der vorgesehenen Stelle übermitteln."))
    return True


def translate(item, xml_root, xr_target, xml_bytes):
    sev = item.tag  # error | warning | notice | fatal | exception
    msg = re.sub(r"<stacktrace>.*", "", item.text or "", flags=re.S).strip()
    section = item.get("type", "")
    steps = parse_location(item.get("location", ""))
    m = re.search(r"\[ID ([^\]]+)\]", msg)
    rule_id = m.group(1).strip() if m else None
    orig = re.sub(r"\s*\[ID [^\]]+\]\s*from\s+\S+\)?\s*$", "", msg)
    orig = re.sub(r"^\[[A-Z0-9_-]+\]-?\s*", "", orig).replace(" (still status warning)", "")
    out = {"sev": "error" if sev in ("error", "fatal", "exception") else sev, "group": "main",
           "id": rule_id or (f"Mustang {section}" if section else ""), "tech": orig,
           "field": field_label(steps) if steps else "", "value": None, "sources": ["Mustang"], "bts": bts_of(msg)}
    if steps:
        v = resolve(xml_root, steps)
        if v:
            out["value"] = v[:160]
    if section == "27" and not xr_target:
        out["group"], out["sev"] = "xrechnung", "notice"
    if rule_id and "BR-FR" in rule_id:
        out["group"] = "france"
    if apply_rule(out, rule_id) or generic_syntax(out, rule_id):
        return out
    if "Unsupported XR version" in msg:
        out.update(title=_("XRechnung-Variante von Mustang nicht geprüft"),
                   text=_("Mustang kennt diese XRechnung-Variante nicht und hat ihre Zusatzregeln nicht geprüft. Dafür ist die offizielle KoSIT-Prüfung maßgeblich."), fix="")
        return out
    if rule_id and rule_id.startswith("FX-SCH") and fx_generic(out, msg):
        return out

    if section in ("1", "5", "8", "9", "10", "22") and (sx := schema_explain.wellformed(xml_bytes, SCHEMA.area)):
        out.update(title=sx["title"], text=sx["text"], fix=sx["fix"], tech=sx["tech"], field=sx["field"], value=sx["value"])
    elif (section in ("1", "5", "8", "10") and sev == "fatal") or section == "20":
        out.update(title=_("Datei nicht lesbar"), text=_("Die Datei ist keine lesbare PDF- oder XML-Datei (oder zu groß/zu klein)."),
                   fix=_("Die Original-Rechnung erneut exportieren bzw. herunterladen."))
    elif section == "7":
        out.update(title=_("PDF beschädigt"), text=_("Die PDF-Datei ist beschädigt oder nicht korrekt aufgebaut und lässt sich nicht vollständig lesen."),
                   fix=_("Die Rechnung erneut aus dem Rechnungsprogramm erzeugen."))
    elif section == "17" and "XMP" in msg:
        out.update(title=_("Keine E-Rechnungs-Kennzeichnung"), text=_("In den Dokument-Eigenschaften der PDF fehlt der Vermerk, dass es sich um eine ZUGFeRD/Factur-X-Rechnung handelt."),
                   fix=_("Die Rechnung mit einem ZUGFeRD-fähigen Programm erzeugen."))
    elif section == "17" and "UBL" in msg:
        out.update(title=_("Falsches Datenformat eingebettet"), text=_("In der PDF steckt eine Rechnung im UBL-Format. ZUGFeRD/Factur-X erlaubt in der PDF nur das CII-Format."),
                   fix=_("Die UBL-Datei separat versenden oder als CII-Variante einbetten lassen."))
    elif section in ("11", "12", "13", "14", "15", "16", "19", "21", "28"):
        what = {"11": _("Die Angabe des Profils"), "12": _("Die Angabe des Profils"), "13": _("Die Dokumentart"), "14": _("Die Dokumentart"),
                "15": _("Die Versionsnummer"), "16": _("Die Versionsnummer"), "19": _("Der Name der eingebetteten Datei"),
                "21": _("Der Name der eingebetteten Datei"), "28": _("Der gesamte Kennzeichnungsblock")}[section]
        bad = _("fehlt") if "not found" in msg else (_("ist nicht lesbar") if section == "28" else _("ist ungültig"))
        out.update(title=_("Kennzeichnung in der PDF fehlerhaft"),
                   text=_("Die PDF beschreibt in ihren Eigenschaften, welche E-Rechnung sie enthält. {what} {bad}.", what=what, bad=bad),
                   fix=_("Die PDF neu mit einem ZUGFeRD-fähigen Programm erzeugen; Nachbearbeiten (z. B. Drucken als PDF, Zusammenfügen) zerstört diese Angaben oft."))
    elif section == "18" and (sx := SCHEMA.explain(msg, xml_bytes, xml_root, guideline_of(xml_root))):
        out.update(title=sx["title"], text=sx["text"], fix=sx["fix"], tech=sx["tech"])
        out["field"] = sx["field"] or out["field"]
        out["value"] = sx["value"] or out["value"]
    elif section == "18":
        out.update(title=_("Aufbau der Rechnungsdaten fehlerhaft"), text=_("Die eingebetteten Rechnungsdaten sind nicht so aufgebaut, wie der Standard es vorschreibt."),
                   fix=_("Das ist meist ein Fehler im Rechnungsprogramm – an den Hersteller bzw. den Rechnungssteller melden."))
    elif section in ("22", "9"):
        out.update(title=_("Rechnungsdaten nicht lesbar"), text=_("Die Rechnungsdaten konnten nicht ausgewertet werden, vermutlich sind sie beschädigt."),
                   fix=_("Die Rechnung neu erzeugen lassen."))
    elif section == "25":
        out.update(title=_("Unbekannte Profil-Kennung"),
                   text=_("Die Rechnung gibt an, nach welchem Profil sie aufgebaut ist – diese Kennung ist aber keine gültige (oft eine veraltete Vorabversion von Factur-X/ZUGFeRD)."),
                   fix=_("Rechnungsprogramm aktualisieren, damit eine aktuelle Profil-Kennung verwendet wird."),
                   value=msg.split("type", 1)[-1].strip(), field=_("Profil-Kennung"))
    elif section == "26":
        out.update(title=_("Keine prüfbaren Rechnungsdaten"), text=_("In den Rechnungsdaten wurde nichts gefunden, worauf die Prüfregeln passen – sie sind zu unvollständig oder in einem unbekannten Format."),
                   fix=_("Prüfen, ob wirklich eine E-Rechnung (ZUGFeRD/XRechnung) vorliegt."))
    elif section == "10":
        mm = re.search(r"Payable total in XML is ([\d.-]+), but calculated total is ([\d.-]+)", msg)
        txt = (_("Der angegebene Zahlbetrag ({a}) passt nicht zu dem, was sich aus den Positionen, Rabatten und Steuern ergibt ({b}).",
                 a=fmt_money(mm.group(1), ""), b=fmt_money(mm.group(2), "")) if mm
               else _("Beim Nachrechnen der Beträge (Positionen, Steuern, Summen) ergibt sich ein Unterschied."))
        out.update(title=_("Summen passen nicht zusammen"), text=txt, fix=_("Beträge und Rundung im Rechnungsprogramm prüfen."))
    elif section == "23":
        out.update(title=_("PDF ist nicht im Archivformat"), text="", fix="")
    else:
        out.update(title=_("Regel verletzt") if out["sev"] == "error" else _("Hinweis"), text=orig or msg, fix="")
    return out


# ---------------------------------------------------------------- KoSIT-Befunde

def translate_kosit(m, xml_root):
    code = m["code"]
    steps = parse_location(m["location"])
    sev = {"error": "error", "fatal": "error", "warning": "warning"}.get(m["level"], "notice")
    tech = re.sub(r"^\[[A-Z0-9_-]+\]\s*-?\s*", "", m["text"])
    out = {"sev": sev, "group": "main", "id": code or "KoSIT", "tech": tech, "field": field_label(steps) if steps else "",
           "value": None, "sources": ["KoSIT"], "bts": bts_of(m["text"])}
    v = resolve(xml_root, steps) if steps else None
    if v:
        out["value"] = v[:160]
    if apply_rule(out, code) or generic_syntax(out, code):
        return out
    if not code:
        out.update(title=_("Aufbau der Rechnungsdaten fehlerhaft"), text=_("Die Rechnungsdaten sind nicht so aufgebaut, wie der Standard es vorschreibt."),
                   fix=_("Das ist meist ein Fehler im Rechnungsprogramm – an den Hersteller bzw. den Rechnungssteller melden."))
    else:
        out.update(title=_("Regel verletzt") if sev == "error" else _("Hinweis"), text=tech, fix="")
    return out


# ---------------------------------------------------------------- Zusatzprüfung

def missing_payment_info(root):
    """BR-CO-25 der EN 16931: Ist ein Betrag zu zahlen, muss ein Fälligkeitsdatum (BT-9) oder eine Zahlungsbedingung (BT-20) da sein.

    Die offiziellen EN-16931-Regeln enthalten diese Regel nicht, Mustang prüft sie nur im Profil EXTENDED."""
    kind = lname(root.tag)
    if kind == "CrossIndustryInvoice":
        stl = child(root, "SupplyChainTradeTransaction", "ApplicableHeaderTradeSettlement")
        due = text(stl, "SpecifiedTradeSettlementHeaderMonetarySummation", "DuePayableAmount")
        terms = [c for c in (stl if stl is not None else []) if lname(c.tag) == "SpecifiedTradePaymentTerms"]
        present = any(text(t, "Description") or text(t, "DueDateDateTime", "DateTimeString") for t in terms)
    elif kind in ("Invoice", "CreditNote"):
        due = text(root, "LegalMonetaryTotal", "PayableAmount")
        present = bool(text(root, "DueDate") or text(root, "PaymentTerms", "Note")
                       or any(text(c, "PaymentDueDate") for c in root if lname(c.tag) == "PaymentMeans"))
    else:
        return False
    try:
        return Decimal(due) > 0 and not present
    except (InvalidOperation, TypeError):
        return False


def is_credit_note(root):
    if lname(root.tag) == "CreditNote":
        return True
    return text(child(root, "ExchangedDocument"), "TypeCode") in ("381", "396")


def extra_checks(root):
    if root is None or not missing_payment_info(root):
        return []
    source = _("Zusatzprüfung")
    # Bei Gutschriften nur ein Hinweis: Der Betrag fließt an den Käufer, und das offizielle CEN-Muster erfüllt die Regel selbst nicht.
    out = {"sev": "warning" if is_credit_note(root) else "error", "group": "main", "id": "BR-CO-25", "field": "", "value": None, "sources": [source], "bts": ["BT-9", "BT-20"], "part": "xml",
           "tech": _("EN 16931, Regel BR-CO-25: Die offiziellen Prüfregeln enthalten diese Regel nicht, deshalb prüft sie dieses Tool zusätzlich.")}
    apply_rule(out, "BR-CO-25")
    return [out]


SEV_RANK = {"error": 0, "warning": 1, "notice": 2}


def merge(problems):
    """Gleiche Regel wird einmal gezeigt. Mehrere Stellen derselben Engine zählen, gleiche Stellen beider Engines nicht doppelt."""
    merged = {}
    for p in problems:
        key = (p["group"], p["id"], p.get("title"))
        src = p["sources"][0]
        if key not in merged:
            merged[key] = {**p, "fields": [], "values": [], "counts": {}}
        m = merged[key]
        if SEV_RANK.get(p["sev"], 2) < SEV_RANK.get(m["sev"], 2):
            m["sev"] = p["sev"]
        m["counts"][src] = m["counts"].get(src, 0) + 1
        if src not in m["sources"]:
            m["sources"].append(src)
        if p["field"] and p["field"] not in m["fields"]:
            m["fields"].append(p["field"])
        if p["value"] and p["value"] not in m["values"]:
            m["values"].append(p["value"])
        m["bts"] = sorted(set(m["bts"]) | set(p["bts"]), key=lambda b: int(b[3:]))
    out = list(merged.values())
    for p in out:
        p["count"] = max(p.pop("counts").values())
        p.pop("field", None)
        p.pop("value", None)
        p["fields"], p["values"] = p["fields"][:6], p["values"][:6]
        if p["count"] > 1 and p["id"].startswith("FX-SCH") and p.get("title") == _("Unzulässiger Wert"):
            p["text"] = _("In mehreren Feldern steht ein Wert, der hier nicht erlaubt ist – meist ein Code, der nicht in der festgelegten Liste steht, oder eine Angabe, die das gewählte Profil nicht kennt.")
    return out


# ---------------------------------------------------------------- Bericht

KOSIT_TECHNICAL = "technical"


def build_report(report, xml_bytes, is_pdf, duration, kosit):
    """kosit: None (kein Szenario), KOSIT_TECHNICAL (Engine ausgefallen) oder Ergebnis von run_kosit."""
    xml_root = None
    if xml_bytes:
        try:
            xml_root = ET.fromstring(xml_bytes)
        except ET.ParseError:
            xml_root = None
    inv = summarize(xml_root)
    xr_target = "xrechnung" in (inv.get("guideline") or "").lower()

    pdf_el, xml_el = report.find("pdf"), report.find("xml")
    items = []
    for part in (pdf_el, xml_el, report):
        msgs = part.find("messages") if part is not None else None
        if msgs is not None:
            items.extend((part.tag, it) for it in msgs)

    no_xml = any(it.tag == "exception" and "could not be extracted" in (it.text or "") for _p, it in items)
    pdfa_fail = any(it.get("type") == "23" for _p, it in items)

    problems = []
    for part, it in items:
        if it.tag == "exception" and "could not be extracted" in (it.text or ""):
            continue
        if no_xml and part == "pdf" and it.get("type") in ("11", "12", "13", "14", "15", "16", "17", "19", "21"):
            continue  # bei PDFs ohne eingebettete Rechnung nur ein Folgefehler
        p = translate(it, xml_root, xr_target, xml_bytes)
        p["part"] = part
        if it.get("type") == "23":
            plain, tech, flavour = verapdf_findings(pdf_el)
            level = {"1": "PDF/A-1", "2": "PDF/A-2", "3": "PDF/A-3"}.get(flavour[:1], "")
            p["text"] = _("Eine ZUGFeRD-Rechnung muss als PDF/A-3 vorliegen – das ist ein Archivformat, das sicherstellt, dass die Datei in zehn Jahren noch genauso aussieht.")
            if level and level != "PDF/A-3":
                p["text"] += " " + _("Diese Datei ist höchstens als {level} gekennzeichnet.", level=level)
            p["bullets"] = plain[:6]
            p["fix"] = _("Die PDF direkt aus dem Rechnungsprogramm als ZUGFeRD exportieren und nicht nachträglich bearbeiten, drucken oder zusammenfügen.")
            p["tech"] = "\n".join(tech) or p["tech"]
        problems.append(p)

    mustang_xml_errors = {p["id"] for p in problems if p["sev"] == "error" and p["part"] != "pdf" and p["group"] == "main"}
    kosit_ran = isinstance(kosit, dict)
    kosit_errors = set()
    if kosit_ran:
        for m in kosit["messages"]:
            p = translate_kosit(m, xml_root)
            p["part"] = "kosit"
            # KoSIT stuft Regeln je Szenario über customLevel ab und trägt das erst in die Bewertung ein, nicht ins Level der
            # Meldung. Bei akzeptierter Rechnung ist deshalb keine Meldung blockierend.
            if p["sev"] == "error" and kosit["valid"]:
                p["sev"] = "warning"
            if p["sev"] == "error":
                kosit_errors.add(p["id"])
            problems.append(p)

    # Widerspruch zwischen den Engines: sichtbar machen; bei XRechnung gilt KoSIT für Regeln, Mustang für Rechnen und PDF
    conflict = None
    if kosit_ran and kosit["valid"] and mustang_xml_errors:
        if xr_target:
            for p in problems:
                if p["sev"] == "error" and p["part"] != "pdf" and p["part"] != "kosit" and p["id"] != "Mustang 10" and p["id"] not in kosit_errors:
                    p["sev"] = "warning"
            conflict = _("Die Engines sind sich uneinig: Die offizielle KoSIT-Prüfung akzeptiert diese XRechnung, Mustang meldet Regelverstöße. Für XRechnungen ist KoSIT maßgeblich, die Meldungen stehen deshalb als Hinweise im Bericht.")
        else:
            conflict = _("Die Engines sind sich uneinig: Mustang meldet Fehler, die offizielle KoSIT-Prüfung akzeptiert die Rechnung. Die Fehler bleiben zur Sicherheit im Bericht, bitte fachlich bewerten.")
    elif kosit_ran and not kosit["valid"] and not mustang_xml_errors:
        conflict = _("Die Engines sind sich uneinig: Die offizielle KoSIT-Prüfung lehnt die Rechnung ab, Mustang akzeptiert sie. Die Rechnung gilt deshalb als nicht gültig, bitte die Befunde fachlich bewerten.")

    if kosit is not None and not any(p["id"] == "BR-CO-25" for p in problems):
        extra = extra_checks(xml_root)
        problems.extend(extra)
        if not conflict and any(p["sev"] == "error" for p in extra) and not mustang_xml_errors and not kosit_errors:
            conflict = _("Mustang und KoSIT akzeptieren die Rechnung, weil ihre Regelwerke BR-CO-25 für dieses Format nicht enthalten. Die Norm EN 16931 verlangt die Angabe aber, deshalb gilt die Rechnung hier als nicht gültig.")

    sums = money_overview(xml_root)
    if sums:
        for p in problems:
            if re.match(r"BR-CO-1[0-8]$|BR-S-0[89]$", p["id"] or "") or p["id"] == "Mustang 10":
                p["value"] = None
                p["sums"] = sums
    if any(p["id"] == "Mustang 25" for p in problems):
        problems = [p for p in problems if not (p["id"].startswith("FX-SCH") and p["field"].endswith(_("Profil-Kennung")))]

    parts_by_key = {}
    for p in problems:
        parts_by_key.setdefault((p["group"], p["id"], p.get("title")), set()).add(p["part"])
    problems = merge(problems)
    for p in problems:
        p["parts"] = sorted(parts_by_key[(p["group"], p["id"], p.get("title"))])
        p.pop("part", None)

    errors = [p for p in problems if p["group"] == "main" and p["sev"] == "error"]
    warnings = [p for p in problems if p["group"] == "main" and p["sev"] != "error"]
    xrechnung = [p for p in problems if p["group"] == "xrechnung"]
    france = [p for p in problems if p["group"] == "france"]

    status_el = report.find("summary")
    mustang_valid = status_el is not None and status_el.get("status") == "valid"
    downgraded = conflict is not None and kosit_ran and kosit["valid"] and xr_target
    valid = (mustang_valid or downgraded) and not errors

    def step(key, label, ok, detail=""):
        return {"key": key, "label": label, "ok": ok, "detail": detail}

    xml_errs = [p for p in errors if "pdf" not in p["parts"]]
    meta_errs = [p for p in errors if "pdf" in p["parts"] and p["id"] != "Mustang 23"]
    schema_title = _("Rechnungsdaten beschädigt")
    schema_errs = [p for p in xml_errs if p["id"] == "Mustang 18" or p.get("title") == schema_title or p["id"] == "KoSIT"]
    rule_errs = [p for p in xml_errs if p not in schema_errs]
    arith = [p for p in problems if p["id"] == "Mustang 10" or (p["id"] or "").startswith("BR-CO")]
    steps = []
    if is_pdf:
        steps.append(step("pdfa", _("Archivformat PDF/A-3"), None if pdf_el is None else not pdfa_fail))
        steps.append(step("embed", _("Rechnungsdaten eingebettet"), not no_xml and xml_bytes is not None))
        if not no_xml:
            steps.append(step("meta", _("E-Rechnungs-Kennzeichnung"), not meta_errs))
    if not no_xml:
        steps.append(step("schema", _("Aufbau nach Standard"), not schema_errs))
        steps.append(step("rules", _("Pflichtangaben & Regeln (EN 16931)"), not rule_errs if not schema_errs else None))
        steps.append(step("math", _("Beträge rechnerisch korrekt"),
                          not any(p["sev"] == "error" for p in arith) if not schema_errs else None,
                          _("mit Abweichungen") if arith and not any(p["sev"] == "error" for p in arith) else ""))
        if kosit_ran:
            steps.append(step("kosit", _("Offizielle Referenzprüfung (KoSIT)"), kosit["valid"], kosit["scenario"]))
        elif kosit == KOSIT_TECHNICAL:
            steps.append(step("kosit", _("Offizielle Referenzprüfung (KoSIT)"), None, _("technisch nicht möglich")))
        else:
            steps.append(step("kosit", _("Offizielle Referenzprüfung (KoSIT)"), None, _("nicht anwendbar auf dieses Profil")))
    if xrechnung and not xr_target:
        steps.append(step("xr", _("Zusätzlich behördentauglich (XRechnung)"), False, _("{n} Punkte", n=len(xrechnung))))
    elif not no_xml and inv and not xr_target:
        steps.append(step("xr", _("Zusätzlich behördentauglich (XRechnung)"), True))

    legal = None
    if inv.get("profile") in ("MINIMUM", "BASIC WL"):
        legal = _("Das Profil {p} enthält keine vollständigen Rechnungsangaben. In Deutschland gilt so eine Datei steuerlich nicht als E-Rechnung, sondern nur als „sonstige Rechnung“. Für die E-Rechnungspflicht mindestens das Profil BASIC, besser EN 16931, verwenden.", p=inv["profile"])

    if no_xml:
        verdict = "none"
        headline = _("Keine E-Rechnung gefunden")
        lead = _("Diese PDF enthält keine eingebetteten Rechnungsdaten. Sie ist damit eine normale PDF-Rechnung und keine E-Rechnung nach ZUGFeRD/Factur-X.")
    elif valid:
        verdict = "warn" if (warnings or legal) else "ok"
        headline = _("Gültige E-Rechnung")
        if inv.get("type") in (_("Bestellung"), _("Bestellbestätigung"), _("Lieferavis")):
            headline = _("Gültiges Dokument ({t})", t=inv["type"])
        if inv.get("profile") == "ZUGFeRD 1.0":
            legal = _("Die Rechnung nutzt noch ZUGFeRD 1.0. Diese Version entspricht nicht der europäischen Norm EN 16931 und wird für die deutsche E-Rechnungspflicht nicht mehr anerkannt. Das Rechnungsprogramm sollte auf ZUGFeRD 2.x umgestellt werden.")
            verdict = "warn"
        lead = _("Die Rechnung erfüllt den Standard EN 16931 – sie kann so verschickt und verarbeitet werden.")
        if legal:
            lead = _("Technisch in Ordnung – aber beachte den Hinweis zum Profil.")
        elif warnings:
            lead += " " + (_("Es gibt einen Hinweis, der aber nicht zur Ablehnung führt.") if len(warnings) == 1
                           else _("Es gibt {n} Hinweise, die aber nicht zur Ablehnung führen.", n=len(warnings)))
    else:
        verdict = "fail"
        headline = _("Nicht gültig")
        lead = (_("Die Prüfung hat ein Problem gefunden. Eine solche Rechnung kann vom Empfänger abgelehnt werden.") if len(errors) == 1
                else _("Die Prüfung hat {n} Probleme gefunden. Eine solche Rechnung kann vom Empfänger abgelehnt werden.", n=len(errors)))

    return {"verdict": verdict, "headline": headline, "lead": lead, "legal": legal, "conflict": conflict, "invoice": inv,
            "steps": steps, "errors": errors, "warnings": warnings, "xrechnung": xrechnung, "france": france,
            "duration": round(duration, 1)}


def simple_report(headline, lead):
    return {"verdict": "none", "headline": headline, "lead": lead, "steps": [], "errors": [], "warnings": [],
            "xrechnung": [], "france": [], "invoice": {}}
