# -*- coding: utf-8 -*-
import json
import re
import time
import base64
import random
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

NAME = "抖阴"
PUBLISH = "https://18dyw.net/"
MAIN_DOMAIN = "feigu.cc"
BACKUP_DOMAIN = "gfwpbqds.cc"
DEFAULT_HOST = "https://dys18.com"
UA = "Mozilla/5.0 (Linux; Android 16; 2510DRK44C Build/BP2A.250605.031.A3) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/143.0.7499.192 Mobile Safari/537.36"
PAGE_SIZE = 23
CACHE_TTL = 1800
AES_KEY = b"f5d965df75336270"
AES_IV = b"97b60394abc2fbe1"
CHARS = "abcdefghjkmnpqrstuvwxy23456789"

VIDEO_CATS = [
    ("llsn", "萝莉少女"), ("mzll", "母子乱伦"), ("crdm", "成人动漫"),
    ("tyjr", "童颜巨乳"), ("xyss", "校园师生"), ("aidj", "AI短剧"),
    ("zwgc", "自慰高潮"), ("tpzp", "偷拍自拍"), ("sqzy", "色情综艺"),
    ("gytq", "勾引偷情"), ("yccm", "原创传媒"), ("zfyh", "制服诱惑"),
    ("gtsj", "港台三级"), ("bhnx", "白虎嫩穴"), ("flj", "福利姬"),
    ("whzb", "网黄主播"), ("rywn", "人妖伪娘"), ("hwds", "户外搭讪"),
    ("amhs", "按摩会所"), ("xyl", "辛尤里"), ("omxa", "欧美性爱"),
    ("nszc", "内射中出"), ("thyp", "探花约啪"), ("drqp", "多人群P"),
    ("yzcz", "野战车震"), ("smdj", "SM调教"), ("lmhq", "绿帽换妻"),
    ("rhll", "日韩伦理"), ("aihl", "AI换脸"), ("hrhm", "黑人黑妹"),
    ("zjgj", "足交肛交"), ("wojj", "玩偶姐姐"), ("tznt", "同志男同"),
    ("ntll", "女同拉拉"), ("jxsp", "精选视频"), ("qjmj", "强奸迷奸"),
    ("dsp", "短视频"), ("snsf", "熟女少妇"), ("zklq", "重口猎奇"),
]
VIDEO_SORTS = [
    ("best-recently", "近期最佳"), ("latest-updates", "最近更新"),
    ("most-viewed", "最多观看"), ("most-favorites", "最多收藏"),
]
MELON_CATS = [
    ("cgxw", "吃瓜新闻"), ("ldgb", "领导干部"), ("hwcg", "海外吃瓜"),
    ("lldd", "伦理道德"), ("mrds", "每日大赛"), ("whhj", "网黄合集"),
    ("mxhl", "明星黑料"), ("whhl", "网红黑料"), ("rmdg", "热门大瓜"),
    ("xsxy", "学生校园"), ("jrcg", "今日吃瓜"), ("fcsn", "反差骚女"),
    ("thtp", "探花偷拍"), ("aidj", "Ai短剧"), ("czdj", "寸止调教"),
    ("sjbkh", "世界杯狂欢"),
]
MELON_SORTS = [
    ("recommend", "推荐"), ("hot", "热门"), ("latest", "最新"),
]
AV_SORTS = [
    ("trending", "最多搜索"), ("new", "最新上线"),
    ("watching", "最多观看"), ("release", "最新发布"),
]
THEME_SORTS = VIDEO_SORTS
ACTOR_SORTS = [
    ("hot-first", "热度优先"), ("name-order", "名称顺序"),
    ("latest-updates", "最近更新"), ("most-videos", "最多影片"),
]

class Spider(BaseSpider):

    def __init__(self):
        self.host = DEFAULT_HOST
        self._host_ts = 0
        self._host_fail = False
        self.options = {}
        self._cache = {}
        self._cache_time = {}

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
        if site and site.startswith("http"):
            self.host = site
        self.options = cfg

    def getDependence(self):
        return []

    def destroy(self):
        self._cache.clear()
        self._cache_time.clear()
        self.options = {}

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {"msg": ""}

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", str(url)))

    # ================= 网络层 (6d++ 全播放器兼容) =================
    def _req(self, url, timeout=15000, buffer=0):
        if not url:
            return None
        h = {"User-Agent": UA}
        net = getattr(self, "net", None)
        if net is not None:
            try:
                opts = {"headers": h, "timeout": timeout, "buffer": buffer}
                # 5.8.4 旧 Java Net 接受 JSON 字符串 options; NetAdapter 接受 dict
                if hasattr(net, "_native"):
                    options = opts
                else:
                    try:
                        options = json.dumps(opts)
                    except Exception:
                        options = opts
                r = net.req(url, options)
                if isinstance(r, dict):
                    if r.get("error"):
                        return None
                    return r.get("content", "")
                return r
            except Exception:
                pass
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout / 1000) as resp:
                return resp.read()
        except Exception:
            return None

    def _text(self, url):
        r = self._req(url)
        if r is None:
            return ""
        if isinstance(r, bytes):
            return r.decode("utf-8", "replace")
        if isinstance(r, (list, tuple)):
            return bytes(r).decode("utf-8", "replace")
        return str(r)

    def _bytes(self, url, timeout=15000):
        r = self._req(url, timeout, buffer=3)
        if isinstance(r, bytes):
            return r
        if isinstance(r, str):
            return r.encode("utf-8", "replace")
        if isinstance(r, (list, tuple)):
            return bytes(r)
        return b""

    # ================= 域名解析 (发布页 → 随机子域) =================
    def _host(self):
        if self._host_ts and time.time() - self._host_ts < CACHE_TTL and not self._host_fail:
            return self.host
        return self._resolve_host()

    def _resolve_host(self):
        self._host_fail = False
        if self._probe(DEFAULT_HOST):
            self.host = DEFAULT_HOST
            self._host_ts = time.time()
            return self.host
        main, backup = self._pub_domains()
        for _ in range(8):
            prefix = "".join(random.choice(CHARS) for _ in range(4))
            for dom in (main, backup):
                if not dom:
                    continue
                h = "https://%s.%s" % (prefix, dom)
                if self._probe(h):
                    self.host = h
                    self._host_ts = time.time()
                    return h
        self.host = DEFAULT_HOST
        self._host_ts = 0
        return self.host

    def _probe(self, url):
        try:
            r = self._req(url + "/")
            if r is None:
                return False
            text = r.decode("utf-8", "replace") if isinstance(r, bytes) else str(r)
            return len(text) > 500 and ("抖阴" in text or "video-item" in text or "dys18" in text)
        except Exception:
            return False

    def _pub_domains(self):
        main, backup = "", ""
        try:
            html = self._text(PUBLISH)
            m = re.search(r"mainDomain\s*=\s*'([^']+)'", html)
            if m:
                main = m.group(1)
            m = re.search(r"backupDomain\s*=\s*'([^']+)'", html)
            if m:
                backup = m.group(1)
        except Exception:
            pass
        return main or MAIN_DOMAIN, backup or BACKUP_DOMAIN

    def _mark_fail(self):
        self._host_fail = True
        self._host_ts = 0

    def _get(self, path):
        if path.startswith("http"):
            url = path
        else:
            url = self._host() + path
        text = self._text(url)
        if not text:
            self._resolve_host()
            if path.startswith("http"):
                url = path
            else:
                url = self.host + path
            text = self._text(url)
        return text

    # ================= 小工具 =================
    def _e64(self, text):
        try:
            return base64.b64encode(text.encode("utf-8")).decode("utf-8")
        except Exception:
            return ""

    def _d64(self, text):
        try:
            return base64.b64decode(text.encode("utf-8")).decode("utf-8")
        except Exception:
            return ""

    def _clean(self, text):
        return re.sub(r"\s+", " ", str(text or "")).strip()

    def _strip_tags(self, html):
        return self._clean(re.sub(r"<[^>]+>", " ", str(html or "")))

    def _int(self, v, default=1):
        try:
            return int(v)
        except Exception:
            return default

    def _clickable(self, kind, ident, name=None):
        name = str(name or ident or "").strip()
        ident = str(ident or "").strip()
        if not ident:
            return ""
        enc = quote(ident, safe="")
        return '[a=cr:{"id":"%s/%s","name":"%s"}/]%s[/a]' % (
            kind, enc, name.replace('"', ""), name)

    def _ext(self, extend):
        if isinstance(extend, dict):
            return extend
        if isinstance(extend, str):
            extend = extend.strip()
            if not extend or extend in ("{}", "null", "undefined"):
                return {}
            try:
                return json.loads(extend)
            except Exception:
                out = {}
                for part in extend.split("&"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        out[k] = v
                return out
        return {}

    # ================= 封面代理 (AES-CBC 解密) =================
    def _proxy_url(self, params):
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
                pass
        try:
            base = gp(True)
        except Exception:
            base = gp()
        if isinstance(params, dict) and params:
            qs = "&".join("%s=%s" % (k, quote(str(v), safe="")) for k, v in params.items())
            if qs:
                base = base + ("&" if "?" in base else "?") + qs
        return base

    def _pic(self, u):
        u = (u or "").strip()
        if not u:
            return ""
        return self._proxy_url({"type": "pic", "url": self._e64(u)})

    def _pic_frame(self, u):
        if not u:
            return ""
        if hasattr(self, "proxyUrl"):
            try:
                return self.proxyUrl({"type": "pic", "url": self._e64(u), "ext": ".jpg"}, True)
            except Exception:
                pass
        gp = getattr(self, "getProxyUrl", None)
        if gp is not None:
            try:
                import inspect
                names = list(inspect.signature(gp).parameters.keys())
            except Exception:
                names = ["params", "local"]
            if names and names[0] == "params":
                try:
                    return gp({"type": "pic", "url": self._e64(u), "ext": ".jpg"}, True)
                except Exception:
                    pass
            base = ""
            try:
                base = gp(True)
            except Exception:
                base = gp()
            if base:
                return base + ("&" if "?" in base else "?") + \
                    "type=pic&url=%s&ext=.jpg" % quote(self._e64(u), safe="")
        return ""

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

    def _pic_decrypt(self, raw):
        if not raw:
            return b""
        if raw[:3] == b"\xff\xd8\xff" or raw[:8] == b"\x89PNG\r\n\x1a\n":
            return raw
        try:
            from Crypto.Cipher import AES
            dec = AES.new(AES_KEY, AES.MODE_CBC, AES_IV).decrypt(raw)
            pad = dec[-1]
            if 1 <= pad <= 16 and dec[-pad:] == bytes([pad]) * pad:
                dec = dec[:-pad]
            else:
                dec = dec.rstrip(b"\x00")
            return dec
        except Exception:
            return raw

    def _mime(self, data):
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if data[:6] in (b"GIF87a", b"GIF89a"):
            return "image/gif"
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "image/webp"
        return "image/jpeg"

    def _gallery_imgs(self, html):
        if not html:
            return []
        body = html
        am = re.search(r'<article[^>]*>(.*?)</article>', html, re.DOTALL)
        if am:
            body = am.group(1)
        imgs = []
        for m in re.finditer(r'data-src="(https://[^"]+)"', body):
            u = m.group(1)
            if u and u not in imgs:
                imgs.append(u)
        return imgs

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
            url = self._d64(params.get("url", ""))
            if not url:
                return [404, "text/plain", ""]
            raw = self._bytes(url)
            img = self._pic_decrypt(raw)
            if not img:
                return [404, "text/plain", ""]
            return [200, self._mime(img), self._img_stream(img), {}]
        if ptype == "gallery":
            kind = params.get("kind", "melon")
            vid = params.get("vid", "")
            text = self._get("/%s/detail/%s" % (kind, vid)) if kind in ("melon", "video", "av") else ""
            imgs = self._gallery_imgs(text)
            lines = ["#EXTM3U"]
            for img in imgs:
                u = self._pic_frame(img)
                if u:
                    lines.append("#EXTINF:3.000,")
                    lines.append(u)
            if len(lines) <= 1:
                return [404, "text/plain", ""]
            body = "\n".join(lines)
            return [200, "application/x-mpegURL", self._img_stream(body.encode("utf-8")), {}]
        return [404, "text/plain", ""]

    localProxy = proxy

    # ================= 卡解析 =================
    def _vod(self, kind, vid, title, pic, remarks=""):
        return {
            "vod_id": "%s/%s" % (kind, vid),
            "vod_name": title or vid,
            "vod_pic": pic or "",
            "vod_remarks": remarks or "",
        }

    def _parse_video_cards(self, html):
        result = []
        if not html:
            return result
        blocks = re.split(r'<div class="video-item">', html)[1:]
        for blk in blocks:
            hm = re.search(r'href="/(video|av)/detail/(\d+)"', blk)
            if not hm:
                continue
            kind = hm.group(1)
            vid = hm.group(2)
            if not re.search(r'/media/m3u8', blk):
                continue
            # 广告卡/弹窗链接是外部域名 (https://...)，不会匹配 /detail/；
            # 真视频卡的 /detail/ 必须在 data-url=/media/m3u8 之前（广告弹窗在块尾）
            dpos = blk.find("/media/m3u8")
            if dpos >= 0:
                if blk.find('href="/%s/detail/%s' % (kind, vid)) > dpos:
                    continue
            img = re.search(r'data-src="([^"]+)"', blk)
            pic = self._pic(img.group(1)) if img else ""
            title = vid
            h3 = re.search(r'<h3[^>]*>([^<]+)</h3>', blk)
            if h3:
                title = self._clean(h3.group(1))
            if not title or title == vid:
                alt = re.search(r'alt="([^"]*)"', blk)
                title = self._clean(alt.group(1)) if alt else vid
            dur = ""
            d1 = re.search(r'<span class="text-sm ml-auto">([^<]+)</span>', blk)
            if d1:
                dur = self._clean(d1.group(1))
            if not dur:
                d2 = re.search(r'<div class="text-sm opacity-50[^"]*">\s*([^<]+)\s*</div>', blk)
                if d2:
                    dur = self._clean(d2.group(1))
            result.append(self._vod(kind, vid, title, pic, dur))
        return self._dedupe(result)

    def _parse_melon_cards(self, html):
        result = []
        if not html:
            return result
        for blk in re.split(r'<a href="/melon/detail/', html)[1:]:
            mid = blk.split('"', 1)[0]
            if not mid.isdigit():
                continue
            img = re.search(r'data-src="([^"]+)"', blk)
            pic = self._pic(img.group(1)) if img else ""
            title = mid
            tm = re.search(r'post-item-title[^>]*>(.*?)</h2>', blk, re.DOTALL)
            if tm:
                title = self._strip_tags(re.sub(r'<div class="wrap">.*?</div>', '', tm.group(1), flags=re.DOTALL))
            dm = re.search(r'<span>(\d{4}-\d{2}-\d{2})</span>', blk)
            remarks = dm.group(1) if dm else ""
            result.append(self._vod("melon", mid, title, pic, remarks))
        return self._dedupe(result)

    def _parse_theme_cards(self, html):
        result = []
        if not html:
            return result
        for blk in re.split(r'<li class="group theme-item">', html)[1:]:
            m = re.search(r'href="/av/theme/([a-z0-9]+)/', blk)
            if not m:
                continue
            slug = m.group(1)
            img = re.search(r'data-src="([^"]+)"', blk)
            pic = self._pic(img.group(1)) if img else ""
            name = slug
            alt = re.search(r'alt="([^"]*)"', blk)
            if alt and alt.group(1):
                name = self._clean(alt.group(1))
            strong = re.search(r'<strong[^>]*>\s*([^<]+)', blk)
            if strong and strong.group(1):
                name = self._clean(strong.group(1))
            result.append({
                "vod_id": "folder/theme/%s" % slug,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": "",
                "vod_tag": "folder",
            })
        return self._dedupe(result)

    def _parse_actor_cards(self, html):
        result = []
        if not html:
            return result
        for blk in re.split(r'<li class="group">', html)[1:]:
            m = re.search(r'href="/av/actors-video/(\d+)/', blk)
            if not m:
                continue
            aid = m.group(1)
            img = re.search(r'data-src="([^"]+)"', blk)
            pic = self._pic(img.group(1)) if img else ""
            name = aid
            strong = re.search(r'<strong[^>]*>\s*([^<]+)', blk)
            if strong:
                name = self._clean(strong.group(1))
            remarks = ""
            rm = re.search(r'(\d+)\s*(?:部|个|作品|视频)', blk)
            if rm:
                remarks = rm.group(1) + "部"
            result.append({
                "vod_id": "folder/actor/%s" % aid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": remarks,
                "vod_tag": "folder",
            })
        return self._dedupe(result)

    def _parse_tag_cards(self, html):
        result = []
        if not html:
            return result
        for blk in re.split(r'<li class="flex rounded group">', html)[1:]:
            m = re.search(r'href="/av/tag/([^"]+)"', blk)
            if not m:
                continue
            tag = unquote(m.group(1))
            name = tag
            h3 = re.search(r'<h3[^>]*>\s*([^<]+)', blk)
            if h3:
                name = self._clean(h3.group(1))
            result.append({
                "vod_id": "folder/tag/%s" % tag,
                "vod_name": name,
                "vod_pic": "",
                "vod_remarks": "",
                "vod_tag": "folder",
            })
        return self._dedupe(result)

    def _dedupe(self, items):
        seen = set()
        out = []
        for it in items:
            vid = it.get("vod_id")
            if vid and vid not in seen:
                seen.add(vid)
                out.append(it)
        return out

    # ================= 列表抓取 =================
    def _list_videos(self, path):
        html = self._get(path)
        return self._parse_video_cards(html)

    def _pagecount(self, html, default=1):
        if not html:
            return default
        total = re.search(r'data-rec-total="(\d+)"', html)
        per = re.search(r'data-rec-per-page="(\d+)"', html)
        if total and per and int(per.group(1)) > 0:
            t = int(total.group(1))
            p = int(per.group(1))
            if t > 0:
                return (t + p - 1) // p
        if re.search(r'<link rel="next"', html):
            return 999
        return default

    def _page(self, items, pg, pagecount=999, per=None):
        pagecount = pagecount if pagecount > 1 else 1
        per = per if per else (len(items) or PAGE_SIZE)
        return {
            "list": items,
            "page": pg,
            "pagecount": pagecount,
            "limit": per,
            "total": pagecount * per,
        }

    def _folder_page(self, items, pg, pagecount=1):
        return {
            "list": items,
            "page": pg,
            "pagecount": pagecount,
            "limit": len(items) or PAGE_SIZE,
            "total": len(items),
        }

    # ================= 首页 =================
    def homeContent(self, filter):
        classes = [
            {"type_id": "video", "type_name": "精选AV"},
            {"type_id": "melon", "type_name": "黑料吃瓜"},
            {"type_id": "av", "type_name": "AV影片"},
            {"type_id": "folder/theme/_", "type_name": "🎭 影片主题"},
            {"type_id": "folder/actor/_", "type_name": "💃 AV女优"},
            {"type_id": "folder/tag/_", "type_name": "🏷️ AV标签"},
        ]
        result = {"class": classes}
        if filter:
            result["filters"] = {
                "video": [
                    {"key": "cat", "name": "分类", "value": [{"n": n, "v": v} for v, n in VIDEO_CATS]},
                    {"key": "sort", "name": "排序", "value": [{"n": n, "v": v} for v, n in VIDEO_SORTS]},
                ],
                "melon": [
                    {"key": "cat", "name": "分类", "value": [{"n": n, "v": v} for v, n in MELON_CATS]},
                    {"key": "sort", "name": "排序", "value": [{"n": n, "v": v} for v, n in MELON_SORTS]},
                ],
                "av": [
                    {"key": "cateId", "name": "类型", "value": [{"n": n, "v": v} for v, n in AV_SORTS]},
                ],
                "folder/theme/_": [
                    {"key": "by", "name": "影片排序", "value": [{"n": n, "v": v} for v, n in THEME_SORTS]},
                ],
                "folder/actor/_": [
                    {"key": "by", "name": "女优排序", "value": [{"n": n, "v": v} for v, n in ACTOR_SORTS]},
                ],
            }
        result["list"] = self._list_videos("/video/drqp/best-recently")
        return result

    def homeVideoContent(self):
        return {"list": self._list_videos("/video/drqp/best-recently")}

    # ================= 分类 =================
    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        ext = self._ext(extend) or {}
        if tid == "video":
            cat = ext.get("cat", "") or "drqp"
            sort = ext.get("sort", "") or "latest-updates"
            html = self._get("/video/%s/%s/%d" % (cat, sort, pg))
            items = self._parse_video_cards(html)
            return self._page(items, pg, self._pagecount(html))
        if tid == "melon":
            cat = ext.get("cat", "") or "cgxw"
            sort = ext.get("sort", "") or "latest"
            html = self._get("/melon/%s/%s/%d" % (cat, sort, pg))
            items = self._parse_melon_cards(html)
            return self._page(items, pg, self._pagecount(html))
        if tid == "av":
            sort = ext.get("cateId", "") or "trending"
            html = self._get("/av/%s/%d" % (sort, pg))
            items = self._parse_video_cards(html)
            return self._page(items, pg, self._pagecount(html))
        if tid == "folder/theme/_":
            html = self._get("/av/theme")
            return self._folder_page(self._parse_theme_cards(html), pg)
        if tid.startswith("folder/theme/"):
            slug = unquote(tid.split("/", 2)[2])
            sort = ext.get("by", "") or "latest-updates"
            html = self._get("/av/theme/%s/%s/%d" % (slug, sort, pg))
            items = self._parse_video_cards(html)
            return self._page(items, pg, self._pagecount(html))
        if tid == "folder/actor/_":
            by = ext.get("by", "") or "hot-first"
            html = self._get("/av/actors-list/%s/%d" % (by, pg))
            items = self._parse_actor_cards(html)
            return self._page(items, pg, self._pagecount(html))
        if tid.startswith("folder/actor/"):
            aid = unquote(tid.split("/", 2)[2])
            sort = ext.get("by", "") or "latest-updates"
            html = self._get("/av/actors-video/%s/%s/%d" % (aid, sort, pg))
            items = self._parse_video_cards(html)
            return self._page(items, pg, self._pagecount(html))
        if tid == "folder/tag/_":
            html = self._get("/av/tag")
            return self._folder_page(self._parse_tag_cards(html), pg)
        if tid.startswith("folder/tag/"):
            tag = unquote(tid.split("/", 2)[2])
            html = self._get("/av/tag/%s/%d" % (quote(tag, safe=""), pg))
            items = self._parse_video_cards(html)
            return self._page(items, pg, self._pagecount(html))
        if tid.startswith("video_tag/"):
            tag = unquote(tid.split("/", 1)[1])
            html = self._get("/video/tag/%s" % quote(tag, safe=""))
            items = self._parse_video_cards(html)
            return self._page(items, pg, 1)
        if tid.startswith("actor/"):
            name = unquote(tid.split("/", 1)[1])
            html = self._get("/search/%s" % quote(name, safe=""))
            items = self._parse_video_cards(html)
            return self._page(items, pg, 1)
        if tid.startswith("public_video/"):
            uid = unquote(tid.split("/", 1)[1])
            html = self._get("/public-video/%s/list/%d" % (uid, pg))
            items = self._parse_video_cards(html)
            return self._page(items, pg, self._pagecount(html))
        return self._page([], pg, 1)

    # ================= 搜索 =================
    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        key = str(key or "").strip()
        if not key:
            return self._page([], pg, 1)
        if pg > 1:
            return self._page([], pg, 1)
        html = self._get("/search/%s" % quote(key, safe=""))
        items = self._parse_video_cards(html)
        return self._page(items, pg, 1)

    # ================= 详情 =================
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        results = []
        for vid_id in ids:
            vid_id = str(vid_id)
            parts = vid_id.split("/", 1)
            if len(parts) != 2:
                continue
            kind, vid = parts
            v = self._detail_vod(kind, vid)
            if v:
                results.append(v)
        if not results:
            return {"list": []}
        return {"list": results}

    def _match_brace(self, text, start):
        """从 text[start]='{' 起做花括号配平, 返回完整子串 (含括号)。"""
        if start >= len(text) or text[start] != "{":
            return ""
        depth = 0
        i = start
        while i < len(text):
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
            i += 1
        return ""

    def _detail_vod(self, kind, vid):
        html = self._get("/%s/detail/%s" % (kind, vid))
        if not html:
            return None
        d = {}
        dm = re.search(r'const _detail_ = \{', html)
        if dm:
            raw = self._match_brace(html, dm.start() + len("const _detail_ = "))
            if raw:
                try:
                    d = json.loads(raw)
                except Exception:
                    d = {}
        title = d.get("title") or ""
        if not title:
            tm = re.search(r'<title>([^<]+)</title>', html)
            if tm:
                title = self._clean(tm.group(1))
                title = re.split(r'\s*[-|]\s*(?:免费|高清|播放|在线|抖阴|dys18)', title)[0].strip()
        pic = d.get("poster") or ""
        if not pic:
            pm = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            if pm and "default" not in pm.group(1):
                pic = pm.group(1)
        desc = ""
        dm2 = re.search(r'<meta name="description" content="([^"]*)"', html)
        if dm2:
            desc = self._clean(dm2.group(1))
        if not desc:
            am2 = re.search(r'<article[^>]*>(.*?)</article>', html, re.DOTALL)
            if am2:
                txt = re.sub(r"<[^>]+>", " ", am2.group(1))
                txt = re.sub(r"\s+", " ", txt).strip()
                if len(txt) > 40:
                    desc = txt
        duration = ""
        dur = re.search(r'"duration"\s*:\s*"PT(\d+)M(\d+)S"', html)
        if dur:
            duration = "%d:%02d" % (int(dur.group(1)), int(dur.group(2)))
        date = ""
        times = d.get("times") or ""
        if times:
            date = times[:10]
        else:
            up = re.search(r'"uploadDate"\s*:\s*"([^"]+)"', html)
            if up:
                date = up.group(1)[:10]
        tags = []
        tag = d.get("tag") or ""
        if tag:
            tags = [t.strip() for t in tag.split(",") if t.strip()]
        if not tags:
            gm = re.search(r'"genre"\s*:\s*\[(.*?)\]', html)
            if gm:
                tags = [t.strip().strip('"') for t in gm.group(1).split(",") if t.strip()]
        author_name = d.get("user_name") or ""
        author_uid = ""
        au = re.search(r'public-video/(\d+)/list', html)
        if au:
            author_uid = au.group(1)
        category = ""
        ldm = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
        if ldm:
            try:
                ld = json.loads(ldm.group(1))
                for g in (ld.get("@graph") or []):
                    if g.get("@type") == "BreadcrumbList":
                        for it in (g.get("itemListElement") or []):
                            nm = self._clean(it.get("name", ""))
                            if nm and nm not in ("抖阴成人网", "抖阴"):
                                category = nm
                                break
                        if category:
                            break
                    if not category and g.get("@type") in ("NewsArticle", "Article"):
                        nm = self._clean(g.get("articleSection", ""))
                        if nm:
                            category = nm
                            break
            except Exception:
                pass

        # 演员：标题 " - " 拆分 (av 详情如 "xxx - 佐仓绊"; video/melon 无)
        actor_name = ""
        title_parts = re.split(r"\s+-\s+", title or "")
        if len(title_parts) > 1:
            for seg in title_parts[1:]:
                seg = seg.strip()
                if seg and not re.search(r"(免费|高清|播放|在线|抖阴|dys18|资源|下载)", seg):
                    actor_name = seg
                    break
        vod = {
            "vod_id": "%s/%s" % (kind, vid),
            "vod_name": title or vid,
            "vod_pic": self._pic(pic),
            "type_name": category or "",
            "vod_remarks": " ".join(filter(None, [duration, date])),
            "vod_actor": self._clickable("actor", actor_name) if actor_name else "",
            "vod_content": desc or "",
        }
        content_lines = []
        if tags:
            content_lines.append("标签：" + "、".join(tags))
        if author_name:
            content_lines.append("作者：" + author_name)
        if desc:
            content_lines.append(desc)
        if content_lines:
            vod["vod_content"] = "\n".join(content_lines)
        if kind == "melon":
            play_from = ["正片"]
            play_urls = ["%s/%s" % (kind, vid)]
            imgs = self._gallery_imgs(html)
            if imgs:
                play_from.append("图集")
                play_urls.append("gallery:%s/%s" % (kind, vid))
            vod["vod_play_from"] = "$$$".join(play_from)
            vod["vod_play_url"] = "$$$".join(play_urls)
        else:
            vod["vod_play_from"] = "正片"
            vod["vod_play_url"] = "正片$%s/%s" % (kind, vid)
        return vod

    # ================= 播放 =================
    def playerContent(self, flag, id, vipFlags):
        id = str(id or "")
        if not id:
            return {"parse": 0, "msg": "无法获取播放地址"}
        if id.startswith("gallery:"):
            kv = id.split(":", 1)[1]
            parts = kv.split("/", 1)
            if len(parts) == 2:
                url = self._proxy_url({"type": "gallery", "kind": parts[0], "vid": parts[1], "ext": ".m3u8"})
                if url:
                    return {"parse": 0, "url": url}
            return {"parse": 0, "msg": "无法获取图集"}
        parts = id.split("/", 1)
        if len(parts) == 2:
            kind, vid = parts
            play = self._fetch_play(kind, vid)
            if play:
                return {"parse": 0, "url": play, "header": {"User-Agent": UA, "Referer": self.host + "/"}}
        return {"parse": 0, "msg": "无法获取播放地址"}

    def _fetch_play(self, kind, vid):
        html = self._get("/%s/detail/%s" % (kind, vid))
        if not html:
            return ""
        params = self._extract_dp_params(html, kind)
        if not params:
            return ""
        t = int(time.time() // 1800)
        if kind == "melon":
            url = "/melon/melon-detail-play?u=%s&c=%s&t=%d" % (
                quote(params.get("u", ""), safe=""), quote(params.get("c", ""), safe=""), t)
        else:
            url = "/%s/detail-play?e=%s&id=%s&img=%s&ads=%s&u=%s&t=%d" % (
                kind, quote(params.get("e", ""), safe=""), vid,
                params.get("img", ""), params.get("ads", ""),
                quote(params.get("u", ""), safe=""), t)
        play_html = self._get(url)
        ev = self._first_eval(play_html)
        if not ev:
            return ""
        up = self._unpack_eval(ev)
        if not up:
            return ""
        m = re.search(r'(/media/m3u8\?[^"\' \\)]+)', up)
        if m:
            return self.host + m.group(1)
        return ""

    # ================= eval 解包 (站点混淆) =================
    def _first_eval(self, html):
        m = re.search(r"eval\(function\(p,a,c,k,e,d\)\{.*?\}\)\)", html, re.DOTALL)
        return m.group(0) if m else None

    def _unpack_eval(self, code):
        m = re.search(r"\('((?:[^'\\]|\\.)*)',(\d+),(\d+),'", code)
        if not m:
            return None
        template = m.group(1).replace("\\'", "'").replace('\\"', '"')
        base = int(m.group(2))
        sm = re.search(r"'([^']+)'\.split\('\|'\)", code)
        if not sm:
            return None
        parts = sm.group(1).split('|')
        result = []
        i = 0
        while i < len(template):
            ch = template[i]
            if ch.isalnum() or ch == '_':
                j = i
                while j < len(template) and (template[j].isalnum() or template[j] == '_'):
                    j += 1
                token = template[i:j]
                idx = 0
                valid = True
                for c in token:
                    if '0' <= c <= '9':
                        dd = ord(c) - ord('0')
                    elif 'a' <= c <= 'z':
                        dd = ord(c) - ord('a') + 10
                    elif 'A' <= c <= 'Z':
                        dd = ord(c) - ord('A') + 36
                    else:
                        valid = False
                        break
                    idx = idx * base + dd
                if valid and 0 <= idx < len(parts) and parts[idx]:
                    result.append(parts[idx])
                else:
                    result.append(token)
                i = j
            else:
                result.append(ch)
                i += 1
        return ''.join(result)

    def _extract_dp_params(self, html, kind):
        ev = self._first_eval(html)
        if not ev:
            return {}
        up = self._unpack_eval(ev)
        if not up:
            return {}
        if kind == "melon":
            u = re.search(r'encodeURIComponent\("([^"]+)"\)', up)
            c = re.search(r'&c=(https?://[^"]+?)&t=', up)
            if u and c:
                return {"u": u.group(1), "c": c.group(1)}
            return {}
        e = re.search(r'encodeURIComponent\("([^"]*)"\)\+"&id="', up)
        u = re.search(r'encodeURIComponent\("([^"]+)"\)\+"&t="', up)
        img = re.search(r'&img=([^&]+)&ads=', up)
        ads = re.search(r'&ads=([^&]+)&u=', up)
        if u and img and ads:
            return {
                "e": e.group(1) if e else "",
                "u": u.group(1),
                "img": img.group(1),
                "ads": ads.group(1),
            }
        return {}
