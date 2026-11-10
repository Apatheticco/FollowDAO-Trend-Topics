#!/usr/bin/env python3
"""console.py — console-mcp 会话客户端(v3.7.0):topic.py / downstream-check.py 共用。
传输复用 b0_fetch.rpc(系统 curl;凭证运行时读 ~/.claude.json,不落盘不打印)。

注入(回归):CONSOLE_FAKE=<json 文件> 时不联网,题目存在该文件里(跨进程持久),
  create 分配新 id、update 改字段、list 按日期过滤——让 topic.py 的「预检→写→记账→回读」整条链能离线测。
  CONSOLE_FAKE_FAIL=create|update 时对应写操作返回失败,用来测「写失败不落账」。
  CONSOLE_FAKE_RAISE=create|update 时写操作照常生效、随后抛 ConsoleError(模拟服务端已写、客户端超时/读坏回包,10-30 retro)。
"""
import json, os, sys, datetime, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


class ConsoleError(Exception):
    pass


def _text(r):
    content = (r.get('result') or {}).get('content') or []
    return next((c.get('text') for c in content if c.get('type') == 'text'), '') or ''


class Console:
    def __init__(self):
        self.fake = os.environ.get('CONSOLE_FAKE')
        if self.fake:
            return
        from b0_fetch import cfg, rpc
        self._rpc = rpc
        self.url, self.h = cfg()
        r, self.sid = rpc(self.url, self.h, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "trend-scout-topic", "version": "1"}}})
        if 'error' in r:
            raise ConsoleError(f"initialize 失败: {r['error']}")
        try:
            rpc(self.url, self.h, {"jsonrpc": "2.0", "method": "notifications/initialized"}, self.sid)
        except Exception:
            pass
        self._id = 10

    def call(self, name, args):
        if self.fake:
            r = _fake_call(self.fake, name, args)
            if os.environ.get('CONSOLE_FAKE_RAISE') and name.startswith(os.environ['CONSOLE_FAKE_RAISE'] + '_'):
                raise ConsoleError(f'{name} fake raise after write')
            return r
        self._id += 1
        r, self.sid = self._rpc(self.url, self.h, {"jsonrpc": "2.0", "id": self._id, "method": "tools/call",
                                                   "params": {"name": name, "arguments": args}}, self.sid)
        if 'error' in r:
            raise ConsoleError(f"{name} 失败: {r['error']}")
        txt = _text(r)
        try:
            return json.loads(txt)
        except Exception:
            raise ConsoleError(f"{name} 返回非 JSON: {txt[:200]}")

    def list_day(self, day, lang=None, status=None):
        out, offset = [], 0
        for _ in range(10):
            args = {"start_date": day, "end_date": day, "limit": 100, "offset": offset}
            if lang:
                args['lang'] = lang
            if status is not None:
                args['status'] = status
            d = self.call('list_trending_topics', args)
            out += d.get('topics') or []
            if not d.get('has_more'):
                break
            offset += 100
        return out

    def get(self, tid, lang=None, max_days=7):
        """按 id 取题(console 没有按 id 查的接口):先用 b0-latest.json 里的 created_at 定日期,查不到再往前逐日翻。"""
        tid = str(tid)
        days = []
        b0 = os.environ.get('B0JSON') or os.path.expanduser('~/.trend-scout/b0-latest.json')
        try:
            d = json.load(open(b0, encoding='utf-8'))
            for t in (d if isinstance(d, list) else d.get('topics') or []):
                if str(t.get('id')) == tid and t.get('created_at'):
                    days.append(str(t['created_at'])[:10])
        except Exception:
            pass
        # 11-07 复盘(10000003136 update 被拦「看板上找不到题(近 7 天)」):b0-latest 只有近 3 天,>7 天的老题按台账 create 行定建题日
        try:
            act = os.environ.get('ACTIONS') or os.path.expanduser('~/.trend-scout/actions.tsv')
            for ln in open(act, encoding='utf-8'):
                c = ln.split('\t', 3)
                if len(c) > 2 and c[1] == 'create' and c[2] == tid and c[0].isdigit():
                    x = datetime.datetime.fromtimestamp(int(c[0]) / 1000).date()
                    for y in (x, x - datetime.timedelta(days=1)):   # 落账时刻与 created_at 可能跨零点
                        if y.isoformat() not in days:
                            days.append(y.isoformat())
        except Exception:
            pass
        today = datetime.date.today()
        for k in range(max_days + 1):
            x = (today - datetime.timedelta(days=k)).isoformat()
            if x not in days:
                days.append(x)
        for day in days:
            for t in self.list_day(day, lang=lang):
                if str(t.get('id')) == tid:
                    return t
        return None


# ── 离线假 console(回归用)───────────────────────────────────────────────
def _fake_load(path):
    try:
        return json.load(open(path, encoding='utf-8'))
    except Exception:
        return {"next_crypto": 90001, "next_tradfi": 10000090001, "topics": []}


def _fake_call(path, name, args):
    st = _fake_load(path)
    fail = os.environ.get('CONSOLE_FAKE_FAIL', '')
    if name == 'create_trending_topic':
        if fail == 'create':
            return {"success": False, "error": "fake create failure"}
        dom = args.get('domain', 'crypto')
        key = 'next_' + dom
        tid = st[key]
        st[key] += 1
        kw = args.get('keywords', '')
        t = {"id": tid, "domain": dom, "title": args['title'], "keywords": kw, "status": 2,
             "created_at": time.strftime('%Y-%m-%d %H:%M:%S'), "closed_ts": int(time.time() * 1000) + 86400000,
             "original_title": args['title'], "tags": [{"id": 214728}] if 'Neutron' in kw else [],
             "score_weight": args.get('score_weight', 1)}
        st['topics'].append(t)
        json.dump(st, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
        return {"success": True, "id": tid, "domain": dom, "title": t['title'], "status": 2, "matched_tags": t['tags']}
    if name == 'update_trending_topic':
        if fail == 'update':
            return {"success": False, "error": "fake update failure"}
        t = next((x for x in st['topics'] if str(x['id']) == str(args.get('id'))), None)
        if not t:
            return {"success": False, "error": "not found"}
        ch = {"domain": t['domain']}
        if 'status' in args:
            ch.update(previous_status=t['status'], new_status=args['status'])
            t['status'] = args['status']
        if 'new_title' in args:
            ch.update(previous_title=t['title'], new_title=args['new_title'])
            t['title'] = args['new_title']
        if 'keywords' in args:
            ch.update(previous_keywords=t['keywords'], new_keywords=args['keywords'])
            t['keywords'] = args['keywords']
            t['tags'] = [{"id": 214728}] if 'Neutron' in args['keywords'] else []
            ch['auto_matched_tags'] = t['tags']
        if 'tags' in args:
            t['tags'] = json.loads(args['tags'])
        if 'score_weight' in args:
            ch.update(previous_score_weight=t.get('score_weight', 1), new_score_weight=args['score_weight'])
            t['score_weight'] = args['score_weight']
        json.dump(st, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
        return {"success": True, "id": t['id'], "domain": t['domain'], "title": t['title'], "changes": ch}
    if name == 'list_trending_topics':
        day = args.get('start_date')
        ts = [x for x in st['topics'] if str(x.get('created_at', ''))[:10] == day]
        if args.get('status') is not None:
            ts = [x for x in ts if x['status'] == args['status']]
        if args.get('lang') == 'en':
            ts = [dict(x, title=x.get('title_en') or x['title']) for x in ts]
        return {"success": True, "total": len(ts), "has_more": False, "topics": ts}
    raise ConsoleError(f"fake 不支持 {name}")
