# -*- coding: utf-8 -*-
# [XX01 AV¹⁸ 更新于:2026-11-06]
import json
import re
import time
import threading
import urllib.request
import gzip
import zlib
import base64
from urllib.parse import quote, unquote

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        def proxy(self, params):
            return [404, "text/plain", ""]
        def localProxy(self, params):
            return [404, "text/plain", ""]

NAME = "XX01 AV"
HOSTS = ["https://xx01.com"]
UA = "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 24
CACHE_TTL = 30
DEBUG = False
VOD_ID_PREFIX = ""

CATS = [
    ("new", "最近更新"), ("chinese-subtitle", "中文字幕"), ("madou", "国产AV"),
    ("masem", "马赛姆"), ("kinostream", "kinostream"), ("anime", "成人动漫"),
    ("uncensored-leak", "無碼流出"), ("VR", "VR"), ("avtalk", "AV解说"),
    ("fc2", "FC2"), ("heyzo", "HEYZO"), ("tokyohot", "東京熱"),
    ("1pondo", "一本道"), ("caribbeancom", "Caribbeancom"), ("caribbeancompr", "Caribbeancompr"),
    ("10musume", "10musume"), ("pacopacomama", "pacopacomama"), ("gachinco", "Gachinco"),
    ("xxxav", "XXX-AV"), ("marriedslash", "人妻斬"), ("naughty4610", "頑皮 4610"),
    ("naughty0930", "頑皮 0930"), ("twav", "TWAV"), ("furuke", "Furuke"),
    ("klive", "韓國直播"), ("clive", "中國直播"), ("tiktok", "抖阴视频"),
    ("starface", "明星换脸"), ("cnlive", "主播直播"), ("cmedia", "国产传媒"),
    ("playgirl", "玩偶姐姐"), ("netdoor", "网曝黑料"), ("siro", "SIRO"),
    ("luxu", "LUXU"), ("maan", "PRESTIGE PREMIUM"), ("scute", "S-CUTE"),
    ("ara", "ARA"),
]

class Spider(BaseSpider):

    def __init__(self):
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self._cache = {}
        self._cache_time = {}
        self._lock = threading.Lock()
        self.options = {}

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
        result["list"] = [self._vod(x) for x in self._fetch_list("new", 1, {})[0]]
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        extend = extend or {}
        if tid.startswith("actor/") or tid.startswith("director/"):
            name = unquote(tid.split("/", 1)[1])
            items, pc = self._fetch_search(name, pg)
            return self._page([self._vod(x) for x in items], pg, pc)
        if tid.startswith("tag/"):
            name = unquote(tid.replace("tag/", "", 1))
            items, pc = self._fetch_search(name, pg)
            return self._page([self._vod(x) for x in items], pg, pc)
        items, pc = self._fetch_list(tid, pg, extend)
        return self._page([self._vod(x) for x in items], pg, pc)

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
        play_url = "正片$" + (url or vid)
        vod = {
            "vod_id": self._vod_id(vid),
            "vod_name": data.get("name") or vid,
            "vod_pic": data.get("pic") or "",
            "type_name": data.get("category") or "",
            "vod_year": str(data.get("year") or ""),
            "vod_area": data.get("area") or "",
            "vod_remarks": data.get("remarks") or "",
            "vod_director": self._clickable("director", data.get("director") or ""),
            "vod_actor": "、".join(self._clickable("actor", a) for a in data.get("actors") or []),
            "vod_content": data.get("description") or "",
            "vod_play_from": "正片",
            "vod_play_url": play_url,
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        items, pc = self._fetch_search(str(key or "").strip(), pg)
        return self._page([self._vod(x) for x in items], pg, pc)

    def playerContent(self, flag, id, vipFlags):
        url = str(id or "")
        if not url:
            return {"parse": 0, "msg": "无法获取播放地址"}
        return {"parse": 0, "jx": 0, "url": url, "header": {}}

    def liveContent(self, url):
        return "[]"

    def _proxy_base(self, local=True):
        """拿 proxy 基址并确保 ?do=py&siteKey（等价基类自动拼行为）。"""
        base = ""
        try:
            from com.github.catvod import Proxy
            base = Proxy.getUrl(local)
        except Exception:
            pass
        if not base:
            return ""
        sep = "&" if "?" in base else "?"
        if "do=" not in base:
            base = base + sep + "do=py"
        sk = getattr(self, "siteKey", "") or ""
        if sk and "siteKey=" not in base:
            base = base + "&siteKey=" + sk
        return base

    def getProxyUrl(self, params=None, local=True):
        base = self._proxy_base(local)
        if not base:
            return ""
        if params is None or isinstance(params, bool):
            return base
        if isinstance(params, dict) and params:
            qs = "&".join("%s=%s" % (k, quote(str(v), safe="")) for k, v in params.items())
            return base + ("&" + qs if qs else "")
        return base

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
            u = params.get("url") or ""
            real = self._d64(u)
            raw = self._fetch_binary(real)
            if raw is None:
                return [404, "text/plain", ""]
            return [200, self._mime(raw), self._img_stream(raw), {}]
        return [404, "text/plain", ""]

    localProxy = proxy

    def _classes(self):
        hit = self._cache.get("__cls")
        if hit and time.time() - self._cache_time.get("__cls", 0) < CACHE_TTL:
            return hit[0]
        arr = []
        for cid, cname in CATS:
            arr.append({"type_id": cid, "type_name": cname})
        with self._lock:
            self._cache["__cls"] = (arr, time.time())
        return arr

    def _filters(self, classes):
        return {c["type_id"]: [] for c in classes}

    def _page(self, items, pg, pagecount=None):
        try:
            page = max(1, int(pg))
        except (TypeError, ValueError):
            page = 1
        if pagecount is None or pagecount < 2:
            pagecount = 9999 if len(items) >= PAGE_SIZE else page
        else:
            pagecount = max(pagecount, page)
        return {
            "list": items,
            "page": page,
            "pagecount": pagecount,
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("id") or item.get("vod_id") or "")
        return {
            "vod_id": self._vod_id(vid),
            "vod_name": item.get("name") or item.get("title") or vid,
            "vod_pic": item.get("pic") or "",
            "vod_remarks": item.get("remarks") or "",
        }

    def _vod_id(self, site_id):
        return f"{VOD_ID_PREFIX}{site_id}" if VOD_ID_PREFIX else str(site_id)

    def _clickable(self, kind, name):
        if not name:
            return ""
        sid = self._search_name(name) if kind == "actor" else name
        ident = f"{kind}/{quote(sid, safe='')}"
        payload = json.dumps({"id": ident, "name": name, "type_flag": "0"}, ensure_ascii=False, separators=(",", ":"))
        return f"[a=cr:{payload}/]{name}[/a]"

    @staticmethod
    def _search_name(name):
        """演员名清洗: 去掉翻译括号 (日文/英文) 取简体名，否则搜索 0 条。
        例: '园田美樱 (園田みおん)' -> '园田美樱'。"""
        n = re.sub(r'\s*\([^)]*\)', '', str(name or "")).strip()
        return n or str(name or "")

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

    def _resp_dict(self, resp):
        if isinstance(resp, dict):
            return resp
        if isinstance(resp, str):
            return {"code": 200, "content": resp, "headers": {}, "error": None}
        if isinstance(resp, (bytes, bytearray)):
            return {"code": 200, "content": resp, "headers": {}, "error": None}
        return {"code": 0, "content": "", "headers": {}, "error": str(resp)}

    def _req(self, url, **kw):
        net = getattr(self, 'net', None)
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
        resp = self._req(url, **kw)
        if resp.get("error"):
            return None
        code = resp.get("code") or 0
        if not 200 <= code < 300:
            return None
        return resp.get("content", "")

    def _fetch_binary(self, url):
        net = getattr(self, "net", None)
        if net is not None:
            try:
                if hasattr(net, "reqParts"):
                    r = net.reqParts(url, {"buffer": 3})
                    if r and len(r) > 1 and r[1]:
                        return r[1]
                r = net.req(url, {"buffer": 3})
                r = self._resp_dict(r)
                if r.get("content") and not r.get("error"):
                    return r["content"]
            except Exception:
                pass
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read()
        except Exception:
            return None

    def _mime(self, data):
        if data is None:
            return "application/octet-stream"
        head = data[:4]
        if head[:2] == b"\xff\xd8":
            return "image/jpeg"
        if head[:4] == b"\x89PNG":
            return "image/png"
        if head[:3] == b"GIF":
            return "image/gif"
        if head[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "image/webp"
        return "application/octet-stream"

    def _proxy_url(self, params):
        """统一封面/媒体代理 URL，兼容三契约（Quss 规范 v2.2）：
        - FongMi 5.8.5+: proxyUrl(params, local) 基类自动拼 do=py&siteKey 并编码
        - FongMi 5.8.4: getProxyUrl(params, local) 基类自动拼
        - TVBox: getProxyUrl(local) 只 bool，源内自拼业务参数
        """
        if hasattr(self, "proxyUrl"):
            try:
                return self.proxyUrl(params, True)
            except TypeError:
                try:
                    return self.proxyUrl(params)
                except Exception:
                    return ""
        gp = getattr(self, "getProxyUrl", None)
        if gp is None:
            return ""
        try:
            import inspect
            names = list(inspect.signature(gp).parameters.keys())
        except Exception:
            names = ["params", "local"]
        if names and names[0] == "params":
            try:
                return gp(params, True)
            except TypeError:
                try:
                    return gp(params)
                except Exception:
                    return ""
        base = gp(True)
        if isinstance(params, dict) and params:
            qs = "&".join("%s=%s" % (k, quote(str(v), safe="")) for k, v in params.items())
            return base + ("&" + qs if qs else "")
        return base

    def _pic_url(self, pic):
        if not pic:
            return ""
        raw_b64 = base64.b64encode(pic.encode("utf-8")).decode("utf-8")
        try:
            u = self._proxy_url({"type": "pic", "url": raw_b64})
            if u:
                return u
        except Exception:
            pass
        # 兜底: getProxyUrl() 拿基址手动拼（5.8.4/TVBox 无 proxyUrl 时）
        try:
            base = self.getProxyUrl()
            if base:
                sep = "&" if "?" in base else "?"
                enc = quote(raw_b64, safe="")
                key = getattr(self, "siteKey", "") or ""
                extra = ("&siteKey=%s" % key) if (key and "siteKey=" not in base) else ""
                return "%s%stype=pic&url=%s%s" % (base, sep, enc, extra)
        except Exception:
            pass
        return pic

    @staticmethod
    def _d64(s):
        s = str(s or "")
        try:
            from urllib.parse import unquote
            s = unquote(s)
        except Exception:
            pass
        pad = "=" * (-len(s) % 4)
        try:
            return base64.b64decode(s + pad).decode("utf-8", "ignore")
        except Exception:
            return s

    def _norm_pic(self, u):
        if not u:
            return ""
        try:
            from html import unescape
            u = unescape(u)
        except Exception:
            pass
        if "api/proxy" in u and "url=" in u:
            m = re.search(r"[?&]url=([^&]+)", u)
            if m:
                u = unquote(m.group(1))
        return u

    def _parse_cards(self, html):
        out = []
        if not html:
            return out
        parts = re.split(r'(?=<div[^>]*class="thumbnail group")', html)
        for c in parts:
            if "thumbnail group" not in c:
                continue
            tm = re.search(r'class="text-secondary[^"]*"[^>]*href="([^"]+)"[^>]*>\s*([^<]{1,200})', c)
            if not tm:
                tm = re.search(r'href="([^"]+)"[^>]*class="text-secondary[^"]*"[^>]*>\s*([^<]{1,200})', c)
            if not tm:
                continue
            href = tm.group(1).strip()
            title = tm.group(2).strip()
            if not href or not title:
                continue
            if not re.match(r'^/(?:video-\d+|[A-Za-z0-9][A-Za-z0-9_-]*)$', href):
                continue
            im = re.search(r'<img[^>]*data-src="([^"]+)"', c)
            pic = im.group(1) if im else ""
            rem = ""
            dm = re.search(r'bg-gray-800[^"]*"[^>]*?>\s*([0-9:]{1,20})\s*<', c)
            if dm:
                rem = dm.group(1).strip()
            else:
                cm = re.search(r'bg-red-800[^"]*"[^>]*?>\s*([^<]{1,20})<', c)
                if cm:
                    rem = cm.group(1).strip()
            out.append({"id": href.lstrip("/"), "name": title, "pic": self._pic_url(self._norm_pic(pic)), "remarks": rem})
        # 站点渲染重复卡（同一视频多次出现）——按 id 去重保序
        seen = set()
        dedup = []
        for it in out:
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            dedup.append(it)
        return dedup

    def _fetch_list(self, tid, pg, extend):
        url = self.host + "/" + tid.strip("/")
        if pg > 1:
            url += "?page=%d" % pg
        html = self._get_html(url)
        if not html:
            return [], 1
        return self._parse_cards(html), self._pagecount(html)

    def _fetch_search(self, keyword, pg):
        kw = quote(keyword.strip(), safe="")
        url = self.host + "/search/" + kw
        if pg > 1:
            url += "?page=%d" % pg
        html = self._get_html(url)
        if not html:
            return [], 1
        return self._parse_cards(html), self._pagecount(html)

    def _pagecount(self, html):
        m = re.search(r'totalPages\s*:\s*(\d+)', html)
        if m:
            return max(1, int(m.group(1)))
        pages = [int(x) for x in re.findall(r'page[=](\d+)', html) if x.isdigit()]
        if pages:
            return max(pages)
        return 1

    def _decode_sources(self, html):
        m = re.search(r"\}\((.+),\s*\d+,\s*\d+,\s*'([^']*)'\.split\('\|'\),0,\{\}\)\)", html, re.S)
        if not m:
            return None
        packed = m.group(1).strip()
        if packed[:1] == "'" and packed[-1:] == "'":
            packed = packed[1:-1]
        packed = packed.replace("\\'", "'")
        dic = m.group(2).split('|')
        def repl(mm):
            try:
                i = int(mm.group(0), 36)
                return dic[i] if i < len(dic) else mm.group(0)
            except Exception:
                return mm.group(0)
        out = re.sub(r'\b[0-9a-z]+\b', repl, packed)
        res = {}
        for mm in re.finditer(r"(source|source842|source1280)\s*=\s*'([^']+)'", out):
            res[mm.group(1)] = mm.group(2)
        return res

    def _play_url(self, source):
        if not source:
            return ""
        if ('/proxy/' in source or 'pl2.vvvvvvvv.top' in source or 'pl3.vvvvvvvv.top' in source
                or 'player.xxnet999.com' in source or '/index.m3u8' in source or source.startswith('/')):
            return source
        return 'https://pl3.vvvvvvvv.top/api/play?url=' + quote(source, safe='')

    def _clean_text(self, s):
        return re.sub(r'\s+', ' ', s).strip()

    def _fetch_detail(self, vid):
        vid = str(vid or "")
        if not vid:
            return {}
        url = self.host + "/" + vid
        html = self._get_html(url)
        if not html:
            return {}
        body = html[html.find("<body"):] if "<body" in html else html
        data = {}
        m = re.search(r'<h1[^>]*itemprop="name"[^>]*>(.*?)</h1>', body, re.S)
        if m:
            data["name"] = self._clean_text(re.sub(r'<[^>]+>', '', m.group(1)))
        if not data.get("name"):
            m = re.search(r'<title>([^<]+)</title>', html)
            if m:
                data["name"] = self._clean_text(m.group(1).split(" - ")[0])
        m = re.search(r'og:image" content="([^"]+)"', html)
        if m:
            data["pic"] = self._pic_url(self._norm_pic(m.group(1)))
        actresses = []
        for am in re.finditer(r'<span>女优:</span>\s*<a href="[^"]*"[^>]*>\s*(?:<span[^>]*>([^<]*)</span>|([^<]*))</a>', body):
            nm = (am.group(1) or am.group(2) or "").strip()
            if nm and nm not in actresses:
                actresses.append(nm)
        data["actors"] = actresses
        m = re.search(r'<span>导演:</span>\s*<a href="[^"]*"[^>]*>\s*(?:<span[^>]*>([^<]*)</span>|([^<]*))</a>', body)
        if m:
            data["director"] = (m.group(1) or m.group(2) or "").strip()
        m = re.search(r'<span>系列:</span>\s*<a href="[^"]*"[^>]*>\s*([^<]{1,80})</a>', body)
        if m:
            data["series"] = self._clean_text(m.group(1))
        m = re.search(r'<span>发行商:</span>\s*<a href="[^"]*"[^>]*>\s*(?:<span[^>]*>([^<]*)</span>|([^<]*))</a>', body)
        if m:
            data["maker"] = (m.group(1) or m.group(2) or "").strip()
        m = re.search(r'<p class="sr-only"[^>]*itemprop="description"[^>]*>(.*?)</p>', body, re.S)
        if m:
            desc = self._clean_text(re.sub(r'<[^>]+>', '', m.group(1)))
            dm = re.search(r'时长\s*(\d{1,2}:\d{2}:\d{2})', desc)
            if dm:
                data["remarks"] = dm.group(1)
            data["description"] = desc
        m = re.search(r'uploadDate[^0-9]*(\d{4})-(\d{2})-(\d{2})', html)
        if m:
            data["year"] = m.group(1)
        src = self._decode_sources(html)
        source = ""
        if src:
            source = src.get("source") or src.get("source842") or src.get("source1280") or ""
        data["url"] = self._play_url(source)
        return data
