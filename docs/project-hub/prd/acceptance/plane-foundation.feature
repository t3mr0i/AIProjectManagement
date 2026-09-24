# language: de
# Neue Spezifikationen; keine implementierten Anwendungsschritte.
Funktionalität: Plane-Foundation unverändert nutzen und sicher erweitern

  @PF01 @FR-B01
  Szenario: Fixierter Quellenstand statt beweglichem Preview
    Angenommen der Analysiscommit ist dokumentiert und die Implementierungsbaseline noch nicht freigegeben
    Wenn ein Agent einen abweichenden HEAD verwenden soll
    Dann muss eine bewusste Baselineentscheidung samt Quellenvergleich erfolgen

  @PF02 @FR-B02
  Szenario: Ein bestehendes Issue wird ohne Duplikat zum Paket
    Angenommen ein berechtigter Nutzer hat ein bestehendes Plane-Issue ohne Paketprofil
    Wenn er das Paketprofil zweimal mit derselben Idempotenzkennung aktiviert
    Dann existiert genau ein Profil am selben Issue und kein zweites Ticket

  @PF03 @FR-B03
  Szenario: Native Projektverwaltung bleibt die Grundlage
    Angenommen ein Plane-Workspace mit Mitgliedern und Projekten existiert
    Wenn die Erweiterung aktiviert wird
    Dann verwenden Paket- und Chatfunktionen dieselben nativen Benutzer- und Projektidentitäten

  @PF04 @FR-B04
  Szenario: Additive Migration auf einen Altbestand
    Angenommen eine gesicherte Plane-Testinstanz enthält Issues Pages Cycles und Modules
    Wenn Extensionmigration und wiederholbarer Backfill ausgeführt werden
    Dann bleiben native IDs Inhalte und Beziehungen erhalten

  @PF05 @FR-B05
  Szenario: Statusänderung ist keine Runfreigabe
    Angenommen ein Issue besitzt einen nicht freigegebenen Paketentwurf
    Wenn der Status über native UI Bulk oder API auf In Progress geändert wird
    Dann kann kein Implementierungsrun ohne gültige menschliche Revisionsfreigabe starten

  @PF06 @FR-B06
  Szenario: Native Beschreibung ändert freigegebenen Umfang
    Angenommen eine Paketrevision wurde freigegeben und ihre native Beschreibung anschließend geändert
    Wenn ein Run startet bevor das Änderungsereignis projiziert wurde
    Dann prüft das Gate den aktuellen Stand und lässt die neue Absicht nicht unter der alten Freigabe ausführen

  @PF07 @FR-B07
  Szenario: Draftfilter umgehen keine Rechte
    Angenommen ein Workspace enthält einen eigenen Draft ein fremdes privates Issue und ein archiviertes Projekt
    Wenn ein Nutzer die Paket-Draftansicht öffnet und einen Claim anfordert
    Dann sieht er nur erlaubte Drafts und erhält keinen neuen Claim für archivierte Projekte

  @PF08 @FR-B08
  Szenario: Bestehende Editorinhalte bleiben erhalten
    Angenommen eine native Page enthält bekannte und unbekannte Editorblöcke sowie Assets
    Wenn der Paketeditor einen OpenSpec-Roundtrip und eine reine Diagramm-Layoutänderung verarbeitet
    Dann gehen keine Blöcke verloren und entsteht kein Implementierungsauftrag aus dem Layoutdiff

  @PF09 @FR-B09
  Szenario: Private Inhalte gelangen nicht in öffentliche Plane-Flächen
    Angenommen ein Paket referenziert eine private Nachricht und eine nur intern lesbare Quelle
    Wenn ein öffentlicher Viewer eine verknüpfte Seite oder einen Export liest
    Dann enthält die Ausgabe weder private Inhalte noch unberechtigte Metadaten aus dem Paket

  @PF10 @FR-B10
  Szenario: Native Activity und Webhook werden korreliert
    Angenommen ein Merge erzeugt eine native Issue-Aktivität und mehrfach zugestellte Providerereignisse
    Wenn der Aktivitätsworker diese Signale verarbeitet
    Dann zeigt der Paketverlauf genau ein fachliches Mergeereignis mit nachvollziehbaren Rohquellen

  @PF11 @FR-B11
  Szenario: Done ist kein Deployment
    Angenommen ein paketfähiges Issue steht nativ auf Done und es gibt keinen Deploymentbeleg
    Wenn die Build Review Ship Ansicht geladen wird
    Dann bleibt der Produktionsstand unbekannt und die Abweichung ist sichtbar

  @PF12 @FR-B12
  Szenario: Upstreamupdate erhält native und neue Daten
    Angenommen ein geprüfter Forkbestand und ein neuer vorgeschlagener Upstreamcommit liegen vor
    Wenn das Probeupdate samt Migration und Restoretest ausgeführt wird
    Dann werden native Kernflows und Paketfreigaben verifiziert bevor ein Rollout erlaubt ist

  @PF13 @FR-B13
  Szenario: Cloudfunktion ist kein Community-Nachweis
    Angenommen eine gewünschte Enterprisefunktion ist nur in Produktdokumentation belegt
    Wenn ein Agent ihren fertigen Code im Community-Fork einplanen möchte
    Dann bleibt die Funktion bis zum Quellen Rechte und Laufzeitnachweis eine offene Eignungsprüfung

  @PF14 @FR-B14
  Szenario: Ein Issue ein Navigationsziel
    Angenommen ein normales Issue wird aus einer Plane-Liste und aus der neuen Paketübersicht geöffnet
    Wenn ein berechtigter Nutzer zwischen den Ansichten wechselt
    Dann bleiben Issueidentität Projektkontext native Links und Eigenschaften konsistent
