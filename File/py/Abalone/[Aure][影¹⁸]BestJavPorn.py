# -*- coding: utf-8 -*-
# [BestJavPorn¹⁸ 更新于:2026-11-06]
import json
import re
import time
import threading
import base64
import urllib.request
import urllib.parse
from urllib.parse import quote, unquote, quote_plus
from hashlib import md5

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        def proxy(self, params):
            return [404, "text/plain", ""]
        def localProxy(self, params):
            return [404, "text/plain", ""]

NAME = "BestJavPorn"
HOSTS = ["https://bestjavporn.me"]
UA = "Mozilla/5.0 (Linux; Android 12; SM-S9180) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 20
CACHE_TTL = 60
DEBUG = False

CATS = [
    {"id": "censored", "name": "Censored"},
    {"id": "reducing-mosaic", "name": "Reducing Mosaic"},
    {"id": "amateur", "name": "Amateur"},
]

try:
    from Crypto.Cipher import AES
    _HAS_CRYPTO = True
except Exception:
    _HAS_CRYPTO = False


class Spider(BaseSpider):

    def __init__(self):
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self._cache = {}
        self._cache_time = {}
        self._lock = threading.Lock()
        self._good_host = None

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
            slug = unquote(tid.split("/", 1)[1])
            if tid.startswith("actor/"):
                items = self._fetch_actor(slug, pg)
            elif tid.startswith("director/"):
                items = self._fetch_studio(slug, pg)
            else:
                items = self._fetch_tag(slug, pg)
            has_more = len(items) >= PAGE_SIZE
            return {
                "list": [self._vod(x) for x in items],
                "page": pg,
                "pagecount": 9999 if has_more else pg,
                "limit": PAGE_SIZE,
                "total": 999999,
            }
        items = self._fetch_list(tid, pg, extend)
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pg if len(items) < PAGE_SIZE else 9999,
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
        eps = data.get("episodes") or []
        if eps:
            lines = []
            for ep in eps:
                title = self._safe_label(ep.get("name") or "正片")
                url = ep.get("url") or ""
                if url:
                    lines.append("%s$%s" % (title, url))
            play_url = "#".join(lines)
            play_from = "正片"
        else:
            url = data.get("url") or vid
            play_url = "正片$%s" % url
            play_from = "正片"
        vod = {
            "vod_id": self._vod_id(vid),
            "vod_name": data.get("name") or vid,
            "vod_pic": data.get("pic") or "",
            "type_name": data.get("category") or "",
            "vod_year": str(data.get("year") or ""),
            "vod_area": data.get("area") or "",
            "vod_remarks": data.get("duration") or "",
            "vod_director": self._clickable("director", data.get("studio_slug") or "", data.get("studio") or ""),
            "vod_actor": "、".join(self._clickable("actor", a.get("slug") or "", a.get("name") or "") for a in data.get("actors") or []),
            "vod_content": data.get("description") or "",
            "vod_play_from": play_from,
            "vod_play_url": play_url,
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        items = self._fetch_search(str(key or "").strip(), pg)
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pg if len(items) < PAGE_SIZE else 9999,
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def playerContent(self, flag, id, vipFlags):
        url = self._fetch_play(str(id or ""))
        if not url:
            return {"parse": 0, "msg": "无法获取播放地址"}
        result = {
            "parse": 0,
            "jx": 0,
            "url": url,
            "header": self._string_map({"User-Agent": UA}),
        }
        return result

    def liveContent(self, url):
        return "[]"

    def getProxyUrl(self, params=None, local=True):
        from com.github.catvod import Proxy
        url = Proxy.getUrl(local)
        sk = getattr(self, "siteKey", "") or ""
        return url + "?do=py" + ("&siteKey=%s" % sk if sk else "")

    def proxyUrl(self, params=None, local=True):
        return self.getProxyUrl(params, local)

    def _img_stream(self, data):
        net = getattr(self, "net", None)
        if net is not None and hasattr(net, "stream"):
            try:
                def _gen():
                    yield data
                return net.stream(_gen())["stream"]
            except Exception:
                pass
        return data

    def proxy(self, params):
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                return [404, "text/plain", ""]
        if not isinstance(params, dict):
            return [404, "text/plain", ""]
        if params.get("type") == "pic":
            net = getattr(self, "net", None)
            try:
                if net is not None and hasattr(net, "reqParts"):
                    raw = net.reqParts(params["url"], {"buffer": 3})[1]
                else:
                    raw = net.req(params["url"], {"buffer": 3})["content"]
                img = raw
                return [200, "image/jpeg", self._img_stream(img), {}]
            except Exception:
                return [404, "text/plain", ""]
        return [404, "text/plain", ""]

    localProxy = proxy

    def _safe_label(self, text):
        return str(text or "").replace("$", "＄").replace("#", "＃").strip()

    def _vod_id(self, site_id):
        return str(site_id)

    def _clickable(self, kind, ident, name=""):
        name = name or ident
        if not name:
            return ""
        ident = "%s/%s" % (kind, quote(str(ident or name), safe=""))
        payload = json.dumps({"id": ident, "name": name, "type_flag": "0"}, ensure_ascii=False, separators=(",", ":"))
        return "[a=cr:%s/]%s[/a]" % (payload, name)

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
                opts = {"timeout": kw.get("timeout", 20000)}
                for k in ("headers", "method", "data", "body", "buffer", "cookie"):
                    if k in kw and kw[k] is not None:
                        opts[k] = kw[k]
                resp = net.req(url, opts)
                return self._resp_dict(resp)
            except Exception:
                return {}
        return self._req_urllib(url, **kw)

    def _req_urllib(self, url, **kw):
        try:
            timeout = (kw.get("timeout") or 20000) / 1000.0
            headers = dict(kw.get("headers") or {})
            headers.setdefault("User-Agent", UA)
            headers.setdefault("Accept", "*/*")
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            return {"code": resp.status, "content": raw, "headers": {}, "error": None}
        except Exception:
            return {}

    def _get(self, url, **kw):
        resp = self._req(url, **kw)
        if not resp:
            return ""
        content = resp.get("content") or ""
        if isinstance(content, bytes):
            try:
                return content.decode("utf-8", "replace")
            except Exception:
                return content.decode("latin1", "replace")
        return str(content)

    def _classes(self):
        hit = self._cache.get("__cls")
        if hit and time.time() - self._cache_time.get("__cls", 0) < CACHE_TTL:
            return hit[0]
        arr = []
        for c in CATS:
            arr.append({"type_id": c["id"], "type_name": c["name"]})
        if not arr:
            arr = [{"type_id": "censored", "type_name": "Censored"}]
        with self._lock:
            self._cache["__cls"] = (arr, time.time())
        return arr

    def _filters(self, classes):
        sort_filter = {
            "key": "order", "name": "排序", "init": "latest",
            "value": [{"n": "默认", "v": ""}, {"n": "最新", "v": "latest"}, {"n": "最热", "v": "most-viewed"}],
        }
        return {c["type_id"]: [sort_filter] for c in classes}

    def _home_items(self):
        items = []
        try:
            html = self._get(self.host + "/")
            items = self._parse_cards(html)
        except Exception:
            items = []
        if not items:
            for c in CATS:
                try:
                    html = self._get(self.host + "/category/" + c["id"])
                    it = self._parse_cards(html)
                    if it:
                        items = it
                        break
                except Exception:
                    continue
        return items[:PAGE_SIZE]

    def _parse_cards(self, html):
        cards = []
        if not html:
            return cards
        for m in re.finditer(r'<article\b[^>]*class="[^"]*loop-video[^"]*"[^>]*>', html):
            block = html[m.start():m.start() + 3000]
            pm = re.search(r'data-post-id="(\d+)"', html[m.start():m.start() + 200])
            if not pm:
                continue
            vid = pm.group(1)
            hm = re.search(r'<a href="([^"]+)"[^>]*title="([^"]*)"', block)
            if not hm:
                continue
            url = hm.group(1)
            title = hm.group(2)
            pm2 = re.search(r'<img[^>]*data-src="([^"]+)"', block)
            pic = pm2.group(1) if pm2 else ""
            dm = re.search(r'<span class="duration">\s*<i[^>]*></i>\s*([0-9:]+)\s*</span>', block)
            rem = dm.group(1).strip() if dm else ""
            title = title.replace("&#8216;", "'").replace("&#8217;", "'").replace("&#038;", "&").replace("&amp;", "&")
            slug = ""
            sm = re.search(r'href="[^"]*/([a-z0-9][a-z0-9-]*/[0-9]+|[a-z0-9]+-[0-9]+)"', block)
            if sm:
                slug = sm.group(1)
            if not slug:
                sm2 = re.search(r'<a href="[^"]*?/([a-z0-9][a-z0-9-]*)"', block)
                if sm2:
                    slug = sm2.group(1)
            vid_final = slug or vid
            cards.append({"id": vid_final, "name": title, "pic": pic, "remarks": rem, "url": url})
        seen = set()
        uniq = []
        for c in cards:
            code_m = re.search(r'([A-Z]{2,6}-\d{2,5})', c.get("name") or c.get("id") or "")
            dedup_key = (code_m.group(1) if code_m else c["id"]).lower()
            if dedup_key not in seen:
                seen.add(dedup_key)
                uniq.append(c)
        return uniq

    def _fetch_list(self, tid, pg, extend):
        if pg <= 1:
            url = self.host + "/category/" + tid
        else:
            url = self.host + "/category/" + tid + "/page/" + str(pg)
        html = self._get(url)
        return self._parse_cards(html)

    def _fetch_search(self, kw, pg):
        if pg <= 1:
            url = self.host + "/?s=" + quote_plus(kw)
        else:
            url = self.host + "/page/" + str(pg) + "?s=" + quote_plus(kw)
        html = self._get(url)
        return self._parse_cards(html)

    def _fetch_actor(self, slug, pg):
        if pg <= 1:
            url = self.host + "/actor/" + slug
        else:
            url = self.host + "/actor/" + slug + "/page/" + str(pg)
        html = self._get(url)
        return self._parse_cards(html)

    def _fetch_studio(self, slug, pg):
        if pg <= 1:
            url = self.host + "/studios/" + slug
        else:
            url = self.host + "/studios/" + slug + "/page/" + str(pg)
        html = self._get(url)
        return self._parse_cards(html)

    def _fetch_tag(self, slug, pg):
        if pg <= 1:
            url = self.host + "/tag/" + slug
        else:
            url = self.host + "/tag/" + slug + "/page/" + str(pg)
        html = self._get(url)
        return self._parse_cards(html)

    def _fetch_detail(self, vid):
        url = self.host + "/" + vid
        html = self._get(url)
        if not html:
            return None
        return self._parse_detail(html)

    def _parse_detail(self, html):
        title = ""
        m = re.search(r'<h1[^>]*>([^<]+)<', html)
        if m:
            title = m.group(1).strip()
        if not title:
            m = re.search(r'<title>([^<]*)</title>', html)
            if m:
                title = m.group(1).split(" - ")[0].strip()
        pic = ""
        m = re.search(r'property="og:image"\s+content="([^"]+)"', html)
        if m:
            pic = m.group(1)
        actors = []
        for m in re.finditer(r'<a href="[^"]*?/actor/([^"]+)"[^>]*title="([^"]+)"[^>]*>', html):
            slug = m.group(1).strip()
            a = m.group(2).strip()
            if a and slug and a not in actors:
                actors.append({"slug": slug, "name": a})
        if not actors:
            for m in re.finditer(r'<a href="[^"]*?/actor/([^"]+)"[^>]*>([^<]+)<', html):
                slug = m.group(1).strip()
                a = m.group(2).strip()
                if a and slug and a not in actors:
                    actors.append({"slug": slug, "name": a})
        studio = ""
        studio_slug = ""
        m = re.search(r'<div id="video-actors">\s*<i class="fa fa-film"></i>\s*Studio:\s*<a href="[^"]*?/studios/([^"]+)"[^>]*>([^<]+)<', html)
        if m:
            studio_slug = m.group(1).strip()
            studio = m.group(2).strip()
        if not studio:
            m = re.search(r'<div id="video-actors">\s*<i class="fa fa-film"></i>\s*Studio:\s*<a[^>]*>([^<]+)<', html)
            if m:
                studio = m.group(1).strip()
        duration = ""
        m = re.search(r'<i class="fa fa-clock-o"></i>\s*Duration:\s*([^<]+)<', html)
        if m:
            duration = m.group(1).strip()
        category = ""
        m = re.search(r'<a href="[^"]*?/category/([^"]+)"[^>]*>([^<]+)<', html)
        if m:
            category = m.group(2).strip()
        description = ""
        m = re.search(r'property="og:description"\s+content="([^"]+)"', html)
        if m:
            description = m.group(1).strip()
        code = ""
        m = re.search(r'\b([A-Z]{2,6}-\d{2,5})\b', title)
        if m:
            code = m.group(1)
        embed = ""
        m = re.search(r'base64,([A-Za-z0-9+/=]+)', html)
        if m:
            try:
                dec = base64.b64decode(m.group(1)).decode("utf-8", "replace")
                mm = re.search(r'var defaultUrl = "([^"]+)"', dec)
                if mm:
                    embed = mm.group(1)
            except Exception:
                embed = ""
        return {
            "name": title,
            "pic": pic,
            "category": category,
            "actors": actors,
            "studio": studio,
            "studio_slug": studio_slug,
            "duration": duration,
            "description": description,
            "code": code,
            "embed": embed,
            "episodes": [{"name": "正片", "url": embed}] if embed else [],
        }

    def _fetch_play(self, vid):
        if "videplay.us/embed/" in str(vid):
            return self._resolve_embed(str(vid))
        data = self._fetch_detail(vid)
        if not data:
            return ""
        embed = data.get("embed") or ""
        if not embed:
            return ""
        try:
            return self._resolve_embed(embed)
        except Exception:
            return ""

    def _resolve_embed(self, embed):
        emb_html = self._get(embed)
        if not emb_html:
            return ""
        m1 = re.search(r"hdddedd252\s*=\s*'([^']+)'", emb_html)
        m2 = re.search(r"hdddedg252\s*=\s*'([^']+)'", emb_html)
        if not m1 or not m2:
            return ""
        key = m1.group(1).encode()
        iv = m2.group(1).encode()
        m3 = re.search(r"mvarr\['42_1'\]=.*?',\s*'([^']+)'", emb_html)
        if not m3:
            return ""
        s = m3.group(1)
        mb = re.search(r"hcdeedg252\s*=\s*([0-9]+)", emb_html)
        mx = re.search(r"hadeedg252\s*=\s*([0-9]+)", emb_html)
        base = int(mb.group(1)) if mb else 3
        xor = int(mx.group(1)) if mx else 6
        sep = chr(base + 97) if base <= 25 else "d"
        if sep not in s:
            sep = "d" if "d" in s else "i"
        parts = s.split(sep)
        try:
            ct_b64 = "".join(chr(int(p, base) ^ xor) for p in parts)
        except Exception:
            try:
                ct_b64 = "".join(chr(int(p, 3) ^ 6) for p in s.split("d"))
            except Exception:
                return ""
        try:
            ct = base64.b64decode(ct_b64)
        except Exception:
            return ""
        if not _HAS_CRYPTO:
            return ""
        pt = AES.new(key, AES.MODE_CBC, iv).decrypt(ct)
        pad = pt[-1]
        if 1 <= pad <= 16 and pt[-pad:] == bytes([pad]) * pad:
            pt = pt[:-pad]
        vid_id = pt.decode("latin1", "replace")
        if not vid_id or not all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for c in vid_id):
            return ""
        return self._resolve_ps(vid_id)

    def _resolve_ps(self, vid_id):
        ps_url = "https://videplay.us/ps/" + vid_id
        ps_html = self._get(ps_url)
        if not ps_html:
            return ""
        mp = re.search(r"let pox = '([^']+)';", ps_html)
        md = re.search(r"let dp = '([^']+)';", ps_html)
        if not mp or not md:
            return ""
        pox = mp.group(1)
        dp_raw = md.group(1)
        try:
            dp = json.loads(base64.b64decode(dp_raw))
        except Exception:
            return ""
        key = pox.split("+")[1][1:]
        ct = base64.b64decode(dp["ct"])
        salt = bytes.fromhex(dp["s"])
        k, i = self._evp(key.encode(), salt)
        pt = AES.new(k, AES.MODE_CBC, i).decrypt(ct)
        pad = pt[-1]
        if 1 <= pad <= 16 and pt[-pad:] == bytes([pad]) * pad:
            pt = pt[:-pad]
        url = pt.decode("utf-8", "replace").replace("\\/", "/").strip('"')
        return url

    def _evp(self, password, salt, klen=32, ilen=16):
        key = b""
        prev = b""
        while len(key) < klen + ilen:
            prev = md5(prev + password + salt).digest()
            key += prev
        return key[:klen], key[klen:klen + ilen]

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("id") or "")
        return {
            "vod_id": self._vod_id(vid),
            "vod_name": item.get("name") or vid,
            "vod_pic": self._pic(item),
            "vod_remarks": item.get("remarks") or "",
        }

    def _pic(self, item):
        for k in ("pic", "cover", "img", "vod_pic"):
            v = item.get(k)
            if v:
                return v
        return ""

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

    def _page(self, items, pg, has_more=None):
        try:
            page = max(1, int(pg))
        except (TypeError, ValueError):
            page = 1
        total = len(items)
        start = (page - 1) * PAGE_SIZE
        if has_more is None:
            has_more = total >= PAGE_SIZE
        return {
            "list": items[start:start + PAGE_SIZE],
            "page": page,
            "pagecount": 9999 if has_more else page,
            "limit": PAGE_SIZE,
            "total": total,
        }
