# -*- coding: utf-8 -*-
import json
import re
import time
import threading
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

NAME = "AVJOY"
HOSTS = ["https://cn.avjoy.me", "https://avjoy.me"]
UA = "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 16
CACHE_TTL = 30
DEBUG = False
VOD_ID_PREFIX = ""

CATS = [
    ("jav", "JAV・日本AV"), ("china", "China・中國"), ("asian", "Asian・アジア"),
    ("japan", "Japan・日本"), ("uncensored", "Uncensored・無修正"),
    ("pornstar", "Pornstar·AV女優"), ("big-tits", "Big Tits・巨乳"),
    ("amateur", "Amateur・素人"), ("anal", "Anal・アナル・肛交"),
    ("anime", "Anime・アニメ"), ("cosplay", "Cosplay・コスプレ"),
    ("korea", "Korea・韓国・대한민국"), ("mature", "Mature・熟女"),
    ("schoolgirl", "Schoolgirl・女子校生"), ("sm", "SM"),
    ("teen", "Teen・ギャル・少女"), ("wife", "Wife・人妻"),
]

ORDERS = [("最新", "mr"), ("最受歡迎", "mv"), ("最高評分", "tr"), ("最愛", "tf")]


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
        extend = extend or {}
        if tid.startswith("actor/") or tid.startswith("director/"):
            name = unquote(tid.split("/", 1)[1])
            items, has_more = self._fetch_search(name, pg)
            return self._page([self._vod(x) for x in items], pg, has_more)
        if tid.startswith("tag/"):
            name = unquote(tid.replace("tag/", "", 1))
            items, has_more = self._fetch_search(name, pg)
            return self._page([self._vod(x) for x in items], pg, has_more)
        order = (extend.get("order") or "").strip()
        items, has_more = self._fetch_list(tid, pg, order)
        return self._page([self._vod(x) for x in items], pg, has_more)

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
        url = data.get("url") or ""
        vod = {
            "vod_id": self._vod_id(vid),
            "vod_name": data.get("name") or vid,
            "vod_pic": self._pic(data),
            "type_name": "",
            "vod_year": str(data.get("year") or ""),
            "vod_area": "",
            "vod_remarks": data.get("remarks") or "",
            "vod_director": "",
            "vod_actor": "、".join(self._clickable("tag", t) for t in (data.get("tags") or [])),
            "vod_content": data.get("description") or "",
            "vod_play_from": "正片",
            "vod_play_url": (self._safe_label("正片") + "$" + url) if url else "",
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        items, has_more = self._fetch_search(str(key or "").strip(), pg)
        return self._page([self._vod(x) for x in items], pg, has_more)

    def playerContent(self, flag, id, vipFlags):
        play_id = str(id or "")
        vid = self._vid_from_play(play_id)
        url = self._fetch_play(vid)
        if not url:
            return {"parse": 0, "msg": "无法获取播放地址"}
        return {
            "parse": 0,
            "jx": 0,
            "url": url,
            "header": self._string_map({"User-Agent": UA, "Referer": self.host + "/"}),
        }

    def _vid_from_play(self, play_id):
        if not play_id:
            return ""
        if re.match(r"^\d+$", play_id):
            return play_id
        m = re.search(r"(\d+)_\d+p\.mp4", play_id)
        if m:
            return m.group(1)
        m = re.search(r"/video/(\d+)", play_id)
        if m:
            return m.group(1)
        m = re.search(r"/(\d+)/", play_id)
        if m:
            return m.group(1)
        return play_id

    def liveContent(self, url):
        return "[]"

    def _classes(self):
        hit = self._cache.get("__cls")
        if hit and time.time() - self._cache_time.get("__cls", 0) < CACHE_TTL:
            return hit[0]
        arr = [{"type_id": cid, "type_name": nm} for cid, nm in CATS]
        with self._lock:
            self._cache["__cls"] = (arr, time.time())
        return arr

    def _filters(self, classes):
        sort_filter = {
            "key": "order", "name": "排序", "init": "",
            "value": [{"n": n, "v": v} for n, v in ORDERS],
        }
        return {c["type_id"]: [sort_filter] for c in classes}

    def _home_items(self):
        html = self._get_html(self.host + "/")
        return self._parse_cards(html)

    def _fetch_list(self, cid, pg, order):
        url = self.host + "/videos/" + quote(str(cid), safe="")
        params = {}
        if pg and pg > 1:
            params["page"] = pg
        if order:
            params["o"] = order
        html = self._get_html(self._with_params(url, params))
        items = self._parse_cards(html)
        return items, self._has_more(html, pg)

    def _fetch_search(self, kw, pg):
        url = self.host + "/search/videos/" + quote(str(kw), safe="")
        params = {}
        if pg and pg > 1:
            params["page"] = pg
        html = self._get_html(self._with_params(url, params))
        items = self._parse_cards(html)
        return items, self._has_more(html, pg)

    def _has_more(self, html, pg):
        if not html:
            return False
        nums = []
        for m in re.finditer(r"[?&]page=(\d+)", html):
            try:
                nums.append(int(m.group(1)))
            except Exception:
                pass
        return bool(nums and max(nums) > max(1, int(pg)))

    def _fetch_detail(self, vid):
        html = self._get_html(self.host + "/video/" + quote(str(vid), safe=""))
        if not html:
            return {}
        doc = self._doc(html)
        if doc is None:
            return {}
        name = self._text(doc, '//h1[1]')
        if not name:
            return {}
        pic = self._attr(doc, '//meta[@itemprop="thumbnailUrl"]/@content') or self._attr(doc, '//video/@poster')
        src = self._attr(doc, '//source[contains(@src, ".mp4") and not(contains(@type, "av01"))]/@src')
        if not src:
            src = self._attr(doc, '//source[contains(@src, ".mp4")]/@src')
        year = ""
        dt = self._attr(doc, '//time/@datetime')
        if dt:
            m = re.match(r"(\d{4})", dt)
            if m:
                year = m.group(1)
        if not year:
            ago = self._text(doc, '//span[contains(@class, "d-none") and contains(@class, "d-sm-inline")]')
            if not ago:
                ago = self._text(doc, '//div[contains(@class, "card-sub")]')
            m = re.search(r"(\d+)\s*年\s*(?:前|ago)", ago)
            if m:
                year = str(self._int(time.strftime("%Y"), 2026) - self._int(m.group(1), 0))
        desc = self._text(doc, '//div[contains(@class, "video-description")]//p[1]') or self._text(doc, '//section[contains(@class, "video-description")]//p[1]')
        remarks = ""
        dm = self._attr(doc, '//meta[@itemprop="duration"]/@content')
        if dm:
            m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dm)
            if m:
                parts = []
                if m.group(1):
                    parts.append("%d时" % int(m.group(1)))
                if m.group(2):
                    parts.append("%d分" % int(m.group(2)))
                if m.group(3):
                    parts.append("%d秒" % int(m.group(3)))
                remarks = "".join(parts)
        tags = [t for t in self._texts(doc, '//a[contains(@class, "tag") and starts-with(@href, "/search/videos/")]') if t]
        if not tags:
            tags = [t for t in self._texts(doc, '//section[contains(@class, "video-tags")]//a[contains(@class, "tag")]') if t]
        return {"name": name, "pic": pic, "url": src, "year": year, "description": desc, "remarks": remarks, "tags": tags}

    def _fetch_play(self, vid):
        html = self._get_html(self.host + "/video/" + quote(str(vid), safe=""))
        if not html:
            return ""
        doc = self._doc(html)
        if doc is None:
            return ""
        return self._attr(doc, '//source[contains(@src, ".mp4") and not(contains(@type, "av01"))]/@src') or self._attr(doc, '//source[contains(@src, ".mp4")]/@src')

    def _parse_cards(self, html):
        if not html:
            return []
        doc = self._doc(html)
        if doc is None:
            return []
        out = []
        seen = set()
        for node in doc.xpath('//div[@id="wrapper"]//div[contains(@class, "col-") and .//div[contains(@class, "thumb-overlay")] and .//a[starts-with(@href, "/video/")]]'):
            a = node.xpath('.//a[starts-with(@href, "/video/")][1]')
            if not a:
                continue
            href = a[0].get("href") or ""
            m = re.search(r"/video/(\d+)/", href)
            if not m:
                continue
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            img = node.xpath('.//img[1]/@src')
            pic = img[0] if img else ""
            dur = node.xpath('.//div[contains(@class, "duration")]')
            remarks = ""
            if dur:
                remarks = "".join(dur[0].itertext()).strip()
            title = node.xpath('.//span[contains(@class, "content-title")]')
            name = ""
            if title:
                name = "".join(title[0].itertext()).strip()
            out.append({"id": vid, "name": name, "pic": pic, "remarks": remarks})
        return out

    def _norm_dur(self, text):
        if not text:
            return 0
        m = re.search(r"(\d+):(\d+):(\d+)", text)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        m = re.search(r"(\d+):(\d+)", text)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2))
        return 0

    def _doc(self, html):
        try:
            return etree.HTML(html)
        except Exception:
            return None

    def _text(self, doc, xp):
        vals = doc.xpath(xp)
        if not vals:
            return ""
        if isinstance(vals[0], etree._Element):
            return "".join(vals[0].itertext()).strip()
        return str(vals[0]).strip()

    def _texts(self, doc, xp):
        out = []
        for v in doc.xpath(xp):
            if isinstance(v, etree._Element):
                t = "".join(v.itertext()).strip()
            else:
                t = str(v).strip()
            if t:
                out.append(t)
        return out

    def _attr(self, doc, xp):
        vals = doc.xpath(xp)
        return str(vals[0]).strip() if vals else ""

    def _safe_label(self, text):
        return str(text or "").replace("$", "＄").replace("#", "＃").strip()

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("id") or "")
        return {
            "vod_id": self._vod_id(vid),
            "vod_name": item.get("name") or vid,
            "vod_pic": item.get("pic") or "",
            "vod_remarks": item.get("remarks") or "",
        }

    def _pic(self, item):
        for k in ("img_y", "cover", "pic", "img", "thumb", "vod_pic"):
            v = item.get(k)
            if v:
                return v
        return ""

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
    def _string_map(value, name="headers"):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            return {}
        return {str(k): str(v) for k, v in value.items() if v is not None}

    def _page(self, items, pg, has_more=None):
        try:
            page = max(1, int(pg))
        except (TypeError, ValueError):
            page = 1
        total = len(items)
        if has_more is None:
            has_more = total >= PAGE_SIZE
        return {
            "list": items,
            "page": page,
            "pagecount": 9999 if has_more else page,
            "limit": PAGE_SIZE,
            "total": total,
        }

    def _with_params(self, url, params):
        if not params:
            return url
        sep = "&" if "?" in url else "?"
        return url + sep + "&".join("%s=%s" % (k, quote(str(v), safe="")) for k, v in params.items())

    def _req(self, url, **kw):
        net = getattr(self, "net", None)
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
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"}, method="GET")
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
        return resp.get("content", "")
