# -*- coding: utf-8 -*-
# [独播库  更新于:2026-11-03 00:20]
import base64
import json
import re
import threading
import time
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

NAME = "独播库"
HOSTS = ["https://www.dbku.tv"]
UA = "Mozilla/5.0 (Linux; Android 13; Pixel) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
PAGE_SIZE = 20
CACHE_TTL = 60
DEBUG = False
VOD_ID_PREFIX = ""

CLASSES = [
    ("1", "电影"),
    ("2", "连续剧"),
    ("13", "陆剧"),
    ("15", "日韩剧"),
    ("14", "台泰剧"),
    ("21", "短剧"),
    ("3", "综艺"),
    ("4", "动漫"),
]


class Spider(BaseSpider):

    def __init__(self):
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self._cache = {}
        self._cache_time = {}
        self._lock = threading.Lock()
        self._good_host = None
        self.options = {}

    def init(self, extend=""):
        cfg = {}
        if isinstance(extend, dict):
            cfg = extend
        elif extend:
            try:
                cfg = json.loads(extend)
            except Exception:
                cfg = {}
        if isinstance(cfg, dict):
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
        classes = [{"type_id": tid, "type_name": nm} for tid, nm in CLASSES]
        result = {"class": classes}
        if filter:
            result["filters"] = self._filters(classes)
        result["list"] = []
        return result

    def homeVideoContent(self):
        html = self._get_html(self.host + "/")
        if not html:
            return {"list": []}
        items = self._flat_home_items(html)
        return {"list": items}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        extend = extend or {}
        if tid == "hot":
            items = self._hot_items()
            return self._list_resp(items, pg)
        if tid.startswith("actor/"):
            name = unquote(tid.split("/", 1)[1])
            return self._search_resp(self._fetch_search_page(name, 1, 12), pg)
        if tid.startswith("director/"):
            name = unquote(tid.split("/", 1)[1])
            return self._search_resp(self._fetch_search_page(name, 5, 8), pg)
        if tid.startswith("tag/"):
            name = unquote(tid.replace("tag/", "", 1))
            return self._search_resp(self._fetch_search(name, pg), pg)
        items, pagecount = self._fetch_list_page(tid, pg, extend)
        return self._list_resp(items, pg, pagecount)

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        responses = [self._detail(str(video_id)) for video_id in ids]
        merged = {}
        for r in responses:
            if r:
                for k, v in r.items():
                    if k == "list":
                        merged.setdefault("list", []).extend(v)
                    elif k not in merged:
                        merged[k] = v
        merged.setdefault("list", [])
        return merged

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        items = self._fetch_search(str(key or "").strip(), pg)
        return self._search_resp(items, pg)

    def playerContent(self, flag, id, vipFlags):
        url = self._fetch_play(str(id or ""))
        if not url:
            return {"parse": 0, "msg": "无法获取播放地址"}
        return {
            "parse": 0,
            "jx": 0,
            "url": url,
            "header": self._string_map({"User-Agent": UA}),
        }

    def liveContent(self, url):
        return "[]"

    def _req(self, url, **kw):
        net = getattr(self, "net", None)
        if net is not None:
            try:
                opts = {"timeout": kw.get("timeout", 15000)}
                for k in ("params", "headers", "method", "postType", "data", "body", "buffer", "redirect", "cookie"):
                    if k in kw and kw[k] is not None:
                        opts[k] = kw[k]
                return net.req(url, opts) or {}
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
                code = resp.getcode() or 0
                return {"code": code, "content": raw.decode("utf-8", "replace"), "headers": dict(resp.headers), "error": None}
        except Exception as e:
            return {"code": 0, "content": "", "headers": {}, "error": str(e)}

    def _get_html(self, url, **kw):
        ck = "h:" + url
        with self._lock:
            hit = self._cache.get(ck)
            if hit and time.time() - self._cache_time.get(ck, 0) < CACHE_TTL:
                return hit
        resp = self._req(url, **kw)
        if resp.get("error"):
            return None
        code = resp.get("code") or 0
        if not 200 <= code < 300:
            return None
        c = resp.get("content", "")
        if isinstance(c, (bytes, bytearray)):
            c = c.decode("utf-8", "replace")
        with self._lock:
            self._cache[ck] = c
            self._cache_time[ck] = time.time()
        return c

    def _get_json(self, url, **kw):
        try:
            t = self._get_html(url, **kw)
            return json.loads(t) if t else {}
        except Exception:
            return {}

    def _fix_url(self, u):
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return self.host.rstrip("/") + u
        return u

    def _parse_cards(self, html):
        from lxml import etree
        items = []
        if not html:
            return items
        tree = etree.HTML(html)
        return self._parse_cards_el(tree)

    def _parse_cards_el(self, root):
        items = []
        for a in root.xpath('.//a[contains(@class,"myui-vodlist__thumb")]'):
            href = a.get("href") or ""
            m = re.search(r"/voddetail/(\d+)\.html", href)
            if not m:
                continue
            vid = m.group(1)
            name = (a.get("title") or "").strip()
            pic = a.get("data-original") or a.get("data-src") or ""
            if not pic:
                im = a.xpath(".//img/@data-original")
                if im:
                    pic = im[0]
            remarks = ""
            pt = a.xpath('.//span[contains(@class,"pic-text")]')
            if pt:
                remarks = self._text(pt[0]).strip()
            if not remarks:
                pg = a.xpath('.//span[contains(@class,"pic-tag")]//span[contains(@class,"tag")]')
                if pg:
                    remarks = self._text(pg[0]).strip()
            items.append({
                "id": vid,
                "name": name,
                "pic": self._fix_url(pic),
                "remarks": remarks,
            })
        return items

    def _flat_home_items(self, html):
        from lxml import etree
        seen = set()
        out = []
        if not html:
            return out
        tree = etree.HTML(html)
        for panel in tree.xpath('//div[contains(@class,"myui-panel") and contains(@class,"myui-panel-bg")]'):
            hd = panel.xpath('.//div[contains(@class,"myui-panel__head")]//h3[contains(@class,"title")]')
            if not hd:
                continue
            cards = self._parse_cards_el(panel)
            for c in cards:
                vid = c.get("id")
                if vid and vid not in seen:
                    seen.add(vid)
                    out.append(c)
        return [self._vod(x) for x in out]

    def _hot_items(self):
        html = self._get_html(self.host + "/")
        if not html:
            return []
        from lxml import etree
        tree = etree.HTML(html)
        for panel in tree.xpath('//div[contains(@class,"myui-panel") and contains(@class,"myui-panel-bg")]'):
            hd = panel.xpath('.//div[contains(@class,"myui-panel__head")]//h3[contains(@class,"title")]')
            if hd and self._text(hd[0]).strip() == "热剧推荐":
                return self._parse_cards_el(panel)
        return []

    def _get_pagecount(self, html):
        m = re.search(r'href="([^"]*vodshow[^"]*\.html)"[^>]*>\s*尾页\s*<', html or "")
        if m:
            mm = re.search(r"-(\d+)---", m.group(1))
            if mm:
                return int(mm.group(1))
        nums = []
        for mm in re.finditer(r"-(\d+)---(?:\.html|(?:\d))", html or ""):
            nums.append(int(mm.group(1)))
        if nums:
            return max(nums)
        return 1

    def _build_show_url(self, tid, pg, extend):
        f = [""] * 11
        f[0] = quote(extend.get("area", ""), safe="")
        f[1] = quote(extend.get("order", ""), safe="")
        f[2] = quote(extend.get("class", ""), safe="")
        f[3] = quote(extend.get("lang", ""), safe="")
        f[4] = quote(extend.get("letter", ""), safe="")
        f[7] = str(pg)
        f[10] = quote(extend.get("year", ""), safe="")
        return self.host.rstrip("/") + "/vodshow/%s-%s.html" % (tid, "-".join(f))

    def _fetch_list(self, tid, pg, extend):
        url = self._build_show_url(tid, pg, extend)
        html = self._get_html(url)
        if not html:
            return []
        return self._parse_cards(html)

    def _fetch_list_page(self, tid, pg, extend):
        url = self._build_show_url(tid, pg, extend)
        html = self._get_html(url)
        if not html:
            return [], 1
        items = self._parse_cards(html)
        return items, self._get_pagecount(html)

    def _fetch_search(self, keyword, pg):
        url = self.host.rstrip("/") + "/index.php/ajax/suggest?mid=1&wd=" + quote(keyword, safe="") + "&limit=50"
        data = self._get_json(url)
        items = []
        if not isinstance(data, dict):
            return items
        for it in data.get("list", []) or []:
            u = it.get("url") or ""
            m = re.search(r"/voddetail/(\d+)\.html", u)
            if m:
                items.append({"id": m.group(1), "name": it.get("name") or "", "pic": "", "remarks": ""})
        return items

    def _fetch_search_page(self, name, dash_before, dash_after):
        url = self.host.rstrip("/") + "/vodsearch/" + "-" * dash_before + quote(name, safe="") + "-" * dash_after + ".html"
        html = self._get_html(url)
        if not html:
            return []
        return self._parse_cards(html)

    def _fetch_detail(self, vid):
        html = self._get_html(self.host.rstrip("/") + "/voddetail/%s.html" % vid)
        if not html:
            return None
        from lxml import etree
        tree = etree.HTML(html)
        name = ""
        pic = ""
        h1 = tree.xpath('//div[contains(@class,"myui-content__detail")]//h1[contains(@class,"title")]')
        if h1:
            name = self._text(h1[0]).strip()
        img = tree.xpath('//div[contains(@class,"myui-content__thumb")]//img/@data-original')
        if img:
            pic = self._fix_url(img[0])
        category = ""
        area = ""
        year = ""
        for a in tree.xpath('//div[contains(@class,"myui-content__detail")]//p[contains(@class,"data")]//a'):
            href = a.get("href") or ""
            txt = self._text(a).strip()
            if re.search(r"/vodshow/\d+-----------\d{4}\.html$", href):
                year = txt
            elif re.search(r"/vodshow/\d+[^-]+\-+\.html$", href) or re.search(r"/vodshow/\d+-\S+?----------\.html$", href):
                area = txt
            elif re.search(r"/vodshow/\d+-+\.html$", href):
                category = txt
        actors = []
        directors = []
        for p in tree.xpath('//div[contains(@class,"myui-content__detail")]//p[contains(@class,"data")]'):
            seg = self._text(p)
            links = [self._text(a).strip() for a in p.xpath(".//a")]
            if "主演" in seg or "主演：" in seg:
                actors.extend([x for x in links if x])
            elif "导演" in seg or "导演：" in seg:
                directors.extend([x for x in links if x])
        description = ""
        sketch = tree.xpath('//div[@id="desc"]//span[contains(@class,"sketch")]')
        full = tree.xpath('//div[@id="desc"]//span[contains(@class,"data")]')
        if full:
            description = self._text(full[0]).strip()
        elif sketch:
            description = self._text(sketch[0]).strip()
        episodes = []
        for pl in tree.xpath('//div[starts-with(@id,"playlist")]'):
            for li in pl.xpath(".//li//a"):
                href = li.get("href") or ""
                m = re.search(r"/vodplay/(\d+)-(\d+)-(\d+)\.html", href)
                if m:
                    ep_name = self._text(li).strip() or ("第%s集" % m.group(3))
                    episodes.append({
                        "name": ep_name,
                        "url": self._fix_url(href),
                    })
        return {
            "name": name,
            "pic": pic,
            "category": category,
            "area": area,
            "year": year,
            "actors": actors,
            "directors": directors,
            "description": description,
            "episodes": episodes,
        }

    def _fetch_play(self, play_id):
        if re.search(r"\.(m3u8|mp4|flv|ts)(\?|$)", play_id):
            return play_id
        url = self._fix_url(play_id)
        html = self._get_html(url)
        if not html:
            return ""
        m = re.search(r"player_data\s*=\s*(\{.*?\})\s*</script>", html, re.S)
        if not m:
            return ""
        try:
            pd = json.loads(m.group(1))
        except Exception:
            return ""
        raw = pd.get("url") or ""
        enc = pd.get("encrypt", 0)
        try:
            if enc == 2:
                b64 = raw + "=" * (-len(raw) % 4)
                dec = base64.b64decode(b64).decode("utf-8", "replace")
                return unquote(dec)
            if enc == 1:
                return unquote(raw)
            return raw
        except Exception:
            return raw

    def _vod(self, item):
        item = item or {}
        vid = str(item.get("id") or item.get("vod_id") or "")
        return {
            "vod_id": vid,
            "vod_name": item.get("name") or item.get("title") or vid,
            "vod_pic": item.get("pic") or item.get("cover") or "",
            "vod_remarks": item.get("remarks") or item.get("duration") or "",
        }

    def _detail(self, vid):
        data = self._fetch_detail(vid)
        if not data:
            return {"list": []}
        eps = data.get("episodes") or []
        if eps:
            lines = []
            for ep in eps:
                title = self._safe_label(ep.get("name") or "")
                url = ep.get("url") or ""
                if url:
                    lines.append("%s$%s" % (title, url))
            play_url = "#".join(lines)
            play_from = "正片"
        else:
            play_url = ""
            play_from = "正片"
        vod = {
            "vod_id": vid,
            "vod_name": data.get("name") or vid,
            "vod_pic": data.get("pic") or "",
            "type_name": data.get("category") or "",
            "vod_year": str(data.get("year") or ""),
            "vod_area": data.get("area") or "",
            "vod_remarks": data.get("remarks") or "",
            "vod_director": self._clickable("director", "、".join(data.get("directors") or [])),
            "vod_actor": "、".join(self._clickable("actor", a) for a in (data.get("actors") or [])),
            "vod_content": data.get("description") or "",
            "vod_play_from": play_from,
            "vod_play_url": play_url,
        }
        return {"list": [vod]}

    def _list_resp(self, items, pg, pagecount=None):
        if not pagecount:
            pagecount = pg if len(items) < PAGE_SIZE else 9999
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pagecount,
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def _search_resp(self, items, pg):
        return {
            "list": [self._vod(x) for x in items],
            "page": pg,
            "pagecount": pg if len(items) < PAGE_SIZE else 9999,
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def _filters(self, classes):
        filters = {}
        order = {"key": "order", "name": "排序", "init": "",
                 "value": [{"n": "时间", "v": ""}, {"n": "人气", "v": "人气"}, {"n": "评分", "v": "评分"}]}
        class_f = {"key": "class", "name": "类型", "init": "全部",
                   "value": [{"n": "全部", "v": ""}]}
        area_f = {"key": "area", "name": "地区", "init": "全部",
                  "value": [{"n": "全部", "v": ""}]}
        year_f = {"key": "year", "name": "年份", "init": "全部",
                  "value": [{"n": "全部", "v": ""}]}
        lang_f = {"key": "lang", "name": "语言", "init": "全部",
                  "value": [{"n": "全部", "v": ""}]}
        letter_f = {"key": "letter", "name": "字母", "init": "全部",
                    "value": [{"n": "全部", "v": ""}]}
        html = self._get_html(self._build_show_url("2", 1, {}))
        if html:
            from lxml import etree
            tree = etree.HTML(html)
            for ul in tree.xpath('//ul[contains(@class,"myui-screen__list")]'):
                lab = ul.xpath('.//a[contains(@class,"text-muted")]')
                if not lab:
                    continue
                label = self._text(lab[0]).strip()
                values = []
                for a in ul.xpath('.//a[contains(@class,"btn")]'):
                    txt = self._text(a).strip()
                    if txt in ("全部", "") or "text-muted" in (a.get("class") or ""):
                        continue
                    values.append({"n": txt, "v": txt})
                if label == "排序":
                    order["value"] = [{"n": "时间", "v": ""}] + values
                elif label == "剧情":
                    class_f["value"] = [{"n": "全部", "v": ""}] + values
                elif label == "地区":
                    area_f["value"] = [{"n": "全部", "v": ""}] + values
                elif label == "年份":
                    year_f["value"] = [{"n": "全部", "v": ""}] + values
                elif label == "语言":
                    lang_f["value"] = [{"n": "全部", "v": ""}] + values
                elif label == "字母":
                    letter_f["value"] = [{"n": "全部", "v": ""}] + values
        fl = [order, class_f, area_f, year_f, lang_f, letter_f]
        for c in classes:
            filters[c["type_id"]] = fl
        return filters


    @staticmethod
    def _text(el):
        if el is None:
            return ""
        if hasattr(el, "text_content"):
            return el.text_content().strip()
        return "".join(el.itertext()).strip()

    def _safe_label(self, text):
        return str(text or "").replace("$", "＄").replace("#", "＃").strip()

    def _clickable(self, kind, name):
        if not name:
            return ""
        ident = "%s/%s" % (kind, quote(name, safe=""))
        payload = json.dumps({"id": ident, "name": name, "type_flag": "0"}, ensure_ascii=False, separators=(",", ":"))
        return "[a=cr:%s/]%s[/a]" % (payload, name)

    @staticmethod
    def _string_map(value):
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            return {}
        return {str(k): str(v) for k, v in value.items() if v is not None}

    def _int(self, x, d=0):
        try:
            return int(x)
        except Exception:
            return d
