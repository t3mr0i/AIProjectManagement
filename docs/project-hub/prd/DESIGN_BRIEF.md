# Design-Brief — Plane erweitern, gemeinsame Arbeit sichtbar machen

Version 0.2 · 24. September 2026 · Vorschlag, noch keine visuelle Abnahme.

## 0. Verbindliche Foundation für alle Screens

Die Screens aus 0.1 bleiben funktionale Zielbilder, werden aber **innerhalb von Plane** realisiert. Die Codebasis wird nicht durch einen neuen Linear-Klon ersetzt. Die vorhandene App-Shell, Projekt-/Issue-Navigation, Standardansichten, Komponenten, Theming und Editorbasis bilden den Ausgangspunkt. Plane-Cloud-Screens belegen keine frei verfügbare Funktion im Community-Repository.

| Oberfläche                 | Übernehmen                                                             | Gezielte Ergänzung                                                                                     |
| -------------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Workspace / Projektwechsel | Native Navigation, Mitgliedschaften und Projektidentität.              | Projektübergreifender Überblick, persönliche Entscheidungen, letzte relevante Änderungen.              |
| Issue-Liste / Board        | Native Zeilen, Filter, Zustände, Detailzugang und Tastaturinteraktion. | Ergebnispaket als Profil desselben Issues; kompakter belegter Build–Review–Ship-Stand.                 |
| Issue-Detail               | Vorhandener Titel, Eigenschaften, Beschreibung und Diskussion.         | Spezifikation/Revision, Freigabe, Kontext-Chat, Umsetzung/Nachweise als zusätzliche Bereiche.          |
| Pages / Editor             | Bestehender Rich-Text-/Kollaborationseditor und Assetbezug.            | KI-Seitenbereich, strukturierte Diagramme, semantischer Diff, OpenSpec-Zuordnung.                      |
| Cycles / Modules           | Vorhandene Projektplanung und Gruppierung.                             | Nicht jede technische Kleinigkeit anzeigen; kein paralleler Sprintplan.                                |
| Roadmap                    | Vorhandene Datums-/Projektinformationen und geeignete Listen/Views.    | Mehrere Projekte/Teams, bestätigte Abhängigkeiten und Szenarien; fehlende Funktionen ausdrücklich neu. |
| Chat                       | Plane-Mitglieder, Projektbezug und vorhandene Kommentare als Kontext.  | Richtige Kanäle, DMs, Threads und @AI; nicht bloß ein umbenannter Issue-Kommentarbereich.              |

**Implementierungsbasis:** `apps/web`, `@makeplane/propel`, `@plane/blocks`, `packages/shared-state`, `packages/editor`, `apps/live`; geprüft in den Source-Referenzen P03, P07–P09. Neue semantische Komponenten ergänzen die vorhandenen Primitives. Ein zweites Basiskomponenten- oder Routing-System ist kein Bestandteil dieses Auftrags.

**Reale Designarbeit vor Umsetzung:** Die freigegebene Plane-Baseline starten, die vorhandenen Screens bei gleicher Auflösung aufnehmen, neue Funktionen an diesen Screens entwerfen und Side-by-side auf Regression prüfen. Die hier enthaltene HTML-Datei ist ein Dokumentenleser, kein getesteter Plane-UI-Prototyp. Die Referenzauswertung aus 0.1 bleibt erhalten; in dieser Anpassung wurden keine neuen Mobbin-Screens geprüft und keine fremden Assets übernommen.

## 1. Zielbild

Die Anwendung soll zuerst wie ein gut organisiertes Arbeitswerkzeug wirken: kompakte Listen, klare Typografie, direkte Bearbeitung und kurze Wege. Der Nutzer hat Linear als positive Referenz bestätigt. Eine absichtlich ungewohnte Navigation wäre daher kein Selbstzweck.

Eigenständigkeit entsteht durch die sichtbare Verbindung von **Absicht, aktueller Arbeit, Entscheidung und Liefernachweis**, nicht durch eine exotische Sidebar oder dekorative KI-Animation. Die Hauptansicht beantwortet: Was hat sich verändert? Was steht an? Wo fehlt eine Entscheidung? Details zu einzelnen Dateien oder Agentenschritten werden bei Bedarf geöffnet.

## 2. Tatsächlich über Mobbin betrachtete Referenzen

Die folgenden Screens wurden laut Rechercheprotokoll der Fassung 0.1 über das Mobbin-MCP gesucht und anhand der zurückgegebenen Bilder betrachtet; diese Auswertung wird unverändert als Referenz übernommen. Beobachtung ist von eigener Übertragung getrennt. Die Screens belegen sichtbare Gestaltung, nicht automatisch die zugrunde liegende Funktionsweise der Produkte.

### M01 — Linear: Projektübersicht

[Screen auf Mobbin](https://mobbin.com/screens/9c8e3907-b7af-48d6-ae2d-9b4ff700d433)

**Beobachtet:** Links eine schmale globale Navigation. In der Mitte Projekttitel, Metadaten und ein aktuelles Projektupdate. Rechts Eigenschaften, Meilensteine und ein Fortschrittsbereich. Die Projektinformation ist nicht auf gleich große KPI-Kacheln verteilt.

**Übernehmen:** Stabile Orientierung, kompakte Metadaten, enger Zusammenhang zwischen Projekt und Update.

**Anders lösen:** Hauptfläche stärker auf jüngste tatsächliche Änderungen und benötigte Entscheidungen ausrichten. Automatisch erfasste Signale und manuell bestätigte Angaben sichtbar unterscheiden. Rechts nicht dauerhaft jede Projekteigenschaft wiederholen.

### M02 — Linear: Gruppierte Arbeitsliste

[Screen auf Mobbin](https://mobbin.com/screens/be6c4ee4-aa93-42b4-89b3-dcfc8386f022)

**Beobachtet:** Kompakte Zeilen, Statusgruppen, Titel, Labels, Projektbezug, Personen und Termine. Eine Mehrfachauswahl ist am unteren Rand erkennbar. Wenig Kartenfläche, viele gleichzeitig sichtbare Einträge.

**Übernehmen:** Zeilen statt überwiegend großer Karten, stabile Ausrichtung, tastaturfreundliche Auswahl, Gruppierung und Filter.

**Anders lösen:** Sichtbares Hauptobjekt ist das Ergebnispaket. Technische Kleinschritte werden standardmäßig darunter verdichtet. Build–Review–Ship erscheint als kompakter Lieferzustand; kein künstlicher Prozentbalken aus der Zahl abgearbeiteter Agentenschritte.

### M03 — Linear: Projektzeitachse

[Screen auf Mobbin](https://mobbin.com/screens/b3aab33b-60b3-4eb5-b21d-5aa6ba3061e2)

**Beobachtet:** Projektzeilen stehen links einer breiten Kalenderachse gegenüber. Ein Heute-Marker und zeitlich platzierte Projektbereiche sind sichtbar. Die betrachtete Ansicht ist sehr weit herausgezoomt.

**Übernehmen:** Gemeinsame Zeitnavigation über Projekte, feste linke Zuordnung, variable zeitliche Auflösung.

**Anders lösen:** Für eine kleine Zahl kurzer Projekte standardmäßig auf einen sinnvollen Zeitraum zoomen, nicht ein weitgehend leeres Jahr anzeigen. Bestätigte Abhängigkeiten, Varianten und fehlende Termine explizit kennzeichnen.

### M04 — Wrike: Tabelle mit angekoppeltem Zeitplan

[Screen auf Mobbin](https://mobbin.com/screens/c852fffb-8f64-48ba-a078-84b4ca21ecc7)

**Beobachtet:** Links strukturierte Zeilen mit Namen, Status und Datumsfeldern; rechts dazugehörige Balken auf einer Zeitachse. Die Zeilenhierarchie bleibt beim Zeitplan erhalten.

**Übernehmen:** Tiefergehendes PM kann in einer anderen Ansicht desselben Datenmodells stattfinden. Tabelle und Zeitachse sind zusammen nutzbar.

**Anders lösen:** Diese höhere Dichte ist ein Planungsmodus, nicht die erste Ansicht für jedes Teammitglied. Keine dauerhaft sichtbaren, selten genutzten PM-Felder.

### M05 — Fibery: Dokument mit KI-Seitenbereich

[Screen auf Mobbin](https://mobbin.com/screens/e1f475cd-9340-4b6d-98c3-9ad852993175)

**Beobachtet:** Links eine umfangreiche Objekt-/Workspace-Navigation, zentral ein neues Dokument, rechts ein eigener Ask-AI-Bereich mit Frage und Antwort.

**Übernehmen:** Bearbeitbares Artefakt und KI-Gespräch bleiben nebeneinander sichtbar. Gespräch ist nicht das einzige Ergebnis.

**Anders lösen:** Einfachere linke Navigation. Ausgewählter Kontext, Quellen und vorgeschlagene Änderungen werden explizit angezeigt. Eine KI-Änderung wird nicht unbemerkt in das geteilte Dokument geschrieben.

### M06 — Langdock: Gespräch neben entstehendem Artefakt

[Screen auf Mobbin](https://mobbin.com/screens/579fb137-50fa-42d0-9222-4970f35648d5)

**Beobachtet:** Navigation links, Gespräch mit angehängter Quelle daneben, rechts ein eigener Artefaktbereich mit Titel und Bearbeitungsleiste. Der betrachtete Inhalt ist noch im Ladezustand mit Platzhaltern; daraus lässt sich keine Qualität eines fertigen Dokuments ableiten.

**Übernehmen:** Eine AI-Aktion erzeugt ein dauerhaft bearbeitbares Objekt neben dem Gespräch. Der Auftrag und seine Quelle bleiben nachvollziehbar.

**Anders lösen:** Für Teamarbeit wird Draft, gemeinsam gespeicherte Revision und freigegebene Version explizit getrennt. Keine dauerhafte Drei-Spalten-Enge auf kleinen Bildschirmen.

### M07 — Slack: Aktivität mit zugehöriger Diskussion

[Screen auf Mobbin](https://mobbin.com/screens/84dfe56c-4571-4248-a067-1432727bc5d6)

**Beobachtet:** Eine Aktivitätsliste steht links neben einem geöffneten Thread. Der konkrete Screen zeigt einen Thread zu einer Direktnachricht, nicht den gesamten Kanalchat. Navigation und Liste bleiben beim Lesen sichtbar.

**Übernehmen:** Ein Ereignis kann geöffnet werden, ohne die vorherige Orientierung zu verlieren. Liste und Detail gehören zusammen.

**Anders lösen:** In unserem Produkt öffnen Ereignisse nicht nur Threads, sondern auch Paket, Entscheidung, Diff oder Lieferbeleg. Eine ausgewählte Nachricht kann mit @AI zu einem bestätigten Objekt werden.

### Referenzmaterial im Paket

Enthalten sind dauerhafte Mobbin-Screenlinks und diese Auswertung. Hochauflösende Bilddateien konnten über den verfügbaren Downloadpfad nicht gespeichert werden; deshalb enthält das Paket keine eingebetteten Screenshots und keine ersatzweise hochskalierten Vorschauen. Die Referenzen dienen der Analyse, nicht als zu übernehmende Produktassets.

## 3. Informationsarchitektur

### Globale Ebene

Workspace-Wechsel und globale Suche oben links. Darunter Übersicht, Projekte, Roadmap, Nachrichten und Wissen. Persönliche Aufmerksamkeit wird über eine klar bezeichnete Inbox beziehungsweise einen konsistenten Zähler erreicht. Administration steht getrennt und nur bei Berechtigung bereit.

Projektauswahl darf nicht zwanzig permanente Navigationspunkte erzeugen. Favoriten und zuletzt verwendete Projekte reichen zunächst; die gesamte Projektliste bleibt suchbar.

### Projektebene

Projektname und Zustand bleiben stabil im Kopf. Tabs: Aktivität, Arbeit, Roadmap, Wissen und Team. Integrationen erscheinen im Projektmenü statt als dominante fachliche Hauptfunktion.

Die ersten beiden Tabs entsprechen unterschiedlichen Fragen: Aktivität beantwortet „Was hat sich verändert?“, Arbeit beantwortet „Wo stehen die Pakete?“. Beide nutzen dieselben Objekte und Filterkontexte.

### Paketebene

Ein schneller Klick öffnet zunächst ein Detailpanel. Ein bewusster Fokuswechsel öffnet den vollständigen Paketarbeitsraum. In beiden Fällen bleiben Paket-ID, Titel, Projekt, Revision und Status konsistent.

Im Arbeitsraum: Auftrag, Änderungen, Review und Verlauf. Die Diskussion liegt in einem umschaltbaren Seitenpanel. Ein zweites konkurrierendes Chatfenster wird nicht automatisch daneben geöffnet.

## 4. Visuelle Leitplanken

**Vorschlag:** Ruhiger heller Standardmodus, mit Dunkelmodus über dieselben Tokens. Neutrale Flächen, kräftiger lesbarer Text, ein zurückhaltender Akzent. Farben kodieren Status nur zusammen mit Symbol und Text. Keine großflächigen Verläufe, Glasscheiben, generischen KI-Sterne oder pulsierenden Agenten-Avatare als Grundgestaltung.

Die Namen Build, Review und Ship bleiben sichtbar, werden durch verständliche konkrete Zustände ergänzt. Ein rotes Symbol ohne Beschreibung ist kein ausreichender Fehlerzustand.

**Vorgeschlagene Maßbasis für den ersten Prototyp:** 1440 × 900 Desktop-Arbeitsfläche, 224 px Navigation, 40 px Standardzeile, 14 px Grundtext, 13 px Sekundärtext, 4/8-px-Abstandslogik. Dies sind Designwerte zur Prüfung, keine bereits abgenommenen Maße. Auf 1280 px Breite dürfen Hauptaktion und wesentliche Statusinformation nicht verschwinden. Seitenpanels liegen etwa zwischen 360 und 480 px und sind schließbar.

Tabellen sollen gut lesbar dicht sein, nicht möglichst klein. Dokumenttext verwendet eine größere, angenehm lesbare Schrift und begrenzte Zeilenlänge. Diagrammwerkzeuge erhalten mehr Fläche durch fokussierten Editor, nicht durch dauerhaft verkleinerte Schrift.

## 5. Screen-Spezifikationen

### S02 — Projekt-Aktivität

**Aufbau:** Projektkopf; Zeitraumfilter „Seit meinem letzten Besuch / Heute / 7 Tage / Zeitraum“; kompakte Zeile mit offenen Entscheidungen; nach Tagen gruppierte Paketereignisse.

**Ein Ereignis enthält:** Paket, verständliche Änderung, Ergebnisstand, verantwortliche Person oder Agent unter menschlicher Verantwortung, Ereigniszeit und Quellenzugang. Beispieldaten müssen als solche erkennbar sein.

**Interaktion:** Klick öffnet kontextuelles Detail; „Technische Details“ klappt Rohereignisse auf. Eine zusammengefasste Aktivität zeigt die Anzahl und den abgedeckten Zeitraum. Nachträglich importierte Ereignisse erscheinen am ursprünglichen Datum mit Importhinweis.

**Fehlerzustand:** „GitLab zuletzt vor 18 Minuten synchronisiert“ steht am betroffenen Bereich. Die gesamte Ansicht wird nicht fälschlich live genannt.

### S03 — Projekt-Arbeit

**Aufbau:** Such-/Filterzeile, gespeicherte Ansichten, kompakte Paketzeilen nach Zustand. Drafts separat; „Als Nächstes“ zeigt nur freigegebene und tatsächlich startfähige Pakete. Boarddarstellung ist eine alternative Ansicht, keine Pflicht.

**Zeile:** Titel, verantwortliche Person, Build–Review–Ship-Zustand, kurze Blockade/Entscheidungsinfo, Aktivitätszeit. Labels und Zusatzfelder optional. Keine standardmäßig sichtbaren Dateien, Toolaufrufe oder Tokenzahlen.

**Primäre Aktionen:** Neues Paket, Paket öffnen, Übernehmen. Ausführen bleibt an Rechte und Freigabe gebunden. Drag-and-drop auf „Build“ darf keine unsichtbare Ausführungsfreigabe erteilen; ein erforderlicher Übergang öffnet einen erklärenden Dialog.

### S04 — Paket-Draft

**Aufbau:** Titel und Draft-Badge. Zentral Ziel/Warum, gewünschtes Ergebnis, Nichtziele und Kriterien. Kontextquellen und Codebasis liegen in einer kompakten Seitenansicht. „Mit KI konkretisieren“ öffnet das Gespräch daneben.

**Interaktion:** Freies Schreiben, Quellen anhängen, einzelne Anforderung markieren. KI stellt eine wesentliche Frage, zeigt Empfehlung und lässt Antwort direkt in den Entwurf übernehmen. Nicht beantwortete Fragen sind speicherbar und blockieren nur, wenn die Readiness-Regel sie tatsächlich verlangt.

**Freigabe:** Ein klarer Button „Zur Umsetzung freigeben“ öffnet Revision, Scope, Auswirkungen und Ausführungsart. Speichern und Freigeben haben keine gleiche Farb- oder Platzierungshierarchie.

### S05 — Build

**Aufbau:** Freigegebene Revision und eventuell neuere Arbeitsfassung nebeneinander bezeichnet. Runstatus, zuständige Person, betroffene Repositories und nächste offene Entscheidung. „In IDE übernehmen/öffnen“ ist deutlich erreichbar.

**Interaktion:** Run abbrechen bei Berechtigung; Kontext und Logs öffnen; neue Entscheidung beantworten. Kein eingebauter vollständiger Codeeditor erforderlich. Uncommittete Arbeit ist nur mit entsprechender Runnerquelle sichtbar.

**Fehlerzustand:** Offline/Lease abgelaufen, Budgetlimit, fehlende Berechtigung, Basis verändert. Alle Zustände nennen eine konkrete nächste Handlung statt „Something went wrong“.

### S06 — Review

**Aufbau:** Links beziehungsweise oben die beabsichtigte Veränderung; daneben tatsächliche Umsetzung. Kriterienliste mit belegtem, offenem oder fehlgeschlagenem Zustand. Vorschau/Artefakte und Git-Review sind verlinkt. Fachliche und technische Freigabe haben getrennte Abschnitte.

**Interaktion:** Eine Behauptung öffnet ihre Quelle. Veraltete Evidenz nennt geprüften und aktuellen Commit. Bei Änderungen nach Approval zeigt die Ansicht „Neue Prüfung erforderlich“ statt unverändertem grünen Haken.

**Kein zweites Testwerkzeug:** In der IDE oder CI erbrachte Prüfungen werden erklärt und verknüpft, nicht manuell neu eingetippt.

### S07 — Ship

**Aufbau:** Zeilen pro Repository/Komponente; Spalten für integrierten Stand, Artefakt, Umgebung und Freischaltung. Das Paket zeigt ein Gesamturteil nur mit klarer Aggregationsregel.

**Interaktion:** Deployment öffnen, Unterschiede zur vorherigen Lieferung nachvollziehen, Rollbackhistorie sehen. „Nicht bekannt“ ist ein legitimer Zustand.

**Wichtig:** Produktionsdeployment ohne bekannte Feature-Freigabe wird als bereitgestellt, nicht automatisch als für alle Nutzer verfügbar bezeichnet.

### S08 — Gemeinsamer Editor

**Aufbau:** Editierbares Artefakt zentral, Formatwerkzeuge nahe am Inhalt, Personenpräsenz zurückhaltend. Quellen/Kommentare/KI teilen sich ein konsistentes Seitenpanel.

**Interaktion:** Texte und Diagrammelemente markieren; @AI mit sichtbarer Auswahl. KI-Vorschlag erscheint als Diff. Dokument- und Layoutänderungen sind getrennt. Im Fokusmodus verschwinden unwichtige PM-Metadaten.

**Zustände:** Lokal geändert, gespeichert, synchronisiert, Git-Konflikt. Ein in Git noch nicht publiziertes Dokument darf nicht „überall aktuell“ behaupten.

### S09 — Nachrichten und @AI

**Aufbau:** Konversationsliste und Gespräch. Paket-/Projektbezug ist im Kopf sichtbar. Ein Thread öffnet kontextuell. Auswahl von Nachrichten erzeugt eine stabile Auswahlmarkierung.

**Interaktion:** `@AI` zeigt einen Context-Chip mit ausgewähltem Material. Aktionen werden als Vorschaukarten dargestellt: Zusammenfassung, Paketentwurf, Entscheidung. Verbindliches Veröffentlichen ist erkennbar; eine bloße Antwort ist kein Beschluss.

**Privatheit:** Wechsel von DM-Inhalt in ein Projekt zeigt den neuen Empfängerkreis. Bei nicht ausreichenden Rechten wird keine Vorschau mit verbotenen Quellenausschnitten angezeigt.

### S10 — Roadmap

**Aufbau:** Links Projekte/Meilensteine, rechts synchronisierte Zeitachse. Zoom und Filter bleiben erreichbar. Ungeplante Pakete haben einen eigenen Bereich, nicht ein erfundenes Datum.

**Interaktion:** Termin verschieben zeigt eine Variante und betroffene Abhängigkeiten. Bestätigte und vermutete Beziehungen sehen unterschiedlich aus. Eine zugängliche Tabellenansicht enthält dieselben Informationen.

**Grenze:** Ohne Dauer-/Kapazitätsgrundlage werden Auswirkungen und Unsicherheit gezeigt, keine mathematisch wirkende Fantasieprognose.

## 6. Wiederkehrende Komponenten

`ProjectHeader`, `PackageRow`, `DeliveryState`, `DecisionNeeded`, `ActivityGroup`, `EvidenceBadge`, `RevisionDiff`, `SourceReference`, `ContextSelection`, `AIProposal`, `ApprovalDialog`, `SyncHealth`, `PermissionBoundary`, `DependencyEdge`, `UnknownState`, `EmptyState` und `ErrorRecovery` sind neue semantische Erweiterungskomponenten auf der Plane-Komponentenbasis, keine neue Basiskomponentenbibliothek.

Ein `EvidenceBadge` ist kein allgemeiner Erfolgsbutton. Er kennt Quelle, Aktualität und Vertrauensklasse. `ApprovalDialog` ist kein normales Bestätigungsmodal: Er nennt die betroffene Revision und Aktion. `UnknownState` wird nicht wie ein Fehler behandelt, wenn die Datenquelle bewusst fehlt.

## 7. Usability-Abnahme

Fünf Kernaufgaben werden mit technischen und fachlichen Personen getestet: nach Abwesenheit aufholen, Paket erstellen und freigeben, Diagrammänderung als Vorschlag erfassen, Chatentscheidung übernehmen, tatsächlichen Lieferstand zweier Repositories erklären.

Zusätzlich: alles Wesentliche mit Tastatur; mindestens 1280-px-Desktopbreite; lesbare Darstellung bei Zoom; Liveupdates ohne Fokusverlust; langsame oder ausgefallene Integration; private Quelle im gemeinsamen Chat; Draft und freigegebene Revision gleichzeitig.

Ein visueller Prototyp ist abgenommen, wenn die Nutzer die richtigen Aktionen und Zustände verstehen. Die bloße Ähnlichkeit mit Linear oder die Zahl attraktiver Screens genügt nicht.
