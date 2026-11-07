# -*- coding: utf-8 -*-
# [91成人短剧¹⁸  更新于:2026-11-05 03:50]
import json
import re
import time
import base64
import threading
import urllib.request
import urllib.parse
from urllib.parse import quote, unquote

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        def proxy(self, params):
            return [404, "text/plain", ""]
        def localProxy(self, params):
            return [404, "text/plain", ""]

try:
    from Crypto.Cipher import AES as _AES
    _CRYPTO = "crypto"
except Exception:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        _CRYPTO = "cryptography"
    except Exception:
        _CRYPTO = "py"

NAME = "91成人短剧"
HOSTS = ["https://91crdjai.com"]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PAGE_SIZE = 22
CATS = [("duanju", "成人短剧"), ("manju", "成人漫剧"), ("zhenrenju", "真人剧"), ("shipin", "成人视频"), ("paihang", "热播榜")]
MEDIA_KEY = b"f5d965df75336270"
MEDIA_IV = b"97b60394abc2fbe1"

_SBOX = bytes.fromhex(
"637c777bf26b6fc53001672bfed7ab76ca82c97dfa5947f0add4a2af9ca472c0"
"b7fd9326363ff7cc34a5e5f171d8311504c723c31896059a071280e2eb27b275"
"09832c1a1b6e5aa0523bd6b329e32f8453d100ed20fcb15b6acbbe394a4c58cf"
"d0efaafb434d338545f9027f503c9fa851a3408f929d38f5bcb6da2110fff3d2"
"cd0c13ec5f974417c4a77e3d645d197360814fdc222a908846eeb814de5e0bdb"
"e0323a0a4906245cc2d3ac629195e479e7c8376d8dd54ea96c56f4ea657aae08"
"ba78252e1ca6b4c6e8dd741f4bbd8b8a703eb5664803f60e613557b986c11d9e"
"e1f8981169d98e949b1e87e9ce5528df8ca1890dbfe6426841992d0fb054bb16")
_INV = [0] * 256
for _i, _b in enumerate(_SBOX):
    _INV[_b] = _i
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36]

def _xt(a):
    return ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else (a << 1)

def _mul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _xt(a)
        b >>= 1
    return r

def _expand(key):
    nk, nr = 4, 10
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [_SBOX[x] for x in t]
            t[0] ^= _RCON[i // nk - 1]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    return [sum(w[4 * r:4 * r + 4], []) for r in range(nr + 1)]

def _dec_block(blk, rk, nr):
    s = [blk[i] ^ rk[nr][i] for i in range(16)]
    for r in range(nr - 1, -1, -1):
        s = [s[0], s[13], s[10], s[7], s[4], s[1], s[14], s[11],
             s[8], s[5], s[2], s[15], s[12], s[9], s[6], s[3]]
        s = [_INV[x] for x in s]
        s = [s[i] ^ rk[r][i] for i in range(16)]
        if r:
            ns = [0] * 16
            for c in range(4):
                a = s[4 * c:4 * c + 4]
                ns[4 * c + 0] = _mul(a[0], 14) ^ _mul(a[1], 11) ^ _mul(a[2], 13) ^ _mul(a[3], 9)
                ns[4 * c + 1] = _mul(a[0], 9) ^ _mul(a[1], 14) ^ _mul(a[2], 11) ^ _mul(a[3], 13)
                ns[4 * c + 2] = _mul(a[0], 13) ^ _mul(a[1], 9) ^ _mul(a[2], 14) ^ _mul(a[3], 11)
                ns[4 * c + 3] = _mul(a[0], 11) ^ _mul(a[1], 13) ^ _mul(a[2], 9) ^ _mul(a[3], 14)
            s = ns
    return bytes(s)

def _py_cbc_dec(key, iv, data):
    rk = _expand(key)
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        blk = data[i:i + 16]
        p = _dec_block(blk, rk, 10)
        out += bytes(a ^ b for a, b in zip(p, prev))
        prev = blk
    return bytes(out)


class Spider(BaseSpider):

    def __init__(self):
        self.name = NAME
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self._cache = {}
        self._cache_time = {}
        self._lock = threading.Lock()
        self._options = {}

    def init(self, extend=""):
        cfg = {}
        if isinstance(extend, dict):
            cfg = extend
        elif extend:
            try:
                cfg = json.loads(extend)
            except Exception:
                cfg = {}
        if not isinstance(cfg, dict):
            cfg = {}
        self._options = cfg
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
        self._options = {}

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", str(url)))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {"msg": "不支持此操作"}

    def homeContent(self, filter):
        result = {"class": self._classes()}
        result["list"] = [self._vod(x) for x in self._home_items()]
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        tid = str(tid or "")
        if tid.startswith("tag/") or tid.startswith("actor/") or tid.startswith("director/"):
            kw = unquote(tid.split("/", 1)[1])
            items = self._fetch_search(kw)
            return self._page_items(items, pg)
        items, pc = self._fetch_list(tid, pg)
        return self._page_items(items, pg, pc)

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        responses = [self._detail(str(v)) for v in ids]
        merged = {k: v for k, v in (responses[0] or {}).items() if k != "list"}
        merged["list"] = [it for r in responses for it in (r.get("list") or [])]
        return merged

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        items = self._fetch_search(str(key or "").strip())
        return self._page_items(items, pg)

    def playerContent(self, flag, id, vipFlags):
        url = self._fetch_play(str(id or ""))
        if not url:
            return {"parse": 0, "msg": "无法获取播放地址"}
        return {"parse": 0, "jx": 0, "url": url, "header": {}}

    def liveContent(self, url):
        return "[]"

    def _classes(self):
        return [{"type_id": c[0], "type_name": c[1]} for c in CATS]

    def _home_items(self):
        html = self._get_html(self.host + "/")
        return self._parse_cards(html)

    def _fetch_list(self, tid, pg):
        base = self.host.rstrip("/") + "/" + str(tid).strip("/")
        url = base + "/" if pg <= 1 else base + "/page/" + str(pg) + "/"
        html = self._get_html(url)
        items = self._parse_cards(html)
        pc = 0
        if html:
            m = re.search(r'pages="(\d+)"', html)
            if m:
                pc = int(m.group(1))
        return items, pc

    def _fetch_search(self, kw):
        url = self.host.rstrip("/") + "/search/?q=" + quote(str(kw or "").strip())
        html = self._get_html(url)
        return self._parse_cards(html)

    def _detail(self, vid):
        url = self.host.rstrip("/") + "/" + str(vid).lstrip("/")
        html = self._get_html(url)
        if not html:
            return {"list": [], "msg": "未找到此影片"}
        data = self._parse_detail(html, str(vid))
        if not data:
            return {"list": [], "msg": "未找到此影片"}
        eps = data.get("eps") or []
        play_parts = []
        for i, (label, rel) in enumerate(eps, 1):
            abs_url = self._abs_url(rel)
            if not abs_url:
                continue
            name = "第%s集" % (label if re.fullmatch(r"\d+", str(label)) else str(i))
            name = self._safe_label(name)
            play_parts.append("%s$%s" % (name, abs_url))
        if not play_parts:
            url0 = self._abs_url(str(data.get("url") or ""))
            if url0:
                play_parts.append("正片$%s" % url0)
        tags = data.get("tags") or []
        tag_bb = "".join(self._clickable("tag", t) for t in tags)
        content = data.get("desc") or ""
        if tag_bb:
            content = "标签：" + tag_bb + ("\n\n" + content if content else "")
        vod = {
            "vod_id": str(vid),
            "vod_name": data.get("name") or str(vid),
            "vod_pic": self._pic_url(data.get("pic") or ""),
            "type_name": data.get("category") or "",
            "vod_year": str(data.get("year") or ""),
            "vod_remarks": data.get("status") or "",
            "vod_director": "",
            "vod_actor": "",
            "vod_content": content,
            "vod_play_from": "正片",
            "vod_play_url": "#".join(play_parts),
        }
        return {"list": [vod]}

    def _parse_detail(self, html, vid):
        title = ""
        m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
        if m:
            title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        pic = ""
        m = re.search(r'<img[^>]*class="p-img"[^>]*data-src="([^"]+)"', html)
        if m:
            pic = m.group(1).strip()
        desc = ""
        m = re.search(r'<p[^>]*id="viBody"[^>]*>(.*?)</p>', html, re.S)
        if m:
            desc = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            desc = re.sub(r"《[^》]+》共\s*\d+\s*集.*$", "", desc).strip()
        meta = {}
        for m in re.finditer(r"<div><dt>([^<]+)</dt><dd>(.*?)</dd></div>", html, re.S):
            meta[m.group(1).strip()] = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        tags = []
        tm = re.search(r'<div class="d-tags">(.*?)</div>', html, re.S)
        if tm:
            tags = re.findall(r"<a[^>]*>([^<]+)</a>", tm.group(1))
        tags = [t.strip() for t in tags if t.strip()]
        eps = []
        em = re.search(r'<div class="ep-grid">(.*?)</div>', html, re.S)
        if em:
            for x in re.finditer(r'href="(/[^"]+)"[^>]*>([^<]*)</a>', em.group(1)):
                eps.append((x.group(2).strip(), x.group(1)))
        if not eps:
            m = re.search(r'"numberOfEpisodes":(\d+)', html)
            if m:
                n = int(m.group(1))
                base = str(vid).strip("/")
                for i in range(1, n + 1):
                    eps.append((str(i), "/" + base + "/" + str(i) + "/"))
        return {
            "name": title,
            "pic": pic,
            "desc": desc,
            "category": meta.get("分类", ""),
            "status": meta.get("状态", ""),
            "year": (meta.get("发布") or "")[:4],
            "tags": tags,
            "eps": eps,
        }

    def _fetch_play(self, url):
        if not url:
            return ""
        if not url.startswith("http"):
            url = self.host.rstrip("/") + "/" + url.lstrip("/")
        html = self._get_html(url)
        if not html:
            return ""
        for m in re.finditer(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', html, re.S):
            try:
                d = json.loads(m.group(1))
            except Exception:
                continue
            if isinstance(d, dict) and "current" in d:
                cur = d.get("current") or {}
                src = cur.get("src") or ""
                if src:
                    return str(src)
        return ""

    def _parse_cards(self, html):
        items = []
        if not html:
            return items
        for m in re.finditer(r'<a class="card" href="(/[^"]+)"[^>]*>(.*?)</a>', html, re.S):
            href, inner = m.group(1), m.group(2)
            vid = href.strip("/")
            if not vid or "/" not in vid:
                continue
            img = re.search(r'data-src="([^"]+)"', inner)
            t = re.search(r"<h3>([^<]+)</h3>", inner)
            rem = re.search(r'<span class="eps-flag">([^<]+)</span>', inner)
            title = t.group(1).strip() if t else ""
            if not title:
                alt = re.search(r'alt="([^"]+)"', inner)
                title = alt.group(1).strip() if alt else vid
            items.append({
                "vid": vid,
                "name": title,
                "pic": img.group(1).strip() if img else "",
                "remarks": rem.group(1).strip() if rem else "",
            })
        return items

    def _page_items(self, items, pg, pc=0):
        try:
            page = max(1, int(pg))
        except (TypeError, ValueError):
            page = 1
        if not pc:
            pc = page if len(items) < PAGE_SIZE else 9999
        return {
            "list": [self._vod(x) for x in items],
            "page": page,
            "pagecount": pc,
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def _vod(self, item):
        return {
            "vod_id": item.get("vid") or "",
            "vod_name": item.get("name") or "",
            "vod_pic": self._pic_url(item.get("pic") or ""),
            "vod_remarks": item.get("remarks") or "",
        }

    @staticmethod
    def _safe_label(text):
        return str(text or "").replace("$", "＄").replace("#", "＃").strip()

    def _abs_url(self, u):
        u = str(u or "")
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http"):
            return u
        if u.startswith("/"):
            return self.host.rstrip("/") + u
        return self.host.rstrip("/") + "/" + u

    def _int(self, x, d=0):
        try:
            return int(x)
        except Exception:
            return d

    @staticmethod
    def _clickable(kind, name):
        if not name:
            return ""
        ident = "%s/%s" % (kind, quote(name, safe=""))
        payload = json.dumps({"id": ident, "name": name, "type_flag": "0"},
                             ensure_ascii=False, separators=(",", ":"))
        return "[a=cr:%s/]%s[/a]" % (payload, name)

    def _req(self, url, timeout=15000):
        net = getattr(self, "net", None)
        if net is not None:
            try:
                return net.req(url, {"timeout": timeout}) or {}
            except Exception:
                return {}
        return self._req_urllib(url, timeout)

    def _req_urllib(self, url, timeout=15000):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout / 1000.0) as resp:
                return {"code": resp.getcode() or 0, "content": resp.read().decode("utf-8", "replace"),
                        "headers": dict(resp.headers), "error": None}
        except Exception as e:
            return {"code": 0, "content": "", "headers": {}, "error": str(e)}

    def _get_html(self, url):
        resp = self._req(url)
        if not resp or resp.get("error"):
            return None
        code = resp.get("code") or 0
        if not 200 <= code < 300:
            return None
        return resp.get("content", "")

    def _urlopen_bytes(self, url, timeout=15000):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return urllib.request.urlopen(req, timeout=timeout / 1000.0).read()
        except Exception:
            return b""

    @staticmethod
    def _e64(s):
        return base64.urlsafe_b64encode(str(s).encode("utf-8")).decode("ascii")

    @staticmethod
    def _d64(s):
        try:
            return base64.urlsafe_b64decode(str(s).encode("ascii")).decode("utf-8", "replace")
        except Exception:
            return str(s)

    def _proxy_url(self, params):
        if hasattr(self, "proxyUrl"):
            return self.proxyUrl(params, True)
        gp = getattr(self, "getProxyUrl", None)
        if gp is None:
            return ""
        names = []
        try:
            import inspect
            names = list(inspect.signature(gp).parameters.keys())
        except Exception:
            names = ["params", "local"]
        if names and names[0] == "params":
            return gp(params, True)
        base = gp(True)
        if isinstance(params, dict) and params:
            qs = "&".join("%s=%s" % (k, urllib.parse.quote(str(v))) for k, v in params.items())
            return base + ("&" + qs if qs else "")
        return base

    def _pic_url(self, u):
        u = str(u or "")
        if not u:
            return ""
        try:
            return self._proxy_url({"type": "pic", "url": self._e64(u)})
        except Exception:
            return u

    @staticmethod
    def _pic_decrypt(raw):
        if not raw:
            return raw
        if raw[:2] == b"\xff\xd8" or raw[:4] == b"\x89PNG" or raw[:4] == b"RIFF":
            return raw
        if _CRYPTO == "crypto":
            try:
                return _AES.new(MEDIA_KEY, _AES.MODE_CBC, MEDIA_IV).decrypt(raw)
            except Exception:
                return raw
        if _CRYPTO == "cryptography":
            try:
                dec = Cipher(algorithms.AES(MEDIA_KEY), modes.CBC(MEDIA_IV)).decryptor()
                return dec.update(raw) + dec.finalize()
            except Exception:
                return raw
        try:
            return _py_cbc_dec(MEDIA_KEY, MEDIA_IV, raw)
        except Exception:
            return raw

    @staticmethod
    def _mime(img):
        if img[:2] == b"\xff\xd8":
            return "image/jpeg"
        if img[:4] == b"\x89PNG":
            return "image/png"
        if img[:4] == b"RIFF":
            return "image/webp"
        return "image/jpeg"

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
        if params.get("type") != "pic":
            return [404, "text/plain", ""]
        u = self._d64(params.get("url", ""))
        if not u:
            return [404, "text/plain", ""]
        net = getattr(self, "net", None)
        raw = b""
        if net is not None:
            try:
                opts = {"buffer": 3, "headers": {"User-Agent": UA}}
                if hasattr(net, "reqParts"):
                    if hasattr(net, "_native"):
                        raw = net.reqParts(u, opts)[1]
                    else:
                        raw = net.reqParts(u, json.dumps(opts))[1]
                elif hasattr(net, "req"):
                    resp = net.req(u, opts)
                    raw = resp.get("content", b"") if isinstance(resp, dict) else (resp or b"")
            except Exception:
                raw = b""
        if not raw:
            raw = self._urlopen_bytes(u)
        img = self._pic_decrypt(raw)
        return [200, self._mime(img), self._img_stream(img), {}]

    localProxy = proxy
