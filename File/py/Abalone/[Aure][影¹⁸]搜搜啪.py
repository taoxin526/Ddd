# -*- coding: utf-8 -*-
# [搜搜啪¹⁸  更新于:2026-11-07 01:20]
import json
import re
import time
import threading
import gzip
import zlib
import urllib.request
import urllib.parse
from urllib.parse import quote, unquote, urlparse, parse_qs

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        def proxy(self, params):
            return [404, "text/plain", ""]
        def localProxy(self, params):
            return [404, "text/plain", ""]

NAME = "搜搜啪"
HOSTS = ["https://www.sosopa.cc"]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PAGE_SIZE = 16
CACHE_TTL = 60
DEBUG = False
VOD_ID_PREFIX = ""

GROUPS = {
    "zwcm": [45, 46, 47, 48, 72, 73, 74, 2, 3, 15, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29],
    "mxwh": [54, 55, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95],
    "gc": [58, 59, 60, 61, 16, 18, 19],
    "rbav": [49, 50, 51, 52, 53, 70, 78],
    "dm": [56, 57],
    "omav": [62, 63, 64],
    "xzkw": [65, 66, 67, 68, 69, 71],
}
CATS = {
    45: "传媒-麻豆传媒", 46: "传媒-精东影业", 47: "传媒-蜜桃传媒", 48: "传媒-果冻传媒",
    72: "传媒-糖心传媒", 73: "传媒-乐播传媒", 74: "传媒-葫芦影业", 2: "传媒-星空无限传媒",
    3: "传媒-SA国际传媒", 15: "传媒-情欲国潮", 20: "传媒-性视界传媒", 21: "传媒-天美传媒",
    22: "传媒-皇家华人", 23: "传媒-扣扣传媒", 24: "传媒-91传媒", 25: "传媒-杏吧传媒",
    26: "传媒-起点传媒", 27: "传媒-CCAV成人头条", 28: "传媒-渡边传媒", 29: "传媒-辣椒原创",
    54: "玩偶姐姐", 55: "台湾粉红兔", 79: "刘玥", 80: "小二先生", 81: "白菜妹妹",
    82: "地雷系", 83: "唐伯虎", 84: "鸡教练", 85: "粉色情人", 86: "冉冉学姐",
    87: "黑椒盖饭", 88: "水冰月", 89: "捅主任", 90: "御梦子", 91: "小欣奈",
    92: "桥本香菜", 93: "柚子猫", 94: "台北娜娜", 95: "饼干姐姐",
    58: "国产-网红", 59: "国产-户外", 60: "国产-吃瓜", 61: "国产-台湾JVID",
    16: "国产-自拍", 18: "国产-探花", 19: "国产-主播",
    49: "日本-中文字幕", 50: "日本-无码流出", 51: "日本-高清有码", 52: "日本-东京热",
    53: "日本-一本道", 70: "AV解说", 78: "日本-素人",
    56: "动漫-黄漫", 57: "动漫-里番中字",
    62: "欧美-高清无码", 63: "欧美-高清有码", 64: "欧美-中文字幕",
    65: "恐怖色情", 66: "重口味", 67: "小众女同", 68: "TS人妖", 69: "SM虐待", 71: "AI换脸",
    77: "韩国主播",
}

class Spider(BaseSpider):

    def __init__(self):
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self._cache = {}
        self._cache_time = {}
        self._lock = threading.Lock()
        self._pc_cache = {}
        self._pc_time = {}
        self._cat_cache = None
        self._cat_time = 0

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
            self.host = site

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

    def _req(self, url, **kw):
        net = getattr(self, "net", None)
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
                if kw.get("buffer") == 3:
                    return {"code": code, "content": raw, "headers": dict(resp.headers), "error": None}
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

    def _get_bytes(self, url, **kw):
        resp = self._req(url, buffer=3, **kw)
        if resp.get("error"):
            return None
        code = resp.get("code") or 0
        if not 200 <= code < 300:
            return None
        content = resp.get("content")
        if isinstance(content, str):
            return content.encode("utf-8", "replace")
        if isinstance(content, (bytes, bytearray)):
            return bytes(content)
        return None

    def _fix(self, u):
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return self.host.rstrip("/") + u
        return u

    def _list_url(self, path, pg):
        if pg <= 1:
            return self.host + path + ".html"
        return self.host + path + "/page/%d.html" % pg

    def _classes(self):
        now = time.time()
        if self._cat_cache and now - self._cat_time < CACHE_TTL:
            return self._cat_cache
        arr = []
        arr.append({"type_id": "recent", "type_name": "最近更新"})
        arr.append({"type_id": "77", "type_name": "韩国主播"})
        arr.append({"type_id": "group/zwcm", "type_name": "🗂️ 中文传媒"})
        arr.append({"type_id": "group/mxwh", "type_name": "🗂️ 明星网黄"})
        arr.append({"type_id": "group/gc", "type_name": "🗂️ 国产"})
        arr.append({"type_id": "group/rbav", "type_name": "🗂️ 日本AV"})
        arr.append({"type_id": "group/dm", "type_name": "🗂️ 动漫"})
        arr.append({"type_id": "group/omav", "type_name": "🗂️ 欧美AV"})
        arr.append({"type_id": "group/xzkw", "type_name": "🗂️ 小众口味"})
        self._cat_cache = arr
        self._cat_time = now
        return arr

    def homeContent(self, filter):
        result = {"class": self._classes()}
        result["list"] = [self._to_vod(x) for x in self._home_items()]
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        extend = extend or {}
        if tid.startswith("actor/") or tid.startswith("director/"):
            name = unquote(tid.split("/", 1)[1])
            items = self._fetch_search(name, pg)
            return self._page(items, pg, self._has_more(name, pg))
        if tid.startswith("tag/"):
            name = unquote(tid.replace("tag/", "", 1))
            items = self._fetch_search(name, pg)
            return self._page(items, pg, self._has_more(name, pg))
        if tid.startswith("group/"):
            g = tid.split("/", 1)[1]
            items = self._fetch_group_entries(g)
            return {"list": items, "page": pg, "pagecount": pg, "limit": PAGE_SIZE, "total": len(items)}
        items = self._fetch_list(tid, pg, extend)
        pc = self._real_pc(tid)
        return {
            "list": [self._to_vod(x) for x in items],
            "page": pg,
            "pagecount": pc,
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def _fetch_group_entries(self, g):
        cats = GROUPS.get(g) or []
        out = []
        for tid in cats:
            nm = CATS.get(tid) or str(tid)
            out.append({
                "vod_id": str(tid),
                "vod_name": nm,
                "vod_pic": "",
                "vod_remarks": "",
                "vod_tag": "folder",
            })
        return out

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
        url = data.get("url") or ""
        play_from = "正片"
        play_url = "正片$%s" % vid
        vod = {
            "vod_id": self._vod_id(vid),
            "vod_name": data.get("name") or vid,
            "vod_pic": self._pic_url(data.get("pic") or ""),
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
        pc = self._real_pc("search:" + str(key or "").strip())
        return {
            "list": [self._to_vod(x) for x in items],
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
            "format": "application/x-mpegURL",
        }
        return result

    def _home_items(self):
        html = self._get_html(self.host + "/")
        if not html:
            return []
        items = self._parse_cards(html)
        seen = set()
        out = []
        for it in items:
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            out.append(it)
        return out

    def _fetch_list(self, tid, pg, extend):
        if tid == "recent":
            html = self._get_html(self._list_url("/index.php/label/rank/by/time", pg))
        else:
            html = self._get_html(self._list_url("/index.php/vod/type/id/%s" % tid, pg))
        if not html:
            return []
        return self._parse_cards(html)

    def _fetch_search(self, keyword, pg):
        kw = quote(str(keyword), safe="")
        if pg <= 1:
            url = self.host + "/index.php/vod/search.html?wd=" + kw
        else:
            url = self.host + "/index.php/vod/search/page/%d/wd/%s.html" % (pg, kw)
        html = self._get_html(url)
        if not html:
            return []
        return self._parse_cards(html)

    def _fetch_detail(self, vid):
        url = self.host + "/index.php/vod/play/id/%s/sid/1/nid/1.html" % vid
        html = self._get_html(url)
        if not html:
            return None
        d = self._player_data(html)
        if not d:
            return None
        vd = d.get("vod_data") or {}
        name = vd.get("vod_name") or ""
        actors = [a for a in (vd.get("vod_actor") or "").split(",") if a.strip()]
        director = (vd.get("vod_director") or "").strip()
        tags = [t.strip() for t in (vd.get("vod_class") or "").split(",") if t.strip()]
        date = self._extract_date(html)
        remarks = date or ""
        desc_parts = []
        if tags:
            desc_parts.append("标签：" + "、".join(self._clickable("tag", t) for t in tags))
        desc = "\n".join(desc_parts)
        year = ""
        m = re.search(r"(\d{4})", date)
        if m:
            year = m.group(1)
        return {
            "name": name,
            "pic": d.get("poster") or "",
            "url": d.get("url") or "",
            "category": tags[-1] if tags else "",
            "year": year,
            "area": "",
            "remarks": remarks,
            "director": director,
            "actors": actors,
            "description": desc,
        }

    def _fetch_play(self, play_id):
        if play_id.startswith("http"):
            return play_id
        data = self._fetch_detail(play_id)
        if data and data.get("url"):
            return data["url"]
        return ""

    def _parse_cards(self, html):
        items = []
        blocks = re.split(r'<div class="thumbnail group">', html)
        for blk in blocks[1:]:
            m = re.search(r'/index\.php/vod/play/id/(\d+)/sid/1/nid/1\.html', blk)
            if not m:
                continue
            vid = m.group(1)
            pic = ""
            m2 = re.search(r'data-src="([^"]+)"', blk)
            if m2:
                pic = m2.group(1)
            title = ""
            m3 = re.search(r'<a class="[^"]*"[^>]*href="/index\.php/vod/play/id/%s/[^"]*"[^>]*>([^<]+)</a>' % vid, blk)
            if m3:
                title = m3.group(1).strip()
            if not title:
                m3b = re.search(r'<div class="my-2[^"]*"[^>]*>.*?<a[^>]*>([^<]+)</a>', blk, re.S)
                if m3b:
                    title = m3b.group(1).strip()
            remarks = ""
            m4 = re.search(r'<span class="absolute bottom-1[^"]*"[^>]*>([^<]+)</span>', blk)
            if m4:
                remarks = m4.group(1).strip()
            items.append({"id": vid, "name": title, "pic": pic, "remarks": remarks})
        return items

    def _player_data(self, html):
        i = html.find("player_aaaa")
        if i < 0:
            return {}
        j = html.find("{", i)
        if j < 0:
            return {}
        depth = 0
        end = 0
        for k in range(j, min(j + 20000, len(html))):
            c = html[k]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = k + 1
                    break
        if end <= j:
            return {}
        try:
            return json.loads(html[j:end])
        except Exception:
            return {}

    def _extract_date(self, html):
        m = re.search(r'<span>日期:</span>\s*<span[^>]*>([^<]+)</span>', html)
        if m:
            return m.group(1).strip()
        return ""

    def _real_pc(self, key):
        now = time.time()
        hit = self._pc_cache.get(key)
        if hit and now - self._pc_time.get(key, 0) < CACHE_TTL:
            return hit
        if key == "recent":
            html = self._get_html(self.host + "/index.php/label/rank/by/time.html")
        elif key.startswith("search:"):
            kw = quote(key[7:], safe="")
            html = self._get_html(self.host + "/index.php/vod/search.html?wd=" + kw)
        else:
            html = self._get_html(self.host + "/index.php/vod/type/id/%s.html" % key)
        pc = 1
        if html:
            nums = [int(x) for x in re.findall(r'/page/(\d+)', html)]
            if nums:
                pc = max(nums)
        self._pc_cache[key] = pc
        self._pc_time[key] = now
        return pc

    def _has_more(self, key, pg):
        pc = self._real_pc("search:" + key)
        return pg < pc

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

    def _to_vod(self, item):
        item = item or {}
        vid = str(item.get("id") or item.get("vod_id") or "")
        return {
            "vod_id": self._vod_id(vid),
            "vod_name": item.get("name") or item.get("title") or vid,
            "vod_pic": self._pic_url(item.get("pic") or item.get("vod_pic") or ""),
            "vod_remarks": item.get("remarks") or item.get("duration") or "",
        }

    def _vod_id(self, vid):
        return str(vid)

    def _clickable(self, kind, name):
        if not name:
            return ""
        ident = "%s/%s" % (kind, quote(name, safe=""))
        payload = json.dumps({"id": ident, "name": name}, ensure_ascii=False, separators=(",", ":"))
        return "[a=cr:%s/]%s[/a]" % (payload, name)

    def _string_map(self, value):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            return {}
        return {str(k): str(v) for k, v in value.items() if v is not None}

    @staticmethod
    def _e64(s):
        import base64
        return urllib.parse.quote(base64.b64encode(s.encode("utf-8")).decode("ascii"), safe="")

    def _d64(self, s):
        import base64
        try:
            return base64.b64decode(s).decode("utf-8", "replace")
        except Exception:
            return s

    def _pic_url(self, u):
        u = self._fix(u)
        if not u:
            return ""
        enc = self._e64(u)
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
                p = self.proxyUrl({"type": "pic", "url": self._e64(u)})
                if p:
                    return p
            except Exception:
                pass
        return u

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
                real = unquote(str(real))
            except Exception:
                pass
            try:
                real = self._d64(real)
            except Exception:
                pass
            raw = self._get_bytes(real)
            if not raw:
                return [404, "text/plain", ""]
            img = self._pic_decrypt(raw)
            return [200, self._mime(img), self._img_stream(img), {}]
        return [404, "text/plain", ""]

    def _pic_decrypt(self, raw):
        return raw

    def _mime(self, raw):
        if raw[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if raw[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if raw[:6] in (b"GIF87a", b"GIF89a"):
            return "image/gif"
        if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
            return "image/webp"
        return "image/jpeg"

    localProxy = proxy
