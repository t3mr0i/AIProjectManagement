# Difference — von Greenfield zu Plane

Version 0.2 · 24. September 2026 · maßgebliche Ergänzung zum aktualisierten PRD.

## 1. Die verbindliche Änderung

**Alt:** Eigener PM-Kern; bestehende Anwendungen hauptsächlich als Referenz.

**Neu:** Ein eigenständiges Produkt als gezielte Erweiterung des Plane-Quellcodes. Plane liefert den nativen Arbeitsraum; unsere eigentliche Entwicklung konzentriert sich auf ausführbare Arbeitspakete, automatisch belegte Sichtbarkeit, Kommunikation im Kontext und übergreifende Planung.

Plane ist keine zusätzliche API-Anbindung neben einem zweiten eigenen PM-System. Ein Arbeitspaket ist ein vorhandenes Plane-Work-Item mit Erweiterungen. Die externe Unabhängigkeit von Jira, GitLab, Azure DevOps und Linear bleibt erhalten; die interne Foundation-Abhängigkeit von Plane ist ausdrücklich gewollt.

## 2. Was fachlich unverändert bleibt

Ein gemeinsamer Arbeitsraum für Entwickler, Manager und Fachseite. Entwicklung in der IDE. Manuelle und KI-gestützte Paketerstellung. Drafts werden nicht umgesetzt. Menschliche Freigabe vor Merge. Texte und Diagramme gemeinsam bearbeiten. @AI kann ausgewählte Chat-Inhalte als bestätigte Entscheidung übernehmen. Chronologisch sehen, was sich verändert hat. Mehrere Projekte, Roadmaps und Abhängigkeiten. Kleine Änderungen müssen nicht jedes Mal zu einem neuen Ticket werden.

Kein Bezug zu Lufthansa, DevPilot oder ReqPilot. Keine neue IDE. Keine automatische Annahme, dass der Nutzer einer Quellcodeoffenlegung zugestimmt hat.

## 3. Die wichtigsten Unterschiede

| Bereich                             | Bisheriger Ansatz                                      | Neuer Ansatz                                                                                             |
| ----------------------------------- | ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| Benutzer, Workspaces, Projekte      | Als eigener Produktkern aufbauen.                      | Plane-Modelle und Identitäten wiederverwenden; zusätzliche Rechte gezielt ergänzen.                      |
| Arbeitspaket                        | Unabhängiges `WorkPackage` mit eigener ID.             | `Issue` plus 0..1 `PackageProfile`; `workItemId` ist die Plane-Issue-UUID.                               |
| Titel, Status, Priorität, Assignees | Eigene Felder im PM-Kern.                              | Native Plane-Felder bleiben führend. Freigabe-Snapshots dürfen historische Kopien enthalten.             |
| Frontend                            | Freie React-Grundlage mit eigenem Designsystem.        | Bestehende React-Router-Anwendung und Plane-Komponenten erweitern. Kein neuer Next.js-/Dashboard-Neubau. |
| Backend                             | Neu zu bestimmender modularer Anwendungskern.          | Vorhandenes Django-Backend mit additiven Modulen, Tabellen und kontrollierten Integrationspunkten.       |
| Editor und Realtime                 | Bibliothek nach Spike auswählen.                       | Vorhandene TipTap-/Yjs-/Hocuspocus-Basis als Ausgangspunkt; konkrete Erweiterungen weiterhin testen.     |
| Dokumente und Uploads               | Eigener Document-/Storage-Kern.                        | Plane Pages, Versionen und Assets dort übernehmen, wo geeignet; Semantik und sichere Suche ergänzen.     |
| Board und Sprints                   | Von Grund auf implementieren.                          | Native Views, States, Cycles und Modules erhalten; neue Ergebnis-/Aktivitätsansichten hinzufügen.        |
| Build–Review–Ship                   | Eigene Statuswelt.                                     | Zusätzliche belegte Prozesssicht; keine globale Änderung der Plane-State-Gruppen.                        |
| Automatische Ausführung             | Neuer Runner + Freigabe.                               | Weiterhin neu; an dieselbe native Issue-ID und eine gesicherte Revision gebunden.                        |
| Teamchat / DMs                      | Neu.                                                   | Weiterhin neu, sofern nicht explizit nachgewiesen; native Kommentare sind keine fertigen DMs.            |
| Portfolio / Cross-Projekt-Planung   | Neu.                                                   | Bestehende Projekt-/Termin-/Beziehungsdaten nutzen; fehlende übergreifende Semantik und UI ergänzen.     |
| Integrationen                       | Konnektoren zu eigenem PM-Kern.                        | Konnektoren zu Plane-Identitäten; wiederverwendbare Upstream-Teile nach Capability-Prüfung.              |
| Tests                               | Nur neue Anwendung testen.                             | Unveränderte Plane-Flows, Extension-Flows, Migration und Upstream-Updates gemeinsam testen.              |
| Vertrieb                            | Proprietäre Umsetzung allgemein als möglich behandelt. | Plane-Fork vorgesehen; Lizenzpfad L01 bleibt ein separates Freigabetor.                                  |

## 4. Was nicht mehr neu gebaut werden soll

Kein zweites Login, kein zweiter Workspace-/Projektkatalog, keine neue parallele Issue-Verwaltung, kein konkurrierendes Default-Board, kein separates Basic-Designsystem und keine zweite Kopie sämtlicher Dokumente/Uploads. Vorhandene Plane-Funktionen erhalten Regressionstests statt Greenfield-Implementierungstickets.

Das bedeutet nicht „alles ist fertig“. Die tatsächliche Eignung wird auf der gewählten Community-Baseline geprüft. Ein vorhandener Modellname beweist weder den gesamten UI-Flow noch Enterprise-Reife. Plane Commercial/Cloud und der öffentliche Quellcode sind keine austauschbaren Funktionslisten. [P11](SOURCES.md#p11)

## 5. Worauf die eigene Entwicklung konzentriert wird

**Paketprofil und Freigaben:** bestehendes Issue aktivieren; versionierte Absicht, Kriterien und Entscheidungen; eindeutige menschliche Ausführungsberechtigung.

**Automatische Sichtbarkeit:** Git-/CI-/Runner-/Deploymentereignisse korrelieren; technische Kleinschritte zusammenfassen; offene Entscheidungen und nächste ausführbare Pakete anzeigen.

**IDE-/Git-Verbindung:** OpenSpec-Roundtrip, atomare Übernahme, isolierte Ausführung, Revision-/Basisprüfung und reale Liefernachweise.

**Gemeinsame Bearbeitung:** KI-Konkretisierung, Diagrammsemantik, Chat/DM/@AI und bestätigte Entscheidung im selben Paketkontext.

**Übergreifende Steuerung:** Projekte/Teams und Abhängigkeiten sichtbar machen, ohne eine zusätzliche getrennte Planungshierarchie zu erfinden.

## 6. Konsequenz für die UI

Die vorhandene Plane-Oberfläche wird die Basis. Issue-Details erhalten beispielsweise Bereiche für „Auftrag“, „Spezifikation“, „Aktivität“ und „Review & Lieferung“. Ein KI-/Gesprächsbereich lässt sich kontextbezogen daneben öffnen. Die bestehende Liste bleibt nutzbar; neue kompakte Phasen-/Evidenzindikatoren zeigen das tatsächliche Ergebnis.

Das ist keine fertig gezeichnete UI und keine Aussage über vorhandene Tabs. Es ist die neue Integrationsvorgabe für die nächste Mockup-/Frontend-Arbeit. Ein isolierter HTML-Prototyp soll zukünftig dieselben Grundkomponenten, Abmessungen und Interaktionsmuster der gewählten Plane-Baseline abbilden, statt einen losgelösten Greenfield-Look zu entwickeln.

## 7. Geänderte Dateien und Verträge

| Datei / Bereich                   | Änderung                                                                                                                                     |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `PRD.md`                          | Foundation, Scope, Rollen, Objektmodell, Zustände, API, Architektur, 14 zusätzliche Foundation-Anforderungen. Alle 59 alten FR-IDs erhalten. |
| `DESIGN_BRIEF.md`                 | Plane-Shell und Komponenten als tatsächliche Grundlage; Referenzen bleiben Referenzen.                                                       |
| `IMPLEMENTATION_PLAN.md`          | Gleiche Inkrement-IDs I00–I15, aber native Grundfunktionen prüfen/übernehmen statt neu bauen.                                                |
| `BOOTSTRAP.md`                    | Agent startet im Plane-Fork und liest dessen `AGENTS.md`; kein Greenfield-Gerüst.                                                            |
| `schemas/`                        | Vertragsversion 1.1.0, native `workspaceId`/`workItemId`; alte Payloads sind nicht still kompatibel.                                         |
| `skills/`                         | Identitätsbindung und native Schreibwege ergänzt; Skills bleiben ohne reale Tools nur Entwürfe.                                              |
| `acceptance/`                     | 32 übernommene Kernszenarien plus gesonderte Foundation-/Regressionsfälle.                                                                   |
| `PLANE_FOUNDATION.md`             | Quellenstand, Capability-Matrix, Codebereiche und Prüflücken.                                                                                |
| `MIGRATION_AND_UPSTREAM.md`       | Einführung in bestehende Workspaces, Update- und Rückfallstrategie.                                                                          |
| `foundation/upstream-lock.json`   | Exakter analysierter Commit, nicht automatisch freigegebener Produktionsstand.                                                               |
| `foundation/requirement-map.json` | Jede FR-Anforderung klassifiziert als übernehmen, erweitern, neu oder gesondert prüfen.                                                      |

Der maschinenlesbare Textvergleich des vollständigen PRD liegt unter `diff/PRD-v0.1-v0.2.diff`. Es handelt sich um Dokumentenänderungen, nicht um einen implementierten Plane-Patch.

## 8. Neue Startreihenfolge

Zuerst den Quellenstand und erlaubten Funktionsumfang fixieren. Dann Plane unverändert starten und seine Kernabläufe messen/testen. Anschließend **ein bestehendes Issue** um Paketprofil und Freigabe erweitern. Erst danach den echten Git-/IDE-Rundlauf anbinden. Diese Reihenfolge prüft Wiederverwendung, bevor weitere Plattformflächen gebaut werden.

Die Foundation-Entscheidung allein gestattet keine Veröffentlichung. L01 wird vor externer Bereitstellung geklärt. Die technische Planung wird dabei nicht wieder auf eine andere Basis umgestellt.
