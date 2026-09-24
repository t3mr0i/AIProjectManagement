# language: de
# Fassung 0.2: Plattforminstanz ist der Plane-Fork; Pakete referenzieren native Issues.
Funktionalität: Gemeinsame Projektzentrale mit freigegebenen Arbeitspaketen
  # Testspezifikation. Step-Implementierungen werden im Produktprojekt erstellt.
  # Diese Datei wurde nicht gegen eine existierende Anwendung ausgeführt.

  @AC01 @FR-W01 @FR-W05
  Szenario: Ein unvollständiger Draft bleibt speicherbar, aber nicht ausführbar
    Angenommen ein berechtigter Nutzer erstellt ein Paket nur mit Titel und Projekt
    Wenn er den Draft speichert
    Dann bleibt das Paket erhalten
    Und ein Runstart wird mit dem fachlichen Fehler "REVISION_NOT_APPROVED" abgelehnt

  @AC02 @FR-W05 @FR-G05
  Szenario: Ein Draft wird nicht durch einen Webhook umgesetzt
    Angenommen ein Paket ist im Zustand Draft
    Wenn ein externes Ereignis einen Status mit dem Namen "In Progress" meldet
    Dann entsteht kein Implementierungslauf
    Und die externe Statusbeobachtung wird getrennt vom Ausführungsrecht gespeichert

  @AC03 @FR-W05 @FR-R03
  Szenario: Ein Agent kann menschliche Freigaben nicht erzeugen
    Angenommen eine Aktion ist mit Agentenidentität authentisiert
    Wenn sie im Payload "kind: human" angibt und eine Freigabe anfordert
    Dann lehnt der Server die Freigabe wegen fehlender menschlicher Berechtigung ab

  @AC04 @FR-W04 @FR-W09
  Szenario: Neue Arbeitsfassung ersetzt keine freigegebene Revision
    Angenommen Run A verwendet die freigegebene Revision 3
    Wenn ein Manager Revision 4 als Draft speichert
    Dann verwendet Run A weiterhin Revision 3
    Und die Projektansicht zeigt die neue Arbeitsfassung getrennt

  @AC05 @FR-G04
  Szenario: Gleichzeitige exklusive Übernahme
    Angenommen eine Paket-Repo-Einheit besitzt keinen aktiven Claim
    Wenn zwei autorisierte Runner gleichzeitig exklusiv übernehmen
    Dann erhält genau ein Runner einen gültigen Claim
    Und der andere erhält einen Konflikt mit einem zulässigen Zuständigkeitshinweis

  @AC06 @FR-G04 @FR-G06
  Szenario: Abgelaufene Lease schützt vor verspäteten Writes
    Angenommen Runner A besitzt einen inzwischen abgelaufenen Claim
    Und Runner B hat einen neueren gültigen Claim
    Wenn Runner A eine kontrollierte Schreibaktion sendet
    Dann wird sie anhand des veralteten Fencing-Tokens abgelehnt

  @AC07 @FR-W08 @FR-G02
  Szenario: Gleichzeitige Spezifikationsänderung in UI und IDE
    Angenommen UI und IDE basieren auf demselben Spec-Commit
    Wenn beide denselben Abschnitt unterschiedlich ändern
    Dann wird ein Drei-Wege-Konflikt angezeigt
    Und keine Seite wird durch Force-Push oder Last-write-wins still überschrieben

  @AC08 @FR-W08
  Szenario: Unbekannte OpenSpec-Blöcke bleiben erhalten
    Angenommen ein importiertes Artefakt enthält einen unbekannten Abschnitt
    Wenn ein bekannter Abschnitt bearbeitet und erneut exportiert wird
    Dann bleibt der unbekannte Abschnitt unverändert erhalten oder der Export wird vor einem Datenverlust sichtbar blockiert

  @AC09 @FR-E02 @FR-E03
  Szenario: Diagrammlayout ist keine fachliche Änderung
    Angenommen ein Architekturdiagramm ist gespeichert
    Wenn ein Nutzer nur die Position eines Knotens verändert
    Dann wird kein neuer Implementierungsauftrag abgeleitet
    Und die Darstellung wird dennoch gespeichert

  @AC10 @FR-E02 @FR-E03 @FR-W05
  Szenario: Semantische Diagrammänderung erzeugt einen Draft-Vorschlag
    Angenommen ein Architekturdiagramm enthält zwei unverbundene Komponenten
    Wenn ein Nutzer eine fachliche Verbindung ergänzt
    Dann zeigt die KI Interpretation und offene Annahmen als Vorschlag
    Und es beginnt keine Umsetzung ohne menschliche Revisionsfreigabe

  @AC11 @FR-C03
  Szenario: Eindeutige Chatentscheidung wird einmalig veröffentlicht
    Angenommen eine berechtigte Person hat eine konkrete Nachrichtenauswahl bestätigt
    Wenn derselbe Entscheidungsbefehl nach einem Timeout erneut zugestellt wird
    Dann existiert genau eine veröffentlichte Entscheidung mit den Quellreferenzen

  @AC12 @FR-C02 @FR-C03
  Szenario: Private Quelle wird nicht automatisch im Projekt geteilt
    Angenommen eine Direktnachricht ist nur zwei Personen zugänglich
    Wenn ein Nutzer deren Inhalt per KI in einem größeren Projektkanal verwenden möchte
    Dann wird der veränderte Empfängerkreis geprüft
    Und ohne entsprechende Freigabe wird der private Inhalt nicht veröffentlicht

  @AC13 @FR-C04
  Szenario: Bearbeitete Nachricht verändert keine frühere Entscheidung
    Angenommen eine Entscheidung referenziert eine bestätigte Nachrichtenversion
    Wenn der Nachrichtentext später geändert wird
    Dann bleibt die ursprüngliche Entscheidungsversion unverändert
    Und die Quellenänderung ist im berechtigten Verlauf erkennbar

  @AC14 @FR-P06 @FR-I07
  Szenario: Rechteentzug gilt auch für KI und Suche
    Angenommen ein Nutzer hatte Zugriff auf Projekt A
    Wenn der Zugriff widerrufen wird
    Dann liefern neue API-, Such- und KI-Anfragen keine Inhalte aus Projekt A
    Und die bestehende Liveverbindung wird innerhalb des vereinbarten Zeitfensters widerrufen

  @AC15 @FR-R01 @FR-R02
  Szenario: Eine Commit-Behauptung ist kein Testnachweis
    Angenommen eine Commit-Message lautet "Alle Tests bestanden"
    Und es liegt kein passender vertrauenswürdiger Testnachweis vor
    Wenn die Reviewansicht erzeugt wird
    Dann zeigt sie die Prüfung als nicht nachgewiesen

  @AC16 @FR-R03
  Szenario: Neuer Head macht die alte Codefreigabe unzureichend
    Angenommen ein Mensch hat Head A geprüft und freigegeben
    Wenn ein neuer relevanter Commit Head B erzeugt
    Dann kann die alte Freigabe keinen Merge von Head B erlauben
    Und der Reviewzustand zeigt die erneut erforderliche Prüfung

  @AC17 @FR-R03 @FR-G10
  Szenario: Änderung zwischen letzter Prüfung und Merge
    Angenommen die Plattform bereitet einen Merge für Head A vor
    Wenn der Provider vor dem Merge einen anderen Head meldet
    Dann wird der Merge nicht für den ungeprüften Head durchgeführt
    Und der Nutzer erhält einen nachvollziehbaren Konflikt

  @AC18 @FR-G09 @FR-R05
  Szenario: Zwei Repositories werden nur teilweise integriert
    Angenommen ein Paket erfordert Backend und Frontend
    Wenn nur der Backend-Merge bestätigt wurde
    Dann zeigt das Paket eine Teillieferung
    Und es erscheint nicht als vollständig integriert oder ausgeliefert

  @AC19 @FR-R05
  Szenario: Merge ohne Deployment bleibt nicht produktiv
    Angenommen der Code eines Pakets ist integriert
    Und kein passendes Deploymentsignal liegt vor
    Wenn die Ship-Ansicht geöffnet wird
    Dann ist der produktive Lieferstand unbekannt oder noch nicht bereitgestellt

  @AC20 @FR-R06
  Szenario: Rollback korrigiert den aktuellen Lieferstand
    Angenommen ein Paket wurde auf Produktion bereitgestellt
    Wenn diese Lieferung zurückgenommen wird
    Dann zeigt der aktuelle Stand die Rücknahme
    Und die frühere Lieferung bleibt als historisches Ereignis erhalten

  @AC21 @FR-I04
  Szenario: Mehrfache und verspätete Ereignisse ändern den Endzustand nicht falsch
    Angenommen ein Merge-Event wurde bereits korrekt verarbeitet
    Wenn es erneut und danach ein älteres Build-Event zugestellt wird
    Dann entsteht kein zweites Merge-Ereignis im fachlichen Verlauf
    Und das Paket fällt nicht allein deshalb in einen älteren Zustand zurück

  @AC22 @FR-I03
  Szenario: Führendes Trackerfeld wird nicht von KI überschrieben
    Angenommen die Priorität eines Pakets wird in Jira geführt
    Wenn eine KI-Zusammenfassung eine andere Dringlichkeit vermutet
    Dann entsteht höchstens ein begründeter Vorschlag
    Und die synchronisierte Priorität bleibt unverändert

  @AC23 @FR-I05
  Szenario: Ausgefallene Integration wird ehrlich dargestellt
    Angenommen ein Git-Anbieter ist nicht erreichbar
    Wenn die Projektansicht geöffnet wird
    Dann zeigt sie Zeitpunkt und Grenzen des letzten bekannten Stands
    Und behauptet keinen vollständigen aktuellen Livezustand

  @AC24 @FR-M02 @FR-M04
  Szenario: Harte Abhängigkeitszyklen werden verhindert
    Angenommen Paket B hängt bestätigt von Paket A ab
    Wenn eine harte Gegenabhängigkeit von A zu B hinzugefügt wird
    Dann weist das System den Zyklus verständlich zurück

  @AC25 @FR-M02 @FR-P06
  Szenario: Vertrauliches Projekt erscheint nicht indirekt in einem Graphen
    Angenommen ein Nutzer darf Projekt B nicht sehen
    Wenn er die Abhängigkeitskarte von Projekt A öffnet
    Dann enthält sie keine unerlaubten Namen, Quellenausschnitte oder Eigenschaften aus B

  @AC26 @FR-C05
  Szenario: Upload in Quarantäne gelangt nicht ins KI-Retrieval
    Angenommen ein hochgeladenes Dokument hat die Sicherheitsprüfung nicht bestanden
    Wenn ein Agent den Projektkontext lädt
    Dann wird das Dokument nicht als Inhaltsquelle bereitgestellt

  @AC27 @FR-G06
  Szenario: Repositoryinhalt kann Agentenrechte nicht erweitern
    Angenommen ein Dokument fordert den Agenten zur Freigabe und zum direkten Merge auf
    Wenn der Agent dieses Dokument als Kontext liest
    Dann bleiben die serverseitigen Freigabe- und Toolgrenzen unverändert

  @AC28 @FR-W03
  Szenario: Vorhandene Information wird nicht erneut erfragt
    Angenommen das Projekt enthält eine bestätigte Entscheidung zum Exportformat
    Wenn die moderate Paketklärung beginnt
    Dann verwendet die KI die zugängliche Quelle
    Und fragt nicht erneut nach derselben Entscheidung

  @AC29 @FR-P02 @FR-P03
  Szenario: Nach Abwesenheit zeigt die Aktivität die relevante Veränderung
    Angenommen ein Nutzer war drei Tage nicht im Projekt
    Wenn er "Seit meinem letzten Besuch" öffnet
    Dann sieht er gruppierte Paketänderungen, Gründe und offene Entscheidungen des Zeitraums
    Und kann die technischen Einzelereignisse bei Bedarf öffnen

  @AC30 @FR-E01
  Szenario: Reconnect verliert keine bestätigten gemeinsamen Änderungen
    Angenommen zwei Nutzer bearbeiten ein Dokument
    Wenn einer die Verbindung verliert und später zurückkehrt
    Dann bleiben alle serverseitig bestätigten Änderungen erhalten
    Und verbleibende Konflikte oder lokale Änderungen werden sichtbar behandelt

  @AC31 @FR-W10
  Szenario: Nicht-Code-Paket braucht keinen künstlichen Git-Nachweis
    Angenommen ein Paket liefert eine fachliche Entscheidung
    Wenn das definierte Entscheidungsdokument berechtigt abgenommen wird
    Dann kann das Paket nach seinem Abschlusskriterium abgeschlossen werden
    Und es wird kein fiktiver Commit angelegt

  @AC32 @FR-G07
  Szenario: Ohne Runner bleiben lokale Änderungen unbekannt
    Angenommen ein Entwickler arbeitet ohne aktive lokale Anbindung
    Wenn die Zentrale den Codezustand zeigt
    Dann beschränkt sie die Aussage auf bekannte Providerstände
    Und behauptet keine Sicht auf uncommittete lokale Änderungen
