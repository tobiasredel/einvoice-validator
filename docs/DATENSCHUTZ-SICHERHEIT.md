# Datenschutz und IT-Sicherheit

Dieses Dokument beschreibt, was das Tool technisch tut, und soll die Prüfung durch Datenschutz und IT-Sicherheit erleichtern. Es ersetzt weder deren Bewertung noch eine Rechtsberatung. Ergebnisse der automatisierten Prüfung stehen in `nachweise/security-evidence.md`.

## Einordnung

- **Verarbeitete Daten:** Rechnungsinhalte, darunter personenbezogene Daten wie Namen, Anschriften, E-Mail-Adressen, Steuer-IDs und Bankverbindungen.
- **Auch ohne Speicherung ist das eine Verarbeitung im Sinne der DSGVO.** Das Unternehmen, das das Tool betreibt, ist dafür Verantwortlicher. Das Image liefert die Technik, es ist nicht selbst „DSGVO-konform“.
- **Keine Dritten:** Das Tool sendet keine Daten an externe Dienste und nutzt keine KI, keine Cloud-API und keine Telemetrie.
- **Hinweis zur Aufbewahrung:** Das Tool ist kein Archiv. Pflichten zur Aufbewahrung von Rechnungen bleiben davon unberührt.

## Datenfluss

```
Browser ──TLS──> Proxy (SSO) ──> Container
                                  1. Datei liegt in einem Ordner auf tmpfs (RAM), Rechte 0700
                                  2. Eigene Java-Prozesse prüfen die Datei und enden danach
                                  3. Bericht geht als Antwort zurück (Cache-Control: no-store)
                                  4. Ordner wird gelöscht, auch bei Fehlern und Zeitüberschreitung
```

| Ort | Was liegt dort | Wie lange |
|---|---|---|
| Container, tmpfs `/tmp` | Datei und Zwischenergebnisse | während der Prüfung, wenige Sekunden |
| Container, Arbeitsspeicher | Datei und Bericht | bis Prozess bzw. Anfrage enden |
| Container, Festplatte | nichts, das Dateisystem ist schreibgeschützt | – |
| Logs | nur Pfad, Status, Dauer | nach Log-Einstellung des Betriebs |
| Browser, Arbeitsspeicher | Dateien, Berichte, Ansichten | bis die Seite geschlossen wird |
| Browser, `localStorage` | nur die Spracheinstellung | dauerhaft |

Der **Dateiname wird nicht übertragen**, er bleibt im Browser. Damit taucht er auch in keinem Proxy-Log auf.

## Technische und organisatorische Maßnahmen

| Maßnahme | Umsetzung |
|---|---|
| Keine Speicherung | kein Volume, kein Datenbankdienst, `read_only`, Temp-Ordner nur auf tmpfs |
| Prozess-Trennung | je Datei eigene, kurzlebige Java-Prozesse, kein Daemon mit Rechnungsdaten |
| Keine Dumps | Heap- und Core-Dumps aus, `ulimit core=0`, Java-Fehlerdatei im Temp-Ordner der Prüfung |
| Logs ohne Inhalt | keine Dateinamen, keine Rechnungsdaten, Exceptions nur als Typ; die Ausgaben der Engines werden verworfen |
| Kein Netzzugriff | internes Docker-Netz bzw. NetworkPolicy; das Tool funktioniert nachweislich komplett ohne Netz |
| Minimale Rechte | non-root (UID 10001), `cap_drop: ALL`, `no-new-privileges`, `pids_limit` |
| Schutz vor XML-Angriffen | `DOCTYPE` wird vor jedem Parser abgelehnt (XXE, Entity-Bomben), nur UTF-8, UTF-16, ISO-8859-1 und ASCII sind erlaubt |
| Schutz vor PDF-Bomben | Extraktion im eigenen Prozess mit 1 GB Speicher- und 60 s Zeitlimit |
| Schutz vor manipulierten Rechnungen im Browser | Rechnungsansicht ohne Skripte, Event-Attribute und Links im `iframe sandbox` ohne `allow-scripts`; Anlagen nur als Download mit neutralem Dateityp |
| Browser-Härtung | CSP (`script-src 'self'`, `connect-src 'self'`), `no-store`, `no-referrer`, `X-Frame-Options: DENY`, keine externen Ressourcen |
| Überlastschutz | Größen-, Zeit- und Warteschlangenlimits, Antwort 503 mit `Retry-After` |
| Nachvollziehbare Herkunft | Base-Image per Digest, alle Komponenten per Version und SHA-256 festgelegt, SBOM und Schwachstellenbericht je Release |

Die Bewertung der bekannten Schwachstellen steht in `SCHWACHSTELLEN.md`.

## Was der Betreiber sicherstellen muss

1. **TLS und Anmeldung am Proxy.** Das Tool hat beides nicht.
2. **Proxy ohne Inhalts-Logs und ohne Caching,** siehe `BETRIEB.md`.
3. **Swap verschlüsseln oder abschalten.** Inhalte auf tmpfs und im Arbeitsspeicher können sonst vom Betriebssystem auf die Platte ausgelagert werden.
4. **Ausgehenden Netzverkehr sperren,** wie in den Vorlagen. Bei `docker run` mit veröffentlichtem Port ist das nicht automatisch der Fall.
5. **Host und Backups:** Das Tool legt nichts ab; die Sicherheit des Hosts bleibt aber Sache des Betreibers.
6. **Updates:** neue Images regelmäßig einspielen, siehe Schwachstellenbericht und `BETRIEB.md`.
7. **Eintrag im Verarbeitungsverzeichnis** und die übrigen Pflichten nach Bewertung durch den Datenschutz.

## Grenzen

- **Downloads:** ZIP, Excel und XML, die Nutzer selbst herunterladen, liegen danach auf deren Rechner.
- **Während der Prüfung** sind die Daten im Arbeitsspeicher und auf tmpfs unverschlüsselt. Wer root auf dem Host hat, könnte in dieser Zeit darauf zugreifen.
- **Abbruch des Servers:** Beim harten Beenden des Hauptprozesses bleibt ein Temp-Ordner bis zum Neustart des Containers im RAM. Ein tmpfs überlebt den Container nicht.
- **Eine Antwort enthält Rechnungsdaten.** Sie ist `no-store`, ein falsch konfigurierter Proxy kann sie trotzdem protokollieren.
- **Kein Prüfprotokoll:** Bewusst wird nicht festgehalten, wer was geprüft hat. Wird das gebraucht, gehört es an den Proxy.

## Grenzen der fachlichen Prüfung

- Der Bericht ist eine technische Prüfung gegen die Standards, keine steuerliche oder rechtliche Bewertung.
- **PDF und XML werden nicht automatisch verglichen.** Dass das sichtbare PDF zu den Daten passt, lässt sich nur per Sichtprüfung feststellen (Ansicht „PDF daneben“).
- **Die KoSIT-Prüfung** läuft nur für Rechnungen, die in ihrer Konfiguration vorgesehen sind (EN 16931 und XRechnung 3.0). Bei anderen Profilen zeigt der Bericht „nicht anwendbar“, dann prüft allein Mustang.
- **Zusatzprüfung BR-CO-25:** Die Norm verlangt bei positivem Zahlbetrag ein Fälligkeitsdatum oder Zahlungsbedingungen. Die offiziellen Regelwerke für CII und UBL prüfen das nicht, Mustang nur im Profil EXTENDED. Das Tool prüft es deshalb für EN 16931 und XRechnung selbst und weist den Unterschied im Bericht aus. Eine solche Rechnung gilt hier als nicht gültig, obwohl andere Validatoren sie akzeptieren. Bei Gutschriften ist es nur ein Hinweis.
- **Rechnungsansicht:** EXTENDED-Felder, die EN 16931 nicht kennt, zeigt sie nicht. Für ZUGFeRD 1.0 gibt es keine Ansicht.
- Bei **Widersprüchen der Engines** nennt der Bericht das ausdrücklich. Bei XRechnungen gilt für die Regeln das KoSIT-Urteil, sonst bleiben alle gemeldeten Fehler stehen.
