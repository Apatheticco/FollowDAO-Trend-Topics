#!/usr/bin/env python3
# b0-fetch.py — 直接经 console-mcp 的 HTTP 端点拉 B0(v2.9.81)。凭证运行时从 ~/.claude.json 读,不落盘不打印。
# 用法: b0-fetch.py [start YYYY-MM-DD] [end YYYY-MM-DD] [--status N] [--out 文件]   默认 近3天(today-3~today), 全状态, 输出 ~/.trend-scout/b0-latest.json
# 自动翻页(offset)直到 has_more=false —— 满额守卫内建。
import json, os, sys, datetime, re
def cfg():
    c=json.load(open(os.path.expanduser('~/.claude.json')))
    s=c.get('mcpServers',{}).get('console-mcp')
    if not s: raise SystemExit('🚨 ~/.claude.json 无 mcpServers.console-mcp')
    return s['url'], dict(s.get('headers',{}))
def rpc(url, headers, payload, sid=None):
    # 走系统 curl(macOS 钥匙串证书;Python.org 版 python3 无 CA 链会 CERTIFICATE_VERIFY_FAILED)。
    # 凭证经 0600 临时文件以 -H @file 传入,不出现在进程参数里;URL 上的 api_key 仍在 ps 可见(用户本机,可接受)。
    import subprocess, tempfile
    h={'Content-Type':'application/json','Accept':'application/json, text/event-stream'}; h.update(headers)
    if sid: h['Mcp-Session-Id']=sid
    hf=tempfile.NamedTemporaryFile('w',delete=False,suffix='.hdr'); os.chmod(hf.name,0o600)
    hf.write('\n'.join(f'{k}: {v}' for k,v in h.items())); hf.close()
    df=tempfile.NamedTemporaryFile('w',delete=False,suffix='.json'); df.write(json.dumps(payload)); df.close()
    try:
        r=subprocess.run(['curl','-sS','-D','-','-H','@'+hf.name,'--data-binary','@'+df.name,'--max-time','60',url],capture_output=True,text=True)
    finally:
        os.unlink(hf.name); os.unlink(df.name)
    if r.returncode!=0: raise SystemExit(f"🚨 curl 失败 rc={r.returncode}: {r.stderr.strip()[:200]}")
    raw=r.stdout
    # 拆响应头/体(可能有 100-continue 多段头)
    head, body = '', raw
    while body.startswith('HTTP/'):
        i=body.find('\r\n\r\n'); 
        if i<0: i=body.find('\n\n'); sep=2
        else: sep=4
        head, body = body[:i], body[i+sep:]
    sid2=sid; ct=''
    for line in head.splitlines():
        if line.lower().startswith('mcp-session-id:'): sid2=line.split(':',1)[1].strip()
        if line.lower().startswith('content-type:'): ct=line.split(':',1)[1].strip()
    if 'text/event-stream' in ct:
        objs=[json.loads(l[5:].strip()) for l in body.splitlines() if l.startswith('data:') and l[5:].strip()]
        obj=next((o for o in objs if o.get('id')==payload.get('id')), objs[-1] if objs else {})
    else:
        obj=json.loads(body) if body.strip() else {}
    return obj, sid2
def main():
    a=sys.argv[1:]; today=datetime.date.today()
    out=os.path.expanduser('~/.trend-scout/b0-latest.json'); status=None; dates=[]
    i=0
    while i<len(a):
        if a[i]=='--out': out=a[i+1]; i+=2
        elif a[i]=='--status': status=int(a[i+1]); i+=2
        else: dates.append(a[i]); i+=1
    start=dates[0] if dates else (today-datetime.timedelta(days=3)).isoformat()   # 默认近 3 天:48h 窗口题闸需要 >48h 的在线题在视野内(昨天~今天按定义拉不到)
    end=dates[1] if len(dates)>1 else today.isoformat()
    url,headers=cfg()
    init={"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"trend-scout-b0","version":"1"}}}
    r,sid=rpc(url,headers,init)
    if 'error' in r: raise SystemExit(f"🚨 initialize 失败: {r['error']}")
    try: rpc(url,headers,{"jsonrpc":"2.0","method":"notifications/initialized"},sid)
    except Exception: pass
    topics=[]; offset=0; total=None; pages=0
    while True:
        args={"start_date":start,"end_date":end,"limit":100,"offset":offset}
        if status is not None: args['status']=status
        r,sid=rpc(url,headers,{"jsonrpc":"2.0","id":2+pages,"method":"tools/call","params":{"name":"list_trending_topics","arguments":args}},sid)
        if 'error' in r: raise SystemExit(f"🚨 tools/call 失败: {r['error']}")
        content=r.get('result',{}).get('content',[])
        txt=next((c.get('text') for c in content if c.get('type')=='text'),None)
        if not txt: raise SystemExit(f"🚨 无 text 内容: {json.dumps(r)[:300]}")
        d=json.loads(txt)
        topics+=d.get('topics',[]); total=d.get('total'); pages+=1
        if not d.get('has_more') or pages>20: break
        offset+=100
    seen=set(); uniq=[]
    for t in topics:
        if t['id'] in seen: continue
        seen.add(t['id']); uniq.append(t)
    json.dump({"fetched_at":datetime.datetime.now().isoformat(timespec='seconds'),"date_range":f"{start} ~ {end}","status":status,"total":total,"pages":pages,"topics":uniq},open(out,'w',encoding='utf-8'),ensure_ascii=False)
    st={}
    for t in uniq: st[t.get('status')]=st.get(t.get('status'),0)+1
    print(f"B0 → {out}: {len(uniq)} 条 (total={total}, {pages} 页) status分布={dict(sorted(st.items()))} 范围={start}~{end}")
if __name__=='__main__': main()
