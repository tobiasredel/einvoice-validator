"""Verständliche Erklärung von Schema-Fehlern (Mustang-Abschnitt 18) in CII-Rechnungen.

Mustang meldet nur den ersten Aufbaufehler, als rohe Xerces-Meldung mit Zeile/Spalte. Hier wird
die Stelle im XML gesucht (→ Fundstelle „Position 1 › …“) und mit dem CII-Schema D16B aus dem
Mustang-Jar abgeglichen (Factur-X/ZUGFeRD-Profilschema, gegen das auch Mustang prüft): unbekanntes Feld, falscher Bereich, falsche Reihenfolge, fehlende
Pflichtangabe, falsches Zahlenformat, unerlaubter Code.
"""
import re
import zipfile
import xml.etree.ElementTree as ET
from xml.parsers import expat

from i18n import _, names

XS = "{http://www.w3.org/2001/XMLSchema}"
XSD_DIR = "schema/ZF_250/{p}/FACTUR-X_{f}"
XSD_FILES = (".xsd", "_urn_un_unece_uncefact_data_standard_ReusableAggregateBusinessInformationEntity_100.xsd")
PROFILES = ("MINIMUM", "BASIC-WL", "BASIC", "EN16931", "EXTENDED")


def profile_for(guideline):
    """Profilschema passend zur Profil-Kennung (BT-24); im Zweifel EN 16931."""
    g = (guideline or "").lower()
    if "extended" in g or "#conformant#" in g:
        return "EXTENDED"
    if "minimum" in g:
        return "MINIMUM"
    if "basicwl" in g:
        return "BASIC-WL"
    if "basic" in g:
        return "BASIC"
    return "EN16931"

# Strukturelemente, die in names_de.json bewusst leer sind (für Fundstellen), hier aber einen Namen brauchen
def area_names():
    """Strukturelemente, die in den Namenslisten bewusst leer sind, für Fundstellen aber einen Namen brauchen."""
    return {
        "CrossIndustryInvoice": _("Rechnung"),
        "ExchangedDocumentContext": _("Profil-Angaben"),
        "ExchangedDocument": _("Rechnungskopf"),
        "SupplyChainTradeTransaction": _("Rechnungsinhalt"),
        "ApplicableHeaderTradeAgreement": _("Vertragsangaben (Kopf)"),
        "ApplicableHeaderTradeDelivery": _("Lieferangaben (Kopf)"),
        "ApplicableHeaderTradeSettlement": _("Abrechnungsangaben (Kopf)"),
        "IncludedSupplyChainTradeLineItem": _("Position"),
        "SpecifiedLineTradeAgreement": _("Preisangaben der Position"),
        "SpecifiedLineTradeDelivery": _("Lieferangaben der Position"),
        "SpecifiedLineTradeSettlement": _("Abrechnungsangaben der Position"),
    }

def xsd_type(t):
    return {
        "decimal": _("Zahl"), "integer": _("ganze Zahl"), "dateTime": _("Datum mit Uhrzeit"), "date": _("Datum"),
        "boolean": _("Ja/Nein-Wert (true/false)"), "base64Binary": _("Base64-kodierte Datei"), "token": _("Text"),
        "normalizedString": _("Text"), "string": _("Text"), "anyURI": _("Adresse (URI)"),
    }.get(t, t)


def _local(q):
    return (q or "").split(":")[-1]


def _walk(node, seq, in_choice):
    for c in node:
        if c.tag == XS + "element":
            name = c.get("name") or _local(c.get("ref"))
            seq.append({"name": name, "min": 0 if in_choice else int(c.get("minOccurs", "1")),
                        "max": c.get("maxOccurs", "1"), "type": _local(c.get("type"))})
        elif c.tag == XS + "choice":
            _walk(c, seq, True)
        elif c.tag not in (XS + "annotation", XS + "attribute"):
            _walk(c, seq, in_choice)


def load(jar, profile):
    """Liest die CII-Typen eines Profils aus dem Mustang-Jar: Typname → geordnete Liste der Kindelemente."""
    types, roots = {}, {}
    try:
        z = zipfile.ZipFile(jar)
    except (OSError, zipfile.BadZipFile):
        return types, roots
    for f in XSD_FILES:
        try:
            root = ET.fromstring(z.read(XSD_DIR.format(p=profile, f=profile.replace("-", "")) + f))
        except (KeyError, ET.ParseError):
            continue
        for el in root.findall(XS + "element"):
            roots[el.get("name")] = _local(el.get("type"))
        for ct in root.findall(XS + "complexType"):
            seq = []
            _walk(ct, seq, False)
            types[ct.get("name")] = seq
    return types, roots


class Schema:
    def __init__(self, jar, resolve):
        self.resolve = resolve
        self.profiles = {}
        for prof in PROFILES:
            types, roots = load(jar, prof)
            parents, users = {}, {}  # Elementname → Bereiche, in denen es vorkommen darf
            for seq in types.values():
                for e in seq:
                    users.setdefault(e["type"], []).append(e["name"])
            for t, seq in types.items():
                for e in seq:
                    for u in users.get(t, []):
                        parents.setdefault(e["name"], []).append(u)
            self.profiles[prof] = (types, roots, parents)
        # alle Feldnamen über alle Profile: unbekannt = in keinem Profil vorhanden
        self.everywhere = {e["name"] for t, r, _ in self.profiles.values() for seq in t.values() for e in seq}

    def use(self, profile):
        self.profile = profile
        self.types, self.roots, self.parents = self.profiles.get(profile) or ({}, {}, {})
        self.all = {e["name"] for seq in self.types.values() for e in seq} | set(self.roots)

    # ------------------------------------------------------------ Helfer

    def lab(self, n):
        de = names().get(n) or area_names().get(n)
        return _("„{name}“ ({tag})", name=de, tag=n) if de else _("„{name}“", name=n)

    def area(self, steps):
        """'Position 2 › Abrechnungsangaben der Position › Umsatzsteuer' – mit Namen auch für Strukturelemente."""
        parts, line = [], None
        for _attr, n, idx in (steps or [])[1:]:
            if n == "IncludedSupplyChainTradeLineItem":
                line = idx
                continue
            if n == "SupplyChainTradeTransaction":
                continue
            de = names().get(n) or area_names().get(n) or n
            if not parts or parts[-1] != de:
                parts.append(de)
        label = " › ".join(parts[-3:])
        if line:
            pos = _("Position {n}", n=line)
            label = f"{pos} › {label}" if label else pos
        return label or _("Rechnung")

    def type_at(self, steps):
        if not steps:
            return None
        t = self.roots.get(steps[0][1])
        for _attr, name, _idx in steps[1:]:
            t = next((e["type"] for e in self.types.get(t, []) if e["name"] == name), None)
            if t is None:
                return None
        return t

    def element(self, root, steps):
        if root is None or not steps:
            return None
        el = root
        for _attr, name, idx in steps[1:]:
            m = [c for c in el if c.tag.rsplit("}", 1)[-1] == name]
            if len(m) < idx:
                return None
            el = m[idx - 1]
        return el

    @staticmethod
    def locate(xml_bytes, line, col):
        """Pfad (Name, Index) zum Element an Zeile/Spalte der Xerces-Meldung."""
        target = (line, col)
        p = expat.ParserCreate(namespace_separator=" ")
        stack, counts, best = [], [{}], [None]

        def pos():
            return (p.CurrentLineNumber, p.CurrentColumnNumber + 1)

        def start(name, attrs):
            n = name.split(" ")[-1]
            c = counts[-1]
            c[n] = c.get(n, 0) + 1
            stack.append((False, n, c[n]))
            counts.append({})
            if pos() < target:
                best[0] = list(stack)

        def end(name):
            if pos() < target:
                best[0] = list(stack)
            stack.pop()
            counts.pop()

        p.StartElementHandler = start
        p.EndElementHandler = end
        try:
            p.Parse(xml_bytes, True)
        except expat.ExpatError:
            pass
        return best[0]

    # ------------------------------------------------------------ Erklärung

    def explain(self, msg, xml_bytes, xml_root, guideline=""):
        """Mustang-Meldung → {title, text, fix, field, value, tech} oder None."""
        self.use(profile_for(guideline))
        clean = re.sub(r'"[^"]*":', "", msg)
        clean = re.sub(r"\b\w+:(?=[A-Z]\w*['},])", "", clean)  # Präfixe wie ram:Name
        mpos = re.search(r"lineNumber: (\d+); columnNumber: (\d+); (.*)", clean, re.S)
        if not mpos:
            return None
        line, col, core = int(mpos.group(1)), int(mpos.group(2)), mpos.group(3).strip()
        steps = self.locate(xml_bytes, line, col) if xml_bytes else None
        out = {"tech": core + "\n" + _("(Zeile {line}, Spalte {col} der Rechnungs-XML)", line=line, col=col), "field": "", "value": None}
        if steps:
            out["field"] = self.area(steps)
            v = self.resolve(xml_root, steps) if xml_root is not None else None
            if v:
                out["value"] = v[:160]
        hint = " " + _("Der Aufbau wird nur bis zum ersten Fehler geprüft; nach der Korrektur können weitere Aufbaufehler auftauchen. Die inhaltlichen Regeln (EN 16931) werden erst geprüft, wenn der Aufbau stimmt.")
        dev = _("An den Hersteller des Rechnungsprogramms bzw. den Rechnungssteller melden – mit Fundstelle und technischen Details.")
        lab = self.lab
        either = lambda items: _(" bzw. ").join(lab(e) for e in items)

        def done(title, body, fix=None):
            out.update(title=title, text=body + hint, fix=(fix + " " + dev) if fix else dev)
            return out

        m = re.search(r"cvc-complex-type\.2\.4\.([abd]):", core)
        if m and steps:
            kind = m.group(1)
            mf = re.search(r"starting with element '\{?(\w+)\}?'", core)
            me = re.search(r"One of '\{(.*?)\}' is expected", core)
            found = mf.group(1) if mf else None
            expected = [e.strip() for e in (me.group(1) if me else "").split(",") if e.strip()]
            if kind == "b":
                parent_steps, found = steps, None
            else:
                parent_steps = steps[:-1]
                found = found or steps[-1][1]
            ptype = self.type_at(parent_steps)
            seq = self.types.get(ptype, [])
            order = [e["name"] for e in seq]
            area = self.area(parent_steps)
            parent_el = self.element(xml_root, parent_steps)
            present = [c.tag.rsplit("}", 1)[-1] for c in parent_el] if parent_el is not None else []
            after = present[present.index(found) + 1:] if found in present else []
            before = present[:present.index(found)] if found in present else present

            if kind == "b":
                req = [e for e in expected if any(s["name"] == e and s["min"] > 0 for s in seq)] or expected
                return done(_("Pflichtangabe fehlt"), _("Im Bereich „{area}“ fehlt die Pflichtangabe {req}.", area=area, req=either(req[:3])),
                            _("Die fehlende Angabe ergänzen."))
            if found not in self.everywhere:
                close = [n for n in order if n.lower() == found.lower()]
                detail = (_("gemeint ist vermutlich {f} (Groß-/Kleinschreibung).", f=lab(close[0])) if close
                          else _("vermutlich ein Tippfehler oder eine herstellereigene Erweiterung."))
                return done(_("Unbekanntes Feld"),
                            _("Im Bereich „{area}“ steht das Feld „{found}“. Ein Feld mit diesem Namen gibt es im ZUGFeRD/CII-Standard nicht – {detail}", area=area, found=found, detail=detail),
                            _("Das Feld entfernen oder richtig benennen."))
            if found not in order:
                homes = list(dict.fromkeys(self.parents.get(found, [])))[:3]
                other = [p for p, (t, _r, _x) in self.profiles.items() if p != self.profile and any(e["name"] == found for e in t.get(ptype, []))]
                if other:
                    return done(_("Feld im gewählten Profil nicht erlaubt"),
                                _("Das Feld {f} im Bereich „{area}“ gibt es erst in einem umfangreicheren Profil ({other}). Die Rechnung ist aber als {profile} gekennzeichnet.",
                                  f=lab(found), area=area, other=", ".join(other), profile=self.profile),
                                _("Entweder das Feld weglassen oder die Rechnung im passenden Profil ausstellen."))
                body = _("Das Feld {f} steht im Bereich „{area}“, gehört dort aber nicht hin.", f=lab(found), area=area)
                if homes:
                    body += " " + _("Vorgesehen ist es z. B. in {homes}.", homes=", ".join(lab(h) for h in homes))
                return done(_("Feld im falschen Bereich"), body, _("Das Feld in den richtigen Bereich verschieben."))
            later = [e for e in expected if e in after]
            if later:
                return done(_("Felder in falscher Reihenfolge"),
                            _("Im Bereich „{area}“ steht {f} zu früh: {g} muss davor stehen. Der Standard schreibt die Reihenfolge der Felder fest vor.", area=area, f=lab(found), g=lab(later[0])),
                            _("Die Reihenfolge ändern: erst {a}, dann {b}.", a=lab(later[0]), b=lab(found)))
            fi = order.index(found)
            prev = next((b for b in reversed(before) if b in order), None)
            if prev and order.index(prev) > fi:
                return done(_("Felder in falscher Reihenfolge"),
                            _("Im Bereich „{area}“ steht {f} zu spät: es muss vor {g} stehen. Der Standard schreibt die Reihenfolge der Felder fest vor.", area=area, f=lab(found), g=lab(prev)),
                            _("Die Reihenfolge ändern: erst {a}, dann {b}.", a=lab(found), b=lab(prev)))
            if prev == found and seq[fi]["max"] == "1":
                return done(_("Feld kommt zu oft vor"), _("Im Bereich „{area}“ steht {f} mehrfach; erlaubt ist es dort nur einmal.", area=area, f=lab(found)),
                            _("Die doppelte Angabe entfernen."))
            req = [e for e in expected if any(s["name"] == e and s["min"] > 0 for s in seq) and e not in present]
            if req:
                return done(_("Pflichtangabe fehlt"),
                            _("Im Bereich „{area}“ fehlt {req}. Diese Angabe ist Pflicht und muss vor {f} stehen.", area=area, req=either(req[:3]), f=lab(found)),
                            _("Die fehlende Angabe ergänzen."))
            if kind == "d":
                return done(_("Feld an dieser Stelle nicht erlaubt"),
                            _("Im Bereich „{area}“ steht {f} an einer Stelle, an der kein weiteres Feld mehr folgen darf (falsche Reihenfolge oder zu oft vorhanden).", area=area, f=lab(found)),
                            _("Reihenfolge und Anzahl prüfen."))
            return done(_("Feld an falscher Stelle"),
                        _("Im Bereich „{area}“ steht {f}, an dieser Stelle wird aber {exp} erwartet.", area=area, f=lab(found), exp=_(" oder ").join(lab(e) for e in expected[:4])))

        m = re.search(r"cvc-datatype-valid\.1\.2\.\d: '(.*?)' is not a valid value for '(\w+)'", core, re.S)
        if m:
            val, typ = m.group(1), m.group(2)
            out["value"] = val[:160] or _("(leer)")
            if typ == "decimal":
                sug = ""
                if re.fullmatch(r"-?\d{1,3}(\.\d{3})*,\d+|-?\d+,\d+", val):
                    sug = " " + _("Richtig wäre {v}.", v=val.replace(".", "").replace(",", "."))
                return done(_("Zahl im falschen Format"),
                            _("Der Wert „{val}“ ist keine gültige Zahl. In E-Rechnungen stehen Zahlen ohne Tausendertrennzeichen, ohne Währungszeichen und mit Punkt als Dezimaltrennzeichen, z. B. 1234.56.", val=val) + sug,
                            _("Das Zahlenformat im Export korrigieren."))
            return done(_("Wert im falschen Format"), _("Der Wert „{val}“ ist kein gültiger Wert vom Typ {t}.", val=val, t=xsd_type(typ)))

        m = re.search(r"cvc-enumeration-valid: Value '(.*?)' is not facet-valid with respect to enumeration '\[(.*?)\]'", core, re.S)
        if m:
            val, allowed = m.group(1), [a.strip() for a in m.group(2).split(",")]
            out["value"] = val or _("(leer)")
            shown = ", ".join(allowed[:12]) + (" " + _("… ({n} Werte)", n=len(allowed)) if len(allowed) > 12 else "")
            return done(_("Unerlaubter Code"), _("Der Code „{val}“ ist hier nicht erlaubt. Zulässig sind nur Codes aus der festgelegten Liste: {shown}.", val=val, shown=shown),
                        _("Einen gültigen Code verwenden (auf Groß-/Kleinschreibung und Leerzeichen achten)."))

        m = re.search(r"cvc-(minLength|maxLength|pattern|length)-valid: Value '(.*?)' with length = '(\d+)'.*?'(\d+)'", core, re.S) \
            or re.search(r"cvc-(pattern)-valid: Value '(.*?)' is not facet-valid with respect to pattern '(.*?)'", core, re.S)
        if m:
            out["value"] = m.group(2) or _("(leer)")
            if m.group(1) == "minLength" and m.group(3) == "0":
                return done(_("Leeres Feld"), _("Das Feld ist leer, muss aber einen Wert enthalten."), _("Den Wert ergänzen oder das Feld weglassen, wenn es optional ist."))
            if m.group(1) == "maxLength":
                return done(_("Wert zu lang"), _("Der Wert ist {n} Zeichen lang, erlaubt sind höchstens {max}.", n=m.group(3), max=m.group(4)))
            if m.group(1) == "pattern":
                return done(_("Wert im falschen Format"), _("Der Wert „{val}“ entspricht nicht dem vorgeschriebenen Muster.", val=m.group(2)))
            return done(_("Wert hat falsche Länge"), _("Der Wert „{val}“ hat nicht die vorgeschriebene Länge.", val=m.group(2)))

        m = re.search(r"cvc-complex-type\.3\.2\.2: Attribute '(\w+)' is not allowed to appear in element '(\w+)'", core)
        if m:
            return done(_("Unerlaubte Zusatzangabe"), _("Beim Feld {f} steht die Zusatzangabe (Attribut) „{a}“, die dort nicht vorgesehen ist.", f=lab(m.group(2)), a=m.group(1)))
        m = re.search(r"cvc-complex-type\.4: Attribute '(\w+)' must appear on element '(\w+)'", core)
        if m:
            return done(_("Zusatzangabe fehlt"), _("Beim Feld {f} fehlt die vorgeschriebene Zusatzangabe (Attribut) „{a}“.", f=lab(m.group(2)), a=m.group(1)))
        m = re.search(r"cvc-complex-type\.2\.3: Element '(\w+)' cannot have character", core)
        if m:
            return done(_("Text an falscher Stelle"), _("Im Bereich {f} steht direkt Text. Dort sind nur Unterfelder erlaubt, der Text gehört in eines davon.", f=lab(m.group(1))))
        m = re.search(r"cvc-elt\.1(?:\.a)?: Cannot find the declaration of element '(\w+)'", core)
        if m:
            return done(_("Kein CII-Rechnungsformat"), _("Die Rechnungsdaten beginnen mit „{e}“. Das ist kein Element des CII-Standards – entweder ein anderes Format oder ein falscher Namensraum (xmlns) im Kopf der Datei.", e=m.group(1)))
        if re.search(r"must be terminated|must start and end|not allowed in prolog|must be followed|must be well-formed|XML document structures", core):
            return done(_("Rechnungsdaten beschädigt"),
                        _("Die XML ist an dieser Stelle (Zeile {line}) nicht korrekt aufgebaut – zum Beispiel ein nicht geschlossenes Feld oder ein unzulässiges Zeichen. Sie lässt sich deshalb nicht lesen.", line=line),
                        _("Die Rechnung neu exportieren."))
        return None


def expat_text(reason):
    return {
        "mismatched tag": _("Ein Feld wird mit einem anderen Namen geschlossen, als es geöffnet wurde."),
        "not well-formed (invalid token)": _("An dieser Stelle steht ein Zeichen, das in XML so nicht vorkommen darf (z. B. ein unmaskiertes „&“ oder „<“)."),
        "unclosed token": _("Ein Feld oder eine Angabe ist nicht abgeschlossen."),
        "no element found": _("Die Datei endet, bevor alle Felder geschlossen sind – sie ist vermutlich abgeschnitten."),
        "junk after document element": _("Nach dem Ende der Rechnung folgt noch weiterer Inhalt."),
        "undefined entity": _("Es wird ein Sonderzeichen-Kürzel (z. B. „&nbsp;“) verwendet, das XML nicht kennt."),
        "syntax error": _("Die Datei beginnt nicht mit gültigem XML."),
        "unclosed CDATA section": _("Ein CDATA-Abschnitt ist nicht geschlossen."),
        "XML or text declaration not at start of entity": _("Vor dem XML-Kopf (<?xml …?>) stehen noch Zeichen, z. B. Leerzeilen."),
        "duplicate attribute": _("Eine Zusatzangabe (Attribut) steht doppelt am selben Feld."),
        "unbound prefix": _("Ein Namensraum-Kürzel (z. B. „ram:“) wird benutzt, ist im Kopf aber nicht deklariert."),
    }.get(reason, _("Die XML ist an dieser Stelle nicht korrekt aufgebaut."))


def wellformed(xml_bytes, area=None):
    """Prüft, ob die XML lesbar ist. None = in Ordnung, sonst {title, text, fix, field, value, tech}."""
    if not xml_bytes:
        return None
    p = expat.ParserCreate(namespace_separator=" ")
    stack, counts = [], [{}]

    def start(name, attrs):
        n = name.split(" ")[-1]
        counts[-1][n] = counts[-1].get(n, 0) + 1
        stack.append((False, n, counts[-1][n]))
        counts.append({})

    def end(name):
        stack.pop()
        counts.pop()

    p.StartElementHandler = start
    p.EndElementHandler = end
    try:
        p.Parse(xml_bytes, True)
        return None
    except expat.ExpatError as e:
        reason = expat.ErrorString(e.code)
        line_no, col = e.lineno, e.offset
    lines = xml_bytes.decode("utf-8", "replace").splitlines() or [""]
    src = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
    body = expat_text(reason)
    at_end = line_no >= len(lines) and col >= len(src.rstrip()) - 1
    if reason in ("unclosed token", "no element found") and at_end:
        body = _("Die Datei endet mitten in der Rechnung – sie ist vermutlich beim Erzeugen oder Übertragen abgeschnitten worden.")
    if reason == "mismatched tag" and stack:
        m = re.search(r"</([\w.:-]+)", src[max(0, col - 2):])
        closed = m.group(1).split(":")[-1] if m else "?"
        body = _("Das Feld „{a}“ wird geöffnet, aber als „{b}“ geschlossen. Öffnen und Schließen müssen exakt gleich heißen.", a=stack[-1][1], b=closed)
    snippet = src[max(0, col - 50):col + 50].strip()
    return {
        "title": _("Rechnungsdaten beschädigt"),
        "text": body + " " + _("Fundstelle: Zeile {line}, Spalte {col}. Weil die Datei nicht lesbar ist, konnte nichts weiter geprüft werden.", line=line_no, col=col + 1),
        "fix": _("Die Rechnung neu erzeugen bzw. exportieren. Tritt der Fehler wieder auf, an den Hersteller des Rechnungsprogramms melden."),
        "field": (area(stack) if area and len(stack) > 1 else " › ".join(n for _x, n, _y in stack[-3:])),
        "value": snippet[:160] or None,
        "tech": f"{reason} ({line_no}:{col + 1})",
    }
