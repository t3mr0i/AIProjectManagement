# Quellen und Recherchegrenzen

Stand: 24. September 2026. Die Fassung 0.2 prüft gezielt die Plane-Quellen P01–P11. Technische Quellen S01–S11 und Mobbin-Beobachtungen M01–M07 stammen aus Fassung 0.1 und wurden in diesem Änderungsschritt nicht erneut abgerufen. Die vorgeschlagene Gesamtanwendung ist eine eigene Produktspezifikation; sie wurde nicht durch diese Recherche als fertiges System validiert.

## Für die Plane-Anpassung verwendete Primärquellen

Alle Dateiquellen sind auf denselben Analysecommit fixiert. Quellcode wird im Auslieferungspaket nicht mitgebündelt.

### P01

**Repository- und Commitbasis.** Branch und Commit am 24.09.2026 über GitHub-Connector gelesen; Daten im Lock fixiert.

[Primärquelle öffnen](https://api.github.com/repos/makeplane/plane/branches/preview)

### P02

**Root-Manifest.** Version, Node-/pnpm-Vorgabe, Monorepo-Scripts und Lizenzbezeichnung.

[Primärquelle öffnen](https://github.com/makeplane/plane/blob/d616636119d20a531a815c78d364bdb47d552a2d/package.json)

### P03

**Web-Manifest.** React Router, React, gemeinsame Pakete und UI-/Store-Abhängigkeiten.

[Primärquelle öffnen](https://github.com/makeplane/plane/blob/d616636119d20a531a815c78d364bdb47d552a2d/apps/web/package.json)

### P04

**Native Modell-Exporte.** Existierende Modellexporte, keine vollständige Funktions-/Rechteabnahme.

[Primärquelle öffnen](https://github.com/makeplane/plane/blob/d616636119d20a531a815c78d364bdb47d552a2d/apps/api/plane/db/models/__init__.py)

### P05

**Issue-Modell.** Zeilen 1–240 gelesen: Identität, Eigenschaften, Draftfilter und Speichern.

[Primärquelle öffnen](https://github.com/makeplane/plane/blob/d616636119d20a531a815c78d364bdb47d552a2d/apps/api/plane/db/models/issue.py)

### P06

**State-Modell.** Native State-Gruppen und projektlokale States; vollständig zurückgegebene Datei gelesen.

[Primärquelle öffnen](https://github.com/makeplane/plane/blob/d616636119d20a531a815c78d364bdb47d552a2d/apps/api/plane/db/models/state.py)

### P07

**Agenten-/Entwicklungsregeln.** Dokumentierte Befehle, Tests, shared-state, propel und blocks; keine Ausführung der Befehle.

[Primärquelle öffnen](https://github.com/makeplane/plane/blob/d616636119d20a531a815c78d364bdb47d552a2d/AGENTS.md)

### P08

**Editor-Manifest.** TipTap-/ProseMirror-/Yjs-/Providerabhängigkeiten, nicht sämtliche Node-Implementierungen.

[Primärquelle öffnen](https://github.com/makeplane/plane/blob/d616636119d20a531a815c78d364bdb47d552a2d/packages/editor/package.json)

### P09

**Live-Manifest.** Hocuspocus, Kollaboration und Vitest-Scripts; keine Sicherheits-/Chatgarantie.

[Primärquelle öffnen](https://github.com/makeplane/plane/blob/d616636119d20a531a815c78d364bdb47d552a2d/apps/live/package.json)

### P10

**Lokaler Compose-Stack.** Lokale DB-/Queue-/Cache-/Asset-/Worker-/Migratorservices; kein Produktionsaudit.

[Primärquelle öffnen](https://github.com/makeplane/plane/blob/d616636119d20a531a815c78d364bdb47d552a2d/docker-compose-local.yml)

### P11

**Plane-Editionen.** Community und Commercial/Airgapped unterscheiden sich in Codebasis/Funktionsumfang. Am 24.09.2026 geöffnet.

[Primärquelle öffnen](https://developers.plane.so/self-hosting/editions-and-versions)

### P12

**Lizenzbezug.** AGPL-Zuordnung durch Root-Manifest, SPDX-Kopfzeilen der gelesenen Modelle sowie offizielle Editionsdokumentation belegt. Vollständiger Lizenztext bereits im vorausgehenden Lizenzgespräch gelesen; kein neuer Rechtsgutachten-/Vertragsnachweis.

[Primärquelle öffnen](https://github.com/makeplane/plane/blob/d616636119d20a531a815c78d364bdb47d552a2d/LICENSE.txt)

## Technische Primärquellen aus 0.1

### S01

**OpenSpec — Concepts.** Abgrenzung bestehender Specs und vorgeschlagener Änderungen, Artefakte und Delta-Spezifikationen. Die zusätzliche menschliche Freigabe und sichere Synchronisierung in unserem PRD sind eigene Anforderungen, keine zugesagten Standardfunktionen von OpenSpec.

https://github.com/Fission-AI/OpenSpec/blob/main/docs/concepts.md

### S02

**Matt Pocock — Grill Me.** Dokumentation und Skill als Grundlage für einzelne Fragen und Codeanalyse vor unnötigen Rückfragen. Die reduzierte Intensität und Integration in Pakete werden eigenständig entworfen. Der im vorangegangenen Gespräch erwähnte `grill-with-docs`-Pfad war bei dieser Prüfung nicht abrufbar und ist keine tragende Quelle dieses PRD.

https://github.com/mattpocock/skills/blob/main/docs/productivity/grill-me.md

https://github.com/mattpocock/skills/blob/main/skills/productivity/grill-me/SKILL.md

### S03

**Git — git-worktree.** Mehrere Arbeitsverzeichnisse eines Repositorys. Keine Zusage einer Sicherheits-Sandbox oder Synchronisierung zwischen Rechnern.

https://git-scm.com/docs/git-worktree

### S04

**GitLab — Merge request approval settings.** Menschliche Approval-Regeln und Umgang mit späteren Änderungen; Edition und Konfiguration beachten. Eigene Adapter müssen die konkreten Fähigkeiten prüfen.

https://docs.gitlab.com/user/project/merge_requests/approvals/settings/

### S05

**GitLab — Environments.** Umgebung und Deployments als eigene Lieferinformationen, getrennt von einem bloßen Merge.

https://docs.gitlab.com/ci/environments/

### S06

**Atlassian — Jira Cloud Webhooks.** Ereignisintegration mit wiederholter Zustellung und betrieblichen Einschränkungen. Keine Behauptung identischer Jira-Data-Center-Funktionen.

https://developer.atlassian.com/cloud/jira/platform/webhooks/

### S07

**Linear — Webhooks.** Ereignisschnittstelle als Adaptergrundlage, einschließlich Authentizitätsprüfung der Zustellung.

https://linear.app/developers/webhooks

### S08

**Microsoft — Azure DevOps Service Hooks.** Externe Ereignisanbindung. Konkreter Funktionsumfang von Services/Server und gewählten Ereignissen separat prüfen.

https://learn.microsoft.com/en-us/azure/devops/service-hooks/overview?view=azure-devops

### S09

**W3C — WCAG 2.2.** Zielstandard für die Accessibility-Abnahme. Ein PRD mit diesem Ziel ist keine zertifizierte oder geprüfte Implementierung.

https://www.w3.org/TR/WCAG22/

### S10

**React — Quick Start.** Historische Referenz aus 0.1. Für den tatsächlichen Plane-Stack sind jetzt P02/P03 maßgeblich; keine freie Neuwahl des Frontendframeworks.

https://react.dev/learn

### S11

**PostgreSQL — Row Security Policies.** Zusätzliche Datenbankzugriffsgrenze; privilegierte Rollen und Eigentümer-Ausnahmen müssen berücksichtigt werden.

https://www.postgresql.org/docs/current/ddl-rowsecurity.html

## Über Mobbin betrachtete UI-Referenzen

Laut Rechercheprotokoll von 0.1 wurden diese Referenzen mit dem Mobbin-MCP gesucht und die zurückgegebenen Screens visuell betrachtet; keine erneute Mobbin-Prüfung in 0.2. Screenshots sind Momentaufnahmen. Aus ihrer Darstellung werden keine Aussagen über aktuelle Tarife, Backends, Automatisierungsfähigkeiten oder allgemeine Produktqualität abgeleitet.

| ID  | Referenz                                               | Link                                                                      |
| --- | ------------------------------------------------------ | ------------------------------------------------------------------------- |
| M01 | Linear — Projektübersicht mit Update und Meilensteinen | [Mobbin](https://mobbin.com/screens/9c8e3907-b7af-48d6-ae2d-9b4ff700d433) |
| M02 | Linear — kompakte, gruppierte Arbeitsliste             | [Mobbin](https://mobbin.com/screens/be6c4ee4-aa93-42b4-89b3-dcfc8386f022) |
| M03 | Linear — Projektzeitachse                              | [Mobbin](https://mobbin.com/screens/b3aab33b-60b3-4eb5-b21d-5aa6ba3061e2) |
| M04 | Wrike — Tabelle mit Zeitplan                           | [Mobbin](https://mobbin.com/screens/c852fffb-8f64-48ba-a078-84b4ca21ecc7) |
| M05 | Fibery — Dokument neben KI-Seitenbereich               | [Mobbin](https://mobbin.com/screens/e1f475cd-9340-4b6d-98c3-9ad852993175) |
| M06 | Langdock — Gespräch neben entstehendem Artefakt        | [Mobbin](https://mobbin.com/screens/579fb137-50fa-42d0-9222-4970f35648d5) |
| M07 | Slack — Aktivität und zugehöriger Thread               | [Mobbin](https://mobbin.com/screens/84dfe56c-4571-4248-a067-1432727bc5d6) |

Die hochauflösenden Mobbin-Downloads waren über den verfügbaren Downloadpfad nicht abrufbar. Es wurden keine niedrig aufgelösten Vorschauen als exportierte Originale ausgegeben. Das Paket enthält stattdessen kanonische Referenzlinks und eine eigenständige schriftliche Auswertung.

## Nicht geprüft

Keine produktive Verbindung zu Kundensystemen; keine praktische Interoperabilitätsprüfung der vorgeschlagenen Adapter; keine Leistungs-/Sicherheitsmessung einer Implementierung; keine juristische Begutachtung; keine Bestätigung von Modell-, Hosting- oder Lizenzkosten. Verfügbarkeiten und Providerfähigkeiten sind vor einer Implementierung gegen die konkret verwendete Edition und Version erneut zu prüfen.
