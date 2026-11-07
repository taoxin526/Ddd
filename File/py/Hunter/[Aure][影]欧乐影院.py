# -*- coding: utf-8 -*-
# [欧乐影院  更新于:2026-11-04 22:09]
import json
import re
import time
import threading
import gzip
import zlib
import urllib.request
from urllib.parse import quote, unquote

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        def proxy(self, params):
            return [404, "text/plain", ""]
        def localProxy(self, params):
            return [404, "text/plain", ""]

NAME = "欧乐影院"
HOSTS = ["https://www.olevod.one"]
UA = "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 60
CACHE_TTL = 30
DEBUG = False
VOD_ID_PREFIX = ""
STYLE = {"type": "rect", "ratio": 1.33}

CATS = [
    ("movie", "电影"),
    ("tv", "连续剧"),
    ("show", "综艺"),
    ("anime", "动漫"),
]


class Spider(BaseSpider):

    def __init__(self):
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self._cache = {}
        self._cache_time = {}
        self._lock = threading.Lock()

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
        if tid.startswith("actor/") or tid.startswith("director/") or tid.startswith("tag/"):
            name = unquote(tid.split("/", 1)[1])
            items = self._fetch_search(name, pg)
            return self._page(items, pg)
        items = self._fetch_list(tid, pg, extend or {})
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
        play_from_parts = []
        play_url_parts = []
        for src_name, src_eps in eps:
            lines = []
            for i, ep in enumerate(src_eps, 1):
                title = self._safe_label(ep.get("name") or f"第{i}集")
                url = ep.get("url") or ""
                if url:
                    lines.append(f"{title}${url}")
            if lines:
                play_from_parts.append(src_name)
                play_url_parts.append("#".join(lines))
        play_from = "$$$".join(play_from_parts) if play_from_parts else "正片"
        play_url = "$$$".join(play_url_parts) if play_url_parts else ""
        if not play_url:
            url = data.get("url") or ""
            play_from = "正片"
            play_url = f"正片${url}" if url else ""
        vod = {
            "vod_id": vid,
            "vod_name": data.get("name") or vid,
            "vod_pic": self._abs(data.get("pic") or ""),
            "type_name": data.get("category") or "",
            "vod_year": str(data.get("year") or ""),
            "vod_area": data.get("area") or "",
            "vod_remarks": data.get("remarks") or "",
            "vod_director": self._clickable("director", data.get("director") or ""),
            "vod_actor": "、".join(self._clickable("actor", a) for a in (data.get("actors") or [])),
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
        return {"parse": 0, "jx": 0, "url": url, "header": self._string_map({"User-Agent": UA})}

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
        return [404, "text/plain", ""]

    localProxy = proxy


    def _safe_label(self, text):
        return str(text or "").replace("$", "＄").replace("#", "＃").strip()

    def _clickable(self, kind, name):
        if not name:
            return ""
        ident = f"{kind}/{quote(name, safe='')}"
        payload = json.dumps({"id": ident, "name": name, "type_flag": "0"}, ensure_ascii=False, separators=(",", ":"))
        return f"[a=cr:{payload}/]{name}[/a]"

    def _resp_dict(self, resp):
        if isinstance(resp, dict):
            return resp
        if isinstance(resp, str):
            return {"code": 200, "content": resp, "headers": {}, "error": None}
        if isinstance(resp, (bytes, bytearray)):
            return {"code": 200, "content": resp, "headers": {}, "error": None}
        return {"code": 0, "content": "", "headers": {}, "error": str(resp)}

    def _classes(self):
        return [{"type_id": c, "type_name": n} for c, n in CATS]

    def _filters(self, classes):
        return {}

    def _home_items(self):
        html = self._get_html(self.host + "/")
        return self._parse_cards(html)

    def _fetch_list(self, tid, pg, extend):
        cat = str(tid or "movie").strip()
        url = f"{self.host}/type/filter/{quote(cat, safe='')}?page={pg}"
        html = self._get_html(url)
        return self._parse_cards(html)

    def _fetch_search(self, keyword, pg):
        url = f"{self.host}/search.html?wd={quote(keyword, safe='')}"
        html = self._get_html(url)
        return self._parse_cards(html)

    def _parse_cards(self, html):
        if not html:
            return []
        items = []
        seen = set()
        for m in re.finditer(r'<a[^>]*class="vodlist_thumb[^"]*"[^>]*href="(/vod/\d+)"[^>]*title="([^"]*)"[^>]*data-original="([^"]*)"', html):
            href, title, pic = m.group(1), m.group(2), m.group(3)
            vid = re.search(r'/vod/(\d+)', href).group(1)
            if vid in seen:
                continue
            seen.add(vid)
            tail = html[m.end():m.end() + 1200]
            rem = ""
            msub = re.search(r'<p class="vodlist_sub">(.*?)</p>', tail, re.S)
            if msub:
                rem = self._clean_text(msub.group(1))
            elif re.search(r'span class="pic_text[^"]*"[^>]*>([^<]*)<', tail):
                mup = re.search(r'span class="pic_text[^"]*"[^>]*>([^<]*)<', tail)
                if mup:
                    rem = mup.group(1).strip()
            items.append({"id": vid, "name": title, "pic": pic, "remarks": rem})
        return items

    def _fetch_detail(self, vid):
        vid = re.sub(r'\D', '', str(vid))
        if not vid:
            return {}
        html = self._get_html(f"{self.host}/vod/{vid}")
        if not html:
            return {}
        html = re.sub(r'<!--.*?-->', '', html, flags=re.S)
        name = ""
        m = re.search(r'<h1 class="title[^"]*"[^>]*>\s*([^<]+)', html)
        if m:
            name = m.group(1).strip()
        pic = ""
        m = re.search(r'<span class="vodlist_thumb lazyload"[^>]*data-original="([^"]*)"', html)
        if m:
            pic = m.group(1)
        category = ""
        m = re.search(r'<span class="text_muted hidden_xs">类型：</span>\s*(?:<a[^>]*>)?([^<]+)', html)
        if m:
            category = m.group(1).strip()
        year = ""
        m = re.search(r'<span class="text_muted hidden_xs">年份：</span>\s*(?:<a[^>]*>)?([^<]+)', html)
        if m:
            year = m.group(1).strip()
        area = ""
        m = re.search(r'<span class="text_muted hidden_xs">地区：</span>\s*(?:<a[^>]*>)?([^<]+)', html)
        if m:
            area = m.group(1).strip()
        director = ""
        m = re.search(r'<span>导演：</span>\s*(.*?)</li>', html, re.S)
        if m:
            director = self._clean_text(m.group(1))
        actors = []
        m = re.search(r'<span>(?:主演|演员)：</span>\s*(.*?)</li>', html, re.S)
        if m:
            raw = m.group(1)
            actors = [x.strip() for x in re.split(r'&nbsp;\s*|\s+', raw) if x.strip()]
        description = ""
        m = re.search(r'<span class="left text_muted">简介：</span>\s*(.*?)</li>', html, re.S)
        if m:
            description = self._clean_text(m.group(1))
        remarks = ""
        m = re.search(r'更新至\s*([^<]+)', html)
        if m:
            remarks = m.group(1).strip()
        episodes = self._parse_episodes(html, vid)
        return {
            "name": name, "pic": pic, "category": category, "year": year,
            "area": area, "director": director, "actors": actors,
            "description": description, "remarks": remarks, "episodes": episodes,
        }

    def _parse_episodes(self, html, vid):
        episodes = []
        boxes = re.findall(r'<ul class="content_playlist clearfix">(.*?)</ul>', html, re.S)
        if not boxes:
            return episodes
        src_eps = []
        for box in boxes:
            eps = []
            for m in re.finditer(r'<a[^>]*href="(/vod/' + re.escape(vid) + r'/play/[^"]+)"[^>]*>\s*([^<]+)\s*</a>', box):
                href = m.group(1).strip()
                label = m.group(2).strip()
                lazy = self._lazy_url(href)
                if lazy:
                    eps.append({"name": label, "url": lazy})
            if eps:
                eps = self._sort_eps(eps)
                src_eps.append(("正片", eps))
        if not src_eps:
            m = re.search(r'<a[^>]*href="(/vod/' + re.escape(vid) + r'/play/[^"]+)"[^>]*>\s*([^<]+)\s*</a>', html)
            if m:
                lazy = self._lazy_url(m.group(1).strip())
                if lazy:
                    src_eps.append(("正片", [{"name": m.group(2).strip(), "url": lazy}]))
        return src_eps

    def _sort_eps(self, eps):
        if not eps or len(eps) < 2:
            return eps
        def _num(e):
            m = re.search(r'第\s*(\d+)\s*集', e.get("name") or "")
            if not m:
                m = re.search(r'(\d+)', e.get("name") or "")
            return int(m.group(1)) if m else None
        nums = [_num(e) for e in eps]
        if all(n is not None for n in nums):
            return sorted(eps, key=_num)
        return eps

    def _lazy_url(self, href):
        m = re.search(r'/vod/(\d+)/play/([^?#]+)', href)
        if not m:
            return ""
        vid = m.group(1)
        slug = m.group(2)
        q = re.search(r'[?&]ep=([^&]+)', href)
        ep = unquote(q.group(1)) if q else unquote(slug)
        return f"{self.host}/_olevod_lazy/{vid}-{ep}"

    def _fetch_play(self, play_id):
        play_id = str(play_id or "").strip()
        if not play_id:
            return ""
        if not play_id.startswith("http"):
            return ""
        data = self._get_json(play_id)
        if not data:
            return ""
        plays = data.get("video_plays") or []
        if not plays:
            return ""
        def _score(p):
            u = p.get("play_data") or ""
            if not u:
                return -1
            score = 0
            if not p.get("is_pv"):
                score += 10
            if re.search(r'\.(m3u8|mp4|flv|mkv|ts)(\?|$)', u):
                score += 5
            return score
        best = max(plays, key=_score)
        return (best.get("play_data") or "")

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("id") or "")
        return {
            "vod_id": vid,
            "vod_name": item.get("name") or item.get("title") or vid,
            "vod_pic": self._abs(item.get("pic") or ""),
            "vod_remarks": item.get("remarks") or "",
        }

    def _clean_text(self, text):
        if not text:
            return ""
        text = re.sub(r'<[^>]+>', ' ', text)
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&#160;', ' ')
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _abs(self, u):
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return self.host.rstrip("/") + u
        return u

    def _page(self, items, pg):
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pg if len(items) < PAGE_SIZE else 9999,
            "limit": PAGE_SIZE,
            "total": len(items),
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

    def _req(self, url, **kw):
        net = getattr(self, 'net', None)
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
                code = resp.getcode() or 0
                return {"code": code, "content": raw.decode("utf-8", "replace"), "headers": dict(resp.headers), "error": None}
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

    def _get_json(self, url, **kw):
        try:
            text = self._get_html(url, **kw)
            return json.loads(text) if text else {}
        except Exception:
            return {}
