# -*- coding: utf-8 -*-
# [色情百科¹⁸  更新于:2026-11-05 23:20]
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

NAME = "色情百科"
HOSTS = ["https://app-1.pornavav.shop"]
UA = "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 28
CACHE_TTL = 30
DEBUG = False
VOD_ID_PREFIX = ""
STYLE = {"type": "rect", "ratio": 1.33}
MAIN_CATS = ["精品推荐", "国产精品", "主播秀色", "日本有码", "日本无码", "中文字幕", "童颜巨乳",
             "性感人妻", "强奸乱伦", "欧美情色", "三级伦理", "卡通动漫", "丝袜OL", "自拍偷拍",
             "日本片商", "剧情介绍", "网曝系列", "麻豆传媒", "明星换脸", "国产乱伦", "国产丝袜",
             "国产SM", "国产人妻", "探花嫖娼", "同性恋"]
import base64


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
        if action == "toast":
            return {"msg": "这是测试 Toast"}
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
            return self._page(items, pg)

        if tid.startswith("tag/"):
            name = unquote(tid.replace("tag/", "", 1))
            items = self._fetch_search(name, pg)
            return self._page(items, pg)

        if tid.startswith("folder/"):
            parts = tid.split("/", 2)
            if len(parts) == 3:
                f_type, f_value = parts[1], unquote(parts[2])
                if not f_value or f_value == "_":
                    items = self._fetch_folder_entries(f_type)
                else:
                    items = self._fetch_folder(f_type, f_value, pg)
                return {
                    "list": items,
                    "page": pg,
                    "pagecount": pg if len(items) < PAGE_SIZE else 9999,
                    "limit": PAGE_SIZE,
                    "total": 999999,
                }

        items = self._fetch_list(tid, pg, extend)
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": getattr(self, "_last_pc", 9999) or pg,
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
            play_from_parts = []
            play_url_parts = []
            lines = []
            for i, ep in enumerate(eps, 1):
                title = self._safe_label(ep.get("name") or f"第{i}集")
                url = ep.get("url") or ep.get("play_url") or ""
                if url:
                    lines.append(f"{title}${url}")
            play_url = "#".join(lines)
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
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": getattr(self, "_last_pc", 9999) or pg,
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
            "header": self._string_map({"User-Agent": UA}),
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
        if not isinstance(params, dict):
            return [404, "text/plain", ""]
        ptype = params.get("type")
        if ptype == "pic":
            real = params.get("url") or ""
            try:
                real = self._d64(real)
            except Exception:
                pass
            raw = self._download(real)
            if not raw:
                return [404, "text/plain", ""]
            return [200, self._mime(raw), self._img_stream(raw), {}]
        return [404, "text/plain", ""]

    localProxy = proxy

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


    def _safe_label(self, text: str) -> str:
        return str(text or "").replace("$", "＄").replace("#", "＃").strip()

    def _vod_id(self, site_id: str) -> str:
        return f"{VOD_ID_PREFIX}{site_id}" if VOD_ID_PREFIX else str(site_id)

    def _folder_id(self, type_: str, value: str) -> str:
        return f"folder/{type_}/{quote(value, safe='')}"

    def _folder_vod(self, type_: str, value: str, name: str, count=None):
        card = {
            "vod_id": self._folder_id(type_, value),
            "vod_name": str(name or value or ""),
            "vod_pic": "",
            "vod_remarks": ("%s部" % count) if count else "",
            "vod_tag": "folder",
        }
        return card

    def _actor_id(self, name: str) -> str:
        return f"actor/{quote(name, safe='')}"

    def _director_id(self, name: str) -> str:
        return f"director/{quote(name, safe='')}"

    def _action_id(self, value: str) -> str:
        return f"action/{value}"

    def _play_id(self, site_id: str, ep_idx: int, source: str) -> str:
        return f"play/{site_id}/{ep_idx}/{source}"

    def _clickable(self, kind: str, name: str) -> str:
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

    def _api(self, path, params=None, method="GET"):
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
                url = h + "/api" + path
                opts = {"params": params or {}, "timeout": 10000}
                if method == "POST":
                    opts["method"] = "POST"
                    opts["postType"] = "form"
                    opts["data"] = params or {}
                resp = self.net.req(url, opts)
                resp = self._resp_dict(resp)
                if resp.get("error"):
                    continue
                if not 200 <= (resp.get("code") or 0) < 300:
                    continue
                if DEBUG:
                    print("[Quss DEBUG] %s -> %d bytes host=%s" % (url, len(resp.get("content", "")), h))
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

    def _classes(self):
        hit = self._cache.get("__cls")
        if hit and time.time() - self._cache_time.get("__cls", 0) < CACHE_TTL:
            return hit[0]
        arr = [{"type_id": "video", "type_name": "最新更新"}]
        seen = {"video"}
        try:
            html = self._get_html(self._abs("/"))
            if html:
                m = re.search(r'class="collapse show"[^>]*>(.*?)</div>', html, re.S)
                seg = m.group(1) if m else html
                for mm in re.finditer(r'class="pm-sublink"href="/\?fenlei=([^"&]+)"', seg):
                    nm = mm.group(1).strip()
                    if nm and nm not in seen:
                        seen.add(nm)
                        arr.append({"type_id": nm, "type_name": nm})
        except Exception:
            pass
        if len(arr) <= 1:
            for nm in MAIN_CATS:
                if nm not in seen:
                    seen.add(nm)
                    arr.append({"type_id": nm, "type_name": nm})
        with self._lock:
            self._cache["__cls"] = (arr, time.time())
        return arr

    def _filters(self, classes):
        sort_filter = {
            "key": "order", "name": "排序", "init": "latest",
            "value": [{"n": "默认", "v": ""}, {"n": "最新", "v": "latest"}, {"n": "最热", "v": "hot"}],
        }
        genre_filter = {"key": "genre", "name": "类型", "init": "all", "value": [{"n": "全部", "v": "all"}]}
        area_filter = {"key": "area", "name": "地区", "init": "all", "value": [{"n": "全部", "v": "all"}]}
        year_filter = {"key": "year", "name": "年份", "init": "all", "value": [{"n": "全部", "v": "all"}]}
        return {c["type_id"]: [sort_filter, genre_filter, area_filter, year_filter] for c in classes}

    def _home_items(self):
        return self._fetch_list("video", 1, {})

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("id") or item.get("vod_id") or "")
        return {
            "vod_id": self._vod_id(vid),
            "vod_name": item.get("name") or item.get("title") or vid,
            "vod_pic": self._pic_url(item.get("pic") or ""),
            "vod_remarks": item.get("remarks") or item.get("duration") or "",
        }

    def _pic(self, item):
        for k in ("img_y", "cover", "pic", "img", "thumb", "vod_pic"):
            v = item.get(k)
            if v:
                return v
        return ""

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

    def _post_html(self, url, data=None, **kw):
        resp = self._req(url, method="POST", postType="form", data=data or {}, **kw)
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

    def _extract_m3u8(self, html):
        if not html:
            return ""
        patterns = [
            r'var\s+now\s*=\s*["\']([^"\']+)["\']',
            r'var\s+player_data\s*=\s*(\{.*?\})',
            r'url\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'var\s+playurl\s*=\s*["\']([^"\']+)["\']',
            r'(https?://[^\s"\']+\.m3u8[^\s"\']*)',
            r'(https?://[^\s"\']+\.mp4[^\s"\']*)',
        ]
        for p in patterns:
            m = re.search(p, html)
            if m:
                val = m.group(1)
                if "{" in val:
                    m2 = re.search(r'"(?:url|play_url|m3u8)"\s*:\s*"(https?://[^"]+)"', val)
                    if m2:
                        return self._fix_url(m2.group(1))
                    m3 = re.search(r'(https?://[^"\s]+\.m3u8[^"\s]*)', val)
                    return self._fix_url(m3.group(1)) if m3 else ""
                return self._fix_url(val)
        return ""

    def _parse_iframe(self, html):
        m = re.search(r'<iframe[^>]+src=["\']([^"\']+)', html, re.I)
        if m:
            iframe_url = self._fix_url(m.group(1))
            iframe_html = self._get_html(iframe_url)
            if iframe_html:
                url = self._extract_m3u8(iframe_html)
                if url:
                    return url
        return ""

    def _extract_json(self, html, pattern):
        if not html:
            return {}
        m = re.search(pattern, html)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
        return {}

    def _get_pagecount(self, html, xpath='//a[contains(@class,"page") and text()[normalize-space()]]'):
        if not html:
            return 1
        try:
            from lxml import etree
            tree = etree.HTML(html)
            pages = tree.xpath(xpath)
            if pages:
                nums = []
                for p in pages:
                    txt = p.text_content().strip() if hasattr(p, 'text_content') else str(p).strip()
                    if txt.isdigit():
                        nums.append(int(txt))
                if nums:
                    return max(nums)
        except Exception:
            pass
        m = re.search(r'共\s*(\d+)\s*页', html)
        if m:
            return int(m.group(1))
        return 1


    def _abs(self, path):
        path = str(path or "")
        if path.startswith("http"):
            return path
        return self.host.rstrip("/") + "/" + path.lstrip("/")

    def _parse_cards(self, html):
        items = []
        if not html:
            return items
        for block in re.finditer(r'<div class="thumb video-img-box">(.*?)</figcaption>', html, re.S):
            b = block.group(1)
            m = re.search(r'\?play-(\d+)-1-\.html', b)
            if not m:
                continue
            vid = m.group(1)
            img = re.search(r'<img src="([^"]+)" alt="([^"]*)"', b)
            pic = img.group(1) if img else ""
            title = ""
            tm = re.search(r'class="title"\s*title="([^"]*)"', b)
            if tm:
                title = tm.group(1)
            elif img:
                title = img.group(2)
            remarks = ""
            dm = re.search(r'class="upload"[^>]*>\s*<i[^>]*></i>&nbsp;\s*([^<]*)<', b)
            if dm:
                remarks = dm.group(1).strip()
            if not remarks:
                cm = re.search(r'class="icons" href="/\?fenlei=([^"&]+)"', b)
                if cm:
                    remarks = cm.group(1)
            if vid:
                items.append({"id": vid, "name": title, "pic": pic, "remarks": remarks})
        return items

    def _last_page(self, html, mode):
        nums = []
        if mode == "video":
            nums = [int(x) for x in re.findall(r'\?video=(\d+)\.html', html or "")]
        else:
            nums = [int(x) for x in re.findall(r'\?fenlei=[^"&]*&p=(\d+)', html or "")]
            nums += [int(x) for x in re.findall(r'\?fenlei=(\d+)(?![0-9])', html or "")]
        return max(nums) if nums else 0

    def _fetch_list(self, tid, pg, extend):
        pg = max(1, int(pg or 1))
        tid = unquote(str(tid or ""))
        if tid == "video":
            url = self._abs("/?video=%d.html" % pg)
            mode = "video"
        else:
            url = self._abs("/?fenlei=%s&p=%d" % (quote(tid, safe=""), pg))
            mode = "fenlei"
        html = self._get_html(url)
        items = self._parse_cards(html)
        self._last_pc = self._last_page(html, mode) or (pg if len(items) < PAGE_SIZE else 9999)
        return items

    def _fetch_detail(self, vid):
        vid = str(vid or "").strip()
        if not vid:
            return None
        html = self._get_html(self._abs("/?play-%s-1-.html" % vid))
        if not html:
            return None
        name = ""
        m = re.search(r'<h1>([^<]+)</h1>', html)
        if m:
            name = m.group(1).strip()
        if not name:
            m = re.search(r'<title>([^<]+)</title>', html)
            if m:
                name = m.group(1).split("-")[0].strip()
        category = ""
        cm = re.search(r'href="/\?fenlei=([^"&]+)"', html)
        if cm:
            category = cm.group(1)
        remarks = ""
        dm = re.search(r'<span class="btn btn-shadow ml-2 mr-1"><i class="fa-regular fa-calendar"></i></span>\s*([0-9-]+)', html)
        if dm:
            remarks = dm.group(1).strip()
        return {
            "id": vid,
            "name": name or vid,
            "pic": "",
            "category": category,
            "remarks": remarks,
            "description": "",
            "url": vid,
        }

    def _fetch_search(self, keyword, pg):
        pg = max(1, int(pg or 1))
        kw = quote(str(keyword or "").strip(), safe="")
        url = self._abs("/?search=%s&p=%d" % (kw, pg))
        html = self._get_html(url)
        items = self._parse_cards(html)
        nums = [int(x) for x in re.findall(r'\?search=[^"&]*&p=(\d+)', html or "")]
        self._last_pc = max(nums) if nums else (pg if len(items) < PAGE_SIZE else 9999)
        return items

    def _fetch_play(self, play_id):
        play_id = str(play_id or "").strip()
        if not play_id:
            return ""
        m = re.search(r'(\d+)', play_id)
        vid = m.group(1) if m else play_id
        js = self._get_html(self._abs("/js/js.php?did=%s&src=1" % vid))
        if not js:
            return ""
        m = re.search(r'url=([^"&\']+\.m3u8[^"&\']*)', js)
        if m:
            return unquote(m.group(1))
        m = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', js)
        if m:
            return m.group(1)
        return ""

    def _pic_url(self, u):
        u = self._abs(u)
        if not u:
            return ""
        enc = quote(base64.b64encode(u.encode("utf-8")), safe="")
        try:
            proxy = self.getProxyUrl()
            if proxy:
                sep = "&" if "?" in proxy else "?"
                key = getattr(self, "siteKey", "") or ""
                extra = ("&siteKey=%s" % key) if (key and "siteKey=" not in proxy) else ""
                return "%s%stype=pic&url=%s%s" % (proxy, sep, enc, extra)
        except Exception:
            pass
        if hasattr(self, "proxyUrl"):
            try:
                p = self.proxyUrl({"type": "pic", "url": base64.b64encode(u.encode("utf-8")).decode("utf-8")})
                if p:
                    return p
            except Exception:
                pass
        return u

    def _download(self, url):
        url = self._abs(url)
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

    @staticmethod
    def _d64(s):
        s = str(s or "")
        pad = "=" * (-len(s) % 4)
        try:
            return base64.b64decode(s + pad).decode("utf-8", "ignore")
        except Exception:
            return s

    @staticmethod
    def _mime(raw):
        if isinstance(raw, (bytes, bytearray)) and raw[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if isinstance(raw, (bytes, bytearray)) and raw[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if isinstance(raw, (bytes, bytearray)) and raw[:4] == b"GIF8":
            return "image/gif"
        if isinstance(raw, (bytes, bytearray)) and raw[:4] == b"RIFF":
            return "image/webp"
        return "image/jpeg"
