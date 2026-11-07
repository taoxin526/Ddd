# -*- coding: utf-8 -*-
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

NAME = "PigAV"
HOSTS = ["https://pigav.com", "https://pigav.ws"]
UA = "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 24
CACHE_TTL = 60
DEBUG = False
VOD_ID_PREFIX = ""
STYLE = {"type": "rect", "ratio": 1.33}

SORTS = [
    ("publishedAt", "最近更新"),
    ("hot", "热门视频"),
    ("views", "最多观看"),
    ("likes", "最多点赞"),
    ("name", "标题排序"),
    ("duration", "时长排序"),
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
        if tid.startswith("actor/") or tid.startswith("director/") or tid.startswith("tag/"):
            name = unquote(tid.split("/", 1)[1])
            items = self._fetch_tag(name, pg)
            return self._page_result(items, pg)
        items = self._fetch_list(tid, pg, extend)
        return self._page_result(items, pg)

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
            play_url = "#".join(f"{self._safe_label(ep.get('name') or f'第{i}集')}${ep.get('url') or ''}" for i, ep in enumerate(eps, 1))
            play_from = data.get("source_name") or data.get("play_from") or "正片"
        else:
            url = data.get("url") or data.get("play_url") or vid
            play_url = f"正片${url}"
            play_from = data.get("source_name") or data.get("play_from") or "正片"
        vod = {
            "vod_id": self._vod_id(vid),
            "vod_name": data.get("name") or vid,
            "vod_pic": self._pic(data),
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
        return self._page_result(items, pg)

    def playerContent(self, flag, id, vipFlags):
        url = self._fetch_play(str(id or ""))
        if not url:
            return {"parse": 0, "msg": "无法获取播放地址"}
        result = {
            "parse": 0,
            "jx": 0,
            "url": url,
            "header": self._string_map({"User-Agent": UA}),
        }
        return result

    def liveContent(self, url):
        return "[]"

    def _fetch_list(self, tid, pg, extend):
        sort_key = tid or "publishedAt"
        start = (max(1, pg) - 1) * PAGE_SIZE
        data = self._api("/videos", {"sort": "-" + sort_key, "count": PAGE_SIZE, "start": start})
        return self._list(data)

    def _fetch_search(self, keyword, pg):
        start = (max(1, pg) - 1) * PAGE_SIZE
        data = self._api("/search/videos", {"search": keyword, "count": PAGE_SIZE, "start": start})
        return self._list(data)

    def _fetch_tag(self, keyword, pg):
        start = (max(1, pg) - 1) * PAGE_SIZE
        data = self._api("/videos", {"tagsOneOf": keyword, "count": PAGE_SIZE, "start": start, "sort": "-publishedAt"})
        return self._list(data)

    def _fetch_detail(self, vid):
        vid = str(vid)
        if vid.startswith("play/"):
            parts = vid.split("/", 2)
            vid = parts[1] if len(parts) > 1 else vid
        data = self._api("/videos/" + vid, {})
        if not data:
            return {}
        actors = []
        tags = data.get("tags") or []
        desc = data.get("description") or ""
        actresses = self._parse_actresses(desc)
        for a in actresses:
            if a and a not in actors:
                actors.append(a)
        for t in tags:
            if t and t not in actors and not self._looks_tag(t, actresses):
                pass
        year = ""
        m = re.search(r"日期：\s*\n?\s*(\d{4})-(\d{2})-(\d{2})", desc)
        if m:
            year = m.group(1)
        category = ""
        cm = re.search(r"類別：\s*\n?\s*([^\n]+)", desc)
        if cm:
            category = cm.group(1).strip()
        master = ""
        sps = data.get("streamingPlaylists") or []
        if sps:
            master = sps[0].get("playlistUrl") or ""
        if not master:
            files = data.get("files") or []
            for f in files:
                fu = f.get("fileUrl") or f.get("fileDownloadUrl")
                if fu:
                    master = fu
                    break
        return {
            "name": data.get("name") or vid,
            "category": category,
            "year": year,
            "remarks": self._fmt_duration(data.get("duration") or 0),
            "actors": actors,
            "director": "",
            "description": desc,
            "url": master,
            "episodes": [{"name": "正片", "url": master}] if master else [],
            "pic": data.get("thumbnailPath") or "",
        }

    def _fetch_play(self, play_id):
        play_id = str(play_id)
        if re.match(r"^https?://", play_id):
            return play_id
        if play_id.startswith("play/"):
            parts = play_id.split("/", 2)
            play_id = parts[1] if len(parts) > 1 else play_id
        data = self._api("/videos/" + play_id, {})
        if not data:
            return ""
        sps = data.get("streamingPlaylists") or []
        if sps:
            return sps[0].get("playlistUrl") or ""
        files = data.get("files") or []
        for f in files:
            fu = f.get("fileUrl") or f.get("fileDownloadUrl")
            if fu:
                return fu
        return ""

    def _classes(self):
        arr = []
        for key, nm in SORTS:
            arr.append({"type_id": key, "type_name": nm})
        return arr

    def _filters(self, classes):
        return {}

    def _home_items(self):
        data = self._api("/videos", {"sort": "-publishedAt", "count": PAGE_SIZE, "start": 0})
        return self._list(data)

    def _page_result(self, items, pg):
        try:
            page = max(1, int(pg))
        except (TypeError, ValueError):
            page = 1
        vods = [self._vod(x) for x in items]
        has_more = len(vods) >= PAGE_SIZE
        return {
            "list": vods,
            "page": page,
            "pagecount": 9999 if has_more else page,
            "limit": PAGE_SIZE,
            "total": len(vods),
        }

    def _api(self, path, params=None):
        path = "/" + str(path).lstrip("/")
        ck = path + json.dumps(params or {}, sort_keys=True)
        with self._lock:
            hit = self._cache.get(ck)
            if hit and time.time() - self._cache_time.get(ck, 0) < CACHE_TTL:
                return hit
        hosts = list(self.hosts)
        if self._good_host in hosts:
            hosts.remove(self._good_host)
            hosts.insert(0, self._good_host)
        for h in hosts:
            try:
                url = h + "/api/v1" + path
                opts = {"params": params or {}, "timeout": 10000}
                resp = self._req(url, params=params or {}, timeout=10000)
                resp = self._resp_dict(resp)
                if resp.get("error"):
                    continue
                if not 200 <= (resp.get("code") or 0) < 300:
                    continue
                if DEBUG:
                    print("[PigAV DEBUG] %s -> %s bytes host=%s" % (url, len(resp.get("content", "")), h))
                obj = json.loads(resp.get("content", ""))
                self._good_host = h
                if h != self.host:
                    self.host = h
                with self._lock:
                    self._cache[ck] = obj
                    self._cache_time[ck] = time.time()
                return obj
            except Exception:
                continue
        return {}

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("shortUUID") or item.get("uuid") or item.get("id") or "")
        return {
            "vod_id": self._vod_id(vid),
            "vod_name": item.get("name") or item.get("title") or vid,
            "vod_pic": self._pic(item),
            "vod_remarks": self._fmt_duration(item.get("duration") or 0),
        }

    def _pic(self, item):
        for k in ("thumbnailPath", "previewPath", "img_y", "cover", "pic", "img", "thumb", "vod_pic"):
            v = item.get(k)
            if v:
                return v
        return ""

    def _list(self, data):
        if isinstance(data, list):
            return data
        if not isinstance(data, dict):
            return []
        for k in ("data", "list", "items", "records"):
            v = data.get(k)
            if isinstance(v, list):
                return v
        return []

    def _parse_actresses(self, desc):
        if not desc:
            return []
        m = re.search(r"女優名：\s*\n?([\s\S]*?)(?:\n\s*\n\s*男優名|$)", desc)
        if not m:
            return []
        block = m.group(1)
        names = []
        for seg in re.split(r"[,\n]", block):
            seg = seg.strip()
            if seg and seg != "N/A" and seg not in names:
                names.append(seg)
        return names

    def _looks_tag(self, t, actresses):
        return t in actresses

    def _fmt_duration(self, seconds):
        try:
            sec = int(seconds)
            if sec <= 0:
                return ""
            h, rem = divmod(sec, 3600)
            m, s = divmod(rem, 60)
            if h > 0:
                return f"{h:02d}:{m:02d}:{s:02d}"
            return f"{m:02d}:{s:02d}"
        except Exception:
            return ""

    def _clickable(self, kind, name):
        if not name:
            return ""
        ident = f"{kind}/{quote(name, safe='')}"
        payload = json.dumps({"id": ident, "name": name, "type_flag": "0"}, ensure_ascii=False, separators=(",", ":"))
        return f"[a=cr:{payload}/]{name}[/a]"

    def _safe_label(self, text):
        return str(text or "").replace("$", "＄").replace("#", "＃").strip()

    def _vod_id(self, site_id):
        return f"{VOD_ID_PREFIX}{site_id}" if VOD_ID_PREFIX else str(site_id)

    def _int(self, x, d=0):
        try:
            return int(x)
        except Exception:
            return d

    def _resp_dict(self, resp):
        if isinstance(resp, dict):
            return resp
        if isinstance(resp, str):
            return {"code": 200, "content": resp, "headers": {}, "error": None}
        if isinstance(resp, (bytes, bytearray)):
            return {"code": 200, "content": resp, "headers": {}, "error": None}
        return {"code": 0, "content": "", "headers": {}, "error": str(resp)}

    def _string_map(self, value, name="headers"):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            return {}
        return {str(k): str(v) for k, v in value.items() if v is not None}

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
                enc = (resp.headers.get("Content-Encoding") or "").lower()
                if enc == "gzip":
                    raw = gzip.decompress(raw)
                elif enc == "deflate":
                    raw = zlib.decompress(raw)
                code = resp.getcode() or 0
                return {"code": code, "content": raw.decode("utf-8", "replace"), "headers": dict(resp.headers), "error": None}
        except Exception as e:
            return {"code": 0, "content": "", "headers": {}, "error": str(e)}
