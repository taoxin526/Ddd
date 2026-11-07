# -*- coding: utf-8 -*-
# [禁片天堂¹⁸  更新于:2026-11-07 02:30]
import json
import re
import time
import threading
import base64
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

NAME = "禁片天堂"
HOSTS = ["https://jptt.tv"]
BASE = "/cn"
UA = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 30
CACHE_TTL = 120
DEBUG = False
VOD_ID_PREFIX = ""

CATS = [
    ("latest", "最新"),
    ("hot_today", "今日热门"),
    ("hot_week", "本周热门"),
    ("hot_month", "本月热门"),
    ("tag-2", "中出"),
    ("tag-15", "巨乳"),
    ("tag-9", "素人"),
    ("tag-16", "人妻"),
    ("tag-5", "自拍"),
    ("tag-75", "痴女"),
    ("tag-7", "720p"),
    ("tag-3", "AV女优片"),
    ("tag-21", "HD"),
    ("folder/tag/_", "🗂️ 更多分类"),
    ("folder/actor/_", "💃 女优"),
    ("folder/factory/_", "🎬 发行商"),
    ("folder/vlist/_", "🔢 连播"),
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
        result = {"class": self._classes()}
        if filter:
            result["filters"] = self._filters(result["class"])
        result["list"] = [self._vod(x) for x in self._home_items()]
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        tid = str(tid or "").strip("/")
        if tid.startswith("actor/") or tid.startswith("director/"):
            name = unquote(tid.split("/", 1)[1])
            return self._search_result(name, pg)
        if tid.startswith("tag/"):
            name = unquote(tid.replace("tag/", "", 1))
            return self._search_result(name, pg)
        if tid.startswith("folder/"):
            parts = tid.split("/", 2)
            if len(parts) == 3:
                f_type, f_value = parts[1], unquote(parts[2])
                if not f_value or f_value == "_":
                    items = self._fetch_folder_entries(f_type)
                    return {
                        "list": items,
                        "page": pg,
                        "pagecount": pg if len(items) < PAGE_SIZE else 9999,
                        "limit": PAGE_SIZE,
                        "total": 999999,
                    }
                items, pc = self._fetch_folder(f_type, f_value, pg)
                return {
                    "list": [self._vod(x) for x in items],
                    "page": pg,
                    "pagecount": pc if pc else (pg if len(items) < PAGE_SIZE else 9999),
                    "limit": PAGE_SIZE,
                    "total": 999999,
                }
        items = self._fetch_list(tid, pg, extend or {})
        pc = self._pagecount_of(tid)
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pc if pc else (pg if len(items) < PAGE_SIZE else 9999),
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        responses = [self._detail(str(video_id)) for video_id in ids]
        merged = {k: v for k, v in (responses[0] or {}).items() if k != "list"} if responses[0] else {}
        merged["list"] = [item for response in responses if response for item in (response.get("list") or [])]
        return merged

    def _detail(self, vid):
        vid = str(vid or "").strip()
        if VOD_ID_PREFIX and vid.startswith(VOD_ID_PREFIX):
            vid = vid[len(VOD_ID_PREFIX):]
        data = self._fetch_detail(vid)
        if not data:
            return {"list": [], "msg": "未找到此影片"}
        url = data.get("url") or ""
        vod = {
            "vod_id": vid,
            "vod_name": data.get("name") or vid,
            "vod_pic": self._pic_url(data.get("pic") or ""),
            "type_name": data.get("category") or "",
            "vod_year": data.get("year") or "",
            "vod_area": "",
            "vod_remarks": data.get("remarks") or "",
            "vod_director": "",
            "vod_actor": "、".join(self._clickable("actor", a) for a in data.get("actors") or []),
            "vod_content": data.get("description") or "",
            "vod_play_from": "正片",
            "vod_play_url": "正片$" + vid,
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        return self._search_result(str(key or "").strip(), pg)

    def _search_result(self, keyword, pg):
        items = self._fetch_search(keyword, pg)
        pc = self._search_pagecount(keyword)
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pc if pc else (pg if len(items) < PAGE_SIZE else 9999),
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def _search_pagecount(self, keyword):
        key = "spc:" + str(keyword)
        hit = self._cache.get(key)
        if hit and time.time() - self._cache_time.get(key, 0) < CACHE_TTL:
            return hit
        kw = quote(keyword, safe="")
        html = self._get_html(self._abs("/search?kw=%s&sort=2" % kw))
        pc = 0
        if html:
            m = re.search(r'name="idx"[^>]*max="(\d+)"', html)
            if m:
                pc = self._int(m.group(1))
            if not pc:
                pages = [int(x) for x in re.findall(r"idx=(\d+)", html)]
                pc = max(pages) if pages else 0
        with self._lock:
            self._cache[key] = pc
            self._cache_time[key] = time.time()
        return pc

    def playerContent(self, flag, id, vipFlags):
        vid = str(id or "")
        if VOD_ID_PREFIX and vid.startswith(VOD_ID_PREFIX):
            vid = vid[len(VOD_ID_PREFIX):]
        url = self._fetch_play(vid)
        if not url:
            return {"parse": 0, "msg": "无法获取播放地址"}
        return {
            "parse": 0,
            "jx": 0,
            "url": url,
            "header": self._string_map({"User-Agent": UA, "Referer": self.host + "/"}),
            "format": "application/x-mpegURL",
        }

    def liveContent(self, url):
        return "[]"

    def proxy(self, params):
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                return [404, "text/plain", ""]
        if not isinstance(params, dict):
            return [404, "text/plain", ""]
        if params.get("type") == "pic":
            real = params.get("url") or ""
            try:
                real = self._d64(real)
            except Exception:
                pass
            raw = self._download(real)
            if not raw:
                return [404, "text/plain", ""]
            img = self._pic_decrypt(raw)
            return [200, self._mime(img), self._img_stream(img), {}]
        return [404, "text/plain", ""]

    localProxy = proxy

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

    def _classes(self):
        hit = self._cache.get("__cls")
        if hit and time.time() - self._cache_time.get("__cls", 0) < CACHE_TTL:
            return hit
        arr = [{"type_id": tid, "type_name": nm} for tid, nm in CATS]
        with self._lock:
            self._cache["__cls"] = arr
            self._cache_time["__cls"] = time.time()
        return arr

    def _filters(self, classes):
        return {}

    def _home_items(self):
        html = self._get_html(self._abs("/"))
        if not html:
            return []
        return self._parse_cards(html)

    def _fetch_list(self, tid, pg, extend):
        url = self._list_url(tid, pg)
        if not url:
            return []
        html = self._get_html(url)
        if not html:
            return []
        return self._parse_cards(html)

    def _list_url(self, tid, pg):
        if tid == "latest":
            return self._abs("/list?sort=2") if pg <= 1 else self._abs("/list?idx=%d&sort=2" % pg)
        if tid == "hot_today":
            return self._abs("/list?sort=3") if pg <= 1 else self._abs("/list?idx=%d&sort=3" % pg)
        if tid == "hot_week":
            return self._abs("/list?sort=4") if pg <= 1 else self._abs("/list?idx=%d&sort=4" % pg)
        if tid == "hot_month":
            return self._abs("/list?sort=5") if pg <= 1 else self._abs("/list?idx=%d&sort=5" % pg)
        m = re.match(r"^tag-(\d+)$", tid)
        if m:
            t = m.group(1)
            return self._abs("/tag_list?tid=%s" % t) if pg <= 1 else self._abs("/tag_list?id=%s&idx=%d" % (t, pg))
        return ""

    def _fetch_search(self, keyword, pg):
        keyword = (keyword or "").strip()
        if not keyword:
            return []
        kw = quote(keyword, safe="")
        if pg <= 1:
            url = self._abs("/search?kw=%s&sort=2" % kw)
        else:
            url = self._abs("/search?kw=%s&idx=%d&sort=2" % (kw, pg))
        html = self._get_html(url)
        if not html:
            return []
        return self._parse_cards(html)

    def _fetch_detail(self, vid):
        vid = str(vid or "").strip().split("?")[0]
        if not vid:
            return None
        url = self._abs("/video/" + quote(vid, safe="-_.~"))
        html = self._get_html(url)
        if not html:
            return None
        name = ""
        m = re.search(r'<h1[^>]*class="h1_title"[^>]*>([\s\S]*?)</h1>', html)
        if m:
            name = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if not name:
            m = re.search(r'property="og:title"\s+content="([^"]+)"', html)
            if m:
                name = m.group(1).strip()
        if not name:
            return None
        pic = ""
        m = re.search(r'<video[^>]+poster="([^"]+)"', html)
        if m:
            pic = m.group(1)
        if not pic:
            m = re.search(r'property="og:image"\s+content="([^"]+)"', html)
            if m:
                pic = m.group(1)
        actors = []
        tags = []
        factories = []
        info = html[html.find("info-list"):] if "info-list" in html else html
        for am in re.finditer(r'/cn/actor\?id=(\d+)"[^>]*>([^<]+)<', info):
            nm = am.group(2).strip()
            if nm and nm not in actors:
                actors.append(nm)
        for tm in re.finditer(r'/cn/tag_list\?tid=(\d+)"[^>]*>([^<]+)<', info):
            nm = tm.group(2).strip()
            if nm and nm not in tags:
                tags.append(nm)
        for fm in re.finditer(r'/cn/tag_list\?fid=(\d+)"[^>]*>([^<]+)<', info):
            nm = fm.group(2).strip()
            if nm and nm not in factories:
                factories.append(nm)
        desc = ""
        m = re.search(r'class="info_original[^"]*"[^>]*>([\s\S]*?)</div>', html)
        if m:
            desc = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        remarks = ""
        m = re.search(r'class="video-item"[^>]*>[\s\S]*?fa-clock[^>]*></i>([^<]+)<', html)
        if m:
            remarks = m.group(1).strip()
        category = factories[0] if factories else (tags[0] if tags else "")
        year = ""
        m = re.search(r"(\d{4})-\d{2}-\d{2}", remarks or "")
        if m:
            year = m.group(1)
        parts = []
        parts.append("番号：" + vid)
        if actors:
            parts.append("女优：" + "、".join(actors))
        if tags:
            parts.append("标签：" + "、".join(self._clickable("tag", t) for t in tags))
        if factories:
            parts.append("厂商：" + "、".join(self._clickable("tag", f) for f in factories))
        if remarks:
            parts.append("日期：" + remarks)
        content = "\n".join(parts)
        if desc:
            content += "\n\n" + desc
        play_url = self._extract_play(html)
        return {
            "name": name,
            "pic": pic,
            "category": category,
            "year": year,
            "remarks": remarks,
            "actors": actors,
            "description": content,
            "url": play_url,
        }

    def _extract_play(self, html):
        m = re.search(r'<source[^>]+data-src="(//[^"]+?\.m3u8[^"]*)"', html)
        if m:
            return self._fix(m.group(1))
        m = re.search(r'videoSourceUrl\s*=\s*"(.*?\.m3u8[^"]*)"', html)
        if m:
            return self._fix(m.group(1).replace("\\/", "/"))
        m = re.search(r'(https?:)?//[^\s"\']+\.m3u8[^\s"\']*', html)
        if m:
            return self._fix(m.group(0))
        return ""

    def _fetch_play(self, vid):
        data = self._fetch_detail(vid)
        if not data:
            return ""
        url = data.get("url") or ""
        if url:
            return url
        return ""

    def _fetch_folder_entries(self, type_):
        if type_ == "tag":
            return self._parse_type_items(self._get_html(self._abs("/tag?sort=3")), "tag")
        if type_ == "actor":
            return self._parse_idol_items(self._get_html(self._abs("/actor_list")))
        if type_ == "factory":
            return self._parse_type_items(self._get_html(self._abs("/factory?sort=1")), "factory")
        if type_ == "vlist":
            return self._parse_vlist_cards(self._get_html(self._abs("/video_list")))
        return []

    def _fetch_folder(self, type_, value, pg):
        value = str(value or "").strip()
        if type_ == "tag":
            url = self._abs("/tag_list?tid=%s" % value) if pg <= 1 else self._abs("/tag_list?id=%s&idx=%d" % (value, pg))
            html = self._get_html(url)
            return self._parse_cards(html or ""), self._pag(html)
        if type_ == "actor":
            url = self._abs("/actor?id=%s&sort=2" % value) if pg <= 1 else self._abs("/actor?id=%s&idx=%d&sort=2" % (value, pg))
            html = self._get_html(url)
            return self._parse_cards(html or ""), self._pag(html)
        if type_ == "factory":
            url = self._abs("/tag_list?fid=%s" % value) if pg <= 1 else self._abs("/tag_list?fid=%s&idx=%d" % (value, pg))
            html = self._get_html(url)
            return self._parse_cards(html or ""), self._pag(html)
        if type_ == "vlist":
            html = self._get_html(self._abs("/video_list_info?id=%s" % value))
            items = self._parse_vlist_episodes(html or "")
            total = len(items)
            start = (pg - 1) * PAGE_SIZE
            sl = items[start:start + PAGE_SIZE]
            return sl, ((total + PAGE_SIZE - 1) // PAGE_SIZE if total else 1)
        return [], 0

    def _parse_type_items(self, html, type_):
        items = []
        if not html:
            return items
        for m in re.finditer(r'<div class="type-item">([\s\S]*?)</div>\s*</div>', html):
            seg = m.group(1)
            if type_ == "tag":
                lm = re.search(r'href="[^"]*?/tag_list\?tid=(\d+)"', seg)
            else:
                lm = re.search(r'href="[^"]*?/tag_list\?fid=(\d+)"', seg)
            if not lm:
                continue
            ident = lm.group(1)
            nm = ""
            mt = re.search(r'<h5[^>]*>([^<]+)</h5>', seg)
            if mt:
                nm = mt.group(1).strip()
            cnt = ""
            mc = re.search(r'<p[^>]*>([^<]*部[^<]*)</p>', seg)
            if mc:
                cnt = mc.group(1).strip()
            if not nm:
                nm = ident
            items.append(self._folder_vod(type_, ident, nm, cnt))
        return items

    def _parse_idol_items(self, html):
        items = []
        if not html:
            return items
        for m in re.finditer(r'<div class="idol-item">([\s\S]*?)</div>\s*</div>', html):
            seg = m.group(1)
            lm = re.search(r'href="[^"]*?/actor\?id=(\d+)"', seg)
            if not lm:
                continue
            ident = lm.group(1)
            nm = ""
            mt = re.search(r'<h5[^>]*>([^<]+)</h5>', seg)
            if mt:
                nm = mt.group(1).strip()
            pic = ""
            mp = re.search(r'src="([^"]*actors/avatar[^"]*)"', seg)
            if mp:
                pic = self._pic_url(self._fix(mp.group(1)))
            if not nm:
                nm = ident
            card = self._folder_vod("actor", ident, nm, "")
            if pic:
                card["vod_pic"] = pic
            items.append(card)
        return items

    def _parse_vlist_cards(self, html):
        items = []
        if not html:
            return items
        for m in re.finditer(r'<div class="col oneVideo vdo_lst_cover[^"]*">([\s\S]*?)(?=<div class="col oneVideo|</div>\s*</div>\s*</div>\s*</div>)', html):
            seg = m.group(1)
            lm = re.search(r'href="[^"]*?/video_list_info\?id=(\d+)"', seg)
            if not lm:
                continue
            ident = lm.group(1)
            nm = ""
            mt = re.search(r'<h3[^>]*>([^<]+)</h3>', seg)
            if mt:
                nm = mt.group(1).strip()
            pic = ""
            mp = re.search(r'src="([^"]*video_list[^"]*)"', seg)
            if mp:
                pic = self._pic_url(self._fix(mp.group(1)))
            cnt = ""
            mc = re.search(r'(\d+)部', seg)
            if mc:
                cnt = mc.group(1) + "部"
            if not nm:
                nm = ident
            card = self._folder_vod("vlist", ident, nm, cnt)
            if pic:
                card["vod_pic"] = pic
            items.append(card)
        return items

    def _parse_vlist_episodes(self, html):
        items = []
        seen = set()
        if not html:
            return items
        for seg in re.split(r'<div class="row div_v_list_item">', html)[1:]:
            lm = re.search(r'/cn/video/([^"\']+)', seg)
            if not lm:
                continue
            code = lm.group(1).split("?")[0]
            if code in seen:
                continue
            seen.add(code)
            nm = ""
            mt = re.search(r'<h3[^>]*>([^<]+)</h3>', seg)
            if mt:
                nm = mt.group(1).strip()
            pic = ""
            mp = re.search(r'src="([^"]*storage/cover[^"]*)"', seg)
            if mp:
                pic = self._fix(mp.group(1))
            if not nm:
                nm = code
            items.append({"id": code, "name": nm, "pic": pic, "remarks": ""})
        return items

    def _parse_cards(self, html):
        cards = []
        seen = set()
        for m in re.finditer(r'<div class="col oneVideo[^"]*">([\s\S]*?)(?=<div class="col oneVideo|\Z)', html):
            seg = m.group(1)
            lm = re.search(r'/cn/video/([^"\']+)', seg)
            if not lm:
                continue
            code = lm.group(1).split("?")[0]
            if code in seen:
                continue
            name = ""
            mt = re.search(r'alt="([^"]+)"', seg)
            if mt:
                name = mt.group(1)
            if not name:
                mt = re.search(r'<h[35][^>]*>([\s\S]*?)</h[35]>', seg)
                if mt:
                    name = re.sub(r"<[^>]+>", "", mt.group(1)).strip()
            name = self._unescape(name).strip()
            pic = ""
            mp = re.search(r'src="([^"]*storage/cover[^"]*)"', seg)
            if mp:
                pic = self._fix(mp.group(1))
            remarks = ""
            md = re.search(r'class="p_duration">([^<]+)<', seg)
            if md:
                remarks = md.group(1).strip()
            mtg = re.search(r'class="p_show_tag[^"]*">([^<]+)<', seg)
            if mtg and remarks:
                remarks = mtg.group(1).strip() + "|" + remarks
            elif mtg:
                remarks = mtg.group(1).strip()
            if not name:
                name = code
            seen.add(code)
            cards.append({"id": code, "name": name, "pic": pic, "remarks": remarks})
        return cards

    def _folder_vod(self, type_, value, name, count=None):
        card = {
            "vod_id": self._folder_id(type_, value),
            "vod_name": str(name or value or ""),
            "vod_pic": "",
            "vod_remarks": ("%s" % count) if count else "",
            "vod_tag": "folder",
        }
        return card

    def _folder_id(self, type_, value):
        return "folder/%s/%s" % (type_, quote(str(value), safe=""))

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

    def _pagecount_of(self, tid):
        key = "pc:" + str(tid)
        hit = self._cache.get(key)
        if hit and time.time() - self._cache_time.get(key, 0) < CACHE_TTL:
            return hit
        m = re.match(r"^tag-(\d+)$", tid)
        if m:
            t = m.group(1)
            html = self._get_html(self._abs("/tag_list?tid=%s" % t))
        elif tid == "latest":
            html = self._get_html(self._abs("/list?sort=2"))
        elif tid == "hot_today":
            html = self._get_html(self._abs("/list?sort=3"))
        elif tid == "hot_week":
            html = self._get_html(self._abs("/list?sort=4"))
        elif tid == "hot_month":
            html = self._get_html(self._abs("/list?sort=5"))
        else:
            return 0
        pc = self._pag(html)
        with self._lock:
            self._cache[key] = pc
            self._cache_time[key] = time.time()
        return pc

    @staticmethod
    def _pag(html):
        if not html:
            return 0
        pages = [int(x) for x in re.findall(r"idx=(\d+)", html)]
        return max(pages) if pages else 0

    def _abs(self, path):
        return self.host.rstrip("/") + BASE + "/" + str(path).lstrip("/")

    def _fix(self, u):
        if not u:
            return ""
        u = u.strip()
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return self.host.rstrip("/") + u
        return u

    @staticmethod
    def _unescape(s):
        try:
            import html as _h
            return _h.unescape(s)
        except Exception:
            return s

    def _req(self, url, **kw):
        net = getattr(self, "net", None)
        if net is not None:
            try:
                opts = {"timeout": kw.get("timeout", 15000)}
                for k in ("params", "headers", "method", "postType", "data", "body", "buffer", "redirect"):
                    if k in kw and kw[k] is not None:
                        opts[k] = kw[k]
                resp = net.req(url, opts)
                return resp or {}
            except Exception:
                return {}
        return self._req_urllib(url, **kw)

    def _req_urllib(self, url, **kw):
        try:
            import gzip as _g
            import zlib as _z
            timeout = (kw.get("timeout") or 15000) / 1000.0
            headers = dict(kw.get("headers") or {})
            headers.setdefault("User-Agent", UA)
            headers.setdefault("Accept", "*/*")
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                enc = (resp.headers.get("Content-Encoding") or "").lower()
                if enc == "gzip":
                    raw = _g.decompress(raw)
                elif enc == "deflate":
                    raw = _z.decompress(raw)
                return {"code": resp.getcode() or 0, "content": raw.decode("utf-8", "replace"), "headers": dict(resp.headers), "error": None}
        except Exception as e:
            return {"code": 0, "content": "", "headers": {}, "error": str(e)}

    def _get_html(self, url):
        resp = self._req(url)
        if resp.get("error"):
            return None
        code = resp.get("code") or 0
        if not 200 <= code < 300:
            return None
        return resp.get("content", "")

    def _download(self, url):
        url = self._fix(url)
        if not url:
            return b""
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
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.read()
        except Exception:
            return b""

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
        u = self._fix(u)
        if not u:
            return ""
        try:
            p = self._proxy_url({"type": "pic", "url": self._e64(u)})
            return p or u
        except Exception:
            return u

    @staticmethod
    def _e64(s):
        return base64.urlsafe_b64encode(str(s).encode("utf-8")).decode("ascii")

    @staticmethod
    def _d64(s):
        try:
            return base64.urlsafe_b64decode(str(s).encode("ascii")).decode("utf-8", "replace")
        except Exception:
            return str(s)

    @staticmethod
    def _pic_decrypt(raw):
        return raw

    @staticmethod
    def _mime(data):
        if data[:2] == b"\xff\xd8":
            return "image/jpeg"
        if data[:4] == b"\x89PNG":
            return "image/png"
        if data[:3] == b"GIF":
            return "image/gif"
        if data[:4] == b"RIFF":
            return "image/webp"
        return "image/jpeg"

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("id") or item.get("vod_id") or "")
        return {
            "vod_id": vid,
            "vod_name": item.get("name") or item.get("title") or vid,
            "vod_pic": item.get("pic") or self._pic_url(item.get("pic") or ""),
            "vod_remarks": item.get("remarks") or item.get("duration") or "",
        }

    @staticmethod
    def _string_map(value, name="headers"):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            return {}
        return {str(k): str(v) for k, v in value.items() if v is not None}

    def _clickable(self, kind, name):
        if not name:
            return ""
        ident = "%s/%s" % (kind, quote(name, safe=""))
        payload = json.dumps({"id": ident, "name": name, "type_flag": "0"}, ensure_ascii=False, separators=(",", ":"))
        return "[a=cr:%s/]%s[/a]" % (payload, name)

    @staticmethod
    def _int(x, d=0):
        try:
            return int(x)
        except Exception:
            return d
