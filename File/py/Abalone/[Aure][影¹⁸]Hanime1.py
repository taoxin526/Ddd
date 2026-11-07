# -*- coding: utf-8 -*-
# [Hanime1¹⁸  更新于:2026-11-05 13:45]
import json
import re
import time
import threading
import gzip
import zlib
import ssl
import urllib.request
from urllib.parse import quote, unquote
from lxml import etree

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        def proxy(self, params):
            return [404, "text/plain", ""]
        def localProxy(self, params):
            return [404, "text/plain", ""]

NAME = "Hanime1"
HOSTS = ["https://www.hanime999.cc"]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
AUTH_COOKIE = "x-index-auth=authed"
PAGE_SIZE = 90
CACHE_TTL = 30

CATS = [
    ("裏番", "里番"), ("泡麵番", "泡面番"), ("Motion Anime", "Motion Anime"),
    ("3DCG", "3DCG"), ("2.5D", "2.5D"), ("AI生成", "AI生成"),
    ("MMD", "MMD"), ("Cosplay", "Cosplay"), ("新番預告", "新番预告"), ("2D動畫", "2D动画"),
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

    def getDependence(self):
        return []

    def destroy(self):
        with self._lock:
            self._cache.clear()
            self._cache_time.clear()

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", str(url)))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {"msg": "不支持此操作"}

    def homeContent(self, filter):
        classes = self._classes()
        result = {"class": classes}
        result["list"] = [self._vod(x) for x in self._home_items()]
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        tid = str(tid or "")
        if tid.startswith("tag/"):
            kw = unquote(tid.replace("tag/", "", 1))
            return self._search_page(kw, pg)
        if tid.startswith("actor/"):
            kw = unquote(tid.replace("actor/", "", 1))
            return self._search_page(kw, pg)
        url = self.host + "/search?genre=" + quote(tid, safe="") + ("&page=" + str(pg) if pg > 1 else "")
        html = self._get_html(url)
        items = self._parse_cards(html) if html else []
        return self._page([self._vod(x) for x in items], pg, self._has_more(html))

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        out = []
        for v in ids:
            out.extend((self._detail(str(v)) or {}).get("list") or [])
        return {"list": out}

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        return self._search_page(str(key or "").strip(), pg)

    def playerContent(self, flag, id, vipFlags):
        play_id = str(id or "")
        vid = self._vid_from_play(play_id)
        quality = self._quality_from_play(play_id)
        url = self._fetch_play(vid, quality)
        if not url:
            url = play_id
        return {
            "parse": 0,
            "playUrl": "",
            "url": url,
            "header": {"User-Agent": UA, "Referer": self.host + "/", "Cookie": AUTH_COOKIE},
        }

    def _vid_from_play(self, play_id):
        if not play_id:
            return ""
        m = re.search(r"/(\d+)-\d+p\.mp4", play_id)
        if m:
            return m.group(1)
        m = re.search(r"/watch\?v=(\d+)", play_id)
        if m:
            return m.group(1)
        m = re.search(r"/(\d+)", play_id)
        if m:
            return m.group(1)
        return play_id

    def _quality_from_play(self, play_id):
        m = re.search(r"-(\d+)p\.mp4", play_id)
        if m:
            return m.group(1)
        return ""

    def _fetch_play(self, vid, quality):
        if not vid:
            return ""
        html = self._get_html(self.host + "/watch?v=" + quote(str(vid), safe=""))
        if not html:
            return ""
        doc = self._doc(html)
        if doc is None:
            return ""
        srcs = doc.xpath('//source[contains(@src, ".mp4")]/@src')
        if not srcs:
            return ""
        if quality:
            for s in srcs:
                if ("-" + quality + "p.mp4") in s:
                    return s
        best = None
        best_w = -1
        for s in srcs:
            m = re.search(r"-(\d+)p\.mp4", s)
            w = self._int(m.group(1), 0) if m else 0
            if w > best_w:
                best_w = w
                best = s
        return best or srcs[0]

    def liveContent(self, url):
        return "[]"

    def _classes(self):
        return [{"type_id": cid, "type_name": nm} for cid, nm in CATS]

    def _home_items(self):
        html = self._get_html(self.host + "/")
        return self._parse_cards(html) if html else []

    def _search_page(self, kw, pg):
        url = self.host + "/search?query=" + quote(str(kw), safe="") + ("&page=" + str(pg) if pg > 1 else "")
        html = self._get_html(url)
        items = self._parse_cards(html) if html else []
        return self._page([self._vod(x) for x in items], pg, self._has_more(html))

    def _has_more(self, html):
        if not html:
            return False
        return 'rel="next"' in html

    def _detail(self, vid):
        html = self._get_html(self.host + "/watch?v=" + quote(str(vid), safe=""))
        if not html:
            return {"list": [], "msg": "未找到此影片"}
        doc = self._doc(html)
        if doc is None:
            return {"list": [], "msg": "页面解析失败"}
        meta = {}
        for key in ("title", "description", "keywords"):
            v = doc.xpath('//meta[@name="%s"]/@content' % key)
            if v:
                meta[key] = v[0]
        ogtitle = doc.xpath('//meta[@property="og:title"]/@content')
        ogimage = doc.xpath('//meta[@property="og:image"]/@content')
        raw_title = (ogtitle[0] if ogtitle else meta.get("title") or "")
        name = re.split(r"\s*-\s*(?:H動漫|hanime|Hanime1)", raw_title)[0].strip() if raw_title else vid
        pic = ogimage[0] if ogimage else ""
        desc = meta.get("description") or ""
        brand = self._field(desc, r"Brand\s*/\s*ブランド:\s*([^\r\n]+)")
        release = self._field(desc, r"Release\s*/\s*販売日:\s*([^\r\n]+)")
        filesize = self._field(desc, r"File size\s*/\s*ファイル容量:\s*([^\r\n]+)")
        year = ""
        m = re.search(r"(\d{4})/(\d{2})/(\d{2})", release or "")
        if m:
            year = m.group(1)
        kw = meta.get("keywords") or ""
        tags = []
        parts = [t.strip() for t in kw.split(",") if t.strip()]
        if len(parts) > 1:
            tags = parts[1:]
        else:
            tags = parts
        srcs = doc.xpath('//source[contains(@src, ".mp4")]/@src')
        play = self._build_play(srcs)
        remarks = ""
        if len(parts) > 0:
            remarks = parts[0].upper()
        content_lines = []
        if brand or release or filesize:
            if brand:
                content_lines.append("品牌: " + brand)
            if release:
                content_lines.append("发行日: " + release)
            if filesize:
                content_lines.append("文件大小: " + filesize)
        elif desc:
            plot = re.sub(r"\s+", " ", desc).strip()
            if plot:
                content_lines.append(plot)
        if tags:
            content_lines.append("标签: " + "、".join(self._clickable("tag", t) for t in tags))
        vod = {
            "vod_id": str(vid),
            "vod_name": name or vid,
            "vod_pic": pic,
            "type_name": "",
            "vod_year": year,
            "vod_area": "",
            "vod_remarks": remarks,
            "vod_director": "",
            "vod_actor": (self._clickable("actor", brand) if brand else ""),
            "vod_content": "\n".join(content_lines),
            "vod_play_from": "正片",
            "vod_play_url": play,
        }
        return {"list": [vod]}

    def _build_play(self, srcs):
        if not srcs:
            return ""
        seen = set()
        items = []
        for s in srcs:
            if s in seen:
                continue
            seen.add(s)
            m = re.search(r"-(\d+)p\.mp4", s)
            res = (m.group(1) + "P") if m else "默认"
            items.append((self._int(m.group(1), 0) if m else 0, res, s))
        items.sort(key=lambda x: x[0], reverse=True)
        return "#".join("%s$%s" % (res, s) for _, res, s in items)

    def _fetch_play(self, vid, quality):
        if not vid:
            return ""
        html = self._get_html(self.host + "/watch?v=" + quote(str(vid), safe=""))
        if not html:
            return ""
        doc = self._doc(html)
        if doc is None:
            return ""
        srcs = doc.xpath('//source[contains(@src, ".mp4")]/@src')
        if not srcs:
            return ""
        if quality:
            for s in srcs:
                if ("-" + quality + "p.mp4") in s:
                    return s
        best = None
        best_w = -1
        for s in srcs:
            m = re.search(r"-(\d+)p\.mp4", s)
            w = self._int(m.group(1), 0) if m else 0
            if w > best_w:
                best_w = w
                best = s
        return best or srcs[0]

    def _field(self, text, pattern):
        m = re.search(pattern, text)
        return m.group(1).strip() if m else ""

    def _parse_cards(self, html):
        doc = self._doc(html)
        if doc is None:
            return []
        out = []
        seen = set()
        for a in doc.xpath('//a[contains(@href, "/watch?v=")]'):
            href = a.get("href") or ""
            m = re.search(r"/watch\?v=(\d+)", href)
            if not m:
                continue
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            imgs = a.xpath('.//img/@src')
            pic = imgs[0] if imgs else ""
            name = ""
            t = a.xpath('.//div[contains(@class, "home-rows-videos-title")]')
            if not t:
                t = a.xpath('.//div[contains(@class, "title")]')
            if t:
                name = "".join(t[0].itertext()).strip()
            if not name:
                title_attr = a.xpath('.//*[contains(@class, "video-item-container")]/@title')
                if title_attr:
                    name = title_attr[0].strip()
            remarks = ""
            dur = a.xpath('.//div[contains(@class, "duration")]')
            if dur:
                remarks = "".join(dur[0].itertext()).strip()
            views = ""
            for si in a.xpath('.//div[contains(@class, "stat-item")]'):
                s = "".join(si.itertext()).strip()
                if re.search(r"\d+(?:\.\d+)?万?次", s):
                    views = s
                    break
            if views:
                remarks = (remarks + " | " + views) if remarks else views
            out.append({"id": vid, "name": name or vid, "pic": pic, "remarks": remarks})
        return out

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("id") or "")
        return {
            "vod_id": vid,
            "vod_name": item.get("name") or vid,
            "vod_pic": item.get("pic") or "",
            "vod_remarks": item.get("remarks") or "",
        }

    def _clickable(self, kind, name):
        if not name:
            return ""
        ident = "%s/%s" % (kind, quote(name, safe=""))
        payload = json.dumps({"id": ident, "name": name, "type_flag": "0"}, ensure_ascii=False, separators=(",", ":"))
        return "[a=cr:%s/]%s[/a]" % (payload, name)

    def _doc(self, html):
        try:
            return etree.HTML(html)
        except Exception:
            return None

    def _page(self, items, pg, has_more=None):
        try:
            page = max(1, int(pg))
        except (TypeError, ValueError):
            page = 1
        if has_more is None:
            has_more = len(items) >= PAGE_SIZE
        return {
            "list": items,
            "page": page,
            "pagecount": 9999 if has_more else page,
            "limit": PAGE_SIZE,
            "total": len(items),
        }

    def _int(self, x, d=0):
        try:
            return int(x)
        except Exception:
            return d

    def _headers(self):
        return {"User-Agent": UA, "Cookie": AUTH_COOKIE, "Referer": self.host + "/"}

    def _net_opts(self, opts):
        net = getattr(self, "net", None)
        if net is not None and not hasattr(net, "_native"):
            return json.dumps(opts, ensure_ascii=False)
        return opts

    def _resp_dict(self, resp):
        if isinstance(resp, dict):
            return resp
        if isinstance(resp, (bytes, bytearray)):
            return {"code": 200, "content": resp, "headers": {}, "error": None}
        if isinstance(resp, str):
            return {"code": 200, "content": resp, "headers": {}, "error": None}
        return {"code": 0, "content": "", "headers": {}, "error": str(resp)}

    def _req(self, url, **kw):
        net = getattr(self, "net", None)
        if net is not None:
            try:
                opts = {"timeout": kw.get("timeout", 15000)}
                for k in ("params", "headers", "method", "postType", "data", "body", "buffer", "redirect", "cookie"):
                    if k in kw and kw[k] is not None:
                        opts[k] = kw[k]
                resp = net.req(url, self._net_opts(opts))
                return self._resp_dict(resp)
            except Exception:
                return {}
        return self._req_urllib(url, **kw)

    def _req_urllib(self, url, **kw):
        try:
            timeout = (kw.get("timeout") or 15000) / 1000.0
            headers = dict(kw.get("headers") or {})
            headers.setdefault("User-Agent", UA)
            headers.setdefault("Accept", "*/*")
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                enc = (resp.headers.get("Content-Encoding") or "").lower()
                if enc == "gzip":
                    raw = gzip.decompress(raw)
                elif enc == "deflate":
                    raw = zlib.decompress(raw)
                return {"code": resp.getcode() or 0, "content": raw.decode("utf-8", "replace"),
                        "headers": dict(resp.headers), "error": None}
        except Exception as e:
            return {"code": 0, "content": "", "headers": {}, "error": str(e)}

    def _get_html(self, url, **kw):
        kw.setdefault("headers", self._headers())
        resp = self._req(url, **kw)
        if resp.get("error"):
            return None
        code = resp.get("code") or 0
        if not 200 <= code < 300:
            return None
        return resp.get("content", "")
