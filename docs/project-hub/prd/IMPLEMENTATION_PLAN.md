# Implementierungsplan — Plane-Fork gezielt erweitern

Version 0.2 · Die Inkrement-IDs I00–I15 bleiben erhalten. Der Greenfield-Neubau aus 0.1 ist aufgehoben.

## 1. Arbeitsprinzip

Zuerst vorhandene Plane-Funktion nachweisen, dann erweitern. Jeder Schritt hat ein freigegebenes Ziel, passende Tests und einen engen Umfang. Nicht alle Inkremente gleichzeitig an Agenten vergeben. Bereits verfügbare Grundfunktionen sind Regressionstest-Arbeit, kein Auftrag sie neu zu bauen.

I00/I01/I02 sind die erste zusammenhängende Strecke: unveränderte Baseline, additive Daten-/Rechteanbindung, ein vorhandenes Issue mit Paketprofil. Eine größere UI-Neugestaltung oder automatische Ausführung folgt erst danach.

## 2. Inkremente

### I00 — Plane-Quellenstand und unveränderte Baseline

**Voraussetzung:** O06; für externe Bereitstellung zusätzlich L01.

**Umfang:** Analysierten Commit prüfen, tatsächlichen Fork-Startstand freigeben, vorhandenes AGENTS.md/Manifeste/Lockfile lesen. Unveränderte Plane-Instanz starten; Edition, native Flows, Runtime und Dependencies erfassen. Bestehende UI-Screens und ein repräsentatives Testdataset sichern.

**Bereich:** Root, AGENTS.md, package.json, vorhandene Compose-/Testdateien; noch keine fachliche Neukonstruktion.

**Abnahme:** Checkout und foundation/upstream-lock.json stimmen überein. Login, Projekt, Issue, Pages und vorhandene Planungsfunktionen laufen beziehungsweise ihre Baselinefehler sind ehrlich dokumentiert. Keine neue Auth-/Projekt-App erzeugt.

**Bezug:** FR-B01, FR-B03, FR-B12, FR-B13.

### I01 — Native Identitäten, Rechte und additive Extensionbasis

**Voraussetzung:** I00.

**Umfang:** Plane Workspace/User/Project/Issue als Referenzen übernehmen. Extension-App und Migrationen minimal anlegen; Feature-Flag und zusätzliche Capability-Prüfungen. Keine parallelen Mitglieder-/Projekttabellen. Mutations-/Public-Surface-/Exportpfade inventarisieren.

**Bereich:** apps/api, vorhandene Permission-/Model-/Migrationsbereiche; neu vorgesehene Extensionmodule.

**Abnahme:** Zwei echte Plane-Workspaces/Projekte bleiben isoliert. Vorhandene Issues funktionieren ohne Paketprofil. Migration auf Altbestand erhält IDs und Referenzen. Keine Adminabkürzung in Isolationstests.

**Bezug:** FR-P01, FR-I01, FR-I07, FR-B02, FR-B04, FR-B09.

### I02 — Ein bestehendes Issue zum freigegebenen Paket erweitern

**Voraussetzung:** I01.

**Umfang:** 0..1-Paketprofil, Draft, Kriterien, unveränderliche Revision, Readiness, menschliche Freigabe/Widerruf. Native Draftpfade prüfen. Standard-Issue bleibt frei von zusätzlicher Bürokratie.

**Bereich:** Native Issue-/Description-Anknüpfung und neue Profile-/Revision-/Approvalmodule; bestehender Issue-Detailbereich.

**Abnahme:** Dieselbe Issue-ID wird überall verwendet. Draft weder per API noch durch Statuswechsel ausführbar. Agentenprincipal kann keine Human-Freigabe erzeugen. Fremde Projekt-/Workspace-Referenz wird abgelehnt.

**Bezug:** FR-W01, FR-W02, FR-W04, FR-W05, FR-W06, FR-B02, FR-B05, FR-B07.

### I03 — Plane-Übersicht um belegte Arbeit erweitern

**Voraussetzung:** I02.

**Umfang:** Native Shell, Liste, Filter, Projektwechsel und Issue-Detail verwenden. Paketzeilen, persönliche Besuchsmarker, verdichtete Aktivität und Build–Review–Ship-Read-Model ergänzen. Native State-Gruppen erhalten; Fixtures kennzeichnen.

**Bereich:** apps/web; @plane/blocks, @makeplane/propel, gemeinsame Stores/Services/Typen.

**Abnahme:** Gewöhnliche Plane-Issues und Links funktionieren weiterhin. Ein „Done“-Issue ohne Deploymentsignal erscheint nicht als produktiv. Doppelte Events erzeugen keine doppelten fachlichen Updates.

**Bezug:** FR-P02, FR-P03, FR-P04, FR-P05, FR-B10, FR-B11, FR-B14.

### I04 — Reale Git-Anbindung zunächst lesend

**Voraussetzung:** I01–I03; O02.

**Umfang:** Vorhandene Integrationsmodelle/Endpunkte auf Eignung prüfen. RepositoryBinding zum Plane-Projekt, Importvorschau, Commit/MR/CI-Metadaten, authentisierte Inbox und Reconciliation. Noch keine Repo-Writes.

**Bereich:** Vorhandene Integrations-/Workerbereiche und neue Provider-/Correlationmodule.

**Abnahme:** Externe Providerobjekte referenzieren dieselben nativen Issues. Retries, veraltete Ereignisse und ausgeschaltete Integration sind korrekt sichtbar. Kein zweiter lokaler PM-Store.

**Bezug:** FR-G01, FR-G08, FR-I02, FR-I04, FR-I05, FR-B10.

### I05 — Plane-Editor und OpenSpec-Roundtrip

**Voraussetzung:** I02, I04.

**Umfang:** Vorhandene Pages/Descriptions und packages/editor/apps/live nutzen. Paketversionen referenzieren sichere Snapshots. Git-Import/-Export bekannter OpenSpec-Blöcke, unbekannte Inhalte erhalten, Drei-Wege-Konflikt.

**Bereich:** packages/editor, apps/live, native Pages-/Description-/Versionbereiche; neuer OpenSpec-Adapter.

**Abnahme:** Native Editor- und IDE-Änderung kollidieren nachvollziehbar. Draft-Dokumentexport startet keine Implementierung und keinen Produktbuild. Alte Freigabe wird nicht an neue Inhalte angepasst.

**Bezug:** FR-E01, FR-W08, FR-W09, FR-G02, FR-B06, FR-B08.

### I06 — IDE-Übernahme und Runnervertrag

**Voraussetzung:** I02, I04, I05; O01.

**Umfang:** CLI-Anmeldung auf Plane-Identität/Integration mappen, Manifest mit workItemId/workspaceId, atomarer Claim, Lease/Heartbeat/Fencing, Widerruf. Deterministischer Test-Runner zuerst. Worktree erst nach gültigem Ausführungsauftrag.

**Bereich:** Neue Runner-/Claimmodule und CLI; getrennt von Plane-Web/API-Ausführung.

**Abnahme:** Zwei exklusive Claims ergeben einen Besitzer. Ungültige Approval-/Workspace-/Revisionkombination scheitert. Archivierung oder Zugriffsentzug verhindert folgende kontrollierte Aktionen.

**Bezug:** FR-G03, FR-G04, FR-G05, FR-G06, FR-G07, FR-B05, FR-B07.

### I07 — Kontrollierte Agentenausführung am selben Issue

**Voraussetzung:** I06; explizit gewählter Agentadapter.

**Umfang:** Ein freigegebenes Testpaket aus Plane wird in einem isolierten Testrepository umgesetzt. Runner begrenzt Befehle, Dateiscope, Netz, Kosten und Laufzeit. Native Änderungen werden bei kritischen Aktionen erneut geprüft.

**Bereich:** Runneradapter und neue Freigabe-/Resultverarbeitung; kein Modellaufruf als Ersatz für Policy.

**Abnahme:** Realer Diff und Prüfergebnisse hängen an Issue/Revision/Run. Repo-Prompt-Injection erweitert keine Rechte. Kein automatischer Merge, keine Ausführung ungeklärter Drafts.

**Bezug:** FR-G05, FR-G06, FR-G10, FR-B06.

### I08 — Gemeinsame Kommunikation und Entscheidungen

**Voraussetzung:** I01, I02.

**Umfang:** Projekt-/Paketthreads, DMs, Teilnehmerrechte, @AI-Vorschau, selektierte Quellen und idempotenter Beschluss. Bestehende Issue-Kommentare bleiben Kontext, nicht die gesamte neue Chatarchitektur.

**Bereich:** Neue Conversation-/Decisionmodelle, apps/web-Kontextfläche; Live-Transport nach Protokoll-/ACL-Prüfung.

**Abnahme:** Eine private Quelle wird nicht automatisch im Projekt veröffentlicht. Bearbeitete Nachricht verändert keinen alten Beschluss. Native User-/Projekt-IDs sind der Bezug; kein zweiter Teamkatalog.

**Bezug:** FR-C01, FR-C02, FR-C03, FR-C04, FR-C07, FR-E05, FR-B09.

### I09 — Moderate KI-Klärung und semantische Diagramme

**Voraussetzung:** I05, I08.

**Umfang:** Grill-Me-inspirierte begrenzte Klärung, belegter Codekontext, strukturierte Diagrammnodes mit stabilen IDs, Layout-/Semantik-Diff. KI-Vorschläge in bestehenden Editor integrieren, nicht blind schreiben.

**Bereich:** packages/editor und neue Semantik-/Proposalmodule; vorhandene Pages-/Issue-Oberflächen.

**Abnahme:** Layoutänderung erzeugt keinen Codeauftrag. Inhaltliche Änderung erzeugt Draftvorschlag. Vorhandene Editorblöcke, Kollaboration und Undo bleiben intakt.

**Bezug:** FR-W03, FR-W07, FR-E02, FR-E03, FR-E04, FR-E06, FR-B08.

### I10 — Review, menschlicher Merge und Lieferstand

**Voraussetzung:** I04, I06, I07.

**Umfang:** Evidence/Approval/Delivery, verständliche Resultansicht, fachliche/technische Abnahme, sicherer Mergepfad, Multi-Repo-Manifest, Deployment und Rollback. Native „Done“-Stateinformation getrennt behandeln.

**Bereich:** Neue Evidence-/Delivery-/Reviewmodule, vorhandene Issue-Links/Activity und Provideradapter.

**Abnahme:** Neue relevante Commits/Specänderung blockieren stale Approval. Merge ohne Deployment bleibt nicht produktiv. Teillieferung und Rollback werden gezeigt; lokale Selbstmeldung ersetzt kein CI-Gate.

**Bezug:** FR-R01, FR-R02, FR-R03, FR-R04, FR-R05, FR-R06, FR-G09, FR-G10, FR-B11.

### I11 — Planung über vorhandene Plane-Projekte

**Voraussetzung:** I01–I03.

**Umfang:** Vorhandene Cycles/Modules/Views/Termine wiederverwenden. Projektübergreifende Milestones, bestätigte Abhängigkeiten, Tabellen-/Zeitansicht und Risiken ergänzen. Keine zweite Sprintverwaltung.

**Bereich:** Native Projekt-/Planungsbereiche, neue dünne Portfolio-/Dependencyrelationen und Ansichten.

**Abnahme:** Zwei echte Plane-Projekte und vertraulicher dritter Bereich. Zyklen in harten Abhängigkeiten erkannt; keine Quelloffenlegung über Graphen; keine erfundenen Termine.

**Bezug:** FR-M01, FR-M02, FR-M04, FR-M05, FR-M06, FR-C06, FR-B13.

### I12 — Externer Tracker ohne doppelte Ticketwelt

**Voraussetzung:** I04, I11; O02.

**Umfang:** Erster externer Tracker mit Providerinstanz-/Objektmapping, Preview, Feldverantwortung und bewusst begrenztem Sync. Vorhandene Plane-Importer unterscheiden von einer laufenden Synchronisierung.

**Bereich:** Bestehende Integrations-/Importer-Anknüpfung und neue Sync-/Capabilityverträge.

**Abnahme:** Ein externer Vorgang entspricht derselben nativen Issue-ID. Disconnect bewahrt diese. Concurrent Edit nicht vom Echo verschluckt. Providerfähigkeit explizit statt „alles unterstützt“.

**Bezug:** FR-I01, FR-I02, FR-I03, FR-I04, FR-I05, FR-I06, FR-B02, FR-B10, FR-B13.

### I13 — Wissen, Uploads und sichere Wiederauffindbarkeit

**Voraussetzung:** I01, I05, I08.

**Umfang:** Plane Pages/FileAsset/Versionen als Basis; Uploadprüfung, sichere Volltext-/Kontextsuche, zusätzliche Semantik nur bei Bedarf, Termine/Export. Quellenrechte auch in KI, Snippets und öffentlichen Flächen.

**Bereich:** Bestehende Dokument-/Asset-/Such-/Exportbereiche, neue Index-/ACL-/Kontextanbindung.

**Abnahme:** Entzogene Quelle verschwindet aus folgenden Ausgaben. Gesperrter Upload wird nicht indiziert. Keine zweite Dokumentkopie. Native Export-/Restorepfade berücksichtigen Extensiondaten.

**Bezug:** FR-P06, FR-C05, FR-C06, FR-I07, FR-I08, FR-B08, FR-B09.

### I14 — Pilot-, Migration- und Upstream-Härtung

**Voraussetzung:** I00–I13.

**Umfang:** Alle fachlichen und Foundation-Szenarien implementieren/ausführen, Upstream-Probeupdate und Restore, Last-/Accessibility-/Realtime-/Widerruftests, menschliche Usability mit echten Pilotdaten.

**Bereich:** Integrationstestumgebung, konkrete Provider-Testinstanzen, UI- und Betriebsabnahme.

**Abnahme:** Native Plane-Flows bleiben nutzbar. End-to-End-Paket und Migrations-/Rollbackpfad bestanden oder explizit blockiert. Kein Agent behauptet eine nicht erfolgte menschliche Abnahme.

**Bezug:** PRD §18, FR-B04, FR-B09, FR-B12, FR-B14.

### I15 — Anbieterbreite und zulässiger Enterprise-Rollout

**Voraussetzung:** I14; O03/O04/O07 und L01.

**Umfang:** Getestete Basisadapter der vier Zielsysteme, konkret vereinbarte Identity-/Provisioning-/Retention-/Betriebsfähigkeiten. Vertrieb, Lizenznotice, Code-/Dependencyumfang und Marke gemäß freigegebenem Weg.

**Bereich:** Provider-/Betriebs-/Identity-Erweiterungen auf dem freigegebenen Plane-Fork.

**Abnahme:** Reale Contract-Tests pro unterstütztem Profil, dokumentierte Editionsgrenzen, Wiederherstellung und Support. Kein AGPL-/OEM-/Cloudfeature wird als automatisch geklärt angenommen.

**Bezug:** FR-I07, FR-I08, FR-B12, FR-B13.

## 3. Teststrategie

**Upstream-Baseline:** Vorhandene Prüfkommandos aus dem gewählten `AGENTS.md` ausführen. Backendtests sind dort über `docker-compose-test.yml` dokumentiert; `apps/live` enthält Vitest-Scripts. Die konkreten vorhandenen Testbereiche müssen vor dem ersten Lauf festgestellt werden. Ein Build allein ersetzt keine Funktionsprüfung.

**Neue Domain-Tests:** Issue-/Workspace-Referenzintegrität, exakte Revision, Readiness, Human-Principal, Claim/Lease/Fencing, Statusprojektion, Datenaufbewahrung, Multi-Repo-Stand und Berechtigungsentzug.

**Native Mutationstests:** Dieselbe Änderung über native UI/API, Bulk, Import/Sync und Editor-Realtime. Kein Pfad darf ein Draft-/Approval-Gate umgehen. Kritische Prüfung bleibt auch bei verspätetem Event wirksam.

**Adapterverträge:** Doppelte/ungeordnete Events, gelöschte Objekte, Rate Limit, Rechteverlust, neue Headstände, Squash, Echo und Concurrent Edit. Quelle und Vertrauensklasse von Nachweisen prüfen.

**Migration/Regression:** Echter Plane-Altbestand mit und ohne Extensionflag; Restore von Datenbank und Assets; Probe-Upstream-Bump; native Links, Filter, Editor, Cycles/Modules und bestehende Issues.

**Menschliche Prüfung:** Nach Abwesenheit orientieren, Paket konkretisieren, Decision aus Chat, Übergabe an IDE und tatsächliche Lieferung erklären. Keine Produktivitätswerte oder Usability-Ergebnisse erfinden.

## 4. Definition of Done

Nur freigegebener Umfang umgesetzt; native und neue IDs konsistent; passende Tests tatsächlich ausgeführt und Ergebnis dokumentiert; keine Draftausführung oder eigene Humanfreigabe; Migration-/Rückfallpfad geprüft; UI-Zustände vorhanden; keine zweite PM-Datenhaltung; Quellen-/Edtionsgrenzen und bekannte Defekte offen. Lizenz-/Vertriebspfad vor externer Bereitstellung freigegeben.

Die Gherkin-Dateien und JSON-Schemas in diesem Paket sind Startpunkte. Sie enthalten noch keine laufende Plane-Implementierung.
