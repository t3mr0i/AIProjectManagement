# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from pathlib import Path
import re, html
from markdown_it import MarkdownIt
root=Path(__file__).parent
files=[('PLANE_DELTA.md', 'delta', 'Was sich ändert'), ('PRD.md', 'prd', 'Vollständiges PRD'), ('PLANE_FOUNDATION.md', 'foundation', 'Plane-Bestand & Erweiterung'), ('IMPLEMENTATION_PLAN.md', 'implementation-plan', 'Implementierungsplan'), ('DESIGN_BRIEF.md', 'design-brief', 'Design auf Plane'), ('MIGRATION_AND_UPSTREAM.md', 'migration', 'Migration & Upstream'), ('BOOTSTRAP.md', 'bootstrap', 'Agenten-Startauftrag'), ('SOURCES.md', 'sources', 'Quellen'), ('VALIDATION.md', 'validation', 'Prüfbericht')]
prefixes={x[0]:x[1] for x in files}
md=MarkdownIt('commonmark',{'html':False}).enable('table')
def slug(text):
    return re.sub(r'-+','-',re.sub(r'[^\w\- ]','',text.lower()).replace(' ','-')).strip('-')
sections=[];toc=[]
for fname,prefix,label in files:
    text=(root/fname).read_text()
    text=re.sub(r'(?m)^(https://\S+)$',r'[Quelle öffnen](\1)',text)
    tokens=md.parse(text)
    for i,t in enumerate(tokens):
        if t.type=='heading_open':
            val=slug(tokens[i+1].content)
            ident=prefix+'-'+val
            t.attrSet('id',ident)
            if t.tag=='h2' and fname=='PRD.md': toc.append((ident,tokens[i+1].content))
        if t.type=='inline' and t.children:
            for c in t.children:
                if c.type=='link_open':
                    href=c.attrGet('href')
                    for fn,pref in prefixes.items():
                        if href==fn: c.attrSet('href','#'+pref)
                        elif href.startswith(fn+'#'): c.attrSet('href','#'+pref+'-'+href.split('#',1)[1])
                    if href.startswith('https://'): c.attrSet('rel','noreferrer')
    sections.append('<section class="document" id="'+prefix+'">'+md.renderer.render(tokens,md.options,{})+'</section>')
nav=''.join(f'<a href="#{pref}">{html.escape(label)}</a>' for _,pref,label in files)
subnav=''.join(f'<a href="#{ident}">{html.escape(title)}</a>' for ident,title in toc)
css='''
:root{color-scheme:light;--ink:#202b37;--muted:#536171;--line:#dce2e8;--accent:#225a7b;--paper:#fff;--soft:#f5f7f9}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:28px}body{overflow-wrap:anywhere;margin:0;color:var(--ink);background:var(--paper);font:16px/1.7 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}a{color:var(--accent);text-underline-offset:3px}aside{position:fixed;left:0;top:0;bottom:0;width:260px;padding:30px 22px;background:var(--soft);border-right:1px solid var(--line);overflow:auto}aside strong{display:block;font-size:17px;line-height:1.4}aside .meta{font-size:12px;color:var(--muted);margin:8px 0 24px}nav a{display:block;font-size:14px;padding:7px 0;text-decoration:none}nav a:hover{text-decoration:underline}details{border-top:1px solid var(--line);margin-top:18px;padding-top:14px}summary{cursor:pointer;font-size:13px;font-weight:650}.subnav a{font-size:12px;line-height:1.5;padding:5px 0;color:var(--muted)}main{margin-left:260px;padding:48px 5vw 80px;max-width:1430px}.intro{font-size:14px;color:var(--muted);border-bottom:2px solid var(--ink);padding-bottom:18px;margin-bottom:38px}.document+ .document{border-top:3px solid var(--line);margin-top:80px;padding-top:36px}h1{font-size:34px;line-height:1.22;letter-spacing:-.025em;margin:0 0 26px}h2{font-size:25px;line-height:1.35;letter-spacing:-.015em;margin:48px 0 18px}h3{font-size:19px;line-height:1.4;margin:30px 0 12px}p{margin:0 0 16px}strong{font-weight:680}ul,ol{padding-left:25px}li{margin:7px 0}table{width:100%;border-collapse:collapse;margin:22px 0 30px;font-size:14px;line-height:1.55;display:block;overflow:auto}th,td{text-align:left;vertical-align:top;padding:12px 13px;border:1px solid var(--line);min-width:95px}th{background:var(--soft);font-weight:650}tr:nth-child(even) td{background:#fafbfc}code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.87em;overflow-wrap:anywhere;background:var(--soft);padding:2px 4px;border-radius:3px}pre{padding:18px;background:var(--soft);border:1px solid var(--line);overflow:auto;line-height:1.6}pre code{padding:0;overflow-wrap:normal}blockquote{margin:22px 0;padding:4px 18px;border-left:3px solid var(--accent);color:var(--muted)}hr{border:0;border-top:1px solid var(--line);margin:32px 0}
@media(max-width:960px){aside{position:static;width:auto;border-right:0;border-bottom:1px solid var(--line);padding:20px}aside nav{display:flex;flex-wrap:wrap;gap:8px 20px}aside details{display:none}main{margin:0;padding:28px 20px 60px}h1{font-size:29px}h2{font-size:23px}table{font-size:13px}th,td{padding:10px}}
@media print{aside{display:none}main{margin:0;max-width:none;padding:0}body{font-size:10pt;line-height:1.5}h1{font-size:24pt}h2{font-size:17pt;break-after:avoid}h3{font-size:13pt;break-after:avoid}table{display:table;font-size:9pt}tr{break-inside:avoid}a{color:inherit}.document+.document{break-before:page}pre{white-space:pre-wrap} }
'''
html_doc='''<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Projektzentrale auf Plane — PRD 0.2</title><style>'''+css+'''</style></head><body><aside><strong>Projektzentrale<br>auf Plane</strong><div class="meta">PRD 0.2 · 24. September 2026<br>Plane Foundation · Umsetzungsentwurf</div><nav>'''+nav+'''</nav><details open><summary>PRD-Kapitel</summary><nav class="subnav">'''+subnav+'''</nav></details></aside><main><div class="intro">Plane ist die verbindliche Foundation. · 73 funktionale Anforderungen · 46 spezifizierte Abnahmeszenarien · Dokumentenpaket, keine implementierte Plane-Erweiterung.</div>'''+''.join(sections)+'''</main></body></html>'''
(root/'READABLE.html').write_text(html_doc)
print('reader bytes',len(html_doc.encode()))
