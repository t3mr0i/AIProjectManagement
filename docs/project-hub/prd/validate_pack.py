"""Validate documents and synthetic contracts, not a running Plane application."""
from __future__ import annotations
import copy, difflib, json, re
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from markdown_it import MarkdownIt
ROOT=Path(__file__).resolve().parent

def main()->None:
    results=[];validators={};examples={}
    stems=['package-revision','execution-authorization','domain-event','plane-package-profile']
    for stem in stems:
        raw=(ROOT/'schemas'/f'{stem}.schema.json').read_text()
        assert '"tenantId"' not in raw and '"packageId"' not in raw, f'Obsolete contract identity in {stem}'
        schema=json.loads(raw);Draft202012Validator.check_schema(schema)
        v=Draft202012Validator(schema,format_checker=FormatChecker())
        ex=json.loads((ROOT/'schemas'/f'{stem}.example.json').read_text());v.validate(ex)
        assert ex['schemaVersion']=='1.1.0'
        validators[stem]=v;examples[stem]=ex
        results.append(f'PASS Schema und synthetisches Beispiel: {stem} 1.1.0')
    def reject(label,stem,obj):
        try: validators[stem].validate(obj)
        except ValidationError:results.append('PASS Ungültiges Beispiel abgelehnt: '+label)
        else:raise AssertionError('Invalid example accepted: '+label)
    bad=copy.deepcopy(examples['execution-authorization']);bad['approvedBy']['kind']='agent';reject('Agent als Human-Approver','execution-authorization',bad)
    bad=copy.deepcopy(examples['execution-authorization']);bad['allowedActions'].append('merge_to_main');reject('Merge im Ausführungstoken','execution-authorization',bad)
    bad=copy.deepcopy(examples['package-revision']);bad['repositories'][0]['baseCommit']='main';reject('Branchname statt Commit','package-revision',bad)
    bad=copy.deepcopy(examples['domain-event']);bad.pop('deduplicationKey');reject('Fehlende Deduplikationskennung','domain-event',bad)
    bad=copy.deepcopy(examples['domain-event']);bad['actor']['kind']='agent';reject('Agentengeneriertes Human-Approval-Event','domain-event',bad)
    bad=copy.deepcopy(examples['plane-package-profile']);bad['packageId']=bad['workItemId'];reject('Zweite Paket-ID im Profil','plane-package-profile',bad)
    bad=copy.deepcopy(examples['plane-package-profile']);bad['status']='Done';reject('Duplizierter nativer Status im Profil','plane-package-profile',bad)
    bad=copy.deepcopy(examples['package-revision']);bad['tenantId']=bad.pop('workspaceId');reject('Veraltetes tenantId statt workspaceId','package-revision',bad)
    bad=copy.deepcopy(examples['package-revision']);bad['schemaVersion']='1.0.0';reject('Alter Vertrag 1.0.0','package-revision',bad)
    draft=copy.deepcopy(examples['package-revision']);draft.update(intent='',outcome='',criteria=[],repositories=[]);validators['package-revision'].validate(draft)
    results.append('PASS Unvollständiger Draft strukturell zulässig; keine Freigabe daraus abgeleitet')
    rev=examples['package-revision'];profile=examples['plane-package-profile'];auth=examples['execution-authorization'];event=examples['domain-event']
    assert profile['workItemId']==rev['workItemId']==auth['workItemId']==event['aggregateId']
    assert profile['workspaceId']==rev['workspaceId']==auth['workspaceId']==event['workspaceId']
    assert profile['projectId']==rev['projectId'] and auth['revisionId']==rev['id']
    results.append('PASS Beispielreferenzen verwenden konsistente native Workspace-/Issue-Identitäten')
    prd=(ROOT/'PRD.md').read_text();defined=re.findall(r'^\*\*(FR-[A-Z]\d{2}) —',prd,re.M)
    original=(ROOT/'diff/PRD-v0.1.md').read_text();old=re.findall(r'^\*\*(FR-[A-Z]\d{2}) —',original,re.M)
    assert len(defined)==len(set(defined))==73
    assert set(old)<=set(defined) and len(old)==59
    assert len([x for x in defined if x.startswith('FR-B')])==14
    results.append('PASS 73 eindeutige Requirements: 59 alte IDs erhalten, 14 Foundation-Anforderungen ergänzt')
    refs=json.loads((ROOT/'foundation/requirement-map.json').read_text())
    mapped=[x['requirementId'] for x in refs['requirements']]
    assert len(mapped)==len(set(mapped)) and set(mapped)==set(defined)
    results.append('PASS Vollständige Requirement-Zuordnung ohne Doppelungen')
    all_ids=[];count=0
    for name,pat,expected in [('core.feature',r'@(AC\d{2})',32),('plane-foundation.feature',r'@(PF\d{2})',14)]:
        text=(ROOT/'acceptance'/name).read_text()
        assert text.startswith('# language: de')
        cases=re.findall(pat,text);sc=re.findall(r'^  Szenario:',text,re.M)
        assert len(cases)==len(sc)==expected
        used=set(re.findall(r'@(FR-[A-Z]\d{2})',text));assert used<=set(defined),used-set(defined)
        for line in text.splitlines():
            if line.startswith('    '):assert re.match(r'    (Angenommen|Wenn|Dann|Und|Aber) ',line),line
        all_ids+=cases;count+=len(cases)
    assert len(all_ids)==len(set(all_ids))==46
    results.append('PASS 46 Scenario-IDs und ihre Requirement-Verweise strukturell geprüft')
    lock=json.loads((ROOT/'foundation/upstream-lock.json').read_text());evidence=json.loads((ROOT/'foundation/source-evidence.json').read_text())
    sha=lock['analysisCommit'];assert re.fullmatch('[0-9a-f]{40}',sha)
    assert evidence['analysisCommit']==refs['analysisCommit']==sha
    assert lock['implementationBaselineApproved'] is False and lock['licensePathApproved'] is False
    assert sha in prd and sha in (ROOT/'PLANE_FOUNDATION.md').read_text()
    srcids={x['id'] for x in evidence['sources']}
    for item in refs['requirements']:assert set(item['sourceIds'])<=srcids
    results.append('PASS Quellen-/Commitkonsistenz und offen markierte Baseline-/Vertriebsfreigaben')
    expected=''.join(difflib.unified_diff(original.splitlines(True),prd.splitlines(True),fromfile='v0.1/PRD.md',tofile='v0.2/PRD.md'))
    assert expected==(ROOT/'diff/PRD-v0.1-v0.2.diff').read_text()
    results.append('PASS Vollständiger PRD-Diff aus Original und neuer Fassung reproduziert')
    prohibited=['Für den Neubau wird weder ein Plane-Fork','Es hat einen eigenen Projektmanagement-Kern und austauschbare Anbindungen.','**Web-Anwendung:** TypeScript/React als Ausgangspunkt']
    assert not any(x in prd for x in prohibited)
    for f in [ROOT/'PRD.md',ROOT/'BOOTSTRAP.md',ROOT/'DESIGN_BRIEF.md',ROOT/'IMPLEMENTATION_PLAN.md']:
        assert '' not in f.read_text()
        assert not re.search(r'\b(TODO|TBD)\b',f.read_text())
    assert 'Erzeuge keine Greenfield-Anwendung' in (ROOT/'BOOTSTRAP.md').read_text()
    assert not (ROOT/'build_contracts.py').exists()
    results.append('PASS Bekannte Greenfield-Widersprüche und alter Schemagenerator entfernt')
    # Validate local markdown links, excluding historical non-operative snapshot.
    md=MarkdownIt('commonmark').enable('table')
    for file in ROOT.rglob('*.md'):
        if 'diff' in file.parts:continue
        for tok in md.parse(file.read_text()):
            for child in tok.children or []:
                if child.type=='link_open':
                    href=child.attrGet('href') or ''
                    if not href or href.startswith(('http:','https:','mailto:','#')):continue
                    target=href.split('#',1)[0]
                    assert (file.parent/target).exists(),f'Broken local link {file}: {href}'
    results.append('PASS Lokale Dokumentenlinks auf vorhandene Dateien geprüft')
    assert not any(p.suffix.lower() in {'.ttf','.otf','.woff','.woff2'} for p in ROOT.rglob('*'))
    results.append('PASS Keine Schriftdateien oder gebündelten Fremdproduktassets')
    report='# Tatsächlich ausgeführte Dokumentenprüfung\n\nStand: 24. September 2026 · Paket 0.2\n\n'
    report+='\n'.join('- '+r for r in results)+'\n'
    report+='''
## Grenzen dieser Prüfung

Geprüft wurden Dokumentstruktur, JSON-Schemas, synthetische Positiv-/Negativbeispiele, IDs, Verweise, Baselinekonsistenz und der Text-Diff. Die 46 Gherkin-Szenarien enthalten keine Anwendungsschritte und wurden nicht gegen Plane ausgeführt. Es wurde weder Plane gebaut noch eine echte Integration, Datenmigration, Sicherheitsgrenze, Freigabe oder Performance getestet. Quellen wurden gezielt statisch gelesen, nicht vollständig auditiert. Der HTML-Leser ist kein Produktmockup. Vertrags-/Lizenzfreigabe und Produktionsbaseline bleiben offen.
'''
    (ROOT/'VALIDATION.md').write_text(report)
    print('\n'.join(results));print('Document checks complete; application behavior NOT tested.')
if __name__=='__main__':main()
