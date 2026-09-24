---
name: package-clarify
description: Konkretisiert einen Projektauftrag anhand zugänglicher Quellen zu einem überprüfbaren Draft, ohne Implementierung oder Freigabe auszulösen.
---

# Paket gemeinsam konkretisieren

## Plane-Anbindung

Dieses Paket beschreibt eine Erweiterung des Plane-Forks. Nutze dieselbe native Workspace-/Projekt-/Issue-Identität wie UI und Repositorymanifest (`workspaceId`, `projectId`, `workItemId`); kein zweites Ticket anlegen. Die Vertragsversion ist 1.1.0. Native Beschreibung/Page, aktueller Entwurf und freigegebener Snapshot sind nicht automatisch dieselbe Fassung.

Statuswechsel, Draft-Promotion, Kommentare oder importierte Trackerlabels sind keine Ausführungs-/Mergefreigabe. Eine native Änderung kann eine erneute Prüfung auslösen; der Runner prüft die aktuelle genehmigte Grundlage serverseitig. Verwende nur tatsächlich implementierte und autorisierte Werkzeuge. Die neuen API-Pfade im PRD sind Entwürfe, keine bereits verfügbaren Plane-Funktionen.

## Status und Grenzen

Entwurf für dieses Produkt. Keine installierte Integration und keine Berechtigungsquelle. Die Umsetzung ist nur möglich, wenn die Plattform entsprechende autorisierte Lese-/Draft-Werkzeuge bereitstellt.

## Verhalten

Lies den ursprünglichen Auftrag, die vorhandene Paketrevision und den explizit bereitgestellten Kontext. Prüfe Rechte und Empfängerkreis vor jeder weiteren Quelle. Verwende bereits beantwortete Fragen und bestätigte Entscheidungen. Codeanalyse bleibt lesend: keine Setup-Skripte, Tests, Builds, Agentenimplementierung oder Vorschau aus einem Draft starten.

Unterscheide beobachtetes Verhalten, bestätigte Absicht, Schlussfolgerung und Vorschlag. Code kann das aktuelle Verhalten zeigen, aber nicht zuverlässig den ursprünglichen Grund. Erfinde keine Motivation und erkläre einen vorhandenen Fehler nicht zur bestätigten Anforderung.

Erstelle einen möglichst kurzen Draft mit Ziel/Warum, gewünschtem Ergebnis, Nichtzielen und konkreten Abnahmekriterien. Technische Details gehören in einen ergänzenden Abschnitt, nicht an die Stelle verständlichen Verhaltens.

Frage jeweils nur nach einer wesentlichen offenen Entscheidung. Zeige eine begründete Empfehlung als Vorschlag, nicht als bereits getroffene Entscheidung. Nach höchstens drei aufeinanderfolgenden Klärungsfragen liefere einen speicherbaren Zwischenstand. Weitere Fragen nur bei tatsächlichen Blockern oder ausdrücklicher weiterer Klärung. Speichern darf auch mit offenen Punkten möglich sein.

Bei Diagrammen verwende das strukturierte Elementmodell und den Diff. Reine Layoutänderungen erzeugen keine fachliche Anforderung. Eine semantische Änderung erzeugt zunächst eine bestätigungsbedürftige Interpretation.

## Ausgabe

Ein Draft-Patch auf die erwartete Revision, Quellenreferenzen, offene Annahmen und gegebenenfalls konkrete Readiness-Blocker. Keine automatische Statusänderung zu freigegeben. Keine Ausgabe, die die spätere Anwendung als erteilte Ausführungsgenehmigung missverstehen kann.
