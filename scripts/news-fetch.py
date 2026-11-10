#!/usr/bin/env python3
"""news-fetch.py — 脚本直连 followin MCP(SSE)拉新闻,落 dump 供 hot-names.py 用(v3.3.3)。

**为什么直连而不是 haiku 子进程转录**:子进程要把几十 KB JSON 原样复述进 Write,转录本身是出错点;
SSE 握手 09-08 实测三步即通(GET /sse 得 endpoint → POST initialize 202 → POST tools/call 202,结果从 SSE 流回),
只是裸 MCP 的 news 参数与会话包装不同:**没有 categories,用 sources=[telegram|twitter]**,空 query 走内部十类召回。
凭证:~/.claude.json 的 mcpServers.followin(url + x-api-key),运行时读,不落盘。
用法: news-fetch.py [--range 6h] [--limit 50] [--sources telegram,twitter,media]   → 写 ~/.trend-scout/news-dump/<ts>.json 并打印路径
      news-fetch.py --latest [max_age_h]   → 打印最新 dump 路径(超龄则空)
注入(回归): NEWS_DUMP_DIR 改目录。
"""
import json, os, ssl, sys, time, threading, queue, urllib.request
from urllib.parse import urljoin

DUMP=os.environ.get('NEWS_DUMP_DIR') or os.path.expanduser('~/.trend-scout/news-dump')

def _cfg():
    c=json.load(open(os.path.expanduser('~/.claude.json')))
    s=(c.get('mcpServers') or {}).get('followin')
    if not s:
        for p in c.get('projects',{}).values():
            s=(p.get('mcpServers') or {}).get('followin')
            if s: break
    if not s: raise SystemExit('🚨 ~/.claude.json 无 followin MCP 配置')
    return s['url'], dict(s.get('headers') or {})

class SSE:
    def __init__(self):
        self.url,self.hdr=_cfg(); self.q=queue.Queue()
        try:
            import certifi; self.ctx=ssl.create_default_context(cafile=certifi.where())
        except Exception: self.ctx=ssl.create_default_context()
        threading.Thread(target=self._read,daemon=True).start()
        ev=self.q.get(timeout=25)
        if ev.get('event')!='endpoint': raise SystemExit('🚨 SSE 首事件不是 endpoint: %s'%str(ev)[:120])
        self.post=urljoin(self.url,ev['data']); self._id=0
        self.rpc({"jsonrpc":"2.0","id":self._nid(),"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"trend-scout-news","version":"1"}}})
        self._wait(self._id); self.rpc({"jsonrpc":"2.0","method":"notifications/initialized"})
    def _nid(self): self._id+=1; return self._id
    def _read(self):
        req=urllib.request.Request(self.url,headers=dict(self.hdr,**{'Accept':'text/event-stream'}))
        try:
            with urllib.request.urlopen(req,timeout=60,context=self.ctx) as r:
                ev={}
                for raw in r:
                    line=raw.decode('utf-8','ignore').rstrip('\n')
                    if line.startswith('event:'): ev['event']=line[6:].strip()
                    elif line.startswith('data:'): ev['data']=ev.get('data','')+line[5:].strip()
                    elif line=='' and ev: self.q.put(ev); ev={}
        except Exception as e: self.q.put({'event':'ERR','data':str(e)[:200]})
    def rpc(self,p):
        req=urllib.request.Request(self.post,data=json.dumps(p).encode(),headers=dict(self.hdr,**{'Content-Type':'application/json'}),method='POST')
        urllib.request.urlopen(req,timeout=30,context=self.ctx).read()
    def _wait(self,rid,timeout=60):
        t0=time.time()
        while time.time()-t0<timeout:
            ev=self.q.get(timeout=timeout)
            if ev.get('event')=='ERR': raise SystemExit('🚨 SSE 流错误: '+ev['data'])
            try: d=json.loads(ev.get('data','{}'))
            except Exception: continue
            if d.get('id')==rid: return d
        raise SystemExit('🚨 等待 id=%s 超时'%rid)
    def call(self,name,args):
        rid=self._nid(); self.rpc({"jsonrpc":"2.0","id":rid,"method":"tools/call","params":{"name":name,"arguments":args}})
        d=self._wait(rid); content=(d.get('result') or {}).get('content') or []
        txt=content[0].get('text','') if content else ''
        try: return json.loads(txt)
        except Exception: return {'_error':txt[:300]}

def _norm(items, src):
    out=[]
    for it in items:
        ki=it.get('kol_info') or {}
        su=it.get('source_url') or ''; dom=su.split('/')[2] if su.count('/')>=2 else ''
        nm=ki.get('name') or (dom if (it.get('source_name') in (None,'media','followin') and dom) else it.get('source_name')) or su[:40]
        out.append({'ts':it.get('published_ts'),'src':src,
                    'name':nm,   # media 文章按域名计源,否则 27 篇文章塌成一个源 "media"、共现计数失真
                    'kol':ki.get('name'),'lang':it.get('source_lang'),
                    'text':((it.get('title') or '')+' '+(it.get('content') or ''))[:1200]})
    return out

def fetch(rng='6h',limit=50,sources=('telegram','twitter','media')):
    s=SSE(); pulls={}; errs={}
    for src in sources:
        args={'asset_type':'crypto','time_range':rng,'limit':limit,'verbosity':'standard'}
        if src!='media': args['sources']=[src]
        r=s.call('news',args)
        if '_error' in r: errs[src]=r['_error']; pulls[src]=[]; continue
        res=r.get('results') or {}
        pulls[src]=_norm(res.get('articles') or [],src+':article')+_norm(res.get('social') or [],src+':social')
    os.makedirs(DUMP,exist_ok=True)
    ts=int(time.time()*1000); path=os.path.join(DUMP,f'{ts}.json')
    json.dump({'ts':ts,'range':rng,'pulls':pulls,'errors':errs},open(path,'w',encoding='utf-8'),ensure_ascii=False)
    for f in sorted(x for x in os.listdir(DUMP) if x.endswith('.json'))[:-48]: os.remove(os.path.join(DUMP,f))   # 只留最近 48 份(≈两天)
    return path,pulls,errs

def recent(max_age_h=6.0):
    """窗口内的全部 dump(新→旧)。v3.3.5:followin 的空 query 召回是「当下热门 top-N」,不是时间窗全集——
    09-08 实测 17:41 dump 里有 crypto_banter 的 AERO 帖,21:58 再拉(仍在 6h 内)它已不在返回里。
    只喂最新一份会把 4 小时前刷到的帖子当没发生过;把窗口内所有 dump 一起喂,才是真正的 6h 视野。"""
    if not os.path.isdir(DUMP): return []
    now=time.time()*1000
    fs=sorted((f for f in os.listdir(DUMP) if f.endswith('.json')), reverse=True)
    return [os.path.join(DUMP,f) for f in fs if (now-int(f[:-5]))/3600e3<=max_age_h]

def latest(max_age_h=2.0):
    if not os.path.isdir(DUMP): return None
    fs=sorted(f for f in os.listdir(DUMP) if f.endswith('.json'))
    if not fs: return None
    p=os.path.join(DUMP,fs[-1]); age=(time.time()*1000-int(fs[-1][:-5]))/3600e3
    return p if age<=max_age_h else None

if __name__=='__main__':
    a=sys.argv[1:]
    if '--latest' in a:
        i=a.index('--latest'); mh=float(a[i+1]) if len(a)>i+1 else 2.0
        p=latest(mh); print(p or ''); sys.exit(0)
    rng=a[a.index('--range')+1] if '--range' in a else '6h'
    lim=int(a[a.index('--limit')+1]) if '--limit' in a else 50
    srcs=tuple(a[a.index('--sources')+1].split(',')) if '--sources' in a else ('telegram','twitter','media')
    p,pulls,errs=fetch(rng,lim,srcs)
    print(p); print('  '+' | '.join(f'{k}={len(v)}' for k,v in pulls.items())+(('  ⚠️errors: '+json.dumps(errs,ensure_ascii=False)[:200]) if errs else ''))
