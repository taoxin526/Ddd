# -*- coding: utf-8 -*-
# [枫叶影院  更新于:2026-11-01 01:25]
import json
import re
import time
import threading
import struct
import zlib
import base64
import gzip
import urllib.request
import http.cookiejar
from lxml import etree
from urllib.parse import quote, unquote

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        def proxy(self, params):
            return [404, "text/plain", ""]
        def localProxy(self, params):
            return [404, "text/plain", ""]

NAME = "枫叶影院"
HOSTS = ["https://www.cd-zj.com", "https://maihaolian.com", "https://zzztool.com"]
UA = ("Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36")

PARSE_API = {
    "JD4K": "https://fgsrg.hzqingshan.com",
    "JD": "https://fgsrg.hzqingshan.com",
    "co": "https://zzrs.mfdyvip.com",
    "YYNB": "https://zzrs.mfdyvip.com",
    "knmb": "https://zzrs.mfdyvip.com",
}

TRAIN_B64 = "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AAAABgOB4NgAGYxj/AABgGAYAAAABBgPBmMMADDMMwwAGYPAYAAAAAAYFg2AYAAGAYBgAAYBg2wAAAABfDGAMBgABwBgDAAAzGHwAAAAAzwZjCMAADcOYwwAMMZg8AAAAAYYFg2AYAAGAYBgAAYBg2wAAAABBgOB4NgAGYxj/AABgGAYAAAABDwZjDMMABnDsAwAEMZg8AAAAAn+MAwDcAA5gDAMADDGYPAAAAAFPBmMIwAANw5jDAAwxmDwAAAABjwZjCMAADcOYwwAMMZg8AAAAAYGA4Hg2AAZjGP8AAGAYBgAAAAEBgOB4NgAGYxj/AABgGAYAAAABDwZjCMAADcOYwwAMMZg8AAAAAYYFg2AYAAGAYBgAAYBg2wAAAABPBmMIwAANw5jDAAwxmDwAAAABgYDgeDYABmMY/wAAYBgGAAAAAQYFg2AYAAGAYBgAAYBg2wAAAAB/jAMA3AAOYAwDAAwxmDwAAAABTwZjCMAADcOYwwAMMZg8AAAAAYYDwZjDAAwzDMMABmDwGAAAAAAfDGAMBgABwBgDAAAzGHwAAAAAzwZjDGYAA8GYwwAMMZg8AAAAAgYFg2AYAAGAYBgAAYBg2wAAAABfDGAMBgABwBgDAAAzGHwAAAAAxgPBmMMADDMMwwAGYPAYAAAAAAGA4Hg2AAZjGP8AAGAYBgAAAAEPBmMMZgADwZjDAAwxmDwAAAAAxgPBmMMADDMMwwAGYPAYAAAAAA8GYwjAAA3DmMMADDGYPAAAAAGPBmMMZgADwZjDAAwxmDwAAAACHwxgDAYAAcAYAwAAMxh8AAAAAN8MYAwGAAHAGAMAADMYfAAAAADfDGAMBgABwBgDAAAzGHwAAAAA3wxgDAYAAcAYAwAAMxh8AAAAAM="

class Spider(BaseSpider):
    def __init__(self):
        self.hosts = list(HOSTS)
        self.host = self.hosts[0]
        self.name = NAME
        self.options = {}
        self._idx = 0
        self._lock = threading.Lock()
        self._jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._jar))
        self._train_cache = None

    def init(self, extend=""):
        if isinstance(extend, dict):
            cfg = extend
        elif extend:
            try:
                cfg = json.loads(str(extend))
            except Exception:
                cfg = {}
        else:
            cfg = {}
        if isinstance(cfg, dict):
            site = (cfg.get("site") or cfg.get("url") or "").strip().rstrip("/")
            if site and site not in self.hosts:
                with self._lock:
                    self.hosts = [site] + self.hosts
                    self.host = self.hosts[0]
        self.options = cfg

    def getDependence(self):
        return []

    def destroy(self):
        with self._lock:
            self._jar.clear()
            self._train_cache = None
        self.options = {}

    def _req(self, url, **kw):
        net = getattr(self, "net", None)
        if net is not None:
            try:
                opts = {"timeout": kw.get("timeout", 15000)}
                for k in ("params", "headers", "method", "postType", "data",
                          "body", "buffer", "redirect", "callTimeout", "cookie"):
                    if k in kw and kw[k] is not None:
                        opts[k] = kw[k]
                opts.setdefault("cookie", True)
                resp = net.req(url, opts)
                return resp or {}
            except Exception:
                pass
        return self._req_urllib(url, **kw)

    def _req_urllib(self, url, **kw):
        try:
            timeout = (kw.get("timeout") or 15000) / 1000.0
            method = (kw.get("method") or "GET").upper()
            params = kw.get("params")
            if params:
                sep = "&" if "?" in url else "?"
                url = url + sep + "&".join(
                    "%s=%s" % (k, quote(str(v), safe="")) for k, v in params.items())
            headers = dict(kw.get("headers") or {})
            headers.setdefault("User-Agent", UA)
            headers.setdefault("Accept", "*/*")
            data = None
            if method == "POST":
                body = kw.get("data") or kw.get("body") or {}
                if isinstance(body, dict):
                    data = "&".join("%s=%s" % (k, quote(str(v), safe=""))
                                    for k, v in body.items()).encode()
                elif isinstance(body, str):
                    data = body.encode()
                else:
                    data = body
                headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with self._opener.open(req, timeout=timeout) as resp:
                raw = resp.read()
                enc = (resp.headers.get("Content-Encoding") or "").lower()
                if enc == "gzip":
                    raw = gzip.decompress(raw)
                elif enc == "deflate":
                    raw = zlib.decompress(raw)
                if kw.get("buffer") == 3:
                    return {"code": resp.getcode() or 0, "content": raw,
                            "headers": dict(resp.headers), "error": None}
                return {"code": resp.getcode() or 0,
                        "content": raw.decode("utf-8", "replace"),
                        "headers": dict(resp.headers), "error": None}
        except Exception as e:
            return {"code": 0, "content": "", "headers": {}, "error": str(e)}

    def _get(self, path, referer=None):
        hosts = self.hosts
        verified = getattr(self, "_verified_host", None)
        if verified and verified in hosts:
            hosts = [verified] + [h for h in hosts if h != verified]
        for _ in range(len(hosts) * 2):
            d = hosts[self._idx % len(hosts)]
            url = path if path.startswith("http") else d + self._path_for(d, path)
            try:
                resp = self._req(url, headers={"Referer": referer or d + "/"})
                if resp.get("error") or not (200 <= (resp.get("code") or 0) < 300):
                    self._idx += 1
                    continue
                text = resp.get("content", "")
                if isinstance(text, (bytes, bytearray)):
                    text = text.decode("utf-8", "replace")
                if "系统安全验证" in text:
                    if self._verify(d, self._path_for(d, path)):
                        resp = self._req(url, headers={"Referer": d + "/"})
                        text = resp.get("content", "")
                        if isinstance(text, (bytes, bytearray)):
                            text = text.decode("utf-8", "replace")
                    if "系统安全验证" in text:
                        self._idx += 1
                        continue
                return text
            except Exception:
                self._idx += 1
        return ""

    def _path_for(self, domain, path):
        if "zzztool" in domain:
            return path
        if path.startswith("/list/"):
            return path.replace("/list/", "/cupfox-list/", 1)
        if path.startswith("/search/"):
            return path.replace("/search/", "/cupfox-search/", 1)
        return path

    def _post_form(self, url, data, referer=None):
        net = getattr(self, "net", None)
        if net is not None:
            try:
                resp = net.req(url, {"method": "POST", "postType": "form",
                                     "data": data, "cookie": True,
                                     "headers": {"Referer": referer or url},
                                     "timeout": 15000})
                return resp or {}
            except Exception:
                pass
        return self._req_urllib(url, method="POST", data=data,
                                headers={"Referer": referer or url,
                                         "X-Requested-With": "XMLHttpRequest"})

    def _host(self):
        return self.hosts[self._idx % len(self.hosts)]

    def _verify(self, domain, back_path):
        for attempt in range(6):
            try:
                resp = self._req(domain + "/captcha.php?type=code&r=0.%d" % (attempt + 1),
                                 headers={"Referer": domain + "/"}, buffer=3)
                if resp.get("error"):
                    continue
                img = resp.get("content")
                if isinstance(img, str):
                    continue
                code = self._ocr(img)
                if not code:
                    continue
                rv = self._post_form(domain + "/captcha.php?type=verify",
                                     {"check": code}, domain + back_path)
                text = rv.get("content", "")
                if isinstance(text, (bytes, bytearray)):
                    text = text.decode("utf-8", "replace")
                if '"code":1' in text or "验证成功" in text:
                    self._verified_host = domain
                    return True
            except Exception:
                continue
        return False

    def _ocr(self, img_bytes):
        try:
            mats = self._split_digits(img_bytes)
            if not mats or len(mats) != 4:
                return ""
            return "".join(str(self._knn(m)) for m in mats)
        except Exception:
            return ""

    @staticmethod
    def _decode_png(data):
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError("not png")
        pos, idat, w, h, ct = 8, b"", 0, 0, 0
        while pos < len(data):
            ln = struct.unpack(">I", data[pos:pos + 4])[0]
            typ = data[pos + 4:pos + 8]
            if typ == b"IHDR":
                w, h, bd, ct, comp, filt, inter = struct.unpack(
                    ">IIBBBBB", data[pos + 8:pos + 21])
            elif typ == b"IDAT":
                idat += data[pos + 8:pos + 8 + ln]
            elif typ == b"IEND":
                break
            pos += 12 + ln
        raw = zlib.decompress(idat)
        bpp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
        stride = w * bpp
        out = bytearray()
        prev = bytearray(stride)
        p = 0
        for _ in range(h):
            f = raw[p]
            p += 1
            line = bytearray(raw[p:p + stride])
            p += stride
            if f == 1:
                for i in range(bpp, stride):
                    line[i] = (line[i] + line[i - bpp]) & 0xff
            elif f == 2:
                for i in range(stride):
                    line[i] = (line[i] + prev[i]) & 0xff
            elif f == 3:
                for i in range(stride):
                    a = line[i - bpp] if i >= bpp else 0
                    line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xff
            elif f == 4:
                for i in range(stride):
                    a = line[i - bpp] if i >= bpp else 0
                    b = prev[i]
                    c = prev[i - bpp] if i >= bpp else 0
                    pp = a + b - c
                    pa, pb, pc = abs(pp - a), abs(pp - b), abs(pp - c)
                    pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                    line[i] = (line[i] + pr) & 0xff
            out += line
            prev = line
        return w, h, out, stride

    def _split_digits(self, img_bytes):
        w, h, out, stride = self._decode_png(img_bytes)
        col = [0] * w
        for y in range(h):
            for x in range(w):
                off = y * stride + x * 3
                if (out[off] + out[off + 1] + out[off + 2]) / 3 < 128:
                    col[x] += 1
        runs, x = [], 0
        while x < w:
            if col[x] > 0:
                x0 = x
                while x < w and col[x] > 0:
                    x += 1
                if x - x0 >= 4:
                    runs.append((x0, x))
            else:
                x += 1
        if len(runs) != 4:
            return []
        mats = []
        for (x0, x1) in runs:
            ys = [y for y in range(h) if any(
                (out[y * stride + xx * 3] + out[y * stride + xx * 3 + 1]
                 + out[y * stride + xx * 3 + 2]) / 3 < 128 for xx in range(x0, x1))]
            if not ys:
                return []
            y0, y1 = min(ys), max(ys) + 1
            mat = [[0] * 10 for _ in range(14)]
            for yy in range(y0, y1):
                for xx in range(x0, x1):
                    if (out[yy * stride + xx * 3] + out[yy * stride + xx * 3 + 1]
                            + out[yy * stride + xx * 3 + 2]) / 3 < 128:
                        mat[int((yy - y0) / (y1 - y0) * 13)][int((xx - x0) / (x1 - x0) * 9)] = 1
            mats.append(mat)
        return mats

    def _knn(self, mat):
        train = self._train()
        dists = []
        for rows, lab in train:
            s = 0
            for yy in range(14):
                for xx in range(10):
                    s += abs(mat[yy][xx] - rows[yy][xx])
            dists.append((s, lab))
        dists.sort(key=lambda t: t[0])
        votes = {}
        for _, lab in dists[:5]:
            votes[lab] = votes.get(lab, 0) + 1
        return max(votes.items(), key=lambda t: t[1])[0]

    def _train(self):
        if self._train_cache is not None:
            return self._train_cache
        blob = base64.b64decode(TRAIN_B64)
        out = []
        for i in range(0, len(blob), 19):
            if i + 19 > len(blob):
                break
            b = blob[i:i + 18]
            lab = blob[i + 18]
            rows = []
            for yy in range(14):
                rows.append([(b[(yy * 10 + xx) >> 3] >> (7 - ((yy * 10 + xx) & 7))) & 1
                             for xx in range(10)])
            out.append((rows, lab))
        self._train_cache = out
        return out

    def homeContent(self, filter):
        cls = [
            {"type_id": "/label/qq", "type_name": "腾讯SVIP"},
            {"type_id": "/label/youku", "type_name": "优酷SVIP"},
            {"type_id": "/label/bli", "type_name": "B站SVIP"},
            {"type_id": "2", "type_name": "电视剧"},
            {"type_id": "1", "type_name": "电影"},
            {"type_id": "4", "type_name": "动漫"},
            {"type_id": "3", "type_name": "综艺"},
            {"type_id": "5", "type_name": "热门短剧"},
        ]
        return {"class": cls, "filters": self._filters()}

    def _filters(self):
        years = [{"n": "全部", "v": ""}] + [{"n": str(y), "v": str(y)}
                                            for y in range(2026, 2003, -1)]
        area = [{"n": "全部", "v": ""}, {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"},
                {"n": "台湾", "v": "台湾"}, {"n": "美国", "v": "美国"}, {"n": "韩国", "v": "韩国"},
                {"n": "日本", "v": "日本"}, {"n": "泰国", "v": "泰国"}, {"n": "新加坡", "v": "新加坡"},
                {"n": "马来西亚", "v": "马来西亚"}, {"n": "印度", "v": "印度"}, {"n": "英国", "v": "英国"},
                {"n": "法国", "v": "法国"}, {"n": "加拿大", "v": "加拿大"}, {"n": "西班牙", "v": "西班牙"},
                {"n": "俄罗斯", "v": "俄罗斯"}, {"n": "其它", "v": "其它"}]
        lang = [{"n": "全部", "v": ""}, {"n": "国语", "v": "国语"}, {"n": "英语", "v": "英语"},
                {"n": "粤语", "v": "粤语"}, {"n": "闽南语", "v": "闽南语"}, {"n": "韩语", "v": "韩语"},
                {"n": "日语", "v": "日语"}, {"n": "法语", "v": "法语"}, {"n": "德语", "v": "德语"},
                {"n": "其它", "v": "其它"}]
        sort = [{"n": "时间", "v": "time"}, {"n": "人气", "v": "hits"}, {"n": "评分", "v": "score"}]
        letter = [{"n": "全部", "v": ""}] + [{"n": c, "v": c} for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"] \
                 + [{"n": "0-9", "v": "0-9"}]
        g = lambda vs: [{"n": v[0], "v": v[1]} for v in vs]
        return {
            "2": [
                {"key": "class", "name": "类型", "value": g(
                    [("全部", "2"), ("国产剧", "13"), ("日韩剧", "15"), ("海外剧", "16")])},
                {"key": "area", "name": "地区", "value": area},
                {"key": "genre", "name": "剧情", "value": g([("全部", ""), ("古装", "古装"),
                    ("战争", "战争"), ("青春偶像", "青春偶像"), ("喜剧", "喜剧"), ("家庭", "家庭"),
                    ("犯罪", "犯罪"), ("动作", "动作"), ("奇幻", "奇幻"), ("剧情", "剧情"),
                    ("历史", "历史"), ("经典", "经典"), ("乡村", "乡村"), ("情景", "情景"),
                    ("商战", "商战"), ("网剧", "网剧"), ("其他", "其他")])},
                {"key": "year", "name": "年份", "value": years},
                {"key": "lang", "name": "语言", "value": lang},
                {"key": "letter", "name": "字母", "value": letter},
                {"key": "sort", "name": "排序", "value": sort},
            ],
            "1": [
                {"key": "class", "name": "类型", "value": g([("全部", "1"), ("动作片", "6"),
                    ("喜剧片", "7"), ("恐怖片", "8"), ("科幻片", "9"), ("爱情片", "10"),
                    ("剧情片", "11"), ("战争片", "12"), ("纪录片", "20")])},
                {"key": "area", "name": "地区", "value": area},
                {"key": "genre", "name": "剧情", "value": g([("全部", ""), ("喜剧", "喜剧"),
                    ("爱情", "爱情"), ("恐怖", "恐怖"), ("动作", "动作"), ("科幻", "科幻"),
                    ("剧情", "剧情"), ("战争", "战争"), ("警匪", "警匪"), ("犯罪", "犯罪"),
                    ("动画", "动画"), ("奇幻", "奇幻"), ("武侠", "武侠"), ("冒险", "冒险"),
                    ("枪战", "枪战"), ("悬疑", "悬疑"), ("惊悚", "惊悚"), ("经典", "经典"),
                    ("青春", "青春"), ("文艺", "文艺"), ("微电影", "微电影"), ("古装", "古装"),
                    ("历史", "历史"), ("运动", "运动"), ("农村", "农村"), ("儿童", "儿童"),
                    ("网络电影", "网络电影")])},
                {"key": "year", "name": "年份", "value": years},
                {"key": "lang", "name": "语言", "value": lang},
                {"key": "letter", "name": "字母", "value": letter},
                {"key": "sort", "name": "排序", "value": sort},
            ],
            "4": [
                {"key": "class", "name": "类型", "value": g([("全部", "4"), ("国产动漫", "25"),
                    ("日韩动漫", "26")])},
                {"key": "genre", "name": "剧情", "value": g([("全部", ""), ("情感", "情感"),
                    ("科幻", "科幻"), ("热血", "热血"), ("推理", "推理"), ("搞笑", "搞笑"),
                    ("冒险", "冒险"), ("奇幻", "奇幻"), ("战斗", "战斗"), ("校园", "校园"),
                    ("萝莉", "萝莉"), ("治愈", "治愈"), ("原创", "原创"), ("亲子", "亲子"),
                    ("益智", "益智"), ("励志", "励志"), ("其他", "其他")])},
                {"key": "area", "name": "地区", "value": area},
                {"key": "year", "name": "年份", "value": years},
                {"key": "lang", "name": "语言", "value": lang},
                {"key": "letter", "name": "字母", "value": letter},
                {"key": "sort", "name": "排序", "value": sort},
            ],
            "3": [
                {"key": "class", "name": "类型", "value": g([("全部", "3"), ("大陆综艺", "21"),
                    ("日韩综艺", "22")])},
                {"key": "genre", "name": "剧情", "value": g([("全部", ""), ("选秀", "选秀"),
                    ("情感", "情感"), ("访谈", "访谈"), ("播报", "播报"), ("音乐", "音乐"),
                    ("美食", "美食"), ("旅游", "旅游"), ("搞笑", "搞笑"), ("游戏", "游戏"),
                    ("亲子", "亲子"), ("其它", "其它")])},
                {"key": "area", "name": "地区", "value": area},
                {"key": "year", "name": "年份", "value": years},
                {"key": "lang", "name": "语言", "value": lang},
                {"key": "letter", "name": "字母", "value": letter},
                {"key": "sort", "name": "排序", "value": sort},
            ],
        }

    def homeVideoContent(self):
        html = self._get("/")
        return {"list": self._parse_list(html)}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            tid = str(tid)
            page = int(pg) if pg else 1
            if tid.startswith("/label"):
                html = self._get("%s/page/%d.html" % (tid, page))
                items = self._parse_list(html)
                return {"list": items, "page": page,
                        "pagecount": page + 2 if len(items) >= 20 else page,
                        "limit": 20, "total": len(items)}
            args = {}
            if isinstance(filter, dict):
                args.update({k: str(v) for k, v in filter.items() if v})
            if isinstance(extend, dict):
                args.update({k: str(v) for k, v in extend.items() if v and k not in args})
            type_val = args.get("class", args.get("tid", tid))
            area = args.get("area", "")
            genre = args.get("genre", "")
            year = args.get("year", "")
            lang = args.get("lang", "")
            letter = args.get("letter", "")
            sort = args.get("sort", "")
            if not any([area, genre, year, lang, letter, sort]):
                url = "/list/%s--------%d---.html" % (type_val, page)
            else:
                url = "/list/%s-%s-%s-%s-%s-%s--%d---%s.html" % (
                    type_val, area, sort, genre, lang, letter, page, year)
            html = self._get(url)
            items = self._parse_list(html)
            total = page
            if html:
                m = re.search(r"尾页[^>]*href=\"[^\"]*?/?(\d+)[^\"]*\"", html)
                if m:
                    total = int(m.group(1))
                else:
                    m2 = re.search(r"(\d+)页", html)
                    if m2:
                        total = int(m2.group(1))
            if not items:
                total = 0
            return {"list": items, "page": page, "pagecount": total,
                    "limit": 36, "total": total * 36}
        except Exception as e:
            return {"list": [], "pagecount": 1, "msg": str(e)}

    def _parse_list(self, html):
        if not html or "系统安全验证" in html:
            return []
        try:
            root = etree.HTML(html)
        except Exception:
            return []
        videos, seen = [], set()
        for a in root.xpath(
                '//a[contains(@class,"module-item") or contains(@class,"public-list-exp")]'):
            href = a.get("href") or ""
            m = re.search(r"/detail/(\d+)\.html", href)
            if not m:
                continue
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            imgs = a.xpath('.//div[contains(@class,"module-item-pic")]/img | .//img')
            img = imgs[0] if imgs else None
            name = a.get("title") or a.get("alt") or (img.get("alt") if img is not None else "") or ""
            if not name:
                s = a.xpath('.//strong')
                if s:
                    name = "".join(s[0].itertext()).strip()
            pic = img.get("data-src") if img is not None else ""
            if pic.startswith("//"):
                pic = "https:" + pic
            pic = pic.replace("&amp;", "&")
            note = a.xpath('.//*[contains(@class,"module-item-note") or contains(@class,"ft2")]')
            remarks = "".join(note[0].itertext()).strip() if note else ""
            if not name:
                continue
            videos.append({"vod_id": vid, "vod_name": name.strip(),
                           "vod_pic": pic, "vod_remarks": remarks,
                           "vod_year": remarks})
        return videos

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        results = []
        for vid in ids:
            r = self._detail(str(vid))
            if r:
                results.append(r)
        merged = {"list": [item for r in results for item in (r.get("list") or [])]}
        return merged

    def _detail(self, vid):
        if vid.startswith("http"):
            return {"list": [{"vod_id": vid, "vod_name": vid.replace("https://", ""),
                              "vod_pic": "", "vod_director": "", "vod_actor": "",
                              "vod_content": "枫叶影院入口",
                              "vod_play_from": "入口", "vod_play_url": "进入$" + vid}]}
        html = self._get("/detail/%s.html" % vid)
        if not html or "系统安全验证" in html:
            return {"list": []}
        try:
            root = etree.HTML(html)
        except Exception:
            return {"list": []}
        name = ""
        h1 = root.xpath('//*[contains(@class,"module-info-heading")]//h1 | //h1')
        if h1:
            name = "".join(h1[0].itertext()).strip()
        if not name:
            st = root.xpath('//*[contains(@class,"slide-info-title")]')
            if st:
                name = "".join(st[0].itertext()).strip()
        name = name or vid
        pic = ""
        imgs = root.xpath('//*[contains(@class,"module-item-pic")]/img | '
                          '//*[contains(@class,"slide-info")]//img | //img[@class="lazy"] | //img')
        if imgs:
            pic = imgs[0].get("data-src") or imgs[0].get("src") or ""
            if pic.startswith("//"):
                pic = "https:" + pic
            pic = pic.replace("&amp;", "&")
        director, actor, content = "", "", ""
        for item in root.xpath('//*[contains(@class,"module-info-item")]'):
            t = item.xpath('.//*[contains(@class,"module-info-item-title")]')
            c = item.xpath('.//*[contains(@class,"module-info-item-content")]')
            if t and c:
                tt = "".join(t[0].itertext()).strip()
                cc = "".join(c[0].itertext()).strip()
                if "导演" in tt:
                    director = cc
                elif "主演" in tt:
                    actor = cc
        for el in root.xpath('//*[contains(@class,"slide-info")]'):
            txt = " ".join(el.itertext()).strip()
            if txt.startswith("导演"):
                director = txt.replace("导演", "").replace("：", "").strip()
            elif txt.startswith("演员"):
                actor = txt.replace("演员", "").replace("：", "").strip()
        p = root.xpath('//*[contains(@class,"module-info-introduction-content")]//p')
        if p:
            content = "".join(p[0].itertext()).strip()
        tabs, eps_groups = [], []
        mx_tabs = root.xpath('//button[contains(concat(" ",normalize-space(@class)," ")," mx-anthology-tab ")]')
        if mx_tabs:
            for t in mx_tabs:
                lab = t.xpath('.//span[contains(concat(" ",normalize-space(@class)," ")," mx-anthology-tab-label ")]')
                tabs.append("".join(lab[0].itertext()).strip() if lab
                            else " ".join(t.itertext()).strip())
            for panel in root.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," mx-anthology-panel ")]'):
                eps = [a.get("href") or "" for a in panel.xpath('.//a')]
                eps_groups.append([e for e in eps if e])
        else:
            for t in root.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," anthology-tab ")]//a[contains(concat(" ",normalize-space(@class)," ")," swiper-slide ")]'):
                tabs.append(re.sub(r"\s*[（(]?\d+[）)]?\s*$", "",
                                   " ".join(t.itertext()).strip()))
            for box in root.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," anthology-list-box ")]'):
                eps = [a.get("href") or "" for a in box.xpath('.//a')]
                eps_groups.append([e for e in eps if e])
        name_cnt = {}
        clean_tabs = []
        for t in tabs:
            key = re.sub(r"\s*[（(]?\d+[）)]?\s*$", "", t).strip()
            name_cnt[key] = name_cnt.get(key, 0) + 1
            clean_tabs.append(key if name_cnt[key] == 1 else "%s-%d" % (key, name_cnt[key]))
        order = []
        for i, t in enumerate(clean_tabs):
            order.append((self._line_key(t), i, t))
        order.sort(key=lambda x: (x[0], x[1]))
        play_from, play_url = [], []
        for _, _, t in order:
            idx = clean_tabs.index(t)
            if idx < len(eps_groups) and eps_groups[idx]:
                play_from.append(t)
                play_url.append("#".join(eps_groups[idx]))
        if not play_from:
            return {"list": []}
        return {"list": [{
            "vod_id": vid, "vod_name": name, "vod_pic": pic,
            "vod_director": director, "vod_actor": actor, "vod_content": content,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url)}]}

    def _line_key(self, name):
        n = name.lower()
        if "4k" in n:
            return 0
        if "2k" in n:
            return 1
        if "自营r" in n or n == "r":
            return 2
        if "自营t" in n or n == "t":
            return 3
        if "自营y" in n or n == "y":
            return 4
        return 9

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg) if pg else 1
            kw = unquote(str(key))
            url = "/search/%s----------%d---.html" % (quote(kw), page)
            html = self._get(url)
            items = self._parse_list(html)
            return {"list": items, "page": page,
                    "pagecount": page + 2 if len(items) >= 20 else page,
                    "limit": 36, "total": len(items)}
        except Exception as e:
            return {"list": [], "pagecount": 1, "msg": str(e)}

    def playerContent(self, flag, id, vipFlags):
        try:
            play = str(id).split("$")[-1]
            if play.startswith("http") and not re.search(r"\.(m3u8|mp4)", play, re.I):
                return {"parse": 0, "url": play, "header": {"User-Agent": UA}}
            if re.search(r"\.(m3u8|mp4)", play, re.I):
                return {"parse": 0, "url": play, "header": {"User-Agent": UA,
                        "Referer": self._host() + "/"}}
            if not play.startswith("/play/"):
                play = "/play/%s.html" % play
            html = self._get(play)
            if not html:
                return {"parse": 0, "url": "", "msg": "播放页获取失败"}
            m = re.search(r"player_aaaa=(.*?)</script>", html, re.S)
            if not m:
                return {"parse": 0, "url": "", "msg": "未找到播放数据"}
            try:
                pd = json.loads(m.group(1))
            except Exception:
                return {"parse": 0, "url": "", "msg": "播放数据解析失败"}
            url = pd.get("url", "")
            pf = pd.get("from", "")
            if not url:
                return {"parse": 0, "url": "", "msg": "该集无播放地址"}
            if url.startswith("http"):
                return {"parse": 0, "url": url, "header": {"User-Agent": UA,
                        "Referer": self._host() + "/"}}
            final = self._resolve(url, pf)
            if not final:
                return {"parse": 0, "url": "", "msg": "解析失败"}
            return {"parse": 0, "url": final, "header": {"User-Agent": UA,
                    "Referer": self._host() + "/"}}
        except Exception as e:
            return {"parse": 0, "url": "", "msg": str(e)}

    def _resolve(self, enc_url, play_from):
        base = PARSE_API.get(play_from, "https://fgsrg.hzqingshan.com")
        try:
            page = self._req(base + "/player/?url=" + quote(enc_url),
                             headers={"User-Agent": UA, "Referer": self._host() + "/"})
            text = page.get("content", "")
            if isinstance(text, (bytes, bytearray)):
                text = text.decode("utf-8", "replace")
            tm = re.search(r"data-te=\"([^\"]+)\"", text)
            if not tm:
                return ""
            token = tm.group(1)
            r = self._post_form(base + "/player/mplayer.php",
                                {"url": enc_url, "token": token},
                                base + "/player/?url=" + enc_url)
            t = r.get("content", "")
            if isinstance(t, (bytes, bytearray)):
                t = t.decode("utf-8", "replace")
            j = json.loads(t)
            return j.get("url", "")
        except Exception:
            return ""

    def getProxyUrl(self, params=None, local=True):
        try:
            from com.github.catvod import Proxy
            u = Proxy.getUrl(local)
            return u + "?do=py" + ("&siteKey=%s" % getattr(self, "siteKey", "")
                                   if getattr(self, "siteKey", "") else "")
        except Exception:
            return ""

    def proxyUrl(self, params=None, local=True):
        try:
            from com.github.catvod import Proxy
            return Proxy.getUrl(local)
        except Exception:
            return ""

    def proxy(self, params):
        return [404, "text/plain", ""]

    def localProxy(self, params):
        return self.proxy(params)

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|flv|mkv|ts)(\?|$)", str(url)))

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {"msg": "不支持此操作"}
