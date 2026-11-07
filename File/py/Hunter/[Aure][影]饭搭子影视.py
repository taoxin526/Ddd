# -*- coding: utf-8 -*-
# [饭搭子影视  更新于:2026-11-05 00:00]
# 主机: fdzys.net / fdzys.com (发布页 fff666.xyz 动态取最新, 弹窗提示收藏)
# 契约: macCMS mizhiady 模板 / HTML 路线 (API /api.php 被禁)
#   列表 /<cat>/all?page=N, 详情 /<cat>/<slug>, 搜索 /yu-<kw>-xianguan-de-yingpian-shippin-zhibo
#   播放: 详情源 tab -> 播放页 player_aaaa.url (m3u8 直链 / share 分享页)
#   share 分享页: var main / const url -> m3u8 直链 (需 Referer=站点 + 移动 UA)
import json
import re
import time
import threading
import urllib.request
import urllib.error
import urllib.parse
import ssl
from urllib.parse import quote, unquote

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        def proxy(self, params):
            return [404, "text/plain", ""]
        def localProxy(self, params):
            return [404, "text/plain", ""]

NAME = "饭搭子影视"
DEFAULT_HOSTS = ["https://fdzys.net", "https://fdzys.com"]
PUB_SITES = ["https://fff666.xyz", "https://fff666.site", "https://fdzys666.xyz"]
UA = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Mobile Safari/537.36"
MOBILE_UA = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Mobile Safari/537.36"
PAGE_SIZE = 24
DOMAIN_TTL = 6 * 3600
CACHE_TTL = 60
VIDEO_RE = re.compile(r"\.(m3u8|mp4|flv|mkv|ts|mpd)(\?|$)", re.I)
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

_CLASSES = [
    {"type_id": "movie", "type_name": "电影"},
    {"type_id": "tv", "type_name": "电视剧"},
    {"type_id": "dongman", "type_name": "动漫片"},
    {"type_id": "zongyi", "type_name": "综艺片"},
    {"type_id": "tiyu", "type_name": "体育"},
    {"type_id": "duanju", "type_name": "短剧"},
]


class Spider(BaseSpider):

    def __init__(self):
        self.host = DEFAULT_HOSTS[0]
        self.name = NAME
        self._cache = {}
        self._cache_time = {}
        self._lock = threading.Lock()
        self._domain_pool = list(DEFAULT_HOSTS)
        self._pub_sites = list(PUB_SITES)

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
                if site not in self._domain_pool:
                    self._domain_pool.insert(0, site)
                self.host = site
        self.options = cfg

    def getDependence(self):
        return []

    def destroy(self):
        with self._lock:
            self._cache.clear()
            self._cache_time.clear()
        self.options = {}

    def isVideoFormat(self, url):
        return bool(VIDEO_RE.search(str(url)))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {"msg": "不支持此操作"}

    def homeContent(self, filter):
        self._refresh_domains()
        result = {"class": _CLASSES}
        items = self._fetch_cards(self._site_html("movie/all?page=1"))
        if not items:
            items = self._fetch_cards(self._site_html(""))
        result["list"] = [self._vod(c) for c in items[:PAGE_SIZE]]
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._int(pg, 1)
        tid = str(tid or "")
        if tid.startswith("actor/") or tid.startswith("director/") or tid.startswith("tag/"):
            name = unquote(tid.split("/", 1)[1])
            items = self._search_items(name, pg)
            return self._page(items, pg)
        path = "%s/all?page=%d" % (tid.strip("/"), pg)
        items = self._fetch_cards(self._site_html(path))
        return self._page(items, pg)

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        results = []
        for vid in ids:
            r = self._detail(str(vid or ""))
            results.extend(r.get("list") or [])
        return {"list": results}

    def searchContent(self, key, quick, pg="1"):
        pg = self._int(pg, 1)
        items = self._search_items(str(key or "").strip(), pg)
        return {
            "list": [self._vod(c) for c in items],
            "page": pg,
            "pagecount": pg,
            "limit": PAGE_SIZE,
            "total": len(items),
        }

    def playerContent(self, flag, id, vipFlags):
        url = self._fetch_play(str(id or ""))
        if not url:
            return {"parse": 0, "msg": "无法获取播放地址"}
        if VIDEO_RE.search(url):
            return {
                "parse": 0,
                "jx": 0,
                "url": url,
                "header": self._string_map({"User-Agent": UA, "Referer": self._pick_host() + "/"}),
            }
        # 非视频 URL (腾讯页面 / 分享页兜底) 交给解析器/嗅探
        return {"parse": 1, "jx": 0, "url": url}

    def liveContent(self, url):
        return "[]"

    def _page(self, items, pg):
        return {
            "list": [self._vod(c) for c in items],
            "page": pg,
            "pagecount": pg if len(items) < PAGE_SIZE else 9999,
            "limit": PAGE_SIZE,
            "total": 999999,
        }

    def _vod(self, c):
        vid = "%s/%s" % (c.get("cat", ""), c.get("slug", ""))
        return {
            "vod_id": vid,
            "vod_name": c.get("name") or vid,
            "vod_pic": c.get("pic") or "",
            "vod_remarks": c.get("remark") or "",
        }

    def _detail(self, vid):
        vid = vid.strip("/")
        if not vid:
            return {"list": []}
        html = self._site_html(vid)
        if not html:
            return {"list": [], "msg": "未找到此影片"}
        html = re.sub(r'<!--.*?-->', '', html, flags=re.S)
        name = self._detail_name(html)
        pic = self._g(html, r'<meta property="og:image" content="([^"]+)"')
        if not pic:
            pic = self._g(html, r'data-original="([^"]+)"')
        if pic and pic.startswith("/") and not pic.startswith("//"):
            pic = self._pick_host() + pic
        elif pic.startswith("//"):
            pic = "https:" + pic
        tags = [t.strip() for t in re.findall(r'<a class="tag" href="[^"]*">([^<]*)</a>', html) if t.strip()]
        director = self._detail_meta(html, "导演")
        actor = self._detail_meta(html, "主演")
        intro = self._extract_intro(html)
        lang = self._g(html, r'<div class="item-top" title="([^"]*)"').strip()
        score = self._g(html, r'<span[^>]*class="iconfont icon-pingfen\s*"></span>\s*<div class="score">([^<]*)</div>').strip()
        if not score:
            score = self._g(html, r'detail-box[^>]*>\s*([\d.]+)', 1).strip()
        sources = self._parse_sources(html)
        play_from_parts = []
        play_url_parts = []
        for sid, sname, eps in sources:
            ep_parts = []
            for en, eu in eps:
                ep_parts.append("%s$%s" % (self._safe_label(en), eu))
            if ep_parts:
                play_from_parts.append(sname)
                play_url_parts.append("#".join(ep_parts))
        play_from = "$$$".join(play_from_parts)
        play_url = "$$$".join(play_url_parts)
        if not play_url:
            m = re.search(r'<a href="([^"]*/\d+[^"]*)"[^>]*>([^<]*)</a>', html)
            if m:
                play_from = "正片"
                play_url = self._safe_label(m.group(2)) + "$" + m.group(1)
        content_parts = []
        if director:
            content_parts.append("导演：" + director)
        if actor:
            content_parts.append("主演：" + actor)
        if lang:
            content_parts.append("语言：" + lang)
        if score:
            content_parts.append("评分：" + score)
        if intro:
            content_parts.append(intro)
        vod = {
            "vod_id": vid,
            "vod_name": name or vid,
            "vod_pic": pic,
            "type_name": "",
            "vod_year": "",
            "vod_area": "",
            "vod_remarks": "",
            "vod_director": self._clickable("director", director),
            "vod_actor": "、".join(self._clickable("actor", a) for a in [x.strip() for x in actor.split(",") if x.strip()]),
            "vod_content": "\n".join(content_parts),
            "vod_play_from": play_from,
            "vod_play_url": play_url,
        }
        return {"list": [vod]}

    def _fetch_play(self, url):
        url = (url or "").strip()
        if not url:
            return ""
        page_url = url if url.startswith("http") else (self._pick_host() + "/" + url.lstrip("/"))
        html = self._req_text(page_url)
        if not html:
            return ""
        raw = self._extract_player(html)
        if not raw:
            return ""
        try:
            pj = json.loads(raw)
        except Exception:
            return ""
        u = pj.get("url") or ""
        u = str(u).replace("\\/", "/").strip()
        if "/share/" in u:
            return self._resolve_share(u)
        return u

    def _resolve_share(self, share_url):
        text = self._req_text(share_url, headers={"User-Agent": MOBILE_UA, "Referer": self._pick_host() + "/"})
        if not text:
            return share_url
        m = re.search(r'(?:const url|var main)\s*=\s*"([^"]+)"', text)
        if not m:
            m = re.search(r'\burl\s*=\s*"([^"]+)"', text)
        if not m:
            return share_url
        path = m.group(1).strip().replace("\\/", "/")
        if path.startswith("http"):
            return path
        try:
            netloc = urllib.parse.urlparse(share_url).netloc
        except Exception:
            return share_url
        return "https://" + netloc + (path if path.startswith("/") else "/" + path)

    def _search_items(self, key, pg):
        if not key:
            return []
        q = urllib.parse.quote(key)
        path = "yu-%s-xianguan-de-yingpian-shippin-zhibo" % q
        return self._fetch_cards(self._site_html(path))

    def _fetch_cards(self, html):
        if not html:
            return []
        html = re.sub(r'<!--.*?-->', '', html, flags=re.S)
        cards = []
        parts = re.split(r'<div class="myui-vodbox-content">', html)
        for part in parts[1:]:
            m = re.search(r'<a href="([^"]+)"', part)
            if not m:
                continue
            href = m.group(1)
            if not href.startswith("/") and "fdzys" not in href and not href.startswith("http"):
                continue
            m2 = re.search(r'data-src="([^"]+)"', part)
            pic = m2.group(1) if m2 else ""
            if not pic or "loading" in pic or "placeholder" in pic:
                m3 = re.search(r'src="([^"]+)"', part)
                pic = m3.group(1) if m3 else ""
                if pic and ("loading" in pic or "placeholder" in pic or pic.startswith("data:")):
                    pic = ""
            if pic and pic.startswith("/") and not pic.startswith("//"):
                pic = self._pick_host() + pic
            elif pic.startswith("//"):
                pic = "https:" + pic
            tag = re.search(r'<div class="tag[^"]*">([^<]*)</div>', part)
            remark = tag.group(1).strip() if tag else ""
            title = re.search(r'<div class="card-info">.*?<div class="title">([^<]*)</div>', part, re.S)
            name = title.group(1).strip() if title else ""
            if not name:
                t2 = re.search(r'<div class="title">([^<]*)</div>', part)
                name = t2.group(1).strip() if t2 else ""
            cat, slug = self._split_href(href)
            if not slug:
                continue
            cards.append({"cat": cat, "slug": slug, "name": name, "pic": pic, "remark": remark})
        return cards

    def _split_href(self, href):
        href = href.split("?")[0].rstrip("/")
        href = href.replace("https://", "").replace("http://", "")
        if "/" in href:
            parts = href.split("/")
            if len(parts) >= 2:
                return parts[-2], parts[-1]
        return "", ""

    def _parse_sources(self, html):
        out = []
        seen = set()
        for sid, seg in re.findall(r'<a href="#playlist(\d+)"[^>]*>(.*?)</a>', html, re.S):
            name = re.sub(r'<[^>]+>', '', seg).strip()
            if not name or sid in seen:
                continue
            seen.add(sid)
            eps = []
            m = re.search(r'<div id="playlist%s"[^>]*>(.*?)(?=<div id="playlist|\Z)' % sid, html, re.S)
            if m:
                for em in re.finditer(r'<a href="([^"]*)">([^<]*)</a>', m.group(1)):
                    eu = em.group(1).strip()
                    en = em.group(2).strip()
                    if eu:
                        eps.append((en, eu))
            out.append((sid, name, eps))
        return out

    def _extract_player(self, html):
        i = html.find("var player_aaaa=")
        if i < 0:
            return ""
        j = html.find("{", i)
        if j < 0:
            return ""
        depth = 0
        for k in range(j, len(html)):
            if html[k] == "{":
                depth += 1
            elif html[k] == "}":
                depth -= 1
                if depth == 0:
                    return html[j:k + 1]
        return ""

    def _detail_name(self, html):
        m = re.search(r'<h1 class="title_name"[^>]*>(.*?)</h1>', html, re.S)
        if m:
            seg = re.sub(r'<span class="title_ep">.*?</span>', '', m.group(1), flags=re.S)
            txt = re.sub(r'<[^>]+>', ' ', seg)
            txt = re.sub(r'\s+', ' ', txt).strip()
            if txt:
                return txt
        t = self._g(html, r'<h1 class="title"[^>]*>([^<]*)</h1>')
        return t.strip()

    def _detail_meta(self, html, label):
        m = re.search(r'<div class="name">%s:</div>\s*([^<]+)' % label, html)
        if m:
            v = m.group(1).strip()
            if v:
                return v
        m = re.search(r'<div class="detail-meta"[^>]*>%s：([^<]+)</div>' % label, html)
        if m:
            return m.group(1).strip()
        return ""

    def _extract_intro(self, html):
        i = html.find('<div class="intro">')
        if i < 0:
            return ""
        m = re.search(r'<div class="intro">(.*?)</div>\s*</div>\s*</div>', html[i:], re.S)
        seg = m.group(1) if m else html[i:i + 3000]
        ps = re.findall(r'<p[^>]*>([^<]+)</p>', seg)
        if ps:
            txt = "".join(p.strip() for p in ps if p.strip())
        else:
            txt = re.sub(r'<[^>]+>', ' ', seg)
            txt = re.sub(r'\s+', ' ', txt).strip()
        return txt.strip()

    def _refresh_domains(self, force=False):
        local = getattr(self, "local", None)
        cached = None
        if local is not None and not force:
            try:
                cached = local.get("fdz_domains")
            except Exception:
                cached = None
        if cached and isinstance(cached, dict) and time.time() - (cached.get("ts") or 0) < DOMAIN_TTL:
            pool = cached.get("sites") or []
            pubs = cached.get("pub") or []
            if pool:
                self._domain_pool = pool
                self._pub_sites = pubs or list(PUB_SITES)
                return
        pool = []
        pubs = []
        for pub in PUB_SITES:
            text = self._req_text(pub + "/")
            if not text:
                continue
            for m in re.finditer(r"\{\s*url:\s*'([^']+)'", text):
                u = m.group(1).strip().rstrip("/")
                if not re.match(r"^https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(/|$)", u):
                    continue
                if any(k in u for k in ("t.me", "你的", "xxxx", "example", "your-")):
                    continue
                if u not in pool:
                    pool.append(u)
            m = re.search(r"var SITES\s*=\s*\[([^\]]*)\]", text)
            if m:
                for d in re.findall(r"'([^']+)'", m.group(1)):
                    if d not in pubs:
                        pubs.append(d)
            if pool:
                break
        if not pool:
            pool = list(DEFAULT_HOSTS)
        if not pubs:
            pubs = list(PUB_SITES)
        self._domain_pool = pool
        self._pub_sites = pubs
        if local is not None:
            try:
                local.set("fdz_domains", {"ts": time.time(), "sites": pool, "pub": pubs})
            except Exception:
                pass

    def _site_html(self, path):
        path = str(path or "").lstrip("/")
        pool = self._domain_pool or list(DEFAULT_HOSTS)
        for h in pool:
            url = h + "/" + path
            resp = self._req(url)
            code, text = self._resp_parts(resp)
            if code and 200 <= code < 400 and text:
                self._set_host(h)
                return text
        return ""

    def _req_text(self, url, **kw):
        resp = self._req(url, **kw)
        code, text = self._resp_parts(resp)
        return text if text else ""

    def _req(self, url, **kw):
        net = getattr(self, "net", None)
        if net is not None:
            try:
                opts = {"timeout": kw.get("timeout", 15000)}
                for k in ("params", "headers", "method", "postType", "data", "body", "buffer", "redirect", "cookie"):
                    if k in kw and kw[k] is not None:
                        opts[k] = kw[k]
                return net.req(url, self._net_opts(opts)) or {}
            except Exception:
                return {}
        return self._req_urllib(url, **kw)

    def _net_opts(self, opts):
        net = getattr(self, "net", None)
        if net is not None and hasattr(net, "_native"):
            return opts
        return json.dumps(opts)

    def _req_urllib(self, url, **kw):
        headers = {"User-Agent": UA}
        hd = kw.get("headers")
        if hd:
            headers.update(hd)
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=kw.get("timeout", 15), context=SSL_CTX) as resp:
                data = resp.read()
                return {"code": resp.status, "content": data, "headers": dict(resp.headers), "error": None}
        except urllib.error.HTTPError as e:
            try:
                return {"code": e.code, "content": e.read(), "headers": {}, "error": None}
            except Exception:
                return {"code": e.code, "content": "", "headers": {}, "error": None}
        except Exception as e:
            return {"code": 0, "content": "", "headers": {}, "error": str(e)}

    def _resp_parts(self, resp):
        if isinstance(resp, dict):
            code = resp.get("code", 200)
            content = resp.get("content", "")
            if isinstance(content, bytes):
                return code, content.decode("utf-8", "replace")
            return code, str(content or "")
        if isinstance(resp, str):
            return 200, resp
        return 200, str(resp or "")

    def _set_host(self, h):
        if h and h != self.host:
            self.host = h
        with self._lock:
            self._cache.clear()

    def _pick_host(self):
        pool = self._domain_pool or list(DEFAULT_HOSTS)
        return self.host if self.host in pool else pool[0]

    def _clickable(self, kind, name):
        if not name:
            return ""
        ident = "%s/%s" % (kind, quote(name, safe=""))
        payload = json.dumps({"id": ident, "name": name, "type_flag": "0"}, ensure_ascii=False, separators=(",", ":"))
        return "[a=cr:%s/]%s[/a]" % (payload, name)

    def _safe_label(self, text):
        return str(text or "").replace("$", "＄").replace("#", "＃").strip()

    def _g(self, html, pat, group=1):
        m = re.search(pat, html, re.S)
        return m.group(group) if m else ""

    def _int(self, x, d=0):
        try:
            return int(x)
        except Exception:
            return d

    @staticmethod
    def _string_map(value):
        if not isinstance(value, dict):
            return {}
        return {str(k): str(v) for k, v in value.items() if v is not None}
