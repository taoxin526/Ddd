# -*- coding: utf-8 -*-
# [GGJAV¹⁸  更新于:2026-11-05 16:30]
import json
import re
import time
import base64
import threading
import urllib.request
from urllib.parse import quote, unquote, urlparse, parse_qs

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        def proxy(self, params):
            return [404, "text/plain", ""]
        def localProxy(self, params):
            return [404, "text/plain", ""]

NAME = "GGJAV"
HOSTS = ["https://ggjav.com"]
UA = "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 23
CACHE_TTL = 30
DEBUG = False
VOD_ID_PREFIX = ""

CATS = [
    ("censored", "有碼AV"),
    ("uncensored", "無碼AV"),
    ("chinese", "中文字幕"),
    ("cartoon", "卡通"),
    ("amateur", "素人"),
    ("europe", "歐美"),
]
ORDERS = [
    {"n": "推薦", "v": "recommended"},
    {"n": "最新", "v": "pub_date"},
    {"n": "按讚", "v": "likes"},
    {"n": "瀏覽", "v": "views"},
]


class Spider(BaseSpider):

    def __init__(self):
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self._cache = {}
        self._cache_time = {}
        self._lock = threading.Lock()
        self.options = {}

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
            items = self._fetch_search(name, pg)
            return {"list": [self._vod(x) for x in items], "page": pg,
                    "pagecount": pg if len(items) < PAGE_SIZE else 9999, "limit": PAGE_SIZE, "total": 999999}

        if tid.startswith("tag/"):
            name = unquote(tid.replace("tag/", "", 1))
            items = self._fetch_search(name, pg)
            return {"list": [self._vod(x) for x in items], "page": pg,
                    "pagecount": pg if len(items) < PAGE_SIZE else 9999, "limit": PAGE_SIZE, "total": 999999}

        if tid.startswith("folder/"):
            parts = tid.split("/", 2)
            if len(parts) == 3:
                f_type, f_value = parts[1], unquote(parts[2])
                if not f_value or f_value == "_":
                    items = self._fetch_folder_entries(f_type)
                    out = items
                else:
                    raw = self._fetch_folder(f_type, f_value, pg)
                    out = [self._vod(x) for x in raw]
                return {
                    "list": out,
                    "page": pg,
                    "pagecount": pg if len(out) < PAGE_SIZE else 9999,
                    "limit": PAGE_SIZE,
                    "total": 999999,
                }

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
        url = data.get("url") or ""
        if url:
            play_from = "正片"
            play_url = "正片$%s" % url
        else:
            play_from = "正片"
            play_url = ""

        vod = {
            "vod_id": self._vod_id(vid),
            "vod_name": data.get("name") or vid,
            "vod_pic": self._pic(data),
            "type_name": data.get("category") or "",
            "vod_year": str(data.get("year") or ""),
            "vod_area": data.get("area") or "",
            "vod_remarks": data.get("remarks") or "",
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
            "parse": 0 if self._is_direct(url) else 1,
            "jx": 0,
            "url": url,
            "header": self._string_map({"User-Agent": UA, "Referer": self.host + "/"}),
        }
        return result

    def liveContent(self, url):
        return "[]"


    def _safe_label(self, text):
        return str(text or "").replace("$", "＄").replace("#", "＃").strip()

    def _vod_id(self, site_id):
        return f"{VOD_ID_PREFIX}{site_id}" if VOD_ID_PREFIX else str(site_id)

    def _folder_id(self, type_, value):
        return f"folder/{type_}/{quote(value, safe='')}"

    def _folder_vod(self, type_, value, name, count=None, pic=""):
        card = {
            "vod_id": self._folder_id(type_, value),
            "vod_name": str(name or value or ""),
            "vod_pic": pic or "",
            "vod_remarks": ("%s部" % count) if count else "",
            "vod_tag": "folder",
        }
        return card

    def _clickable(self, kind, name):
        if not name:
            return ""
        ident = f"{kind}/{quote(name, safe='')}"
        payload = json.dumps(
            {"id": ident, "name": name, "type_flag": "0"},
            ensure_ascii=False,
            separators=(",", ":"),
        )
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
        arr = []
        for tid, nm in CATS:
            arr.append({"type_id": tid, "type_name": nm})
        arr.append({"type_id": "folder/model/_", "type_name": "💃 女優"})
        arr.append({"type_id": "folder/ctg/_", "type_name": "🗂️ 類別"})
        return arr

    def _filters(self, classes):
        sort_filter = {
            "key": "order",
            "name": "排序",
            "init": "recommended",
            "value": ORDERS,
        }
        result = {}
        for c in classes:
            tid = c["type_id"]
            if tid.startswith("folder/"):
                result[tid] = []
            else:
                result[tid] = [sort_filter]
        return result

    def _home_items(self):
        return self._fetch_list("censored", 1, {})

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("id") or item.get("vod_id") or "")
        return {
            "vod_id": self._vod_id(vid),
            "vod_name": item.get("name") or item.get("title") or vid,
            "vod_pic": self._pic(item),
            "vod_remarks": item.get("remarks") or "",
        }

    def _pic(self, item):
        for k in ("pic", "cover", "img", "vod_pic"):
            v = item.get(k)
            if v:
                return v
        return ""

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
        start = (page - 1) * PAGE_SIZE
        if has_more is None:
            has_more = total >= PAGE_SIZE
        return {
            "list": items[start:start + PAGE_SIZE],
            "page": page,
            "pagecount": 9999 if has_more else page,
            "limit": PAGE_SIZE,
            "total": total,
        }

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
            data = None
            method = (kw.get("method") or "GET").upper()
            params = kw.get("params")
            if params:
                sep = "&" if "?" in url else "?"
                url = url + sep + "&".join("%s=%s" % (k, quote(str(v), safe="")) for k, v in params.items())
            headers = dict(kw.get("headers") or {})
            headers.setdefault("User-Agent", UA)
            headers.setdefault("Accept", "*/*")
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
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

    def _fix_url(self, u):
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/") and self.host:
            return self.host.rstrip("/") + u
        return u


    def _fetch_list(self, tid, pg, extend):
        order = (extend or {}).get("order") or "recommended"
        url = "%s/main/%s" % (self.host.rstrip("/"), tid)
        sep = "?" if "?" not in url else "&"
        url = "%s%sorder=%s&page=%d" % (url, sep, quote(str(order), safe=""), pg)
        html = self._get_html(url)
        if not html:
            return []
        return self._parse_cards(html)

    def _parse_cards(self, html):
        items = []
        for block in re.finditer(r'<div[^>]*class="[^"]*\bitem\b[^"]*"[^>]*>(.*?)(?=<div[^>]*class="[^"]*\bitem\b|<div[^>]*class="[^"]*item_title"|$)', html, re.S):
            seg = block.group(1)
            m = re.search(r'href="/main/video\?id=(\d+)"', seg)
            if not m:
                continue
            vid = m.group(1)
            name = ""
            tm = re.search(r'item_title[^>]*>.*?<a[^>]*>(.*?)</a>', seg, re.S)
            if tm:
                name = self._clean(tm.group(1))
            if not name:
                am = re.search(r'<img[^>]*alt="([^"]*)"', seg)
                if am:
                    name = self._clean(am.group(1))
            pic = ""
            pm = re.search(r'<img[^>]*class="item_image"[^>]*src="([^"]+)"', seg)
            if not pm:
                pm = re.search(r'<img[^>]*src="([^"]+)"[^>]*class="item_image"', seg)
            if pm:
                pic = self._fix_url(pm.group(1))
            items.append({"id": vid, "name": name, "pic": pic})
        seen = set()
        out = []
        for it in items:
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            out.append(it)
        return out

    def _clean(self, text):
        return re.sub(r"<[^>]+>", "", text or "").replace("&quot;", '"').replace("&amp;", "&").replace("&#039;", "'").strip()

    def _fetch_detail(self, vid):
        url = "%s/main/video?id=%s" % (self.host.rstrip("/"), vid)
        html = self._get_html(url)
        if not html:
            return {}
        name = ""
        m = re.search(r'class="columns small-12 title_text"[^>]*>([^<]{2,150})', html)
        if m:
            name = self._clean(m.group(1))
        if not name:
            m = re.search(r'property="og:title" content="([^"]+)"', html)
            if m:
                name = self._clean(m.group(1)).split(" - GGJAV")[0].strip()
        pic = ""
        m = re.search(r'property="og:image" content="([^"]+)"', html)
        if m:
            pic = self._fix_url(m.group(1))
        if not pic:
            m = re.search(r'<img[^>]*src="([^"]*media/video/large_[^"]+)"', html)
            if m:
                pic = self._fix_url(m.group(1))
        actors = []
        for m in re.finditer(r'/main/model\?name=([^"&]+)', html):
            nm = unquote(m.group(1))
            if nm and nm not in actors:
                actors.append(nm)
        ctgs = []
        for m in re.finditer(r'/main/ctg\?ctgs=([^"&]+)', html):
            nm = unquote(m.group(1))
            if nm and nm not in ctgs:
                ctgs.append(nm)
        return {
            "name": name,
            "pic": pic,
            "actors": actors,
            "category": "、".join(ctgs),
            "description": "",
            "url": self._resolve_play(html),
        }

    def _resolve_play(self, html):
        m = re.search(r'var l = "([^"]+)"', html)
        if not m:
            return ""
        try:
            raw = base64.b64decode(m.group(1))
            decoded = "".join(chr(b - 0x58) for b in raw)
            links = json.loads(decoded)
        except Exception:
            return ""
        gg = links.get("ggjav") or []
        if gg and gg[0]:
            emb = gg[0]
            u = parse_qs(urlparse(emb).query).get("u", [""])[0]
            if u:
                try:
                    mp4 = base64.b64decode(u).decode()
                    if mp4:
                        return mp4 + "/index.m3u8"
                except Exception:
                    pass
            return emb
        for k, v in links.items():
            if v and v[0]:
                return v[0]
        return ""

    def _fetch_search(self, keyword, pg):
        url = "%s/main/search?string=%s&type=all&page=%d&order=recommended" % (
            self.host.rstrip("/"), quote(str(keyword), safe=""), pg)
        html = self._get_html(url)
        if not html:
            return []
        return self._parse_cards(html)

    def _fetch_folder_entries(self, type_):
        if type_ == "model":
            return self._fetch_model_entries()
        if type_ == "ctg":
            return self._fetch_ctg_entries()
        return []

    def _fetch_model_entries(self):
        out = []
        url = "%s/main/all_censored_model" % self.host.rstrip("/")
        html = self._get_html(url)
        if not html:
            return out
        for m in re.finditer(r'<div[^>]*class="model"[^>]*>\s*<div><a href="/main/model\?name=([^"&]+)"[^>]*>(.*?)</a>', html, re.S):
            nm = unquote(m.group(1))
            seg = m.group(2)
            pic = ""
            pm = re.search(r'src="([^"]+)"', seg)
            if pm:
                pic = self._fix_url(pm.group(1))
            if nm:
                out.append(self._folder_vod("model", nm, nm, None, pic))
        return out

    def _fetch_ctg_entries(self):
        out = []
        url = "%s/main/all_censored_ctg" % self.host.rstrip("/")
        html = self._get_html(url)
        if not html:
            return out
        seen = set()
        for m in re.finditer(r'<input[^>]*type="checkbox"[^>]*value="([^"]+)"[^>]*name="ctgs"', html):
            nm = m.group(1)
            if nm and nm not in seen:
                seen.add(nm)
                out.append(self._folder_vod("ctg", nm, nm, None, ""))
        return out

    def _fetch_folder(self, type_, value, pg):
        if type_ == "model":
            url = "%s/main/model?type=all&name=%s&order=recommended&page=%d" % (
                self.host.rstrip("/"), quote(value, safe=""), pg)
        elif type_ == "ctg":
            url = "%s/main/ctg?type=all&ctgs=%s&order=recommended&page=%d" % (
                self.host.rstrip("/"), quote(value, safe=""), pg)
        else:
            return []
        html = self._get_html(url)
        if not html:
            return []
        return self._parse_cards(html)

    def _fetch_play(self, play_id):
        pid = str(play_id or "")
        if not pid:
            return ""
        if pid.startswith("http"):
            return pid
        url = "%s/main/video?id=%s" % (self.host.rstrip("/"), pid)
        html = self._get_html(url)
        if not html:
            return ""
        return self._resolve_play(html)

    def _is_direct(self, url):
        u = str(url or "")
        if re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", u):
            return True
        if ".ggjav.com" in u and ("/video_" in u or "/hls" in u):
            return True
        return False
