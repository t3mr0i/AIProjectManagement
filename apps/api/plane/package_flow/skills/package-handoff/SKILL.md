---
name: package-handoff
description: Erstellt eine quellengebundene Änderungs- und Übergabeansicht aus Paketabsicht, Code, Prüfungen und Lieferereignissen, ohne fehlende Nachweise zu erfinden.
---

# Änderungen erklären und übergeben

## Plane-Anbindung

Dieses Paket beschreibt eine Erweiterung des Plane-Forks. Nutze dieselbe native Workspace-/Projekt-/Issue-Identität wie UI und Repositorymanifest (`workspaceId`, `projectId`, `workItemId`); kein zweites Ticket anlegen. Die Vertragsversion ist 1.1.0. Native Beschreibung/Page, aktueller Entwurf und freigegebener Snapshot sind nicht automatisch dieselbe Fassung.

Statuswechsel, Draft-Promotion, Kommentare oder importierte Trackerlabels sind keine Ausführungs-/Mergefreigabe. Eine native Änderung kann eine erneute Prüfung auslösen; der Runner prüft die aktuelle genehmigte Grundlage serverseitig. Verwende nur tatsächlich implementierte und autorisierte Werkzeuge. Die neuen API-Pfade im PRD sind Entwürfe, keine bereits verfügbaren Plane-Funktionen.

## Status und Grenzen

Entwurf für eine Plattformintegration. Nur berechtigte Quellen lesen. Eine verständliche Zusammenfassung ist weder Testnachweis noch menschliche Freigabe oder Beweis tatsächlichen Teamverständnisses.

## Quellen zusammentragen

Ermittle Paketrevision, bestätigte Absicht, Kriterien, tatsächliche Änderung, Commit-/Merge-Request-Beschreibung, CI-/lokale Nachweise und Lieferereignisse. Jede Quelle behält Version, Zeitpunkt und Vertrauensklasse. Für eine gemeinsame Ausgabe prüfe den Empfängerkreis, nicht nur die Rechte des anfragenden Nutzers.

Commit-Messages sind Hinweise. Eine Aussage „alle Tests bestanden“ ist ohne passenden Nachweis kein bestandener Test. Eine Codeänderung erklärt nicht automatisch das ursprüngliche Warum. Fehlende Begründungen und widersprüchliche Informationen ausdrücklich kennzeichnen.

## Ergebnis formulieren

Beschreibe knapp: Was wurde verändert? Welches gewünschte Verhalten wird damit erreicht? Warum wurde es beauftragt? Was wurde am vorliegenden Stand tatsächlich geprüft? Was fehlt oder benötigt eine Entscheidung? Welche Repositories und Lieferstufen sind betroffen?

Verknüpfe zentrale Aussagen mit prüfbaren Quellen. Ein neuer Head macht alte Evidenz gegebenenfalls veraltet. Unterscheide Run beendet, Code integriert, Artefakt bereitgestellt und Funktion freigeschaltet. Bei mehreren Repositories zeige Teillieferung statt eines pauschalen grünen Status.

Gib Vorschläge für nächste Schritte als solche aus. Keine automatische fachliche Abnahme, keine erfundene Unterschrift und kein Schließen des übergeordneten Pakets allein wegen eines einzelnen erfolgreichen Merge Requests.

## Dauerhaftes Lernen

Halte nur wiederverwendbare Erkenntnisse, bestätigte technische Entscheidungen oder einen konkreten Regressionstest fest. Nicht jeden Agentenschritt in dauerhafte Projektdokumentation umwandeln. Originalabsicht bleibt erhalten; eine neue Erkenntnis ergänzt sie, statt sie rückwirkend umzuschreiben.
