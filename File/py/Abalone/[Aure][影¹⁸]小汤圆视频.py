# -*- coding: utf-8 -*-
# [小汤圆视频¹⁸  更新于:2026-11-06 17:45]
import json
import re
import time
import threading
import gzip
import zlib
import urllib.request
from urllib.parse import quote, unquote

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        def proxy(self, params):
            return [404, "text/plain", ""]
        def localProxy(self, params):
            return [404, "text/plain", ""]

NAME = "小汤圆视频"
HOSTS = ["https://mmajj.icu"]
UA = "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 28
CACHE_TTL = 30
DEBUG = False

AD_DOMAINS = ("ddimg.cn", "platform-permanent", "trivolna", "adx", "advert")

CATS = [
    ("1", "国产"), ("2", "日韩"), ("3", "欧美"), ("4", "动漫"),
    ("10", "吃瓜黑料"), ("11", "酒店探花"), ("12", "网红主播"), ("13", "网络传媒"),
    ("19", "伦理影片"), ("20", "自拍偷拍"), ("21", "反差母狗"), ("8", "中文字幕"),
    ("9", "高清无码"), ("16", "日韩精品"), ("17", "AV明星"), ("18", "AV解说"),
    ("22", "熟女少妇"), ("23", "乱伦强奸"), ("14", "欧美精品"), ("15", "成人动漫"),
]


class Spider(BaseSpider):

    def __init__(self):
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self._cache = {}
        self._cache_time = {}
        self._lock = threading.Lock()

    def init(self, extend=""):
        if isinstance(extend, dict):
            cfg = extend
        elif extend:
            try:
                cfg = json.loads(extend)
            except Exception:
                cfg = {}
        else:
            cfg = {}
        if not isinstance(cfg, dict):
            return
        site = (cfg.get("site") or cfg.get("url") or "").strip().rstrip("/")
        if site:
            with self._lock:
                self.hosts = [site] + [h for h in self.hosts if h != site]
                self.host = self.hosts[0]
        self.options = cfg

    def destroy(self):
        with self._lock:
            self._cache.clear()
            self._cache_time.clear()
        self.options = {}

    def homeContent(self, filter):
        return {
            "class": [{"type_id": t, "type_name": n} for t, n in CATS],
            "list": [self._vod(x) for x in self._home_items()],
        }

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        if tid.startswith(("actor/", "director/", "tag/")):
            name = unquote(tid.split("/", 1)[1] if "/" in tid else tid.replace("tag/", "", 1))
            items, pc = self._fetch_search(name, pg)
            return {"list": [self._vod(x) for x in items], "page": pg, "pagecount": pc, "limit": PAGE_SIZE, "total": 999999}
        items, pc = self._fetch_list(tid, pg)
        return {"list": [self._vod(x) for x in items], "page": pg, "pagecount": pc, "limit": PAGE_SIZE, "total": 999999}

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        items, pc = self._fetch_search(str(key or "").strip(), pg)
        return {"list": [self._vod(x) for x in items], "page": pg, "pagecount": pc, "limit": PAGE_SIZE, "total": 999999}

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        responses = [self._detail(str(v)) for v in ids]
        merged = {k: v for k, v in (responses[0] or {}).items() if k != "list"}
        merged["list"] = [item for r in responses for item in (r.get("list") or [])]
        return merged

    def playerContent(self, flag, id, vipFlags):
        url = self._fetch_play(str(id or ""))
        if not url:
            return {"parse": 0, "msg": "无法获取播放地址"}
        return {"parse": 0, "jx": 0, "url": url, "header": {"User-Agent": UA}}

    def liveContent(self, url):
        return "[]"

    def action(self, action):
        return {"msg": "不支持此操作"}

    def _detail(self, vod_id):
        parts = str(vod_id).split("|", 1)
        vid = parts[0]
        pic = parts[1] if len(parts) > 1 else ""
        d = self._fetch_detail(vid)
        if not d:
            return {"list": [], "msg": "未找到此影片"}
        vod = {
            "vod_id": str(vod_id),
            "vod_name": d.get("name") or vid,
            "vod_pic": pic or d.get("pic") or "",
            "type_name": d.get("category") or "",
            "vod_year": "",
            "vod_area": "",
            "vod_remarks": d.get("remarks") or "",
            "vod_director": "",
            "vod_actor": "",
            "vod_content": d.get("description") or "",
            "vod_play_from": d.get("play_from") or "正片",
            "vod_play_url": "正片$%s" % (d.get("url") or vid),
        }
        return {"list": [vod]}

    def _home_items(self):
        html = self._get_html(self.host + "/")
        if not html:
            return []
        return self._parse_cards(html)

    def _fetch_list(self, tid, pg):
        if pg <= 1:
            url = "%s/index.php/vod/type/id/%s.html" % (self.host, tid)
        else:
            url = "%s/index.php/vod/type/id/%s/page/%s.html" % (self.host, tid, pg)
        html = self._get_html(url)
        if not html:
            return [], pg
        return self._parse_cards(html), self._parse_pagecount(html, pg)

    def _fetch_search(self, kw, pg):
        kw_enc = quote(kw, safe="")
        if pg <= 1:
            url = "%s/index.php/vod/search/wd/%s.html" % (self.host, kw_enc)
        else:
            url = "%s/index.php/vod/search/page/%s/wd/%s.html" % (self.host, pg, kw_enc)
        html = self._get_html(url)
        if not html:
            return [], pg
        return self._parse_cards(html), self._parse_pagecount(html, pg)

    def _fetch_detail(self, vid):
        url = "%s/index.php/vod/play/id/%s/sid/1/nid/1.html" % (self.host, vid)
        html = self._get_html(url)
        if not html:
            return {}
        d = self._parse_player(html)
        if not d:
            return {}
        vd = d.get("vod_data") or {}
        remarks = ""
        m = re.search(r'播放：<strong[^>]*>([^<]*)</strong>\s*次', html)
        if m:
            remarks = "%s 次播放" % m.group(1).strip()
        return {
            "name": vd.get("vod_name") or "",
            "category": vd.get("vod_class") or "",
            "url": d.get("url") or "",
            "play_from": d.get("from") or "正片",
            "remarks": remarks,
            "description": "",
        }

    def _fetch_play(self, play_id):
        play_id = (play_id or "").strip()
        if not play_id:
            return ""
        if play_id.startswith("http"):
            return play_id
        d = self._fetch_detail(play_id)
        return d.get("url") or ""

    def _parse_cards(self, html):
        cards = []
        for block in re.split(r'<div class="xv-video-card">', html)[1:]:
            m = re.search(r'href="/index\.php/vod/play/id/(\d+)/sid/1/nid/1\.html"', block)
            if not m:
                continue
            vid = m.group(1)
            tm = re.search(r'title="([^"]*)"', block)
            name = tm.group(1) if tm else vid
            im = re.search(r'data-original="([^"]*)"', block) or re.search(r'src="([^"]*)"', block)
            pic = im.group(1) if im else ""
            if pic and any(d in pic for d in AD_DOMAINS):
                continue
            hm = re.search(r'class="xv-hits"[^>]*>\s*<i[^>]*></i>\s*([^<]*)<', block)
            remarks = hm.group(1).strip() if hm else ""
            cards.append({"id": vid, "name": name, "pic": pic, "remarks": remarks})
        return cards

    def _parse_pagecount(self, html, pg):
        nums = [int(n) for n in re.findall(r'page/(\d+)', html) if n.isdigit()]
        if nums:
            return max(nums)
        m = re.search(r'共\s*(\d+)\s*页', html)
        if m:
            return int(m.group(1))
        return pg if pg > 1 else 1

    def _parse_player(self, html):
        i = html.find("player_aaaa=")
        if i < 0:
            return {}
        s = html[i + len("player_aaaa="):]
        depth = 0
        in_str = False
        esc = False
        end = -1
        for j, c in enumerate(s):
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        end = j + 1
                        break
        if end < 0:
            return {}
        try:
            return json.loads(s[:end])
        except Exception:
            return {}

    def _vod(self, item):
        vid = str(item.get("id") or "")
        pic = item.get("pic") or ""
        return {
            "vod_id": "%s|%s" % (vid, pic) if pic else vid,
            "vod_name": item.get("name") or vid,
            "vod_pic": pic,
            "vod_remarks": item.get("remarks") or "",
        }

    def _int(self, x, d=0):
        try:
            return int(x)
        except Exception:
            return d

    def _resp_dict(self, resp):
        if isinstance(resp, dict):
            return resp
        if isinstance(resp, str):
            return {"code": 200, "content": resp, "headers": {}, "error": None}
        if isinstance(resp, (bytes, bytearray)):
            return {"code": 200, "content": resp, "headers": {}, "error": None}
        return {"code": 0, "content": "", "headers": {}, "error": str(resp)}

    def _req(self, url, **kw):
        net = getattr(self, "net", None)
        if net is not None:
            try:
                opts = {"timeout": kw.get("timeout", 15000)}
                for k in ("params", "headers", "method", "postType", "data", "body", "buffer", "redirect", "callTimeout", "cookie"):
                    if k in kw and kw[k] is not None:
                        opts[k] = kw[k]
                resp = net.req(url, opts)
                return resp or {}
            except Exception:
                return {}
        return self._req_urllib(url, **kw)

    def _req_urllib(self, url, **kw):
        try:
            timeout = (kw.get("timeout") or 15000) / 1000.0
            data = None
            method = (kw.get("method") or "GET").upper()
            params = kw.get("params")
            if params:
                sep = "&" if "?" in url else "?"
                url = url + sep + "&".join("%s=%s" % (k, quote(str(v), safe="")) for k, v in params.items())
            headers = dict(kw.get("headers") or {})
            headers.setdefault("User-Agent", UA)
            headers.setdefault("Accept", "*/*")
            if method == "POST":
                body = kw.get("data") or kw.get("body") or {}
                if isinstance(body, dict):
                    data = "&".join("%s=%s" % (k, quote(str(v), safe="")) for k, v in body.items()).encode()
                elif isinstance(body, str):
                    data = body.encode()
                else:
                    data = body
                headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                enc = (resp.headers.get("Content-Encoding") or "").lower()
                if enc == "gzip":
                    raw = gzip.decompress(raw)
                elif enc == "deflate":
                    raw = zlib.decompress(raw)
                return {"code": resp.getcode() or 0, "content": raw.decode("utf-8", "replace"), "headers": dict(resp.headers), "error": None}
        except Exception as e:
            return {"code": 0, "content": "", "headers": {}, "error": str(e)}

    def _get_html(self, url, **kw):
        for _ in range(3):
            resp = self._req(url, **kw)
            if resp.get("error"):
                time.sleep(1)
                continue
            code = resp.get("code") or 0
            if not 200 <= code < 300:
                time.sleep(1)
                continue
            content = resp.get("content", "")
            if content:
                return content
            time.sleep(1)
        return None
