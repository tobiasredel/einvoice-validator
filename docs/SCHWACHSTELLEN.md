# Bewertung bekannter Schwachstellen

Stand: Version 1.0.0, Scan vom 2026-11-03 mit Trivy. Vollständiger Bericht: `trivy-report.txt`. Der Bericht altert: Vor dem Einsatz und regelmäßig danach neu scannen.

## Ergebnis

| Schweregrad | Anzahl | Herkunft |
|---|---|---|
| Kritisch | 0 | – |
| Hoch | 5 | Bibliotheken im Mustang-Jar |
| Mittel | 31 | Ubuntu-Pakete, derzeit ohne verfügbaren Fix |
| Niedrig | 5 | Ubuntu-Pakete, derzeit ohne verfügbaren Fix |

## Hohe Funde

| CVE | Bibliothek | Art | Bewertung |
|---|---|---|---|
| CVE-2026-89407, CVE-2026-89425 | jackson-core 2.22.2 | Denial of Service beim Lesen von JSON | nicht erreichbar |
| CVE-2026-91776, CVE-2026-91777 | jackson-databind 2.22.2 | Denial of Service beim Lesen von JSON | nicht erreichbar |
| CVE-2026-24400 | assertj-core 2.9.0 | XXE im Test-Hilfsmittel `XmlStringPrettyFormatter` | nicht erreichbar |

**Begründung:**

1. Das Tool nimmt nur PDF und XML an. Keine JSON-Eingabe erreicht Jackson. Die JSON-Antworten der API erzeugt die Python-App.
2. AssertJ ist eine Testbibliothek, die beim Bau von Mustang mit in das Jar geraten ist.
3. **Gemessen:** Über alle Prüf- und Anzeigewege lädt die JVM keine einzige Klasse dieser Bibliotheken (`nachweise/reachability.txt`, erzeugt mit `tests/reachability.sh`).
4. Unabhängig davon begrenzen eigene Prozesse, Zeit- und Speicherlimits die Folgen eines Denial of Service auf eine Prüfung, und `DOCTYPE` wird vor dem Parser abgelehnt.

**Nicht behoben, weil** die Bibliotheken fest im unveränderten Mustang-Jar stecken. Ein eigener Umbau des Jars würde die Nachvollziehbarkeit der Herkunft verschlechtern. Mit einem neuen Mustang-Release sollten die Funde entfallen; dann neu scannen.

## Mittlere und niedrige Funde

Sie betreffen Ubuntu-24.04-Pakete wie `libpcre2`, `libgnutls`, `libc`, `tar` und `wget`. Ubuntu bietet dafür aktuell keine Fixes an, ein Update des Images ändert also nichts. Das Risiko ist gering, weil der Container ohne Netz, ohne Rechte und mit schreibgeschütztem Dateisystem läuft. Neue Fixes kommen mit dem nächsten Image-Bau.

## Grenzen

Die Bewertung beruht auf den getesteten Abläufen und Beispielrechnungen. Die endgültige Risikoentscheidung liegt bei der IT-Sicherheit des Betreibers.
