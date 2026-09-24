# Plane Foundation — Bestand, Erweiterungen und Quellenstand

Version 0.2 · 24. September 2026. Statische Quellenprüfung; kein ausgeführter Plane-Build.

## 1. Fixierter Untersuchungsstand

- Repository: `makeplane/plane`.
- Default-Branch bei Abfrage: `preview`.
- Untersuchter Commit: `d616636119d20a531a815c78d364bdb47d552a2d`.
- Commitdatum: `2026-09-24T09:45:14Z`.
- `package.json`: Version `1.4.2`; dies wird **nicht** als Bestätigung eines Release-Tags verwendet.
- Root-Manifest: Node `>=22.22.0`, pnpm `11.10.0` mit Integrity-Suffix. Die konkrete Toolchain wird aus dem freigegebenen Lock-/Manifeststand übernommen, nicht neu gewählt.
- Status: **Analysebasis, vorläufig.** Kein Release-, Security- oder Betriebszertifikat.

Primärquellen P01–P10 wurden für diese Anpassung gezielt gelesen. Der vollständige Repository-Build, Testlauf und eine vollständige Dateiauditierung wurden nicht durchgeführt. Aussagen über fehlende Gesamtfunktionen sind deshalb als „nicht als geliefert eingeplant“ formuliert, nicht als Behauptung, das gesamte Repository enthalte sie nirgends.

## 2. Capability-Matrix

**Ü = übernehmen und regressionsprüfen. E = vorhandene Basis erweitern. N = eigene Funktion einplanen. P = Umfang/Edition/Eignung vor Implementierung prüfen.** Ein Ü ist kein bestandener Laufzeittest.

| Bereich                               | Klasse | Statisch belegte Basis                                                         | Eigene Ergänzung / Abnahme                                                                                                   |
| ------------------------------------- | ------ | ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| Benutzer und Memberships              | Ü/E    | `User`, `WorkspaceMember`, `ProjectMember` in Modellexporten. P04              | Fachliche Capability-Prüfung für Approvals und private Kommunikationsbereiche.                                               |
| Workspace / Projekte                  | Ü      | `Workspace`, `Project` und zugehörige Modelle. P04                             | Kein zweiter Katalog; Member-/Isolationstests.                                                                               |
| Issues / Eigenschaften                | Ü/E    | `Issue`, Titel, Beschreibung, Priority, Assignees, States, Draftflag. P05      | 1:1-Paketprofil und sichere Mutations-/Revisionslogik.                                                                       |
| Parent/Sub-Issues                     | Ü/E    | Parent-Relation im Issue-Modell. P05                                           | Ergebnisverdichtung; nicht jeder interne Agentenschritt wird Sub-Issue.                                                      |
| States                                | Ü/E    | Gruppen und Projekt-State-Modell. P06                                          | Mapping zu Phasen, aber keine neue globale StateGroup-Enum.                                                                  |
| Cycles / Modules                      | Ü      | Modelle und Zuordnungen im Export. P04                                         | Nutzung im bestehenden Scrum-/Planungskontext abnehmen.                                                                      |
| Views / native Aktivität              | Ü/E    | `IssueView`, `IssueActivity`, Notifications. P04                               | Chronologische, quellenbelegte Zusammenfassung und persönliche Besuchsmarker.                                                |
| Pages / Versionen / Assets            | Ü/E    | `Page`, `ProjectPage`, `PageVersion`, `FileAsset`, `DescriptionVersion`. P04   | Zugriffe, Format-Roundtrip und Paket-Snapshots prüfen; keine parallele vollständige Speicherhierarchie.                      |
| Rich-Text-Kollaboration               | Ü/E    | TipTap, Yjs, Hocuspocus in Editor-/Live-Manifests. P08/P09                     | Diagrammmodell, semantischer Diff, Genehmigungsbezug und ACL-Reconnect.                                                      |
| Native Beziehungen                    | E/P    | `IssueRelation`, `IssueBlocker` im Export. P04                                 | Cross-Projekt-/Teamsemantik, Zyklen, vertrauliche Knoten und Szenarien gesondert.                                            |
| Portfolio und Roadmap                 | E/N/P  | Projekte, Termine, Cycles/Modules als Datenbasis. P04/P05                      | Kein Beleg einer vollständigen Enterprise-Portfoliofunktion; eigene dünne Planungsbeziehungen/UI vorsehen.                   |
| Kommentare                            | Ü/E    | `IssueComment`, Mentions, Reactions. P04                                       | Als Diskussions-/Quellenkontext erhalten.                                                                                    |
| Teamchat / private DMs / @AI          | N/P    | Keine vollständige gewünschte Chatfunktion durch die gelesenen Quellen belegt. | Richtiger Nachrichten-/Teilnehmer-/Retentionvertrag; neue KI-Vorschlags-/Entscheidungslogik.                                 |
| OpenSpec / Runner / Claims            | N/P    | Unsere gesicherte Semantik nicht als gegeben nachgewiesen.                     | Paketmanifest, Roundtrip, Lease/Fencing, exakte Freigabe, isolierte Ausführung.                                              |
| Review-/Deliverybelege                | N/E    | Native Issue-/Link-/Activity-Basis vorhanden. P04                              | Eigene Evidence-/Approval-/Deliverymodelle; native „Done“-Information reicht nicht.                                          |
| Drittanbieterintegration              | E/P    | GitHub-/Slack-bezogene Modelle sowie Webhook-/Tokenmodelle exportiert. P04     | Verfügbarkeit, Richtungen, Credentials, Upstream-UI und Edition wirklich prüfen; vier Konnektoren nicht als fertig ausgeben. |
| Enterprise Identity / Audit / Betrieb | P/E    | Allgemeine Auth-, API- und Basismodelle vorhanden. P04                         | SAML/OIDC/SCIM, private Inhalte, Retention, HA und Compliance nicht aus Marketing ableiten.                                  |

## 3. Codebereiche für die Implementierung

| Bestehender Pfad / Paket                                      | Geprüfter Bezug                                               | Beabsichtigte Arbeit                                                                                                               |
| ------------------------------------------------------------- | ------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `AGENTS.md`                                                   | Befehle, Codekonventionen, Testhinweise.                      | Vor jeder Agentenarbeit lesen; eigene Produktregeln ergänzen, nicht Upstream-Anweisungen blind überschreiben.                      |
| `apps/web/package.json`                                       | React Router, Workspace-Pakete und Scripts.                   | Routing/Shell und neue Details im bestehenden Appkontext. Konkrete Routendateien zuerst im Checkout finden.                        |
| `apps/api/plane/db/models/__init__.py`                        | Native Domänenmodelle.                                        | Existierende Beziehungen prüfen; neue Extension-Modelle additiv verknüpfen.                                                        |
| `apps/api/plane/db/models/issue.py`                           | Native Issue-Identität, Felder, Draftfilter, Speichersemanik. | Keine neue Issue-Engine; Änderungen und Konflikte an sicheren Integrationspunkten behandeln.                                       |
| `apps/api/plane/db/models/state.py`                           | StateGroup und projektlokale States.                          | Gruppen erhalten, projektlokales Mapping ergänzen.                                                                                 |
| `packages/editor/package.json`                                | Editor- und Kollaborationsbasis.                              | Vorhandene Nodes/Serialisierung prüfen, gezielte Erweiterung.                                                                      |
| `apps/live/package.json`                                      | Vorhandener Liveprozess und Tests.                            | Kontext-/ACL-/Revocationprüfung bei neuen Liveinhalten. Keine Annahme, dass ein Editor-Raum private Chats bereits sicher abbildet. |
| `packages/shared-state`, `@plane/blocks`, `@makeplane/propel` | In AGENTS/Manifest dokumentiert.                              | Bestehende Stores und Basiskomponenten nutzen. Nicht in diesem Paket als vollständig auditiert ausgegeben.                         |
| `docker-compose-local.yml`                                    | Daten-/Jobservices und Migrator.                              | Lokale Baseline reproduzieren; Produktionsprofile und Images separat prüfen.                                                       |

**Neu vorgesehene Bereiche, noch nicht vorhanden/implementiert:** Paketprofil-/Revisions-/Approvalmodule, Runner/CLI-Vertrag, Konnektorkorrelation, Chat-/Entscheidungsdomain und übergreifende Planungsrelationen. Ein möglicher Django-Appname `plane/package_flow` ist ein Vorschlag, kein Upstream-Pfadnachweis.

## 4. Wichtige Designentscheidungen für Daten

**Paket = Issue + Extension.** Die native UUID bleibt der Bezug für UI, API, Gitmanifest und externe Links. Keine neue autonome `WorkPackage`-ID. Snapshots sind unveränderliche historische Zustände, nicht eine zweite live synchronisierte Kopie des Issue-Objekts.

**State ≠ Freigabe ≠ Lieferung.** Native State-Änderungen bleiben Planungsinformation. Ausführung benötigt eine serverseitige Approval-Ressource. „Done“ kann eine fachliche Rückmeldung sein, beweist aber kein Deployment.

**Native Mutationen berücksichtigen.** Native UI, REST, Bulk, Import, Page-Liveeditor und externe Synchronisierung können relevante Informationen verändern. Deshalb nicht nur neue Formulare instrumentieren. Im Run-/Merge-Gate aktuellen Quellstand prüfen, auch falls die Aktivitätsprojektion noch zurückliegt.

**Die neue Revision darf besser sein als die alte, ohne sie zu überschreiben.** Eine Arbeitsfassung kann weiter wachsen. Ein laufender Run bleibt an der freigegebenen Fassung; relevante Abweichung pausiert beziehungsweise erfordert Neubewertung.

**Migration ohne Issue-Pflichtkonvertierung.** Bestehende Plane-Issues werden nicht automatisch alle zu strengeren Paketen. Die Zusatzfunktion ist zunächst opt-in; kleine technische Änderungen können als ChangeRecord unter einem genehmigten Paket laufen.

## 5. Editionen und Rechte

Diese Planung verwendet die öffentliche Community-Codebasis als überprüfbare Ausgangslage. Plane dokumentiert eigene Community-, Commercial- und Airgapped-Codebasen; die Commercial Edition ist nicht einfach ein Featureflag im hier geprüften Repository. P11.

AGPL ist im öffentlichen Root-Manifest und an den geprüften Modellen ausgewiesen. Das Paket behauptet keine zusätzliche OEM-/Embedding-/White-Label-Erlaubnis. Ein gewollter geschlossener Fork braucht einen passenden geklärten Lizenzweg. L01 verhindert, dass eine technische Foundation-Entscheidung als Vertriebsfreigabe ausgelegt wird. P12.

Neue Module, getrennte Services oder eigene Dateinamen sind keine hier festgestellte rechtliche Ausnahme. Lizenztexte, Copyright-/Hinweise und Paket-Lizenzen werden nicht entfernt. Ein späterer Vertrag kann den tatsächlich nutzbaren Codeumfang ändern; dann sind Capability-Matrix und Baseline neu zu bewerten.

## 6. Nicht verifiziert

Keine vollständige lokale Ausführung des Plane-Quellcodes, keine produktive Testinstanz, kein tatsächlicher Fork und keine Migration. Kein Benchmark, keine sichere Bestätigung aller Draft-/Permission-/Realtimepfade. Kein vollständiger Dependency-/Supply-Chain-/Lizenzaudit. Keine aktuelle Inspektion von Plane-UI-Screens über Mobbin in diesem Änderungsschritt. Die bisherigen Designreferenzen bleiben historische Entwurfsinputs.

Die Quellenprüfung reicht für eine präzise Anpassung des Bauplans. Sie ersetzt nicht I00s Baseline- und Capability-Tests.
