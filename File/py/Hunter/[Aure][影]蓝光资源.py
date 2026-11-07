# -*- coding: utf-8 -*-
"""
FongMi Type3 Python Spider — 蓝光资源 (lgzyz.xyz)
依据 Quss v2.4 规范 (5.8.4/5.8.5+ 双兼容)
站点契约 (苹果CMS V10 / 蓝光资源):
  - 数据接口: {host}/api.php/provide/vod/?ac=list (分类) / ac=detail&t=<tid>&pg=<pg> (分类页)
              / ac=detail&ids=<ids> (详情) / ac=detail&wd=<kw>&pg=<pg> (搜索)
  - 播放: vod_play_url = "第N集$https://lgvideo.xyz/player/<token>#..."
          正片 token 必须经解析站 {parse_host}?url= 走 boom.php HMAC 挑战取流
  - 封面: img.lgzy01.xyz/cover/<id>.jpg -> 302 -> pic3.yzzyimg.online (直链无防盗链)
"""
import json
import re
import time
import ssl
import hmac
import hashlib
import threading
import urllib.request
import urllib.parse
import urllib.error
from urllib.error import URLError, HTTPError

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        def proxy(self, params):
            return [404, "text/plain", ""]
        def localProxy(self, params):
            return [404, "text/plain", ""]

NAME = "蓝光资源"
HOSTS = ["https://lgzyz.xyz"]
PARSE_HOST = "https://vv00.xyz"
DEMO_HOST = "https://yanshi.lgzyz.xyz"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
PAGE_SIZE = 20
RESOLVE_TTL = 1800  # 取流结果缓存 30 分钟

class Spider(BaseSpider):

    def __init__(self):
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.parse_host = PARSE_HOST
        self.demo_host = DEMO_HOST
        self.name = NAME
        self.headers = {
            "User-Agent": UA,
            "Accept-Encoding": "identity",
        }
        self._lock = threading.Lock()
        self._resolve_cache = {}
        self._opener = None
        self._good_host = None
        self._diag = {}

    # ---------- 生命周期 ----------
    def init(self, extend=""):
        # 不在 init 发网络请求
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
        if cfg.get("parse_host"):
            self.parse_host = str(cfg["parse_host"]).strip().rstrip("/")
        if cfg.get("demo_host"):
            self.demo_host = str(cfg["demo_host"]).strip().rstrip("/")
        self.options = cfg

    def getDependence(self):
        return []

    def destroy(self):
        with self._lock:
            self._resolve_cache.clear()
        self.options = {}

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", str(url)))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {"msg": "不支持此操作"}

    # ---------- 网络: self.net (App) + urllib 回退 (沙盒) ----------
    def _resp_dict(self, resp):
        if isinstance(resp, dict):
            return resp
        if isinstance(resp, str):
            return {"code": 200, "content": resp, "headers": {}, "error": None}
        if isinstance(resp, (bytes, bytearray)):
            try:
                return {"code": 200, "content": resp.decode("utf-8", "ignore"), "headers": {}, "error": None}
            except Exception:
                return {"code": 200, "content": resp, "headers": {}, "error": None}
        return {"code": 0, "content": "", "headers": {}, "error": str(resp)}

    def _urllib_opener(self):
        # 共享 cookie 罐: boom.php 的 Set-Cookie 必须带到 ruabo.php
        # HTTPSHandler 携带 unverified context (OpenerDirector.open 不接受 context 关键字)
        if self._opener is None:
            import http.cookiejar
            cj = http.cookiejar.CookieJar()
            ctx = ssl._create_unverified_context()
            self._opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(cj),
                urllib.request.HTTPSHandler(context=ctx),
            )
        return self._opener

    def _req(self, url, headers=None, post=None, method="GET", cookie=False, timeout=12):
        """统一请求。返回 dict {code, content, headers, error}。cookie=True 保留会话(取流用)。"""
        net = getattr(self, "net", None)
        opts = {}
        hh = dict(self.headers)
        if headers:
            hh.update(headers)
        opts["headers"] = hh
        opts["timeout"] = timeout * 1000  # 毫秒
        if method.upper() != "GET":
            opts["method"] = method.upper()
        if post is not None:
            if isinstance(post, dict):
                opts["postType"] = "json"
                opts["data"] = post
            else:
                opts["data"] = post
        if cookie:
            opts["cookie"] = True
        if net is not None and hasattr(net, "req"):
            try:
                return self._resp_dict(net.req(url, opts))
            except Exception:
                pass
        # urllib 回退
        data = None
        if post is not None:
            if isinstance(post, dict):
                data = json.dumps(post, separators=(",", ":")).encode("utf-8")
            else:
                data = bytes(post) if isinstance(post, (bytes, bytearray)) else str(post).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=hh, method=method.upper())
        ctx = ssl._create_unverified_context()
        last = ""
        for _ in range(3):
            try:
                opener = self._urllib_opener() if cookie else urllib.request.urlopen
                if cookie:
                    with opener.open(req, timeout=timeout) as r:
                        body = r.read()
                        ct = r.headers.get("Content-Type", "")
                        if "json" in ct or "text" in ct:
                            try:
                                body = body.decode("utf-8", "ignore")
                            except Exception:
                                pass
                        return {"code": r.status, "content": body, "headers": dict(r.headers), "error": None}
                else:
                    with urllib.request.urlopen(req, context=ctx, timeout=timeout) as r:
                        body = r.read()
                        try:
                            body = body.decode("utf-8", "ignore")
                        except Exception:
                            pass
                        return {"code": r.status, "content": body, "headers": dict(r.headers), "error": None}
            except HTTPError as e:
                last = "HTTP %s" % e.code
                try:
                    body = e.read()
                    try:
                        body = body.decode("utf-8", "ignore")
                    except Exception:
                        pass
                    return {"code": e.code, "content": body, "headers": dict(e.headers), "error": last}
                except Exception:
                    pass
            except Exception as e:
                last = str(e)
                time.sleep(0.4)
        return {"code": 0, "content": "", "headers": {}, "error": last}

    def _ureq(self, url, headers=None, post=None, method="GET", timeout=12):
        """取流专用: 强制 urllib + 共享 cookie 罐 (boom.php Set-Cookie 带到 ruabo.php)。
        参考源取流全程用 urllib (FongMi 有 Python stdlib), 这里保持一致。"""
        hh = dict(self.headers)
        if headers:
            hh.update(headers)
        data = None
        if post is not None:
            if isinstance(post, dict):
                data = json.dumps(post, separators=(",", ":")).encode("utf-8")
                hh["Content-Type"] = "application/json"
            else:
                data = bytes(post) if isinstance(post, (bytes, bytearray)) else str(post).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=hh, method=method.upper())
        last = ""
        for _ in range(3):
            try:
                # 共享 cookie 罐 opener (boom.php/页面 Set-Cookie 必须带到 ruabo.php, 模拟浏览器导航)
                opener = self._urllib_opener()
                with opener.open(req, timeout=timeout) as r:
                    body = r.read()
                    ct = r.headers.get("Content-Type", "") or ""
                    if "json" in ct or "text" in ct or "html" in ct or "javascript" in ct:
                        try:
                            body = body.decode("utf-8", "ignore")
                        except Exception:
                            pass
                    return {"code": r.status, "content": body}
            except HTTPError as e:
                body = b""
                try:
                    body = e.read()
                except Exception:
                    pass
                ct = (e.headers.get("Content-Type", "") or "") if e.headers else ""
                if "json" in ct or "text" in ct or "html" in ct or "javascript" in ct:
                    try:
                        body = body.decode("utf-8", "ignore")
                    except Exception:
                        pass
                return {"code": e.code, "content": body}
            except Exception as e:
                last = str(e)
                time.sleep(0.4)
        return {"code": 0, "content": "", "error": last}

    def _api(self, params, retries=1):
        """苹果CMS JSON 接口。params: dict。返回 dict 或 None。"""
        host = self.host
        for _ in range(retries + 1):
            url = "%s/api.php/provide/vod/?%s" % (host, urllib.parse.urlencode(params))
            d = self._req(url, timeout=12)
            if d.get("code") in (200, 201) and d.get("content"):
                try:
                    txt = d["content"]
                    if isinstance(txt, (bytes, bytearray)):
                        txt = txt.decode("utf-8", "ignore")
                    return json.loads(txt)
                except Exception:
                    pass
            # 域名轮换
            if self._good_host:
                host = self._good_host
            elif host != self.hosts[0]:
                host = self.hosts[0]
            else:
                break
        return None

    # ---------- 分类 ----------
    def _classes(self):
        data = self._api({"ac": "list"})
        classes = []
        if not data or not isinstance(data.get("class"), list):
            return classes
        raw = data["class"]
        parent_ids = {c.get("type_pid", 0) for c in raw if c.get("type_pid", 0) != 0}
        seen = set()
        for c in raw:
            tid = c.get("type_id")
            pid = c.get("type_pid", 0)
            name = (c.get("type_name") or "").strip()
            if not tid or not name:
                continue
            # 去掉"有子分类的父分类"(站内导航只列叶子), 保留无子父类(电影解说/预告片)
            if pid == 0 and tid in parent_ids:
                continue
            if tid in seen:
                continue
            seen.add(tid)
            classes.append({"type_id": str(tid), "type_name": name})
        return classes

    def _vod(self, it):
        pic = it.get("vod_pic") or ""
        return {
            "vod_id": str(it.get("vod_id", "")),
            "vod_name": it.get("vod_name") or "",
            "vod_pic": pic,
            "vod_remarks": it.get("vod_remarks") or "",
            "vod_year": str(it.get("vod_year") or ""),
        }

    def _page_items(self, data, pg):
        items = []
        if data and isinstance(data.get("list"), list):
            items = [self._vod(x) for x in data["list"]]
        return items

    def homeContent(self, filter):
        classes = self._classes()
        result = {"class": classes}
        if filter:
            result["filters"] = {}
        items = []
        # 首页推荐: 第一个叶子分类第一页(带封面)
        if classes:
            d = self._api({"ac": "detail", "t": classes[0]["type_id"], "pg": "1"})
            items = self._page_items(d, 1)
        if not items:
            d = self._api({"ac": "list"})
            items = self._page_items(d, 1)
        result["list"] = items
        return result

    def homeVideoContent(self):
        res = self.homeContent(False)
        return {"list": res.get("list", [])}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        d = self._api({"ac": "detail", "t": str(tid), "pg": str(pg)})
        items = self._page_items(d, pg)
        pagecount = 1
        if d:
            try:
                pagecount = int(d.get("pagecount") or 1)
            except Exception:
                pagecount = 1
        return {
            "list": items,
            "page": pg,
            "pagecount": pagecount,
            "limit": PAGE_SIZE,
            "total": int(d.get("total") or 0) if d else 0,
        }

    # ---------- 详情: 完整 ids 集合 ----------
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        responses = [self._detail(str(i)) for i in ids]
        merged = {k: v for k, v in (responses[0] or {}).items() if k != "list"}
        merged["list"] = [it for r in responses for it in (r.get("list") or [])]
        return merged

    def _detail(self, vid):
        d = self._api({"ac": "detail", "ids": vid})
        if not d or not isinstance(d.get("list"), list) or not d["list"]:
            return {"list": [], "msg": "未找到此影片"}
        it = d["list"][0]
        play_from_raw = it.get("vod_play_from") or ""
        play_url_raw = it.get("vod_play_url") or ""
        # 拆分多线路 ($$$): 站点通常单线路 lgzym3u8
        lines = []
        for block in play_url_raw.split("$$$"):
            block = block.strip()
            if not block:
                continue
            eps = []
            for ep in block.split("#"):
                ep = ep.strip()
                if "$" in ep:
                    name, url = ep.split("$", 1)
                    eps.append("%s$%s" % (self._safe_label(name), url.strip()))
            if eps:
                lines.append("#".join(eps))
        if not lines:
            # 单视频直链
            url = (it.get("vod_play_url") or "").strip()
            if url:
                lines = ["正片$%s" % url]
            else:
                lines = []
        if not lines:
            return {"list": [], "msg": "无播放地址"}
        play_from = "正片" if len(lines) == 1 else "$$$".join(
            "正片" for _ in lines)
        vod = {
            "vod_id": str(it.get("vod_id", "")),
            "vod_name": it.get("vod_name") or vid,
            "vod_pic": it.get("vod_pic") or "",
            "type_name": it.get("type_name") or "",
            "vod_year": str(it.get("vod_year") or ""),
            "vod_area": it.get("vod_area") or "",
            "vod_remarks": it.get("vod_remarks") or "",
            "vod_director": it.get("vod_director") or "",
            "vod_actor": it.get("vod_actor") or "",
            "vod_content": (it.get("vod_content") or "").strip(),
            "vod_play_from": play_from,
            "vod_play_url": "$$$".join(lines),
        }
        return {"list": [vod]}

    # ---------- 搜索 ----------
    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        d = self._api({"ac": "detail", "wd": str(key or "").strip(), "pg": str(pg)})
        items = self._page_items(d, pg)
        pagecount = 1
        if d:
            try:
                pagecount = int(d.get("pagecount") or 1)
            except Exception:
                pagecount = 1
        return {
            "list": items,
            "page": pg,
            "pagecount": pagecount,
            "limit": PAGE_SIZE,
            "total": int(d.get("total") or 0) if d else 0,
        }

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags):
        raw = str(id or "")
        # m3u8 直链 CDN 可能校验 Referer = 解析站 (站点 DPlayer 在 vv00.xyz 拉流)
        play_headers = {"User-Agent": UA, "Referer": self.parse_host + "/"}
        if raw.startswith("http://") or raw.startswith("https://"):
            if "lgvideo.xyz" in raw or "lgzy" in raw:
                # ⚠️ 必须 try/except: 真机 net.req 路径任何一步异常都要兜底，否则 playerContent 崩溃 -> 播放不起
                try:
                    resolved = self._resolve_stream(raw)
                except Exception:
                    resolved = ""
                if resolved:
                    self._diag = {}
                    return {
                        "parse": 0,
                        "jx": 0,
                        "url": resolved,
                        "header": play_headers,
                    }
                # 取流失败回退: 交 FongMi 配置的解析器处理 (参考源行为)
                diag = self._diag
                self._diag = {}
                return {
                    "parse": 1,
                    "jx": 0,
                    "url": raw,
                    "header": play_headers,
                    "desc": ("lgzy-resolve " + ",".join("%s=%s" % (k, v) for k, v in diag.items())),
                }
            if self.isVideoFormat(raw):
                return {
                    "parse": 0,
                    "jx": 0,
                    "url": raw,
                    "header": play_headers,
                }
            return {
                "parse": 0,
                "jx": 0,
                "url": raw,
                "header": play_headers,
            }
        return {"parse": 0, "jx": 0, "url": raw, "header": play_headers}

    # ---------- 取流: vv00.xyz boom.php HMAC 挑战 ----------
    def _resolve_stream(self, target_url):
        now = time.time()
        with self._lock:
            if target_url in self._resolve_cache:
                cache_url, exp = self._resolve_cache[target_url]
                if now < exp:
                    return cache_url

        page_url = "%s?url=%s" % (self.parse_host, urllib.parse.quote(target_url, safe=""))
        page = self._req(page_url, headers={"Referer": "%s/" % self.demo_host}, cookie=True, timeout=10)
        self._diag["page"] = page.get("code")
        if page.get("code") != 200 or not page.get("content"):
            return ""
        html = page["content"]
        if isinstance(html, (bytes, bytearray)):
            html = html.decode("utf-8", "ignore")
        sess_m = re.search(r"hishow\.php\?session=([a-f0-9]+)", html)
        if not sess_m:
            self._diag["sess"] = "no-match"
            return ""
        sess = sess_m.group(1)
        self._diag["sess"] = sess

        js = self._req("%s/godoo/hishow.php?session=%s" % (self.parse_host, sess),
                       headers={"Referer": page_url}, cookie=True, timeout=10)
        self._diag["hishow"] = js.get("code")
        if js.get("code") != 200 or not js.get("content"):
            return ""
        js_txt = js["content"]
        if isinstance(js_txt, (bytes, bytearray)):
            js_txt = js_txt.decode("utf-8", "ignore")
        sec_m = re.search(r"var SECRET\s*=\s*['\"]([a-f0-9]+)['\"]", js_txt)
        if not sec_m:
            self._diag["secret"] = "no-match"
            return ""
        secret = sec_m.group(1)
        self._diag["secret"] = "ok"
        rand_m = re.search(r"var RANDOM_INDICATORS\s*=\s*(\[[^\]]+\])", js_txt)
        rand_keys = json.loads(rand_m.group(1)) if rand_m else []

        getters = {
            "plugins": "Chrome PDF Viewer",
            "mimeTypes": 2,
            "timezone": -480,
            "language": "zh-CN",
            "hardwareConcurrency": 8,
            "deviceMemory": 8,
            "platform": "Win32",
            "audioFingerprint": "audio_placeholder",
            "fontList": "fonts_placeholder",
            "canvasNoise": "canvas_noise",
            "webglVendor": "Google Inc. (NVIDIA)",
        }
        random_data = {k: getters.get(k, "") for k in rand_keys}
        payload = {
            "sessionId": sess,
            "isTop": True,
            "isRealBrowser": True,
            "isTrusted": False,
            "deviceId": "-1827491203",
            "domain": self.demo_host.replace("https://", "").split("/")[0],
            "randomIndicators": random_data,
        }
        payload_str = json.dumps(payload, separators=(",", ":"))
        sig = hmac.new(secret.encode("utf-8"), payload_str.encode("utf-8"),
                       hashlib.sha256).hexdigest()
        boom = self._req("%s/godoo/boom.php" % self.parse_host,
                         headers={"Referer": page_url, "Origin": self.parse_host},
                         post={"payload": payload, "signature": sig},
                         method="POST", cookie=True, timeout=10)
        boom_txt = boom.get("content") or ""
        if isinstance(boom_txt, (bytes, bytearray)):
            boom_txt = boom_txt.decode("utf-8", "ignore")
        try:
            bj = json.loads(boom_txt)
            self._diag["boom"] = "%s:%s" % (bj.get("success", "?"), bj.get("error", ""))
            # 只在明确失败时中止; success 字段缺失(怪异响应)时继续尝试, 贴近参考源行为
            if bj.get("success") is False:
                return ""
        except Exception:
            self._diag["boom"] = "parse-err"
            return ""

        vurl_m = re.search(r'videoUrl:\s*"([^"]+)"', html)
        if not vurl_m:
            self._diag["videoUrl"] = "no-match"
            return ""
        playback_url = "%s%s" % (self.parse_host, vurl_m.group(1).replace("\\/", "/"))
        pb = self._req(playback_url, headers={"Referer": page_url}, cookie=True, timeout=10)
        self._diag["playback"] = pb.get("code")
        if pb.get("code") != 200 or not pb.get("content"):
            return ""
        pb_html = pb["content"]
        if isinstance(pb_html, (bytes, bytearray)):
            pb_html = pb_html.decode("utf-8", "ignore")

        # specialPlayConfig.playSources (m3u8 解析型)
        spec_m = re.search(r"specialPlayConfig\s*=\s*(\{[\s\S]*?\});", pb_html)
        if spec_m:
            ps_m = re.search(r"playSources:\s*(\[[^\]]*\])", spec_m.group(1))
            if ps_m:
                try:
                    play_sources = json.loads(ps_m.group(1))
                except Exception:
                    play_sources = []
                for src in play_sources:
                    mac_src = src.get("mac_play_source", "") if isinstance(src, dict) else ""
                    if not mac_src:
                        continue
                    if mac_src == "dujia":
                        res_url = "%s&resolve_dujia_plain=1" % playback_url
                    else:
                        res_url = "%s&resolve_special_plain=1&resolve_source=%s" % (
                            playback_url, mac_src)
                    res = self._req(res_url,
                                    headers={"Referer": playback_url,
                                             "Accept": "application/json"}, cookie=True, timeout=10)
                    res_txt = res.get("content") or ""
                    if isinstance(res_txt, (bytes, bytearray)):
                        res_txt = res_txt.decode("utf-8", "ignore")
                    try:
                        rj = json.loads(res_txt)
                        stream_url = rj.get("url", "")
                        if stream_url and stream_url.startswith("http"):
                            with self._lock:
                                self._resolve_cache[target_url] = (stream_url, now + RESOLVE_TTL)
                            return stream_url
                    except Exception:
                        continue

        # normalPlayUrl (直连 m3u8)
        norm_m = re.search(r"normalPlayUrl:\s*['\"]([^'\"]+)['\"]", pb_html)
        if norm_m:
            norm_url = norm_m.group(1).strip()
            if norm_url.startswith("http"):
                with self._lock:
                    self._resolve_cache[target_url] = (norm_url, now + RESOLVE_TTL)
                return norm_url
        return ""

    # ---------- 工具 ----------
    def _int(self, v, default=1):
        try:
            return int(v)
        except Exception:
            return default

    def _safe_label(self, text):
        return str(text or "").replace("$", "＄").replace("#", "＃").strip()

    # ---------- proxy (封面直链无需代理, 仅按契约提供) ----------
    def getProxyUrl(self, params=None, local=True):
        try:
            from com.github.catvod import Proxy
            url = Proxy.getUrl(local)
        except Exception:
            url = "http://127.0.0.1:9978/proxy"
        sk = getattr(self, "siteKey", "") or ""
        return url + "?do=py" + ("&siteKey=%s" % sk if sk else "")

    def proxyUrl(self, params=None, local=True):
        return self.getProxyUrl(params, local)

    def proxy(self, params):
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                return [404, "text/plain", ""]
        if not isinstance(params, dict):
            return [404, "text/plain", ""]
        if params.get("type") == "pic":
            net = getattr(self, "net", None)
            if net is not None and hasattr(net, "reqParts"):
                raw = net.reqParts(params["url"], {"buffer": 3})[1]
            else:
                raw = self._req(params["url"], {"buffer": 3}).get("content") or ""
            return [200, "image/jpeg", self._img_stream(raw), {}]
        return [404, "text/plain", ""]

    localProxy = proxy

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
