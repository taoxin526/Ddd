# coding=utf-8
# [推特APP¹⁸  更新于:2026-11-07 01:35]
import json
import re
import time
import random
import string
import hashlib
import base64
import threading
import gzip
import zlib
import ssl
import urllib.request
from urllib.parse import quote, unquote

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        def proxy(self, params):
            return [404, "text/plain", ""]
        def localProxy(self, params):
            return [404, "text/plain", ""]

NAME = "推特APP"
HS = ["bqeaaxzplt", "pdcqllfomw", "hfbtpixjso", "wcyfhknomg", "alxhzjvean"]
UA = "Mozilla/5.0 (Linux; Android 11; M2012K10C Build/RP1A.200720.011; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/87.0.4280.141 Mobile Safari/537.36;SuiRui/twitter/ver=1.4.4"
PAGE_SIZE = 20
CACHE_TTL = 30
IMG_KEY = "2020-zq3-888"
AES_KEY = base64.b64decode("SmhiR2NpT2lKSVV6STFOaQ==")


class Spider(BaseSpider):

    def __init__(self):
        super().__init__()
        self.name = NAME
        self.host = ""
        self.phost = ""
        self.token = ""
        self.did = ""
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
        self.options = cfg if isinstance(cfg, dict) else {}

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

    def _ensure(self):
        if self.token and self.host:
            return True
        with self._lock:
            if self.token and self.host:
                return True
            did = ""
            try:
                did = self.local.get("twdid") or ""
            except Exception:
                did = ""
            if not did:
                did = hashlib.md5((str(int(time.time() * 1000)) + str(random.randint(1000, 9999))).encode()).hexdigest()
                try:
                    self.local.set("twdid", did)
                except Exception:
                    pass
            self.did = did
            self._dance()
        return bool(self.token and self.host)

    def _dance(self):
        sign, t = self._getsign()
        for idx, suffix in enumerate(HS):
            n = 5 if idx == 0 else 2
            for _ in range(n):
                sub = "".join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(5, 10)))
                dom = "https://%s.%s.work" % (sub, suffix)
                try:
                    h = {"User-Agent": UA, "Accept": "application/json", "deviceid": self.did, "t": t, "s": sign}
                    d = {"deviceId": self.did, "tt": "U", "code": "##X-4m6Goo4zzPi1hF##", "chCode": "tt09"}
                    r = self._req_json(dom + "/api/user/traveler", method="POST", json_body=d, headers=h, timeout=4000)
                    if r and isinstance(r, dict) and r.get("data") and r["data"].get("token"):
                        self.token = r["data"]["token"]
                        self.phost = r["data"].get("imgDomain", "") or ""
                        self.host = dom
                        return True
                except Exception:
                    pass
        return False

    def _getsign(self):
        t = str(int(time.time() * 1000))
        return hashlib.md5(t.encode()).hexdigest(), t

    def _headers(self):
        sign, t = self._getsign()
        return {"User-Agent": UA, "deviceid": self.did, "t": t, "s": sign, "aut": self.token}

    def _api(self, path, cache=True):
        if not self._ensure():
            return {}
        ck = path
        if cache:
            with self._lock:
                hit = self._cache.get(ck)
                if hit and time.time() - self._cache_time.get(ck, 0) < CACHE_TTL:
                    return hit
        j = self._call_api(path)
        if not isinstance(j, dict):
            j = {}
        if j.get("encData"):
            j = self._aes(j["encData"])
        elif j.get("code") not in (None, 200, "200"):
            with self._lock:
                self.token = ""
                self.host = ""
            if self._ensure():
                j = self._call_api(path)
                if isinstance(j, dict) and j.get("encData"):
                    j = self._aes(j["encData"])
        if cache and isinstance(j, (dict, list)):
            with self._lock:
                self._cache[ck] = j
                self._cache_time[ck] = time.time()
        return j

    def _call_api(self, path):
        try:
            j = self._req_json(self.host + path, headers=self._headers(), timeout=12000)
            return j if isinstance(j, dict) else {}
        except Exception:
            return {}

    def homeContent(self, filter):
        classes = [{"type_id": "jx", "type_name": "精选"}]
        try:
            data = self._api("/api/video/classifyList") or {}
            for k in data.get("data", []) or []:
                tid = str(k.get("classifyId", ""))
                nm = k.get("classifyTitle", "")
                if tid and nm:
                    classes.append({"type_id": tid, "type_name": nm})
        except Exception:
            pass
        sort = [{"key": "fl", "name": "分类", "value": [{"n": "最近更新", "v": "1"}, {"n": "最多播放", "v": "2"}, {"n": "好评榜", "v": "3"}]}]
        filters = {c["type_id"]: sort for c in classes if c["type_id"] != "jx"}
        filters["jx"] = [{"key": "type", "name": "精选", "value": [{"n": "日榜", "v": "1"}, {"n": "周榜", "v": "2"}, {"n": "月榜", "v": "3"}, {"n": "总榜", "v": "4"}]}]
        result = {"class": classes}
        if filter:
            result["filters"] = filters
        result["list"] = self._category("jx", "1", {"type": "1"})
        return result

    def homeVideoContent(self):
        return {"list": self._category("jx", "1", {"type": "1"})}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        ext = self._ext(extend)
        tid = str(tid or "")
        if tid.startswith("person/"):
            uid = unquote(tid.split("/", 1)[1])
            items, total = self._person(uid, pg)
            return self._page(items, pg, total)
        if tid.startswith("tag/"):
            name = unquote(tid.replace("tag/", "", 1))
            items = self._search_items(name, pg)
            return self._page(items, pg, None)
        items = self._category(tid, pg, ext)
        return self._page(items, pg, None)

    def _category(self, tid, pg, ext):
        pg = self._int(pg, 1)
        ext = ext or {}
        if tid == "jx":
            data = self._api("/api/video/getRankVideos?pageSize=%d&page=%d&type=%s" % (PAGE_SIZE, pg, ext.get("type", "1")))
            arr = self._list_of(data, "data")
            return [x for x in (self._to_vod(i) for i in arr) if x]
        path = "/api/video/queryVideoByClassifyId?pageSize=%d&page=%d&classifyId=%s&sortType=%s" % (PAGE_SIZE, pg, tid, ext.get("fl", "1"))
        data = self._api(path)
        arr = self._list_of(data, "data")
        return [x for x in (self._to_vod(i) for i in arr) if x]

    def _person(self, uid, pg):
        pg = self._int(pg, 1)
        data = self._api("/api/video/queryPersonVideoByType?pageSize=%d&page=%d&userId=%s" % (PAGE_SIZE, pg, uid))
        arr = self._list_of(data, "data")
        total = None
        if isinstance(data, dict):
            try:
                total = int(data.get("total") or 0)
            except Exception:
                total = None
        return [x for x in (self._to_vod(i, person=True) for i in arr) if x], total

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        items = self._search_items(str(key or ""), pg)
        return self._page(items, pg, None)

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, str(pg or "1"))

    def _search_items(self, key, pg):
        pg = self._int(pg, 1)
        data = self._api("/api/search/keyWord?pageSize=%d&page=%d&searchWord=%s&searchType=1" % (PAGE_SIZE, pg, quote(key)))
        arr = self._list_of(data, "videoList")
        return [x for x in (self._to_vod(i) for i in arr) if x]

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        out = []
        for i in ids:
            v = self._detail(str(i))
            if v:
                out.append(v)
        return {"list": out}

    def _detail(self, raw):
        person = raw.endswith("?p")
        if person:
            raw = raw[:-2]
        parts = raw.split("?")
        if len(parts) < 5:
            return None
        vid, uid, nb, tb, pb = parts[0], parts[1], parts[2], parts[3], parts[4]
        meta = {}
        if len(parts) >= 6 and parts[5]:
            try:
                meta = json.loads(self._b64d(parts[5]))
            except Exception:
                meta = {}
        nick = self._b64d(nb)
        title = self._b64d(tb)
        pic = self._b64d(pb)
        name = (title or nick or vid).replace("$", "＄")
        director = nick
        if uid and not person:
            director = self._clickable("person", uid, nick)
        return {
            "vod_id": raw + ("?p" if person else ""),
            "vod_name": name,
            "vod_pic": self._pic(pic) if pic else "",
            "vod_director": director,
            "vod_actor": "",
            "vod_content": self._content(meta, nick, name),
            "vod_play_from": "正片",
            "vod_play_url": "正片$" + vid,
        }

    def _content(self, meta, nick, name):
        lines = []
        cat = meta.get("cat")
        if cat:
            lines.append("分类：" + str(cat))
        tags = meta.get("tags") or []
        if tags:
            parts = []
            for tg in tags:
                t = str(tg)
                if t:
                    parts.append(self._clickable("tag", t, t))
            if parts:
                lines.append("标签：" + "、".join(parts))
        dur = meta.get("dur")
        if dur:
            lines.append("时长：" + self._dtim(dur))
        views = meta.get("views")
        if views:
            lines.append("播放：" + str(views))
        sub = meta.get("sub")
        if sub:
            lines.append(str(sub))
        if not lines:
            lines.append(name)
        return "\n".join(lines)

    def playerContent(self, flag, id, vipFlags):
        vid = str(id or "")
        if not vid:
            return {"parse": 0, "msg": "无法获取播放地址"}
        if not self._ensure():
            return {"parse": 0, "msg": "无法获取播放地址"}
        data = self._api("/api/video/can/watch?videoId=%s" % vid, cache=False)
        ak = data.get("authKey", "") if isinstance(data, dict) else ""
        vu = data.get("videoUrl", "") if isinstance(data, dict) else ""
        url = ""
        if ak and vu:
            url = self.host + "/api/m3u8/decode/authPath?auth_key=" + ak + "&path=" + vu
        if not url:
            pp = data.get("playPath", "") if isinstance(data, dict) else ""
            url = pp or ""
        if not url:
            return {"parse": 0, "msg": "无法获取播放地址"}
        return {"parse": 0, "jx": 0, "url": url, "header": self._headers(), "format": "application/x-mpegURL"}

    def _to_vod(self, k, person=False):
        k = k or {}
        vid = str(k.get("videoId", ""))
        if not vid:
            return None
        uid = str(k.get("userId", ""))
        nick = str(k.get("nickName", ""))
        title = str(k.get("title") or nick or vid)
        cover = k.get("coverImg") or []
        pic = cover[0] if isinstance(cover, list) and cover else (cover if isinstance(cover, str) else "")
        vod_id = "%s?%s?%s?%s?%s" % (vid, uid, self._b64e(nick), self._b64e(title), self._b64e(pic))
        meta = {}
        if isinstance(k.get("classify"), dict):
            meta["cat"] = str(k["classify"].get("classifyTitle", ""))
        tags = k.get("tagTitles") or []
        if isinstance(tags, list):
            meta["tags"] = [str(x) for x in tags if x]
        if k.get("subtitle"):
            meta["sub"] = str(k["subtitle"])
        if k.get("playTime"):
            meta["dur"] = k["playTime"]
        if k.get("fakeWatchNum"):
            meta["views"] = k["fakeWatchNum"]
        if meta:
            vod_id += "?" + self._b64e(json.dumps(meta, ensure_ascii=False))
        if person:
            vod_id += "?p"
        return {
            "vod_id": vod_id,
            "vod_name": title,
            "vod_pic": self._pic(pic),
            "vod_remarks": self._dtim(k.get("playTime")),
        }

    def _pic(self, u):
        u = (u or "").strip()
        if not u:
            return ""
        if not u.startswith("http"):
            u = (self.phost or "") + u
        return self._proxy_url({"type": "pic", "url": self._e64(u)})

    def _proxy_url(self, params):
        if hasattr(self, "proxyUrl"):
            try:
                return self.proxyUrl(params, True)
            except Exception:
                pass
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
            except Exception:
                pass
        try:
            base = gp(True)
        except Exception:
            base = gp()
        if isinstance(params, dict) and params:
            qs = "&".join("%s=%s" % (k, quote(str(v), safe="")) for k, v in params.items())
            if qs:
                base = base + ("&" if "?" in base else "?") + qs
        return base

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

    def _pic_decrypt(self, raw):
        if not raw:
            return b""
        if raw[:3] == b"\xff\xd8\xff" or raw[:8] == b"\x89PNG\r\n\x1a\n" or raw[:4] == b"RIFF" or raw[:3] == b"GIF":
            return raw
        kb = IMG_KEY.encode("utf-8")
        res = bytearray(raw)
        for i in range(min(100, len(res))):
            res[i] ^= kb[i % len(kb)]
        return bytes(res)

    def _mime(self, data):
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if data[:6] in (b"GIF87a", b"GIF89a"):
            return "image/gif"
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "image/webp"
        return "image/jpeg"

    def proxy(self, params):
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                return [404, "text/plain", ""]
        if not isinstance(params, dict):
            return [404, "text/plain", ""]
        if params.get("type") == "pic":
            url = self._d64(params.get("url", ""))
            if not url:
                return [404, "text/plain", ""]
            raw = self._bytes(url)
            img = self._pic_decrypt(raw)
            if not img:
                return [404, "text/plain", ""]
            return [200, self._mime(img), self._img_stream(img), {}]
        return [404, "text/plain", ""]

    localProxy = proxy

    def _req(self, url, method="GET", headers=None, json_body=None, timeout=15000, buffer=0):
        if not url:
            return None
        h = dict(headers or {})
        h.setdefault("User-Agent", UA)
        net = getattr(self, "net", None)
        if net is not None:
            try:
                opts = {"headers": h, "timeout": timeout, "buffer": buffer}
                if method == "POST":
                    opts["method"] = "POST"
                    opts["postType"] = "json"
                    opts["data"] = json_body
                if hasattr(net, "_native"):
                    options = opts
                else:
                    try:
                        options = json.dumps(opts)
                    except Exception:
                        options = opts
                r = net.req(url, options)
                if isinstance(r, dict):
                    if r.get("error"):
                        return None
                    content = r.get("content", "")
                    if buffer == 3:
                        return content
                    if isinstance(content, bytes):
                        return content.decode("utf-8", "replace")
                    return content
                return r
            except Exception:
                pass
        return self._req_urllib(url, method, h, json_body, timeout, buffer)

    def _req_urllib(self, url, method, headers, json_body, timeout, buffer):
        try:
            data = None
            h = dict(headers or {})
            if method == "POST":
                data = json.dumps(json_body).encode("utf-8")
                h.setdefault("Content-Type", "application/json")
            req = urllib.request.Request(url, data=data, headers=h, method=method)
            with urllib.request.urlopen(req, timeout=timeout / 1000, context=_SSL_CTX) as resp:
                raw = resp.read()
                if buffer == 3:
                    return raw
                enc = (resp.headers.get("Content-Encoding") or "").lower()
                if enc == "gzip":
                    raw = gzip.decompress(raw)
                elif enc == "deflate":
                    raw = zlib.decompress(raw)
                return raw.decode("utf-8", "replace")
        except Exception:
            return None

    def _req_json(self, url, method="GET", json_body=None, headers=None, timeout=12000):
        text = self._req(url, method, headers, json_body, timeout, buffer=0)
        if text is None:
            return None
        if isinstance(text, bytes):
            text = text.decode("utf-8", "replace")
        try:
            return json.loads(text)
        except Exception:
            return None

    def _bytes(self, url, timeout=15000):
        r = self._req(url, "GET", None, None, timeout, buffer=3)
        if isinstance(r, bytes):
            return r
        if isinstance(r, str):
            return r.encode("utf-8", "replace")
        if isinstance(r, (list, tuple)):
            return bytes(r)
        return b""

    def _aes(self, word):
        try:
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import unpad
            c = AES.new(AES_KEY, AES.MODE_CBC, AES_KEY)
            dec = unpad(c.decrypt(base64.b64decode(word)), AES.block_size)
            return json.loads(dec.decode("utf-8"))
        except Exception:
            pass
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.primitives.padding import PKCS7
            dec = Cipher(algorithms.AES(AES_KEY), modes.CBC(AES_KEY)).decryptor()
            data = dec.update(base64.b64decode(word)) + dec.finalize()
            unp = PKCS7(128).unpadder()
            data = unp.update(data) + unp.finalize()
            return json.loads(data.decode("utf-8"))
        except Exception:
            return {}

    def _clickable(self, kind, ident, name=None):
        name = str(name or ident or "").strip()
        ident = str(ident or "").strip()
        if not ident:
            return ""
        enc = quote(ident, safe="")
        return '[a=cr:{"id":"%s/%s","name":"%s"}/]%s[/a]' % (kind, enc, name.replace('"', ""), name)

    def _b64e(self, s):
        try:
            return base64.urlsafe_b64encode(str(s or "").encode("utf-8")).decode("utf-8").rstrip("=")
        except Exception:
            return ""

    def _b64d(self, s):
        try:
            s = str(s or "")
            s += "=" * (-len(s) % 4)
            return base64.urlsafe_b64decode(s).decode("utf-8", "replace")
        except Exception:
            return ""

    def _e64(self, text):
        try:
            return base64.b64encode(text.encode("utf-8")).decode("utf-8")
        except Exception:
            return ""

    def _d64(self, text):
        try:
            text = str(text or "")
            text += "=" * (-len(text) % 4)
            return base64.b64decode(text).decode("utf-8", "replace")
        except Exception:
            return ""

    def _dtim(self, seconds):
        try:
            seconds = int(seconds or 0)
            h = seconds // 3600
            m = seconds % 3600 // 60
            s = seconds % 60
            if h > 0:
                return "%02d:%02d:%02d" % (h, m, s)
            return "%02d:%02d" % (m, s)
        except Exception:
            return ""

    def _int(self, x, d=0):
        try:
            return int(x)
        except Exception:
            return d

    def _ext(self, extend):
        if isinstance(extend, dict):
            return extend
        if isinstance(extend, str):
            try:
                return json.loads(extend)
            except Exception:
                return {}
        return {}

    def _list_of(self, data, key="data"):
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            v = data.get(key)
            if isinstance(v, list):
                return v
            for k in ("list", "items", "records", "videoList", "data"):
                vv = data.get(k)
                if isinstance(vv, list):
                    return vv
        return []

    def _page(self, items, pg, total=None):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        if total:
            try:
                pc = (int(total) + PAGE_SIZE - 1) // PAGE_SIZE
            except Exception:
                pc = 9999
        elif len(items) >= PAGE_SIZE:
            pc = 9999
        else:
            pc = page
        return {"list": items, "page": page, "pagecount": pc, "limit": PAGE_SIZE, "total": 999999}
