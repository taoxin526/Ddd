# -*- coding: utf-8 -*-
# [OWOAV¹⁸  更新于:2026-11-04 16:00]
import json
import re
import time
import threading
import gzip
import zlib
import urllib.request
from urllib.parse import quote, unquote
from lxml import etree

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        def proxy(self, params):
            return [404, "text/plain", ""]
        def localProxy(self, params):
            return [404, "text/plain", ""]

NAME = "OWOAV"
PUB_PAGE = "https://www.owodz.com"
DEFAULT_HOSTS = [
    "https://owoav22.cc", "https://owoav21.cc", "https://owoav20.cc",
    "https://owoav23.cc", "https://600kk.net", "https://owoav.com",
]
BLACKLIST = {
    "t.me", "qq.com", "sina.com.cn", "sohu.com", "163.com", "ifeng.com",
    "weibo.com", "zhihu.com", "58.com", "douban.com", "tianya.cn",
    "cn.bing.com", "outlook.live.com", "ip138.com", "xunlei.com",
    "mail.qq.com", "dnspod.cn", "alidns.com", "dudns.baidu.com",
    "microsoft.com", "google.cn", "pan.baidu.com", "wandoujia.com",
    "owodz.com", "owodz.org",
}
HOST_TTL = 21600
PAGE_SIZE = 20
CACHE_TTL = 60
UA = "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"


class Spider(BaseSpider):

    def __init__(self):
        super().__init__()
        self.name = NAME
        self.host = DEFAULT_HOSTS[0]
        self._cache = {}
        self._cache_time = {}
        self._good_host = None
        self._host_ts = 0
        self._lock = threading.Lock()
        self.options = {}
        self._session = None

    def _get_session(self):
        if self._session is None:
            import requests as _rq
            self._session = _rq.Session()
        return self._session

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
        self.options = cfg

    def destroy(self):
        with self._lock:
            self._cache.clear()
            self._cache_time.clear()
        self.options = {}

    def getDependence(self):
        return []

    def action(self, action):
        return {"msg": "不支持此操作"}

    def _get_host(self):
        now = time.time()
        if self._good_host and now - self._host_ts < HOST_TTL:
            return self._good_host
        local = getattr(self, "local", None)
        if local is not None:
            try:
                c = local.get("owo_host", {})
                if isinstance(c, dict) and c.get("host") and now - float(c.get("ts", 0)) < HOST_TTL:
                    self._good_host = c["host"]
                    self._host_ts = float(c["ts"])
                    return c["host"]
            except Exception:
                pass
        h = self._refresh_host()
        if h:
            self._good_host = h
            self._host_ts = now
            if local is not None:
                try:
                    local.set("owo_host", {"host": h, "ts": now})
                except Exception:
                    pass
            return h
        return DEFAULT_HOSTS[0]

    def _refresh_host(self):
        cands = self._pub_candidates()
        for c in cands:
            if self._probe(c):
                return c
        for d in DEFAULT_HOSTS:
            if self._probe(d):
                return d
        return DEFAULT_HOSTS[0]

    def _is_blacklist(self, dom):
        for b in BLACKLIST:
            if dom == b or dom.endswith("." + b):
                return True
        return False

    def _pub_candidates(self):
        out = []
        try:
            html = self._get_html(PUB_PAGE, timeout=10000)
            if html:
                for dom in re.findall(r'https?://([a-zA-Z0-9.\-]+)', html):
                    dom = dom.lower().strip()
                    if not dom or self._is_blacklist(dom):
                        continue
                    url = "https://" + dom
                    if url not in out:
                        out.append(url)
        except Exception:
            pass
        for d in DEFAULT_HOSTS:
            if d not in out:
                out.append(d)
        return out

    def _probe(self, host):
        try:
            html = self._get_html(host + "/", timeout=8000)
            if not html:
                return False
            low = html.lower()
            return "videos_screenshots" in low or "owoav" in low
        except Exception:
            return False

    def _host_url(self):
        return self._get_host()

    def _resp_dict(self, resp):
        if isinstance(resp, dict):
            return resp
        if isinstance(resp, (bytes, bytearray)):
            return {"code": 200, "content": resp, "headers": {}, "error": None}
        if isinstance(resp, str):
            return {"code": 200, "content": resp, "headers": {}, "error": None}
        return {"code": 0, "content": "", "headers": {}, "error": str(resp)}

    def _net_opts(self, opts):
        net = getattr(self, "net", None)
        if net is not None and not hasattr(net, "_native"):
            return json.dumps(opts, ensure_ascii=False)
        return opts

    def _req(self, url, **kw):
        net = getattr(self, "net", None)
        if net is not None:
            try:
                opts = {"timeout": kw.get("timeout", 15000)}
                for k in ("params", "headers", "method", "postType", "data",
                          "body", "buffer", "redirect", "cookie"):
                    if k in kw and kw[k] is not None:
                        opts[k] = kw[k]
                resp = net.req(url, self._net_opts(opts))
                return resp or {}
            except Exception:
                return {}
        try:
            import requests as _rq
            _rq
        except Exception:
            return self._req_urllib(url, **kw)
        return self._req_requests(url, **kw)

    def _req_requests(self, url, **kw):
        try:
            sess = self._get_session()
            timeout = (kw.get("timeout") or 15000) / 1000.0
            method = (kw.get("method") or "GET").upper()
            headers = dict(kw.get("headers") or {})
            headers.setdefault("User-Agent", UA)
            headers.setdefault("Accept", "*/*")
            allow_redirects = kw.get("redirect", 1) != 0
            if method == "GET":
                r = sess.get(url, headers=headers, timeout=timeout, allow_redirects=allow_redirects)
            else:
                body = kw.get("data") or kw.get("body")
                r = sess.request(method, url, headers=headers, timeout=timeout,
                                 allow_redirects=allow_redirects, data=body)
            return {"code": r.status_code, "content": r.text,
                    "headers": dict(r.headers), "error": None}
        except Exception as e:
            return {"code": 0, "content": "", "headers": {}, "error": str(e)}

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
                return {"code": resp.getcode() or 0,
                        "content": raw.decode("utf-8", "replace"),
                        "headers": dict(resp.headers), "error": None}
        except Exception as e:
            return {"code": 0, "content": "", "headers": {}, "error": str(e)}

    def _get_html(self, url, **kw):
        resp = self._req(url, **kw)
        resp = self._resp_dict(resp)
        if resp.get("error"):
            return None
        code = resp.get("code") or 0
        if not 200 <= code < 300:
            return None
        return resp.get("content", "")

    def _req_site(self, path, **kw):
        host = self._get_host()
        kw.setdefault("cookie", True)
        ref = kw.get("headers") or {}
        ref.setdefault("Referer", host + "/")
        kw["headers"] = ref
        first_host = host
        for attempt in (0, 1):
            h = first_host if attempt == 0 else self._refresh_host()
            if not h:
                return None
            url = h + path
            resp = self._req(url, **kw)
            resp = self._resp_dict(resp)
            if resp.get("error"):
                continue
            code = resp.get("code") or 0
            if not 200 <= code < 300:
                continue
            if h != self.host:
                self.host = h
            return resp
        return None

    def _site_html(self, path, **kw):
        resp = self._req_site(path, **kw)
        if not resp:
            return None
        return resp.get("content", "")

    def _cache_get(self, key):
        with self._lock:
            if key in self._cache and time.time() - self._cache_time.get(key, 0) < CACHE_TTL:
                return self._cache[key]
        return None

    def _cache_set(self, key, val):
        with self._lock:
            self._cache[key] = val
            self._cache_time[key] = time.time()

    def homeContent(self, filter):
        classes = [
            {"type_id": "videos", "type_name": "视频"},
            {"type_id": "folder/models/_", "type_name": "女优"},
            {"type_id": "folder/categories/_", "type_name": "分类"},
            {"type_id": "folder/channels/_", "type_name": "频道"},
            {"type_id": "folder/tags/_", "type_name": "标签"},
        ]
        result = {"class": classes}
        if filter:
            result["filters"] = self._filters(classes)
        items = self._fetch_list("/videos/", 1, None)
        result["list"] = [self._vod(x) for x in items]
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        if tid.startswith("folder/"):
            parts = tid.split("/", 2)
            f_type = parts[1] if len(parts) > 1 else ""
            f_val = unquote(parts[2]) if len(parts) > 2 else ""
            if not f_val or f_val == "_":
                items = self._fetch_folder_entries(f_type)
                return {
                    "list": items,
                    "page": pg,
                    "pagecount": pg if len(items) < PAGE_SIZE else 9999,
                    "limit": PAGE_SIZE,
                    "total": 999999,
                }
            items = self._fetch_folder(f_type, f_val, pg)
            return {
                "list": [self._vod(x) for x in items],
                "page": pg,
                "pagecount": pg if len(items) < PAGE_SIZE else 9999,
                "limit": PAGE_SIZE,
                "total": 999999,
            }
        if tid == "videos":
            by = ""
            if isinstance(extend, dict) and extend.get("order"):
                by = str(extend["order"]).strip()
            items = self._fetch_list("/videos/", pg, by)
        else:
            items = self._fetch_list("/videos/", pg, None)
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pg if len(items) < PAGE_SIZE else 9999,
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def _fetch_list(self, base, pg, by):
        if by:
            if pg <= 1:
                url = base + ("&" if "?" in base else "?") + "by=%s" % quote(by, safe="")
            else:
                url = base.rstrip("/") + "/%d/?by=%s" % (pg, quote(by, safe=""))
        else:
            if pg <= 1:
                url = base
            else:
                url = base.rstrip("/") + "/%d/" % pg
        ck = "L|" + url
        hit = self._cache_get(ck)
        if hit is not None:
            return hit
        html = self._site_html(url)
        if not html:
            return []
        items = self._parse_video_list(html)
        self._cache_set(ck, items)
        return items

    def _parse_video_list(self, html):
        items = []
        seen = set()
        try:
            doc = etree.HTML(html)
        except Exception:
            return items
        for a in doc.xpath('//a[contains(@href, "/video/")]'):
            href = a.get("href") or ""
            m = re.search(r'/video/(\d+)/([^/]+)/?', href)
            if not m:
                continue
            vid, slug = m.group(1), m.group(2)
            if vid in seen:
                continue
            title = (a.get("title") or "").strip()
            if not title:
                h5 = a.xpath('.//h5[contains(@class,"thumb-spot__title")]/text()')
                if h5:
                    title = "".join(h5).strip()
            if not title:
                continue
            imgs = a.xpath('.//img')
            pic = imgs[0].get("src") or "" if imgs else ""
            if pic.startswith("//"):
                pic = "https:" + pic
            dur = ""
            lis = a.xpath('.//ul[contains(@class,"thumb-spot__data")]/li/text()')
            if lis:
                dur = (lis[0] or "").strip()
            seen.add(vid)
            items.append({"id": vid, "slug": slug, "name": title, "pic": pic, "remarks": dur})
        return items

    def _vod_id(self, vid, slug):
        return "%s_%s" % (vid, slug)

    def _vod(self, item):
        return {
            "vod_id": self._vod_id(item["id"], item.get("slug", "")),
            "vod_name": item.get("name", ""),
            "vod_pic": item.get("pic", ""),
            "vod_remarks": item.get("remarks", ""),
        }

    def _fetch_folder_entries(self, f_type):
        ck = "F|" + f_type
        hit = self._cache_get(ck)
        if hit is not None:
            return hit
        html = self._site_html("/%s/" % f_type)
        if not html:
            return []
        items = []
        try:
            doc = etree.HTML(html)
        except Exception:
            return []
        if f_type == "tags":
            for a in doc.xpath('//a[contains(@href, "/tags/")]'):
                href = a.get("href") or ""
                m = re.search(r'/tags/([^/]+)/?', href)
                if not m:
                    continue
                name = "".join(a.xpath('.//text()')).strip() or (a.get("title") or "")
                if not name:
                    continue
                items.append({"vod_id": "folder/tags/%s" % m.group(1),
                              "vod_name": name, "vod_pic": "", "vod_remarks": "",
                              "vod_tag": "folder"})
        else:
            for a in doc.xpath('//a[contains(@href, "/%s/")]' % f_type):
                href = a.get("href") or ""
                m = re.search(r'/%s/([^/]+)/?$' % f_type, href.rstrip("/") + "/")
                if not m:
                    continue
                name = (a.get("title") or "").strip()
                imgs = a.xpath('.//img')
                pic = imgs[0].get("src") or "" if imgs else ""
                if pic.startswith("//"):
                    pic = "https:" + pic
                cnt = ""
                cnts = a.xpath('.//*[contains(@class,"videos")]/text() | .//li/text()')
                for t in cnts:
                    if re.search(r'\d+\s*个视频', t):
                        cnt = t.strip()
                        break
                if not name:
                    strong = a.xpath('.//strong[contains(@class,"title")]/text()')
                    if strong:
                        name = "".join(strong).strip()
                if not name:
                    continue
                items.append({"vod_id": "folder/%s/%s" % (f_type, m.group(1)),
                              "vod_name": name, "vod_pic": pic,
                              "vod_remarks": cnt, "vod_tag": "folder"})
        self._cache_set(ck, items)
        return items

    def _fetch_folder(self, f_type, f_val, pg):
        if f_type == "categories":
            base = "/categories/%s/videos/" % f_val
        elif f_type in ("channels", "models"):
            base = "/%s/%s/" % (f_type, f_val)
        else:
            base = "/%s/%s/" % (f_type, f_val)
        return self._fetch_list(base, pg, None)

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        results = [self._detail(str(v)) for v in ids]
        merged = {k: v for k, v in (results[0] or {}).items() if k != "list"}
        merged["list"] = [it for r in results for it in (r.get("list") or [])]
        return merged

    def _split_vod_id(self, vid):
        if "_" in vid:
            vid, slug = vid.split("_", 1)
            return vid, slug
        return vid, ""

    def _detail(self, vid):
        v_id, slug = self._split_vod_id(vid)
        if not slug:
            return {"list": [], "msg": "无效ID"}
        html = self._site_html("/video/%s/%s/" % (v_id, slug))
        if not html:
            return {"list": [], "msg": "详情获取失败"}
        try:
            doc = etree.HTML(html)
        except Exception:
            return {"list": [], "msg": "详情解析失败"}
        name = doc.xpath('string(//h1)').strip()
        if not name:
            name = v_id
        pic = doc.xpath('string(//meta[@property="og:image"]/@content)').strip()
        dur = ""
        durs = doc.xpath('//*[contains(@class,"media-data__list-value")]/text()')
        if durs:
            dur = (durs[0] or "").strip()
        desc = doc.xpath('string(//*[contains(@class,"media-info__desc")])').strip()
        actors = []
        for t in doc.xpath('//*[contains(@class,"media-box__title")]/text()'):
            t = t.strip()
            if t and t not in actors:
                actors.append(t)
        cats, tags = [], []
        for row in doc.xpath('//*[contains(@class,"media-info__lists-row")]'):
            label = "".join(row.xpath('.//*[contains(@class,"media-info__label")]/text()')).strip().rstrip(":").strip()
            btns = []
            for a in row.xpath('.//a[contains(@class,"btn")]'):
                txt = "".join(a.xpath('.//text()')).strip()
                if txt:
                    btns.append(txt)
            if label == "分类":
                cats = btns
            elif label == "标签":
                tags = btns
        vod = {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "type_name": "、".join(cats),
            "vod_year": "",
            "vod_area": "",
            "vod_remarks": dur,
            "vod_director": "",
            "vod_actor": "、".join(actors),
            "vod_content": desc,
            "vod_play_from": "正片",
            "vod_play_url": "正片$" + vid,
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        kw = str(key or "").strip()
        if not kw:
            return {"list": [], "page": pg, "pagecount": 1, "limit": PAGE_SIZE, "total": 0}
        items = self._fetch_list("/search/%s/" % quote(kw, safe=""), 1, None)
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pg if len(items) < PAGE_SIZE else 9999,
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def playerContent(self, flag, id, vipFlags):
        v_id, slug = self._split_vod_id(str(id or ""))
        if not slug:
            return {"parse": 0, "msg": "无效ID"}
        url = self._resolve_play(v_id, slug)
        if not url:
            return {"parse": 0, "msg": "播放地址获取失败"}
        return {"parse": 0, "jx": 0, "url": url}

    def _resolve_play(self, v_id, slug):
        ck = "P|%s_%s" % (v_id, slug)
        hit = self._cache_get(ck)
        if hit:
            return hit
        host = self._get_host()
        html = self._site_html("/video/%s/%s/" % (v_id, slug))
        if not html:
            return ""
        m = re.search(r"video_url\s*:\s*'([^']+)'", html)
        if not m:
            return ""
        gf = m.group(1)
        if not gf.startswith("http"):
            gf = host + "/" + gf.lstrip("/")
        ref = host + "/"
        m3u8 = ""
        net = getattr(self, "net", None)
        if net is not None and not hasattr(net, "_native") and hasattr(net, "reqParts"):
            try:
                parts = net.reqParts(gf, self._net_opts({
                    "redirect": 0, "cookie": True,
                    "headers": {"Referer": ref, "User-Agent": UA},
                    "timeout": 15000}))
                if parts:
                    meta = parts[0]
                    if isinstance(meta, str):
                        meta = json.loads(meta)
                    hd = (meta or {}).get("headers") or {}
                    m3u8 = hd.get("Location") or hd.get("location") or ""
            except Exception:
                m3u8 = ""
        elif net is not None:
            resp = self._req(gf, redirect=0, cookie=True,
                             headers={"Referer": ref, "User-Agent": UA}, timeout=15000)
            resp = self._resp_dict(resp)
            if (resp.get("code") or 0) in (301, 302):
                hd = resp.get("headers") or {}
                m3u8 = hd.get("Location") or hd.get("location") or ""
        else:
            resp = self._req(gf, redirect=0, cookie=True,
                             headers={"Referer": ref, "User-Agent": UA}, timeout=15000)
            resp = self._resp_dict(resp)
            if (resp.get("code") or 0) in (301, 302):
                hd = resp.get("headers") or {}
                m3u8 = hd.get("Location") or hd.get("location") or ""
        if m3u8:
            self._cache_set(ck, m3u8)
        return m3u8

    def _filters(self, classes):
        sort_filter = {
            "key": "order", "name": "排序", "init": "",
            "value": [
                {"n": "最新", "v": ""},
                {"n": "最热", "v": "video_viewed"},
                {"n": "评分", "v": "rating"},
                {"n": "最长", "v": "duration"},
                {"n": "收藏", "v": "most_favourited"},
            ],
        }
        return {c["type_id"]: [sort_filter] for c in classes}

    def _int(self, x, d=0):
        try:
            return int(x)
        except Exception:
            return d

    def _cache_del(self, key):
        with self._lock:
            self._cache.pop(key, None)
            self._cache_time.pop(key, None)

    def getProxyUrl(self, params=None, local=True):
        try:
            from com.github.catvod import Proxy
            url = Proxy.getUrl(local)
            sk = getattr(self, "siteKey", "") or ""
            return url + "?do=py" + ("&siteKey=%s" % sk if sk else "")
        except Exception:
            return ""

    def proxyUrl(self, params=None, local=True):
        return self.getProxyUrl(params, local)

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

    def proxy(self, params):
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                return [404, "text/plain", ""]
        if not isinstance(params, dict):
            return [404, "text/plain", ""]
        ptype = params.get("type") or ""
        url = params.get("url") or ""
        if ptype == "pic" and url:
            net = getattr(self, "net", None)
            if net is not None and hasattr(net, "reqParts"):
                try:
                    body = net.reqParts(url, {"buffer": 3})[1]
                except Exception:
                    body = b""
            elif net is not None:
                try:
                    body = net.req(url, {"buffer": 3})["content"]
                except Exception:
                    body = b""
            else:
                body = b""
            if body:
                return [200, "image/jpeg", self._bytes_stream(body), {}]
        if ptype in ("m3u8", "variant") and url:
            resp = self._req(url, timeout=15000)
            resp = self._resp_dict(resp)
            code = resp.get("code") or 0
            if 200 <= code < 300:
                text = resp.get("content", "")
                if isinstance(text, bytes):
                    text = text.decode("utf-8", "replace")
                return [200, "application/vnd.apple.mpegurl", text, {}]
        return [404, "text/plain", ""]

    localProxy = proxy

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", str(url)))

    def manualVideoCheck(self):
        return False
