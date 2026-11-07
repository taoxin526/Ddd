# -*- coding: utf-8 -*-
# [51吃瓜网¹⁸  更新于:2026-11-05]
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
        pass

try:
    from Crypto.Cipher import AES as _AES
    from Crypto.Util.Padding import unpad as _unpad
    _CRYPTO = "crypto"
except Exception:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        _CRYPTO = "cryptography"
    except Exception:
        _CRYPTO = None

NAME = "51吃瓜网"
HOSTS = ["https://chigua.com", "https://51cg1.com"]
UA = "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 20
CACHE_TTL = 30
DEBUG = False
VOD_ID_PREFIX = ""
MEDIA_KEY = b"f5d965df75336270"
MEDIA_IV = b"97b60394abc2fbe1"

CATEGORIES = [
    ("wpcz", "今日吃瓜"),
    ("mrds", "每日大赛"),
    ("whhj", "网黄合集"),
    ("mrdg", "吃瓜榜单"),
    ("qghj", "瓜友点播"),
    ("rdsj", "热门大瓜"),
    ("bkdg", "必看大瓜"),
    ("ysyl", "成人视频"),
    ("lldd", "伦理道德"),
    ("gcjq", "国产视频"),
    ("thjx", "探花精选"),
    ("xsxy", "学生校园"),
    ("whhl", "网红黑料"),
    ("snsn", "骚男骚女"),
    ("whmx", "明星爆料"),
    ("hwcg", "海外吃瓜"),
    ("rrcg", "人人吃瓜"),
    ("ldcg", "领导干部"),
    ("jpll", "软萌甜妹"),
    ("sjb", "竞技吃瓜"),
    ("qubk", "吃瓜看戏"),
    ("dcbq", "擦边撩骚"),
    ("zzs", "性爱技巧"),
    ("cgxw", "吃瓜新闻"),
    ("yczq", "原创博主"),
    ("51djc", "51剧场"),
    ("51hd", "往期活动"),
]


class Spider(BaseSpider):

    def __init__(self):
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self._cache = {}
        self._cache_time = {}
        self._good_host = None
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

    def liveContent(self, url):
        return "[]"

    def homeContent(self, filter):
        classes = self._classes()
        result = {"class": classes}
        if filter:
            result["filters"] = {}
        result["list"] = [self._vod(x) for x in self._fetch_list("wpcz", 1, {})]
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        tid = str(tid or "").strip("/")
        if tid.startswith("actor/") or tid.startswith("director/"):
            name = unquote(tid.split("/", 1)[1])
            return self._page(self._fetch_search(name, pg), pg)
        if tid.startswith("tag/"):
            name = unquote(tid.replace("tag/", "", 1))
            return self._page(self._fetch_search(name, pg), pg)
        items = self._fetch_list(tid, pg, extend or {})
        pc = self._pagecount_of(tid)
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pg if len(items) < PAGE_SIZE else (pc if pc else 9999),
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        responses = [self._detail(str(video_id)) for video_id in ids]
        merged = {k: v for k, v in (responses[0] or {}).items() if k != "list"} if responses[0] else {}
        merged["list"] = [item for response in responses if response for item in (response.get("list") or [])]
        return merged

    def _detail(self, vid):
        vid = str(vid or "").strip()
        if VOD_ID_PREFIX and vid.startswith(VOD_ID_PREFIX):
            vid = vid[len(VOD_ID_PREFIX):]
        data = self._fetch_detail(vid)
        if not data:
            return {"list": [], "msg": "未找到此影片"}
        episodes = data.get("episodes") or []
        gallery = data.get("gallery") or []
        lines = []
        for i, ep in enumerate(episodes, 1):
            title = self._safe_label(ep.get("name") or f"视频{i}")
            lines.append(f"{title}${vid}@{i}")
        play_parts = []
        play_from_parts = []
        if lines:
            play_parts.append("#".join(lines))
            play_from_parts.append("正片")
        if gallery:
            play_parts.append(f"图集${vid}@gallery")
            play_from_parts.append("图集")
        if not play_parts:
            play_parts.append(f"正片${vid}@gallery")
            play_from_parts.append("正片")
        vod = {
            "vod_id": vid,
            "vod_name": data.get("name") or vid,
            "vod_pic": self._pic_url(data.get("pic") or ""),
            "type_name": data.get("category") or "",
            "vod_year": str(data.get("year") or ""),
            "vod_area": data.get("area") or "",
            "vod_remarks": data.get("remarks") or "",
            "vod_director": self._clickable("director", data.get("director") or ""),
            "vod_actor": "、".join(self._clickable("actor", a) for a in data.get("actors") or []),
            "vod_content": data.get("description") or "",
            "vod_play_from": "$$$".join(play_from_parts),
            "vod_play_url": "$$$".join(play_parts),
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        items = self._fetch_search(str(key or "").strip(), pg)
        pc = self._pagecount_search(str(key or "").strip())
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pg if len(items) < PAGE_SIZE else (pc if pc else 9999),
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def playerContent(self, flag, id, vipFlags):
        raw = str(id or "").strip()
        if raw.lower().startswith("http") and (".m3u8" in raw.lower() or ".mp4" in raw.lower()):
            return {"parse": 0, "jx": 0, "url": raw,
                    "header": self._string_map({"User-Agent": UA, "Referer": self.host + "/"})}
        if "@" in raw:
            aid, kind = raw.split("@", 1)
        else:
            aid, kind = raw, "0"
        if kind == "gallery":
            proxy = self._proxy_url({"type": "gallery", "aid": aid, "ext": ".m3u8"})
            if proxy:
                return {"parse": 0, "jx": 0, "url": proxy,
                        "header": self._string_map({"User-Agent": UA, "Referer": self.host + "/"})}
            return {"parse": 0, "msg": "图集地址生成失败"}
        idx = self._int(kind, 1) - 1
        data = self._fetch_detail(aid)
        if not data:
            return {"parse": 0, "msg": "未找到此影片"}
        eps = data.get("episodes") or []
        if 0 <= idx < len(eps):
            url = eps[idx].get("url") or ""
            if url:
                return {"parse": 0, "jx": 0, "url": url,
                        "header": self._string_map({"User-Agent": UA, "Referer": self.host + "/"})}
        if eps:
            url = eps[0].get("url") or ""
            if url:
                return {"parse": 0, "jx": 0, "url": url,
                        "header": self._string_map({"User-Agent": UA, "Referer": self.host + "/"})}
        return {"parse": 0, "msg": "无法获取播放地址"}

    def proxy(self, params):
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                return [404, "text/plain", ""]
        if not isinstance(params, dict):
            return [404, "text/plain", ""]
        ptype = params.get("type")
        if ptype == "pic":
            real = params.get("url") or ""
            try:
                real = self._d64(real)
            except Exception:
                pass
            raw = self._download(real)
            if not raw:
                return [404, "text/plain", ""]
            img = self._pic_decrypt(raw)
            return [200, self._mime(img), self._img_stream(img), {}]
        if ptype == "gallery":
            aid = str(params.get("aid") or "")
            data = self._fetch_detail(aid)
            gallery = (data or {}).get("gallery") or []
            if not gallery:
                return [404, "text/plain", ""]
            text = self._gallery_m3u8(gallery)
            return [200, "application/vnd.apple.mpegurl", self._img_stream(text.encode("utf-8")), {}]
        return [404, "text/plain", ""]

    localProxy = proxy

    def getProxyUrl(self, params=None, local=True):
        from com.github.catvod import Proxy
        url = Proxy.getUrl(local)
        sk = getattr(self, "siteKey", "") or ""
        return url + "?do=py" + ("&siteKey=%s" % sk if sk else "")

    def proxyUrl(self, params=None, local=True):
        return self.getProxyUrl(params, local)

    def _classes(self):
        hit = self._cache.get("__cls")
        if hit and time.time() - self._cache_time.get("__cls", 0) < CACHE_TTL:
            return hit
        arr = [{"type_id": "wpcz", "type_name": "今日吃瓜"}]
        seen = {"wpcz"}
        html = self._get_html(self._abs("/"))
        if html:
            for m in re.finditer(r'href="(/category/([a-z0-9]+)/)"[^>]*>\s*([^<]{1,20})<', html):
                slug, nm = m.group(2), m.group(3).strip()
                if slug in seen or not nm:
                    continue
                seen.add(slug)
                arr.append({"type_id": slug, "type_name": nm})
        if len(arr) <= 1:
            arr = [{"type_id": s, "type_name": n} for s, n in CATEGORIES]
        with self._lock:
            self._cache["__cls"] = arr
            self._cache_time["__cls"] = time.time()
        return arr

    def _fetch_list(self, tid, pg, extend):
        if not tid:
            return []
        url = self._list_url(tid, pg)
        html = self._get_html(url)
        if not html:
            return []
        cards = self._parse_cards(html)
        return self._dedup(cards)

    def _list_url(self, tid, pg):
        if tid == "wpcz":
            return self._abs(f"/page/{pg}/") if pg > 1 else self._abs("/")
        return self._abs(f"/category/{tid}/{pg}/") if pg > 1 else self._abs(f"/category/{tid}/")

    def _pagecount_of(self, tid):
        hit = self._cache.get("__pc_" + tid)
        if hit and time.time() - self._cache_time.get("__pc_" + tid, 0) < CACHE_TTL:
            return hit
        url = self._list_url(tid, 1)
        html = self._get_html(url)
        pc = 0
        if html:
            if tid == "wpcz":
                nums = [int(x) for x in re.findall(r'href="/page/(\d+)/"', html)]
            else:
                nums = [int(x) for x in re.findall(r'href="/category/%s/(\d+)/"' % re.escape(tid), html)]
            if nums:
                pc = max(nums)
        with self._lock:
            self._cache["__pc_" + tid] = pc
            self._cache_time["__pc_" + tid] = time.time()
        return pc

    def _fetch_search(self, keyword, pg):
        kw = quote(str(keyword or "").strip(), safe="")
        if not kw:
            return []
        url = self._abs(f"/search/{kw}/{pg}/") if pg > 1 else self._abs(f"/search/{kw}/")
        html = self._get_html(url)
        if not html:
            return []
        return self._dedup(self._parse_cards(html))

    def _pagecount_search(self, keyword):
        kw = quote(str(keyword or "").strip(), safe="")
        if not kw:
            return 0
        html = self._get_html(self._abs(f"/search/{kw}/"))
        if not html:
            return 0
        nums = [int(x) for x in re.findall(r'href="/search/%s/(\d+)/"' % re.escape(kw), html)]
        return max(nums) if nums else 0

    def _parse_cards(self, html):
        cards = []
        seen = set()
        for m in re.finditer(r'<article\b[^>]*itemtype="http://schema\.org/BlogPosting"[^>]*>([\s\S]*?)</article>', html):
            seg = m.group(1)
            lm = re.search(r'href="(/archives/(\d+)/)"', seg)
            if not lm:
                continue
            aid = lm.group(2)
            if aid in seen:
                continue
            pic = ""
            mp = re.search(r'[xz]-bg-loader-url="([^"]+)"', seg)
            if mp:
                pic = mp.group(1)
            name = ""
            mt = re.search(r'post-card-title[^>]*>([\s\S]*?)</h2>', seg)
            if mt:
                name = re.sub(r'<[^>]+>', '', mt.group(1)).strip()
            remarks = ""
            md = re.search(r'itemprop="datePublished"\s+content="([^"]+)"', seg)
            if md:
                remarks = md.group(1)[:10]
            if not name:
                name = f"吃瓜{aid}"
            seen.add(aid)
            cards.append({"id": aid, "name": name, "pic": pic, "remarks": remarks})
        return cards

    def _fetch_detail(self, aid):
        aid = str(aid or "").strip()
        url = self._abs(f"/archives/{aid}/")
        html = self._get_html(url)
        if not html:
            return None
        name = ""
        m = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', html)
        if m:
            name = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if not name:
            m = re.search(r'property="og:title"\s+content="([^"]+)"', html)
            if not m:
                m = re.search(r'content="([^"]+)"[^>]+property="og:title"', html)
            if m:
                name = m.group(1)
        desc = ""
        m = re.search(r'property="og:description"\s+content="([^"]+)"', html)
        if not m:
            m = re.search(r'content="([^"]+)"[^>]+property="og:description"', html)
        if m:
            desc = m.group(1)
        imgs = []
        for mm in re.finditer(r'z-image-loader-url="([^"]+)"', html):
            u = mm.group(1)
            if u and u not in imgs:
                imgs.append(u)
        pic = imgs[0] if imgs else ""
        if not pic:
            m = re.search(r'property="og:image"\s+content="([^"]+)"', html)
            if not m:
                m = re.search(r'content="([^"]+)"[^>]+property="og:image"', html)
            if m:
                pic = m.group(1)
        episodes = []
        tags = []
        category = ""
        for dm in re.finditer(r'<div class="dplayer"[^>]*>', html):
            attr = dm.group(0)
            if not category:
                tm = re.search(r'data-video_type_name="([^"]+)"', attr)
                if tm:
                    category = tm.group(1).strip()
            tm = re.search(r'data-video_tag_name="([^"]+)"', attr)
            if tm:
                for t in tm.group(1).split(","):
                    t = t.strip()
                    if t and t not in tags:
                        tags.append(t)
            cm = re.search(r"data-config='([^']*)'", attr)
            if not cm:
                continue
            try:
                cfg = json.loads(cm.group(1))
            except Exception:
                continue
            v = cfg.get("video") or {}
            u = v.get("url") or ""
            if not u:
                continue
            tname = "视频"
            tv = re.search(r'data-video_title="([^"]+)"', attr)
            if tv:
                tname = tv.group(1).strip()
            episodes.append({"name": tname, "url": u})
        if not category:
            cms = re.findall(r'href="/category/([a-z0-9]+)/"[^>]*>\s*([^<]{1,20})<', html)
            if cms:
                category = cms[0][1].strip()
        return {
            "name": name,
            "pic": pic,
            "category": category,
            "year": "",
            "area": "",
            "remarks": "",
            "director": "",
            "actors": tags,
            "description": desc,
            "episodes": episodes,
            "gallery": imgs,
        }

    def _gallery_m3u8(self, gallery):
        lines = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-TARGETDURATION:5"]
        for u in gallery:
            lines.append("#EXTINF:3.000,")
            lines.append(self._gallery_pic(u))
        lines.append("#EXT-X-ENDLIST")
        return "\n".join(lines)

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("id") or item.get("vod_id") or "")
        return {
            "vod_id": vid,
            "vod_name": item.get("name") or item.get("title") or vid,
            "vod_pic": self._pic_url(item.get("pic") or ""),
            "vod_remarks": item.get("remarks") or "",
        }

    def _dedup(self, cards):
        seen = set()
        out = []
        for c in cards:
            k = str(c.get("id") or "")
            if not k or k in seen:
                continue
            seen.add(k)
            out.append(c)
        return out

    def _proxy_url(self, params):
        ptype = params.get("type")
        if ptype != "gallery":
            return ""
        aid = str(params.get("aid") or "")
        ext = str(params.get("ext") or "")
        try:
            proxy = self.getProxyUrl()
            if proxy:
                sep = "&" if "?" in proxy else "?"
                key = getattr(self, "siteKey", "") or ""
                extra = ("&siteKey=%s" % key) if (key and "siteKey=" not in proxy) else ""
                tail = ("&ext=%s" % quote(ext, safe="")) if ext else ""
                return "%s%stype=gallery&aid=%s%s%s" % (proxy, sep, quote(aid, safe=""), tail, extra)
        except Exception:
            pass
        if hasattr(self, "proxyUrl"):
            try:
                return self.proxyUrl({"type": "gallery", "aid": aid})
            except Exception:
                pass
        return ""

    def _pic_url(self, u):
        u = self._fix(u)
        if not u:
            return ""
        enc = quote(base64.b64encode(u.encode("utf-8")), safe="")
        try:
            proxy = self.getProxyUrl()
            if proxy:
                sep = "&" if "?" in proxy else "?"
                key = getattr(self, "siteKey", "") or ""
                extra = ("&siteKey=%s" % key) if (key and "siteKey=" not in proxy) else ""
                return "%s%stype=pic&url=%s%s" % (proxy, sep, enc, extra)
        except Exception:
            pass
        if hasattr(self, "proxyUrl"):
            try:
                p = self.proxyUrl({"type": "pic", "url": base64.b64encode(u.encode("utf-8")).decode("utf-8")})
                if p:
                    return p
            except Exception:
                pass
        return u

    def _download(self, url):
        url = self._fix(url)
        if not url:
            return b""
        net = getattr(self, "net", None)
        if net is not None:
            try:
                if hasattr(net, "reqParts"):
                    parts = net.reqParts(url, {"headers": {}, "buffer": 3})
                    return parts[1]
                r = net.req(url, {"headers": {}, "buffer": 3})
                return r["content"] if isinstance(r, dict) else r
            except Exception:
                pass
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.read()
        except Exception:
            return b""

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

    @staticmethod
    def _d64(s):
        s = str(s or "")
        pad = "=" * (-len(s) % 4)
        try:
            return base64.b64decode(s + pad).decode("utf-8", "ignore")
        except Exception:
            return s

    @staticmethod
    def _pic_decrypt(raw):
        if not raw:
            return raw
        if raw[:2] == b"\xff\xd8" or raw[:4] == b"\x89PNG" or raw[:4] == b"RIFF" or raw[:4] == b"WEBP":
            return raw
        if _CRYPTO == "crypto":
            try:
                pt = _AES.new(MEDIA_KEY, _AES.MODE_CBC, MEDIA_IV).decrypt(raw)
                return _unpad(pt, 16)
            except Exception:
                return raw
        if _CRYPTO == "cryptography":
            try:
                dec = Cipher(algorithms.AES(MEDIA_KEY), modes.CBC(MEDIA_IV)).decryptor()
                pt = dec.update(raw) + dec.finalize()
                return pt[:-pt[-1]] if pt else raw
            except Exception:
                return raw
        return raw

    def _gallery_pic(self, u):
        u = self._fix(u)
        if not u:
            return ""
        enc = quote(base64.b64encode(u.encode("utf-8")), safe="")
        try:
            proxy = self.getProxyUrl()
            if proxy:
                sep = "&" if "?" in proxy else "?"
                key = getattr(self, "siteKey", "") or ""
                extra = ("&siteKey=%s" % key) if (key and "siteKey=" not in proxy) else ""
                return "%s%stype=pic&url=%s%s&ext=.jpg" % (proxy, sep, enc, extra)
        except Exception:
            pass
        if hasattr(self, "proxyUrl"):
            try:
                p = self.proxyUrl({"type": "pic", "url": base64.b64encode(u.encode("utf-8")).decode("utf-8")})
                if p:
                    return p + ("&ext=.jpg" if "?" in p else "?ext=.jpg")
            except Exception:
                pass
        return u

    @staticmethod
    def _mime(raw):
        if isinstance(raw, (bytes, bytearray)) and raw[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if isinstance(raw, (bytes, bytearray)) and raw[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if isinstance(raw, (bytes, bytearray)) and raw[:4] == b"GIF8":
            return "image/gif"
        if isinstance(raw, (bytes, bytearray)) and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
            return "image/webp"
        return "image/jpeg"

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
            headers = dict(kw.get("headers") or {})
            headers.setdefault("User-Agent", UA)
            headers.setdefault("Accept", "*/*")
            req = urllib.request.Request(url, headers=headers)
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

    def _fix(self, u):
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return self.host + u
        return u

    def _abs(self, path):
        if not path:
            return ""
        if path.startswith("http"):
            return path
        if path.startswith("//"):
            return "https:" + path
        return self.host + "/" + str(path).lstrip("/")

    def _safe_label(self, text):
        return str(text or "").replace("$", "＄").replace("#", "＃").strip()

    def _clickable(self, kind, name):
        if not name:
            return ""
        ident = f"{kind}/{quote(name, safe='')}"
        payload = json.dumps({"id": ident, "name": name, "type_flag": "0"}, ensure_ascii=False, separators=(",", ":"))
        return f"[a=cr:{payload}/]{name}[/a]"

    def _page(self, items, pg):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        total = len(items)
        start = (page - 1) * PAGE_SIZE
        return {
            "list": items[start:start + PAGE_SIZE],
            "page": page,
            "pagecount": page if total < PAGE_SIZE else 9999,
            "limit": PAGE_SIZE,
            "total": total,
        }

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
