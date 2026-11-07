# -*- coding: utf-8 -*-
# [TOPTV¹⁸  更新于:2026-11-05 22:05]
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

NAME = "TOPTV"
HOSTS = ["https://toptv15.cyou"]
UA = "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 20
CACHE_TTL = 60
DEBUG = False


class Spider(BaseSpider):

    def __init__(self):
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self._cache = {}
        self._cache_time = {}
        self._good_host = None
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
        extend = extend or {}
        if tid.startswith("actor/") or tid.startswith("director/") or tid.startswith("tag/"):
            name = unquote(tid.split("/", 1)[1])
            items, pagecount = self._search_data(name, pg)
            return {
                "list": [self._vod(x) for x in items],
                "page": pg,
                "pagecount": pagecount or (pg if len(items) < PAGE_SIZE else 9999),
                "limit": PAGE_SIZE,
                "total": 999999,
            }
        html = self._get_html(self._cat_url(tid, pg))
        if not html:
            return {"list": [], "page": pg, "pagecount": pg, "limit": PAGE_SIZE, "total": 0}
        items = self._parse_cards(html)
        pagecount = self._pagecount(html, "type")
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pagecount or (pg if len(items) < PAGE_SIZE else 9999),
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        responses = [self._detail(str(video_id)) for video_id in ids]
        merged = {k: v for k, v in (responses[0] or {}).items() if k != "list"}
        merged["list"] = [item for response in responses for item in (response.get("list") or [])]
        return merged

    def _detail(self, vid):
        data = self._fetch_detail(vid)
        if not data:
            return {"list": [], "msg": "未找到此影片"}
        url = data.get("url") or ""
        play_url = f"正片${url}"
        play_from = "正片"
        vod = {
            "vod_id": vid,
            "vod_name": data.get("name") or vid,
            "vod_pic": data.get("pic") or "",
            "type_name": data.get("category") or "",
            "vod_year": "",
            "vod_area": "",
            "vod_remarks": data.get("remarks") or "",
            "vod_director": self._clickable("director", data.get("director") or ""),
            "vod_actor": "、".join(self._clickable("actor", a) for a in data.get("actors") or []),
            "vod_content": data.get("description") or "",
            "vod_play_from": play_from,
            "vod_play_url": play_url,
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        items, pagecount = self._search_data(str(key or "").strip(), pg)
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pagecount or (pg if len(items) < PAGE_SIZE else 9999),
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def playerContent(self, flag, id, vipFlags):
        url = str(id or "")
        if not url.startswith("http"):
            return {"parse": 0, "msg": "无法获取播放地址"}
        return {
            "parse": 0,
            "jx": 0,
            "url": url,
            "header": self._string_map({"User-Agent": UA}),
        }

    def liveContent(self, url):
        return "[]"


    def _classes(self):
        hit = self._cache.get("__cls")
        if hit and time.time() - self._cache_time.get("__cls", 0) < CACHE_TTL:
            return hit[0]
        arr = []
        html = self._get_html(self.host + "/")
        if html:
            for m in re.finditer(r'href="(/index\.php/vod/type/id/(\d+)\.html)"\s+title="([^"]+)"', html):
                tid, nm = m.group(2), m.group(3)
                if tid and nm:
                    arr.append({"type_id": tid, "type_name": nm})
        if not arr:
            arr = [{"type_id": "1", "type_name": "国产自拍"}]
        with self._lock:
            self._cache["__cls"] = (arr, time.time())
        return arr

    def _filters(self, classes):
        return {c["type_id"]: [] for c in classes}

    def _home_items(self):
        html = self._get_html(self.host + "/")
        if not html:
            return []
        return self._parse_cards(html)

    def _cat_url(self, tid, pg):
        if pg <= 1:
            return self.host + f"/index.php/vod/type/id/{tid}.html"
        return self.host + f"/index.php/vod/type/id/{tid}/page/{pg}.html"

    def _search_url(self, key, pg):
        k = quote(key, safe="")
        if pg <= 1:
            return self.host + f"/index.php/vod/search.html?wd={k}"
        return self.host + f"/index.php/vod/search/page/{pg}/wd/{k}.html"

    def _search_data(self, key, pg):
        html = self._get_html(self._search_url(key, pg))
        if not html:
            return [], pg
        items = self._parse_cards(html)
        pagecount = self._pagecount(html, "search")
        return items, pagecount

    def _parse_cards(self, html):
        items = []
        for m in re.finditer(r'<a[^>]*href="/index\.php/vod/detail/id/(\d+)\.html"[^>]*>(.*?)</a>\s*</div>', html, re.S):
            vid = m.group(1)
            block = m.group(2)
            pic = ""
            mm = re.search(r'data-original="([^"]+)"', block)
            if mm:
                pic = mm.group(1)
            else:
                mm = re.search(r'<img[^>]+src="([^"]+)"', block)
                if mm:
                    pic = mm.group(1)
            name = ""
            mm = re.search(r'<p class="vod-name[^"]*">([^<]*)</p>', block)
            if mm:
                name = re.sub(r"\s+", " ", mm.group(1)).strip()
            if not name:
                mm = re.search(r'alt="([^"]*)"', block)
                if mm:
                    name = mm.group(1).strip()
            rem = ""
            mm = re.search(r'<p class="vod-class[^"]*">([^<]*)</p>', block)
            if mm:
                rem = re.sub(r"\s+", " ", mm.group(1)).strip()
            if vid:
                items.append({"id": vid, "name": name, "pic": pic, "remarks": rem})
        return items

    def _pagecount(self, html, kind):
        if not html:
            return 0
        nums = [int(x) for x in re.findall(r"page/(\d+)", html)]
        if nums:
            return max(nums)
        return 0

    def _fetch_detail(self, vid):
        vid = str(vid)
        html = self._get_html(self.host + f"/index.php/vod/detail/id/{vid}.html")
        if not html:
            return None
        name = ""
        m = re.search(r"<h1[^>]*>\s*资源名称：\s*([^<]+)</h1>", html)
        if m:
            name = re.sub(r"\s+", " ", m.group(1)).strip()
        pic = ""
        m = re.search(r'<a[^>]*href="/play/\d+\.html"[^>]*>\s*<img[^>]+src="([^"]+)"', html)
        if m:
            pic = m.group(1)
        if not pic:
            m = re.search(r'<img[^>]+src="(https://img\.[^"]+)"', html)
            if m:
                pic = m.group(1)
        url = ""
        actor = ""
        director = ""
        category = ""
        vod_name = ""
        play_html = self._get_html(self.host + f"/index.php/vod/play/id/{vid}/sid/1/nid/1.html")
        if play_html:
            m = re.search(r"player_aaaa=(\{.*?\})\s*</script>", play_html, re.S)
            if m:
                try:
                    pd = json.loads(m.group(1))
                    url = (pd.get("url") or "").strip()
                    vd = pd.get("vod_data") or {}
                    vod_name = vd.get("vod_name") or ""
                    actor = vd.get("vod_actor") or ""
                    director = vd.get("vod_director") or ""
                    category = vd.get("vod_class") or ""
                except Exception:
                    pass
        if not vod_name:
            vod_name = name
        actors = []
        if actor:
            for a in re.split(r"[、,，/\s]+", actor):
                a = a.strip()
                if a:
                    actors.append(a)
        return {
            "name": vod_name or name or vid,
            "pic": pic,
            "category": category,
            "actors": actors,
            "director": director,
            "remarks": "",
            "description": "",
            "url": url,
        }

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("id") or item.get("vod_id") or "")
        return {
            "vod_id": vid,
            "vod_name": item.get("name") or item.get("title") or vid,
            "vod_pic": item.get("pic") or "",
            "vod_remarks": item.get("remarks") or "",
        }

    def _clickable(self, kind, name):
        if not name:
            return ""
        ident = f"{kind}/{quote(name, safe='')}"
        payload = json.dumps({"id": ident, "name": name, "type_flag": "0"}, ensure_ascii=False, separators=(",", ":"))
        return f"[a=cr:{payload}/]{name}[/a]"

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
                code = resp.getcode() or 0
                return {"code": code, "content": raw.decode("utf-8", "replace"), "headers": dict(resp.headers), "error": None}
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
