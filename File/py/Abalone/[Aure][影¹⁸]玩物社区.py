# -*- coding: utf-8 -*-
# [玩物社区¹⁸  更新于:2026-11-05 15:25]
import json
import re
import time
import html as _html
import gzip
import zlib
import base64
import urllib.request
from urllib.parse import quote, unquote, urljoin, urlparse

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        def proxy(self, params):
            return [404, "text/plain", ""]
        def localProxy(self, params):
            return [404, "text/plain", ""]

NAME = "玩物社区"
HOSTS = ["https://pku.daqbqrri.cc", "https://wanwuu.com", "https://c5ad.oqgciumz.cc", "https://wanwusm.io"]
UA = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36")
PAGE_SIZE = 24
CACHE_TTL = 30

CLASSES = [
    ("new", "视频"),
    ("zhibo-huifang", "直播回放"),
    ("guochan-sm", "国产sm"),
    ("rihan-sm", "日韩sm"),
    ("oumei-sm", "欧美sm"),
    ("dongman-sm", "动漫sm"),
    ("tiaojiao-av", "调教av"),
    ("ai-duanju", "AI成人短剧"),
    ("ai-manju", "AI漫剧"),
    ("ai-huanlian", "AI换脸"),
    ("ai-meinv", "AI美女"),
    ("all", "AI全部"),
    ("moviesets", "视频合集"),
]
AI_TIDS = {"all", "ai-duanju", "ai-manju", "ai-huanlian", "ai-meinv"}

SORTS = [
    ("new", "最近更新"),
    ("watchings", "正在播放"),
    ("popular", "当前最热"),
    ("mon", "本月最热"),
    ("10min", "10分钟以上"),
    ("20min", "20分钟以上"),
    ("collect", "本月收藏"),
    ("hd", "高清"),
    ("every", "每月最热"),
    ("current", "本月讨论"),
    ("most", "收藏最多"),
]

_AES_KEY = b"f5d965df75336270"
_AES_IV = b"97b60394abc2fbe1"

_B36 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_unescape = _html.unescape
_PACKER_RE = re.compile(
    r"eval\(function\(p,a,c,k,e,d\)\{.*?\}\('((?:[^'\\]|\\.)*)',(\d+),(\d+),'(.*?)'\.split\('\|'\),0,\{\}\)\)",
    re.S)


def _to_base(n, base):
    if n <= 0:
        return "0"
    s = ""
    while n > 0:
        s = _B36[n % base] + s
        n //= base
    return s


def _unescape_js_str(s):
    s = s.replace("\\\\", "\x00")
    s = s.replace("\\'", "'").replace('\\"', '"').replace("\\/", "/")
    s = s.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
    return s.replace("\x00", "\\")


def _unpack(js):
    m = _PACKER_RE.search(js)
    if not m:
        return None
    try:
        payload = _unescape_js_str(m.group(1))
        radix, count = int(m.group(2)), int(m.group(3))
        symtab = m.group(4).split("|")
        for i in range(count - 1, -1, -1):
            word = _to_base(i, radix)
            val = symtab[i] if i < len(symtab) else word
            if not val:
                val = word
            payload = re.sub(r"\b" + re.escape(word) + r"\b",
                             lambda _m, v=val: v, payload)
        return payload
    except Exception:
        return None


def _unpack_all(js):
    out = []
    for m in _PACKER_RE.finditer(js):
        try:
            payload = _unescape_js_str(m.group(1))
            radix, count = int(m.group(2)), int(m.group(3))
            symtab = m.group(4).split("|")
            for i in range(count - 1, -1, -1):
                word = _to_base(i, radix)
                val = symtab[i] if i < len(symtab) else word
                if not val:
                    val = word
                payload = re.sub(r"\b" + re.escape(word) + r"\b",
                                 lambda _m, v=val: v, payload)
            out.append(payload)
        except Exception:
            continue
    return out


def _gf_mul(a, b):
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return p


def _gf_pow(a, e):
    r = 1
    while e:
        if e & 1:
            r = _gf_mul(r, a)
        a = _gf_mul(a, a)
        e >>= 1
    return r


def _rotl8(x, n):
    return ((x << n) | (x >> (8 - n))) & 0xFF


def _aes_sbox():
    sb = []
    for i in range(256):
        inv = _gf_pow(i, 254) if i else 0
        y = (inv ^ _rotl8(inv, 1) ^ _rotl8(inv, 2)
             ^ _rotl8(inv, 3) ^ _rotl8(inv, 4) ^ 0x63) & 0xFF
        sb.append(y)
    return sb


_AES_SBOX = _aes_sbox()
_AES_INV_SBOX = [0] * 256
for _si, _sv in enumerate(_AES_SBOX):
    _AES_INV_SBOX[_sv] = _si
_AES_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]
_DEC_M9 = [_gf_mul(a, 0x09) for a in range(256)]
_DEC_MB = [_gf_mul(a, 0x0B) for a in range(256)]
_DEC_MD = [_gf_mul(a, 0x0D) for a in range(256)]
_DEC_ME = [_gf_mul(a, 0x0E) for a in range(256)]

_JAVA_OK = None


def _java_ok():
    global _JAVA_OK
    if _JAVA_OK is None:
        try:
            from java import jclass
            _JAVA_OK = True
        except Exception:
            _JAVA_OK = False
    return _JAVA_OK


def _java_decrypt(data, key, iv):
    from java import jclass
    Cipher = jclass("javax.crypto.Cipher")
    SecretKeySpec = jclass("javax.crypto.spec.SecretKeySpec")
    IvParameterSpec = jclass("javax.crypto.spec.IvParameterSpec")
    c = Cipher.getInstance("AES/CBC/NoPadding")
    c.init(2, SecretKeySpec(key, "AES"), IvParameterSpec(iv))
    return bytes(c.doFinal(data))


def _key_expand(key):
    w = [list(key[i:i + 4]) for i in range(0, 16, 4)]
    for i in range(4, 44):
        t = list(w[i - 1])
        if i % 4 == 0:
            t = t[1:] + t[:1]
            t = [_AES_SBOX[b] for b in t]
            t[0] ^= _AES_RCON[i // 4 - 1]
        w.append([a ^ b for a, b in zip(w[i - 4], t)])
    rks = []
    for r in range(11):
        rk = []
        for c in range(4):
            rk.extend(w[r * 4 + c])
        rks.append(bytes(rk))
    return rks


def _dec_block(block16, rks):
    s = [b ^ k for b, k in zip(block16, rks[10])]
    for rnd in range(9, 0, -1):
        t = [0] * 16
        for rr in range(4):
            for cc in range(4):
                t[rr + 4 * cc] = s[rr + 4 * ((cc - rr) % 4)]
        s = [_AES_INV_SBOX[b] ^ k for b, k in zip(t, rks[rnd])]
        u = [0] * 16
        for cc in range(4):
            a0, a1, a2, a3 = s[cc * 4:cc * 4 + 4]
            u[cc * 4] = _DEC_ME[a0] ^ _DEC_MB[a1] ^ _DEC_MD[a2] ^ _DEC_M9[a3]
            u[cc * 4 + 1] = _DEC_M9[a0] ^ _DEC_ME[a1] ^ _DEC_MB[a2] ^ _DEC_MD[a3]
            u[cc * 4 + 2] = _DEC_MD[a0] ^ _DEC_M9[a1] ^ _DEC_ME[a2] ^ _DEC_MB[a3]
            u[cc * 4 + 3] = _DEC_MB[a0] ^ _DEC_MD[a1] ^ _DEC_M9[a2] ^ _DEC_ME[a3]
        s = u
    t = [0] * 16
    for rr in range(4):
        for cc in range(4):
            t[rr + 4 * cc] = s[rr + 4 * ((cc - rr) % 4)]
    return bytes([_AES_INV_SBOX[b] ^ k for b, k in zip(t, rks[0])])


def _aes_cbc(data, key, iv):
    if _java_ok():
        try:
            return _java_decrypt(data, key, iv)
        except Exception:
            pass
    rks = _key_expand(key)
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        blk = _dec_block(data[i:i + 16], rks)
        out.extend(b ^ p for b, p in zip(blk, prev))
        prev = data[i:i + 16]
    return bytes(out)


def _gunzip(data):
    if not data or len(data) < 2 or data[:2] != b"\x1f\x8b":
        return data
    try:
        return gzip.decompress(data)
    except Exception:
        pass
    try:
        return zlib.decompress(data, 16 + zlib.MAX_WBITS)
    except Exception:
        return data


def _img_mime(data):
    if not data or len(data) < 4:
        return ""
    data = _gunzip(data)
    n = len(data)
    if n >= 3 and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if n >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if n >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if n >= 6 and data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if n >= 2 and data[:2] == b"BM":
        return "image/bmp"
    if n >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"avif", b"avis"):
            return "image/avif"
        if brand in (b"heic", b"heif", b"mif1"):
            return "image/heic" if brand == b"heic" else "image/heif"
        if b"avif" in data[8:64] or b"avis" in data[8:64]:
            return "image/avif"
        if b"heic" in data[8:64] or b"heif" in data[8:64]:
            return "image/heif"
    return ""


def _blank_png(w=300, h=450, rgb=(0x1c, 0x1c, 0x22)):
    import struct
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))
    cx, cy = w // 2, h // 2
    tri_h, tri_w = 70, 56
    raw = b""
    for y in range(h):
        raw += b"\x00"
        for x in range(w):
            on = ((x >> 3) + (y >> 3)) & 1
            r, g, b = rgb
            if on:
                r, g, b = min(255, r + 16), min(255, g + 16), min(255, b + 18)
            dy = abs(y - cy)
            if dy <= tri_h // 2:
                half = int((1 - dy / (tri_h // 2)) * tri_w)
                if cx - tri_w // 3 <= x <= cx - tri_w // 3 + half:
                    r, g, b = 200, 200, 210
            raw += bytes((r, g, b))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


_BLANK = None


def _blank():
    global _BLANK
    if _BLANK is None:
        try:
            _BLANK = _blank_png()
        except Exception:
            _BLANK = b""
    return _BLANK


_DEC_CACHE = {}
_DEC_CACHE_ORDER = []
_DEC_CACHE_MAX = 256


def _decrypt_cached(url, data):
    if url:
        hit = _DEC_CACHE.get(url)
        if hit:
            return hit
    out = _decrypt_cover(data)
    if not url or not _img_mime(out):
        return out
    if len(_DEC_CACHE_ORDER) >= _DEC_CACHE_MAX:
        try:
            _DEC_CACHE.pop(_DEC_CACHE_ORDER.pop(0), None)
        except Exception:
            pass
    _DEC_CACHE[url] = out
    _DEC_CACHE_ORDER.append(url)
    return out


def _decrypt_cover(data):
    if not data or _img_mime(data):
        return data
    candidates = [data]
    if len(data) % 16:
        candidates.append(data + b"\x00" * (16 - len(data) % 16))
    if len(data) > 16 and len(data) % 16 == 0:
        candidates.append(data[16:])
    for c in candidates:
        if len(c) >= 16 and len(c) % 16 == 0:
            try:
                pt = _aes_cbc(c, _AES_KEY, _AES_IV)
                if _img_mime(pt):
                    return pt
            except Exception:
                continue
    return data


class Spider(BaseSpider):

    def __init__(self):
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self._good_host = None
        self._cache = {}
        self._cache_time = {}

    def init(self, extend=""):
        cfg = {}
        if isinstance(extend, dict):
            cfg = extend
        elif extend:
            try:
                cfg = json.loads(extend)
            except Exception:
                cfg = {}
        site = (cfg.get("site") or cfg.get("url") or "").strip().rstrip("/")
        if site:
            self.hosts = [site] + [h for h in self.hosts if h != site]
            self.host = self.hosts[0]

    def getDependence(self):
        return []

    def action(self, action):
        if action == "toast":
            return {"msg": "玩物社区源已加载"}
        return {"msg": "不支持此操作"}

    def destroy(self):
        self._cache.clear()
        self._cache_time.clear()

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", str(url)))

    def manualVideoCheck(self):
        return True

    def homeContent(self, filter):
        result = {"class": [{"type_id": tid, "type_name": nm}
                            for tid, nm in CLASSES]}
        if filter:
            result["filters"] = self._filters()
        return result

    def _filters(self):
        return {
            "new": [{
                "key": "order", "name": "排序", "init": "new",
                "value": [{"n": nm, "v": tid} for tid, nm in SORTS],
            }]
        }

    def homeVideoContent(self):
        items = self._fetch_list("new", 1, {})
        return {"list": items}

    def _cat_path(self, tid):
        if tid == "moviesets":
            return "/moviesets/"
        if tid in AI_TIDS:
            return "/ai/%s/" % tid
        return "/videos/%s/" % tid

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        extend = extend or {}
        if tid.startswith("actor/") or tid.startswith("director/") or tid.startswith("tag/"):
            name = unquote(tid.split("/", 1)[1])
            items = self._fetch_search(name, pg)
            return self._page(items, pg)
        if tid == "new":
            order = extend.get("order") or ""
            if order and order in {s[0] for s in SORTS}:
                tid = order
        if tid == "moviesets":
            return self._movieset_list(pg)
        try:
            path = self._cat_path(tid)
            if pg > 1:
                path = path + "page/%d/" % pg
            html = self._get_html(self._host_url(path))
            items = self._parse_video_cards(html)
            has_next = ("/page/%d/" % (pg + 1)) in (html or "")
            return self._page(items, pg, has_next)
        except Exception:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 0, "total": "0"}

    def _movieset_list(self, pg):
        try:
            path = "/moviesets/"
            if pg > 1:
                path = path + "page/%d/" % pg
            html = self._get_html(self._host_url(path))
            items = self._parse_movieset_cards(html)
            has_next = ("/page/%d/" % (pg + 1)) in (html or "")
            return self._page(items, pg, has_next)
        except Exception:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 0, "total": "0"}

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        responses = [self._detail(str(video_id)) for video_id in ids]
        merged = {}
        lst = []
        for r in responses:
            for it in (r.get("list") or []):
                lst.append(it)
        merged["list"] = lst
        return merged

    def _detail(self, vid):
        try:
            if "/moviesets/" in vid and "/vd-" not in vid:
                return self._movieset_detail(vid)
            html = self._get_html(vid)
            if not html:
                return {"list": [], "msg": "未找到此影片"}
            name = (self._rx(r"<title>(.*?)视频在线观看", html)
                    or self._rx(r"<h1[^>]*>(.*?)</h1>", html, re.S))
            pic = (self._rx(r'property="og:image" content="([^"]+)"', html)
                   or self._rx(r'content="([^"]+)"[^>]*property="og:image"', html)
                   or self._rx(r'data-src="(https?://[^"]+\.(?:jpg|jpeg|png|webp|avif|gif|gif))"', html))
            desc = self._rx(r'name="description" content="([^"]+)"', html)
            tags = self._rx_tags(html)
            vod = {
                "vod_id": vid,
                "vod_name": self._clean(name),
                "vod_pic": self._pic_url(pic),
                "vod_remarks": "",
                "vod_year": "",
                "vod_area": "",
                "vod_actor": "、".join(self._clickable("tag", t) for t in tags),
                "vod_content": self._clean(desc),
                "vod_play_from": "正片",
                "vod_play_url": "正片$" + vid,
            }
            return {"list": [vod]}
        except Exception:
            return {"list": []}

    def _movieset_detail(self, url):
        try:
            html = self._get_html(url)
            if not html:
                return {"list": []}
            name = (self._rx(r"<h1[^>]*>(.*?)</h1>", html, re.S)
                    or self._rx(r"<title>(.*?)</title>", html, re.S))
            name = re.sub(r"\s*[|｜\-–—]\s*玩物社区\s*$", "", self._clean(name))
            name = re.sub(r"\s*高清在线观看\s*$", "", name)
            pic = (self._rx(r'property="og:image" content="([^"]+)"', html)
                   or self._rx(r'data-src="(https?://[^"]+\.(?:jpg|jpeg|png|webp|avif|gif|gif))"', html))
            vids = self._parse_video_cards(html)
            eps = "#".join("%s$%s" % (self._safe_label(v["vod_name"]), v["vod_id"]) for v in vids)
            vod = {
                "vod_id": url,
                "vod_name": name,
                "vod_pic": self._pic_url(pic),
                "vod_play_from": "合集选集",
                "vod_play_url": eps,
            }
            return {"list": [vod]}
        except Exception:
            return {"list": []}

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        items = self._fetch_search(str(key or "").strip(), pg)
        return self._page(items, pg, self._search_has_next(str(key or "").strip(), pg))

    def _search_has_next(self, kw, pg):
        try:
            path = "/videos/search/%s/" % quote(kw, safe="")
            if pg > 1:
                path = path + "page/%d/" % pg
            html = self._get_html(self._host_url(path))
            return ("/page/%d/" % (pg + 1)) in (html or "")
        except Exception:
            return False

    def _fetch_search(self, keyword, pg):
        path = "/videos/search/%s/" % quote(keyword, safe="")
        if pg > 1:
            path = path + "page/%d/" % pg
        html = self._get_html(self._host_url(path))
        return self._parse_video_cards(html)

    def _fetch_list(self, tid, pg, extend):
        try:
            path = self._cat_path(tid)
            if pg > 1:
                path = path + "page/%d/" % pg
            html = self._get_html(self._host_url(path))
            return self._parse_video_cards(html)
        except Exception:
            return []

    def playerContent(self, flag, id, vipFlags):
        try:
            m3u8 = self._get_m3u8(str(id or ""))
            if not m3u8:
                return {"parse": 0, "msg": "无法获取播放地址"}
            return {"parse": 0, "jx": 0, "url": m3u8,
                    "header": self._string_map({"User-Agent": UA})}
        except Exception:
            return {"parse": 0, "msg": "无法获取播放地址"}

    def _get_m3u8(self, detail_url):
        html = ""
        last = ""
        for u in self._expand(detail_url):
            html = self._get_html(u)
            if html:
                last = u
                break
        if not html:
            return ""
        dp_url = None
        m = re.search(r"/videos/detail_play\?[^\"'\s<>]+", html)
        if m:
            dp_url = urljoin(last, _unescape(m.group(0)))
        else:
            for packed in _unpack_all(html):
                if "detail_play" in packed:
                    dp_url = self._build_detail_play(packed, last)
                    if dp_url:
                        break
        if not dp_url:
            return ""
        r2 = self._get_html(dp_url)
        if not r2:
            return ""
        unpacked = (_unpack(r2) or r2).replace('\\"', '"')
        m3 = re.search(r'data-url="([^"]+)"', unpacked)
        if not m3:
            return ""
        return _unescape(m3.group(1)).replace("&amp;", "&")

    def _build_detail_play(self, packed, page_url):
        def rx(p):
            m = re.search(p, packed)
            return m.group(1) if m else ""
        vid = rx(r"[?&]id=(\d+)")
        img = rx(r"[?&]img=([^\"&]+)")
        ads = rx(r"[?&]ads=([^\"&]+)")
        tok = rx(r'encodeURIComponent\("([^"]+)"\)')
        if not (vid and tok):
            return ""
        t = str(int(time.time()) // 1800)
        origin = "%s://%s" % (urlparse(page_url).scheme or "https",
                              urlparse(page_url).netloc)
        return ("%s/videos/detail_play?id=%s&img=%s&ads=%s&u=%s&t=%s"
                % (origin, vid, img, ads, quote(tok, safe=""), t))


    def proxy(self, params):
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                return [404, "text/plain", ""]
        if not isinstance(params, dict):
            return [404, "text/plain", ""]
        url = params.get("url") or params.get("u") or ""
        if not url:
            return [404, "text/plain", ""]
        url = self._d64(url)
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            url = self._fix_url(url)
        if not url.startswith("http"):
            return [404, "text/plain", ""]
        img = _decrypt_cached(url, self._download_img(url))
        if not _img_mime(img):
            img = _decrypt_cached(url, self._download_img(self._weserv(url)))
        mime = _img_mime(img)
        if not mime:
            return [200, "image/png", self._img_stream(_blank()), {}]
        return [200, mime, self._img_stream(img), {}]

    localProxy = proxy

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

    def _download_img(self, url):
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
        return self._urllib_bytes(url)

    def _weserv(self, url):
        u = re.sub(r"^https?://", "", url)
        return "https://images.weserv.nl/?url=" + quote(u, safe="")

    def _urllib_bytes(self, url, timeout=18):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception:
            return b""

    @staticmethod
    def _d64(s):
        try:
            out = base64.b64decode(unquote(str(s))).decode("utf-8")
            if out.startswith("http"):
                return out
        except Exception:
            pass
        return str(s)

    def _pic_url(self, u):
        u = self._fix_url(u)
        if not u:
            return ""
        enc = quote(base64.b64encode(u.encode()), safe="")
        if hasattr(self, "proxyUrl"):
            try:
                p = self.proxyUrl({"type": "pic", "url": enc})
                if p:
                    return p
            except Exception:
                pass
        try:
            proxy = self.getProxyUrl()
            if proxy:
                sep = "&" if "?" in proxy else "?"
                key = getattr(self, "siteKey", "") or ""
                extra = ("&siteKey=%s" % key) if (key and "siteKey=" not in proxy) else ""
                return "%s%stype=pic&url=%s%s" % (proxy, sep, enc, extra)
        except Exception:
            pass
        return u

    def _parse_video_cards(self, html):
        vods, seen = [], set()
        if not html:
            return vods
        for m in re.finditer(r'href="(/videos/(?!cate/)[^"?]*?/vd-[A-Za-z0-9\-]+/)"', html):
            try:
                href = m.group(1)
                if href in seen:
                    continue
                seen.add(href)
                seg = html[m.start():m.start() + 8000]
                pic = (self._rx(r'data-src="(https?://[^"]+)"', seg)
                       or self._rx(r'data-original="(https?://[^"]+)"', seg)
                       or self._rx(r'data-lazy-src="(https?://[^"]+)"', seg)
                       or self._rx(r'src="((?:https?://|/)[^"]+\.(?:jpg|jpeg|png|webp|avif|gif))"', seg))
                name = self._clean(self._rx(r"<h[23][^>]*>(.*?)</h[23]>", seg, re.S))
                if not name:
                    name = self._clean(self._rx(r'<a[^>]*class="[^"]*line-clamp[^"]*"[^>]*>([^<]{1,200})</a>', seg))
                if not name:
                    name = self._clean(self._rx(r'<img[^>]*alt="([^"]{1,200})"', seg))
                remark = self._rx(r">(\d{1,3}:\d{2}(?::\d{2})?)<", seg)
                if not name:
                    continue
                vods.append({
                    "vod_id": self._fix_url(href),
                    "vod_name": name,
                    "vod_pic": self._pic_url(pic),
                    "vod_remarks": remark,
                })
            except Exception:
                continue
        return vods

    def _parse_movieset_cards(self, html):
        vods, seen = [], set()
        if not html:
            return vods
        for m in re.finditer(r'<li>\s*<a[^>]*href="(/moviesets/[A-Za-z0-9\-]+/)"(.*?)</li>', html, re.S):
            try:
                href = m.group(1)
                if href in seen:
                    continue
                seen.add(href)
                seg = m.group(2)
                if "data-src" not in seg and "<h2" not in seg and "<h3" not in seg:
                    continue
                pic = (self._rx(r'data-src="(https?://[^"]+)"', seg)
                       or self._rx(r'data-original="(https?://[^"]+)"', seg)
                       or self._rx(r'src="((?:https?://|/)[^"]+\.(?:jpg|jpeg|png|webp|avif|gif))"', seg))
                name = self._clean(self._rx(r"<h[23][^>]*>(.*?)</h[23]>", seg, re.S))
                remark = self._clean(self._rx(r">(\d+部)<", seg))
                if not name:
                    continue
                vods.append({
                    "vod_id": self._fix_url(href),
                    "vod_name": name,
                    "vod_pic": self._pic_url(pic),
                    "vod_remarks": remark,
                })
            except Exception:
                continue
        return vods

    def _rx_tags(self, html):
        tags, seen = [], set()
        for _u, t in re.findall(r'href="(/videos/search/[^"]+)"[^>]*>\s*(?:<[^>]+>)*([^<]{1,20})', html):
            t = self._clean(t)
            if t and t not in seen and not t.isdigit():
                seen.add(t)
                tags.append(t)
            if len(tags) >= 12:
                break
        return tags

    def _clickable(self, kind, name):
        if not name:
            return ""
        ident = "%s/%s" % (kind, quote(name, safe=''))
        payload = json.dumps({"id": ident, "name": name, "type_flag": "0"},
                             ensure_ascii=False, separators=(",", ":"))
        return "[a=cr:%s/]%s[/a]" % (payload, name)

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

    @staticmethod
    def _clean(s):
        if not s:
            return ""
        s = re.sub(r"<[^>]+>", "", s)
        return _html.unescape(s).strip()

    @staticmethod
    def _safe_label(text):
        return str(text or "").replace("$", "＄").replace("#", "＃").strip()

    @staticmethod
    def _rx(pattern, text, flags=0):
        m = re.search(pattern, text, flags)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _int(x, d=0):
        try:
            return int(x)
        except Exception:
            return d

    @staticmethod
    def _string_map(value):
        if not isinstance(value, dict):
            return {}
        return {str(k): str(v) for k, v in value.items() if v is not None}

    def _fix_url(self, u):
        if not u:
            return ""
        u = u.strip()
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http"):
            return u
        if u.startswith("/"):
            return self._host_url(u)
        return self._host_url("/" + u)

    def _host_url(self, path):
        h = self._good_host or self.host
        return h.rstrip("/") + path

    def _expand(self, url):
        urls = []
        if url.startswith("http"):
            p = urlparse(url)
            for h in self.hosts:
                netloc = urlparse(h).netloc
                u = p._replace(netloc=netloc).geturl()
                if u not in urls:
                    urls.append(u)
        return urls or [url]

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
            headers = dict(kw.get("headers") or {})
            headers.setdefault("User-Agent", UA)
            headers.setdefault("Accept", "*/*")
            req = urllib.request.Request(url, headers=headers,
                                         method=kw.get("method") or "GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                enc = (resp.headers.get("Content-Encoding") or "").lower()
                if enc == "gzip":
                    raw = gzip.decompress(raw)
                elif enc == "deflate":
                    raw = zlib.decompress(raw)
                return {"code": resp.getcode() or 0,
                        "content": raw.decode("utf-8", "replace"),
                        "headers": dict(resp.headers), "error": None}
        except Exception as e:
            return {"code": 0, "content": "", "headers": {}, "error": str(e)}

    def _get_html(self, url, **kw):
        resp = self._req(url, **kw)
        if resp.get("error"):
            return None
        code = resp.get("code") or 0
        if not 200 <= code < 300:
            return None
        content = resp.get("content", "")
        if isinstance(content, (bytes, bytearray)):
            return content.decode("utf-8", "replace")
        return content
