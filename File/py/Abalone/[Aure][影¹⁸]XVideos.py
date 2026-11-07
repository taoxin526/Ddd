# -*- coding: utf-8 -*-
# [XVideos¹⁸  更新于:2026-11-06 16:50]
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

NAME = "XVideos"
HOSTS = ["https://www.xvideos.com"]
LIVE_HOST = "https://www.xvlivecams.com"
UA = "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 25
CACHE_TTL = 120
DEBUG = False
VOD_ID_PREFIX = ""
STYLE = {"type": "rect", "ratio": 1.33}

CATS = [
    ("素人", "/c/Amateur-65"), ("肛交", "/c/Anal-12"), ("阿拉伯", "/c/Arab-159"),
    ("亚洲", "/c/Asian_Woman-32"), ("ASMR", "/c/ASMR-229"), ("美臀", "/c/Ass-14"),
    ("大码丰满", "/c/bbw-51"), ("巨臀", "/c/Big_Ass-24"), ("大屌", "/c/Big_Cock-34"),
    ("巨乳", "/c/Big_Tits-23"), ("黑人", "/c/Black_Woman-30"), ("金发", "/c/Blonde-20"),
    ("口交", "/c/Blowjob-15"), ("深褐发", "/c/Brunette-25"), ("直播自拍", "/c/Cam_Porn-58"),
    ("内射", "/c/Creampie-40"), ("换妻/绿帽", "/c/Cuckold-237"), ("颜射", "/c/Cumshot-18"),
    ("女支配", "/c/Femdom-235"), ("拳交", "/c/Fisting-165"), ("乱伦家庭", "/c/Fucked_Up_Family-81"),
    ("群交", "/c/Gangbang-69"), ("扩肛", "/c/Gapes-167"), ("印度", "/c/Indian-89"),
    ("跨种族", "/c/Interracial-27"), ("拉美", "/c/Latina-16"), ("女同", "/c/Lesbian-26"),
    ("内衣", "/c/Lingerie-83"), ("熟女", "/c/Mature-38"), ("人妻", "/c/Milf-19"),
    ("涂油", "/c/Oiled-22"), ("红发", "/c/Redhead-31"), ("自慰", "/c/Solo_and_Masturbation-33"),
    ("潮吹", "/c/Squirting-56"), ("丝袜", "/c/Stockings-28"), ("少女", "/c/Teen-13"),
    ("同志", "/gay?fmc=1"), ("人妖", "/trans?fmc=1"),
]


TAG_CN = {
    "amateur": "素人", "anal": "肛交", "asian": "亚洲", "ass": "美臀", "bbw": "大码丰满",
    "bigass": "巨臀", "bigtits": "巨乳", "big-tits": "巨乳", "blonde": "金发", "blowjob": "口交",
    "brunette": "深褐发", "creampie": "内射", "cumshot": "颜射", "hardcore": "硬核",
    "hot": "性感", "sucking": "吸吮", "cock": "肉棒", "milf": "人妻", "mature": "熟女",
    "fingering": "手指", "fuck": "性爱", "lesbian": "女同", "latina": "拉美", "teen": "少女",
    "squirt": "潮吹", "squirting": "潮吹", "hairy": "浓毛", "pussy": "蜜穴", "licking": "舔舐",
    "stockings": "丝袜", "lingerie": "内衣", "oiled": "涂油", "redhead": "红发", "solo": "自慰",
    "masturbation": "自慰", "ebony": "黑人", "interracial": "跨种族", "gangbang": "群交",
    "threesome": "三人", "deepthroat": "深喉", "feet": "恋足", "pregnant": "孕妇",
    "japanese": "日本", "chinese": "国产", "indian": "印度", "arab": "阿拉伯",
    "casting": "试镜", "babe": "宝贝", "beauty": "美女", "natural": "自然", "pov": "第一视角",
    "close-up": "特写", "homemade": "自拍", "webcam": "直播", "cosplay": "角色扮演",
    "schoolgirl": "学生", "cheerleader": "啦啦队", "massage": "按摩", "orgasm": "高潮",
    "riding": "骑乘", "doggy": "后入", "missionary": "传教士", "cum-in-mouth": "口爆",
    "cumshot-compilation": "颜射合集", "compilation": "合集", "hd": "高清", "4k": "4K",
}

LIVE_TAGS = [
    ("ebony", "黑人"), ("squirt", "潮吹"), ("bigboobs", "巨乳"), ("mature", "熟女"),
    ("milf", "人妻"), ("anal", "肛交"), ("asian", "亚洲"), ("latina", "拉美"),
    ("hairy", "浓毛"), ("teen", "少女"), ("bbw", "大码丰满"), ("fuckmachine", "炮机"),
    ("bigass", "巨臀"), ("skinny", "苗条"), ("deepthroat", "深喉"),
    ("feet", "恋足"), ("young", "年轻"), ("smalltits", "小胸"), ("pregnant", "孕妇"),
    ("pantyhose", "连裤袜"), ("british", "英国"), ("german", "德国"),
    ("bigcock", "大屌"), ("pinay", "菲律宾"), ("goth", "哥特"), ("curvy", "丰满"),
    ("blonde", "金发"), ("threesome", "三人"), ("lesbian", "女同"), ("redhead", "红发"),
]


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
            pc = getattr(self, "_cur_pagecount", 9999)
            if not items:
                pc = pg
            return {
                "list": [self._vod(x) for x in items],
                "page": pg,
                "pagecount": pc,
                "limit": PAGE_SIZE,
                "total": 999999,
            }

        if tid.startswith("folder/"):
            parts = tid.split("/", 2)
            if len(parts) == 3:
                f_type, f_value = parts[1], unquote(parts[2])
                if not f_value or f_value == "_":
                    items = self._fetch_folder_entries(f_type)
                else:
                    items = [self._vod(x) for x in self._fetch_folder(f_type, f_value, pg)]
                return {
                    "list": items,
                    "page": pg,
                    "pagecount": pg if len(items) < PAGE_SIZE else 9999,
                    "limit": PAGE_SIZE,
                    "total": 999999,
                }

        items = self._fetch_list(tid, pg, extend)
        pc = getattr(self, "_cur_pagecount", 9999)
        if pg > pc:
            pc = pg
        if items and len(items) < PAGE_SIZE:
            pc = pg
            self._last_good_pg = pg
        elif not items and pg > 1:
            pc = min(pc, getattr(self, "_last_good_pg", pg - 1))
        else:
            self._last_good_pg = pg
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pc,
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
        if vid.startswith("live/"):
            return self._detail_live(vid)
        data = self._fetch_detail(vid)
        if not data:
            return {"list": [], "msg": "未找到此影片"}
        eps = data.get("episodes") or []
        if eps:
            lines = []
            for i, ep in enumerate(eps, 1):
                title = self._safe_label(ep.get("name") or f"第{i}集")
                url = ep.get("url") or ep.get("play_url") or ""
                if url:
                    lines.append(f"{title}${url}")
            play_url = "#".join(lines)
            play_from = data.get("source_name") or data.get("play_from") or "正片"
        else:
            url = data.get("play_ref") or vid
            play_url = f"正片${url}"
            play_from = data.get("source_name") or data.get("play_from") or "正片"
        vod = {
            "vod_id": self._vod_id(vid),
            "vod_name": data.get("name") or vid,
            "vod_pic": self._pic(data),
            "type_name": self._cat_cn(data.get("category") or ""),
            "vod_year": str(data.get("year") or ""),
            "vod_area": data.get("area") or "",
            "vod_remarks": self._rem(data.get("duration") or data.get("remarks")),
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
        pc = getattr(self, "_cur_pagecount", 9999)
        if not items:
            pc = pg
        elif pg > pc:
            pc = pg
        else:
            self._last_good_pg = pg
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pc,
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
            "header": self._string_map({"User-Agent": UA, "Referer": self.host + "/"}),
        }
        return result

    def liveContent(self, url):
        return "[]"


    def _safe_label(self, text):
        return str(text or "").replace("$", "＄").replace("#", "＃").strip()

    def _vod_id(self, site_id):
        return f"{VOD_ID_PREFIX}{site_id}" if VOD_ID_PREFIX else str(site_id)

    def _clickable(self, kind, name):
        if not name:
            return ""
        ident = f"{kind}/{quote(name, safe='')}"
        payload = json.dumps({"id": ident, "name": name}, ensure_ascii=False, separators=(",", ":"))
        return f"[a=cr:{payload}/]{name}[/a]"

    def _resp_dict(self, resp):
        if isinstance(resp, dict):
            return resp
        if isinstance(resp, str):
            return {"code": 200, "content": resp, "headers": {}, "error": None}
        if isinstance(resp, (bytes, bytearray)):
            return {"code": 200, "content": resp, "headers": {}, "error": None}
        return {"code": 0, "content": "", "headers": {}, "error": str(resp)}

    def _req(self, url, **kw):
        net = getattr(self, 'net', None)
        if net is not None:
            try:
                opts = {"timeout": kw.get("timeout", 15000)}
                for k in ("params", "headers", "method", "postType", "data", "body", "buffer", "redirect", "cookie"):
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

    def _pic(self, item):
        for k in ("img_y", "cover", "pic", "img", "thumb", "vod_pic"):
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

    def _cache_get(self, key, ttl=CACHE_TTL):
        with self._lock:
            v = self._cache.get(key)
            if v is not None and time.time() - self._cache_time.get(key, 0) < ttl:
                return v
        return None

    def _cache_set(self, key, val):
        with self._lock:
            self._cache[key] = val
            self._cache_time[key] = time.time()


    def _classes(self):
        arr = [{"type_id": "cat/" + c[1].strip("/"), "type_name": c[0]} for c in CATS]
        arr.append({"type_id": "folder/live/_", "type_name": "🔴 直播"})
        return arr

    def _home_items(self):
        html = self._get_html(self.host + "/")
        if not html:
            return []
        return self._parse_cards(html, limit=40)

    def _parse_cards(self, html, limit=None):
        import html as _html
        items = []
        seen = set()
        parts = re.split(r'<div class="thumb-inside">', html)
        blocks = parts[1:] if len(parts) > 1 else []
        for block in blocks:
            href_m = re.search(r'href="(/video\.[^"]+)"', block)
            if not href_m:
                continue
            href = href_m.group(1)
            parts_h = href.split("/")
            eid = ""
            slug = ""
            for i, p in enumerate(parts_h):
                if p.startswith("video."):
                    eid = p[6:]
                    rest = parts_h[i + 1:]
                    if len(rest) >= 3 and rest[1] == "0":
                        slug = "/".join(rest[2:])
                    else:
                        slug = "/".join(rest)
                    break
            if not eid:
                continue
            vid = f"{eid}|{slug}"
            if vid in seen:
                continue
            seen.add(vid)
            title_m = re.search(r'<a[^>]*title="([^"]*)"[^>]*>', block)
            title = _html.unescape(title_m.group(1)) if title_m else ""
            dur_m = re.search(r'<span class="duration">([^<]+)</span>', block)
            duration = dur_m.group(1) if dur_m else ""
            pic_m = re.search(r'data-src="([^"]+)"', block)
            pic = pic_m.group(1) if pic_m else ""
            if not pic:
                pic_m = re.search(r'<img[^>]+src="([^"]+)"', block)
                pic = pic_m.group(1) if pic_m else ""
            hd = re.search(r'video-hd-mark">([^<]+)</span>', block)
            hdmark = hd.group(1) if hd else ""
            uploader_m = re.search(r'<span class="name">([^<]+)</span>', block)
            uploader = uploader_m.group(1) if uploader_m else ""
            views_m = re.search(r'>\s*([\d.,]+[kKmM]?)\s*Views', block)
            views = views_m.group(1) if views_m else ""
            remark = hdmark or self._rem(duration)
            items.append({
                "id": vid,
                "eid": eid,
                "slug": slug,
                "name": title or slug,
                "pic": pic,
                "duration": duration,
                "hd": hdmark,
                "uploader": uploader,
                "views": views,
                "remarks": remark,
                "category": self._card_category(block),
            })
            if limit and len(items) >= limit:
                break
        return items

    def _card_category(self, block):
        cat_m = re.search(r'href="(/c/[^"]+)"', block)
        if cat_m:
            return cat_m.group(1)
        return ""

    def _fetch_list(self, tid, pg, extend):
        if tid.startswith("cat/"):
            path = tid[4:]
        else:
            path = tid
        if pg > 1:
            base = path.split("?")[0]
            url = self.host + "/" + base.rstrip("/") + "/" + str(pg)
        else:
            url = self.host + "/" + path
        html = self._get_html(url)
        if not html:
            self._cur_pagecount = 1
            return []
        items = self._parse_cards(html)
        self._cur_pagecount = self._extract_pagecount(html, path)
        return items

    def _extract_pagecount(self, html, path):
        nums = []
        for m in re.finditer(r'/([^/"]+)/(\d+)(?:"[^>]*>\s*\d+\s*<|["\s])', html):
            pass
        slug = path.split("?")[0].strip("/")
        pat = re.escape("/" + slug + "/") + r'(\d+)'
        for m in re.finditer(pat, html):
            n = int(m.group(1))
            if n > 0:
                nums.append(n)
        if nums:
            return max(nums)
        for m in re.finditer(r'href="[^"]*/(\d+)"[^>]*>\s*(\d+)\s*<', html):
            n = int(m.group(1))
            if n > 0:
                nums.append(n)
        return max(nums) if nums else 9999

    def _fetch_search(self, keyword, pg):
        url = self.host + "/?k=" + quote(keyword, safe="")
        if pg > 1:
            url += "&p=" + str(pg)
        html = self._get_html(url)
        if not html:
            self._cur_pagecount = 1
            return []
        items = self._parse_cards(html)
        self._cur_pagecount = self._extract_search_pagecount(html)
        return items

    def _extract_search_pagecount(self, html):
        nums = []
        for m in re.finditer(r'\?k=[^"&\s]*&amp;p=(\d+)', html):
            n = int(m.group(1))
            if n > 0:
                nums.append(n)
        if not nums:
            for m in re.finditer(r'[?&]p=(\d+)', html):
                n = int(m.group(1))
                if n > 0:
                    nums.append(n)
        return max(nums) if nums else 9999

    def _fetch_detail(self, vid):
        if "|" in vid:
            eid, slug = vid.split("|", 1)
        else:
            eid, slug = vid, ""
        if slug:
            url = self.host + "/video." + quote(eid, safe="") + "/" + quote(slug, safe="")
        else:
            url = self.host + "/video." + quote(eid, safe="") + "/"
        html = self._get_html(url)
        if not html:
            return {}
        import html as _html
        title_m = re.search(r'og:title" content="([^"]+)"', html)
        name = _html.unescape(title_m.group(1)) if title_m else ""
        pic_m = re.search(r'og:image" content="([^"]+)"', html)
        pic = pic_m.group(1) if pic_m else ""
        dur_m = re.search(r'<span class="duration">([^<]+)</span>', html)
        duration = dur_m.group(1) if dur_m else ""
        views_m = re.search(r'([\d.,]+[kKmM]?)\s*Views', html)
        views = views_m.group(1) if views_m else ""
        hls = self._extract_hls(html)
        tags = []
        for m in re.finditer(r'href="(/tags/[^"]+)"', html):
            t = m.group(1).replace("/tags/", "").replace("/", "")
            if t and t not in tags:
                tags.append(t)
        meta_i = html.find('video-metadata')
        meta = html[meta_i:meta_i + 4000] if meta_i > 0 else ""
        actors = []
        for m in re.finditer(r'<li class="model"><a href="/models/[^"]*"[^>]*>(.*?)</a>', meta, re.S):
            an = re.sub(r'<[^>]+>', '', m.group(1))
            an = re.sub(r'[\d.,]+[kKmM]?$', '', an).strip()
            if an and an not in actors:
                actors.append(an)
        uploader = ""
        um = re.search(r'class="main uploader-tag[^"]*"[^>]*>(.*?)</a>', meta, re.S)
        if um:
            uploader = re.sub(r'<[^>]+>', '', um.group(1)).strip()
            uploader = re.sub(r'[\d.,]+[kKmM]?$', '', uploader).strip()
        desc_m = re.search(r'<p class="video-text[^"]*"[^>]*>(.*?)</p>', html, re.S)
        desc = ""
        if desc_m:
            desc = re.sub(r'<[^>]+>', '', desc_m.group(1)).strip()
        return {
            "name": name or eid,
            "url": hls,
            "play_url": hls,
            "play_ref": vid,
            "pic": pic,
            "duration": duration,
            "remarks": self._rem(duration) or views,
            "category": uploader,
            "description": desc or "标签：" + self._tag_cn(tags),
            "actors": actors,
        }

    def _extract_hls(self, html):
        if not html:
            return ""
        m = re.search(r'(https://hls-cdn[^"\']+?\.m3u8[^"\']*)', html)
        if m:
            return m.group(1)
        m = re.search(r'(https://[^"\']+\.m3u8[^"\']*)', html)
        if m:
            return m.group(1)
        return ""

    def _fetch_play(self, play_id):
        if play_id.startswith("live/"):
            return self._fetch_play_live(play_id)
        if play_id.startswith("http") and "origin." in play_id and "mmcdn.com" in play_id:
            um = re.search(r'/origin\.([^.]+)\.', play_id)
            if um:
                return self._fetch_play_live("live/" + um.group(1))
        if play_id.startswith("http") and (".m3u8" in play_id or ".mp4" in play_id):
            return play_id
        if "|" in play_id:
            eid, slug = play_id.split("|", 1)
        else:
            eid, slug = play_id, ""
        if slug:
            url = self.host + "/video." + quote(eid, safe="") + "/" + quote(slug, safe="")
        else:
            url = self.host + "/video." + quote(eid, safe="") + "/"
        html = self._get_html(url)
        if not html:
            return ""
        return self._extract_hls(html)


    def _fetch_folder_entries(self, type_):
        cards = []
        for tag, cn in LIVE_TAGS:
            cards.append(self._folder_vod("live", tag, cn))
        return cards

    def _folder_vod(self, type_, value, name, count=None):
        card = {
            "vod_id": f"folder/{type_}/{quote(value, safe='')}",
            "vod_name": str(name or value or ""),
            "vod_pic": "",
            "vod_remarks": ("%s个房间" % count) if count else "",
            "vod_tag": "folder",
        }
        return card

    def _fetch_folder(self, type_, value, pg):
        return self._fetch_live_rooms(value, pg)

    def _fetch_live_rooms(self, tag, pg):
        offset = (pg - 1) * 41
        params = f"hashtags={quote(tag, safe='')}&limit=41&offset={offset}"
        url = LIVE_HOST + "/api/ts/roomlist/room-list/?" + params
        data = self._get_json(url)
        rooms = data.get("rooms") or []
        items = []
        for r in rooms:
            username = r.get("username") or ""
            if not username:
                continue
            subject = self._clean_subject(r.get("subject") or r.get("room_subject") or "")
            pic = r.get("img") or ""
            users = r.get("num_users") or 0
            tags = r.get("tags") or []
            items.append({
                "id": "live/" + username,
                "username": username,
                "name": subject or username,
                "pic": pic,
                "remarks": f"{users}人" if users else "",
                "category": "#" + tag,
                "description": subject,
                "tags": tags,
            })
        return items

    def _clean_subject(self, subject):
        import html as _html
        s = _html.unescape(subject or "")
        s = re.sub(r'<[^>]+>', ' ', s)
        s = re.sub(r'#\w+', '', s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s[:80]

    def _detail_live(self, vid):
        username = vid.split("live/", 1)[-1]
        html = self._get_html(LIVE_HOST + "/" + quote(username, safe="") + "/")
        if not html:
            return {"list": [], "msg": "未找到直播间"}
        pic_m = re.search(r'og:image" content="([^"]+)"', html)
        pic = pic_m.group(1) if pic_m else ""
        desc_m = re.search(r'og:description" content="([^"]+)"', html)
        desc = ""
        if desc_m:
            raw = desc_m.group(1)
            raw = re.sub(r"^[^.!?]*?live sex show\.[^!]*?!\s*", "", raw)
            desc = self._clean_subject(raw)
        title_m = re.search(r'og:title" content="([^"]+)"', html)
        name = desc or username
        if not name:
            name = (title_m.group(1) if title_m else username).split(" camgirl")[0]
        hls = self._extract_live_hls(html)
        vod = {
            "vod_id": self._vod_id(vid),
            "vod_name": name or username,
            "vod_pic": pic,
            "type_name": "直播",
            "vod_remarks": "直播",
            "vod_actor": "",
            "vod_content": desc or "",
            "vod_play_from": "直播",
            "vod_play_url": f"正片${hls}",
        }
        return {"list": [vod]}

    def _extract_live_hls(self, html):
        if not html:
            return ""
        m = re.search(r'hls_source\\?u0022:\s*\\?u0022(.*?)\\?u0022', html, re.S)
        if m:
            s = m.group(1).replace('\\u002D', '-').replace('\\u003D', '=').replace('\\u0026', '&')
            return s
        m = re.search(r'(https://edge\d+[^"\']+?llhls\.m3u8\?token=[^"\']+)', html)
        if m:
            return m.group(1).replace('\\u002D', '-').replace('\\u003D', '=').replace('\\u0026', '&')
        return ""

    def _fetch_play_live(self, play_id):
        username = play_id.split("live/", 1)[-1]
        html = self._get_html(LIVE_HOST + "/" + quote(username, safe="") + "/")
        if not html:
            return ""
        return self._extract_live_hls(html)

    def _tag_cn(self, tags):
        out = []
        for t in tags or []:
            k = str(t).strip().lower()
            out.append(TAG_CN.get(k, k))
        return "、".join(out)

    def _cat_cn(self, path):
        for cn, p in CATS:
            if p == path:
                return cn
        return ""

    def _rem(self, text):
        if not text:
            return ""
        s = str(text).strip()
        m = re.match(r'^(\d+)\s*h(?:our)?s?(?:\s*(\d+)\s*min)?$', s, re.I)
        if m:
            h = m.group(1)
            mi = m.group(2)
            return (h + "小时" + (mi + "分" if mi else "")) if mi else (h + "小时")
        m = re.match(r'^(\d+)\s*min(?:ute)?s?$', s, re.I)
        if m:
            return m.group(1) + "分钟"
        m = re.match(r'^(\d+)\s*sec(?:ond)?s?$', s, re.I)
        if m:
            return m.group(1) + "秒"
        return s

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("id") or item.get("vod_id") or "")
        return {
            "vod_id": self._vod_id(vid),
            "vod_name": item.get("name") or item.get("title") or vid,
            "vod_pic": self._pic(item),
            "vod_remarks": item.get("remarks") or item.get("update_label") or item.get("duration") or "",
        }
