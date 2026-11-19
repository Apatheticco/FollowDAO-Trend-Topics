#!/usr/bin/env python3
"""tw-dump.py — 推特 list 直连拉取,替代 A1 双栈的 haiku 子进程(audit1119)。

为什么:A1 是固定流程(翻页→按时间排→每条一行),不需要模型判断;11-19 首扫两个子进程各耗 13~15 万 token。
直连走 news_fetch.SSE(与 news-fetch.py 同一套 SSE 握手),11-19 实测 list_timeline 一页 20 条、带 next_cursor。
server 降级梯:先 followin;配额耗尽或取数失败再换 followdao-test(两边配额池独立);两个都失败才退出码 2。

用法: tw-dump.py <list_id> [--pages 4] [--n 15] [--since <ms>]
  --since 只留晚于该毫秒时间戳的推(刷新传 last-refresh 末行;首扫不传)
输出:每条一行 [MM/DD HH:MM] @author | 👍likes 🔁rt 💬reply | 正文前130字(北京时间,按时间倒序),
      末行原样附服务端截断警告,最后一行 TWDUMP: list=… 取到=N 输出=N server=…
注入(回归): TW_FAKE=<json 文件>,内容为若干页 results/meta 的列表,不联网。
"""
import json, os, sys, datetime

BJ = datetime.timezone(datetime.timedelta(hours=8))


def parse_time(s):
    return datetime.datetime.strptime(s, '%a %b %d %H:%M:%S %z %Y')


def pages_live(list_id, max_pages, server):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import news_fetch as nf
    if server != 'followin':
        orig = nf._cfg

        def _cfg_alt():
            c = json.load(open(os.path.expanduser('~/.claude.json')))
            s = (c.get('mcpServers') or {}).get(server)
            if not s:
                for p in c.get('projects', {}).values():
                    s = (p.get('mcpServers') or {}).get(server)
                    if s:
                        break
            if not s:
                raise SystemExit('🚨 ~/.claude.json 无 %s MCP 配置' % server)
            return s['url'], dict(s.get('headers') or {})
        nf._cfg = _cfg_alt
    try:
        s = nf.SSE()
    finally:
        if server != 'followin':
            nf._cfg = orig
    cursor = None
    for _ in range(max_pages):
        args = {"action": "list_timeline", "list_id": list_id, "limit": 20}
        if cursor:
            args["cursor"] = cursor
        r = s.call('twitter', args)
        yield r
        meta = (r or {}).get('meta') or {}
        fa = meta.get('filters_applied') or {}
        cursor = fa.get('next_cursor')
        if not fa.get('has_next_page') or not cursor:
            return


def collect(pages, since_ms):
    rows, warns, got, err = [], [], 0, None
    for r in pages:
        if not isinstance(r, dict) or '_error' in r or 'results' not in r:
            err = (r or {}).get('_error') if isinstance(r, dict) else str(r)[:200]
            break
        meta = r.get('meta') or {}
        for w in meta.get('warnings') or []:
            if w.get('message'):
                warns.append(w['message'])
        oldest = None
        for x in r['results']:
            got += 1
            try:
                t = parse_time(x['createdAt'])
            except Exception:
                continue
            oldest = t if oldest is None or t < oldest else oldest
            if since_ms and t.timestamp() * 1000 <= since_ms:
                continue
            rows.append((t, x))
        if since_ms and oldest is not None and oldest.timestamp() * 1000 <= since_ms:
            break
    return rows, warns, got, err


def fmt(t, x):
    a = (x.get('author') or {}).get('userName', '?')
    txt = ' '.join((x.get('text') or '').split())[:130]
    return '[%s] @%s | 👍%s 🔁%s 💬%s | %s' % (
        t.astimezone(BJ).strftime('%m/%d %H:%M'), a, x.get('likeCount', 0),
        x.get('retweetCount', 0), x.get('replyCount', 0), txt)


def main(argv):
    if not argv or argv[0].startswith('-'):
        print(__doc__)
        return 1
    list_id = argv[0]
    opt = {'--pages': '4', '--n': '15', '--since': '0'}
    i = 1
    while i < len(argv):
        if argv[i] in opt and i + 1 < len(argv):
            opt[argv[i]] = argv[i + 1]
            i += 2
        else:
            print('未知参数: ' + argv[i])
            return 1
    max_pages, n, since = int(opt['--pages']), int(opt['--n']), int(opt['--since'])
    fake = os.environ.get('TW_FAKE')
    tried = []
    for server in (['fake'] if fake else ['followin', 'followdao-test']):
        try:
            pages = json.load(open(fake)) if fake else pages_live(list_id, max_pages, server)
            rows, warns, got, err = collect(pages, since)
        except SystemExit as e:
            err, rows, warns, got = str(e), [], [], 0
        except Exception as e:
            err, rows, warns, got = '%s: %s' % (type(e).__name__, e), [], [], 0
        if err and not rows:
            tried.append('%s(%s)' % (server, err[:80]))
            continue
        rows.sort(key=lambda z: z[0], reverse=True)
        for t, x in rows[:n]:
            print(fmt(t, x))
        if warns:
            print('截断警告: ' + ' | '.join(warns))
        if err:
            print('⚠️ 中途出错(已输出取到的部分): ' + err[:120])
        print('TWDUMP: list=%s 取到=%d 输出=%d server=%s' % (list_id, got, min(n, len(rows)), server))
        return 0
    print('🚨 两个 server 都失败: ' + '; '.join(tried))
    print('TWDUMP: list=%s 取到=0 输出=0 server=无' % list_id)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
