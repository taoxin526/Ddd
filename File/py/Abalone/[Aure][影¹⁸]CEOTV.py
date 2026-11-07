# coding=utf-8
import json
import re
import time
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

NAME = "CEOTV"
HOSTS = ["https://ceotv1108.xyz", "https://www.ceotv125.sbs"]
UA = "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 20

CATS = [
    ("1", "国产"), ("2", "日韩"), ("3", "综合"), ("4", "日本有码"), ("5", "日本无码"),
    ("6", "欧美无码"), ("7", "强奸乱伦"), ("8", "制服诱惑"), ("9", "国产主播"), ("10", "激情动漫"),
    ("11", "明星换脸"), ("12", "抖音视频"), ("13", "女优明星"), ("14", "网曝黑料"), ("15", "伦理三级"),
    ("16", "AV解说"), ("17", "SM调教"), ("18", "人妖系列"),
]


class Spider(BaseSpider):

    def __init__(self):
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self._cache = {}

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
            return
        site = (cfg.get("site") or cfg.get("url") or "").strip().rstrip("/")
        if site:
            self.hosts = [site] + [h for h in self.hosts if h != site]
            self.host = self.hosts[0]
        self.options = cfg

    def getDependence(self):
        return []

    def destroy(self):
        self._cache = {}
        self.options = {}

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", str(url)))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {"msg": "不支持此操作"}

    def homeContent(self, filter):
        result = {"class": self._classes()}
        result["list"] = [self._vod(x) for x in self._home_items()]
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        extend = extend or {}
        if tid.startswith("actor/") or tid.startswith("director/") or tid.startswith("tag/"):
            name = unquote(tid.split("/", 1)[1])
            items, pc = self._fetch_search(name, pg)
            return {
                "list": [self._vod(x) for x in items],
                "page": pg,
                "pagecount": pc if pc > pg else pg,
                "limit": PAGE_SIZE,
                "total": 999999,
            }
        items, pc = self._fetch_list(tid, pg, extend)
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pc if pc > pg else pg,
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
        play_url = data.get("url") or ""
        vod = {
            "vod_id": str(vid),
            "vod_name": data.get("name") or vid,
            "vod_pic": data.get("pic") or "",
            "type_name": data.get("category") or "",
            "vod_year": "",
            "vod_area": "",
            "vod_remarks": "",
            "vod_director": "",
            "vod_actor": "",
            "vod_content": data.get("description") or "",
            "vod_play_from": "正片",
            "vod_play_url": ("正片$" + play_url) if play_url else "",
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        items, pc = self._fetch_search(str(key or "").strip(), pg)
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pc if pc > pg else pg,
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def playerContent(self, flag, id, vipFlags):
        url = self._fetch_play(str(id or ""))
        if not url:
            return {"parse": 0, "msg": "无法获取播放地址"}
        return {"parse": 0, "jx": 0, "url": url, "header": {"User-Agent": UA}}

    def liveContent(self, url):
        return "[]"

    def proxy(self, params):
        return [404, "text/plain", ""]

    localProxy = proxy

    def _classes(self):
        return [{"type_id": tid, "type_name": nm} for tid, nm in CATS]

    def _home_items(self):
        html = self._get_html(self.host + "/")
        if not html:
            return []
        items = self._parse_cards(html)
        return items[:PAGE_SIZE]

    def _fetch_list(self, tid, pg, extend):
        if pg <= 1:
            url = self.host + "/index.php/vod/type/id/%s.html" % tid
        else:
            url = self.host + "/index.php/vod/type/id/%s/page/%s.html" % (tid, pg)
        html = self._get_html(url)
        if not html:
            return [], max(pg, 1)
        items = self._parse_cards(html)
        pc = self._pagecount_from_count(html)
        if pc < pg:
            pc = pg
        return items, pc

    def _fetch_search(self, keyword, pg):
        if not keyword:
            return [], max(pg, 1)
        kw = quote(keyword, safe="")
        if pg <= 1:
            url = self.host + "/index.php/vod/search.html?wd=" + kw
        else:
            url = self.host + "/index.php/vod/search/page/%s/wd/%s.html" % (pg, kw)
        html = self._get_html(url)
        if not html:
            return [], max(pg, 1)
        items = self._parse_cards(html)
        pc = self._pagecount_from_pager(html)
        if pc < pg:
            pc = pg
        return items, pc

    def _fetch_detail(self, vid):
        url = self._play_url(vid)
        html = self._get_html(url)
        if not html:
            return {}
        d = self._extract_player(html)
        play = d.get("url") or ""
        vd = d.get("vod_data") or {}
        name = vd.get("vod_name") or ""
        category = vd.get("vod_class") or ""
        if not name:
            m = re.search(r"<title>([^<]*)</title>", html)
            if m:
                name = m.group(1).split("-")[0].strip()
        if not name:
            name = vid
        pic = ""
        if play:
            pic = re.sub(r"/[^/]+\.m3u8([?#].*)?$", "/1.jpg", play)
        return {"name": name, "category": category, "url": play, "pic": pic}

    def _fetch_play(self, play_id):
        play_id = str(play_id or "").strip()
        if not play_id:
            return ""
        if re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", play_id):
            return play_id
        if not play_id.startswith("http"):
            play_id = self._play_url(play_id)
        html = self._get_html(play_id)
        if not html:
            return ""
        d = self._extract_player(html)
        return d.get("url") or ""

    def _play_url(self, vid):
        return self.host + "/index.php/vod/play/id/%s/sid/1/nid/1.html" % vid

    def _parse_cards(self, html):
        items = []
        seen = set()
        for m in re.finditer(r'<section class="item-box">(.*?)</section>', html, re.S):
            block = m.group(1)
            hm = re.search(r'href="(/index\.php/vod/play/id/(\d+)/sid/1/nid/1\.html)"', block)
            if not hm:
                continue
            vid = hm.group(2)
            if vid in seen:
                continue
            seen.add(vid)
            tm = re.search(r'title="([^"]+)"', block)
            name = tm.group(1) if tm else ""
            pm = re.search(r'<img[^>]*src="([^"]+)"', block)
            pic = pm.group(1) if pm else ""
            smalls = [s.strip() for s in re.findall(r'<small>([^<]*)</small>', block) if s.strip()]
            remarks = smalls[-1] if smalls else ""
            if name and pic:
                items.append({"id": vid, "name": name, "pic": pic, "remarks": remarks})
        return items

    def _extract_player(self, html):
        m = re.search(r"player_aaaa=", html)
        if not m:
            mm = re.search(r"(https?://[^\s\"']+\.m3u8[^\s\"']*)", html)
            return {"url": mm.group(1) if mm else ""}
        start = m.end()
        depth = 0
        i = start
        instr = False
        esc = False
        while i < len(html):
            c = html[i]
            if instr:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    instr = False
            else:
                if c == '"':
                    instr = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        break
            i += 1
        try:
            d = json.loads(html[start:i + 1])
            if isinstance(d, dict):
                return d
        except Exception:
            pass
        mm = re.search(r"(https?://[^\s\"']+\.m3u8[^\s\"']*)", html)
        return {"url": mm.group(1) if mm else ""}

    def _pagecount_from_count(self, html):
        m = re.search(r'tx-c1 ml5">\s*(\d+)\+?', html)
        if m:
            total = int(m.group(1))
            return max(1, -(-total // PAGE_SIZE))
        return self._pagecount_from_pager(html)

    def _pagecount_from_pager(self, html):
        nums = [int(x) for x in re.findall(r"/page/(\d+)", html)]
        if nums:
            return max(nums)
        return 1

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("id") or item.get("vod_id") or "")
        return {
            "vod_id": vid,
            "vod_name": item.get("name") or item.get("title") or vid,
            "vod_pic": item.get("pic") or item.get("vod_pic") or "",
            "vod_remarks": item.get("remarks") or "",
        }

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

    def _net_opts(self, opts):
        net = getattr(self, "net", None)
        if net is None:
            return opts
        if hasattr(net, "_native"):
            return opts
        return json.dumps(opts)

    def _req(self, url, **kw):
        net = getattr(self, "net", None)
        if net is not None:
            try:
                opts = {"timeout": kw.get("timeout", 15000)}
                for k in ("params", "headers", "method", "postType", "data", "body", "buffer", "redirect", "callTimeout", "cookie"):
                    if k in kw and kw[k] is not None:
                        opts[k] = kw[k]
                resp = net.req(url, self._net_opts(opts))
                return self._resp_dict(resp)
            except Exception:
                return {"code": 0, "content": "", "headers": {}, "error": "req"}
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
                return {"code": resp.getcode() or 0, "content": raw.decode("utf-8", "replace"), "headers": dict(resp.headers), "error": None}
        except Exception as e:
            return {"code": 0, "content": "", "headers": {}, "error": str(e)}

    def _get_html(self, url, **kw):
        resp = self._req(url, **kw)
        if isinstance(resp, str):
            return resp
        if not isinstance(resp, dict):
            return None
        if resp.get("error"):
            return None
        code = resp.get("code") or 0
        if not 200 <= code < 300:
            return None
        return resp.get("content", "")
