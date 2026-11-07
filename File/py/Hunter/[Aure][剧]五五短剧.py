# -*- coding: utf-8 -*-
# [五五短剧  更新于:2026-11-03 09:40]

import json
import re
import time
import threading
import gzip
import zlib
import urllib.request
import http.cookiejar
from urllib.parse import quote, unquote

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        def proxy(self, params):
            return [404, "text/plain", ""]
        def localProxy(self, params):
            return [404, "text/plain", ""]

NAME = "五五短剧"
HOSTS = ["https://www.duanju55.com"]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
PAGE_SIZE = 24
CACHE_TTL = 60
DEBUG = False
VOD_ID_PREFIX = ""
CHALLENGE = "window.location.href"


class Spider(BaseSpider):

    def __init__(self):
        super().__init__()
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self._cache = {}
        self._cache_time = {}
        self._lock = threading.Lock()
        self.options = {}
        self._cls = None
        self._cls_t = 0
        self._cj = http.cookiejar.CookieJar()
        self._opener = None

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

    def getDependence(self):
        return []

    def destroy(self):
        with self._lock:
            self._cache.clear()
            self._cache_time.clear()
        self.options = {}

    def homeContent(self, filter):
        classes = self._classes()
        result = {"class": classes}
        if filter:
            result["filters"] = {}
        result["list"] = [self._vod(x) for x in self._home_items()]
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        tid = str(tid or "")
        if tid.startswith("tag/"):
            cls = unquote(tid.split("/", 1)[1])
            items = self._fetch_list(cls, pg, extend or {})
            return {
                "list": [self._vod(x) for x in items],
                "page": pg,
                "pagecount": 9999 if items else pg,
                "limit": PAGE_SIZE,
                "total": 999999,
            }
        if tid.startswith("actor/") or tid.startswith("director/"):
            name = unquote(tid.split("/", 1)[1])
            items, pagecount = self._fetch_search(name, pg)
            return {
                "list": [self._vod(x) for x in items],
                "page": pg,
                "pagecount": pagecount,
                "limit": PAGE_SIZE,
                "total": 999999,
            }
        items = self._fetch_list(tid, pg, extend or {})
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": 9999 if items else pg,
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
        vid = vid.replace("vod/", "").strip()
        data = self._fetch_detail(vid)
        if not data:
            return {"list": [], "msg": "未找到此影片"}
        eps = data.get("episodes") or []
        if eps:
            lines = []
            for i, ep in enumerate(eps, 1):
                title = self._safe_label(ep.get("name") or f"第{i}集")
                url = ep.get("url") or ""
                if url:
                    lines.append(f"{title}${url}")
            play_url = "#".join(lines)
            play_from = data.get("source_name") or data.get("play_from") or "正片"
        else:
            url = data.get("url") or vid
            play_url = f"正片${url}"
            play_from = data.get("source_name") or data.get("play_from") or "正片"
        vod = {
            "vod_id": self._vod_id(vid),
            "vod_name": data.get("name") or vid,
            "vod_pic": self._pic(data),
            "type_name": data.get("category") or "",
            "vod_year": str(data.get("year") or ""),
            "vod_area": data.get("area") or "",
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
        items, pagecount = self._fetch_search(str(key or "").strip(), pg)
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pagecount,
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def playerContent(self, flag, id, vipFlags):
        url = self._fetch_play(str(id or ""))
        if not url:
            return {"parse": 0, "msg": "无法获取播放地址"}
        return {
            "parse": 0,
            "jx": 0,
            "url": url,
            "header": self._string_map({
                "User-Agent": UA,
                "Referer": self.host + "/",
            }),
        }

    def liveContent(self, url):
        return "[]"

    def action(self, action):
        return {"msg": "不支持此操作"}

    def getProxyUrl(self, params=None, local=True):
        try:
            from com.github.catvod import Proxy
            u = Proxy.getUrl(local)
            key = getattr(self, "siteKey", "") or ""
            return u + "?do=py" + ("&siteKey=%s" % key if key else "")
        except Exception:
            return ""

    def proxyUrl(self, params=None, local=True):
        try:
            from com.github.catvod import Proxy
            return Proxy.getUrl(local)
        except Exception:
            return ""

    def _play_proxy_url(self, url):
        return self._proxy_url_for("m3u8", url)

    def proxy(self, params):
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                return [404, "text/plain", ""]
        if not isinstance(params, dict):
            return [404, "text/plain", ""]
        url = params.get("url") or ""
        if not url:
            return [404, "text/plain", ""]
        ptype = params.get("type") or ""
        referer = "https://tyyszywjx.com/?url=" + quote(url, safe="")
        headers = {
            "User-Agent": UA,
            "Referer": referer,
            "Origin": "https://tyyszywjx.com",
        }
        low = url.lower()
        is_m3u8 = low.endswith(".m3u8") or ".m3u8" in low or ptype in ("m3u8", "variant")
        if is_m3u8:
            text = self._http1_m3u8(url, headers)
            if text is None:
                return [404, "text/plain", ""]
            text = self._rewrite_m3u8(text, url)
            return [200, "application/vnd.apple.mpegurl", text, self._string_map(headers)]
        body = self._http1_bytes(url, headers)
        if body is None:
            return [404, "application/octet-stream", ""]
        if low.endswith((".ts", ".mpeg", ".mp4", ".jpeg", ".jpg", ".m4s")):
            mime = "video/mp2t"
        else:
            mime = "application/octet-stream"
        return [200, mime, self._bytes_stream(body), self._string_map(headers)]

    localProxy = proxy

    def _proxy_url_for(self, typ, url):
        try:
            base = self.getProxyUrl()
            if base:
                sep = "&" if "?" in base else "?"
                sk = getattr(self, "siteKey", "") or ""
                extra = ("&siteKey=%s" % sk) if (sk and "siteKey=" not in base) else ""
                return "%s%stype=%s&url=%s%s" % (base, sep, typ, quote(url, safe=""), extra)
        except Exception:
            pass
        try:
            return self.proxyUrl({"type": typ, "url": url})
        except Exception:
            return url

    def _rewrite_m3u8(self, text, base_url):
        out = []
        for line in text.split("\n"):
            s = line.strip()
            if not s:
                out.append(line)
                continue
            if s.startswith("#"):
                m = re.search(r'URI="([^"]+)"', s)
                if m:
                    u = self._resolve_url(base_url, m.group(1))
                    typ = "key" if "KEY" in s else "map"
                    pu = self._proxy_url_for(typ, u)
                    s = s.replace('URI="%s"' % m.group(1), 'URI="%s"' % quote(pu, safe=""))
                out.append(s)
                continue
            u = self._resolve_url(base_url, s)
            typ = "variant" if ".m3u8" in u.lower() else "segment"
            out.append(self._proxy_url_for(typ, u))
        return "\n".join(out)

    def _resolve_url(self, base, ref):
        try:
            from urllib.parse import urljoin
            return urljoin(base, ref)
        except Exception:
            return ref if ref.startswith("http") else base

    def _http1_m3u8(self, url, headers):
        attempts = (
            headers,
            {"User-Agent": UA, "Origin": "https://tyyszywjx.com"},
            {"User-Agent": UA, "Referer": "https://tyyszywjx.com/"},
            {"User-Agent": UA},
        )
        for h in attempts:
            raw = self._http1_bytes(url, h)
            if raw is None:
                continue
            text = raw.decode("utf-8", "replace")
            if "EXTM3U" in text or "EXT-X-" in text:
                return text
        return None

    def _http1_text(self, url, headers):
        try:
            raw = self._http1_bytes(url, headers)
            return raw.decode("utf-8", "replace") if raw is not None else ""
        except Exception:
            return ""

    def _http1_bytes(self, url, headers):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read()
                enc = (resp.headers.get("Content-Encoding") or "").lower()
                if enc == "gzip":
                    raw = gzip.decompress(raw)
                elif enc == "deflate":
                    raw = zlib.decompress(raw)
                return raw
        except urllib.error.HTTPError as e:
            try:
                return e.read()
            except Exception:
                return None
        except Exception:
            return None

    def _bytes_stream(self, data):
        net = getattr(self, "net", None)
        if net is not None and hasattr(net, "stream"):
            try:
                def gen():
                    yield data
                return net.stream(gen())["stream"]
            except Exception:
                pass
        import io
        return io.BytesIO(data if isinstance(data, bytes) else str(data).encode("utf-8", "ignore"))


    def _classes(self):
        now = time.time()
        if self._cls and now - self._cls_t < 3600:
            return self._cls
        arr = []
        html = self._get_html(self.host + "/index.php/vod/show/id/1.html")
        if html:
            for m in re.finditer(r'<a[^>]+class="pcBrowse_twoVoItem[^"]*"[^>]+href="([^"]+)"[^>]*>([^<]+)</a>', html):
                name = m.group(2).strip()
                if name == "全部":
                    arr.append({"type_id": "all", "type_name": "短剧"})
                else:
                    arr.append({"type_id": name, "type_name": name})
            if not arr:
                for m in re.finditer(r'<div[^>]+class="adm-tabs-tab[^"]*"[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>', html):
                    name = m.group(2).strip()
                    if name == "全部":
                        arr.append({"type_id": "all", "type_name": "短剧"})
                    else:
                        arr.append({"type_id": name, "type_name": name})
        if not arr:
            arr = [{"type_id": "all", "type_name": "短剧"}]
        self._cls = arr
        self._cls_t = now
        return arr

    def _home_items(self):
        html = self._get_html(self.host + "/")
        if not html:
            return []
        return self._parse_cards(html, "SecondList_secondListItem", "FeaturedList_featuredItem")

    def _fetch_list(self, tid, pg, extend):
        if tid == "all" or not tid:
            url = f"{self.host}/index.php/vod/show/id/1/page/{pg}.html"
        else:
            url = f"{self.host}/index.php/vod/show/class/{quote(tid, safe='')}/id/1/page/{pg}.html"
        html = self._get_html(url)
        if not html:
            return []
        return self._parse_cards(html, "BrowseList_itemBox", "BrowseList_listItem")

    def _fetch_search(self, keyword, pg):
        if not keyword:
            return [], 1
        kw = quote(str(keyword).strip(), safe="")
        pg = self._int(pg, 1)
        if pg <= 1:
            url = f"{self.host}/index.php/vod/search/wd/{kw}.html"
        else:
            url = f"{self.host}/index.php/vod/search/page/{pg}/wd/{kw}.html"
        html = self._get_html(url)
        if not html:
            return [], 1
        items = self._parse_cards(html, "TagBookList_tagItem", "MTagBookList_tagBookItem")
        pagecount = pg if len(items) < PAGE_SIZE else 9999
        m = re.search(r'data-total="(\d+)"', html)
        if m:
            pagecount = int(m.group(1))
        else:
            m = re.search(r'MorePagination_middleItem[^>]*>\s*\d+/(\d+)\s*<', html)
            if m:
                pagecount = int(m.group(1))
            else:
                nums = [int(x) for x in re.findall(r'/vod/search/page/(\d+)/wd/', html) if x.isdigit()]
                if nums:
                    pagecount = max(nums)
                else:
                    m = re.search(r'共(\d+)条数据', html)
                    if m:
                        pagecount = max(1, (int(m.group(1)) + 9) // 10)
        return items, pagecount

    def _fetch_detail(self, vid):
        url = f"{self.host}/index.php/vod/detail/id/{vid}.html"
        html = self._get_html(url)
        if not html:
            return None
        name = ""
        pic = ""
        category = ""
        intro = ""
        m = re.search(r'class="DramaDetail_bookName"[^>]*>([^<]+)<', html)
        if m:
            name = m.group(1).strip()
        if not name:
            m = re.search(r'class="dramaDetail_bookName"[^>]*>([^<]+)<', html)
            if m:
                name = m.group(1).strip()
        m = re.search(r'class="DramaDetail_bookCover"[^>]*src="([^"]+)"', html)
        if m:
            pic = m.group(1)
        if not pic:
            m = re.search(r'class="image_imageItem"[^>]*src="([^"]+)"', html)
            if m:
                pic = m.group(1)
        m = re.search(r'class="DramaDetail_tagsBox"[^>]*>(.*?)</div>', html, re.S)
        if m:
            tm = re.search(r'<a[^>]*>([^<]+)</a>', m.group(1))
            if tm:
                category = tm.group(1).strip()
        if not category:
            m = re.search(r'class="dramaDetail_tagsBox"[^>]*>(.*?)</div>', html, re.S)
            if m:
                tm = re.search(r'<a[^>]*>([^<]+)</a>', m.group(1))
                if tm:
                    category = tm.group(1).strip()
        m = re.search(r'class="[^"]*DramaDetail_intro[^"]*"[^>]*>(.*?)</div>', html, re.S)
        if m:
            intro = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if not intro:
            m = re.search(r'class="[^"]*introduction_intro[^"]*"[^>]*>(.*?)</div>', html, re.S)
            if m:
                intro = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        remarks = ""
        m = re.search(r'class="BrowseList_totalChapterNum"[^>]*>([^<]+)<', html)
        if m:
            remarks = m.group(1).strip()
        if not remarks:
            m = re.search(r'class="BrowseList_lastChapter"[^>]*>([^<]+)<', html)
            if m:
                remarks = m.group(1).strip()
        actor = ""
        director = ""
        pdata = self._play_data(vid)
        if pdata:
            vd = pdata.get("vod_data") or {}
            actor = (vd.get("vod_actor") or "").replace("&amp;", "&")
            director = (vd.get("vod_director") or "").replace("&amp;", "&")
            if not category:
                category = vd.get("vod_class") or ""
        actors = [a.strip() for a in re.split(r'[&＆／/、]', actor) if a.strip()] if actor else []
        play_url = f"{self.host}/index.php/vod/play/id/{vid}/sid/1/nid/1.html"
        return {
            "name": name or vid,
            "pic": pic,
            "category": category,
            "description": intro,
            "remarks": remarks,
            "director": director,
            "actors": actors,
            "episodes": [{"name": "全集", "url": play_url}],
            "source_name": "全集",
        }

    def _fetch_play(self, play_id):
        play_id = str(play_id or "").strip()
        if not play_id.startswith("http"):
            play_id = self.host + "/" + play_id.lstrip("/")
        html = self._get_html(play_id)
        if not html:
            return ""
        pdata = self._parse_player(html)
        if pdata:
            url = pdata.get("url") or ""
            enc = pdata.get("encrypt") or 0
            if enc == 0 and url:
                return url
            if enc in (1, 2) and url:
                try:
                    import base64
                    pad = url + "=" * ((4 - len(url) % 4) % 4)
                    return base64.b64decode(pad).decode("utf-8", "ignore")
                except Exception:
                    return url
        cands = []
        for u in re.findall(r'(?:https?:)?//[^\s"\'<>]+\.(?:m3u8|mp4)(?:\?[^"\'\s<>]*)?', html, re.I):
            cands.append(u if u.startswith("http") else ("https:" + u if u.startswith("//") else u))
        for pat in (r'<iframe[^>]+src=["\']([^"\']+)["\']',
                    r'<video[^>]+src=["\']([^"\']+)["\']',
                    r'<source[^>]+src=["\']([^"\']+)["\']'):
            for mm in re.finditer(pat, html, re.I):
                cands.append(mm.group(1).strip())
        media = [u for u in cands if u.startswith("http") and ".m3u8" in u.lower()]
        if media:
            return media[0]
        media = [u for u in cands if u.startswith("http")]
        if media:
            return media[0]
        return ""


    def _play_data(self, vid):
        key = "__play_" + vid
        if key in self._cache:
            return self._cache[key]
        pdata = None
        html = self._get_html(f"{self.host}/index.php/vod/play/id/{vid}/sid/1/nid/1.html")
        if html:
            pdata = self._parse_player(html)
        self._cache[key] = pdata
        return pdata

    def _parse_player(self, html):
        idx = html.find("player_aaaa=")
        if idx < 0:
            idx = html.find("player_aaaa =")
        if idx < 0:
            return None
        start = html.find("{", idx)
        if start < 0:
            return None
        depth = 0
        i = start
        while i < len(html):
            c = html[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(html[start:i + 1])
                    except Exception:
                        return None
            i += 1
        return None

    def _parse_cards(self, html, *item_classes):
        items = []
        best_cls, best_count = None, 0
        for cls in item_classes:
            cnt = len(re.findall(r'class="[^"]*%s[^"]*"' % re.escape(cls), html))
            if cnt > best_count:
                best_count, best_cls = cnt, cls
        if not best_cls or best_count == 0:
            return []
        for m in re.finditer(r'<div[^>]+class="([^"]*%s[^"]*)"' % re.escape(best_cls), html):
            block = html[m.start():m.start() + 2600]
            title = ""
            pic = ""
            remarks = ""
            hid = ""
            ma = re.search(r'href="/index\.php/vod/detail/id/(\d+)\.html"', block)
            if ma:
                hid = ma.group(1)
            mi = re.search(r'<img[^>]+src="([^"]+)"', block)
            if mi:
                pic = mi.group(1)
            mn = re.search(r'class="[^"]*bookName[^"]*"[^>]*>(?:<span>)?([^<]+)', block)
            if mn:
                title = mn.group(1).strip()
            if not title:
                ma2 = re.search(r'<img[^>]+alt="([^"]+)"', block)
                if ma2:
                    alt = ma2.group(1).strip()
                    if alt and alt not in ("已完结", "更新全集", "全集") and not re.fullmatch(r'\d+集', alt):
                        title = alt
            mr = re.search(r'class="[^"]*(?:totalChapterNum|lastChapter)[^"]*"[^>]*>([^<]+)<', block)
            if mr:
                remarks = mr.group(1).strip()
            if hid:
                items.append({"id": hid, "name": title or hid, "pic": pic, "remarks": remarks})
        return items

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("id") or item.get("vod_id") or "")
        return {
            "vod_id": self._vod_id(vid),
            "vod_name": item.get("name") or item.get("title") or vid,
            "vod_pic": self._pic(item),
            "vod_remarks": item.get("remarks") or item.get("update_label") or "",
        }

    def _pic(self, item):
        for k in ("img_y", "cover", "pic", "img", "thumb", "vod_pic"):
            v = item.get(k)
            if v:
                return v
        return ""

    def _safe_label(self, text):
        return str(text or "").replace("$", "＄").replace("#", "＃").strip()

    def _vod_id(self, site_id):
        return f"{VOD_ID_PREFIX}{site_id}" if VOD_ID_PREFIX else str(site_id)

    def _clickable(self, kind, name):
        if not name:
            return ""
        ident = f"{kind}/{quote(name, safe='')}"
        payload = json.dumps({"id": ident, "name": name, "type_flag": "0"}, ensure_ascii=False, separators=(",", ":"))
        return f"[a=cr:{payload}/]{name}[/a]"

    def _int(self, x, d=0):
        try:
            return int(x)
        except Exception:
            return d

    @staticmethod
    def _string_map(value):
        if not isinstance(value, dict):
            return {}
        return {str(k): str(v) for k, v in value.items() if v is not None}

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
                headers = dict(kw.get("headers") or {})
                headers.setdefault("User-Agent", UA)
                opts = {"timeout": kw.get("timeout", 15000), "cookie": True, "headers": headers}
                for k in ("params", "method", "postType", "data", "body", "buffer", "redirect", "callTimeout"):
                    if k in kw and kw[k] is not None:
                        opts[k] = kw[k]
                resp = self._resp_dict(net.req(url, opts))
                if self._should_retry(resp):
                    resp = self._resp_dict(net.req(url, opts))
                return resp
            except Exception:
                return {}
        resp = self._req_urllib(url, **kw)
        if self._should_retry(resp):
            resp = self._req_urllib(url, **kw)
        return resp

    def _should_retry(self, resp):
        code = resp.get("code") or 0
        if code in (403, 429, 502, 503):
            return True
        content = resp.get("content")
        if isinstance(content, str) and CHALLENGE in content and "html" in content[:200].lower():
            return True
        return False

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
            if self._opener is None:
                self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._cj))
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with self._opener.open(req, timeout=timeout) as resp:
                raw = resp.read()
                enc = (resp.headers.get("Content-Encoding") or "").lower()
                if enc == "gzip":
                    raw = gzip.decompress(raw)
                elif enc == "deflate":
                    raw = zlib.decompress(raw)
                return {"code": resp.getcode() or 0, "content": raw.decode("utf-8", "replace"), "headers": dict(resp.headers), "error": None}
        except urllib.error.HTTPError as e:
            try:
                raw = e.read()
                return {"code": e.code, "content": raw.decode("utf-8", "replace"), "headers": dict(e.headers), "error": None}
            except Exception:
                return {"code": e.code, "content": "", "headers": {}, "error": None}
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
