"""Offline lineup HTML from the same read-only projection used by the website."""
import argparse
import html
import json
import re
from pathlib import Path
from lineup_layout import reading_document

def inline(text):
    def link(match):
        label,url=match.groups()
        if not re.match(r'^(?:https?://|#|\.{0,2}/)',url):return html.escape(label)
        return '<a href="'+html.escape(url,quote=True)+'">'+html.escape(label)+'</a>'
    parts=re.split(r'(\[[^\]]+\]\([^)]+\))',text)
    return ''.join(re.sub(r'\[([^\]]+)\]\(([^)]+)\)',link,p) if re.fullmatch(r'\[[^\]]+\]\([^)]+\)',p) else re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',html.escape(p)) for p in parts)

def body(markdown):
    lines=markdown.splitlines();out=[];i=0;listing=False
    def close_list():
        nonlocal listing
        if listing:out.append('</ul>');listing=False
    while i<len(lines):
        line=lines[i].strip()
        if line.startswith('|'):
            close_list();rows=[]
            while i<len(lines) and lines[i].strip().startswith('|'):
                cells=[x.strip() for x in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?',x) for x in cells):rows.append(cells)
                i+=1
            out.append('<div class="table-wrap" tabindex="0" role="region" aria-label="对比表格，可横向滚动"><table>')
            for j,row in enumerate(rows):
                tag='th' if j==0 else 'td'
                out.append('<tr>'+''.join('<'+tag+'>'+inline(c)+'</'+tag+'>' for c in row)+'</tr>')
            out.append('</table></div>');continue
        heading=re.match(r'^(#{3,6}) (.+)$',line)
        if heading:
            close_list();level=len(heading[1]);out.append(f'<h{level}>'+inline(heading[2])+f'</h{level}>')
        elif line.startswith('- '):
            if not listing:out.append('<ul>');listing=True
            out.append('<li>'+inline(line[2:])+'</li>')
        elif line:
            close_list();out.append('<p>'+inline(line)+'</p>')
        i+=1
    close_list();return ''.join(out)

def render_html(note,css=''):
    doc=reading_document(note)
    if not doc['profile']:raise ValueError('仅支持阵容阅读投影')
    title=html.escape(note['title'])
    nav=''.join('<a href="#'+s['id']+'">'+html.escape(s['title'])+'</a>' for s in doc['sections'])
    content=''.join('<section class="chapter" id="'+s['id']+'"><h2>'+html.escape(s['title'])+'</h2>'+body(s['markdown'])+'</section>' for s in doc['sections'])
    css+='\n*{box-sizing:border-box}body{overflow-wrap:anywhere} .table-wrap{overflow-x:auto;max-width:100%}th,td{width:auto} .chapter{min-width:0} @media(max-width:700px){.layout{display:block}.contents{position:static}table{min-width:520px}}'
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+title+' · 万象棋战术手册</title><style>'+css+'</style></head><body><header class="masthead"><p class="brand">万象棋 · 战术手册</p><h1>'+title+'</h1></header><div class="layout"><aside class="contents"><details open><summary>阅读目录</summary><nav>'+nav+'</nav></details><button onclick="window.print()">打印 / 保存为 PDF</button></aside><main class="main">'+content+'</main></div><footer class="footer">已有证据整理 · 可离线阅读</footer></body></html>'

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);args=p.parse_args();root=args.root.resolve()
    reference=root/'exports/常小娥通用打法.html'
    match=re.search(r'<style>(.*?)</style>',reference.read_text(encoding='utf-8'),re.S) if reference.exists() else None
    css=match[1] if match else 'body{margin:0;background:#18283a;color:#e5edf2;font:16px/1.8 sans-serif}.masthead,.main,.contents{padding:24px}.layout{display:grid;grid-template-columns:240px 1fr}nav a{display:block;color:#8fd6bf}.main{min-width:0}table{border-collapse:collapse}td,th{padding:10px;border:1px solid #425469}'
    (root/'exports').mkdir(exist_ok=True)
    from workspace import notes
    for note in notes(root):
        if note['type']!='lineup':continue
        path=root/'exports'/(note['title']+'.html')
        path.write_text(render_html(note,css),encoding='utf-8');print(path)

if __name__=='__main__':main()
