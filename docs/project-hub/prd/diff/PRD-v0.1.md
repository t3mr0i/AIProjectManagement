# PRD — KI-native Projektzentrale für Softwareteams

**Arbeitsbezeichnung:** Project Hub. Kein beschlossener Produktname.  
**Version:** 0.1 · **Stand:** 24. September 2026  
**Status:** Ausgearbeiteter Umsetzungsentwurf; Produkt- und Architekturannahmen sind noch nicht freigegeben.  
**Zweck:** Gemeinsame Grundlage für Produktentwicklung, Design, technische Planung und schrittweise KI-gestützte Implementierung.

## 0. Wie dieses Dokument zu verwenden ist

Dieses PRD beschreibt das Zielprodukt, eine begrenzte erste nutzbare Ausbaustufe und überprüfbare Anforderungen. Es ist kein Versprechen, dass ein Agent die gesamte Anwendung in einem Durchlauf korrekt erstellt. Die Umsetzung erfolgt in vertikalen, getesteten Inkrementen gemäß `IMPLEMENTATION_PLAN.md`.

Verbindlichkeit im Dokument:

- **K — bestätigt:** Im Produktgespräch ausdrücklich vorgegeben. Änderungen brauchen eine bewusste Produktentscheidung.
- **A — Arbeitsannahme:** Konkreter Vorschlag, damit Design und Implementierung vorbereitet werden können. Nicht als Nutzerentscheidung ausgeben.
- **O — offen:** Vor dem jeweils genannten Entscheidungspunkt zu klären. Nicht stillschweigend durch einen Coding-Agenten entscheiden lassen.
- **MUSS / SOLL / KANN:** Anforderungsstärke innerhalb eines freigegebenen Release-Scopes. Ein MUSS für V1 wird dadurch nicht automatisch zum Pilotumfang.

Die Dateien `DESIGN_BRIEF.md`, `IMPLEMENTATION_PLAN.md`, `acceptance/core.feature`, die JSON-Schemas und die drei Skills ergänzen dieses PRD. Bei einem Widerspruch gelten bestätigte Vorgaben und die Sicherheitsinvarianten dieses Dokuments; der Konflikt ist vor Umsetzung aufzulösen. Quellen zu geprüften externen Funktionen und den über Mobbin betrachteten Referenzen stehen in `SOURCES.md`. Eigene Produktvorschläge werden nicht als belegte Eigenschaften bestehender Produkte dargestellt.

## 1. Produktdefinition

### 1.1 Ein Satz

Eine eigenständige Enterprise-Projektzentrale, in der Softwareteams Ziele, ausführbare Arbeitspakete, Kommunikation, Dokumente und projektübergreifende Planung gemeinsam bearbeiten, während die Entwicklung in den vorhandenen IDEs und Git-Systemen stattfindet und der tatsächliche Fortschritt automatisch sichtbar wird.

### 1.2 Das zentrale Versprechen

Menschen pflegen Absicht, Priorität und Entscheidungen. Die Plattform sammelt Ausführung und Nachweise. Ein Arbeitspaket muss nicht erneut in Chat, Ticket, Spezifikation und Statusbericht beschrieben werden.

Ein Teammitglied soll nach mehreren Tagen Abwesenheit verstehen können, was verändert wurde, warum, was tatsächlich ausgeliefert ist und wo eine Entscheidung fehlt. Ein Manager soll ein codebasiertes Paket mit der KI konkretisieren können, ohne selbst Repository-Strukturen oder Agentenbefehle bedienen zu müssen. Ein Entwickler soll dasselbe Paket in seiner IDE übernehmen und weiterentwickeln können.

### 1.3 Abgrenzung

Das Produkt ist weder eine neue IDE noch nur ein Agenten-Dashboard, ein Jira-Skin oder ein reiner Chatbot. Es ist kein Bestandteil von Lufthansa, DevPilot oder ReqPilot und übernimmt keine deren Architekturentscheidungen. Es hat einen eigenen Projektmanagement-Kern und austauschbare Anbindungen.

Die Oberfläche darf sich in Klarheit und Informationsdichte an Linear orientieren. Die Editing-Referenz Nimbalyst ist ein vom Nutzer genanntes Vorbild für bearbeitbare Inhalte neben KI-Unterstützung, keine festgelegte Codebasis. Für den Neubau wird weder ein Plane-Fork noch eine bestehende Kanban-Anwendung vorausgesetzt.

### 1.4 Zielkunden und vorläufiger Markt

**K:** Softwareteams in Unternehmen; unterschiedliche technische und fachliche Rollen arbeiten gemeinsam. Ein typisches erstes Team umfasst zwei bis vier Entwickler sowie Management und fachliche Beteiligte. Das Produkt muss mehrere Projekte und Teams abbilden können.

**A:** Der erste Pilot richtet sich an ein überschaubares Produktentwicklungsteam mit bestehendem Git-Repository, verwendbarer CI und echtem Abstimmungsbedarf. Der Pilot ist keine repräsentative Validierung des gesamten Enterprise-Marktes.

**O:** Käuferrolle, Branche, Beschaffungsvoraussetzungen, Preismodell und erster zahlender Kunde sind noch nicht festgelegt. Für die Implementierung der Kernabläufe sind sie nicht vollständig erforderlich; vor einem externen Enterprise-Rollout beeinflussen sie Hosting, Verträge, Support und Betrieb wesentlich.

## 2. Problem, Nutzen und Grenzen

### 2.1 Drei zusammenhängende Probleme

**Administrationsaufwand:** Kleine Umsetzungen können weniger menschliche Zeit benötigen als ihre mehrfache Beschreibung und Statuspflege. Das Produkt soll unnötige Wiederholung entfernen, nicht alle Entscheidungen abschaffen.

**Verlust gemeinsamer Orientierung:** Git, IDE, Chat und Planung zeigen jeweils einen Ausschnitt. Ohne Verbindung ist unklar, was gerade bearbeitet wird und welchen fachlichen Zweck eine Änderung erfüllt.

**Zu grobe oder zu feine Steuerung:** Einzelne technische Mikroschritte überfrachten Projektansichten. Eine rein grobe Roadmap verbirgt dagegen Blockaden und aktuelle Arbeit. Benötigt werden unterschiedliche Detailstufen auf derselben Datenbasis.

Diese Aussagen sind die Problemhypothesen dieses Produkts, keine hier erhobenen Marktstatistiken.

### 2.2 Drei Schulden als Gestaltungsanforderungen

| Dimension           | Gegenmaßnahme im Produkt                                                                                                      | Was ausdrücklich nicht als Beweis genügt                                                   |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Technische Schulden | Prüfungen, Änderungen, Architekturentscheidungen und bekannte Einschränkungen verbinden.                                      | Ein erfolgreich beendeter Agentenlauf.                                                     |
| Kognitive Schulden  | Verständliche Änderungsansicht, zugehörige Abläufe und überprüfbare Quellen; Verantwortlichkeit und Übergabe sichtbar halten. | Automatisch erzeugter Text oder ein gelesener Bericht als behaupteter Verständnisnachweis. |
| Intent-Schulden     | Auftrag, Ziel, Nichtziele, Entscheidung und spätere Änderungen versionieren.                                                  | Nachträglich aus Code erfundene Begründungen.                                              |

Es gibt in V1 keinen künstlichen Gesamtscore für diese Schulden. Das Produkt zeigt konkrete Lücken, etwa fehlende Begründung, ungeklärte Verantwortung oder veraltete Prüfergebnisse.

### 2.3 Nichtziele

Keine Ablösung der IDE. Kein verpflichtender eigener Coding-Agent. Kein autonomes Umsetzen von Drafts. Kein autonomes Mergen ohne menschliche Freigabe. Kein vollständiger Ersatz von Slack, Microsoft Teams, SharePoint oder ERP-Systemen in der ersten Version. Kein automatisches Erzeugen eines Tickets für jeden Tool-Aufruf. Keine individuelle Leistungsbewertung anhand von Commits, Onlinezeiten oder Agentenausgaben. Keine behauptete Konformität oder Zertifizierung, bevor diese nachgewiesen wurde.

## 3. Bestätigte Produktentscheidungen

| ID  | Bestätigte Vorgabe                                                                                                                  |
| --- | ----------------------------------------------------------------------------------------------------------------------------------- |
| K01 | Eigenständiges, grundsätzlich proprietär entwickelbares Enterprise-Produkt ohne Bindung an Lufthansa, DevPilot oder ReqPilot.       |
| K02 | Gemeinsame Grundlage für Entwickler, Manager und fachliche beziehungsweise Business-Verantwortliche.                                |
| K03 | Lebendige, Linear-nahe Übersicht mit Status und chronologischem Verlauf der tatsächlichen Arbeit.                                   |
| K04 | Build, Review und Ship bilden den sichtbaren Lieferablauf; Detailzustände müssen unterscheidbar bleiben.                            |
| K05 | Manuelle Auftragserstellung bleibt möglich. KI-gestützte Konkretisierung ist ergänzend.                                             |
| K06 | Eine gemäßigte, codekontextbezogene Variante von Matt Pococks Grill-Me-Idee unterstützt die Auftragserstellung.                     |
| K07 | Arbeitspakete beschreiben eine sinnvolle Zielrichtung; kleinere Spezifikationen und technische Details werden darunter organisiert. |
| K08 | Drafts werden nicht implementiert. Eine explizite Freigabe ist Voraussetzung der Ausführung.                                        |
| K09 | Vor einem Merge ist eine menschliche Freigabe erforderlich.                                                                         |
| K10 | Entwickler arbeiten weiter in ihrer IDE. Repository-, Spezifikations- und Statusinformationen werden synchronisiert.                |
| K11 | Gemeinsames Bearbeiten von Texten, Dokumenten und Diagrammen; KI muss relevante Änderungen lesen und interpretieren können.         |
| K12 | Teamchat, Direktnachrichten und @AI im Arbeitskontext; ausgewählte Inhalte können als Entscheidung übernommen werden.               |
| K13 | Roadmaps, mehrere Projekte und team- beziehungsweise projektübergreifende Abhängigkeiten gehören zum Produktkern.                   |
| K14 | Gemeinsamer Speicher, Dokumente, Termine und leicht auffindbare Informationen gehören zur Projektzentrale.                          |
| K15 | Adapter für Jira, Azure DevOps, GitLab, Linear und weitere Systeme; keine Abhängigkeit des Kerndatenmodells von einem Anbieter.     |
| K16 | Sichtbarkeit von Codezustand und tatsächlichem Fortschritt; geringe manuelle Pflege statt Mikromanagement.                          |
| K17 | Bestehende Produkte sind UI-/Interaktionsreferenzen. Ein Neubau ist ausdrücklich möglich.                                           |
| K18 | Review in der Zentrale erklärt Ergebnis, Änderungen und offene Punkte; technische Arbeit und Tests bleiben primär in IDE und CI.    |

## 4. Arbeitsannahmen und Entscheidungstore

| ID  | Vorgeschlagene Annahme                                                                                                             | Begründung                                                                                                                | Spätestens bestätigen                |
| --- | ---------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| A01 | Browserbasierte Desktop-Anwendung; responsive Lesen, Chat und Freigaben auf Mobilgeräten.                                          | Gemeinsamer Zugang ohne zusätzliche Entwicklungsumgebung.                                                                 | Vor der UI-Implementierung.          |
| A02 | Modularer Anwendungskern, relationale Datenbank, getrennte Hintergrund- und Ausführungsprozesse.                                   | Weniger anfängliche Betriebsflächen; klare Sicherheitsgrenzen zur Codeausführung.                                         | Vor dem technischen Grundgerüst.     |
| A03 | SaaS als erste Betriebsform, EU-Region als Pilotannahme; Ausführungsrunner kann im Kundennetz liegen.                              | Konkreter erster Betriebsweg ohne Cloudbindung im Domänenmodell.                                                          | Vor Verarbeitung echter Kundendaten. |
| A04 | GitLab als erster Codeadapter; Jira Cloud als erster externer Tracker.                                                             | Liefert den vollständigen Git-/CI-/MR-Fluss und prüft die Trennung zum Tracker. Keine vom Nutzer festgelegte Reihenfolge. | Vor Adapterentwicklung.              |
| A05 | Ein lokaler CLI-/Runner-Vertrag zuerst, keine eigenständige IDE.                                                                   | Unterschiedliche Entwicklungswerkzeuge sollen weiter nutzbar bleiben.                                                     | Vor dem ersten Ende-zu-Ende-Lauf.    |
| A06 | Bei kurzen Änderungen gilt ein leichtes Paketprofil; Details innerhalb eines freigegebenen Pakets benötigen kein neues Hauptpaket. | Der Prozess darf die ursprüngliche Bürokratie nicht neu erzeugen.                                                         | Vor Paketeditor und Policy-Modell.   |
| A07 | Deutsch und Englisch als vorbereitete UI-Sprachen; erste vollständige Produktabnahme auf Deutsch.                                  | Sprache ist keine Domain- oder Spezifikations-ID.                                                                         | Vor Content- und UI-Freeze.          |
| A08 | Basales gemeinsames Editieren und Nachrichten im Pilot; erweiterte Office-Bearbeitung und vollständige Offline-Nutzung später.     | Kernnutzen zuerst, kein Nachbau einer Office-Suite.                                                                       | Vor Release-Scope-Freigabe.          |

**O01 — Ausführungsort:** lokaler Entwicklerrechner, kundeneigener Runner oder verwalteter Runner? Der Vertrag unterstützt alle; der erste reale Weg muss gewählt werden.

**O02 — Integrationsreihenfolge:** A04 ist austauschbar. Die Architektur darf nicht GitLab-IDs als primäre Paket-IDs verwenden.

**O03 — Betriebsanforderungen:** Verpflichtendes Self-hosting, Air Gap oder besondere Datenstandorte würden A03 ändern. Nicht erst nach dem Pilot technisch prüfen.

**O04 — Rechte im Team:** Wer darf ein Paket zur Umsetzung freigeben, wer Code-Reviews bestätigen, wer Merge auslösen? Vor Pilotbetrieb als konkrete Rollenbesetzung festlegen.

**O05 — Releaseumfang und Ressourcen:** Es liegen keine belastbare Teamkapazität, Budgetgrenze oder verbindlicher Liefertermin vor. Das PRD enthält daher Reihenfolge und Abnahmebedingungen, keine erfundenen Termin- oder Kostenversprechen.

## 5. Nutzer, Aufgaben und Rechte

### 5.1 Gemeinsames Datenmodell, unterschiedliche Ansichten

| Rolle                                          | Hauptaufgabe                                                                              | Typischer Erfolg                                                                                |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Entwickler                                     | Paket in der IDE übernehmen, umsetzen, prüfen und Kontext ergänzen.                       | Kein erneutes Abschreiben des Auftrags; Änderungen und Nachweise erscheinen am richtigen Paket. |
| Fachlicher Verantwortlicher / Manager          | Ziele und gewünschtes Verhalten festlegen, priorisieren und fachliche Fragen beantworten. | Ein verständliches, ausführbares Paket entsteht ohne Git-Kenntnisse.                            |
| Technischer Lead / Reviewer                    | Auswirkungen, Abhängigkeiten und Qualität prüfen.                                         | Geprüfter Code, freigegebene Absicht und Auslieferungsstand sind eindeutig verbunden.           |
| Business Director / Portfolio-Verantwortlicher | Projekte, Meilensteine und Abhängigkeiten beurteilen.                                     | Erkennt gefährdete Vorhaben und die zugrunde liegende Ursache, ohne Mikrotasks lesen zu müssen. |
| Workspace-Admin                                | Personen, Integrationen, Richtlinien und Betrieb konfigurieren.                           | Kann Zugriffe und laufende Automatisierung begrenzen und nachvollziehen.                        |
| Gast / Stakeholder                             | Begrenzten Projektinhalt lesen oder kommentieren.                                         | Erhält notwendige Transparenz, nicht automatisch Zugriff auf alle Repositories und Gespräche.   |

Eine Person kann mehrere Rollen tragen. Ein Jobtitel ist keine automatische Berechtigung. Technische und fachliche Freigaben sind getrennte Fähigkeiten.

### 5.2 Mindestfähigkeiten

`project.read`, `package.edit`, `package.approve_execution`, `run.start`, `run.cancel`, `review.approve_code`, `review.accept_outcome`, `merge.request`, `decision.publish`, `project.plan`, `integration.manage`, `workspace.admin` werden getrennt vergeben.

Admins erhalten nicht implizit die Leserechte privater Direktnachrichten. Ein definierter administrativer Zugriff für rechtlich erforderliche oder ausdrücklich vereinbarte Betriebsfälle wäre eine separate, auditierte Funktion. Die Anwendung darf eine solche Funktion nicht als bereits vorhandene Enterprise-Eigenschaft behaupten.

## 6. Umfang und Releases

**R0 — Funktionierender Produktkern:** Projekte, Rechte, Pakete, Revisionen, Readiness/Freigabe, chronologische Übersicht und Tests mit simulierten Ereignissen. Noch keine Behauptung einer vollständigen Integration.

**R1 — Erster Team-Pilot:** Reale Git-Anbindung, IDE-/Runner-Übernahme, OpenSpec-Roundtrip, Review-/Deployment-Evidenz, Teamchat und Direktnachrichten, gemeinsamer Text-/Diagrammeditor, Upload/Suche, grundlegende Multi-Projekt-Roadmap und Abhängigkeiten. Ein Codeanbieter und ein externer Tracker werden wirklich angebunden. Ohne native KI-Ausführung muss mindestens ein konfigurierter externer Agent vom Runner kontrolliert arbeiten können.

**V1 — Enterprise-fähiger Releaseumfang:** Grundlegende und dokumentierte Adapterabdeckung für die vier genannten Systeme, robuste Berechtigungen und Identitätsintegration, Audit/Export/Löschung, Betriebswiederherstellung, Multi-Team-Planung und Integrationsadministration. Produktionsfreigabe nur nach den jeweiligen Betriebs- und Sicherheitsprüfungen.

**Spätere Erweiterungen:** Vertiefte Kapazitätsszenarien, Budgetplanung, Prognosen, weitere Editorformate, weitere Konnektoren, vollständige Self-hosting-Distribution, umfangreiche Marketplace-Funktionen. Diese Punkte nicht als fertige V1-Funktionen vermarkten.

| Fähigkeit                               | R0                        | R1                             | V1                                                |
| --------------------------------------- | ------------------------- | ------------------------------ | ------------------------------------------------- |
| Projekte, Pakete, Revisionen, Freigaben | Vollständig für Kernfluss | Realdaten und Usability        | Gehärtet                                          |
| Board/Liste und Aktivität               | Simulierte Ereignisse     | Reale Ereignisse               | Große Datenmengen, Export                         |
| OpenSpec und IDE-/Runner-Brücke         | Vertrag und Fixtures      | Echter Roundtrip               | Weitere Runner-/Providerkombinationen             |
| Chat, @AI, Entscheidungen               | Basal                     | Mit Personen und Rechten       | Moderation/Retention nach vereinbarter Policy     |
| Dokumente und Diagramme                 | Basale Formate            | Gemeinsames Editieren          | Weitere Formate nur explizit unterstützt          |
| Roadmap, Meilensteine, Abhängigkeiten   | Basal                     | Mindestens zwei reale Projekte | Mehrere Teams und Portfolios                      |
| Jira/GitLab/Linear/Azure DevOps         | Adapterverträge           | Gewählte Kombination           | Dokumentierte Basisabdeckung aller vier           |
| Identität und Mandantentrennung         | Von Beginn an             | OIDC und Sicherheitstests      | Vereinbarte Enterprise-Identität, z. B. SCIM/SAML |

## 7. Informations- und Datenmodell

### 7.1 Kernobjekte

| Objekt                  | Wesentliche Eigenschaften und Beziehungen                                                                  |
| ----------------------- | ---------------------------------------------------------------------------------------------------------- |
| Tenant / Workspace      | Sicherheitsgrenze, Mitglieder, Richtlinien, Integrationsinstanzen.                                         |
| Team                    | Mitglieder und Zuständigkeiten; kann an mehreren Projekten arbeiten.                                       |
| Portfolio / Initiative  | Gruppierung von Projekten und Zielen; kein Zwang für kleine Workspaces.                                    |
| Project                 | Ziel, Verantwortliche, Status, Termine, Repositories, Dokumente, Chats, Roadmap.                           |
| WorkPackage             | Dauerhafte Identität eines gewünschten Ergebnisses; gehört primär einem Projekt, kann andere beeinflussen. |
| PackageRevision         | Unveränderlicher Snapshot von Absicht, Verhalten, Nichtzielen, Artefakten und Codebasis.                   |
| ChangeRecord            | Konkrete Änderung unter einem Paket; kann kurz sein, ohne eigenes Hauptpaket.                              |
| Requirement / Criterion | Verifizierbare Aussage mit stabiler ID; Umsetzung und Nachweise können darauf verweisen.                   |
| Decision                | Aussage, Begründung, Quellen, entscheidende Person, Geltungsbereich, Version und Ablösung.                 |
| Document / Artifact     | Inhalt, Format, stabile Block-/Element-IDs, ACL, Revision, Paket-/Projektbezug.                            |
| Conversation / Message  | Kanal/DM/Thread, Teilnehmer, Zeit, Bearbeitungsverlauf, Selektion und Anhänge.                             |
| RepositoryBinding       | Anbieterinstanz, externe Repo-ID, zulässige Branches/Pfade, Verbindung und Fähigkeiten.                    |
| ExecutionRun            | Revision, verantwortlicher Mensch, Agent/Runner, Commitbasis, Lease, Budget, Status und Ergebnisse.        |
| Evidence                | Quelle, geprüfter Commit/Artefaktstand, Criterion-Bezug, Ergebnis, Zeit, Vertrauensklasse.                 |
| Approval                | Menschlicher Principal, konkrete Aktion, Revision, relevante Hashes, Policy-Version, Gültigkeit.           |
| Delivery                | Repo-/Artefaktmanifest, Umgebung, Deployment/Release/Freischaltung, Zustand, Zeitpunkt.                    |
| Milestone / Dependency  | Zieltermin oder Terminfenster; gerichtete Abhängigkeit mit Typ, Quelle und Bestätigung.                    |
| ExternalLink            | Abbildung interner ID auf Anbieterinstanz, Objektart und externe ID; Feldverantwortung.                    |
| Event / AuditEntry      | Technisches Ereignis bzw. revisionsfähige menschliche/administrative Aktion.                               |

### 7.2 Wichtige Regeln

Ein Paket ist nicht ein Worktree. Ein Paket kann mehrere Läufe und mehrere Repositories betreffen. Ein Worktree ist eine temporäre Arbeitsumgebung. Ein Ticket in Jira kann ein Paket repräsentieren oder nur mit ihm verknüpft sein; dieses Mapping wird konfiguriert.

Ein Paket besitzt `working_revision_id` und optional `approved_revision_id`. Beide können verschieden sein. Eine neue Arbeitsfassung ersetzt niemals stillschweigend die Grundlage eines laufenden Runs.

Ein technischer Diff ist keine ursprüngliche Absicht. Ein Report referenziert seine Quellen. Eine KI-generierte Aussage erhält die Kennzeichnung `inferred` oder `proposed`, bis sie durch passende Evidenz oder eine berechtigte Person bestätigt ist.

### 7.3 Wo Daten maßgeblich sind

| Information                                                  | Führende Stelle im Standardbetrieb                                                   |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| Paket-ID, Revision, bestätigte Absicht, Freigabe             | Plattform                                                                            |
| Priorität und fachlicher Tracker-Status im verbundenen Modus | Pro Feld explizit Plattform oder externer Tracker                                    |
| Commit, Branch, Merge Request, Mergezustand                  | Git-Anbieter                                                                         |
| Testergebnis und Pipelinezustand                             | CI-Anbieter bzw. deklarierte lokale Evidenzquelle                                    |
| Bereitgestelltes Artefakt und Umgebung                       | Deploymentquelle                                                                     |
| OpenSpec-Artefakte                                           | Versionierter Git-Snapshot; Plattform verwaltet Bearbeitungsentwurf und Sync-Zustand |
| Nachrichten, Termine, Zugriffsrechte, Uploads                | Plattform, sofern kein externer Speicher bewusst führend ist                         |

Verteilte Wahrheit ist kein verteiltes Schreibrecht auf alles. Bei widersprüchlichen Änderungen wird ein Konflikt erzeugt, statt nach Eingangszeit blind zu überschreiben.

## 8. Zustände und Sicherheitsinvarianten

### 8.1 Getrennte Zustandsachsen

Der UI-Verlauf ist verständlich; das interne Modell muss genauer sein.

**Paketlebenszyklus:** `draft`, `ready`, `active`, `review`, `completed`, `cancelled`, `archived`.

**Run:** `queued`, `claimed`, `running`, `waiting`, `failed`, `cancelled`, `finished`.

**Lieferstand:** `not_integrated`, `partially_integrated`, `integrated`, `deployed`, `released`, `rolled_back`, `unknown`.

**Zusätzliche Flags:** `blocked`, `scope_changed`, `sync_conflict`, `stale_evidence`, `integration_offline`.

Ein abgeschlossener Run ist kein abgeschlossenes Paket. Ein Merge ist kein Deployment. Ein Deployment ist nicht automatisch eine Freischaltung. Ein Paket kann fachlich abgenommen sein, aber noch auf Auslieferung warten.

### 8.2 Sichtbare Zuordnung zu Build, Review, Ship

| Sichtbarer Abschnitt  | Bedeutung                                                                                                                                     |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Drafts                | Noch keine Ausführung erlaubt; in eigener Gruppe sichtbar.                                                                                    |
| Bereit / als Nächstes | Gültig freigegeben, Voraussetzungen erfüllt; noch nicht gestartet.                                                                            |
| Build                 | Mindestens ein autorisierter Run oder menschliche Umsetzung aktiv; verbleibender Umfang sichtbar.                                             |
| Review                | Ergebnis zur Prüfung vorhanden; technische und fachliche Prüfung getrennt.                                                                    |
| Ship                  | Prüfschritte abgeschlossen bzw. Lieferung läuft; integrierte, bereitgestellte und freigeschaltete Teile unterscheiden.                        |
| Erledigt              | Das für diesen Pakettyp vereinbarte Abschlusskriterium erfüllt. Für Software standardmäßig bestätigte Auslieferung und erforderliche Abnahme. |

Ein nicht-codebezogenes Paket kann ein Dokument oder eine fachliche Entscheidung als Liefergegenstand haben. Seine Nachweise sind dann andere; Git wird nicht künstlich vorausgesetzt.

### 8.3 Unverhandelbare Invarianten

**INV-01:** Kein Code erzeugender oder ausführender Run ohne gültige Freigabe einer exakten Paketrevision. Draft-Analyse ist lesend; auch Builds, Setup-Skripte oder versteckte Vorschauen dürfen nicht aus Drafts heraus gestartet werden.

**INV-02:** Menschen können Draft-Dokumente gemeinsam bearbeiten. Ein optionaler Git-Export solcher Dokumente ist ausdrücklich ein Dokumentenexport, kein Umsetzungsauftrag. Er darf keine Produktbuilds oder Agentenimplementierungen auslösen.

**INV-03:** Ein Agent kann weder seine Ausführungsfreigabe noch die erforderliche menschliche Mergefreigabe selbst erteilen. Eine vom Modell erzeugte Zeichenfolge `actor_kind: human` ist kein Identitätsnachweis.

**INV-04:** Ausführung ist an Revision, Policy und Commitbasis gebunden. Bei Änderungen wird nur nach dokumentierter Neubewertung weitergearbeitet.

**INV-05:** Mergefreigaben sind an den geprüften Änderungsstand gebunden. Änderungen am Head, an relevanter Zielbranchbasis, Spezifikation oder Policy lösen konservativ eine erneute Prüfung aus. Kein zeitliches Rennen zwischen Prüfung und Merge.

**INV-06:** Code- und Metadatenzugriff wird vor Retrieval, Aktion und Ausgabe geprüft. Ein summarischer Bericht darf keine vertraulichen Quellen offenlegen.

**INV-07:** Mehrfach zugestellte Ereignisse und wiederholte Schreibbefehle erzeugen keine doppelten Pakete, Entscheidungen, Runs oder externen Tickets.

**INV-08:** Fehlende, widersprüchliche oder veraltete Signale werden gekennzeichnet. Sie dürfen nicht als erfolgreiche Prüfung oder Auslieferung erscheinen.

**INV-09:** Laufende lokale Arbeit ist nur sichtbar, soweit ein autorisierter Runner sie meldet. Kein verdecktes Monitoring privater Arbeitsverzeichnisse.

**INV-10:** Das System kann externe Administratoren und lokal frei ausgeführte Programme nicht durch einen UI-Schalter kontrollieren. In solchen Fällen zeigt es beobachtete Umgehungen und seine tatsächliche Durchsetzungsgrenze.

GitLab dokumentiert konfigurierbare, teilweise editionsabhängige Freigaberegeln. Unsere Adapter müssen vorhandene Schutzmechanismen prüfen; eine Plattformfreigabe allein schützt keinen ungeschützten Zielbranch. Siehe [S04](SOURCES.md#s04).

## 9. Zentrale Ende-zu-Ende-Abläufe

### J01 — Bestehendes Projekt anbinden

Ein berechtigter Nutzer erstellt ein Projekt, verbindet Repository und optional Tracker und wählt Zugriffsumfang und Datenverantwortung. Die Plattform liest Metadaten und einen definierten Commit. Sie zeigt eine Vorschau der importierten Inhalte, erkannten Beziehungen und Unsicherheiten. Der Import erzeugt keine Umsetzung und keine stillen Änderungen an Zielsystemen.

Bereits vorhandener Code wird als beobachteter Stand gekennzeichnet. Aus ihm abgeleitete Spezifikationen sind Vorschläge, nicht nachträgliche fachliche Freigaben. Historische Aktivität erhält ihr ursprüngliches Ereignisdatum und wird nicht als heutige Leistung ausgegeben.

### J02 — Paket manuell oder mit KI konkretisieren

Der Manager erstellt einen Titel und beschreibt Absicht oder gewünschtes Verhalten. Er kann sofort speichern. Ein Draft darf unvollständig sein. Optional startet er „Mit KI konkretisieren“. Die KI liest berechtigte Quellen und fragt gezielt nach offenen Entscheidungen. Sie überschreibt keine bestätigten Angaben.

Ein prüfbarer Entwurf enthält mindestens Ziel/Warum, gewünschtes Ergebnis, begrenzten Umfang und konkrete Abnahme. Eigentümer, Projekt und Standardrichtlinien werden soweit möglich übernommen. Größere Architektur- oder Sicherheitsänderungen benötigen zusätzliche technische Klärung; kleine Pakete nicht automatisch.

### J03 — Diagrammänderung wird zum Paketvorschlag

Ein Nutzer ergänzt eine fachlich relevante Verbindung oder verändert einen Eigenschaftswert in einem Architekturdiagramm. Die Plattform speichert einen strukturierten Diff. Die KI zeigt: Interpretation, betroffene Bereiche, mögliche Auswirkungen und Unsicherheit. Erst die bestätigte Interpretation wird Teil einer neuen Paketrevision.

Das Verschieben einer Box erzeugt keine Implementierungsanforderung. Auch eine semantische Diagrammänderung bleibt Draft, bis eine Revision freigegeben ist. Ein Diagramm kann mehrere Repositories betreffen; das System muss fehlende Zugriffsrechte oder unvollständige Zuordnung benennen.

### J04 — Freigeben und in der IDE übernehmen

Ein berechtigter Mensch prüft die Readiness, wählt die konkrete Revision und gibt sie zur Umsetzung frei. Die Plattform erzeugt ein unveränderliches Manifest mit Quellen, zulässigem Umfang, Codebasis, Prüfungen und Referenz auf die serverseitige Freigabe.

Der Entwickler übernimmt das Paket über CLI oder einen unterstützten IDE-Aufruf. Der Runner prüft Identität, Freigabe, Policy und aktuelle Basis, meldet die Übernahme atomar und bereitet anschließend Branch/Worktree vor. Erst dann startet ein menschlicher oder automatisierter Umsetzungslauf. Das Team sieht die Übernahme vor der ersten gemeldeten Codeänderung.

### J05 — Umsetzung, Rückfragen und Änderungen am Umfang

Run-Ereignisse aktualisieren den Paketstatus. Der Entwickler arbeitet in seiner IDE; ein konfigurierter Agent kann im Rahmen der Freigabe Teilaufgaben bearbeiten. Die Zentrale zeigt den relevanten Fortschritt, nicht jeden Tool-Aufruf.

Bei fachlicher Unsicherheit entsteht eine Frage am Paket. Ein Scope-Wechsel pausiert betroffene Aktionen. Eine neue Revision kann parallel diskutiert werden; sie darf den laufenden Auftrag nicht unsichtbar ersetzen. Nicht betroffene Arbeit kann nur weiterlaufen, wenn die neue Situation dies nach der expliziten Projektpolicy erlaubt.

### J06 — Chat wird zur Entscheidung

Im Paket- oder Projektchat wählt ein Nutzer Nachrichten aus und schreibt sinngemäß: „@AI, das Ausgewählte als Entscheidung im Paket übernehmen.“ Die KI zeigt eine kompakte Vorschau mit Entscheidung, Begründung, Quellen und Zielpaket.

Ist Aussage oder Ziel unklar, fragt sie genau dazu nach. Bei eindeutiger Anweisung und vorhandener Berechtigung kann der Nutzer die Vorschau unmittelbar bestätigen. Die Entscheidung referenziert einen stabilen Snapshot der Nachrichtenauswahl und deren Revision. Private Inhalte werden nicht unbemerkt in einen größeren Empfängerkreis kopiert.

### J07 — Ergebnis verstehen und freigeben

Die Reviewansicht zeigt ursprüngliche Absicht, aktuelle Änderung, Kriterien, Nachweise und offene Punkte. Commit-Messages fließen ein, sind aber weder alleiniger Anforderungsnachweis noch Testbeweis. Technische Detailprüfung bleibt im Git-/IDE-Werkzeug verlinkt; fachliche Abnahme findet am verständlichen Ergebnis statt.

Ein berechtigter Mensch bestätigt den relevanten Codezustand. Nach dem Merge wird der tatsächliche integrierte Commit erfasst. Erst ein Deploymentereignis belegt Bereitstellung; Freischaltung erhält einen eigenen Nachweis oder bleibt unbekannt.

### J08 — Nach Abwesenheit aufholen

Ein Nutzer öffnet „Seit meinem letzten Besuch“. Die Liste gruppiert relevante Änderungen nach Paket und Tag. Pro Paket sind Veränderung, Grund, Ergebnis und nötige Entscheidung erkennbar. Ausgeklappte Details zeigen die zugrunde liegenden Ereignisse und Quellen. Das Lesen einer Vorschau markiert nicht automatisch alle Nachrichten als gelesen.

### J09 — Projektübergreifende Änderung planen

Ein Portfolio-Verantwortlicher verbindet zwei Meilensteine durch eine bestätigte Abhängigkeit. Bei Terminänderung zeigt die Plattform potenziell betroffene Pakete/Projekte und die Berechnungsgrundlage. Eine Variante kann betrachtet werden, ohne sofort den verbindlichen Plan zu ändern. Zyklen werden verhindert oder als nicht ausführbare Abhängigkeitsstruktur markiert.

## 10. Funktionale Anforderungen

Die folgenden Anforderungen gelten im angegebenen Release. Zu jeder Anforderung gehört mindestens ein prüfbarer Fall. Die ausführlichen Kernfälle stehen zusätzlich in `acceptance/core.feature`.

### 10.1 Projekte und gemeinsame Übersicht

**FR-P01 — Workspace und Projekte [R0].** Das System MUSS mehrere Projekte pro Workspace mit Ziel, Verantwortlichen, Mitgliedern, Status und optionalen Meilensteinen verwalten. Ein neues Projekt braucht weder Repository noch Tracker. **Abnahme:** Zwei Projekte lassen sich unabhängig bearbeiten; ein nur für Projekt A berechtigter Nutzer erhält keine Inhalte aus B.

**FR-P02 — Lebendige Übersicht [R0/R1].** Die Projektstartseite MUSS aktive, bereitstehende, geprüfte und gelieferte Pakete sowie offene Entscheidungen zeigen. Ein chronologischer Bereich MUSS heute, gewählte Zeiträume und den persönlichen Besuchsmarker unterstützen. **Abnahme:** Ein real importierter Merge aktualisiert genau ein betroffenes Paket; die Details bleiben aufklappbar.

**FR-P03 — Verdichtung ohne Informationsverlust [R1].** Mehrere technische Ereignisse eines Pakets SOLLEN zusammengefasst werden. Rohereignisse und Quellen bleiben zugänglich. Wiederholte Builds dürfen nicht den gesamten Feed verdrängen. **Abnahme:** Zehn Pipelineereignisse ergeben einen verständlichen Paketverlauf und sind weiterhin einzeln auffindbar.

**FR-P04 — Nächste Arbeit [R1].** Vorgeschlagene nächste Pakete MÜSSEN anhand konfigurierter Priorität, Freigabe und bestätigter Abhängigkeiten erklärt werden. Die KI DARF keine neue Priorität ohne Bestätigung setzen. **Abnahme:** Ein blockiertes Paket wird nicht als unmittelbar ausführbar bezeichnet.

**FR-P05 — Persönliche Ansichten [R1].** Filter und gespeicherte Ansichten SOLLEN nach Team, Projekt, Verantwortlichem, Status, Zeitraum und Entscheidungstyp möglich sein. Sie dürfen das gemeinsame Objekt nicht duplizieren. **Abnahme:** Statusänderung ist in zwei gespeicherten Ansichten identisch.

**FR-P06 — Suche und Wiederfinden [R1].** Eine globale Suche MUSS Pakete, Entscheidungen, Dokumente, Nachrichten und Termine innerhalb der Rechte auffinden. Ergebnisse zeigen Typ, Projekt, Quelle und Aktualität. **Abnahme:** Dieselbe Suchanfrage liefert für unterschiedliche Rechte unterschiedliche berechtigte Ergebnisse, ohne verborgene Titel oder Trefferzahlen offenzulegen.

### 10.2 Pakete und Spezifikationen

**FR-W01 — Schneller Draft [R0].** Ein Paket MUSS mit Titel und Projekt speicherbar sein; der Nutzer kann die Absicht anschließend ergänzen. Die Oberfläche darf Vollständigkeit nicht mit Speicherbarkeit verwechseln. **Abnahme:** Ein leerer Draft wird gespeichert, kann aber nicht ausgeführt werden.

**FR-W02 — Leichtes und vertieftes Profil [R0].** Das Standardprofil MUSS Ziel, Ergebnis, Grenzen und Abnahme priorisieren. Zusätzliche Risikoinformationen werden bei Bedarf sichtbar. **Abnahme:** Eine kleine Textänderung erfordert kein Architekturdiagramm; eine Berechtigungsänderung zeigt die projektspezifischen zusätzlichen Prüfpflichten.

**FR-W03 — Moderate Klärung [R1].** Die KI SOLL vorhandene Quellen vor Rückfragen auswerten und jeweils eine zentrale Frage mit begründeter Empfehlung stellen. Nach drei Fragen wird ein speicherbarer Zwischenstand angeboten; dies ist keine erzwungene Freigabe. Nutzer können unterbrechen. **Abnahme:** Eine bereits im Projekt beschriebene unterstützte Plattform wird nicht nochmals erfragt. Die Inspirationsquelle ist [S02](SOURCES.md#s02), die konkrete Gesprächsregel hier ein eigener Entwurf.

**FR-W04 — Versionierte Absicht [R0].** Ziel, Nichtziele, Spezifikation und relevante Entscheidungen MÜSSEN revisioniert sein. Frühere Freigaben bleiben historisch nachvollziehbar. **Abnahme:** Eine geänderte Anforderung erscheint im Revisionsvergleich; die vorherige Fassung bleibt lesbar.

**FR-W05 — Ausführungsfreigabe [R0].** Nur ein berechtigter Mensch DARF eine konkrete, ausreichend vollständige Revision freigeben. Readiness-Prüfung erklärt fehlende Angaben und betroffene Policies. **Abnahme:** Direkter API-Aufruf mit Agentenidentität scheitert auch bei ausgeblendeter UI-Sperre.

**FR-W06 — Teiländerungen [R1].** Ein Paket MUSS mehrere ChangeRecords, technische Aufgaben und OpenSpec-Änderungen aufnehmen können. Neue fachliche Ziele benötigen eine Revision oder ein neues Paket; interne Handgriffe nicht automatisch. **Abnahme:** Header-Reihenfolge und zugehöriger Test erscheinen unter einem Paket, nicht als vorgeschriebene eigenständige PM-Tickets.

**FR-W07 — Brownfield-Kontext [R1].** Aus Repositoryanalyse abgeleitete Aussagen MÜSSEN Codebasis, Pfad und Status als Beobachtung/Annahme/Vorschlag tragen. **Abnahme:** Ein bestehendes Verhalten wird nicht als fachlich bestätigt ausgegeben, solange nur Code als Quelle vorliegt.

**FR-W08 — OpenSpec-Roundtrip [R1].** Unterstützte OpenSpec-Artefakte MÜSSEN importiert, editiert, exportiert und erneut importiert werden können. Unbekannte Blöcke bleiben erhalten oder blockieren einen verlustbehafteten Export sichtbar. **Abnahme:** Ein Roundtrip verändert keine unbekannten Abschnitte und verliert keine stabilen Kriterien-IDs. Formatgrundlage: [S01](SOURCES.md#s01).

**FR-W09 — Änderung während Ausführung [R1].** Ein laufender Run MUSS seine freigegebene Revision behalten. Eine neue Draft-Revision erzeugt einen Hinweis und gegebenenfalls eine Policy-Pause, nicht einen stillen Auftragstausch. **Abnahme:** Run r1 erhält nicht automatisch Anforderungen aus Revision r2.

**FR-W10 — Nicht-Code-Pakete [R1].** Pakete für Analyse, Design oder Entscheidung MÜSSEN ohne Git existieren und verifizierbare Liefergegenstände nutzen können. **Abnahme:** Ein fachliches Klärungspaket kann durch bestätigtes Entscheidungsdokument abgeschlossen werden, ohne fingierten Commit.

### 10.3 Editor, Dokumente und Diagramme

**FR-E01 — Gemeinsamer Texteditor [R1].** Dokumente MÜSSEN gleichzeitig bearbeitbar sein, mit stabilen Block-IDs, Präsenzanzeige und sicherem Wiederverbinden. **Abnahme:** Zwei Nutzer verlieren bei paralleler Eingabe keinen bestätigten Text; Verbindungsverlust wird sichtbar.

**FR-E02 — Strukturierte Diagramme [R1].** Der erste Diagrammtyp MUSS Knoten, Kanten und Eigenschaften als strukturiertes Modell speichern. Layoutinformationen werden getrennt von semantischen Eigenschaften behandelt. **Abnahme:** Positionsänderung erzeugt keinen fachlichen Änderungsauftrag; neue Kante erzeugt einen nachvollziehbaren Vorschlag.

**FR-E03 — Semantischer Änderungsvergleich [R1].** Die KI MUSS geänderte Elemente, Interpretation und Unsicherheit anzeigen, bevor daraus Anforderungen übernommen werden. **Abnahme:** Eine mehrdeutige Kante wird als Frage dargestellt, nicht automatisch als bestätigter Implementierungsbefehl.

**FR-E04 — Formatgrenzen [R1].** Das System MUSS zwischen nativ editierbar, kommentierbar, Vorschau und Download unterscheiden. Ein hochgeladenes Office-Dokument ist nicht automatisch vollständig nativ editierbar. **Abnahme:** Ein nicht unterstütztes Format wird unverändert gespeichert und korrekt gekennzeichnet.

**FR-E05 — Auswahl als Kontext [R1].** Textblöcke, Diagrammelemente und Nachrichten MÜSSEN mit stabiler Auswahlreferenz an @AI übergeben werden. **Abnahme:** Die KI bearbeitet den ausgewählten Bereich statt versehentlich das gesamte Dokument; veraltete Auswahl wird erkannt.

**FR-E06 — KI-Änderungen prüfen [R1].** KI-generierte Bearbeitungen an geteilten Artefakten MÜSSEN als Diff oder Vorschlag überprüfbar sein. **Abnahme:** Eine abgelehnte Änderung verändert die gemeinsame Fassung nicht.

### 10.4 Kommunikation und Wissen

**FR-C01 — Projektchat, Paketthreads und Direktnachrichten [R1].** Nutzer MÜSSEN direkt und in Projektkontexten kommunizieren können. Antworten, Erwähnungen und Quellenlinks bleiben beim entsprechenden Gegenstand. **Abnahme:** Ein Paketthread ist aus Paket und Chat erreichbar, ohne zwei separate Konversationen zu erzeugen.

**FR-C02 — @AI mit sichtbarem Kontext [R1].** Eine Erwähnung MUSS anzeigen, welche Auswahl, Projekte und Anhänge verwendet werden. Zusätzliche Quellen dürfen nur innerhalb bestehender Rechte einbezogen werden. **Abnahme:** Eine private Nachricht wird nicht allein durch @AI in einen öffentlichen Projektkontext aufgenommen.

**FR-C03 — Entscheidung übernehmen [R1].** Eine Entscheidung MUSS Text, Begründung, Ziel, bestätigende Person und Quellen-Snapshot enthalten. Mehrdeutige Anweisungen erzeugen eine Vorschau, keine verbindliche Buchung. **Abnahme:** Derselbe erneut gesendete Befehl erzeugt nicht zwei Entscheidungen.

**FR-C04 — Quellen nach Bearbeitung [R1].** Das spätere Editieren einer Nachricht DARF eine bereits veröffentlichte Entscheidung nicht verändern. Lösch-/Retentionregeln MÜSSEN Entscheidung und Quellenausschnitt konsistent behandeln. **Abnahme:** Der Review zeigt, dass die Quelle seit der Entscheidung bearbeitet wurde; vertrauliche gelöschte Daten werden nicht über versteckte Kopien offengelegt.

**FR-C05 — Uploads und gemeinsamer Speicher [R1].** Dateien MÜSSEN Projekt-/Paketbezug, Eigentümer, MIME-Prüfung, Scanstatus und Zugriffsrechte erhalten. Verarbeitung erfolgt erst nach erfolgreicher Sicherheitsprüfung. **Abnahme:** Ein in Quarantäne befindlicher Upload wird nicht in KI-Antworten verwendet.

**FR-C06 — Termine und Meilensteine [R1].** Projektereignisse, Fälligkeiten und Meilensteine MÜSSEN Zeitzonen und Verantwortliche tragen. Kalenderexport ist möglich; bidirektionale Kalenderintegration ist kein still vorausgesetzter Pilotumfang. **Abnahme:** Eine Anzeige in einer anderen Zeitzone verändert nicht den gespeicherten Zeitpunkt.

**FR-C07 — Benachrichtigungen [R1].** Direktes Erwähnen, Entscheidungsbedarf, Blockaden und Reviewanfragen werden gezielt zugestellt; gewöhnliche technische Ereignisse standardmäßig gebündelt. **Abnahme:** Zehn erfolgreiche Builds erzeugen nicht zehn Pushmeldungen.

### 10.5 Git, IDE und Ausführung

**FR-G01 — Repoanbindung [R1].** Repository-Verbindungen MÜSSEN Anbieterinstanz, externe ID, Branchregeln und Fähigkeiten speichern. Identität ist nicht nur der Repo-Name. **Abnahme:** Zwei gleichnamige Repositories verschiedener Instanzen bleiben getrennt.

**FR-G02 — Gemeinsamer Ursprung, getrennte Arbeitskopien [R1].** Die Plattform DARF nicht dasselbe beschreibbare Arbeitsverzeichnis wie mehrere Entwickler verwenden. Sie synchronisiert über Git und explizite Manifeste. **Abnahme:** Ein Konflikt zwischen UI-Export und IDE-Änderung wird erkannt. Technische Grundlage: [S03](SOURCES.md#s03).

**FR-G03 — IDE-/CLI-Übernahme [R1].** Ein autorisierter Nutzer MUSS ein Paket mit Referenz auf Revision und Repo-Basis übernehmen können. Die CLI ist transportierbar; IDE-spezifische Plugins sind optional. **Abnahme:** Eine Übernahme funktioniert aus zwei unterschiedlichen IDE-Arbeitsweisen über denselben CLI-Vertrag.

**FR-G04 — Atomare Übernahme und Lease [R1].** Automatisierte Bearbeitung einer exklusiven Paket-/Repoeinheit MUSS atomar übernommen werden. Lease, Heartbeat und Fencing verhindern veraltete Runner-Schreibrechte. Bewusste Zusammenarbeit ist als solche modellierbar. **Abnahme:** Zwei gleichzeitige exklusive Claims erzeugen genau einen gültigen Besitzer.

**FR-G05 — Ausführung außerhalb der PM-Anwendung [R1].** Die Zentrale MUSS einen externen Runner/Agenten kontrolliert beauftragen und dessen Zustand lesen können. Kein Webserverprozess führt Kundencode aus. **Abnahme:** Ein lokaler oder kundeneigener Runner setzt ein freigegebenes Testpaket um und meldet ein Ergebnis zurück.

**FR-G06 — Umfang und Budgets [R1].** Pro Run MÜSSEN erlaubte Repositories, Pfade, Aktionen, Laufzeit und Ausgabenlimits konfigurierbar sein. Ein Abbruch wirkt auf weitere Werkzeugaktionen und widerrufbare Zugangsdaten. **Abnahme:** Ein abgebrochener Runner kann keinen neuen Push mit abgelaufenem Run-Token veranlassen.

**FR-G07 — Sichtbarkeit vor Commit [R1].** Der Runner SOLL Übernahme und groben Arbeitsstatus vor dem ersten Commit melden. Ohne Runner bleibt lokale Arbeit ausdrücklich unbekannt. **Abnahme:** Offline-Verlust wird als veralteter Status angezeigt, nicht als weiterhin aktive Echtzeitsitzung.

**FR-G08 — Codezuordnung [R1].** Paket, ChangeRecord, Branch, Merge Request und Commit MÜSSEN stabil verknüpft sein. Branchumbenennung, Squash und Rebase dürfen diese Verbindung nicht unbemerkt lösen. **Abnahme:** Nach Squash-Merge wird der tatsächliche neue Zielcommit am Paket angezeigt.

**FR-G09 — Mehrere Repositories [R1].** Ein Paket MUSS Teilstände pro Repository zeigen. Es DARF nicht als vollständig integriert gelten, weil nur einer von mehreren erforderlichen Merge Requests gemergt ist. **Abnahme:** Backend integriert, Frontend offen erscheint als Teillieferung.

**FR-G10 — Fähigkeitsprüfung [R1].** Vor Run und Merge MUSS der Adapter notwendige Providerfähigkeiten prüfen. Fehlt eine durchsetzbare menschliche Schutzregel, ist der unterstützte Pfad read-only oder blockiert. **Abnahme:** Ein Projekt mit ungeschütztem Branch zeigt keine uneingeschränkt sichere Automatisierung an.

### 10.6 Review und Auslieferung

**FR-R01 — Verständliche Änderungsansicht [R1].** Review MUSS ursprüngliche Absicht, Verhalten vor/nach Änderung, tatsächlichen Diff, Kriterien und offene Punkte zusammenführen. Jede faktische Zusammenfassung braucht Quellen. **Abnahme:** Ein nicht ausgeführter Test wird nicht als bestanden beschrieben.

**FR-R02 — Evidenzklassen [R1].** Nachweise MÜSSEN Quelle, Commit-/Artefaktbezug, Zeit und Vertrauensklasse tragen. Lokale Selbstmeldung und providerbestätigte CI-Evidenz sind unterscheidbar. **Abnahme:** Eine lokale Agentenaussage erfüllt keinen als vertrauenswürdige CI-Prüfung definierten Gate.

**FR-R03 — Menschliche Mergefreigabe [R1].** Vor jedem produktiven Merge im unterstützten Workflow MUSS eine gültige menschliche Freigabe vorliegen. Der Agent DARF das Gate nicht selbst erfüllen. **Abnahme:** Neue Änderungen nach Freigabe erfordern erneute Freigabe bzw. die ausdrücklich konfigurierte sichere Prüfung.

**FR-R04 — Fachliche und technische Abnahme [R1].** Die beiden Prüfungen MÜSSEN getrennt erfasst werden können. Eine fachlich berechtigte Person erhält dadurch nicht automatisch Code-Merge-Rechte. **Abnahme:** Fachlich akzeptiertes Paket bleibt bei fehlendem Code-Review blockiert.

**FR-R05 — Auslieferungskette [R1].** Die Anwendung MUSS integrierten Commit, Build-Artefakt, Umgebung und Freischaltung differenzieren. Fehlende Stufen bleiben unbekannt. **Abnahme:** Ein Merge ohne Deploymentsignal erscheint nicht als produktiv. Providergrundlage: [S05](SOURCES.md#s05).

**FR-R06 — Rücknahme und Rollback [R1].** Ein Rollback MUSS die aktuelle Lieferanzeige korrigieren, ohne historische Lieferung zu löschen. Ein Revert wird verknüpft und kann einen neuen Änderungsbedarf erzeugen. **Abnahme:** Nach Rücknahme zeigt das Paket nicht unverändert „aktuell ausgeliefert“.

### 10.7 Planung und Multi-Projekt-Steuerung

**FR-M01 — Multi-Projekt-Roadmap [R1].** Nutzer MÜSSEN Projekte, Pakete und Meilensteine in einer gemeinsamen Zeitansicht betrachten und filtern können. **Abnahme:** Mindestens zwei Projekte verschiedener Teams sind in derselben Roadmap steuerbar.

**FR-M02 — Bestätigte Abhängigkeiten [R1].** Abhängigkeiten MÜSSEN Typ, Richtung, Quelle und Bestätigungsstatus tragen. AI-Vorschläge werden nicht automatisch zu harten Blockaden. **Abnahme:** Eine unbestätigte vermutete Abhängigkeit erscheint anders als eine explizit bestätigte Voraussetzung.

**FR-M03 — Terminfolgen und Varianten [V1].** Terminänderungen SOLLEN ihre direkten und transitiven Auswirkungen zeigen. Vorschauvarianten verändern den verbindlichen Plan erst nach Bestätigung. **Abnahme:** Eine verschobene Voraussetzung zeigt betroffene Nachfolger, ohne deren Termine still umzuschreiben.

**FR-M04 — Zyklen und fehlende Daten [R1].** Zyklische harte Abhängigkeiten MÜSSEN erkannt werden. Unbekannte Dauer oder Kapazität DARF nicht als verlässlicher Fertigstellungstermin erscheinen. **Abnahme:** Eine Schleife A → B → A wird mit verständlicher Erklärung zurückgewiesen.

**FR-M05 — Scrum und kontinuierlicher Fluss [R1].** Optionale Zyklen, Sprintziele und Zuordnungen MÜSSEN möglich sein. Keine Story-Point-Pflicht, kein Zwang zu Sprints, kein Blockieren einer Lieferung bis Sprintende. **Abnahme:** Ein Paket kann während eines laufenden Zyklus ausgeliefert werden.

**FR-M06 — Risiken und Entscheidungen [R1].** Projekte MÜSSEN Risiken, offene Entscheidungen und verantwortliche Personen erfassen können. Automatische Risikohinweise brauchen eine nachvollziehbare Ursache. **Abnahme:** „Meilenstein gefährdet“ verlinkt die verspätete Voraussetzung statt nur einen KI-Score anzuzeigen.

### 10.8 Integrationen und Betrieb

**FR-I01 — Eigener Betrieb ohne Tracker [R0].** Kernfunktionen MÜSSEN ohne Jira/Linear/Azure-Boards-Verbindung nutzbar sein. **Abnahme:** Ein neues Projekt kann Pakete und Roadmap vollständig nativ verwalten.

**FR-I02 — Adaptervertrag [R1].** Anbieteradapter MÜSSEN Fähigkeiten, Authentifizierung, Rate Limits, Events, Feldmapping und unterstützte Editionen deklarieren. **Abnahme:** Eine nicht unterstützte Operation ist sichtbar deaktiviert und nicht als stiller Erfolg quittiert.

**FR-I03 — Feldverantwortung [R1].** Im verbundenen Betrieb MUSS pro synchronisiertem Feld die führende Quelle feststehen. **Abnahme:** Ein Jira-geführter Prioritätswert wird nicht durch eine lokale KI-Zusammenfassung überschrieben.

**FR-I04 — Zuverlässige Ereignisverarbeitung [R1].** Webhooks MÜSSEN validiert, dedupliziert, dauerhaft angenommen, asynchron verarbeitet und nach Fehlern reconciled werden. Keine Annahme exakt einmaliger oder geordneter Zustellung. **Abnahme:** Doppelte und verspätete Events ändern den fachlichen Endzustand nicht falsch. Grundlage: [S06](SOURCES.md#s06), [S07](SOURCES.md#s07), [S08](SOURCES.md#s08).

**FR-I05 — Disconnect und Wiederverbindung [R1].** Ein Ausfall MUSS letzte erfolgreiche Synchronisierung, Rückstand und betroffene Fähigkeiten sichtbar machen. Lokale erlaubte Arbeit bleibt möglich; unsichere Aktionen bleiben gesperrt. **Abnahme:** Nach Wiederverbindung werden Lücken abgeglichen, ohne neue Duplikate anzulegen.

**FR-I06 — Import, Export, Anbieterwechsel [V1].** Pakete, Entscheidungen, Quellenreferenzen und zulässige Artefakte MÜSSEN strukturiert exportierbar sein. Externe Mappings bleiben getrennte Metadaten. **Abnahme:** Kernobjekte behalten ihre IDs nach Disconnect eines Trackers.

**FR-I07 — Identity und Audit [R0/V1].** Tenant-, Projekt- und Objektberechtigungen MÜSSEN von Beginn an durchgesetzt werden. Enterprise-Identitätsprotokolle und Provisioning werden bis V1 entsprechend O03 konkret abgenommen. Kritische Aktionen sind auditierbar. **Abnahme:** Entzug eines Zugriffs wirkt auf API, Suche, KI, Liveverbindung und folgende Runner-Aktionen.

**FR-I08 — Retention und Löschung [V1].** Inhalte, Indizes, KI-Zwischenergebnisse, Exporte und Quellenausschnitte MÜSSEN einem nachvollziehbaren Aufbewahrungs- und Löschkonzept folgen. **Abnahme:** Ein gelöschtes Dokument erscheint nicht weiter über eine ältere KI-Antwort als frei zugänglicher Quellenausschnitt.

## 11. UI- und Interaktionsanforderungen

### 11.1 Visuelle Richtung

Die Anwendung orientiert sich an der übersichtlichen, kompakten Arbeitsdarstellung der über Mobbin betrachteten [Linear-Arbeitsliste](https://mobbin.com/screens/be6c4ee4-aa93-42b4-89b3-dcfc8386f022). Der eigene Schwerpunkt liegt auf Ereignissen, Entscheidungen, Spezifikationsrevisionen und belegtem Lieferstand. Keine dekorative Dashboard-Sammlung aus großen Kennzahlenkarten.

Die [Fibery-Referenz](https://mobbin.com/screens/e1f475cd-9340-4b6d-98c3-9ad852993175) zeigt eine editierbare Mitte mit getrenntem KI-Seitenbereich; dieses Muster wird als Interaktionsreferenz genutzt, nicht als zugesagte Übereinstimmung mit dessen Funktionen. Die [Linear-Roadmap](https://mobbin.com/screens/b3aab33b-60b3-4eb5-b21d-5aa6ba3061e2) dient der Zeitnavigation, nicht als Vorlage für eine vollständig generierte Projektprognose. Detaillierte Beobachtungen und Entscheidungen: `DESIGN_BRIEF.md`.

### 11.2 Navigation

Globale Navigation: **Übersicht**, **Projekte**, **Roadmap**, **Nachrichten**, **Wissen**, **Suche**. Administration wird zurückhaltend nach Berechtigung eingeblendet. Persönliche Aufmerksamkeit und Erwähnungen sind erreichbar, ohne eine weitere dominante Navigationsstruktur zu erzeugen.

Innerhalb eines Projekts: **Aktivität**, **Arbeit**, **Roadmap**, **Wissen**, **Team**. Die Paketseite bietet **Auftrag**, **Änderungen**, **Review** und **Verlauf**; Diskussion ist als konsistentes Seitenpanel erreichbar. Nicht alle Bereiche müssen gleichzeitig nebeneinander sichtbar sein.

### 11.3 Zentrale Screens

| Screen                       | Hauptinhalt                                                     | Primäre Aktion                             |
| ---------------------------- | --------------------------------------------------------------- | ------------------------------------------ |
| S01 Workspace-Übersicht      | Projektstand, persönliche Entscheidungen, aktuelle Arbeit.      | Projekt öffnen oder Paket erstellen.       |
| S02 Projekt-Aktivität        | Gruppierter Verlauf mit Zeitraum und Quellen.                   | Änderung/Paket verstehen.                  |
| S03 Projekt-Arbeit           | Kompakte Liste, Build–Review–Ship, Drafts und nächste Pakete.   | Paket öffnen/übernehmen.                   |
| S04 Paket-Draft              | Ziel, Spezifikation, Kontext, KI-Klärung.                       | Speichern oder zur Umsetzung freigeben.    |
| S05 Paket-Build              | Freigegebene Revision, Run, Repo-Teilstände, offene Rückfragen. | In IDE öffnen / Entscheidung beantworten.  |
| S06 Paket-Review             | Vorher/nachher, Kriterien, Evidenz, Freigaben.                  | Prüfen oder zur Überarbeitung zurückgeben. |
| S07 Paket-Ship               | Commit/Artefakt/Umgebung/Freischaltung pro Teil.                | Lieferung nachvollziehen.                  |
| S08 Dokument-/Diagrammeditor | Gemeinsamer Inhalt, Auswahl, semantischer Diff, KI-Kontext.     | Änderung als Vorschlag übernehmen.         |
| S09 Chat                     | Konversation, Threads, Auswahl, @AI, Entscheidungsvorschau.     | Nachricht oder bestätigte Aktion.          |
| S10 Multi-Projekt-Roadmap    | Projekte, Meilensteine, Abhängigkeiten, Varianten.              | Planung ändern/Variante bestätigen.        |
| S11 Suche/Wissen             | Berechtigte Quellen, Filter, Quellenstatus.                     | Objekt öffnen oder referenzieren.          |
| S12 Integrationsverwaltung   | Fähigkeiten, Feldverantwortung, Sync-Zustand, Rechte.           | Verbindung prüfen/reparieren.              |

### 11.4 Anforderungen an alle Screens

Loading, Empty, Partial, Error, Permission-denied, Offline/Stale und Conflict werden gestaltet, nicht nachträglich improvisiert. Mutierende Aktionen zeigen Speichern, Synchronisieren, erfolgreich übernommen oder Konflikt. Ein optimistischer UI-Status darf keine serverseitige Freigabe vortäuschen.

Auswahl und Detailpanel dürfen Fokus und Scrollposition nicht verlieren. Tastaturbedienung, sichtbare Fokuszustände, ausreichender Kontrast und Informationen unabhängig von Farbe sind Pflicht. Ziel ist WCAG 2.2 AA für den vereinbarten Funktionsumfang; dieses Ziel ersetzt keine Prüfung. Referenz: [S09](SOURCES.md#s09).

## 12. Integration und Synchronisierung

### 12.1 Fähigkeitsmodell

Ein Adapter deklariert mindestens `read_projects`, `read_work_items`, `write_work_items`, `read_repository`, `write_spec_branch`, `read_merge_requests`, `read_checks`, `read_deployments`, `receive_events`, `verify_human_approval`, `request_merge`, `acl_discovery` und `reconcile`.

Die Fähigkeiten sind boolesch oder genauer als `supported`, `partial`, `unsupported`, `requires_configuration`. Dazu gehören dokumentierte Edition, Instanztyp und Mindestvoraussetzungen. Ein Anbietername allein ist keine Fähigkeitszusage.

### 12.2 Geplanter Adapterumfang

| System          | Geplante Basisintegration                                                                                        | Explizite Grenze                                                                       |
| --------------- | ---------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| GitLab          | Repositories, Merge Requests, Checks/Pipelines, Deploymentereignisse, Specs-Branch, menschliche Freigabeprüfung. | Cloud/Self-Managed und Editionen separat testen.                                       |
| Jira            | Projekte/Vorgänge, Kommentare, Links, Status und priorisierte Felder nach Mapping.                               | Jira Cloud und Data Center sind getrennte Profile; kein vollständiger Workflow-Ersatz. |
| Linear          | Projekte/Issues, zugehörige Felder, Kommentare und Events nach API-Fähigkeit.                                    | Ein Linear-Agentenfeature wird nicht als Voraussetzung für den Kern angenommen.        |
| Azure DevOps    | Boards-Work-Items, Repos/PRs und Pipeline-/Service-Hook-Ereignisse nach gewähltem Profil.                        | Services/Server, Policies und Versionen separat prüfen.                                |
| Generisches Git | Repository-/Spec-Roundtrip über freigegebenen Git-Zugang.                                                        | Ohne Hosting-/CI-API keine behaupteten Review- oder Deploymentnachweise.               |

Die Existenz von Event-Schnittstellen ist in offiziellen Dokumentationen belegt [S06–S08](SOURCES.md). Ihre praktische Zusammenführung wurde für dieses PRD nicht implementiert oder als funktionsfähig getestet.

### 12.3 Schreib- und Konfliktregeln

Alle internen Objekte erhalten stabile IDs. Externe Identität besteht aus Anbieter, Instanz, Objektart und externer ID. Ein Titel ist kein Schlüssel.

Schreibbefehle tragen `Idempotency-Key`, erwartete Objektversion und Korrelations-ID. Eine serverseitige Transaktion aktualisiert den Zustand und legt den zugehörigen Outbox-Eintrag an. Externe Aktionen sind wiederholbar und werden mit eindeutiger Operations-ID verfolgt.

Webhook-Annahme bestätigt erst nach dauerhafter Speicherung. Der Worker prüft Signatur, Zeitfenster, Tenantbindung und Wiederholung. Zustellung kann doppelt, verspätet oder ungeordnet sein. Fachlicher Endzustand wird nach Möglichkeit gegen den Anbieter abgeglichen. Ein Reconciliation-Job nutzt Cursor/Watermarks und einen konservativen Überlappungsbereich.

Bei zeitgleichen Änderungen gelten Feldverantwortung und Versionsprüfung. Ein Konflikt nennt beide Werte, Quellen und Zeitpunkte. Keine Synchronisationsschleife: Eigenes Echo wird anhand einer Operationskorrelation erkannt; echte externe Änderungen im gleichen Zeitfenster dürfen dabei nicht pauschal verworfen werden.

### 12.4 Git-/Dokumenten-Synchronisierung

Die Plattform speichert Arbeitsentwürfe als Dokumentrevisionen. Der OpenSpec-Adapter rendert einen stabilen Git-Snapshot auf einem expliziten Specs-/Arbeitsbranch. Export verwendet eine erwartete Basis; bei abweichendem Head erfolgt kein Force-Push.

IDE-Änderungen werden als neue importierte Revision oder Konfliktvorschlag erfasst. Ein Drei-Wege-Vergleich nutzt gemeinsame Basis, Plattformfassung und Git-Fassung. Unbekannte Blöcke oder Kommentare dürfen nicht still verloren gehen. Eine explizite Publikation bindet Revision und erzeugten Commit.

Ein Spec-Export darf ein Paket nicht implizit zur Umsetzung freigeben. Dokumentenpublikation und Ausführung sind getrennte Commands. Repository-Pipelines müssen dokumentenbezogene Änderungen entsprechend sicher behandeln; andernfalls wird Draft-Publikation deaktiviert.

## 13. Technischer Lösungsrahmen — vorgeschlagene Architektur

Dieser Abschnitt ist **A**, nicht eine bereits bestätigte Technologiefestlegung.

### 13.1 Komponenten

**Web-Anwendung:** TypeScript/React als Ausgangspunkt, mit eigenem Designsystem, starken Tabellen-/Listeninteraktionen und gemeinsamen Editorbausteinen. React ist eine mögliche Komponentenbasis [S10](SOURCES.md#s10), kein Grund, ein fertiges generisches Dashboard-Template zu übernehmen.

**Anwendungskern:** Module für Identität/ACL, Projekte/Planung, Pakete/Revisionen, Kommunikation/Wissen, Integrationen, Run-Koordination und Evidence/Delivery. Ein modularer Monolith ist der erste Vorschlag; fachliche Grenzen sollen spätere Trennung erlauben.

**Persistenz:** Relationale Datenbank für Domänenobjekte, Versionen, ACL und Outbox; Objektspeicher für Uploads und große Artefakte. Volltextsuche zuerst, semantische Suche nur zusätzlich und mit denselben Berechtigungsprüfungen. Keine Graphdatenbank allein wegen einer Abhängigkeitsansicht erzwingen.

**Hintergrundverarbeitung:** Dauerhafte Jobs für Import, Indizierung, AI-Aufträge, Reconciliation, Benachrichtigungen und Export. Retries sind begrenzt; Dead-Letter-Fälle sind administrativ sichtbar.

**Realtime:** Persistente Daten zuerst, Liveübertragung danach. Editor und Chat verwenden ein konfliktfähiges Kollaborationsprotokoll; die konkrete Bibliothek ist nach einem Spike auszuwählen. Realtime-Verbindungen prüfen Rechte auch nach Token-/Mitgliedschaftsänderungen.

**Runner:** Getrennte Sicherheitsdomäne für Repository-/Agentenarbeit. Kundeneigener oder lokaler Runner verbindet sich vorzugsweise ausgehend mit der Koordination, erhält kurzlebige, begrenzte Berechtigungen und besitzt keine globalen Plattformzugangsdaten.

### 13.2 Datenfluss

1. Nutzer oder Integration erzeugt einen autorisierten Command.
2. Anwendungskern prüft Identität, Rechte, erwartete Version und fachliche Invarianten.
3. Zustand und Outbox werden atomar gespeichert.
4. Worker führt externe Arbeit aus oder dispatcht einen freigegebenen Run.
5. Ergebnisse werden als strukturierte Ereignisse und Nachweise aufgenommen.
6. Read-Modelle aktualisieren Board, Aktivität, Roadmap und Review.
7. KI darf diese belegten Zustände erklären und Vorschläge erzeugen, aber nicht direkt fachliche Wahrheit umschreiben.

### 13.3 Tenant- und Repository-Isolation

Jeder Datensatz und jede Jobausführung besitzt eine Tenantbindung aus serverseitig vertrauenswürdiger Zuordnung. Clientparameter bestimmen niemals allein den Tenantzugriff. Suchindex, Objektspeicher, Realtime-Räume und Caches benötigen dieselbe Isolation.

PostgreSQL Row-Level Security kann als zusätzliche Datenbankgrenze dienen; privilegierte Rollen und Tabellenbesitzer können diese standardmäßig umgehen. Daher sind Runtime-Rollen, Pooling-Kontext und Tests entscheidend [S11](SOURCES.md#s11). RLS ersetzt weder Objekt-ACL noch Kontrolle beim KI-Retrieval.

Repo-Caches und Worktrees werden nicht tenantübergreifend gemeinsam beschreibbar verwendet. Ein Worktree trennt Git-Arbeitsverzeichnisse, nicht die Ausführungssicherheit [S03](SOURCES.md#s03). Kundencode gehört in einen begrenzten Runner/Sandbox-Kontext mit restriktivem Netzwerk und Dateizugriff.

### 13.4 API-Designvorgaben

Die nachfolgenden Routen sind eigene Entwürfe, keine vorhandenen API-Funktionen:

| Command / Query                            | Zweck und Schutz                                                                        |
| ------------------------------------------ | --------------------------------------------------------------------------------------- |
| `POST /v1/projects`                        | Projekt erstellen; Workspace-Recht erforderlich.                                        |
| `POST /v1/packages`                        | Draft anlegen; kein Run als Nebenwirkung.                                               |
| `POST /v1/packages/{id}/revisions`         | Revision mit erwarteter Vorversion speichern.                                           |
| `POST /v1/packages/{id}/approve-execution` | Menschliche Freigabe für Revision, Scope und Policy.                                    |
| `POST /v1/packages/{id}/claims`            | Atomare Übernahme mit lease-/runnergebundener Antwort.                                  |
| `POST /v1/runs`                            | Gültige Freigabe, Claim, Baseline und erlaubten Runner prüfen.                          |
| `POST /v1/runs/{id}/cancel`                | Weitere Aktionen sperren und Runnerabbruch auslösen.                                    |
| `POST /v1/decisions/preview`               | Quellengebundenen Vorschlag erzeugen; noch kein gemeinsamer Beschluss.                  |
| `POST /v1/decisions`                       | Bestätigten, berechtigten Vorschlag idempotent veröffentlichen.                         |
| `POST /v1/reviews/{id}/approve`            | Mensch, Rechte und exakt geprüften Stand validieren.                                    |
| `POST /v1/merge-requests/{id}/merge`       | Letzte providerseitige Prüfung; Compare-and-set auf erwarteten Head soweit unterstützt. |
| `GET /v1/projects/{id}/activity`           | Berechtigten Verlauf nach Cursor und Zeitraum lesen.                                    |
| `GET /v1/packages/{id}/delivery`           | Aggregierten sowie repo-/umgebungsspezifischen Lieferstand lesen.                       |
| `POST /v1/integrations/{id}/events`        | Nur nach korrekter Anbieter-Authentisierung und dauerhafter Annahme.                    |

Statuscodes sind konsistent: 401 nicht authentisiert, 403 nicht berechtigt, 409 Versions-/Claimkonflikt, 422 fachlich nicht ausführbar, 429 Limit. 202 bedeutet angenommen, nicht erfolgreich abgeschlossen. Fehler liefern einen stabilen Code und eine verständliche Erklärung, keine Geheimnisse.

### 13.5 Beispiel für Run-Freigabe

Die Freigabe bindet Paketrevision, deren Inhalts-Hash, Policy-Version, verantwortlichen Menschen, genehmigte Repository-Basen und zulässige Aktionen. Ein Run-Token referenziert diese serverseitige Freigabe. Das Manifest im Repository ist eine Arbeitsgrundlage, kein selbstsignierter Berechtigungsnachweis.

Für Merge wird zusätzlich der überprüfte Quell-Head und der relevante Zielstand gebunden. Bei mehreren Repositories gibt es ein Manifest der erforderlichen Teile. Eine allgemeine atomare Transaktion über mehrere Git-Anbieter wird nicht behauptet; Teillieferungen und Rollbackpläne sind explizit.

## 14. KI-Verhalten und Skills

### 14.1 Vier klar getrennte KI-Aufgaben

**Konkretisieren:** Quellen lesen, Lücken finden, Fragen stellen und Draft-Artefakte vorschlagen.

**Interpretieren:** Ausgewählte Dokument-/Diagrammänderungen erklären und verifizierbare Anforderungen vorschlagen.

**Ausführen:** Nur ein freigegebenes, begrenztes Paket über autorisierten Runner bearbeiten. IDE- und Agentenwahl bleiben austauschbar.

**Berichten:** Tatsächliche Änderungen, Nachweise, offene Fragen und Entscheidungen verständlich zusammenführen.

Kein universeller Agent erhält pauschal alle Werkzeuge und Quellen. Pro Aufgabe werden Rechte, Kontext und Toolumfang minimiert. Modelle und Anbieter werden über eine austauschbare interne Schnittstelle angesprochen; konkrete Modelle und Kosten sind nicht Teil bestätigter Produktanforderungen.

### 14.2 Quellen, Unsicherheit und gemeinsamer Chat

KI-Ausgaben unterscheiden `observed`, `confirmed`, `inferred` und `proposed`. Tatsachenbehauptungen zum Projekt tragen Objekt-/Quellenreferenzen. Aus widersprüchlichen Angaben entsteht eine Klärung, keine stille Auswahl.

Wenn eine KI-Antwort in einem gemeinsamen Kanal erscheint, muss ihre Informationsgrundlage für den Empfängerkreis freigegeben sein. Die Rechte des fragenden Nutzers allein reichen nicht. Fehlt eine Quelle für alle Teilnehmer, kann ein berechtigter Nutzer eine ausdrücklich zur Weitergabe geprüfte Zusammenfassung veröffentlichen. Die KI erledigt diese Freigabe nicht selbst.

Private DMs gehören nicht automatisch zum Kontext eines Projekt-Agenten. Der Kontextbereich ist sichtbar und editierbar. Prompts und Dokumentinhalte dürfen keine Plattformrechte, Systemregeln oder Toolfreigaben erweitern.

### 14.3 Moderate Klärung statt Endlosinterview

Der Klärungsskill untersucht zuerst vorhandenen Kontext. Er priorisiert fehlendes Ergebnis, wesentliche Nichtziele, Akzeptanz, Zuständigkeit und relevante Folgen. Pro Runde eine wesentliche Frage. Eine Empfehlung wird als Vorschlag gekennzeichnet. Nach drei Fragen entsteht ein Zwischenstand; weitere Klärung nur, wenn echte Blocker übrig sind oder der Nutzer sie aktiv fortsetzt.

Matt Pococks dokumentierter Skill stellt Fragen einzeln und verweist auf Codeanalyse statt unnötiger Rückfragen [S02](SOURCES.md#s02). Die reduzierte Intensität, persistente Paketstruktur und Rechteprüfung sind unsere eigenen Produktentscheidungen.

### 14.4 Skills sind keine Sicherheitsgrenze

Im Paket liegen eigenständig formulierte Entwürfe für `package-clarify`, `package-execute` und `package-handoff`. Sie beschreiben gewünschtes Agentenverhalten. Backend, Providerpolicy und Runner müssen die Invarianten unabhängig vom Prompt durchsetzen.

Geladene Skills werden versioniert und administrativ freigegeben. Ein Repository kann nicht durch eine neue Skill-Datei zusätzliche Plattformrechte erhalten. Skills und Toolbeschreibungen sind bei Updates erneut zu prüfen.

### 14.5 KI-Qualitätssicherung

Vor Pilotbetrieb gibt es einen festen Evaluationssatz aus mindestens folgenden Situationen: unvollständiger Auftrag, vorhandene Antwort im Repository, widersprüchliche Dokumente, unbekannte ursprüngliche Absicht, rein optische Diagrammänderung, semantische Änderung, private Quellinformation, falsche Commit-Behauptung, fehlender Test und Scope-Wechsel während Run.

Die KI muss korrekte Entscheidungen zum Fragetyp, Quellenstatus und erlaubten Handlungsumfang liefern. Sprachliche Plausibilität allein besteht keinen Test. Modell-/Promptwechsel durchlaufen dieselbe Evaluation; Fortschrittsmeldungen dürfen bei Wechsel nicht ihre faktische Bedeutung ändern.

## 15. Sicherheit, Datenschutz und Enterprise-Betrieb

### 15.1 Mindestkontrollen

Authentisierung und Autorisierung auf jeder API-/Job-/Realtime-Aktion. Verbindungen und Zugangsdaten pro Tenant, minimale Rechte, kurzlebige Tokens wo möglich, Rotation und Widerruf. Geheimnisse nicht im Prompt, Git, Browserlog oder Ereignistext speichern.

Uploadprüfung vor Extraktion und Indizierung. Schutz vor Pfadmanipulation, SSRF und unkontrollierten externen Fetches in Import und KI-Tools. Codeanalyse führt Repositoryskripte nicht automatisch aus. Der auszuführende Projektcode gilt unabhängig vom Repoeigentümer als nicht vertrauenswürdig für den Plattformserver.

Inhaltsbasierte Prompt-Injection aus Repositories, Nachrichten oder Dokumenten wird als Dateninhalt behandelt. Rechte und Toolaktionen bleiben außerhalb des Modells kontrolliert. Audit protokolliert menschliche Freigaben, Rechteänderungen, externe Writes, Scope-Wechsel, Runstart/Abbruch und Merge.

### 15.2 Suche und abgeleitete Informationen

Berechtigungen gelten auch für Titel, Snippets, Embeddings, Chatantworten, Caches, Benachrichtigungen und Abhängigkeitsgraphen. Ein verborgener Projektname darf nicht durch eine sichtbare Abhängigkeitskante verraten werden.

Ein ausdrücklich freigegebener anonymer Blocker wie „externe Voraussetzung offen“ kann sichtbar sein, sofern die Projektpolicy dies erlaubt. Die Existenz einer geheimen Verbindung darf sonst nicht als Nebenkanal offengelegt werden.

### 15.3 Aufbewahrung und Portabilität

Retention ist getrennt für fachliche Objekte, Nachrichten, Audit, Runlogs und Rohereignisse zu konfigurieren. Löschung muss Indizes, abgeleitete Ausschnitte und Exportverfügbarkeit berücksichtigen. Für Backups ist eine dokumentierte Wiederherstellungs- und Ablaufregel erforderlich.

Vor echten Kundendaten sind Datenflüsse zu KI-Anbietern, Auftragsverarbeitung, Datenstandorte und zulässige Speicherung zu entscheiden. Dieses PRD stellt keine rechtliche Freigabe, Datenschutzprüfung oder Zertifizierung dar.

### 15.4 Betriebsfähigkeit

Healthchecks für Web, Worker, Datenbank, Queue und Adapter. Sichtbarer Rückstand pro Integration. Strukturierte Logs mit Korrelations-IDs und ohne geheime Inhalte. Wiederanlauf unterbrochener Jobs ist idempotent. Datenbankschemata benötigen getestete Migrationen und Rückfallstrategie.

Vor externem Rollout: Restoreprobe, Tenant-Isolationstest, Berechtigungsentzug während laufender Sitzung, Runabbruch, Provider-Rate-Limit-Szenario und geplanter Ausfall eines Adapters. Support darf keine produktiven Probleme durch unprotokollierte globale Rechte lösen.

## 16. Nichtfunktionale Ziele

Die folgenden Werte sind **vorgeschlagene Abnahmeziele**, keine gemessene Leistung und kein Kunden-SLA.

**Testprofil A:** Ein Tenant mit 50 Projekten, 10.000 Paketen, 100.000 Nachrichten und 1 Million normalisierten Ereignissen; 100 gleichzeitig verbundene Nutzer; Rechte- und Quellenverteilung realistisch, nicht nur öffentliche Daten. Lastprofil und Infrastruktur müssen im Testbericht genannt werden.

| ID     | Ziel                                                                                                              | Prüfmethode                                                            |
| ------ | ----------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| NFR-01 | Kritische Listen-/Detail-Reads serverseitig p95 ≤ 500 ms im Testprofil A, ohne Provider- oder Modelllaufzeit.     | Reproduzierbarer Lasttest mit Datenbank-/Cachezustand.                 |
| NFR-02 | Nutzbare Projektansicht p95 ≤ 2 s unter dokumentiertem Desktop-Netzprofil.                                        | Browsermessung vom Navigationsstart bis verwendbarem Hauptinhalt.      |
| NFR-03 | 95 % dauerhaft angenommener Normalereignisse innerhalb von 10 s in der Liveansicht sichtbar.                      | Eingangszeitpunkt bis Read-Modell; Backfill separat.                   |
| NFR-04 | Berechtigungsentzug wirkt auf neue Abfragen sofort nach Commit; bestehende Streams innerhalb von 60 s widerrufen. | Test mit zwei Sessions, Suche, Chat und Runner.                        |
| NFR-05 | Keine bestätigte Dokumentänderung geht bei Reconnect verloren.                                                    | Simulierte Netzabbrüche und parallele Bearbeitung.                     |
| NFR-06 | WCAG 2.2 AA für die vereinbarten Kernwege.                                                                        | Automatisierte Checks plus manuelle Tastatur-/Screenreaderprüfung.     |
| NFR-07 | Vorgeschlagenes V1-Betriebsziel 99,9 % monatliche Kernverfügbarkeit; RPO ≤ 1 h, RTO ≤ 4 h.                        | Erst nach Infrastruktur-/Backupentscheidung verbindlich; Restoreübung. |
| NFR-08 | Kein Cross-Tenant-Zugriff in negativen API-, Index-, Cache-, Blob- und Realtime-Tests.                            | Sicherheitstestkatalog; Null-Toleranz für gefundene Isolationfehler.   |
| NFR-09 | Keine Kernaktion ausschließlich per Drag-and-drop oder Farbe bedienbar.                                           | Manuelle Tastaturabnahme; Textalternativen für Graphen.                |
| NFR-10 | KI-Aufgaben besitzen Timeout, Budget, Abbruch und verständlichen Fehlerstatus.                                    | Fehler-/Limitinjektion im Provideradapter.                             |

## 17. Produktmetriken und Pilotbewertung

### 17.1 Primäre Messfrage

Sinkt die menschliche Zeit für Beschreibung, Rückfragen zur Orientierung und Statuspflege, ohne dass Entscheidungen, Qualität oder Nachvollziehbarkeit schlechter werden?

### 17.2 Messgrößen

| Messgröße              | Definition                                                                                         | Vorgeschlagenes Pilotsignal                                                          |
| ---------------------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Administrationszeit    | Menschliche Minuten für Paket-/Ticket-/Statuspflege, getrennt von fachlicher Entscheidung.         | Median im vergleichbaren Direkt-/Standardpfad mindestens 30 % geringer als Baseline. |
| Zeit bis Orientierung  | Zeit, um Änderungen, Gründe und offene Entscheidungen eines Zeitraums korrekt wiederzugeben.       | Median ≤ 3 Minuten für ein abgegrenztes Projekt nach drei Tagen Abwesenheit.         |
| Vorab-Sichtbarkeit     | Anteil autorisierter Umsetzungen, deren Übernahme vor erster gemeldeter Codeänderung sichtbar ist. | ≥ 95 % bei aktiv angebundenem Runner; unbekannte lokale Arbeit separat.              |
| Nachweisabdeckung      | Gelieferte Pakete mit passender Revision, menschlicher Freigabe und Lieferbeleg.                   | 100 % im kontrollierten Pilotpfad.                                                   |
| Erstnutzung            | Manager erstellt einen ausreichenden Draft ohne Git-/CLI-Hilfe.                                    | Mindestens vier von fünf Testpersonen schaffen das vereinbarte Szenario.             |
| Qualitätsschutz        | Regressionen, Reverts und kritische Nacharbeit nach vergleichbarem Umfang.                         | Keine akzeptierte Verschlechterung; kleine Stichprobe ausdrücklich benennen.         |
| Synchronisationspflege | Minuten zur manuellen Korrektur inkonsistenter Stati/Mappings.                                     | Erfassen und pro Fehlertyp auswerten, nicht im allgemeinen Zeitgewinn verstecken.    |

Kein Durchsatzvergleich anhand von Ticketzahl, wenn sich die Granularität ändert. Keine personenbezogene Produktivitätsrangliste. Ein kurzer Pilot zeigt Praxistauglichkeit und Probleme, keinen robusten kausalen Forschungsnachweis.

## 18. Pilot- und Releaseabnahme

Der End-to-End-Pilot MUSS mindestens zwei Projekte, vier Rollen, zwei Repositories und einen externen Tracker enthalten. Ein Paket betrifft beide Repositories. Ein zweites Paket ist nicht-codebezogen. Ein drittes Paket bleibt bewusst im Draft.

Der Ablauf MUSS reale Integration und simulierte Fehler kombinieren: Manager entwirft, KI klärt, Mensch gibt frei, Entwickler übernimmt, Agent oder Mensch setzt um, Scope-Frage entsteht, Entscheidung wird aus Chat übernommen, Review belegt Änderungen, Mensch bestätigt, Merge und Deployment werden getrennt beobachtet.

**Pilotfreigabe:** Kein Draft-Run, kein agentisch erteiltes Human-Approval, keine Datenlecks in den definierten Negativtests, kein verlorener Roundtripinhalt, keine falsche Shipped-Anzeige, nachgewiesene Wiederherstellung des Integrationszustands nach Ausfall. Kernusability wird mit Menschen geprüft, nicht nur mit automatisierten Tests.

**V1-Freigabe:** Zusätzlich vereinbarte Anbieterabdeckung, Identitäts-/Retention-/Auditfunktionen, Betriebsnachweise, dokumentierte Grenzen, Migrationsfähigkeit und Abschluss der blockierenden offenen Entscheidungen. Ein optisch fertiger Prototyp erfüllt diese Freigabe nicht.

## 19. Risiken und Gegenmaßnahmen

| Risiko                                         | Frühindikator                                                        | Gegenmaßnahme / Entscheidung                                                                  |
| ---------------------------------------------- | -------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| Wieder neue Ticketbürokratie                   | Jeder kleine Change erzeugt viele verpflichtende Artefakte.          | Leichtes Profil; technische Details unter Paket; Pflegezeit messen.                           |
| Zu breiter Erstumfang                          | Editor, Chat, fünf Adapter und Portfolio gleichzeitig unvollständig. | Vertikale Inkremente; echte Adapter zuerst in einer gewählten Kombination.                    |
| Verlorene Absicht                              | KI aktualisiert Specs passend zum Code, ohne Änderung zu markieren.  | Immutable Revisionen und explizite Neu-Freigabe.                                              |
| Falscher Fortschritt                           | Agentenmeldungen ersetzen CI-/Deployment-Evidenz.                    | Getrennte Zustandsachsen, Quellenklassen und Stale-Anzeigen.                                  |
| Vertrauliche Information im Teamchat           | KI verwendet private Quelle für gemeinsame Antwort.                  | Empfängerkreisprüfung vor Retrieval/Publikation; private Antwort oder ausdrückliche Freigabe. |
| Tool-/Anbieterbindung                          | Domänenmodell besteht aus GitLab-/Jira-Feldern.                      | Eigene IDs, Adapterfähigkeiten, Roundtrip mit zweitem Anbieter früh testen.                   |
| KI-Code greift Plattform an                    | Repo-Setup läuft im Backendcontainer.                                | Separate Runnergrenze; keine Ausführung im PM-Kern.                                           |
| Nicht durchsetzbare Freigaben                  | Zielbranch erlaubt beliebige direkte Pushes.                         | Providerprüfung, read-only/blockierter Automatikmodus, nachvollziehbarer Hinweis.             |
| Hohe laufende KI-Kosten                        | Vollrepoanalyse bei jeder Nachricht.                                 | Inkrementelle Kontexte, Caching nach Revision und ACL, explizite Budgets.                     |
| Verwechslung von Verständnis und Dokumentation | Viele Berichte, niemand kann Änderungen erklären.                    | Orientierungstests und gezielte Übergabe bei relevanten Änderungen.                           |
| Überladene Linear-Kopie                        | Jede Funktion erhält Sidebarpunkt oder Kennzahlenkarte.              | Aufgabenbezogene Navigation, progressive Details, Szenariotests statt Screenshots allein.     |

## 20. Noch offene Entscheidungen — keine verborgenen Lücken

Für einen lokalen Produktprototyp fehlen keine grundlegenden Produktinformationen. Die hier festgelegten Arbeitsannahmen erlauben Vorbereitung von Design, Datenmodell und Testfällen.

Vor einem echten Implementierungsstart müssen A01/A02 und die erste Ausführungskombination bestätigt sein. Vor Kundendaten müssen Betriebsmodell, Identität, Datenflüsse und Rechtebesetzung entschieden sein. Vor breitem Verkauf müssen Käufer, Editionen, Support, Preismodell und vollständige Integrationszusagen geklärt sein.

Die wichtigste technische Vorprüfung betrifft nicht die Farbe des Boards, sondern den sicheren Roundtrip **gemeinsamer Editor → Git-Specs → IDE → neue Revision → Review → Liefernachweis**. Der wichtigste Produkttest betrifft die Frage, ob das Team dadurch tatsächlich weniger nachpflegt und schneller versteht, was passiert ist.

## 21. Übergabe an ein KI-Entwicklungsteam

Ein Coding-Agent beginnt mit `IMPLEMENTATION_PLAN.md`, übernimmt genau ein freigegebenes Inkrement und liest nur die dafür relevanten Anforderungen, Schemas und Abnahmefälle. Er darf bestätigte Vorgaben nicht aus Bequemlichkeit verändern und fehlende Produktentscheidungen nicht als technische Selbstverständlichkeit behandeln.

Jedes Inkrement liefert implementiertes Verhalten, passende Tests, eine dokumentierte Migration bei Datenänderungen und einen kurzen Bericht über verifizierte beziehungsweise noch offene Punkte. Schemas und Gherkin-Dateien dieses Pakets sind Startverträge und Testspezifikationen, keine bereits ausführbare Anwendung und keine abgeschlossene Sicherheitsprüfung.

Ein möglicher Startauftrag steht in `BOOTSTRAP.md`. Er muss von einem Menschen ausdrücklich freigegeben werden, bevor daraus Umsetzung oder externe Änderungen erfolgen.
