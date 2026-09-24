# Einführung, Datenmigration und Upstream-Pflege

Version 0.2 · Ausführbarer Planungsrahmen, keine ausgeführte Migration.

## 1. Zwei unterschiedliche Ausgangssituationen

**Neues Produkt-Workspace:** Plane-Basis regulär starten, dann die Erweiterungsmigrationen ausführen und einen explizit freigegebenen Workspace aktivieren. Kein Import aus einem bereits vorhandenen Greenfield-System wird vorausgesetzt.

**Bestehende Plane-Daten:** Ein repräsentativer, datenschutzkonformer Snapshot muss vorab in einer isolierten Umgebung eingespielt werden. Vorhandene IDs, Mitgliedschaften, Issues, States, Cycles, Modules, Pages und Assetbezüge werden erhalten. Deren Integrität wird vor und nach der Migration geprüft. Kein automatischer Wechsel aller Projekte auf neue Pflichtprozesse.

Das bisherige PRD 0.1 ist ein Dokumentenstand. Es ist kein Beleg für ein implementiertes Altsystem. Die Umbenennung von Schemafeldern ist daher zunächst ein Vertragswechsel, keine tatsächlich ausgeführte Datenmigration.

## 2. Additive Datenstrategie

`PackageProfile` ist optional und eindeutig an ein `db.Issue` gebunden; es besitzt keine konkurrierende Ticketidentität. Eigene Extension-Tabellen verweisen auf native Workspaces/Projekte/Benutzer. Native Tabellen bleiben erhalten. Redundante Scopefelder dürfen nur als validierte Constraints/Indexhilfen geführt werden, nicht mit unabhängig veränderbarer Bedeutung.

Neue Schemaänderungen laufen zuerst im deaktivierten Zustand. Backfills sind wiederholbar, messbar und batchweise. Die Aktivierung pro Workspace/Projekt ist eine eigene auditierte Aktion. Ein Paket wird erst auf expliziten Wunsch aktiviert; normale Issues bleiben normale Issues.

Unveränderliche Revisionssnapshots sind fachlich nötig und dürfen Angaben aus nativen Dokumenten enthalten. Sie sind keine zweite live zu pflegende Dokumentkopie. Quellenversion, Inhalts-Hash, Empfängerrechte und Retention müssen mitgeführt werden.

Der genaue Django-Appname, Migrationen, Index-/Unique-Constraints und Native-Service-Anknüpfungspunkte werden im ersten Code-Inkrement auf dem freigegebenen Checkout bestimmt. Keine vorgespiegelten vorhandenen Extension-Dateien.

## 3. Native Mutation und Freigabe

Vor Integration werden die echten Mutationseinstiege erhoben: native UI/API, Bulk, Import, externe Integration, Description-/Page-Livebearbeitung, Restore und Archivierung. Für jeden Pfad ist dokumentiert, ob er:

1. nur Planungsmetadaten verändert;
2. freigegebene Absicht/Artefakte verändert;
3. Zugriff oder Gültigkeit der Ausführung berührt.

Klasse 2 erzeugt neue Arbeitsrevision beziehungsweise Konflikt und erneute Prüfung. Klasse 3 widerruft oder sperrt betroffene Berechtigungen. Der Freigabesnapshot selbst wird nicht editiert. Kritische Gates vergleichen den maßgeblichen Stand synchron; Reconciliation ist nur zusätzliche Wiederherstellung, kein Ersatz für diesen Schutz.

`Issue.is_draft = false`, ein Kommentar „approved“ oder ein State-Update nach „In Progress“ erzeugen keine Ausführungsfreigabe. Ein projektspezifischer Status „Review“ ist nicht automatisch ein genehmigter Merge. Diese Semantik muss auch mit deaktivierter Paket-UI gelten.

## 4. Ereignisse und Konsistenz

Native Activity bleibt erhalten. Neue Extension-Ereignisse werden über Korrelation und eine dauerhafte Event-ID zugeordnet. Fachlicher Zustand und Extension-Outbox gehören in dieselbe Datenbanktransaktion. Zu früh publizierte Ereignisse dürfen keinen halb gespeicherten Datensatz referenzieren.

Webhooks werden authentisiert, dauerhaft angenommen und idempotent verarbeitet. Verbindungsinstanz + externe Event-ID dienen als Deduplikationsgrundlage; falls ein Provider keine stabile Event-ID liefert, wird ein dokumentierter Ersatz verwendet. Zeitstempel allein oder nur der Anzeigename eines Repositories genügen nicht.

Aktivitätsverdichtung verändert nicht die Auditdaten. Eine falsche Zuordnung bleibt korrigierbar. Persönliche Besuchsmarker beeinflussen nur die Ansicht, nicht den Projektstatus. Externe Echoereignisse werden von echten konkurrierenden Änderungen unterschieden.

## 5. Löschung, Archivierung und Wiederherstellung

Native Soft-Delete-/Archivregeln werden respektiert. Extension-Queries dürfen nicht pauschal alle Managerfilter entfernen. Ein archiviertes/gesperrtes Projekt erhält keine neuen Claims. Aktive Runner werden soweit technisch kontrollierbar widerrufen; die Grenzen freier lokaler Prozesse werden angezeigt.

Es gibt keine blinde Löschkaskade, die revisionsbezogene Audit-/Approvaldaten versehentlich entfernt. Die endgültige Retention- und Löschstrategie muss mit Quellenrechten, Verträgen und dem tatsächlichen Datenmodell abgestimmt werden. Wiederhergestellte Projektinhalte erzeugen nicht automatisch wieder aktive, alte Run-Tokens.

## 6. Rückfall und Feature-Flag

Ein Abschalten der Extension sperrt neue Paketläufe und neue Erweiterungsschreibvorgänge. Native Plane-Grundfunktionen sollen erhalten bleiben; historische Revisionen und Nachweise bleiben soweit berechtigt lesbar. Frontendflag und Backendpolicy sind gekoppelt, aber das Frontendflag allein ist kein Sicherheitsmechanismus.

Vor einem produktiven Upgrade: Datenbank und Objektspeicher gemeinsam sichern, Wiederherstellung praktisch testen, aktive Runs kontrolliert behandeln. Rückfall bedeutet nicht automatisch `migrate backwards`: irreversibel geänderte Daten erfordern Restore oder einen expliziten Vorwärtskorrekturpfad. Kompatibilität alter Web-/Workerprozesse mit dem neuen Schema wird vor Rolling Deployment geprüft.

## 7. Upstream-Strategie

Der eigene Fork hat einen dokumentierten Upstream-Remote und einen separaten Quellenstand pro Release. Keine direkten Deployments vom veränderlichen Upstream-Branch. Native Modell-/API-/Editoränderungen werden vor Updates verglichen; Erweiterungshooks bleiben klein und begründet.

Jeder Bump prüft mindestens: Login/Projektwechsel, native Issue-Erstellung und -Bearbeitung, Pages/Upload, Cycles/Modules/Views, Paketfreigabe, native Scopeänderung, Runnerwiderruf, Mehrfachereignisse, DM-/Public-Surface-Isolation sowie ein Migration-/Restore-Szenario. Upstream-Baselinefehler werden getrennt von neu verursachten Fehlern dokumentiert. Warnungen werden nicht durch globale deaktivierte Prüfungen verborgen.

Lieferbares Ergebnis eines Bumps: Alter und neuer Commit, betroffene Verträge, Migrationsstatus, tatsächlich ausgeführte Tests, verbleibende Einschränkungen und ausdrücklich freigegebener Rollout.

## 8. Lizenz und Vertrieb

Plane bleibt gewählte Foundation. Vor einer externen Bereitstellung muss L01 geklärt sein; ein Quellenstand oder erfolgreiches Deployment ist keine Vertriebsfreigabe. Copyright-/Lizenzhinweise bleiben erhalten, Abhängigkeiten werden in einem SBOM-/Lizenzinventar dokumentiert. Diese technische Modulstrategie beansprucht keine automatische Copyleft-Ausnahme.
