# -*- coding: utf-8 -*-
# [youavhub¹⁸  更新于:2026-11-05 14:47]
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

NAME = "youavhub"
HOSTS = ["https://youavhub.com"]
UA = "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 60
CACHE_TTL = 30
DEBUG = False
VOD_ID_PREFIX = ""

CATS = [
    ("20", "巨乳"), ("21", "熟女人妻"), ("22", "日本AV"), ("23", "中文字幕"),
    ("24", "少女蘿莉"), ("25", "抖陰短片"), ("26", "翹臀美尻"), ("27", "高潮潮吹"),
    ("28", "歐美無碼"), ("29", "亂倫、誘惑"), ("30", "國產素人自拍"), ("31", "成人動漫"),
    ("32", "同性戀"), ("33", "AV女優無碼"), ("34", "制服誘惑"), ("35", "男同志Gay"),
    ("36", "女同志Lesbian"), ("37", "麻豆"), ("38", "SM調教"), ("39", "激情口交"),
    ("40", "野外性愛"), ("41", "多P群交"), ("43", "18+成人激情電影"), ("45", "AI換臉"),
]

ORDERS = [("最新", "latest"), ("最热", "hits"), ("评分", "score")]


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
        letter = (extend.get("letter") or "").strip()
        items, has_more = self._fetch_list(tid, pg, order, letter)
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
        eps = data.get("episodes") or []
        if eps:
            play_url = "#".join(self._safe_label(ep.get("name") or "第1集") + "$" + ep["url"] for ep in eps)
            play_from = data.get("source_name") or "正片"
        else:
            play_url = ""
            play_from = data.get("source_name") or "正片"
        vod = {
            "vod_id": self._vod_id(vid),
            "vod_name": data.get("name") or vid,
            "vod_pic": data.get("pic") or "",
            "type_name": data.get("category") or "",
            "vod_year": str(data.get("year") or ""),
            "vod_area": "",
            "vod_remarks": data.get("remarks") or "",
            "vod_director": "",
            "vod_actor": "、".join(self._clickable("actor", a) for a in (data.get("actors") or [])),
            "vod_content": data.get("description") or "",
            "vod_play_from": play_from,
            "vod_play_url": play_url,
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
            "header": self._string_map({"User-Agent": UA}),
        }

    def _vid_from_play(self, play_id):
        if not play_id:
            return ""
        if re.match(r"^\d+$", str(play_id)):
            return str(play_id)
        m = re.search(r"/play/id/(\d+)", str(play_id))
        if m:
            return m.group(1)
        m = re.search(r"/detail/id/(\d+)", str(play_id))
        if m:
            return m.group(1)
        m = re.search(r"(\d+)", str(play_id))
        if m:
            return m.group(1)
        return str(play_id)

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
            "key": "order", "name": "排序", "init": "latest",
            "value": [{"n": n, "v": v} for n, v in ORDERS],
        }
        letter_values = [{"n": "全部", "v": ""}]
        for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            letter_values.append({"n": ch, "v": ch})
        letter_values.append({"n": "0-9", "v": "0-9"})
        letter_filter = {
            "key": "letter", "name": "字母", "init": "",
            "value": letter_values,
        }
        return {c["type_id"]: [sort_filter, letter_filter] for c in classes}

    def _home_items(self):
        html = self._get_html(self.host + "/")
        items = self._parse_cards(html)
        return items[:240]

    def _fetch_list(self, cid, pg, order, letter=""):
        seg = "by/time"
        if order == "hits":
            seg = "by/hits"
        elif order == "score":
            seg = "by/score"
        url = self.host + "/index.php/vod/show/" + seg
        if letter:
            url += "/letter/" + quote(str(letter), safe="")
        url += "/id/" + quote(str(cid), safe="")
        if pg and pg > 1:
            url += "/page/" + str(pg)
        url += "/"
        html = self._get_html(url)
        items = self._parse_cards(html)
        return items, self._has_more(html, pg, "show/" + seg + "/id/" + str(cid))

    def _fetch_search(self, kw, pg):
        url = self.host + "/index.php/vod/search/wd/" + quote(str(kw), safe="") + ".html"
        if pg and pg > 1:
            url = self.host + "/index.php/vod/search/wd/" + quote(str(kw), safe="") + "/page/" + str(pg) + "/"
        html = self._get_html(url)
        items = self._parse_search(html)
        return items, self._has_more(html, pg, "search/wd/" + str(kw))

    def _has_more(self, html, pg, base):
        if not html:
            return False
        nums = []
        for m in re.finditer(r"/page/(\d+)/", html):
            try:
                nums.append(int(m.group(1)))
            except Exception:
                pass
        return bool(nums and max(nums) > max(1, int(pg)))

    def _fetch_detail(self, vid):
        html = self._get_html(self.host + "/index.php/vod/detail/id/" + quote(str(vid), safe="") + ".html")
        if not html:
            return {}
        doc = self._doc(html)
        if doc is None:
            return {}
        name = self._text(doc, '//div[contains(@class, "content_box")]//h2[contains(@class, "title")][1]')
        if not name:
            name = self._text(doc, '//h2[contains(@class, "title")][1]')
        if not name:
            return {}
        pic = self._attr(doc, '//div[contains(@class, "content_thumb")]//a[contains(@class, "vodlist_thumb")]/@data-original')
        if not pic:
            pic = self._attr(doc, '//a[contains(@class, "vodlist_thumb")]/@data-original')
        year = self._text(doc, '//li[contains(@class, "data")]//a[contains(@href, "/search/year/")]')
        category = self._text(doc, '//li[contains(@class, "data")]//a[contains(@href, "/search/class/")]')
        actors = []
        for a in doc.xpath('//li[contains(@class, "data")]//a[contains(@href, "/search/actor/")]'):
            t = "".join(a.itertext()).strip()
            if t:
                actors.append(t)
        desc = self._text(doc, '//div[contains(@class, "content_desc") and contains(@class, "context")]//span[1]')
        if not desc:
            desc = self._text(doc, '//li[contains(@class, "desc")]')
        if not desc:
            desc = self._text(doc, '//section[contains(@class, "content")]//div[contains(@class, "content_desc")]//span[1]')
        source_name = self._text(doc, '//div[contains(@class, "play_source_tab")]//a[contains(@class, "active")]')
        source_name = re.sub(r'[\ue000-\uf8ff]', '', source_name).strip()
        if not source_name:
            source_name = "正片"
        eps = []
        seen_ep = set()
        for a in doc.xpath('//ul[contains(@class, "content_playlist")]//a'):
            href = a.get("href") or ""
            nm = "".join(a.itertext()).strip()
            m = re.search(r"/play/id/(\d+)", href)
            if not m or m.group(1) != str(vid):
                continue
            if not nm or href in seen_ep:
                continue
            seen_ep.add(href)
            eps.append({"name": nm, "url": self.host + href})
        return {"name": name, "pic": pic, "year": year, "category": category, "actors": actors,
                "description": desc, "source_name": source_name, "episodes": eps}

    def _fetch_play(self, vid):
        url = self.host + "/index.php/vod/play/id/" + quote(str(vid), safe="") + "/sid/1/nid/1/"
        html = self._get_html(url)
        if not html:
            return ""
        m = re.search(r"player_aaaa\s*=\s*(\{.*?\})(?=</script>)", html, re.S)
        if m:
            try:
                data = json.loads(m.group(1))
                u = data.get("url") or ""
                if u:
                    return u
            except Exception:
                pass
        return self._extract_m3u8(html)

    def _parse_cards(self, html):
        if not html:
            return []
        doc = self._doc(html)
        if doc is None:
            return []
        out = []
        seen = set()
        for node in doc.xpath('//li[contains(@class, "vodlist_item")]'):
            a = node.xpath('.//a[contains(@class, "vodlist_thumb")][1]')
            if not a:
                continue
            href = a[0].get("href") or ""
            m = re.search(r"/play/id/(\d+)", href)
            if not m:
                continue
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            name = a[0].get("title") or ""
            if not name:
                t = node.xpath('.//a[contains(@class, "vodlist_title")]/@title')
                if t:
                    name = t[0]
            pic = a[0].get("data-original") or a[0].get("data-src") or a[0].get("src") or ""
            year = ""
            y = node.xpath('.//em[contains(@class, "voddate_year")]/text()')
            if y:
                year = y[0].strip()
            out.append({"id": vid, "name": name, "pic": pic, "remarks": year})
        return out

    def _parse_search(self, html):
        if not html:
            return []
        doc = self._doc(html)
        if doc is None:
            return []
        out = []
        seen = set()
        for node in doc.xpath('//li[contains(@class, "searchlist_item")]'):
            a = node.xpath('.//a[contains(@class, "vodlist_thumb")][1]')
            if not a:
                continue
            href = a[0].get("href") or ""
            m = re.search(r"/play/id/(\d+)", href)
            if not m:
                continue
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            name = a[0].get("title") or ""
            pic = a[0].get("data-original") or a[0].get("data-src") or a[0].get("src") or ""
            out.append({"id": vid, "name": name, "pic": pic, "remarks": ""})
        return out

    def _extract_m3u8(self, html):
        if not html:
            return ""
        m = re.search(r'"(https?://[^"]+\.m3u8[^"]*)"', html)
        if m:
            return m.group(1)
        m = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', html)
        if m:
            return m.group(1)
        m = re.search(r'(https?://[^\s"\']+\.mp4[^\s"\']*)', html)
        if m:
            return m.group(1)
        return ""

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

    def _list(self, data):
        if isinstance(data, list):
            return data
        if not isinstance(data, dict):
            return []
        for k in ("list", "items", "records", "data"):
            v = data.get(k)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                return self._list(v)
        return []

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

    def _get_json(self, url, **kw):
        try:
            text = self._get_html(url, **kw)
            return json.loads(text) if text else {}
        except Exception:
            return {}
