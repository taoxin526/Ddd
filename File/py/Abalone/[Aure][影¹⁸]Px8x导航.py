# -*- coding: utf-8 -*-
# =============================================================================
# [Aure][影18]Px8x导航.py — px8x.com 导航聚合源
# 入口: px8x.com / yt8x.com / fkk8.com → 302/meta → www.x69x69.com 导航页
# 导航页列 3 个子站: Px8x成人网(www.8xx6.lol) / 黑料社(www.heix8.cc) / 油条视频(www.yt8x1.top)
#
# 结构 (folder 两级):
#   一级 tab: 3 个站点 folder (folder/<site>/_, 不带 type_flag)
#   二级: categoryContent("folder/<site>/_") → 该站分类 folder 卡 (vod_tag="folder")
#   三级: categoryContent("folder/<site>/<cat_id>") → 视频卡
#   homeContent.list → Px8x 国产推荐 (降级: 3 个站点 folder 卡)
#
# 站点契约:
#   Px8x成人网 (www.8xx6.lol): HTML 站, 标题 base64+span 混淆 d('...'), 列表 /list/<id>-<pg>.html,
#       详情 /video/<id>.html, 播放 m.892539.xyz/play.php?site_id&source_id (明文 m3u8 直链)
#   黑料社 (www.heix8.cc): HTML 站, 列表 /video_list/<cat>/<pg>/index.html (pagesize=总数),
#       详情 /video_detail/<id>/<cat>/index.html → conter 页 Play= m3u8 直链, 搜索 /?m=video_search*<kw>*<pg>
#   油条视频 (www.yt8x1.top): Vue SPA + AES-CTR 加密 API (key=wK05tMq7sH2aP1cQ6eB9rV3fG4hL8nDx),
#       列表/详情/搜索全走 POST /api/*, 播放 /api/video/hls/index.m3u8?url=<b64> 明文 m3u8 (parse=0)
# =============================================================================
import json
import re
import time
import threading
import base64
import os
import urllib.request
import urllib.error
from urllib.parse import quote, unquote

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        def proxy(self, params):
            return [404, "text/plain", ""]
        def localProxy(self, params):
            return [404, "text/plain", ""]

NAME = "Px8x导航"
HOSTS = ["https://www.x69x69.com"]
UA = "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 20
CACHE_TTL = 30
DEBUG = False
VOD_ID_PREFIX = ""

# ---- 三站配置 ----
SITE_PX8X = "px8x"
SITE_HEIX8 = "heix8"
SITE_YT8X = "yt8x1"

PX8X_HOST = "https://www.8xx6.lol"
HEIX8_HOST = "https://www.heix8.cc"
YT8X_HOST = "https://www.yt8x1.top"

# 油条视频 AES key
YT_KEY = b"wK05tMq7sH2aP1cQ6eB9rV3fG4hL8nDx"

# Px8x 分类 (id, name) — 8 主分类 + 3 独立补充 (去重: 901169/911169/921169/931169 与主分类同源)
PX8X_CATS = [
    ("901179", "国产"), ("911179", "有码"), ("921179", "无码"),
    ("931179", "欧美"), ("941179", "传媒"), ("951179", "探花"),
    ("961179", "中文"), ("971179", "动漫"),
    ("891319", "日韩无码"), ("901339", "日本无码"), ("901309", "欧美极品"),
]

# 黑料社分类 (id, name)
HEIX8_CATS = [
    ("1", "精品推荐"), ("2", "主播秀色"), ("3", "日本有码"), ("4", "日本无码"),
    ("5", "中文字幕"), ("6", "童颜巨乳"), ("7", "性感人妻"), ("8", "强奸乱伦"),
    ("9", "欧美情色"), ("10", "三级伦理"), ("11", "卡通动漫"), ("12", "丝袜OL"),
    ("13", "自拍偷拍"), ("14", "日本片商"), ("15", "剧情介绍"), ("16", "网曝系列"),
    ("17", "同性恋"), ("18", "探花嫖娼"), ("19", "国产人妻"), ("20", "国产SM"),
    ("21", "国产丝袜"), ("22", "麻豆传媒"), ("23", "国产乱伦"), ("24", "明星换脸"),
    ("25", "主奴调教"), ("26", "凌辱快感"), ("27", "多人群交"), ("28", "角色剧情"),
    ("29", "港台辣妹"), ("30", "重口性癖"), ("31", "变性伪娘"), ("32", "VR视角"),
]

# 油条视频分类 (id, name)
YT8X_CATS = [
    ("1", "无码专区"), ("2", "麻豆传媒"), ("3", "制服诱惑"), ("4", "三级伦理"),
    ("5", "AI换脸"), ("6", "中文字幕"), ("7", "卡通动漫"), ("8", "欧美系列"),
    ("9", "美女主播"), ("10", "国产自拍"), ("11", "熟女人妻"), ("12", "萝莉少女"),
    ("13", "女同性爱"), ("14", "多人群交"), ("15", "美乳巨乳"), ("16", "强奸乱伦"),
    ("33", "抖音视频"), ("34", "韩国主播"), ("35", "网红头条"), ("36", "网爆黑料"),
    ("37", "欧美无码"), ("38", "女优明星"), ("39", "SM调教"), ("40", "AV解说"),
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

    # ============ 首页 ============
    def homeContent(self, filter):
        classes = self._classes()
        result = {"class": classes}
        if filter:
            result["filters"] = self._filters(classes)
        # 首页推荐: 依次尝试 Px8x → 黑料社 → 油条视频 的推荐, 第一个成功者
        for site, cat, fn in ((SITE_PX8X, "901179", self._px8x_list),
                              (SITE_HEIX8, "1", self._heix8_list),
                              (SITE_YT8X, "1", self._yt8x_list)):
            try:
                items, _ = fn(cat, 1)
                if items:
                    result["list"] = [self._to_vod(site, x) for x in items]
                    return result
            except Exception:
                continue
        result["list"] = [self._folder_vod(site, "_", name) for site, name in self._sites()]
        return result

    def homeVideoContent(self):
        return {"list": []}

    # ============ 分类 ============
    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        if tid.startswith("folder/"):
            return self._handle_folder(tid, pg)
        return self._fetch_list(tid, pg)

    # ============ 详情 ============
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        responses = [self._detail(str(video_id)) for video_id in ids]
        merged = {k: v for k, v in (responses[0] or {}).items() if k != "list"}
        merged["list"] = [item for response in responses for item in (response.get("list") or [])]
        return merged

    # ============ 搜索 ============
    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        items = self._fetch_search(str(key or "").strip(), pg)
        return {
            "list": items,
            "page": pg,
            "pagecount": 9999 if len(items) >= PAGE_SIZE else pg,
            "limit": PAGE_SIZE,
            "total": len(items),
        }

    # ============ 播放 ============
    def playerContent(self, flag, id, vipFlags):
        url = self._fetch_play(str(id or ""))
        if not url:
            return {"parse": 0, "msg": "无法获取播放地址"}
        header = {"User-Agent": UA}
        site, _, _ = self._parse_site_vid(str(id or ""))
        if site == SITE_YT8X:
            header["Referer"] = YT8X_HOST + "/"
        elif site == SITE_PX8X:
            header["Referer"] = PX8X_HOST + "/"
        return {
            "parse": 0,
            "jx": 0,
            "url": url,
            "header": header,
        }

    def liveContent(self, url):
        return "[]"

    # ================= Folder 层级 =================
    def _sites(self):
        return [
            (SITE_PX8X, "Px8x成人网"),
            (SITE_HEIX8, "黑料社"),
            (SITE_YT8X, "油条视频"),
        ]

    def _folder_vod(self, type_, value, name, count=None, pic=""):
        card = {
            "vod_id": "folder/%s/%s" % (type_, value),
            "vod_name": str(name or value or ""),
            "vod_pic": pic,
            "vod_remarks": ("%s部" % count) if count else "",
            "vod_tag": "folder",
        }
        return card

    def _classes(self):
        hit = self._cache.get("__cls")
        if hit and time.time() - self._cache_time.get("__cls", 0) < CACHE_TTL:
            return hit[0]
        arr = []
        # 三个站点 folder tab (不带 type_flag, 多列由用户 JSON 配置)
        for site, name in self._sites():
            arr.append({"type_id": "folder/%s/_" % site, "type_name": "🗂️ " + name})
        with self._lock:
            self._cache["__cls"] = (arr, time.time())
        return arr

    def _filters(self, classes):
        return {}

    def _handle_folder(self, tid, pg):
        parts = tid.split("/")
        site = parts[1] if len(parts) > 1 else ""
        value = parts[2] if len(parts) > 2 else "_"
        if not value or value == "_":
            # 一级: 返回该站分类 folder 卡列表
            cats = self._site_cats(site)
            items = []
            for cid, cname in cats:
                # 尝试获取分类封面 (黑料社/油条视频分类无封面, 留空)
                items.append(self._folder_vod(site, cid, cname))
            return {
                "list": items,
                "page": pg,
                "pagecount": pg if len(items) < PAGE_SIZE else 9999,
                "limit": PAGE_SIZE,
                "total": len(items),
            }
        # 二级: 返回该分类视频卡列表
        items, total = self._fetch_cat_videos(site, value, pg)
        vods = [self._to_vod(site, x) for x in items]
        return self._page_items(vods, pg, total)

    def _site_cats(self, site):
        if site == SITE_PX8X:
            return PX8X_CATS
        if site == SITE_HEIX8:
            return HEIX8_CATS
        if site == SITE_YT8X:
            return YT8X_CATS
        return []

    def _fetch_cat_videos(self, site, cid, pg):
        """返回 (items, total)。total 用于 pagecount。"""
        if site == SITE_PX8X:
            return self._px8x_list(cid, pg)
        if site == SITE_HEIX8:
            return self._heix8_list(cid, pg)
        if site == SITE_YT8X:
            return self._yt8x_list(cid, pg)
        return [], 0

    def _page_items(self, items, pg, total=None):
        try:
            page = max(1, int(pg))
        except (TypeError, ValueError):
            page = 1
        total = int(total) if total else len(items)
        if total <= 0:
            pagecount = page
        else:
            pagecount = max(page, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        return {
            "list": items,
            "page": page,
            "pagecount": pagecount,
            "limit": PAGE_SIZE,
            "total": total,
        }

    # ================= 通用工具 =================
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
                    import gzip as _gzip
                    raw = _gzip.decompress(raw)
                elif enc == "deflate":
                    import zlib as _zlib
                    raw = _zlib.decompress(raw)
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

    @staticmethod
    def _clean_text(t):
        t = re.sub(r'<span[^>]*>.*?</span>', '', t)
        t = re.sub(r'<[^>]+>', '', t)
        return t.strip()

    @staticmethod
    def _heix8_clean_title(t):
        """黑料社 title: '黑料社（Fkk8.Com） - 你的成人伙伴！-<分类>-<标题>' → <标题>"""
        t = t or ""
        t = re.sub(r'^黑料社（Fkk8\.Com）\s*-\s*你的成人伙伴！\s*-\s*', '', t)
        # 去掉 '<分类名>-': 分类名是已知集合之一
        for _, cname in HEIX8_CATS:
            if t.startswith(cname + "-"):
                t = t[len(cname) + 1:]
                break
        return t.strip()

    @staticmethod
    def _b64_decode(b):
        try:
            return base64.b64decode(b).decode('utf-8')
        except Exception:
            return ''

    # ---------- Px8x 站 (www.8xx6.lol) ----------
    def _px8x_html(self, path):
        return self._get_html(PX8X_HOST + path, headers={"User-Agent": UA, "Referer": PX8X_HOST + "/"})

    def _px8x_title(self, html):
        m = re.search(r"d\('([^']+)'\)", html or "")
        if m:
            return self._clean_text(self._b64_decode(m.group(1)))
        return ""

    def _px8x_list(self, cid, pg):
        html = self._px8x_html("/list/%s-%s.html" % (cid, pg))
        if not html:
            return [], 0
        items = []
        for card in self._split_thumbnail_cards(html):
            m = re.search(r'href="(/video/(\d+)\.html)"', card)
            if not m:
                continue
            vid = m.group(2)
            tm = re.search(r"d\('([^']+)'\)", card)
            title = self._px8x_title(card) if tm else self._clean_text(card)
            img = re.search(r'src="(https://[^"]+\.jpg)"', card)
            items.append({
                "id": vid,
                "name": title or vid,
                "pic": img.group(1) if img else "",
                "remarks": "",
            })
        total = 0
        m = re.search(r'/\s*(\d+)\s*</span>', html)
        if m:
            total = int(m.group(1))
        return items, total

    def _px8x_detail(self, vid):
        html = self._px8x_html("/video/%s.html" % vid)
        if not html:
            return None
        title = ""
        m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        if m:
            title = self._px8x_title(m.group(1))
        if not title:
            title = self._px8x_title(html)
        # 播放 URL
        play = ""
        m = re.search(r"hls\.loadSource\('([^']+)'\)", html)
        if m:
            play = m.group(1)
        else:
            m = re.search(r"video\.src\s*=\s*'([^']+)'", html)
            if m:
                play = m.group(1)
        # 封面: 第一个 155p upload/vod 图
        pic = ""
        m = re.search(r'<img[^>]*src="(https://155p261028\.com/upload/vod/[^"]+)"', html)
        if m:
            pic = m.group(1)
        return {
            "name": title or vid,
            "pic": pic,
            "play": play,
            "remarks": "",
        }

    def _px8x_search(self, kw, pg):
        html = self._px8x_html("/search.php?content=%s&page=%s" % (quote(kw, safe=""), pg))
        if not html:
            return []
        items = []
        for card in self._split_thumbnail_cards(html):
            m = re.search(r'href="(/video/(\d+)\.html)"', card)
            if not m:
                continue
            vid = m.group(2)
            tm = re.search(r"d\('([^']+)'\)", card)
            title = self._px8x_title(card) if tm else self._clean_text(card)
            img = re.search(r'src="(https://[^"]+\.jpg)"', card)
            items.append({
                "id": vid,
                "name": title or vid,
                "pic": img.group(1) if img else "",
                "remarks": "",
            })
        return items

    # ---------- 黑料社站 (www.heix8.cc) ----------
    def _heix8_html(self, path):
        return self._get_html(HEIX8_HOST + path, headers={"User-Agent": UA, "Referer": HEIX8_HOST + "/"})

    def _heix8_list(self, cid, pg):
        html = self._heix8_html("/video_list/%s/%s/index.html" % (cid, pg))
        if not html:
            return [], 0
        items = []
        for card in self._split_thumbnail_cards(html):
            m = re.search(r'href="/video_detail/(\d+)/(\d+)/index\.html"', card)
            if not m:
                continue
            vid, vcat = m.group(1), m.group(2)
            tm = re.search(r'<div class="[^"]*title[^"]*">(.*?)</div>', card, re.S)
            title = self._clean_text(tm.group(1)) if tm else ""
            img = re.search(r'(?:data-src|src)="(https://[^"]+\.jpg)"', card)
            remark = ""
            spans = re.findall(r'<span[^>]*>([^<]+)</span>', card)
            if spans:
                remark = spans[-1].strip()
            items.append({
                "id": vid,
                "_cat": vcat,
                "name": title or vid,
                "pic": img.group(1) if img else "",
                "remarks": remark,
            })
        total = 0
        m = re.search(r"pagesize:\s*'?(\d+)'?", html)
        if m:
            total = int(m.group(1))
        return items, total

    @staticmethod
    def _split_thumbnail_cards(html):
        """鲁棒切分 thumbnail group 卡片块 (多层 div 嵌套用 </div></div> 会提前截断)。"""
        cards = []
        start = 0
        while True:
            i = html.find('<div class="thumbnail group">', start)
            if i < 0:
                break
            # 找下一个同类 div 或结尾
            j = html.find('<div class="thumbnail group">', i + 5)
            if j < 0:
                j = len(html)
            cards.append(html[i:j])
            start = j
        return cards

    def _heix8_detail(self, vid, cat="2"):
        # 先抓 video_detail 页拿标题和 conter 链接, 再抓 video_conter 页拿 m3u8
        html = self._heix8_html("/video_detail/%s/%s/index.html" % (vid, cat))
        title = ""
        pic = ""
        conter_path = ""
        if html:
            m = re.search(r'<title>([^<]*)</title>', html)
            if m:
                title = self._heix8_clean_title(m.group(1))
            # 当前视频的 conter 链接
            m = re.search(r'href="(/video_conter/%s/(\d+)/index\.html)"' % vid, html)
            if m:
                conter_path = m.group(1)
            # 封面: 第一个 poster/cover 图
            m = re.search(r'(?:data-src|src)="(https://[^"]+\.jpg)"', html)
            if m:
                pic = m.group(1)
        play = ""
        if not conter_path:
            conter_path = "/video_conter/%s/%s/index.html" % (vid, cat)
        conter = self._heix8_html(conter_path)
        if conter:
            m = re.search(r'Play=([^&"]+)', conter)
            if m:
                play = m.group(1)
        return {
            "name": title or vid,
            "pic": pic,
            "play": play,
            "remarks": "",
        }

    def _heix8_search(self, kw, pg):
        html = self._heix8_html("/?m=video_search*%s*%s" % (quote(kw, safe=""), pg))
        if not html:
            return []
        items = []
        for card in self._split_thumbnail_cards(html):
            m = re.search(r'href="/video_detail/(\d+)/(\d+)/index\.html"', card)
            if not m:
                continue
            vid, vcat = m.group(1), m.group(2)
            tm = re.search(r'<div class="[^"]*title[^"]*">(.*?)</div>', card, re.S)
            title = self._clean_text(tm.group(1)) if tm else ""
            img = re.search(r'(?:data-src|src)="(https://[^"]+\.jpg)"', card)
            items.append({
                "id": vid,
                "_cat": vcat,
                "name": title or vid,
                "pic": img.group(1) if img else "",
                "remarks": "",
            })
        return items

    # ---------- 油条视频站 (www.yt8x1.top) AES API ----------
    def _yt_enc(self, plain):
        iv = os.urandom(16)
        ct = self._yt_aes_ctr(plain, iv)
        if ct is None:
            return None
        return {"data": base64.b64encode(ct).decode(), "iv": base64.b64encode(iv).decode()}

    def _yt_dec(self, data_b64, iv_b64):
        try:
            ct = base64.b64decode(data_b64)
            iv = base64.b64decode(iv_b64)
            plain = self._yt_aes_ctr(ct, iv)
            if plain is None:
                return ""
            return plain.decode('utf-8', 'replace')
        except Exception:
            return ""

    def _yt_aes_ctr(self, data, iv):
        """AES-128-CTR 加解密 (key=YT_KEY, nonce=iv)。双回退: Crypto → cryptography。"""
        try:
            from Crypto.Cipher import AES
            cipher = AES.new(YT_KEY, AES.MODE_CTR, nonce=b'', initial_value=iv)
            return cipher.decrypt(data)
        except Exception:
            pass
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            dec = Cipher(algorithms.AES(YT_KEY), modes.CTR(iv)).decryptor()
            return dec.update(data) + dec.finalize()
        except Exception:
            return None

    def _yt_post_api(self, path, body):
        """油条视频 AES 加密 API 调用, 返回解密后 dict"""
        net = getattr(self, 'net', None)
        url = YT8X_HOST + path
        enc = self._yt_enc(json.dumps(body).encode() if not isinstance(body, str) else body.encode())
        if enc is None:
            return {}
        payload = json.dumps(enc)
        if net is not None:
            try:
                resp = net.req(url, {"method": "POST", "postType": "json", "data": payload,
                                     "headers": {"Content-Type": "application/json", "Referer": YT8X_HOST + "/"},
                                     "timeout": 15000})
                resp = resp if isinstance(resp, dict) else {"code": 200, "content": resp, "headers": {}, "error": None}
                if resp.get("error"):
                    return {}
                rj = json.loads(resp.get("content", ""))
                if "data" in rj and "iv" in rj:
                    plain = self._yt_dec(rj["data"], rj["iv"])
                    return json.loads(plain) if plain else {}
                return rj
            except Exception:
                return {}
        # urllib 回退
        try:
            req = urllib.request.Request(url, data=payload.encode(), headers={
                "Content-Type": "application/json", "User-Agent": UA, "Referer": YT8X_HOST + "/"}, method="POST")
            with urllib.request.urlopen(req, timeout=20) as r:
                rj = json.loads(r.read().decode())
                if "data" in rj and "iv" in rj:
                    plain = self._yt_dec(rj["data"], rj["iv"])
                    return json.loads(plain) if plain else {}
                return rj
        except Exception:
            return {}

    def _yt8x_list(self, cid, pg):
        body = {"categoryId": int(cid), "sortBy": "latest", "sortOrder": "asc",
                "page": int(pg), "pageSize": 24}
        data = self._yt_post_api("/api/category/list?lang=zh_cn", body)
        if not data or data.get("code") != 1:
            return [], 0
        items = []
        for v in (data.get("data") or {}).get("list") or []:
            dur = self._fmt_duration(v.get("durationSecs"))
            items.append({
                "id": str(v.get("id") or ""),
                "name": v.get("title") or "",
                "pic": v.get("coverUrl") or "",
                "remarks": dur,
                "_created": v.get("createdAt") or "",
            })
        total = int((data.get("data") or {}).get("total") or 0)
        return items, total

    def _yt8x_search(self, kw, pg):
        body = {"keyword": kw, "page": int(pg), "pageSize": 24,
                "sortBy": "created_at", "sortOrder": "desc"}
        data = self._yt_post_api("/api/search?lang=zh_cn", body)
        if not data or data.get("code") != 1:
            return []
        items = []
        for v in (data.get("data") or {}).get("list") or []:
            items.append({
                "id": str(v.get("id") or ""),
                "name": v.get("title") or "",
                "pic": v.get("coverUrl") or "",
                "remarks": self._fmt_duration(v.get("durationSecs")),
            })
        return items

    @staticmethod
    def _fmt_duration(secs):
        try:
            secs = int(secs)
            if secs <= 0:
                return ""
            h, rem = divmod(secs, 3600)
            m, s = divmod(rem, 60)
            if h:
                return "%d:%02d:%02d" % (h, m, s)
            return "%d:%02d" % (m, s)
        except Exception:
            return ""

    def _yt8x_detail(self, vid):
        body = {"videoId": int(vid), "episodeNo": 1, "deviceId": "ae144c64bdad0a3b611bb73f35c81525"}
        data = self._yt_post_api("/api/video/detail?lang=zh_cn", body)
        if not data or data.get("code") != 1:
            return None
        d = data.get("data") or {}
        play = ""
        ep = d.get("currentEpisode") or {}
        if ep.get("playUrl"):
            play = ep["playUrl"]
            if play.startswith("/"):
                play = YT8X_HOST + play
        return {
            "name": d.get("title") or vid,
            "pic": d.get("coverUrl") or "",
            "play": play,
            "remarks": self._fmt_duration(d.get("durationSecs")),
            "category": (d.get("categories") or [{}])[0].get("name", "") if d.get("categories") else "",
            "year": d.get("year") or "",
            "area": d.get("area") or "",
        }

    # ================= 主入口调度 =================
    def _fetch_list(self, tid, pg, extend=None):
        """tid 形如 folder/<site>/<cat_id> (二级分类)"""
        parts = tid.split("/")
        if len(parts) >= 3:
            site, cid = parts[1], parts[2]
            return self._fetch_cat_videos(site, cid, pg)
        return []

    def _to_vod(self, site, item):
        item = item or {}
        vid = str(item.get("id") or "")
        if site == SITE_HEIX8:
            # 黑料社详情需要 cat, 编码进 vod_id: heix8/<cat>|<vid>
            vcat = item.get("_cat") or "2"
            return {
                "vod_id": "%s/%s|%s" % (site, vcat, vid),
                "vod_name": item.get("name") or vid,
                "vod_pic": item.get("pic") or "",
                "vod_remarks": item.get("remarks") or "",
            }
        return {
            "vod_id": "%s|%s" % (site, vid),
            "vod_name": item.get("name") or vid,
            "vod_pic": item.get("pic") or "",
            "vod_remarks": item.get("remarks") or "",
        }

    def _fetch_search(self, keyword, pg):
        # 三站并行搜索, 合并结果
        items = []
        for site, fn in ((SITE_PX8X, self._px8x_search),
                         (SITE_HEIX8, self._heix8_search),
                         (SITE_YT8X, self._yt8x_search)):
            try:
                sitems = fn(keyword, pg)
                items.extend(self._to_vod(site, x) for x in sitems)
            except Exception:
                continue
        return items

    def _parse_site_vid(self, play_id):
        """解析 play_id 为 (site, cat, vid)。黑料社格式 heix8/<cat>|<vid>"""
        if "|" not in play_id:
            return SITE_PX8X, "", play_id
        head, vid = play_id.split("|", 1)
        if "/" in head:
            site, cat = head.split("/", 1)
            return site, cat, vid
        return head, "", vid

    def _fetch_play(self, play_id):
        if not play_id:
            return ""
        site, cat, vid = self._parse_site_vid(play_id)
        if site == SITE_PX8X:
            d = self._px8x_detail(vid)
            return (d or {}).get("play") or ""
        if site == SITE_HEIX8:
            d = self._heix8_detail(vid, cat or "2")
            return (d or {}).get("play") or ""
        if site == SITE_YT8X:
            d = self._yt8x_detail(vid)
            return (d or {}).get("play") or ""
        return ""

    def _detail(self, play_id):
        if not play_id:
            return {"list": []}
        site, cat, vid = self._parse_site_vid(play_id)
        if site == SITE_PX8X:
            d = self._px8x_detail(vid)
        elif site == SITE_HEIX8:
            d = self._heix8_detail(vid, cat or "2")
        elif site == SITE_YT8X:
            d = self._yt8x_detail(vid)
        else:
            d = None
        if not d:
            return {"list": [], "msg": "未找到此影片"}
        # vod_play_url 用 play_id 作地址 (playerContent 会收到 play_id 再解析)
        play_url = "正片$%s" % play_id
        vod = {
            "vod_id": play_id,
            "vod_name": d.get("name") or vid,
            "vod_pic": d.get("pic") or "",
            "type_name": d.get("category") or "",
            "vod_year": str(d.get("year") or ""),
            "vod_area": d.get("area") or "",
            "vod_remarks": d.get("remarks") or "",
            "vod_actor": "",
            "vod_content": "",
            "vod_play_from": "正片",
            "vod_play_url": play_url,
        }
        return {"list": [vod]}

    def _page(self, items, pg):
        try:
            page = max(1, int(pg))
        except (TypeError, ValueError):
            page = 1
        total = len(items)
        return {
            "list": items,
            "page": page,
            "pagecount": 9999 if total >= PAGE_SIZE else page,
            "limit": PAGE_SIZE,
            "total": total,
        }
