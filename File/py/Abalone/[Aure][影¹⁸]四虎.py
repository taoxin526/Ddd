# -*- coding: utf-8 -*-
# [四虎¹⁸  更新于:2026-10-31 21:00]
import json
import re
import time
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

try:
    from Crypto.Cipher import AES as _AES
    from Crypto.Util.Padding import unpad as _unpad
    _HAS_CRYPTO = True
except Exception:
    _HAS_CRYPTO = False


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
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40]


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
    nk, nr = 8, 14
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [_SBOX[x] for x in t]
            t[0] ^= _RCON[i // nk - 1]
        elif i % nk == 4:
            t = [_SBOX[x] for x in t]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    return [sum(w[4 * r:4 * r + 4], []) for r in range(nr + 1)], nr


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
    rk, nr = _expand(key)
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        blk = data[i:i + 16]
        p = _dec_block(blk, rk, nr)
        out += bytes(a ^ b for a, b in zip(p, prev))
        prev = blk
    return bytes(out)


def _py_cbc_enc(key, iv, data):
    rk, nr = _expand(key)
    padn = 16 - (len(data) % 16)
    data = data + bytes([padn]) * padn
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        c = _enc_block(bytes(a ^ b for a, b in zip(data[i:i + 16], prev)), rk, nr)
        out += c
        prev = c
    return bytes(out)


def _enc_block(blk, rk, nr):
    s = [blk[i] ^ rk[0][i] for i in range(16)]
    for r in range(1, nr + 1):
        s = [_SBOX[x] for x in s]
        s = [s[0], s[5], s[10], s[15], s[4], s[9], s[14], s[3],
             s[8], s[13], s[2], s[7], s[12], s[1], s[6], s[11]]
        if r != nr:
            ns = [0] * 16
            for c in range(4):
                a = s[4 * c:4 * c + 4]
                ns[4 * c + 0] = _mul(a[0], 2) ^ _mul(a[1], 3) ^ a[2] ^ a[3]
                ns[4 * c + 1] = a[0] ^ _mul(a[1], 2) ^ _mul(a[2], 3) ^ a[3]
                ns[4 * c + 2] = a[0] ^ a[1] ^ _mul(a[2], 2) ^ _mul(a[3], 3)
                ns[4 * c + 3] = _mul(a[0], 3) ^ a[1] ^ a[2] ^ _mul(a[3], 2)
            s = ns
        s = [s[i] ^ rk[r][i] for i in range(16)]
    return bytes(s)


NAME = "四虎"
JSON_BASE = "https://portal.instruno.com/public2/json"
SITE = "https://www.4hu.tv"
SEARCH_HOST = "https://37cyx4.com"
KEY = b"22946bc50fd63164b79df55070a85a92"
IV = b"kaixin1234567890"
UA = ("Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")
CDN = ["https://m3u8.41cdn.com", "https://m3u8.44cdn.com", "https://m3u8.46cdn.com",
       "https://m3u8.47cdn.com", "https://m3u8.48cdn.com", "https://m3u8.34cdn.com"]
PAGE_SIZE = 28

CAT_BLACKLIST = {"7"}

FALLBACK_CLASS = [
    {"type_id": "142", "type_name": "热门探花"},
    {"type_id": "40", "type_name": "无码中字"},
    {"type_id": "47", "type_name": "欧美系列"},
    {"type_id": "folder/cate/_", "type_name": "\U0001F4C2 高清国产"},
    {"type_id": "folder/actress/_", "type_name": "\U0001F483 热门女优"},
    {"type_id": "folder/movie/_", "type_name": "\U0001F3AC 热门分类"},
]


def _b64u_dec(s):
    s = str(s or "").replace("-", "+").replace("_", "/")
    s += "=" * ((-len(s)) % 4)
    return base64.b64decode(s)


def _b64u_enc(b):
    return base64.b64encode(b).decode().replace("+", "-").replace("/", "_").rstrip("=")


def _aes_dec_text(s):
    raw = _b64u_dec(s)
    if _HAS_CRYPTO:
        pt = _AES.new(KEY, _AES.MODE_CBC, IV).decrypt(raw)
        try:
            pt = _unpad(pt, 16)
        except Exception:
            pass
        return pt.decode("utf-8", "replace")
    pt = _py_cbc_dec(KEY, IV, raw)
    p = pt[-1] if pt else 0
    if 0 < p <= 16:
        pt = pt[:-p]
    return pt.decode("utf-8", "replace")


def _aes_dec_json(s):
    return json.loads(_aes_dec_text(s))


def _aes_enc_b64u(text):
    data = text.encode("utf-8")
    if _HAS_CRYPTO:
        ct = _AES.new(KEY, _AES.MODE_CBC, IV).encrypt(_pad(data, 16))
    else:
        ct = _py_cbc_enc(KEY, IV, data)
    return _b64u_enc(ct)


def _pad(data, bs):
    n = bs - (len(data) % bs)
    return data + bytes([n]) * n


class Spider(BaseSpider):

    def __init__(self):
        try:
            super().__init__()
        except TypeError:
            pass
        self.siteKey = ""
        self._cache = {}

    def getDependence(self):
        return ""

    def getName(self):
        return NAME

    def isVideoFormat(self, url):
        return True

    def isTextFormat(self, url):
        return False

    def destroy(self):
        self._cache = {}

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **kw: None

    def init(self, extend=""):
        self.siteKey = str(self.__dict__.get("siteKey") or "")
        if not self.siteKey and extend:
            try:
                e = extend if isinstance(extend, dict) else json.loads(extend)
                self.siteKey = str(e.get("siteKey") or e.get("site_id") or "")
            except Exception:
                self.siteKey = ""
        self._cache = {}
        return None

    def getProxyUrl(self, params=None, local=True):
        try:
            from com.github.catvod import Proxy as JProxy
            url = JProxy.getUrl(local)
        except Exception:
            url = "http://127.0.0.1:9978/proxy"
        return url + "?do=py" + ("&siteKey=" + quote(self.siteKey) if self.siteKey else "")

    def proxyUrl(self, params=None, local=True):
        return self.getProxyUrl(params, local)

    def _req(self, url, **kw):
        net = self.__dict__.get("net")
        if net is not None:
            try:
                opts = {"timeout": kw.get("timeout", 15000)}
                for k in ("params", "headers", "method", "postType", "data", "body", "buffer",
                          "redirect", "callTimeout", "cookie"):
                    if k in kw and kw[k] is not None:
                        opts[k] = kw[k]
                resp = net.req(url, opts)
                return self._resp_dict(resp)
            except Exception:
                return {}
        return self._req_urllib(url, **kw)

    def _req_urllib(self, url, **kw):
        import urllib.request
        try:
            timeout = (kw.get("timeout") or 15000) / 1000.0
            data = None
            method = (kw.get("method") or "GET").upper()
            params = kw.get("params")
            if params:
                sep = "&" if "?" in url else "?"
                url = url + sep + "&".join("%s=%s" % (k, quote(str(v), safe=""))
                                            for k, v in params.items())
            headers = dict(kw.get("headers") or {})
            headers.setdefault("User-Agent", UA)
            if method == "POST":
                body = kw.get("data") or kw.get("body") or {}
                if isinstance(body, dict):
                    data = "&".join("%s=%s" % (k, quote(str(v), safe=""))
                                    for k, v in body.items()).encode()
                elif isinstance(body, str):
                    data = body.encode()
                else:
                    data = body
                headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                return {"code": resp.getcode() or 0, "content": raw.decode("utf-8", "replace"),
                        "headers": dict(resp.headers), "error": None}
        except Exception as e:
            return {"code": 0, "content": "", "headers": {}, "error": str(e)}

    def _resp_dict(self, resp):
        if isinstance(resp, dict):
            return resp
        if isinstance(resp, str):
            return {"code": 200, "content": resp, "headers": {}, "error": None}
        if isinstance(resp, (bytes, bytearray)):
            return {"code": 200, "content": resp, "headers": {}, "error": None}
        return {"code": 0, "content": "", "headers": {}, "error": str(resp)}

    def _get_text(self, url, timeout=10000):
        resp = self._req(url, timeout=timeout)
        if resp.get("error"):
            return ""
        code = resp.get("code") or 0
        if not 200 <= code < 300:
            return ""
        c = resp.get("content", "")
        if isinstance(c, (bytes, bytearray)):
            return c.decode("utf-8", "replace")
        return str(c)

    def _json(self, path):
        path = str(path or "").lstrip("/")
        cache = self._cache
        if path in cache:
            return cache[path]
        txt = self._get_text(JSON_BASE + "/" + path)
        if not txt:
            return {}
        try:
            j = json.loads(txt)
        except Exception:
            return {}
        if isinstance(j, dict) and "data" in j:
            try:
                j = _aes_dec_json(j["data"])
            except Exception:
                j = {}
        cache[path] = j
        return j

    def _clean(self, s):
        s = str(s or "")
        s = re.sub(r"[\x00-\x1f\x7f]", "", s)
        s = re.sub(r"[$#]", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    @staticmethod
    def _int(x, d=0):
        try:
            return int(str(x).strip())
        except Exception:
            return d

    def _pic(self, url):
        u = str(url or "").strip()
        if not u:
            return ""
        if u.startswith("data:"):
            return u
        if not re.search(r"(?i)\.txt(\?|$)", u):
            return u
        tok = _b64u_enc(u.encode("utf-8"))
        return "%s&type=pic&url=%s" % (self.getProxyUrl(), tok)

    def _img_stream(self, data):
        net = self.__dict__.get("net")
        if net is not None and hasattr(net, "stream"):
            try:
                def _gen():
                    yield data
                return net.stream(_gen())["stream"]
            except Exception:
                pass
        return data

    def _vod(self, it):
        vid = str(it.get("id") or "")
        if not vid:
            return None
        ts = self._int(it.get("newstime"), 0)
        date = time.strftime("%Y-%m-%d", time.localtime(ts)) if ts else ""
        year = time.strftime("%Y", time.localtime(ts)) if ts else ""
        return {
            "vod_id": vid,
            "vod_name": self._clean(it.get("title")),
            "vod_pic": self._pic(it.get("titlepic")),
            "vod_year": year,
            "vod_area": self._clean(it.get("category_name") or it.get("classname") or ""),
            "vod_remarks": date,
            "vod_tag": "",
        }

    def _vods(self, arr):
        out = []
        seen = set()
        for it in (arr or []):
            if not isinstance(it, dict):
                continue
            v = self._vod(it)
            if v and v["vod_id"] not in seen:
                seen.add(v["vod_id"])
                out.append(v)
        return out

    def _fill_pics(self, items, cap=20):
        pending = []
        for it in (items or []):
            if not isinstance(it, dict):
                continue
            if str(it.get("titlepic") or "").strip():
                continue
            vid = str(it.get("id") or "")
            if vid and len(pending) < cap:
                pending.append((it, vid))
        for it, vid in pending:
            try:
                d = self._json("/video/%s.json" % vid)
                if isinstance(d, dict):
                    tp = str(d.get("titlepic") or "").strip()
                    if tp:
                        it["titlepic"] = tp
            except Exception:
                pass
        return items

    def _cats(self):
        self._folder_lists = {}
        try:
            o = self._json("/category-list.json")
            if isinstance(o, dict):
                o = o.get("data") or o.get("list") or []
            FLAT_IDS = ["142", "40", "47"]
            flat_names = {}
            for top in (o or []):
                if not isinstance(top, dict):
                    continue
                if top.get("tbname") != "movie":
                    continue
                tempid = int(top.get("listtempid") or 0)
                gid = str(top.get("classid") or "")
                if tempid == 13:
                    ft = "actress"
                elif tempid == 9:
                    ft = "cate" if gid == "1" else "movie"
                else:
                    continue
                items = []
                for it in (top.get("items") or []):
                    if not isinstance(it, dict):
                        continue
                    if it.get("tbname") != "movie":
                        continue
                    icid = str(it.get("classid") or "")
                    iname = str(it.get("classname") or "")
                    if not icid or icid in CAT_BLACKLIST:
                        continue
                    if icid in FLAT_IDS:
                        flat_names[icid] = iname
                    items.append({
                        "classid": icid,
                        "classname": iname,
                        "classimg": str(it.get("classimg") or ""),
                    })
                self._folder_lists[ft] = items
            if self._folder_lists.get("actress"):
                self._folder_lists["actress"].insert(0, {
                    "classid": "28", "classname": "全部女优", "classimg": ""})
            out = []
            for cid in FLAT_IDS:
                out.append({"type_id": cid,
                            "type_name": flat_names.get(cid, cid)})
            out.append({"type_id": "folder/cate/_", "type_name": "\U0001F4C2 高清国产"})
            out.append({"type_id": "folder/actress/_", "type_name": "\U0001F483 热门女优"})
            out.append({"type_id": "folder/movie/_", "type_name": "\U0001F3AC 热门分类"})
            if out:
                return out
        except Exception:
            pass
        return [dict(x) for x in FALLBACK_CLASS]

    def _folder_vod(self, ft, entry):
        return {
            "vod_id": "folder/%s/%s" % (ft, quote(entry.get("classid") or "", safe="")),
            "vod_name": str(entry.get("classname") or ""),
            "vod_pic": self._pic(entry.get("classimg") or ""),
            "vod_remarks": "",
            "vod_tag": "folder",
        }

    def homeContent(self, filter):
        try:
            cats = self._cats()
            lst = []
            try:
                o = self._json("/latest.json") or {}
                lst = self._vods(o.get("latest") or [])[:20]
            except Exception:
                lst = []
            return {"class": cats, "list": lst}
        except Exception:
            return {"class": [dict(x) for x in FALLBACK_CLASS], "list": []}

    def homeVideoContent(self):
        try:
            o = self._json("/latest.json") or {}
            return {"list": self._vods(o.get("latest") or [])[:20]}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid or "")
        pg = self._int(pg, 1)
        if pg < 1:
            pg = 1
        if tid.startswith("folder/") and tid.endswith("/_"):
            ft = tid.split("/", 2)[1]
            arr = (self.__dict__.get("_folder_lists") or {}).get(ft)
            if not arr:
                self._cats()
                arr = (self.__dict__.get("_folder_lists") or {}).get(ft) or []
            lst = []
            for e in arr:
                v = self._folder_vod(ft, e)
                if v["vod_name"]:
                    lst.append(v)
            return {"list": lst, "page": 1, "pagecount": 1,
                    "limit": len(lst) or 1, "total": len(lst), "parse": 0, "jx": 0}
        if tid.startswith("folder/"):
            cid = unquote(tid.split("/", 2)[2])
            return self._cat_list(cid, pg)
        return self._cat_list(tid, pg)

    def _cat_list(self, tid, pg):
        try:
            o = self._json("/category/%s-%s.json" % (tid, pg)) or {}
            lst = self._vods(o.get("data") or [])
            last = self._int(o.get("last_page"), 1)
            total = self._int(o.get("total"), len(lst))
            per = self._int(o.get("per_page"), len(lst) or PAGE_SIZE)
            return {"list": lst, "page": pg, "pagecount": max(last, 1),
                    "limit": per, "total": total, "parse": 0, "jx": 0}
        except Exception:
            return {"list": [], "page": pg, "pagecount": 1, "limit": 0,
                    "total": 0, "parse": 0, "jx": 0}

    def _detail_vod(self, o, vid):
        m3u8 = str(o.get("m3u8") or "")
        mp4 = str(o.get("mp4") or "")
        froms, urls = [], []
        if mp4:
            froms.append("MP4")
            urls.append("正片$" + mp4)
        if m3u8:
            if m3u8.startswith("http"):
                cl = [m3u8]
            else:
                cl = [c + m3u8 for c in CDN]
            froms.append("HLS")
            urls.append("正片$" + cl[0])
            if len(cl) > 1:
                froms.append("HLS2")
                urls.append("正片$" + cl[1])
        if not froms:
            froms = ["线路"]
            urls = ["暂无片源$http://"]

        ts = self._int(o.get("newstime"), 0)
        year = time.strftime("%Y", time.localtime(ts)) if ts else ""
        kws = self._clean(o.get("keyboard") or "").replace(",", " / ")
        catn = self._clean(o.get("category_name") or "")
        content_parts = []
        if catn:
            content_parts.append("分类：" + catn)
        if kws:
            content_parts.append("标签：" + kws)

        return {
            "vod_id": vid,
            "vod_name": self._clean(o.get("title")),
            "vod_pic": self._pic(o.get("titlepic") or ""),
            "vod_year": year,
            "vod_area": catn,
            "vod_remarks": catn,
            "vod_content": "\n".join(content_parts),
            "vod_play_from": "$$$".join(froms),
            "vod_play_url": "$$$".join(urls),
        }

    def detailContent(self, ids):
        try:
            if isinstance(ids, str):
                s = ids.strip()
                if s.startswith("["):
                    try:
                        id_list = [str(x).strip("\"' ") for x in json.loads(s)]
                    except Exception:
                        id_list = [x.strip("\"' ") for x in s.strip("[]").split(",")]
                else:
                    id_list = [x.strip("\"' ") for x in s.split(",")]
            elif isinstance(ids, (list, tuple)):
                id_list = [str(x).strip("\"' ") for x in ids]
            else:
                id_list = [str(ids)]
            vods = []
            for vid in id_list:
                if not vid or vid.startswith("folder/"):
                    continue
                o = self._json("/video/%s.json" % vid)
                if not isinstance(o, dict) or not o.get("title"):
                    continue
                vods.append(self._detail_vod(o, vid))
            return {"list": vods}
        except Exception:
            return {"list": []}

    def action(self, action):
        return {"msg": ""}

    def searchContent(self, key, quick, pg="1"):
        try:
            key = str(key or "").strip()
            if not key:
                return {"list": [], "page": 1}
            page = self._int(pg, 1)
            enc = _aes_enc_b64u(key)
            url = "%s/api/v2/search?keyword=%s&classid=0&page=%s" % (SEARCH_HOST, enc, page)
            txt = self._get_text(url, timeout=12000)
            if not txt:
                return {"list": [], "page": page}
            d = json.loads(txt)
            if not isinstance(d, dict) or d.get("status") != 1:
                return {"list": [], "page": page}
            o = _aes_dec_json(d.get("data") or "")
            arr = (o or {}).get("data") or []
            self._fill_pics(arr)
            lst = self._vods(arr)
            return {"list": lst, "page": page}
        except Exception:
            return {"list": [], "page": 1}

    def playerContent(self, flag, id, vipFlags):
        hdr = {"User-Agent": UA, "Referer": SITE + "/"}
        try:
            v = str(id or "").strip()
            seg = v.split("#")[0]
            cand = seg.rsplit("$", 1)[-1] if "$" in seg else seg
            if cand.startswith("http"):
                return {"parse": 0, "url": cand, "header": hdr}
        except Exception:
            pass
        return {"parse": 1, "url": SITE + "/", "header": hdr}

    def proxy(self, params):
        try:
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except Exception:
                    return [404, "text/plain", ""]
            if not isinstance(params, dict):
                return [404, "text/plain", ""]
            if params.get("type") == "pic":
                u = str(params.get("url") or "")
                if u:
                    try:
                        u = _b64u_dec(u).decode("utf-8", "replace")
                    except Exception:
                        u = unquote(u)
                txt = self._get_text(u, timeout=10000)
                m = re.match(r"data:image/([A-Za-z0-9+.-]+);base64,(.*)", txt, re.S)
                if m:
                    try:
                        raw = base64.b64decode(re.sub(r"\s+", "", m.group(2)))
                        mime = "image/" + ("jpeg" if m.group(1).lower() in ("jpg", "jpeg")
                                           else m.group(1).lower())
                        return [200, mime, self._img_stream(raw), {}]
                    except Exception:
                        pass
                return [200, "image/jpeg", self._img_stream(txt.encode("utf-8", "replace")), {}]
        except Exception:
            pass
        return [200, "image/jpeg", b""]

    localProxy = proxy


if __name__ == "__main__":
    print("[OK] module load, Crypto =", _HAS_CRYPTO)
    sp = Spider()
    sp.init("")
    h = sp.homeContent(False)
    print("homeContent: class=%d list=%d" % (len(h.get("class") or []),
                                             len(h.get("list") or [])))
    names = [c["type_name"] for c in (h.get("class") or [])]
    print("  分类样例:", names[:8], "| 含自拍视频?", "自拍视频" in names,
          "| 含女优?", "女优" in names)
    c = sp.categoryContent("4", 1, False, {})
    print("categoryContent(4,p1): list=%d pagecount=%s total=%s" % (
        len(c.get("list") or []), c.get("pagecount"), c.get("total")))
    if c.get("list"):
        vid = c["list"][0]["vod_id"]
        d = sp.detailContent([vid])
        vod = (d.get("list") or [{}])[0]
        print("detailContent:", vod.get("vod_name"), "| from=", vod.get("vod_play_from"))
        pu = vod.get("vod_play_url") or ""
        if pu:
            first = pu.split("$$$")[0].split("#")[0]
            pid = first.rsplit("$", 1)[-1]
            pc = sp.playerContent("MP4", pid, [])
            print("playerContent:", pc.get("parse"), str(pc.get("url"))[:110])
    s = sp.searchContent("自拍", False)
    print("searchContent: list=%d" % len(s.get("list") or []))
    print("[DONE]")
