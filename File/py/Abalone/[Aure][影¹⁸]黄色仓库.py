# -*- coding: utf-8 -*-
# [黄色仓库¹⁸  更新于:2026-11-05 21:15]
import json
import re
import time
import threading
import gzip
import zlib
import base64
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

NAME = "黄色仓库"
ENTRY = "https://hsck.tv"
DEFAULT_HOST = "https://111.9967hsck.cc"
UA = "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36"
PAGE_SIZE = 40
CACHE_TTL = 60
DEBUG = False
VOD_ID_PREFIX = ""
STYLE = {"type": "rect", "ratio": 1.33}

CATS = [
    ("7", "日本有码"), ("8", "无码中文字幕"), ("9", "有码中文字幕"),
    ("10", "日本无码"), ("26", "骑兵破解"), ("15", "国产视频"),
    ("21", "欧美高清"), ("22", "动漫剧情"),
]


class Spider(BaseSpider):

    def __init__(self):
        self.host = DEFAULT_HOST
        self.name = NAME
        self._cache = {}
        self._cache_time = {}
        self._lock = threading.Lock()
        self._ak_cache = {}
        self._host_done = False
        self.options = {}

    def init(self, extend=""):
        try:
            super(Spider, self).init(extend)
        except Exception:
            pass
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
            return None
        site = (cfg.get("site") or cfg.get("url") or "").strip().rstrip("/")
        if site:
            self.host = site
            self._host_done = True
        self.options = cfg
        return None

    def _base(self):
        if self._host_done:
            return self.host
        self._host_done = True
        if self.host == DEFAULT_HOST:
            try:
                req = urllib.request.Request(ENTRY, headers={"User-Agent": UA, "Accept": "*/*"})
                with urllib.request.urlopen(req, timeout=12) as resp:
                    final = resp.geturl()
                m = re.match(r"(https?://[^/]+)", final)
                if m and m.group(1) != ENTRY:
                    self.host = m.group(1)
            except Exception:
                pass
        return self.host

    def getDependence(self):
        return []

    def destroy(self):
        with self._lock:
            self._cache.clear()
            self._cache_time.clear()
        self._ak_cache.clear()
        self.options = {}

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", str(url)))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {"msg": "不支持此操作"}

    def homeContent(self, filter):
        classes = self._classes()
        result = {"class": classes}
        if filter:
            result["filters"] = self._filters(classes)
        result["list"] = [self._vod(x) for x in self._home_items()]
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        tid = str(tid or "")
        if tid.startswith("actor/") or tid.startswith("director/"):
            name = unquote(tid.split("/", 1)[1])
            items = self._fetch_search(name, pg)
            return self._page([self._vod(x) for x in items], pg)
        if tid.startswith("tag/"):
            name = unquote(tid.replace("tag/", "", 1))
            items = self._fetch_search(name, pg)
            return self._page([self._vod(x) for x in items], pg)
        items = self._fetch_list(tid, pg)
        return self._page([self._vod(x) for x in items], pg)

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        responses = [self._detail(str(v)) for v in ids]
        merged = {k: v for k, v in (responses[0] or {}).items() if k != "list"}
        merged["list"] = [it for r in responses for it in (r.get("list") or [])]
        return merged

    def _detail(self, vid):
        vid = str(vid or "")
        url = self._base() + "/" + vid.lstrip("/") + ".html"
        html = self._get_html(url)
        if not html:
            return {"list": [], "msg": "未找到此影片"}
        aid = re.search(r"AID='([^']+)'", html)
        asid = re.search(r"ASID='([^']+)'", html)
        anid = re.search(r"ANID='([^']+)'", html)
        ak = re.search(r"AK='([^']+)'", html)
        if not (aid and asid and anid and ak):
            return {"list": [], "msg": "未找到此影片"}
        AID, ASID, ANID, AK = aid.group(1), asid.group(1), anid.group(1), ak.group(1)
        self._ak_cache[vid] = AK
        title = ""
        tm = re.search(r'<title>([^<]*)</title>', html)
        if tm:
            title = tm.group(1).split(" - ")[0].strip()
        if not title:
            for tm3 in re.findall(r'<h3 class="title">([^<]*)</h3>', html):
                if tm3.strip() and tm3.strip() != "目录":
                    title = tm3.strip()
                    break
        key = "%s-%s-%s" % (AID, ASID, ANID)
        card = re.search(r'href="/v5/' + re.escape(key) + r'\.html"(.{0,500}?)</a>', html, re.S)
        pic = ""
        dur = ""
        if card:
            blk = card.group(1)
            pm = re.search(r'data-original="([^"]*)"', blk)
            if pm:
                pic = pm.group(1)
            dm = re.search(r'pic-text[^>]*>([^<]*)<', blk)
            if dm:
                dur = dm.group(1).strip()
        if not pic:
            pm = re.search(r'data-original="(https://[^"]*vod\.jpg)"', html)
            if pm:
                pic = pm.group(1)
        if not dur:
            for dm in re.findall(r'pic-text[^>]*>([^<]*)<', html):
                if dm.strip() and dm.strip() != "精选":
                    dur = dm.strip()
                    break
        plays = ""
        fm = re.search(r'(\d+)</span>次播放', html)
        if fm:
            plays = fm.group(1)
        content_parts = []
        if dur:
            content_parts.append("时长：" + dur)
        if plays:
            content_parts.append("播放：" + plays + " 次")
        tm_ = re.search(r'时间：([^<]+)<', html)
        if tm_:
            content_parts.append("时间：" + tm_.group(1).strip())
        content = "\n".join(content_parts)
        if not title:
            title = vid
        vod = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "type_name": "",
            "vod_year": "",
            "vod_area": "",
            "vod_remarks": dur,
            "vod_director": "",
            "vod_actor": "",
            "vod_content": content,
            "vod_play_from": "正片",
            "vod_play_url": "正片$" + self._play_token(AID, ASID, ANID),
        }
        return {"list": [vod]}

    def _play_token(self, aid, sid, nid):
        return "v5/%s-%s-%s" % (aid, sid, nid)

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        items = self._fetch_search(str(key or "").strip(), pg)
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": 9999 if items else pg,
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def playerContent(self, flag, id, vipFlags):
        url = self._fetch_play(str(id or ""))
        if not url:
            return {"parse": 0, "msg": "无法获取播放地址"}
        return {"parse": 0, "jx": 0, "url": url, "header": self._string_map({"User-Agent": UA})}

    def liveContent(self, url):
        return "[]"

    def _fetch_list(self, tid, pg):
        if pg <= 1:
            path = "/vodtype/%s.html" % tid
        else:
            path = "/vodtype/%s-%s.html" % (tid, pg)
        html = self._get_html(self._base() + path)
        return self._parse_cards(html or "")

    def _fetch_search(self, key, pg):
        kw = quote(str(key).strip(), safe="")
        if pg <= 1:
            path = "/vodsearch/%s-------------.html" % kw
        else:
            path = "/vodsearch/%s----------%s---.html" % (kw, pg)
        html = self._get_html(self._base() + path)
        return self._parse_cards(html or "")

    def _fetch_play(self, vid):
        vid = str(vid or "")
        m = re.match(r"(?:v5/)?(\d+)-(\d+)-(\d+)", vid)
        if not m:
            return ""
        aid, sid, nid = m.group(1), m.group(2), m.group(3)
        key = "v5/%s-%s-%s" % (aid, sid, nid)
        ak = self._ak_cache.get(key)
        if not ak:
            html = self._get_html(self._base() + "/v5/%s-%s-%s.html" % (aid, sid, nid))
            if not html:
                return ""
            am = re.search(r"AK='([^']+)'", html)
            if not am:
                return ""
            ak = am.group(1)
            self._ak_cache[key] = ak
        body = {
            "id": aid, "sid": sid, "nid": nid, "tk": ak,
            "g": 1, "x": 400, "y": 300, "dt": 300,
            "sw": 1080, "sh": 1920, "tz": -480,
            "t": int(time.time() * 1000),
        }
        hdrs = {
            "User-Agent": UA,
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        }
        resp = self._req(self._base() + "/static/count.php", method="POST", postType="form", data=body, headers=hdrs)
        if resp.get("error"):
            return ""
        code = resp.get("code") or 0
        if not 200 <= code < 300:
            return ""
        text = resp.get("content", "")
        try:
            j = json.loads(text)
        except Exception:
            return ""
        if not (j.get("ok") and j.get("u")):
            return ""
        try:
            return base64.b64decode(j["u"]).decode("utf-8", "ignore")
        except Exception:
            return ""

    def _parse_cards(self, html):
        items = []
        for blk in re.split(r"<li[^>]*>", html):
            m = re.search(r'href="(/v5/[^"]+)"', blk)
            if not m:
                continue
            vid = m.group(1)
            vid = re.sub(r"\.html$", "", vid.strip().lstrip("/"))
            pic = ""
            pm = re.search(r'data-original="([^"]*)"', blk)
            if pm:
                pic = pm.group(1)
            title = ""
            tm = re.search(r'<h4[^>]*class="[^"]*title[^"]*"[^>]*>\s*<a[^>]*>([^<]*)</a>', blk)
            if tm:
                title = tm.group(1).strip()
            if not title:
                tm2 = re.search(r'<a[^>]*href="/v5/[^"]*"[^>]*title="([^"]*)"', blk)
                if tm2:
                    title = tm2.group(1).strip()
            if not title:
                continue
            dur = ""
            dm = re.search(r'pic-text[^>]*>([^<]*)<', blk)
            if dm:
                dur = dm.group(1).strip()
            items.append({"id": vid, "name": title, "pic": pic, "remarks": dur})
        return items

    def _home_items(self):
        html = self._get_html(self._base() + "/")
        items = self._parse_cards(html or "")
        return items[:PAGE_SIZE]

    def _classes(self):
        arr = [{"type_id": tid, "type_name": nm} for tid, nm in CATS]
        return arr

    def _filters(self, classes):
        return {}

    def _vod(self, item):
        item = item or {}
        return {
            "vod_id": item.get("id") or "",
            "vod_name": item.get("name") or "",
            "vod_pic": item.get("pic") or "",
            "vod_remarks": item.get("remarks") or "",
        }

    def _page(self, items, pg):
        try:
            page = max(1, int(pg))
        except (TypeError, ValueError):
            page = 1
        has_more = len(items) >= PAGE_SIZE
        return {
            "list": items,
            "page": page,
            "pagecount": 9999 if has_more else page,
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def _req(self, url, **kw):
        net = getattr(self, "net", None)
        if net is not None:
            try:
                opts = {"timeout": kw.get("timeout", 15000)}
                for k in ("params", "headers", "method", "postType", "data", "body", "buffer", "redirect", "cookie"):
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
        resp = self._req(url, **kw)
        if resp.get("error"):
            return None
        code = resp.get("code") or 0
        if not 200 <= code < 300:
            return None
        return resp.get("content", "")

    def _int(self, x, d=0):
        try:
            return int(x)
        except Exception:
            return d

    @staticmethod
    def _string_map(value, name="headers"):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            return {}
        return {str(k): str(v) for k, v in value.items() if v is not None}
