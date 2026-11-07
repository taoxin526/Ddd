# -*- coding: utf-8 -*-
# [134X¹⁸  更新于:2026-11-05 20:20]
import base64
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, unquote

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        pass

SITE = "https://134x.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TIMEOUT = 20
PAGE_SIZE = 20
PAGECOUNT = 5
CATS = [("熱門", "popular"), ("精選", "featured"),
        ("AV", "search_av"), ("JAV", "search_jav"), ("FC2", "search_fc2")]
_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U0001F900-\U0001F9FF\uFE0F\u200D\u2705\u274C\u26A0\u2757\u2764]+")


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


def _fmt_dur(ms):
    try:
        s = int(ms) // 1000
    except Exception:
        return ""
    if s <= 0:
        return ""
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h > 0:
        return "%d:%02d:%02d" % (h, m, sec)
    return "%d:%02d" % (m, sec)


def _fmt_views(n):
    try:
        n = int(n)
    except Exception:
        return ""
    if n <= 0:
        return ""
    if n >= 10000:
        return "%.1f万" % (n / 10000.0)
    return str(n)


def _clean_line(s):
    s = _EMOJI.sub("", s or "")
    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"@\w+", " ", s)
    s = re.sub(r"#\w+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _has_meaning(s):
    return bool(s) and len(s) >= 3 and bool(re.search(r"[A-Za-z0-9\u4e00-\u9fff]", s))


class Spider(BaseSpider):
    name = "134X"
    site_url = SITE

    def init(self, extend=""):
        try:
            super(Spider, self).init(extend)
        except Exception:
            pass
        self.extend = extend or ""
        self._tw = {}
        self._poster = {}
        return None

    def _req_urllib(self, url, timeout=TIMEOUT):
        import urllib.request
        hdrs = {
            "User-Agent": UA,
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
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
                body = __import__("zlib").decompress(body)
            except Exception:
                pass
        return body

    def _req_text(self, url, timeout=TIMEOUT):
        net = getattr(self, "net", None)
        if net is not None:
            try:
                r = net.req(url, {"headers": {"User-Agent": UA, "Accept": "*/*"},
                                  "timeout": timeout * 1000})
                if isinstance(r, dict):
                    return r.get("content", "")
                if isinstance(r, (bytes, bytearray)):
                    return r.decode("utf-8", "replace")
                return str(r or "")
            except Exception:
                pass
        body = self._req_urllib(url, timeout)
        return body.decode("utf-8", "replace")

    def _get_loader(self, path):
        try:
            html = self._req_text(SITE + "/" + path.lstrip("/"))
        except Exception:
            return {}
        return _loader(html)

    def _req_img(self, url):
        net = getattr(self, "net", None)
        hdrs = {"User-Agent": UA, "Referer": "https://twitter.com/",
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"}
        if net is not None:
            try:
                if hasattr(net, "reqParts"):
                    parts = net.reqParts(url, {"headers": hdrs, "buffer": 3})
                    if parts and len(parts) > 1:
                        return parts[1], "image/jpeg"
                r = net.req(url, {"headers": hdrs, "buffer": 3})
                if isinstance(r, dict):
                    return r.get("content", b""), "image/jpeg"
                if isinstance(r, (bytes, bytearray)):
                    return bytes(r), "image/jpeg"
            except Exception:
                pass
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=hdrs)
            resp = urllib.request.urlopen(req, timeout=15)
            return resp.read(), (resp.headers.get("Content-Type") or "image/jpeg")
        except Exception:
            return b"", ""

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

    def _pic_url(self, u):
        u = (u or "").strip()
        if not u:
            return ""
        enc = quote(base64.b64encode(u.encode("utf-8")).decode("ascii"), safe="")
        if hasattr(self, "proxyUrl"):
            try:
                p = self.proxyUrl({"type": "pic", "url": enc}, True)
                if p:
                    return p
            except Exception:
                pass
        gp = getattr(self, "getProxyUrl", None)
        if gp is None:
            return u
        try:
            import inspect
            names = list(inspect.signature(gp).parameters.keys())
        except Exception:
            names = ["params", "local"]
        if names and names[0] == "params":
            try:
                return gp({"type": "pic", "url": enc}, True)
            except Exception:
                return u
        try:
            base = gp(True)
        except Exception:
            return u
        if base:
            sep = "&" if "?" in base else "?"
            return "%s%stype=pic&url=%s" % (base, sep, enc)
        return u

    def _avatar(self, u):
        u = (u or "").strip()
        if not u:
            return ""
        return re.sub(r"_(?:normal|bigger|mini|x96|reasonably_small)\.", ".", u)

    def _video_meta(self, tid):
        html = ""
        try:
            html = self._req_text(SITE + "/video/" + tid, timeout=6)
        except Exception:
            pass
        poster = ""
        m = re.search(r"https://pbs\.twimg\.com/amplify_video_thumb/[^\"'\\\s]+", html)
        if not m:
            m = re.search(r'property="og:image"\s+content="([^"]+)"', html)
        if m:
            poster = m.group(1) if "amplify_video_thumb" not in m.group(0) else m.group(0)
            poster = poster.replace("&amp;", "&").replace("\\u0026", "&")
        return poster

    def _batch_meta(self, tids):
        todo = [x for x in tids if x and not self._poster.get(x)]
        if not todo:
            return
        def one(tid):
            try:
                return tid, self._video_meta(tid)
            except Exception:
                return tid, ""
        try:
            with ThreadPoolExecutor(max_workers=6) as ex:
                futs = [ex.submit(one, t) for t in todo]
                for f in as_completed(futs, timeout=20):
                    try:
                        tid, pic = f.result()
                        if pic:
                            self._poster[tid] = pic
                    except Exception:
                        pass
        except Exception:
            for tid in todo[:6]:
                try:
                    _, pic = one(tid)
                    if pic:
                        self._poster[tid] = pic
                except Exception:
                    pass

    def _title(self, t):
        text = (t.get("text") or "").replace("\n", "\n")
        lines = [_clean_line(l) for l in text.splitlines()]
        lines = [l for l in lines if l]
        for l in lines:
            m = re.match(r"^(?:Title|標題|标题)\s*[:：]\s*(.+)$", l)
            if m:
                return m.group(1)[:60]
        for l in lines:
            if _has_meaning(l):
                return l[:60]
        return (t.get("name") or t.get("screenName") or "134X視頻")[:60]

    def _remarks(self, t):
        parts = []
        d = _fmt_dur(t.get("durationMillis"))
        if d:
            parts.append(d)
        v = _fmt_views(t.get("playTimes"))
        if v:
            parts.append(v + "播放")
        return " · ".join(parts)

    def _clickable(self, kind, name):
        name = (name or "").strip()
        if not name:
            return ""
        enc = quote(name, safe="")
        return '[a=cr:{"id":"%s/%s","name":"%s"}/]%s[/a]' % (
            kind, enc, name.replace('"', ""), name)

    def _to_vod(self, t):
        tid = (t.get("tweetId") or "").strip()
        if not tid:
            return None
        self._tw[tid] = t
        pic = self._poster.get(tid) or self._avatar(t.get("profileImage"))
        return {
            "vod_id": tid,
            "vod_name": self._title(t),
            "vod_pic": self._pic_url(pic),
            "vod_remarks": self._remarks(t),
        }

    def _detail_vod(self, tid, t):
        name = self._title(t) if t else tid
        pic = self._poster.get(tid) or (self._avatar(t.get("profileImage")) if t else "")
        remarks = self._remarks(t) if t else ""
        media = (t.get("media") or "").strip() if t else ""
        actor = ""
        content = ""
        if t:
            actor = self._clickable("actor", t.get("name") or t.get("screenName"))
            text = (t.get("text") or "").strip()
            d = _fmt_dur(t.get("durationMillis"))
            v = _fmt_views(t.get("playTimes"))
            lv = _fmt_views(t.get("longPlayTimes"))
            fv = _fmt_views(t.get("favoTimes"))
            st = []
            if v:
                st.append("播放 %s" % v)
            if lv:
                st.append("长播 %s" % lv)
            if fv:
                st.append("收藏 %s" % fv)
            if d:
                st.append("时长 %s" % d)
            if t.get("postAt"):
                st.append("时间 %s" % str(t.get("postAt"))[:10])
            line = "  ".join(st)
            content = "\n".join([x for x in (text, line) if x])
        play_url = ("正片$" + media) if media else ""
        return {
            "vod_id": tid,
            "vod_name": name,
            "vod_pic": self._pic_url(pic),
            "vod_remarks": remarks,
            "vod_year": "",
            "vod_actor": actor,
            "vod_content": content,
            "vod_play_from": "twimg",
            "vod_play_url": play_url,
        }

    def _list_page(self, path, pg):
        sep = "&" if "?" in path else "?"
        lod = self._get_loader("%s%spage=%d" % (path, sep, pg))
        rows = lod.get("tweets") or []
        out = []
        seen = set()
        for t in rows:
            if not isinstance(t, dict):
                continue
            v = self._to_vod(t)
            if v and v["vod_id"] not in seen:
                seen.add(v["vod_id"])
                out.append(v)
        self._batch_meta([v["vod_id"] for v in out])
        for v in out:
            p = self._poster.get(v["vod_id"])
            if p:
                v["vod_pic"] = self._pic_url(p)
        return out

    def homeContent(self, filter):
        result = {"class": self._classes(), "list": []}
        try:
            items = self._list_page("/popular", 1)
            items += self._list_page("/featured", 1)
        except Exception:
            items = []
        seen = set()
        dedup = []
        for v in items:
            if v["vod_id"] not in seen:
                seen.add(v["vod_id"])
                dedup.append(v)
        result["list"] = dedup[:40]
        return result

    def _classes(self):
        return [{"type_name": n, "type_id": i, "filters": []} for n, i in CATS]

    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": 1, "pagecount": 0,
                  "limit": PAGE_SIZE, "total": 0}
        try:
            pg = int(pg) if str(pg).isdigit() else 1
        except Exception:
            pg = 1
        result["page"] = pg
        tid = str(tid or "")
        if tid.startswith("actor/"):
            name = unquote(tid.split("/", 1)[1])
            return self._search_page(name, pg, result)
        if tid.startswith("search_"):
            return self._search_page(tid[7:], pg, result)
        if tid == "popular":
            path = "/popular"
        elif tid == "featured":
            path = "/featured"
        else:
            return result
        try:
            result["list"] = self._list_page(path, pg)
            result["pagecount"] = PAGECOUNT
            result["total"] = PAGECOUNT * PAGE_SIZE
        except Exception:
            pass
        return result

    def _search_page(self, key, pg, result):
        try:
            lod = self._get_loader("/search?q=%s&page=%d" % (quote(key, safe=""), pg))
            rows = lod.get("tweets") or []
            out = []
            seen = set()
            for t in rows:
                if not isinstance(t, dict):
                    continue
                v = self._to_vod(t)
                if v and v["vod_id"] not in seen:
                    seen.add(v["vod_id"])
                    out.append(v)
            self._batch_meta([v["vod_id"] for v in out])
            for v in out:
                p = self._poster.get(v["vod_id"])
                if p:
                    v["vod_pic"] = self._pic_url(p)
            result["list"] = out
            result["total"] = int(lod.get("total") or 0)
            tp = int(lod.get("totalPages") or 0)
            result["pagecount"] = tp if tp > 0 else PAGECOUNT
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
            vid = str(vid or "").strip()
            if not vid:
                continue
            t = self._tw.get(vid)
            if not t:
                t = self._fetch_tweet(vid)
            if vid not in self._poster:
                try:
                    p = self._video_meta(vid)
                    if p:
                        self._poster[vid] = p
                except Exception:
                    pass
            out.append(self._detail_vod(vid, t))
        return {"list": out}

    def _fetch_tweet(self, tid):
        for path in ("/popular", "/featured"):
            for pg in range(1, PAGECOUNT + 1):
                try:
                    rows = self._get_loader("%s?page=%d" % (path, pg)).get("tweets") or []
                except Exception:
                    continue
                for t in rows:
                    if isinstance(t, dict) and str(t.get("tweetId") or "") == tid:
                        self._tw[tid] = t
                        return t
        return None

    def playerContent(self, flag, id, vipFlags):
        id = str(id or "").strip()
        if id.startswith("http"):
            return {"parse": 0, "url": id}
        t = self._tw.get(id)
        media = (t.get("media") or "").strip() if t else ""
        if media:
            return {"parse": 0, "url": media}
        return {"parse": 0, "url": ""}

    def proxy(self, params):
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                return [404, "text/plain", ""]
        if not isinstance(params, dict):
            return [404, "text/plain", ""]
        typ = (params.get("type") or "").lower()
        url = str(params.get("url") or "").strip()
        if not url:
            return [404, "text/plain", ""]
        if typ in ("pic", "img", "image") or "twimg.com" in url:
            real = url
            try:
                real = base64.b64decode(unquote(url).encode("utf-8")).decode("utf-8")
            except Exception:
                pass
            data, ctype = self._req_img(real)
            if not data:
                return [502, "text/plain", "img fetch failed"]
            if not ctype or "text" in ctype:
                ctype = "image/jpeg"
            return [200, ctype, self._img_stream(data), {}]
        return [404, "text/plain", ""]

    localProxy = proxy

    def action(self, action):
        return {"msg": "ok"}
