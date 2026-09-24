# Plane-Extension-Verträge 1.1.0

Diese JSON-Schemas beschreiben eigene neue Schnittstellen, nicht vorhandene native Plane-API-Payloads. Version 1.1.0 ist zum ursprünglichen Dokumentenvertrag 1.0.0 bewusst inkompatibel: `tenantId` wird `workspaceId`, `packageId` wird `workItemId`. Die Werte beziehen sich auf native Plane-UUIDs. Kein alter Client wird stillschweigend unterstützt.

Vier Verträge: `package-revision`, `execution-authorization`, `domain-event` und `plane-package-profile`. Zu jedem gibt es ein synthetisches Beispiel. Das Paketprofil ergänzt ein Issue eindeutig und optional; es führt weder eigene Ticket-ID noch Titel-/Status-/Assignee-Duplikate ein.

`workspaceId = db.Workspace.id`, `projectId = db.Project.id`, `workItemId = db.Issue.id`. Server und Datenbank müssen Referenzbeziehungen, Membership, aktuelle Rechte, Revisionen, Content-Hashes und echte menschliche Identität prüfen. Ein syntaktisch korrektes JSON mit `kind: human` beweist nichts davon.

Eine Paketrevision darf unvollständige Draftinhalte enthalten. Nur die serverseitige Readiness-/Policy-/Approvalprüfung kann Ausführung erlauben. `approvedRevisionId` ist eine Referenz, kein allein genügender Berechtigungsnachweis. Domain-Events werden aus authentisierten Quellen erstellt, nicht ungeprüft aus Modellantworten übernommen.

Die Inhalts-Hashwerte in Beispielen sind Platzhalter mit korrekter Syntax für rein synthetische Testfälle. Kanonisierung, Persistenz und kryptografische Verifikation werden erst bei Implementierung konkret getestet. Die Beispieldaten referenzieren keine echte Plane-Installation.
