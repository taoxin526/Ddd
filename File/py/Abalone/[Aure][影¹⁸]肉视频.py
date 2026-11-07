# -*- coding: utf-8 -*-
# [肉視頻¹⁸  更新于:2026-11-05 18:30]
import base64
import hashlib
import json
import re
import struct
import time
import zlib
from urllib.parse import quote, urljoin, unquote

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        pass

SITE = "https://rou.video"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TIMEOUT = 20
PAGE_SIZE = 26
_PNG_SIG = b"\x89PNG\r\n\x1a\n"


class _Ref(object):
    __slots__ = ("n",)

    def __init__(self, n):
        self.n = n


class _Parser(object):
    def __init__(self, s):
        self.s = s
        self.i = 0
        self.store = {}

    def _ws(self):
        s, n = self.s, len(self.s)
        while self.i < n and s[self.i] in " \t\r\n":
            self.i += 1

    def _peek(self):
        self._ws()
        return self.s[self.i] if self.i < len(self.s) else ""

    def _eat(self, ch):
        self._ws()
        if self.s.startswith(ch, self.i):
            self.i += len(ch)
            return True
        return False

    def _string(self):
        s = self.s
        self.i += 1
        out = []
        while self.i < len(s):
            c = s[self.i]
            if c == "\\":
                d = s[self.i + 1]
                if d == "u":
                    try:
                        out.append(chr(int(s[self.i + 2:self.i + 6], 16)))
                    except Exception:
                        pass
                    self.i += 6
                    continue
                out.append({"n": "\n", "t": "\t", "r": "\r", "b": "\b",
                            "f": "\f", "/": "/", '"': '"', "\\": "\\"}.get(d, d))
                self.i += 2
                continue
            if c == '"':
                self.i += 1
                break
            out.append(c)
            self.i += 1
        return "".join(out)

    def _ident(self):
        s = self.s
        st = self.i
        while self.i < len(s) and (s[self.i].isalnum() or s[self.i] in "_$"):
            self.i += 1
        return s[st:self.i]

    def _number(self):
        s = self.s
        st = self.i
        if self.i < len(s) and s[self.i] in "+-":
            self.i += 1
        while self.i < len(s) and (s[self.i].isdigit() or s[self.i] in ".eE+-"):
            if s[self.i] in "+-" and s[self.i - 1] not in "eE":
                break
            self.i += 1
        txt = s[st:self.i]
        try:
            return float(txt) if any(c in txt for c in ".eE") else int(txt)
        except Exception:
            return 0

    def expr(self):
        c = self._peek()
        if c == "{":
            return self._obj()
        if c == "[":
            return self._arr()
        if c == '"':
            return self._string()
        if c == "!":
            self.i += 2
            return self.s[self.i - 1] == "0"
        if c == "-" or c.isdigit():
            return self._number()
        if self.s.startswith("$R[", self.i):
            self.i += 3
            st = self.i
            while self.i < len(self.s) and self.s[self.i] != "]":
                self.i += 1
            try:
                n = int(self.s[st:self.i])
            except Exception:
                n = -1
            self.i += 1
            self._ws()
            if self.i < len(self.s) and self.s[self.i] == "=":
                self.i += 1
                val = self.expr()
                self.store[n] = val
                return val
            return _Ref(n)
        word = self._ident()
        if word == "true":
            return True
        if word == "false":
            return False
        if word == "void":
            self.expr()
            return None
        return None

    def _obj(self):
        self.i += 1
        out = {}
        while True:
            c = self._peek()
            if c == "}":
                self.i += 1
                break
            if c == "":
                break
            if c == '"':
                k = self._string()
            else:
                k = self._ident()
                if not k:
                    self.i += 1
                    continue
            if not self._eat(":"):
                continue
            out[k] = self.expr()
            if not self._eat(","):
                if self._peek() == "}":
                    self.i += 1
                break
        return out

    def _arr(self):
        self.i += 1
        out = []
        while True:
            c = self._peek()
            if c == "]":
                self.i += 1
                break
            if c == "":
                break
            out.append(self.expr())
            if not self._eat(","):
                if self._peek() == "]":
                    self.i += 1
                break
        return out


def _resolve(v, store, depth=0):
    if depth > 300:
        return None
    if isinstance(v, _Ref):
        return _resolve(store.get(v.n), store, depth + 1) if v.n in store else None
    if isinstance(v, dict):
        return dict((k, _resolve(x, store, depth + 1)) for k, x in v.items())
    if isinstance(v, list):
        return [_resolve(x, store, depth + 1) for x in v]
    return v


def _parse_ssr(html):
    m = re.search(r"\$_TSR\.router=\(\$R=>\$R\[0\]=", html)
    if not m:
        return None
    p = _Parser(html)
    p.i = m.end()
    try:
        root = p.expr()
    except Exception:
        return None
    return _resolve(root, p.store)


def _loader(html):
    d = _parse_ssr(html)
    if not d:
        return {}
    ms = d.get("matches") or []
    if not ms:
        return {}
    lod = ms[-1].get("l")
    return lod if isinstance(lod, dict) else {}


def _unwrap_container(buf):
    if not buf[:8] == _PNG_SIG:
        return buf
    i, n = 8, len(buf)
    while i + 8 <= n:
        try:
            ln = struct.unpack(">I", buf[i:i + 4])[0]
        except Exception:
            return buf
        typ = buf[i + 4:i + 8]
        if typ == b"roUd":
            d = buf[i + 8:i + 8 + ln]
            if not d:
                return buf
            if d[0] == 1:
                try:
                    return zlib.decompress(d[1:])
                except Exception:
                    return d[1:]
            return d[1:]
        if typ == b"IEND":
            break
        i += 12 + ln
    return buf


def _xk_decode(d, k):
    try:
        b = base64.b64decode(d)
        s = "".join(chr(c - k) for c in b)
        return json.loads(s)
    except Exception:
        return {}


def _fmt_dur(sec):
    try:
        sec = int(float(sec))
    except Exception:
        return ""
    if sec <= 0:
        return ""
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return ("%d:%02d:%02d" % (h, m, s)) if h else ("%d:%02d" % (m, s))


def _fmt_views(n):
    try:
        n = int(n)
    except Exception:
        return ""
    if n >= 100000000:
        return "%.1f亿" % (n / 100000000.0)
    if n >= 10000:
        return "%.1f万" % (n / 10000.0)
    return str(n)


def _res_of(v):
    srcs = v.get("sources") or []
    best = 0
    for s in srcs:
        try:
            best = max(best, int(s.get("resolution") or 0))
        except Exception:
            pass
    return ("%dP" % best) if best else ""


def _dedup(items):
    seen = set()
    out = []
    for it in items:
        k = it.get("vod_id")
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out
class Spider(BaseSpider):
    name = "肉视频"
    site_url = SITE

    def init(self, extend=""):
        try:
            super(Spider, self).init(extend)
        except Exception:
            pass
        self.extend = extend or ""
        self._tax = None
        self._tax_ts = 0.0
        self._segs = {}
        self._pl_cache = {}
        self._pg_cache = {}
        return None

    def _req_urllib(self, url, referer=None, timeout=TIMEOUT, headers=None):
        import urllib.request
        hdrs = {
            "User-Agent": UA,
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        if referer:
            hdrs["Referer"] = referer
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, headers=hdrs)
        resp = urllib.request.urlopen(req, timeout=timeout)
        body = resp.read()
        enc = (resp.headers.get("Content-Encoding") or "").lower()
        if "gzip" in enc:
            try:
                body = __import__("gzip").decompress(body)
            except Exception:
                pass
        elif "deflate" in enc:
            try:
                body = zlib.decompress(body)
            except Exception:
                try:
                    body = zlib.decompress(body, -zlib.MAX_WBITS)
                except Exception:
                    pass
        return body

    def _urllib_bytes(self, url, referer=None, timeout=TIMEOUT):
        return self._req_urllib(url, referer, timeout)

    def _net_resp(self, resp, url):
        if isinstance(resp, dict):
            return resp.get("code", 200), resp.get("content", b""), resp.get("headers", {})
        return 200, resp, {}

    def _req_bytes(self, url, referer=None, timeout=TIMEOUT):
        net = getattr(self, "net", None)
        hdrs = {"User-Agent": UA, "Accept": "*/*"}
        if referer:
            hdrs["Referer"] = referer
        if net is not None:
            try:
                opts = {"headers": hdrs, "buffer": 3, "timeout": timeout * 1000}
                if hasattr(net, "reqParts"):
                    parts = net.reqParts(url, opts)
                    if parts and len(parts) > 1:
                        return parts[1]
                r = net.req(url, opts)
                if isinstance(r, dict):
                    return r.get("content", b"")
                if isinstance(r, (bytes, bytearray)):
                    return r
            except Exception:
                pass
        return self._req_urllib(url, referer, timeout)

    def _req_text(self, url, referer=None, timeout=TIMEOUT):
        net = getattr(self, "net", None)
        hdrs = {"User-Agent": UA, "Accept": "*/*"}
        if referer:
            hdrs["Referer"] = referer
        if net is not None:
            try:
                r = net.req(url, {"headers": hdrs, "timeout": timeout * 1000})
                if isinstance(r, dict):
                    return r.get("content", "")
                if isinstance(r, (bytes, bytearray)):
                    return r.decode("utf-8", "replace")
                return str(r or "")
            except Exception:
                pass
        body = self._req_urllib(url, referer, timeout)
        return body.decode("utf-8", "replace")

    def _get_html(self, path):
        return self._req_text(urljoin(SITE + "/", path.lstrip("/")), referer=SITE + "/home")

    def _get_loader(self, path):
        try:
            html = self._get_html(path)
        except Exception:
            return {}
        return _loader(html)

    def _fix(self, u):
        u = (u or "").strip()
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("https:/") and not u.startswith("https://"):
            return "https://" + u[len("https:/"):]
        return u

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

    def _proxy_url(self, params):
        if hasattr(self, "proxyUrl"):
            try:
                p = self.proxyUrl(params, True)
                if p:
                    return p
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
                return ""
        try:
            base = gp(True)
        except Exception:
            base = gp()
        if isinstance(params, dict) and params:
            qs = "&".join("%s=%s" % (k, quote(str(v), safe="")) for k, v in params.items())
            return base + ("&" + qs if "?" in base else "?" + qs)
        return base
    def _taxonomy(self):
        if getattr(self, "_tax", None) and time.time() - getattr(self, "_tax_ts", 0) < 1800:
            return self._tax
        try:
            tax = self._get_loader("/cat").get("taxonomy") or {}
        except Exception:
            tax = {}
        if tax:
            self._tax = tax
            self._tax_ts = time.time()
        return getattr(self, "_tax", None) or {}

    def _order_filter(self):
        return [{"key": "order", "name": "排序", "init": "",
                 "value": [{"n": "最新", "v": ""},
                           {"n": "观看数", "v": "viewCount"},
                           {"n": "点赞", "v": "likeCount"}]}]

    def _series_tag_filter(self):
        val = []
        try:
            lod = self._get_loader("/series?page=1")
            for t in (lod.get("tagOptions") or []):
                name = t.get("id") or ""
                if name:
                    val.append({"n": name, "v": name})
        except Exception:
            pass
        return [{"key": "tag", "name": "题材", "init": "", "value": val}]

    def _classes(self):
        out = [{"type_name": "劇集", "type_id": "__series__",
                "filters": self._series_tag_filter()}]
        tax = self._taxonomy()
        for c in (tax.get("cats") or []):
            name = c.get("id") or ""
            if name:
                out.append({"type_name": name, "type_id": name,
                            "filters": self._order_filter()})
        genre = sorted(tax.get("genre") or [], key=lambda x: -(x.get("count") or 0))
        have = set(x["type_id"] for x in out)
        for g in genre[:12]:
            name = g.get("id") or ""
            if name and name not in have:
                out.append({"type_name": name, "type_id": name,
                            "filters": self._order_filter()})
        return out

    def _remarks(self, v):
        parts = []
        r = _res_of(v)
        if r:
            parts.append(r)
        d = _fmt_dur(v.get("duration"))
        if d:
            parts.append(d)
        views = _fmt_views(v.get("viewCount"))
        if views:
            parts.append(views)
        return " · ".join(parts)

    def _vod_item(self, v):
        return {
            "vod_id": v.get("id") or "",
            "vod_name": v.get("nameZh") or v.get("name") or "",
            "vod_pic": self._fix(v.get("coverImageUrl")),
            "vod_remarks": self._remarks(v),
        }

    def _series_item(self, s):
        epl = s.get("epLabel") or ""
        views = _fmt_views(s.get("viewCount"))
        return {
            "vod_id": "series:" + (s.get("id") or ""),
            "vod_name": s.get("nameZh") or s.get("name") or "",
            "vod_pic": self._fix(s.get("coverImageUrl")),
            "vod_remarks": " · ".join([x for x in (epl, views) if x]),
        }

    def _clickable(self, kind, name):
        name = (name or "").strip()
        if not name:
            return ""
        enc = quote(name, safe="")
        return '[a=cr:{"id":"%s/%s","name":"%s","type_flag":"1"}/]%s[/a]' % (
            kind, enc, name.replace('"', ""), name)

    def _safe_label(self, name):
        return (name or "").replace("$", "\uff04").replace("#", "\uff03").strip()

    def _episodes(self, rows, fallback_id):
        eps = []
        for i, ep in enumerate(rows or []):
            eid = ep.get("id") or ""
            if not eid:
                continue
            no = ep.get("episode") or (i + 1)
            nm = str(ep.get("name") or "").split("·")[-1].strip() or ("第%d集" % no)
            eps.append((nm, eid))
        if not eps:
            eps = [("正片", fallback_id)]
        return eps

    def _vod(self, vid, name, pic, remarks, year, content, play_from, play_url):
        return {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "vod_remarks": remarks,
            "vod_year": year,
            "vod_content": content,
            "vod_play_from": play_from,
            "vod_play_url": play_url,
        }
    def homeContent(self, filter):
        result = {"class": self._classes(), "list": []}
        try:
            lod = self._get_loader("/home")
        except Exception:
            return result
        items = []
        for key in ("latestVideos", "dailyHotCNAV", "dailyHotSelfie", "dailyHot91",
                    "dailyOnlyFans", "dailyJV", "hotCNAV", "hotSelfie", "hot91"):
            for v in (lod.get(key) or []):
                if isinstance(v, dict) and v.get("id"):
                    items.append(self._vod_item(v))
        result["list"] = _dedup(items)[:60]
        return result

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": 1, "pagecount": 0,
                  "limit": PAGE_SIZE, "total": 0}
        try:
            pg = int(pg) if str(pg).isdigit() else 1
        except Exception:
            pg = 1
        result["page"] = pg
        tid = str(tid or "")
        if tid.startswith("actor/") or tid.startswith("director/"):
            name = unquote(tid.split("/", 1)[1])
            return self._search_page(name, pg, result)
        if tid.startswith("tag/"):
            name = unquote(tid.split("/", 1)[1])
            return self._tag_page(name, pg, result, {})
        extend = extend if isinstance(extend, dict) else {}
        try:
            if tid == "__series__":
                url = "/series?page=%d" % pg
                tag = extend.get("tag") or ""
                if tag:
                    url += "&tag=" + quote(tag, safe="")
                lod = self._get_loader(url)
                rows = lod.get("list") or []
                result["list"] = _dedup([self._series_item(s) for s in rows if isinstance(s, dict)])
                result["pagecount"] = int(lod.get("totalPage") or 0)
                result["total"] = int(lod.get("total") or 0)
            else:
                return self._tag_page(tid, pg, result, extend)
        except Exception:
            pass
        return result

    def _tag_page(self, tid, pg, result, extend):
        try:
            url = "/t/%s?page=%d" % (quote(tid, safe=""), pg)
            order = extend.get("order") or ""
            if order:
                url += "&order=" + quote(order, safe="")
            lod = self._get_loader(url)
            rows = lod.get("videos") or []
            result["list"] = _dedup([self._vod_item(v) for v in rows if isinstance(v, dict)])
            result["pagecount"] = int(lod.get("totalPage") or 0)
            result["total"] = int(lod.get("totalVideoNum") or 0)
        except Exception:
            pass
        return result

    def _search_page(self, key, pg, result):
        try:
            lod = self._get_loader("/search?q=%s&page=%d" % (quote(key, safe=""), pg))
            items = [self._vod_item(v) for v in (lod.get("videos") or []) if isinstance(v, dict)]
            if not items:
                items = [self._series_item(s) for s in (lod.get("seriesList") or []) if isinstance(s, dict)]
            result["list"] = _dedup(items)
            result["pagecount"] = int(lod.get("totalPage") or 0)
            result["total"] = int(lod.get("totalVideoNum") or 0)
        except Exception:
            pass
        return result

    def searchContent(self, key, quick, pg="1"):
        result = {"list": [], "page": 1, "pagecount": 0,
                  "limit": PAGE_SIZE, "total": 0}
        key = str(key or "").strip()
        try:
            pg = int(pg) if str(pg).isdigit() else 1
        except Exception:
            pg = 1
        result["page"] = pg
        if not key:
            return result
        return self._search_page(key, pg, result)

    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        if not ids:
            return {"list": []}
        out = []
        for vid in ids:
            vid = str(vid or "")
            if not vid:
                continue
            if vid.startswith("series:"):
                out.append(self._series_detail(vid.split(":", 1)[1]))
            else:
                out.append(self._video_detail(vid))
        return {"list": out}

    def _video_detail(self, vid):
        try:
            lod = self._get_loader("/v/" + vid)
        except Exception:
            lod = {}
        v = lod.get("video") or {}
        name = v.get("nameZh") or v.get("name") or vid
        pic = self._fix(v.get("coverImageUrl"))
        remarks = self._remarks(v)
        year = ""
        created = str(v.get("createdAt") or "")
        if created[:4].isdigit():
            year = created[:4]
        tags = v.get("tags") or v.get("tagsZh") or []
        desc = v.get("description") or ""
        head = ""
        if tags:
            head = "标签：" + " ".join(self._clickable("tag", t) for t in tags)
        stat = "播放 %s · 时长 %s" % (_fmt_views(v.get("viewCount")), _fmt_dur(v.get("duration")))
        content = "\n".join([x for x in (desc, head, stat) if x])
        eps = self._episodes(lod.get("episodes") or [], vid)
        play_from = "正片"
        play_url = "#".join(["%s$%s" % (self._safe_label(nm),
                                        self._proxy_url({"type": "hls", "vid": eid}))
                             for nm, eid in eps])
        return self._vod(vid, name, pic, remarks, year, content, play_from, play_url)

    def _series_detail(self, sid):
        try:
            lod = self._get_loader("/s/" + sid)
        except Exception:
            lod = {}
        s = lod.get("series") or {}
        name = s.get("nameZh") or s.get("name") or sid
        pic = self._fix(s.get("coverImageUrl"))
        remarks = s.get("epLabel") or ""
        year = ""
        created = str(s.get("createdAt") or "")
        if created[:4].isdigit():
            year = created[:4]
        tags = s.get("tags") or []
        desc = s.get("description") or ""
        head = ""
        if tags:
            head = "标签：" + " ".join(self._clickable("tag", t) for t in tags)
        stat = "播放 %s · %s" % (_fmt_views(s.get("viewCount")), remarks)
        content = "\n".join([x for x in (desc, head, stat) if x])
        eps = self._episodes(lod.get("episodes") or [], "")
        play_from = "正片"
        play_url = "#".join(["%s$%s" % (self._safe_label(nm),
                                        self._proxy_url({"type": "hls", "vid": eid}))
                             for nm, eid in eps])
        return self._vod("series:" + sid, name, pic, remarks, year, content, play_from, play_url)

    def playerContent(self, flag, id, vipFlags):
        id = str(id or "").strip()
        if id.startswith("http"):
            return {"parse": 0, "url": id}
        return {"parse": 0, "url": self._proxy_url({"type": "hls", "vid": id})}

    def _seg_proxy(self, url, role):
        tok = hashlib.md5(url.encode("utf-8")).hexdigest()[:20]
        if not hasattr(self, "_segs"):
            self._segs = {}
        self._segs[tok] = url
        return self._proxy_url({"type": role, "tok": tok})

    def _rewrite_m3u8(self, text):
        out = []
        pending = None
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("#"):
                if 'URI="' in s:
                    if "EXT-X-KEY" in s:
                        role = "key"
                    elif "EXT-X-MEDIA" in s or "I-FRAME-STREAM-INF" in s:
                        role = "pl"
                    else:
                        role = "seg"

                    def _rep(m):
                        return m.group(1) + self._seg_proxy(m.group(2), role) + m.group(3)
                    s = re.sub(r'(URI=")([^"]+)(")', _rep, s)
                out.append(s)
                pending = "pl" if s.startswith("#EXT-X-STREAM-INF") else None
                continue
            out.append(self._seg_proxy(s, pending or "seg"))
            pending = None
        return "\n".join(out) + "\n"

    def _playlist(self, vid):
        key = vid
        if not hasattr(self, "_pl_cache"):
            self._pl_cache = {}
        hit = self._pl_cache.get(key)
        if hit and hit[1] > time.time():
            return hit[0]
        raw = self._req_bytes(SITE + "/api/hls/" + vid, referer=SITE + "/v/" + vid)
        data = _unwrap_container(raw)
        text = data.decode("utf-8", "replace")
        if not text.lstrip().startswith("#EXTM3U"):
            raise ValueError("bad playlist")
        out = self._rewrite_m3u8(text)
        self._pl_cache[key] = (out, time.time() + 1500)
        return out

    def _seg_bytes(self, url):
        key = url
        if not hasattr(self, "_pg_cache"):
            self._pg_cache = {}
        hit = self._pg_cache.get(key)
        if hit and hit[1] > time.time():
            return hit[0]
        raw = self._req_bytes(url, referer=SITE + "/")
        data = _unwrap_container(raw)
        self._pg_cache[key] = (data, time.time() + 300)
        return data

    def proxy(self, params):
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                return [404, "text/plain", ""]
        if not isinstance(params, dict):
            return [404, "text/plain", ""]
        typ = params.get("type")
        if typ == "hls":
            vid = params.get("vid") or ""
            if not vid:
                return [404, "text/plain", ""]
            try:
                text = self._playlist(vid)
                return [200, "application/vnd.apple.mpegurl",
                        self._img_stream(text.encode("utf-8")), {}]
            except Exception:
                return [404, "text/plain", "playlist error"]
        if typ == "seg":
            tok = params.get("tok") or ""
            url = self._segs.get(tok)
            if not url:
                return [404, "text/plain", "no seg"]
            try:
                data = self._seg_bytes(url)
                return [200, "video/mp2t", self._img_stream(data), {}]
            except Exception:
                return [502, "text/plain", "seg error"]
        if typ == "key":
            tok = params.get("tok") or ""
            url = self._segs.get(tok)
            if not url:
                return [404, "text/plain", "no key"]
            try:
                data = self._req_bytes(url, referer=SITE + "/")
                data = _unwrap_container(data)
                return [200, "application/octet-stream", self._img_stream(data), {}]
            except Exception:
                return [502, "text/plain", "key error"]
        return [404, "text/plain", ""]

    localProxy = proxy

    def action(self, action):
        return {"msg": "ok"}
