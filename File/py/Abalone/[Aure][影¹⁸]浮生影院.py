# -*- coding: utf-8 -*-
# [浮生影院¹⁸  更新于:2026-11-05 16:35]
import json
import re
import threading
import time
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

NAME = "浮生影院"
HOSTS = ["https://tv.fushengr.cc"]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PAGE_SIZE = 20
CACHE_TTL = 60
VOD_ID_PREFIX = ""

CATS = [
    ("cate17", "乱伦之爱"),
    ("cate29", "一手原创"),
    ("cate37", "独家热播"),
    ("cate47", "福利姬"),
    ("cate65", "优选UP"),
    ("cate81", "P站精选"),
    ("cate98", "国产传媒"),
    ("cate113", "日本AV"),
    ("cate129", "性癖"),
    ("cate138", "动漫"),
    ("cate148", "欧美"),
    ("cate162", "劲爆综艺"),
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
        self._last_fetch_error = ""

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
        classes = [{"type_id": t, "type_name": n} for t, n in CATS]
        result = {"class": classes}
        if filter:
            result["filters"] = {}
        result["list"] = [self._vod(x) for x in self._home_items()]
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        extend = extend or {}

        if tid.startswith("tag/"):
            name = unquote(tid.replace("tag/", "", 1))
            items = self._fetch_tag(name, pg)
            return self._page([self._vod(x) for x in items], pg)

        if tid.startswith("group/"):
            items = self._group_items(tid.replace("group/", "", 1))
            total = len(items)
            start = (pg - 1) * PAGE_SIZE
            page_items = items[start:start + PAGE_SIZE]
            pagecount = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE) if total else 1
            return {
                "list": [self._vod(x) for x in page_items],
                "page": pg,
                "pagecount": pagecount,
                "limit": PAGE_SIZE,
                "total": total,
            }

        items = self._group_items(tid)
        total = len(items)
        start = (pg - 1) * PAGE_SIZE
        page_items = items[start:start + PAGE_SIZE]
        pagecount = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE) if total else 1
        return {
            "list": [self._vod(x) for x in page_items],
            "page": pg,
            "pagecount": pagecount,
            "limit": PAGE_SIZE,
            "total": total,
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
            err = getattr(self, "_last_fetch_error", "") or ""
            msg = "未找到此影片"
            if err:
                msg = "未找到此影片(%s)" % err
            return {"list": [], "msg": msg}
        url = data.get("url") or data.get("play_url") or ""
        play_url = f"正片${url}" if url else ""
        play_from = data.get("source_name") or "浮生影院"
        vod = {
            "vod_id": self._vod_id(vid),
            "vod_name": data.get("name") or vid,
            "vod_pic": data.get("pic") or "",
            "type_name": data.get("category") or "",
            "vod_year": str(data.get("year") or ""),
            "vod_area": data.get("area") or "",
            "vod_remarks": data.get("remarks") or data.get("duration") or "",
            "vod_director": self._clickable("director", data.get("director") or ""),
            "vod_actor": "、".join(self._clickable("actor", a) for a in data.get("actors") or []),
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
        url = str(id or "")
        if url and not url.startswith("http"):
            url = ""
        if not url:
            return {"parse": 0, "msg": "无法获取播放地址"}
        result = {
            "parse": 0,
            "jx": 0,
            "url": url,
        }
        return result

    def liveContent(self, url):
        return "[]"

    def proxy(self, params):
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                return [404, "text/plain", ""]
        return [404, "text/plain", ""]

    localProxy = proxy

    def _safe_label(self, text):
        return str(text or "").replace("$", "＄").replace("#", "＃").strip()

    def _vod_id(self, site_id):
        return f"{VOD_ID_PREFIX}{site_id}" if VOD_ID_PREFIX else str(site_id)

    def _clickable(self, kind, name):
        if not name:
            return ""
        ident = f"{kind}/{quote(name, safe='')}"
        payload = json.dumps({"id": ident, "name": name, "type_flag": "0"}, ensure_ascii=False, separators=(",", ":"))
        return f"[a=cr:{payload}/]{name}[/a]"

    def _int(self, x, d=0):
        try:
            return int(x)
        except Exception:
            return d

    def _page(self, items, pg):
        try:
            page = max(1, int(pg))
        except (TypeError, ValueError):
            page = 1
        total = len(items)
        start = (page - 1) * PAGE_SIZE
        has_more = total >= PAGE_SIZE
        return {
            "list": items[start:start + PAGE_SIZE],
            "page": page,
            "pagecount": 9999 if has_more else page,
            "limit": PAGE_SIZE,
            "total": total,
        }

    def _req(self, url, **kw):
        net = getattr(self, 'net', None)
        if net is not None:
            try:
                opts = {"timeout": kw.get("timeout", 15000)}
                for k in ("params", "headers", "method", "postType", "data", "body", "buffer", "redirect", "callTimeout", "cookie"):
                    if k in kw and kw[k] is not None:
                        opts[k] = kw[k]
                if "headers" not in opts or not opts["headers"]:
                    opts["headers"] = {"User-Agent": UA, "Referer": self.host + "/"}
                resp = net.req(url, opts)
                return resp or {}
            except Exception:
                return {}
        return self._req_urllib(url, **kw)

    def _req_urllib(self, url, **kw):
        try:
            timeout = (kw.get("timeout") or 15000) / 1000.0
            hdrs = dict(kw.get("headers") or {})
            hdrs.setdefault("User-Agent", UA)
            hdrs.setdefault("Referer", self.host + "/")
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                code = resp.getcode() or 0
                return {"code": code, "content": raw.decode("utf-8", "replace"), "headers": dict(resp.headers), "error": None}
        except Exception as e:
            return {"code": 0, "content": "", "headers": {}, "error": str(e)}

    def _get_html(self, url, **kw):
        retries = kw.get("retries", 3)
        last = None
        for attempt in range(retries):
            resp = self._req(url, **kw)
            if resp.get("error"):
                last = "error:%s" % resp.get("error")
                if attempt < retries - 1:
                    time.sleep(0.4)
                    continue
                break
            code = resp.get("code") or 0
            if not 200 <= code < 300:
                last = "code:%s" % code
                if attempt < retries - 1:
                    time.sleep(0.4)
                    continue
                break
            content = resp.get("content", "")
            if isinstance(content, (bytes, bytearray)):
                return content.decode("utf-8", "replace")
            if isinstance(content, list):
                try:
                    return bytes(content).decode("utf-8", "replace")
                except Exception:
                    return ""
            if content is None:
                return ""
            return str(content)
        self._last_fetch_error = last
        return None

    def _fix_url(self, u):
        if not u:
            return ""
        u = str(u).strip()
        if u.startswith("https:/") and not u.startswith("https://"):
            u = "https://" + u[7:]
        elif u.startswith("http:/") and not u.startswith("http://"):
            u = "http://" + u[6:]
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/") and self.host:
            return self.host.rstrip("/") + u
        return u

    def _home_items(self):
        html = self._get_html(self.host + "/")
        if not html:
            return []
        items = self._parse_cards(html)
        return self._dedup(items)

    def _group_items(self, tid):
        key = "group_" + tid
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        html = self._get_html("%s/group-category/%s/" % (self.host, tid))
        if not html:
            return []
        items = self._dedup(self._parse_cards(html))
        self._cache_set(key, items)
        return items

    def _fetch_tag(self, tag, pg):
        url = "%s/tag/%s/" % (self.host, quote(tag, safe=""))
        if pg and pg > 1:
            url = "%s/tag/%s/%d/" % (self.host, quote(tag, safe=""), pg)
        html = self._get_html(url)
        if not html:
            return []
        return self._parse_cards(html)

    def _fetch_search(self, keyword, pg):
        url = "%s/search/%s/" % (self.host, quote(keyword, safe=""))
        if pg and pg > 1:
            url = "%s/search/%s/%d/" % (self.host, quote(keyword, safe=""), pg)
        html = self._get_html(url)
        if not html:
            return []
        return self._parse_cards(html)

    def _dedup(self, items):
        seen = set()
        out = []
        for it in items:
            vid = str(it.get("id") or "")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            out.append(it)
        return out

    def _cache_get(self, key):
        now = time.time()
        with self._lock:
            if key in self._cache_time and now - self._cache_time[key] < CACHE_TTL:
                return self._cache.get(key)
        return None

    def _cache_set(self, key, value):
        now = time.time()
        with self._lock:
            self._cache[key] = value
            self._cache_time[key] = now

    def _in_side(self, el):
        node = el.getparent()
        while node is not None:
            tag = node.tag
            if not isinstance(tag, str):
                node = node.getparent()
                continue
            if tag == "aside":
                return True
            cls = node.get("class") or ""
            if "fg2-side" in cls or "side" in cls:
                return True
            node = node.getparent()
        return False

    def _parse_cards(self, html):
        cards = []
        if not html:
            return cards
        try:
            from lxml import etree
            tree = etree.HTML(html)
            for a in tree.xpath('//a[contains(@href, "/video/")]'):
                if self._in_side(a):
                    continue
                href = a.get("href") or ""
                m = re.search(r'/video/(\d+)', href)
                if not m:
                    continue
                vid = m.group(1)
                pic = ""
                imgs = a.xpath('.//img/@data-src') or a.xpath('.//img/@src')
                for s in imgs:
                    if s and "loading" not in s:
                        pic = s
                        break
                name = ""
                for sel in ('.//h3//text()', './/strong//text()', './/em//text()'):
                    t = a.xpath(sel)
                    if t:
                        name = "".join(t).strip()
                        if name:
                            break
                if not name:
                    t = a.xpath('.//div[contains(@class,"fg2-card-copy")]//text()')
                    name = " ".join(x.strip() for x in t if x.strip())
                if not name:
                    al = a.get("aria-label") or ""
                    name = re.sub(r'-\d+$', '', al).strip()
                remarks = ""
                d = a.xpath('.//span[contains(@class,"fg2-duration")]/text()')
                if d:
                    remarks = d[0].strip()
                cards.append({
                    "id": vid,
                    "name": name or vid,
                    "pic": self._fix_url(pic),
                    "remarks": remarks,
                    "url": self._fix_url(href),
                })
        except Exception:
            pass
        return cards

    def _extract_archive_player(self, html):
        m = re.search(r'window\.__ARCHIVE_PLAYER__\s*=\s*(\{.*?\});', html, re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(1))
        except Exception:
            return None

    def _fetch_detail(self, vid):
        url = "%s/video/%s/" % (self.host, vid)
        html = self._get_html(url)
        if not html:
            return None

        name = ""
        m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        if m:
            name = m.group(1).strip()

        ap = self._extract_archive_player(html)
        pic = ""
        if ap:
            pic = self._fix_url(ap.get("posterImg") or "")
        if not pic:
            m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
            if m:
                pic = self._fix_url(m.group(1))

        tags = []
        for m in re.finditer(r'<a[^>]+href="/tag/([^"]+)/"[^>]*class="fg2-tag"[^>]*>(.*?)</a>', html):
            tname = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            if tname:
                tags.append(tname)
        if not tags:
            for m in re.finditer(r'<a[^>]+href="/tag/([^"]+)/"[^>]*>(.*?)</a>', html):
                tname = re.sub(r'<[^>]+>', '', m.group(2)).strip()
                if tname and tname not in tags:
                    tags.append(tname)

        remarks = ""
        m = re.search(r'时长\s*([^<]*)<', html)
        if m:
            remarks = m.group(1).strip()

        category = ""
        m = re.search(r'class="[^"]*breadcrumb[^"]*"[^>]*>(.*?)</nav>', html, re.S)
        if m:
            crumbs = re.findall(r'<a[^>]+href="/category/([^"]+)/"[^>]*>(.*?)</a>', m.group(1), re.S)
            if crumbs:
                category = re.sub(r'<[^>]+>', '', crumbs[-1][1]).strip()
        if not category and tags:
            category = tags[0]

        play_url = ""
        if ap:
            raw = ap.get("rawPath") or ""
            cdn = ap.get("cdnLine") or ""
            if raw:
                if raw.startswith("http"):
                    play_url = self._fix_url(raw)
                else:
                    play_url = self._fix_url(cdn + raw)
        if not play_url:
            m = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', html)
            if m:
                play_url = self._fix_url(m.group(1))

        desc = ""
        if tags:
            desc = "标签：" + "、".join(self._clickable("tag", t) for t in tags)

        return {
            "name": name or vid,
            "pic": pic,
            "url": play_url,
            "category": category,
            "year": "",
            "area": "",
            "remarks": remarks,
            "duration": remarks,
            "director": "",
            "actors": [],
            "description": desc,
            "source_name": "浮生影院",
        }

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("id") or item.get("vod_id") or "")
        return {
            "vod_id": self._vod_id(vid),
            "vod_name": item.get("name") or item.get("title") or vid,
            "vod_pic": item.get("pic") or item.get("vod_pic") or "",
            "vod_remarks": item.get("remarks") or item.get("duration") or "",
        }
