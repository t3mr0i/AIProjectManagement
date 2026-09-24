# Project Hub auf Plane — PRD-Paket 0.2

24. September 2026 · Arbeitsname, keine beschlossene Produktmarke.

## Start

`READABLE.html` lokal im Browser öffnen. Die Datei fasst die wesentlichen Dokumente lesbar zusammen und benötigt keine externen Assets. Sie ist ein Dokumentenleser, kein Plane-UI-Mockup und keine funktionierende Anwendung.

**Zuerst `PLANE_DELTA.md` lesen.** Danach `PRD.md`, `PLANE_FOUNDATION.md` und das freigegebene Inkrement in `IMPLEMENTATION_PLAN.md` verwenden. Version 0.2 ersetzt den Greenfield-Ansatz aus 0.1.

## Enthalten

- Vollständig angepasstes PRD mit den 59 ursprünglichen FR-IDs und 14 neuen Foundation-Anforderungen.
- Konkreter Difference-Report und maschinenlesbarer PRD-Diff.
- Statisch geprüfte Plane-Quellenbasis, Capability-Matrix und vorgeschlagene Erweiterungsgrenzen.
- Plane-orientierter Design-Brief, 16 neu ausgerichtete Inkremente I00–I15 und Agenten-Startauftrag.
- Einführungs-/Migrations-/Upstream-Plan mit Regression, Rechteprüfung und Rückfall.
- 32 ursprüngliche Kern-Szenarien plus 14 Plane-Foundation-Szenarien, noch ohne App-Step-Implementierungen.
- Vier JSON-Verträge 1.1.0 mit synthetischen Beispielen und Plane-identischen Workspace-/Projekt-/Issue-Referenzen.
- Drei angepasste Produkt-Skill-Entwürfe; keine Tools installiert oder Ausführung gestartet.
- Quellenprotokoll, upstream-lock und vollständige Requirement-Zuordnung.
- `validate_pack.py`, `requirements.txt`, `make_reader.py`, `VALIDATION.md` für reproduzierbare Dokumentenprüfung.

## Klare Grenzen

Plane ist verbindlich gewählt. Der genaue Produktionsstartcommit und L01s zulässiger Lizenz-/Vertriebsweg sind offen. Das Paket enthält keinen Plane-Quellcode, keinen vorgenommenen Fork, keine echte Datenmigration und keine getestete Produktimplementierung. Native Modell-/Manifestlektüre ist keine vollständige Capability-/Sicherheitsabnahme.

Die vorhandenen Designreferenzen aus 0.1 bleiben erhalten. In diesem Änderungsschritt wurde kein neuer Mobbin-/Screenshot-/Mockup-Entwurf erstellt. Die UI-Vorgabe ist jetzt ausdrücklich eine Erweiterung der vorhandenen Plane-Oberfläche.

## Strukturprüfung ausführen

Mit Python und den in `requirements.txt` genannten Abhängigkeiten: `python validate_pack.py`. Danach bei Bedarf `python make_reader.py`. Der Validator prüft Dokumentstruktur, neue/alte Requirement-IDs, Scenarioverweise, synthetische JSON-Beispiele, Negativbeispiele, Quellen-/Commitkonsistenz und den PRD-Diff. Er führt keine Anwendungstests aus.
