# -*- coding: utf-8 -*-
import json
import re
import time
import threading
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

NAME = "X红颜"
HOSTS = ["https://xhongyan.com"]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PAGE_SIZE = 24
CACHE_TTL = 60
DEBUG = False
VOD_ID_PREFIX = ""

CATS = [
    ("1", "onlyfans"),
    ("2", "网黄"),
    ("3", "品牌"),
    ("4", "业余"),
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
            result["filters"] = self._filters(classes)
        result["list"] = [self._vod(x) for x in self._home_items()]
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        extend = extend or {}

        if tid.startswith("actor/") or tid.startswith("director/"):
            name = unquote(tid.split("/", 1)[1])
            items = self._fetch_search(name, pg)
            return self._page([self._vod(x) for x in items], pg)

        if tid.startswith("tag/"):
            name = unquote(tid.replace("tag/", "", 1))
            items = self._fetch_tag(name, pg)
            return self._page([self._vod(x) for x in items], pg)

        items = self._fetch_list(tid, pg, extend)
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
        if eps:
            lines = []
            for i, ep in enumerate(eps, 1):
                title = self._safe_label(ep.get("name") or f"第{i}集")
                url = ep.get("url") or ep.get("play_url") or ""
                if url:
                    lines.append(f"{title}${url}")
            play_url = "#".join(lines)
            play_from = data.get("source_name") or data.get("play_from") or "DPlayer-H5播放器"
        else:
            url = data.get("url") or data.get("play_url") or vid
            play_url = f"正片${url}"
            play_from = data.get("source_name") or data.get("play_from") or "DPlayer-H5播放器"

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
        url = self._fetch_play(str(id or ""))
        if not url:
            return {"parse": 0, "msg": "无法获取播放地址"}
        result = {
            "parse": 0,
            "jx": 0,
            "url": url,
            "header": self._string_map({"User-Agent": UA, "Referer": self.host + "/"}),
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

    @staticmethod
    def _string_map(value):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            return {}
        return {str(k): str(v) for k, v in value.items() if v is not None}

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
                resp = net.req(url, opts)
                return resp or {}
            except Exception:
                return {}
        return self._req_urllib(url, **kw)

    def _req_urllib(self, url, **kw):
        try:
            timeout = (kw.get("timeout") or 15000) / 1000.0
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": self.host + "/"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
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
        content = resp.get("content", "")
        if isinstance(content, (bytes, bytearray)):
            return content.decode("utf-8", "replace")
        return content

    def _fix_url(self, u):
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/") and self.host:
            return self.host.rstrip("/") + u
        return u

    def _filters(self, classes):
        sort_filter = {
            "key": "order", "name": "排序", "init": "time",
            "value": [{"n": "最新上架", "v": "time"}, {"n": "人气最高", "v": "hits"}],
        }
        return {c["type_id"]: [sort_filter] for c in classes}

    def _home_items(self):
        html = self._get_html(self.host + "/")
        if not html:
            return []
        return self._parse_cards(html)

    def _fetch_list(self, tid, pg, extend):
        order = extend.get("order") or "time"
        if order not in ("time", "hits"):
            order = "time"
        url = "%s/index.php/vod/show/by/%s/id/%s/page/%d" % (self.host, order, tid, pg)
        html = self._get_html(url)
        if not html:
            return []
        return self._parse_cards(html)

    def _fetch_tag(self, tag, pg):
        url = "%s/index.php/vod/search/tag/%s.html" % (self.host, quote(tag, safe=""))
        if pg and pg > 1:
            url = "%s/index.php/vod/search/page/%d/tag/%s.html" % (self.host, pg, quote(tag, safe=""))
        html = self._get_html(url)
        if not html:
            return []
        return self._parse_cards(html)

    def _fetch_search(self, keyword, pg):
        url = "%s/index.php/vod/search/wd/%s.html" % (self.host, quote(keyword, safe=""))
        if pg and pg > 1:
            url = "%s/index.php/vod/search/page/%d/wd/%s.html" % (self.host, pg, quote(keyword, safe=""))
        html = self._get_html(url)
        if not html:
            return []
        return self._parse_cards(html)

    def _parse_cards(self, html):
        cards = []
        if not html:
            return cards
        try:
            from lxml import etree
            tree = etree.HTML(html)
            for a in tree.xpath('//a[contains(@class,"videoBox") and contains(@href,"/index.php/vod/play/id/")]'):
                href = a.get("href") or ""
                m = re.search(r'/index.php/vod/play/id/(\d+)/', href)
                if not m:
                    continue
                vid = m.group(1)
                pic = ""
                imgs = a.xpath('.//img[contains(@class,"index-lazy-img")]/@data-src')
                if imgs:
                    pic = imgs[0]
                if not pic:
                    imgs2 = a.xpath('.//img[contains(@class,"index-lazy-img")]/@src')
                    if imgs2 and "lazyload" not in imgs2[0]:
                        pic = imgs2[0]
                if not pic:
                    covers = a.xpath('.//div[contains(@class,"videoBox-cover")]/@style')
                    if covers:
                        m2 = re.search(r'url\(["\']?([^"\')]+)', covers[0])
                        if m2:
                            pic = m2.group(1).replace('&quot;', '')
                name = ""
                titles = a.xpath('.//span[contains(@class,"title")]/text()')
                if titles:
                    name = titles[0].strip()
                remarks = ""
                corner = a.xpath('.//span[contains(@class,"video-corner-hd")]/@data-text')
                times = a.xpath('.//span[contains(@class,"videoBox-time")]/text()')
                if times:
                    t0 = times[0].strip()
                    if ":" in t0:
                        remarks = t0
                if not remarks and corner:
                    remarks = corner[0].strip()
                if not remarks and times:
                    remarks = times[0].strip()
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

    def _fetch_detail(self, vid):
        url = "%s/index.php/vod/play/id/%s/sid/1/nid/1.html" % (self.host, vid)
        html = self._get_html(url)
        if not html:
            return None
        try:
            from lxml import etree
            tree = etree.HTML(html)
        except Exception:
            tree = None

        name = ""
        if tree is not None:
            t = tree.xpath('//h1[contains(@class,"video-title")]/text()')
            if t:
                name = t[0].strip()
        if not name:
            m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
            if m:
                name = m.group(1).strip()

        pic = ""
        if tree is not None:
            m = re.search(r'id="J_prismPlayer"[^>]*style="[^"]*background-image:\s*url\(&quot;([^&]*)', html)
            if not m:
                m = re.search(r'background-image:\s*url\(&quot;([^&]*)', html)
            if m:
                pic = m.group(1)
        if not pic:
            m = re.search(r'<img[^>]+src="(/upload/[^"]+)"[^>]*alt="[^"]*"', html)
            if m:
                pic = m.group(1)

        tags = []
        if tree is not None:
            for a in tree.xpath('//span[contains(@class,"tags")]//a[contains(@href,"/index.php/vod/search/tag/")]'):
                tag_name = "".join(a.itertext()).strip()
                if tag_name:
                    tags.append(tag_name)

        pub_time = ""
        m = re.search(r'上传时间：</span><span>([^<]*)', html)
        if m:
            pub_time = m.group(1).strip()

        play_url = ""
        m = re.search(r'var\s+player_data\s*=\s*(\{.*?\})\s*</script>', html, re.S)
        if m:
            try:
                pd = json.loads(m.group(1))
                u = pd.get("url") or ""
                if u:
                    play_url = self._fix_url(u)
            except Exception:
                pass
        if not play_url:
            u = self._extract_m3u8(html)
            if u:
                play_url = u

        episodes = []
        play_page = self._fix_url("/index.php/vod/play/id/%s/sid/1/nid/1.html" % vid)
        if play_page:
            episodes.append({"name": "第1集", "url": play_page})

        desc = tags[0] if tags else ""
        actor = "、".join(tags)
        return {
            "name": name,
            "pic": self._fix_url(pic),
            "episodes": episodes,
            "category": "",
            "year": "",
            "area": "",
            "remarks": pub_time,
            "duration": "",
            "director": "",
            "actors": [],
            "description": desc,
            "source_name": "DPlayer-H5播放器",
        }

    def _fetch_play(self, play_id):
        url = play_id
        if not url:
            return ""
        if not url.startswith("http"):
            if "/index.php/vod/play/" in url:
                url = self._fix_url(url)
            else:
                url = "%s/index.php/vod/play/id/%s/sid/1/nid/1.html" % (self.host, url)
        html = self._get_html(url)
        if not html:
            return ""
        m = re.search(r'var\s+player_data\s*=\s*(\{.*?\})\s*</script>', html, re.S)
        if m:
            try:
                pd = json.loads(m.group(1))
                u = pd.get("url") or ""
                if u:
                    return self._fix_url(u)
            except Exception:
                pass
        u = self._extract_m3u8(html)
        return u

    def _extract_m3u8(self, html):
        if not html:
            return ""
        patterns = [
            r'var\s+now\s*=\s*["\']([^"\']+)["\']',
            r'var\s+playurl\s*=\s*["\']([^"\']+)["\']',
            r'(https?://[^\s"\']+\.m3u8[^\s"\']*)',
            r'(https?://[^\s"\']+\.mp4[^\s"\']*)',
        ]
        for p in patterns:
            m = re.search(p, html)
            if m:
                return self._fix_url(m.group(1))
        return ""

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("id") or item.get("vod_id") or "")
        return {
            "vod_id": self._vod_id(vid),
            "vod_name": item.get("name") or item.get("title") or vid,
            "vod_pic": item.get("pic") or item.get("vod_pic") or "",
            "vod_remarks": item.get("remarks") or item.get("duration") or "",
        }
