# -*- coding: utf-8 -*-
# ============================================================
# ko4.ko43to.com:52000/video (Vv 站点) 影视壳 py 源  v1
# 适配: FongMi(蜂蜜) / 影视仓 / TVBox / OK影视Pro 等
# 参照: _____Vv__.py (旧版), 按 Quss 规范重写
# ------------------------------------------------------------
# 站点接口(2026-11-06 实网逆向):
#   API 集群: mjs.5ntg79qy.com:51999 / mjs.w5i4ygkl.com:52000 / ...
#   列表: /api/v2/home/public/video/list?page=N&limit=20&type=last|good|hot|cate|label&typeId=X&channel=vvmmyjs
#   搜索: /api/v2/home/public/video/search?keyword=K&page=N&limit=20&channel=vvmmyjs
#   详情: /api/v2/home/public/video/long/detail?id=N&channel=vvmmyjs
#   播放: /api/v2/home/user/video/play/url?id=N&channel=vvmmyjs  (需 Bearer token)
#   token: /api-user/v2/login/fingerprint (SHA256("video-view:v1|"+uuid)) + refresh_token
#   分类: /api/v2/home/public/video/cate/list  标签: /api/v2/home/public/video/label/list
#   CDN:  /api/v2/home/public/cdn/index  (动态 picUrl+bucket)
# ------------------------------------------------------------
# ★ 关键契约 (重写新增/修复):
#   1) 封面 .enc 密文 = AES-256-CBC, key="H0Z%7n#k$H8*M7xSE^N@8xXZPG*RZ&wY",
#      iv=前16字节, 明文 JPEG/PNG -> 必须走 proxy 解密 (_pic_url + proxy)
#   2) 播放 m3u8 直链 parse=0; 分片 AES-128 由 m3u8 EXT-X-KEY 提供 key+IV
#      (源内不解密, 播放器按 m3u8 自动拉 key; 沙盒验证解出 TS 0x47)
#   3) 封面 CDN 动态 (cdn/index isDefault), 旧静态 spjq.huibaolian.xin 已失效
#   4) 演员字段站恒空 -> 不做演员点击; 标签 classifyTitles 可点击 -> 本站搜索
# ------------------------------------------------------------
# 配置: {"sites":[{"key":"vv","name":"Vv视频","type":3,"api":"./vv.py",...}]}
# ============================================================
import base64
import gzip
import hashlib
import json
import math
import re
import time
import urllib.parse
import urllib.request
import uuid
import zlib

try:
    import sys
    sys.path.append('..')
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        def proxy(self, params):
            return [404, "text/plain", ""]

        def localProxy(self, params):
            return [404, "text/plain", ""]


_SITE_NAME = "Vv视频"
_CHANNEL = "vvmmyjs"
_SITE_REF = "https://ko4.ko43to.com:52000/"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
_TIMEOUT = 15000

_HOSTS = [
    "https://mjs.5ntg79qy.com:51999",
    "https://mjs.w5i4ygkl.com:52000",
    "https://cns7.da625gu4.com:51666",
    "https://cns7.yz59n9ys.com:51666",
    "https://9sbg.33gl3vju.com:51888",
    "https://9sbg.egnomc4t.com:51888",
    "https://mjs.s6t7y6c8.com:25118",
]

# 封面/分片 CDN 默认(动态 cdn/index 优先)
_DEFAULT_CDN = "https://ww988.sseyy2.uno"
_DEFAULT_BUCKET = "encryption-ts"

# 封面 AES-256-CBC: .enc = iv(16) || ciphertext
_PIC_KEY = b"H0Z%7n#k$H8*M7xSE^N@8xXZPG*RZ&wY"

_FAST = [
    ("last", "最近更新"),
    ("good", "每日精选"),
    ("hot", "热门推荐"),
]

_CATES = [
    ("347", "黑料"),
    ("263", "日本AV"),
    ("262", "国产"),
    ("266", "传媒"),
    ("343", "AV无码"),
    ("344", "AV中字"),
    ("342", "AI换脸"),
    ("341", "三级"),
    ("267", "动漫"),
    ("264", "欧美"),
    ("358", "麻豆"),
    ("345", "女主播"),
    ("346", "VR"),
    ("356", "擦边短剧"),
    ("357", "新闻"),
    ("269", "其他"),
    ("268", "热门"),
]

_LABELS = [
    ("261", "多人运动"),
    ("262", "熟女"),
    ("263", "内衣"),
    ("287", "偶像艺人"),
    ("288", "恋物癖"),
    ("289", "恋乳癖"),
    ("290", "情侣"),
    ("291", "跳舞"),
    ("292", "花痴"),
    ("293", "偷窥"),
    ("294", "恋腿癖"),
    ("295", "性奴"),
    ("296", "姐妹"),
    ("297", "双性人"),
    ("298", "通奸"),
    ("299", "粗暴"),
    ("300", "学校作品"),
    ("301", "恶作剧"),
    ("302", "妄想"),
    ("303", "残忍画面"),
]


def _decrypt(data, key):
    b = re.sub(r'[\r\n\s]+', '', data or '').replace('-', '+').replace('_', '/')
    b += '=' * (-len(b) % 4)
    raw = base64.b64decode(b)
    kb = key.encode('utf-8')
    out = bytes(c ^ kb[i % len(kb)] for i, c in enumerate(raw))
    return out.decode('utf-8', 'replace')


class Spider(BaseSpider):
    def __init__(self):
        self._host = 0
        self._token = {"access": "", "refresh": "", "expire": 0.0}
        self._cdn = {"picUrl": _DEFAULT_CDN, "bucket": _DEFAULT_BUCKET}
        self._cdn_ts = 0.0
        self._cate_cache = None
        self._cate_ts = 0.0

    def init(self, extend=""):
        cfg = {}
        if isinstance(extend, dict):
            cfg = extend
        elif extend:
            try:
                cfg = json.loads(extend)
            except Exception:
                cfg = {}
        self.filter = cfg.get("filter") or {}
        return True

    def getDependence(self):
        return []

    # ---------------- 网络层 ----------------

    def _net_opts(self, opts):
        """5.8.5+/5.8.7 NetAdapter 收 dict; 旧 Java Net(无 _native) 收 JSON 字符串。
        真实 FongMi 5.8.4+ 均为 NetAdapter(有 _native) -> dict。"""
        net = getattr(self, "net", None)
        if net is not None and not hasattr(net, "_native"):
            try:
                return json.dumps(opts)
            except Exception:
                return opts
        return opts

    def _http(self, url, method="GET", body=None, headers=None):
        """返回 (bytes|None, status). self.net 优先, urllib 回退。"""
        net = getattr(self, "net", None)
        if net is not None:
            try:
                opts = {"timeout": _TIMEOUT}
                if method == "POST":
                    opts["method"] = "POST"
                    opts["postType"] = "json"
                    opts["data"] = body if body is not None else {}
                if headers:
                    opts["headers"] = headers
                opts = self._net_opts(opts)
                resp = net.req(url, opts)
                if isinstance(resp, dict):
                    code = resp.get("code") or 0
                    content = resp.get("content", b"")
                    if isinstance(content, str):
                        content = content.encode("utf-8", "replace")
                    elif isinstance(content, list):
                        try:
                            content = bytes(content)
                        except Exception:
                            content = b""
                    return content, code
                if isinstance(resp, str):
                    return resp.encode("utf-8", "replace"), 200
                if isinstance(resp, (bytes, bytearray)):
                    return bytes(resp), 200
                return b"", 0
            except Exception:
                return b"", 0
        return self._http_urllib(url, method=method, body=body, headers=headers)

    def _http_urllib(self, url, method="GET", body=None, headers=None):
        try:
            hdrs = {
                "User-Agent": _UA,
                "Referer": _SITE_REF,
                "Accept": "application/json,text/plain,*/*",
            }
            if headers:
                hdrs.update(headers)
            data = None
            if body is not None:
                data = json.dumps(body).encode("utf-8") if not isinstance(body, (bytes, bytearray)) else body
                hdrs.setdefault("Content-Type", "application/json")
            req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
            with urllib.request.urlopen(req, timeout=_TIMEOUT / 1000.0) as resp:
                raw = resp.read()
                enc = (resp.headers.get("Content-Encoding") or "").lower()
                if enc == "gzip":
                    raw = gzip.decompress(raw)
                elif enc == "deflate":
                    raw = zlib.decompress(raw)
                return raw, resp.getcode() or 0
        except Exception:
            return b"", 0

    def _api(self, path, auth=False, retry_refresh=True, method="GET", body=None):
        headers = None
        if auth:
            tok = self._get_token()
            if not tok:
                return None
            headers = {"Authorization": "Bearer " + tok}
        for k in range(len(_HOSTS)):
            n = (self._host + k) % len(_HOSTS)
            url = _HOSTS[n] + path
            content, status = self._http(url, method=method, body=body, headers=headers)
            if status != 200 or not content:
                continue
            try:
                r = json.loads(content.decode("utf-8", "replace"))
            except Exception:
                continue
            if not isinstance(r, dict):
                continue
            if r.get("code") == 401 and auth and retry_refresh:
                self._token["access"] = ""
                self._token["refresh"] = ""
                return self._api(path, auth=auth, retry_refresh=False)
            if r.get("code") != 200:
                continue
            if isinstance(r.get("data"), str) and r.get("key"):
                try:
                    r["data"] = json.loads(_decrypt(r["data"], r["key"]))
                except Exception:
                    continue
            self._host = n
            return r
        return None

    def _get_token(self):
        now = time.time()
        if self._token["access"] and self._token["expire"] - now > 60:
            return self._token["access"]
        if self._token["refresh"]:
            r = self._api("/api-user/v2/login/refresh_token?channel=" + _CHANNEL,
                          body={"token": self._token["refresh"]}, method="POST")
            if r and isinstance(r.get("data"), dict) and r["data"].get("accessToken"):
                d = r["data"]
                self._token["access"] = d["accessToken"]
                self._token["expire"] = now + int(d.get("accessTokenTtl") or 1800)
                return self._token["access"]
            self._token["refresh"] = ""
        seed = str(uuid.uuid4())
        fp = hashlib.sha256(("video-view:v1|" + seed).encode("utf-8")).hexdigest()
        r = self._api("/api-user/v2/login/fingerprint?channel=" + _CHANNEL,
                      body={"fingerPrint": fp}, method="POST")
        if r and isinstance(r.get("data"), dict) and r["data"].get("accessToken"):
            d = r["data"]
            self._token["access"] = d["accessToken"]
            self._token["refresh"] = d.get("refreshToken") or ""
            self._token["expire"] = now + int(d.get("accessTokenTtl") or 1800)
        return self._token["access"]

    # ---------------- 封面 ----------------

    def _cdn_info(self):
        now = time.time()
        if self._cdn_ts and now - self._cdn_ts < 3600:
            return self._cdn
        r = self._api("/api/v2/home/public/cdn/index?channel=" + _CHANNEL)
        if r:
            lst = (r.get("data") or {}).get("list") or []
            for c in lst:
                if c.get("isDefault") and c.get("picUrl"):
                    self._cdn = {"picUrl": c["picUrl"], "bucket": c.get("bucket") or _DEFAULT_BUCKET}
                    self._cdn_ts = now
                    return self._cdn
            for c in lst:
                if c.get("picUrl"):
                    self._cdn = {"picUrl": c["picUrl"], "bucket": c.get("bucket") or _DEFAULT_BUCKET}
                    self._cdn_ts = now
                    return self._cdn
        return self._cdn

    def _pic(self, thumb):
        if not thumb:
            return ""
        if thumb.startswith("http"):
            return thumb
        cdn = self._cdn_info()
        base = (cdn["picUrl"] or _DEFAULT_CDN).rstrip("/")
        bucket = (cdn["bucket"] or _DEFAULT_BUCKET).strip("/")
        return "%s/%s%s" % (base, bucket, thumb if thumb.startswith("/") else "/" + thumb)

    def _proxy_url(self, params):
        """统一封面/媒体代理 URL，兼容三契约（基类自动拼 do=py&siteKey，不覆写）：
        - 5.8.5+/5.8.7: proxyUrl(params, local)
        - 5.8.4: getProxyUrl(params, local)
        - TVBox: getProxyUrl(local) 只 bool，源内自拼业务参数
        """
        if hasattr(self, "proxyUrl"):
            try:
                return self.proxyUrl(params, True)
            except Exception:
                pass
        gp = getattr(self, "getProxyUrl", None)
        if gp is None:
            return ""
        try:
            import inspect
            names = list(inspect.signature(gp).parameters.keys())
        except Exception:
            names = ["params", "local"]
        if names and names[0] == "params":
            try:
                return gp(params, True)
            except Exception:
                return ""
        try:
            base = gp(True)
        except Exception:
            return ""
        if isinstance(params, dict) and params:
            qs = "&".join("%s=%s" % (k, urllib.parse.quote(str(v))) for k, v in params.items())
            return base + ("&" + qs if qs else "")
        return base

    def _pic_url(self, u):
        if not u:
            return ""
        enc = base64.b64encode(u.encode("utf-8")).decode("utf-8")
        p = self._proxy_url({"type": "pic", "url": enc})
        return p or u

    def _download_img(self, url):
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
        data, status = self._http_urllib(url)
        return data

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
        if isinstance(raw, (bytes, bytearray)) and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
            return "image/webp"
        return "image/jpeg"

    def _pic_decrypt(self, raw):
        if not raw:
            return raw
        if raw[:2] == b"\xff\xd8" or raw[:4] == b"\x89PNG" or raw[:4] == b"RIFF" or raw[:4] == b"WEBP":
            return raw
        if len(raw) < 32:
            return raw
        iv = raw[:16]
        ct = raw[16:]
        n = len(ct) // 16 * 16
        if n <= 0:
            return raw
        try:
            from Crypto.Cipher import AES
            dec = AES.new(_PIC_KEY, AES.MODE_CBC, iv).decrypt(ct[:n])
            return dec
        except Exception:
            pass
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            dec = Cipher(algorithms.AES(_PIC_KEY), modes.CBC(iv)).decryptor()
            pt = dec.update(ct[:n]) + dec.finalize()
            return pt
        except Exception:
            return raw

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
                real = urllib.parse.unquote(str(real))
            except Exception:
                pass
            try:
                real = self._d64(real)
            except Exception:
                pass
            raw = self._download_img(real)
            img = self._pic_decrypt(raw)
            return [200, self._mime(img), self._img_stream(img), {}]
        return [404, "text/plain", ""]

    localProxy = proxy

    # ---------------- 数据 ----------------

    @staticmethod
    def _safe_label(text):
        return str(text or "").replace("$", "＄").replace("#", "＃").strip()

    @staticmethod
    def _vod(item):
        vid = str(item.get("id") or "")
        title = re.sub(r'\s+', ' ', str(item.get("title") or "")).strip()
        remark = str(item.get("classifyTitles") or item.get("labelTitles") or "").strip()
        return {
            "vod_id": vid,
            "vod_name": title or ("视频 %s" % vid),
            "vod_pic": "",
            "vod_remarks": remark,
            "vod_year": (str(item.get("createdAt") or "")[:4]),
        }

    def _parse_list(self, r):
        d = r.get("data") or {}
        lst = d.get("list") or []
        vods = []
        for x in lst:
            if not x.get("id"):
                continue
            v = self._vod(x)
            v["vod_pic"] = self._pic_url(self._pic(x.get("thumb")))
            vods.append(v)
        total = int(d.get("total") or 0)
        pagecount = int(math.ceil(total / 20.0)) if total > 0 else 1
        return vods, pagecount, total

    def _classes(self):
        classes = []
        for tid, name in _FAST:
            classes.append({"type_id": tid, "type_name": name})
        for tid, name in _CATES:
            classes.append({"type_id": "cate:" + tid, "type_name": name})
        for tid, name in _LABELS:
            classes.append({"type_id": "label:" + tid, "type_name": name})
        return classes

    def homeContent(self, filter):
        self.filter = filter or {}
        return {"class": self._classes(), "filters": {}}

    def homeVideoContent(self):
        return self.categoryContent("last", 1, "", None)

    def categoryContent(self, tid, pg, filter, extend=None):
        try:
            pg = int(pg or 1)
        except (TypeError, ValueError):
            pg = 1
        tid = str(tid or "").strip()
        if tid.startswith("actor/") or tid.startswith("tag/"):
            name = urllib.parse.unquote(tid.split("/", 1)[1])
            return self._search(name, pg)
        if tid.startswith("cate:"):
            vtype, tid2 = "cate", tid[5:]
        elif tid.startswith("label:"):
            vtype, tid2 = "label", tid[6:]
        else:
            vtype, tid2 = tid or "last", "0"
        if vtype not in ("last", "good", "hot", "cate", "label"):
            vtype = "last"
        path = "/api/v2/home/public/video/list?page=%d&limit=20&type=%s&typeId=%s&channel=%s" % (
            pg, vtype, tid2, _CHANNEL)
        r = self._api(path)
        if not r:
            return {"list": []}
        vods, pagecount, total = self._parse_list(r)
        return {"list": vods, "page": pg, "pagecount": pagecount, "limit": 20, "total": total}

    def _search(self, kw, pg=1):
        if not kw:
            return {"list": []}
        try:
            pg = int(pg or 1)
        except (TypeError, ValueError):
            pg = 1
        kwq = urllib.parse.quote(str(kw).strip())
        path = "/api/v2/home/public/video/search?keyword=%s&page=%d&limit=20&channel=%s" % (kwq, pg, _CHANNEL)
        r = self._api(path)
        if not r:
            return {"list": []}
        vods, pagecount, total = self._parse_list(r)
        return {"list": vods, "page": pg, "pagecount": pagecount, "limit": 20, "total": total}

    def searchContent(self, key, quick, pg="1"):
        return self._search(str(key or "").strip(), pg)

    def _clickable(self, kind, name):
        if not name:
            return ""
        name = str(name).strip()
        ident = "%s/%s" % (kind, urllib.parse.quote(name, safe=""))
        payload = json.dumps({"id": ident, "name": name, "type_flag": "0"},
                             ensure_ascii=False, separators=(",", ":"))
        return "[a=cr:%s/]%s[/a]" % (payload, name)

    def detailContent(self, ids):
        if not isinstance(ids, list):
            ids = [ids]
        out = []
        for vid_raw in ids:
            vid = re.sub(r'\D', '', str(vid_raw or ""))
            if not vid:
                continue
            r = self._api("/api/v2/home/public/video/long/detail?id=%s&channel=%s" % (vid, _CHANNEL))
            if not r or not isinstance(r.get("data"), dict):
                continue
            out.append(self._detail_vod(vid, r["data"]))
        return {"list": out}

    def _detail_vod(self, vid, d):
        name = re.sub(r'\s+', ' ', str(d.get("title") or "")).strip()
        content = re.sub(r'<[^>]+>', '', str(d.get("content") or ""))
        content = re.sub(r'\s+', ' ', content).strip()
        tags = [t.strip() for t in str(d.get("classifyTitles") or "").split(",") if t.strip()]
        tag_bb = "".join(self._clickable("tag", t) for t in tags)
        if tag_bb:
            content = (content + "\n" if content else "") + tag_bb
        vod = {
            "vod_id": vid,
            "vod_name": name or ("视频 %s" % vid),
            "vod_pic": self._pic_url(self._pic(d.get("thumb"))),
            "type_name": str(d.get("classifyTitles") or _SITE_NAME),
            "vod_year": (str(d.get("createdAt") or "")[:4]),
            "vod_area": "",
            "vod_remarks": str(d.get("labelTitles") or ""),
            "vod_actor": "",
            "vod_director": "",
            "vod_content": content,
            "vod_play_from": "HLS",
            "vod_play_url": "%s$%s" % (self._safe_label(name) or "视频", vid),
        }
        return vod

    def playerContent(self, flag, id, vipFlags=None):
        vid = re.sub(r'\D', '', str(id or ""))
        if not vid:
            for cand in (str(flag or ""), str(vipFlags or "")):
                m = re.search(r'(\d{5,})', cand)
                if m:
                    vid = m.group(1)
                    break
        if not vid:
            return {}
        r = self._api("/api/v2/home/user/video/play/url?id=%s&channel=%s" % (vid, _CHANNEL), auth=True)
        if not r or not isinstance(r.get("data"), dict):
            return {"parse": 0, "msg": "无法获取播放地址"}
        path = r["data"].get("masterUrl") or r["data"].get("p720Url") or r["data"].get("p480Url")
        if not path:
            return {"parse": 0, "msg": "无播放地址"}
        if path.startswith("//"):
            url = "https:" + path
        elif path.startswith("/"):
            url = _HOSTS[self._host % len(_HOSTS)] + path
        else:
            url = path
        return {
            "parse": 0,
            "jx": 0,
            "url": url,
            "format": "application/x-mpegURL",
            "header": {"User-Agent": _UA, "Referer": _SITE_REF},
        }

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4)(\?|$)', url or "", re.I))

    def action(self, action):
        return {"msg": ""}

    def destroy(self):
        return True
