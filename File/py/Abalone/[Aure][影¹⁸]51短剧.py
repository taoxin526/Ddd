# -*- coding: utf-8 -*-
# [51短剧¹⁸ 更新于:2026-11-05 01:10]
import json
import re
import time
import base64
import threading
import urllib.request
import urllib.parse

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        def proxy(self, params):
            return [404, "text/plain", ""]
        def localProxy(self, params):
            return [404, "text/plain", ""]

try:
    from Crypto.Cipher import AES as _AES
    from Crypto.Util.Padding import unpad as _unpad
    _CRYPTO = "crypto"
except Exception:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        _CRYPTO = "cryptography"
    except Exception:
        _CRYPTO = None

NAME = "51短剧"
ENTRY_HOSTS = ["https://51hub.com", "https://7f9.gkxgesqk.cc"]
API_DEFAULT = "https://api.51dj1.com/api.php"
PUB_PAGE = "https://aaaaa.rcjhtycu.cc"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PAGE_SIZE = 30
DOMAIN_TTL = 6 * 3600
AES_KEY = b"2acf7e91e9864673"
AES_IV = b"1c29882d3ddfcfd6"
MEDIA_KEY = b"f5d965df75336270"
MEDIA_IV = b"97b60394abc2fbe1"

class Spider(BaseSpider):

    def __init__(self):
        self.name = NAME
        self.entries = list(ENTRY_HOSTS)
        self.entry = self.entries[0]
        self.api_base = API_DEFAULT
        self._cache = {}
        self._cache_time = {}
        self._lock = threading.Lock()
        self._options = {}

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
            cfg = {}
        self._options = cfg
        site = (cfg.get("site") or cfg.get("url") or "").strip().rstrip("/")
        if site:
            with self._lock:
                self.entries = [site] + [h for h in self.entries if h != site]
                self.entry = self.entries[0]

    def getDependence(self):
        return []

    def destroy(self):
        with self._lock:
            self._cache.clear()
            self._cache_time.clear()
        self._options = {}

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", str(url)))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {"msg": "不支持此操作"}

    @staticmethod
    def _aes_decrypt(b64):
        if not b64:
            return ""
        try:
            ct = base64.b64decode(str(b64).replace(" ", "+"))
        except Exception:
            return ""
        if _CRYPTO == "crypto":
            try:
                pt = _AES.new(AES_KEY, _AES.MODE_CBC, AES_IV).decrypt(ct)
                return _unpad(pt, 16).decode("utf-8", "replace")
            except Exception:
                return ""
        if _CRYPTO == "cryptography":
            try:
                dec = Cipher(algorithms.AES(AES_KEY), modes.CBC(AES_IV)).decryptor()
                pt = dec.update(ct) + dec.finalize()
                return pt[:-pt[-1]].decode("utf-8", "replace") if pt else ""
            except Exception:
                return ""
        return ""

    def _req(self, url, body=None, timeout=15000):
        net = getattr(self, "net", None)
        if net is not None and hasattr(net, "req"):
            try:
                opts = {"timeout": timeout, "method": "POST", "postType": "form", "data": body,
                        "headers": {"User-Agent": UA}}
                if hasattr(net, "_native"):
                    resp = net.req(url, opts)
                else:
                    resp = net.req(url, json.dumps(opts))
                content = ""
                if isinstance(resp, dict):
                    content = resp.get("content", "") or ""
                elif isinstance(resp, str):
                    content = resp
                if content:
                    if isinstance(content, (bytes, bytearray)):
                        content = content.decode("utf-8", "replace")
                    elif isinstance(content, list):
                        content = bytes(content).decode("utf-8", "replace")
                    return content
            except Exception:
                pass
        try:
            data = urllib.parse.urlencode(body).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": UA,
            })
            resp = urllib.request.urlopen(req, timeout=timeout / 1000)
            return resp.read().decode("utf-8", "replace")
        except Exception:
            return ""

    @staticmethod
    def _api_body(params):
        body = {
            "bundleId": "com.pwa.mater",
            "version": "1.3.2",
            "oauth_type": "web",
            "language": "zh",
            "via": "pwa",
            "token": "",
            "trace_id": "7d05538c4b8a5e74e82f93c0dab0163c",
            "device_id": "a1b2c3d4e5f60718",
            "spread_code": "",
        }
        if params:
            for k, v in params.items():
                if v is not None:
                    body[str(k)] = v
        return body

    def _api(self, path, params=None, retry=True):
        params = params or {}
        base = self._api_base()
        raw = self._req(base + path, self._api_body(params))
        obj = self._parse_resp(raw)
        if not obj and retry:
            self._refresh_domains()
            base = self._api_base()
            raw = self._req(base + path, self._api_body(params))
            obj = self._parse_resp(raw)
        return obj

    def _ensure_domains(self):
        """懒触发：会话内首次请求前主动获取最新网址池（TTL 内只跑一次）。"""
        cached = self._local_get("h51_domains_ts")
        if cached and isinstance(cached, dict):
            if time.time() - (cached.get("ts") or 0) < DOMAIN_TTL:
                return
        self._refresh_domains()

    @staticmethod
    def _parse_resp(raw):
        if not raw:
            return None
        try:
            r = json.loads(raw)
        except Exception:
            return None
        if not isinstance(r, dict):
            return None
        if r.get("errcode") not in (0, None):
            return None
        data = r.get("data")
        if isinstance(data, dict):
            return data
        if isinstance(data, str):
            try:
                inner = json.loads(Spider._aes_decrypt(data))
            except Exception:
                return None
            if isinstance(inner, dict):
                inner_data = inner.get("data")
                if isinstance(inner_data, dict):
                    return inner_data
                return inner
            return inner
        return None

    def _local_get(self, key, default=None):
        local = getattr(self, "local", None)
        if local is None:
            return default
        try:
            return local.get(key) or default
        except Exception:
            return default

    def _local_set(self, key, value):
        local = getattr(self, "local", None)
        if local is None:
            return
        try:
            local.set(key, value)
        except Exception:
            pass

    def _api_base(self):
        cached = self._local_get("h51_api_base")
        if cached and isinstance(cached, dict):
            ts = cached.get("ts") or 0
            if time.time() - ts < DOMAIN_TTL and cached.get("base"):
                return cached.get("base")
        return self.api_base

    def _refresh_domains(self):
        """主动获取最新网址池：
        - 数据链路 API 固定 api.51dj1.com（若 config 提供 api_urls 则跟随）
        - 入口域名池从 config general + 发布页动态提取（备用/展示）
        缓存 DOMAIN_TTL；任一请求失败时兜底轮换。"""
        entries = list(ENTRY_HOSTS)
        base = API_DEFAULT
        general = {}
        try:
            raw = self._req(API_DEFAULT + "/api/home/config", self._api_body({}), timeout=8000)
            obj = self._parse_resp(raw)
            if obj:
                general = obj.get("general") or {}
                au = obj.get("api_urls") or obj.get("api_base") or obj.get("apiBaseURL")
                if isinstance(au, str) and au.strip().startswith("http"):
                    base = au.strip().rstrip("/")
                elif isinstance(au, list):
                    for u in au:
                        if isinstance(u, str) and u.startswith("http"):
                            base = u.rstrip("/")
                            break
                for k in ("permanent_entrance", "app_download_url", "releases_page", "latest_url", "transit_page_url", "permanent_url"):
                    u = self._host_of(general.get(k) or "")
                    if u and u not in entries:
                        entries.append(u)
        except Exception:
            pass
        pub_pages = [general.get("app_download_url") or "", PUB_PAGE]
        for pp in pub_pages:
            if not pp:
                continue
            try:
                pub_html = self._plain_get(pp, timeout=8000)
                if not pub_html:
                    continue
                m = re.search(r'"site_url"\s*:\s*"([^"]+)"', pub_html)
                if m:
                    u = self._host_of(m.group(1))
                    if u and u not in entries:
                        entries.append(u)
                for mm in re.finditer(r"https?://[a-z0-9.-]+", pub_html):
                    u = self._host_of(mm.group(0))
                    if u and u not in entries:
                        entries.append(u)
            except Exception:
                continue
        with self._lock:
            self.entries = list(dict.fromkeys(entries))
            self.entry = self.entries[0]
            self.api_base = base
        now = time.time()
        self._local_set("h51_api_base", {"ts": now, "base": base})
        self._local_set("h51_entries", {"ts": now, "entries": self.entries})
        self._local_set("h51_domains_ts", {"ts": now})

    @staticmethod
    def _host_of(url):
        """提取 URL 的站点域名（https://host 形式），过滤工具域名/静态资源后缀。"""
        try:
            u = urllib.parse.urlparse(str(url).strip())
            if u.scheme not in ("http", "https"):
                return ""
            host = u.netloc
        except Exception:
            return ""
        if not host:
            return ""
        h = host.lower()
        for bad in ("cloudflareinsights", "googletagmanager", "mc.yandex", "schema.org",
                    "t.me", "gitlab.com", "yandex.ru", "localhost", "api.51dj1.com",
                    "pic.gyezbp.cn", "hls.ohjzmm.cn", "ts.zhixunkeji.xyz", "vip.", ".apk", ".js"):
            if bad in h:
                return ""
        return "https://" + host

    def _plain_get(self, url, timeout=15000):
        net = getattr(self, "net", None)
        if net is not None and hasattr(net, "req"):
            try:
                opts = {"timeout": timeout, "headers": {"User-Agent": UA}}
                if hasattr(net, "_native"):
                    resp = net.req(url, opts)
                else:
                    resp = net.req(url, json.dumps(opts))
                content = ""
                if isinstance(resp, dict):
                    content = resp.get("content", "") or ""
                elif isinstance(resp, str):
                    content = resp
                if content:
                    if isinstance(content, (bytes, bytearray)):
                        content = content.decode("utf-8", "replace")
                    elif isinstance(content, list):
                        content = bytes(content).decode("utf-8", "replace")
                    return content
            except Exception:
                pass
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return urllib.request.urlopen(req, timeout=timeout / 1000).read().decode("utf-8", "replace")
        except Exception:
            return ""

    def _classes(self):
        hit = self._cache.get("__cls")
        if hit and time.time() - self._cache_time.get("__cls", 0) < 1800:
            return hit[0]
        arr = []
        try:
            obj = self._api("/api/home/contentOptions", {}, retry=False)
            vf = (obj or {}).get("video_filter") or {}
            theme = vf.get("theme") or {}
            for it in theme.get("list") or []:
                name = it.get("name")
                val = it.get("value")
                if name and val is not None:
                    arr.append({"type_id": str(val), "type_name": str(name)})
        except Exception:
            pass
        if not arr:
            arr = [{"type_id": "all", "type_name": "全部"}]
        with self._lock:
            self._cache["__cls"] = (arr, time.time())
        return arr

    def _filters(self, classes):
        rec = {
            "key": "recommend", "name": "推荐", "init": "0",
            "value": [{"n": "默认", "v": "0"}, {"n": "最新", "v": "1"}, {"n": "最热", "v": "2"}],
        }
        setting = {"key": "setting", "name": "设定", "init": "", "value": [{"n": "全部", "v": ""}]}
        background = {"key": "background", "name": "背景", "init": "", "value": [{"n": "全部", "v": ""}]}
        try:
            obj = self._api("/api/home/contentOptions", {}, retry=False)
            vf = (obj or {}).get("video_filter") or {}
            for dim, fkey in (("setting", "setting"), ("background", "background")):
                d = vf.get(dim) or {}
                vals = [{"n": "全部", "v": ""}]
                for it in d.get("list") or []:
                    name = it.get("name")
                    val = it.get("value")
                    if name and val is not None:
                        vals.append({"n": str(name), "v": str(val)})
                if len(vals) > 1:
                    if fkey == "setting":
                        setting["value"] = vals
                    else:
                        background["value"] = vals
        except Exception:
            pass
        fs = [rec, setting, background]
        return {c["type_id"]: fs for c in classes}

    def homeContent(self, filter):
        classes = self._classes()
        result = {"class": classes}
        if filter:
            result["filters"] = self._filters(classes)
        result["list"] = [self._vod(x) for x in self._home_items()]
        try:
            cached = self._local_get("h51_domains_ts")
            if not (cached and isinstance(cached, dict) and time.time() - (cached.get("ts") or 0) < DOMAIN_TTL):
                threading.Thread(target=self._refresh_domains, daemon=True).start()
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        return {"list": []}

    def _home_items(self):
        obj = self._api("/api/home/homePage", {}, retry=False) or {}
        seen = set()
        out = []
        for it in (obj.get("top_list") or []):
            vid = it.get("video_id")
            if vid and vid not in seen:
                seen.add(vid)
                out.append(it)
        mods = (obj.get("modules") or {}).get("list") or []
        for mod in mods:
            for it in (mod.get("items") or []):
                vid = it.get("video_id")
                if vid and vid not in seen:
                    seen.add(vid)
                    out.append(it)
        if not out:
            out = (self._fetch_list("all", 1, {}) or [])
        return out[:PAGE_SIZE]

    def _fetch_list(self, tid, pg, extend):
        extend = extend or {}
        params = {"page": pg}
        if tid and tid != "all":
            try:
                params["theme"] = int(str(tid))
            except Exception:
                params["theme"] = str(tid)
        for k in ("recommend", "setting", "background"):
            v = extend.get(k)
            if v is not None and str(v) != "":
                try:
                    params[k] = int(str(v))
                except Exception:
                    params[k] = str(v)
        obj = self._api("/api/theater/exploreList", params) or {}
        return obj.get("list") or []

    def _fetch_search(self, key, pg):
        obj = self._api("/api/search/result", {"keyword": key, "page": pg}) or {}
        return obj.get("list") or []

    def _detail(self, vid):
        data = self._api("/api/playlet/detail", {"video_id": int(vid)})
        if not data:
            return {"list": [], "msg": "未找到此影片"}
        eps = data.get("episodes") or []
        title = data.get("title") or vid
        cover = data.get("cover") or ""
        desc = data.get("description") or ""
        remarks = data.get("serialize_status_text") or ""
        ep_lines = []
        for ep in eps:
            eid = ep.get("id")
            if not eid:
                continue
            ep_name = ep.get("title") or "第%s集" % (ep.get("sort") or "")
            ep_lines.append("%s$ep:%s:%s" % (self._safe_label(ep_name), vid, eid))
        play_url = "#".join(ep_lines)
        play_from = "正片"
        if not play_url:
            url = data.get("play_url") or ""
            if url:
                play_url = "正片$%s" % url
        vod = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": self._pic_url(cover),
            "type_name": "、".join(data.get("tags") or [])[:30],
            "vod_year": "",
            "vod_area": "",
            "vod_remarks": remarks,
            "vod_director": "",
            "vod_actor": "",
            "vod_content": desc,
            "vod_play_from": play_from,
            "vod_play_url": play_url,
        }
        return {"list": [vod]}

    def _fetch_play(self, playid):
        playid = str(playid or "")
        m = re.match(r"^ep:(\d+):(\d+)$", playid)
        if m:
            vid, eid = m.group(1), m.group(2)
            obj = self._api("/api/playlet/play", {"video_id": int(vid), "episode_id": int(eid)})
            if obj:
                url = obj.get("video_url") or ""
                if url:
                    return url
            return ""
        return playid

    @staticmethod
    def _safe_label(text):
        return str(text or "").replace("$", "＄").replace("#", "＃").strip()

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("video_id") or item.get("id") or "")
        return {
            "vod_id": vid,
            "vod_name": item.get("title") or item.get("name") or vid,
            "vod_pic": self._pic_url(item.get("cover") or item.get("vod_pic") or ""),
            "vod_remarks": item.get("serialize_status_text") or item.get("play_count_text") or item.get("remarks") or "",
        }

    @staticmethod
    def _int(x, d=0):
        try:
            return int(x)
        except Exception:
            return d

    @staticmethod
    def _string_map(value):
        if not isinstance(value, dict):
            return {}
        return {str(k): str(v) for k, v in value.items() if v is not None}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        tid = str(tid or "all")
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
        responses = [self._detail(str(v)) for v in ids]
        merged = {k: v for k, v in (responses[0] or {}).items() if k != "list"}
        merged["list"] = [item for response in responses for item in (response.get("list") or [])]
        return merged

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
        return {"parse": 0, "jx": 0, "url": url, "header": {}}

    def liveContent(self, url):
        return "[]"

    def _proxy_url(self, params):
        """统一封面/媒体代理 URL，兼容三契约：
        - FongMi 5.8.7: proxyUrl(params, local) 基类自动拼 do=py&siteKey
        - FongMi 5.8.4: getProxyUrl(params, local) 基类自动拼 do=py&siteKey
        - TVBox: getProxyUrl(local) 只接受 bool（?do=py），源内拼业务参数
        """
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

    def _pic_url(self, u):
        """列表/详情封面用 proxy 地址（加密图床需解密）。"""
        u = str(u or "")
        if not u:
            return ""
        try:
            return self._proxy_url({"type": "pic", "url": self._e64(u)})
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
        """先判魔术字节（明文透传），否则 AES-CBC 解密（media_key）。"""
        if not raw:
            return raw
        if raw[:2] == b"\xff\xd8" or raw[:4] == b"\x89PNG" or raw[:4] == b"RIFF" or raw[:4] == b"WEBP":
            return raw
        if _CRYPTO == "crypto":
            try:
                pt = _AES.new(MEDIA_KEY, _AES.MODE_CBC, MEDIA_IV).decrypt(raw)
                return _unpad(pt, 16)
            except Exception:
                return raw
        if _CRYPTO == "cryptography":
            try:
                dec = Cipher(algorithms.AES(MEDIA_KEY), modes.CBC(MEDIA_IV)).decryptor()
                pt = dec.update(raw) + dec.finalize()
                return pt[:-pt[-1]] if pt else raw
            except Exception:
                return raw
        return raw

    @staticmethod
    def _mime(img):
        if img[:2] == b"\xff\xd8":
            return "image/jpeg"
        if img[:4] == b"\x89PNG":
            return "image/png"
        if img[:4] == b"RIFF":
            return "image/webp"
        return "image/jpeg"

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

    def _urlopen_bytes(self, url, timeout=15000):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return urllib.request.urlopen(req, timeout=timeout / 1000).read()
        except Exception:
            return b""

    def proxy(self, params):
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                return [404, "text/plain", ""]
        if not isinstance(params, dict):
            return [404, "text/plain", ""]
        if params.get("type") != "pic":
            return [404, "text/plain", ""]
        u = self._d64(params.get("url", ""))
        if not u:
            return [404, "text/plain", ""]
        net = getattr(self, "net", None)
        raw = b""
        if net is not None:
            try:
                opts = {"buffer": 3, "headers": {"User-Agent": UA}}
                if hasattr(net, "reqParts"):
                    if hasattr(net, "_native"):
                        raw = net.reqParts(u, opts)[1]
                    else:
                        raw = net.reqParts(u, json.dumps(opts))[1]
                elif hasattr(net, "req"):
                    resp = net.req(u, opts)
                    raw = resp.get("content", b"") if isinstance(resp, dict) else (resp or b"")
            except Exception:
                raw = b""
        if not raw:
            raw = self._urlopen_bytes(u)
        img = self._pic_decrypt(raw)
        return [200, self._mime(img), self._img_stream(img), {}]

    localProxy = proxy
