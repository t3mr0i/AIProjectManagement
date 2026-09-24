# Startauftrag für den KI-Entwicklungsagenten — Plane Foundation

Version 0.2. Vorlage für eine ausdrücklich autorisierte Umsetzung; dieses Dokument allein erlaubt weder externe Schreibzugriffe noch Veröffentlichung oder Deployment.

## Auftrag

Erweitere `makeplane/plane` zur in `PRD.md` beschriebenen KI-nativen Projektzentrale. **Erzeuge keine Greenfield-Anwendung.** Plane ist die verbindliche Foundation, nicht nur eine UI-Referenz oder ein externer Trackeradapter. Ein Arbeitspaket ist ein bestehendes Plane-Issue mit additivem Profil; keine zweite Projekt-/Ticket-/Benutzerverwaltung.

Lies in dieser Reihenfolge: `PLANE_DELTA.md`, `foundation/upstream-lock.json`, `PLANE_FOUNDATION.md`, bestätigte Vorgaben und Invarianten in `PRD.md`, danach `MIGRATION_AND_UPSTREAM.md`, `DESIGN_BRIEF.md` und das ausdrücklich freigegebene Inkrement aus `IMPLEMENTATION_PLAN.md`.

Im tatsächlichen Plane-Checkout zuerst das dortige `AGENTS.md` und alle für betroffene Pfade geltenden Regeln lesen. Analysecommit und tatsächlichen HEAD vergleichen. Ein anderer Commit erfordert eine bewusste Baselineentscheidung und Aktualisierung der Quellen-/Capability-Matrix; keine stille Anpassung.

## Leitplanken

1. Bestehende Workspace-/User-/Project-/Issue-Identitäten, Grundfunktionen, Router, Komponenten und Backendstrukturen weiterverwenden. Kein Next.js-Neugerüst, keine zweite Auth oder PM-ORM einführen.
2. Die konkreten Upstream-Service-, Permission-, Migrations- und Routendateien zuerst im Checkout finden. In den Dokumenten als „neu vorgesehen“ bezeichnete Pfade sind Vorschläge, keine existierenden APIs.
3. Pakete sind 0..1-Profile nativer Issues. `workItemId` ist die native Issue-UUID; Titel, Priorität, Assignees und Planungsstatus nicht als konkurrierende Livekopie halten.
4. Native Draft-/Stateänderungen autorisieren nichts. Freigaben brauchen echten Human-Principal, aktuelle Rechte und exakten Revision-/Policy-/Basisbezug. Native UI-, API-, Bulk-, Import-, Sync- und Live-Pfade berücksichtigen.
5. Entwicklung der verwalteten Projekte bleibt in IDE/Runner. Untrusted Repositorycode nicht im Plane-Web-, API- oder Liveprozess ausführen. Plattformrepository und verwaltete Kundenrepositories sind getrennte Kontexte.
6. Native State-Gruppen unverändert lassen. Build/Review/Ship als belegte Sicht mit offenen/fehlenden/alten Nachweisen behandeln. Native „Done“-Information ist kein Deploymentbeleg.
7. Plane Pages/Assets/Editor/Live als Basis prüfen; keine parallele gesamte Dateihaltung. Chat/DM/@AI sind eigene Semantik mit echten Teilnehmerrechten, nicht einfach bestehende Kommentare umbenennen.
8. Neue Module additiv und featuregeflagt entwickeln. Native Funktionen, IDs, Links und APIs nicht global ersetzen. Migration auf Altbestand und späterer Upstream-Bump brauchen Regressionstests.
9. Keine Commercial-/Cloud-/Enterprise-Funktion ohne Quellen- und Rechtebeleg als vorhanden verwenden. Lizenzen und Hinweise erhalten. L01 ist offen; keine Verteilung oder öffentliche Bereitstellung ohne konkreten Auftrag und geklärten Weg.
10. Nur das freigegebene Inkrement implementieren. Keine pauschalen Zeit-/Kosten-/Reifeaussagen. Tatsächliche Tests von geplanten Tests trennen.

## Erster Arbeitsnachweis

Bei I00 zuerst unveränderte Plane-Baseline, Quellenstand, konkrete Start-/Testbefehle, entdeckte Eignungslücken und geplante minimale Integrationsstellen dokumentieren. Danach ausschließlich autorisierte Änderungen durchführen. Kein neues Projektgerüst anlegen, um Fehler der bestehenden Basis zu umgehen.

Für Folgeschritte berichten: betroffene native und neue Codebereiche, Requirement-IDs, umgesetzt, tatsächlich geprüft, nicht geprüft, Migrationseffekt und offene Entscheidungen. Mockdaten kennzeichnen. Das Paket `Project_Hub_Plane_PRD_v0.2` enthält Spezifikationen, keine bereits implementierte Plane-Erweiterung.
