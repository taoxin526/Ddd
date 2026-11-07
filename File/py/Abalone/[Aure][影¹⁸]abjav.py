# -*- coding: utf-8 -*-
# [abjav¹⁸  更新于:2026-11-05 08:42]
try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        pass
import re
import json
from urllib.parse import quote, unquote, urlencode

HOST = "https://abjav.com"
_ALPH = "АВСDЕFGHIJKLМNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,~"
_IDX = {c: i for i, c in enumerate(_ALPH)}
_CNT = 60


def _b64dec(s):
    s = re.sub(r"[^АВСЕМA-Za-z0-9.,~]", "", s)
    out = []
    n = 0
    ln = len(s)
    while n < ln:
        v = [_IDX.get(s[n + i], 64) for i in range(4)]
        out.append(chr((v[0] << 2) | (v[1] >> 4)))
        if v[2] != 64:
            out.append(chr(((15 & v[1]) << 4) | (v[2] >> 2)))
        if v[3] != 64:
            out.append(chr(((3 & v[2]) << 6) | v[3]))
        n += 4
    return "".join(out)


class Spider(BaseSpider):
    def init(self, extend=""):
        self._cats = None

    def _req(self, url, **kw):
        net = getattr(self, "net", None)
        if net is not None:
            try:
                opts = {"timeout": kw.get("timeout", 15000)}
                for k in ("params", "headers", "method", "postType", "data", "body", "buffer", "redirect", "cookie"):
                    if k in kw and kw[k] is not None:
                        opts[k] = kw[k]
                return net.req(url, opts)
            except Exception:
                return None
        return self._req_urllib(url, **kw)

    def _req_urllib(self, url, **kw):
        import urllib.request
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            req.add_header("Accept", "application/json")
            hd = kw.get("headers")
            if hd:
                for k, v in hd.items():
                    req.add_header(k, v)
            if kw.get("method") == "POST":
                d = kw.get("data")
                if isinstance(d, dict):
                    d = urlencode(d).encode()
                req.data = d
                req.add_header("Content-Type", "application/x-www-form-urlencoded")
            with urllib.request.urlopen(req, timeout=kw.get("timeout", 15)) as resp:
                return resp.read()
        except Exception:
            return None

    def _j(self, url, **kw):
        r = self._req(url, **kw)
        if r is None:
            return {}
        if isinstance(r, dict):
            if r.get("error"):
                return {}
            r = r.get("content")
        if isinstance(r, bytes):
            r = r.decode("utf-8", "replace")
        if isinstance(r, str):
            try:
                return json.loads(r)
            except Exception:
                return {}
        return {}

    def _clickable(self, kind, name, dirn):
        inner = json.dumps({"id": kind + "/" + dirn, "name": name, "type_flag": "1"}, ensure_ascii=False)
        return "[a=cr:%s/]%s[/a]" % (inner, name)

    def _to_vod(self, v, detail=False):
        if not v:
            return {}
        vid = str(v.get("video_id", ""))
        vod = {
            "vod_id": vid,
            "vod_name": v.get("title", ""),
            "vod_pic": v.get("scr") or v.get("thumb") or "",
            "vod_remarks": v.get("duration") or "",
            "vod_year": (v.get("post_date") or "")[:4],
            "vod_actor": "",
            "vod_director": "",
            "vod_content": "",
            "vod_play_from": "",
            "vod_play_url": "",
        }
        if not detail:
            return vod
        tags = v.get("tags") or {}
        tag_list = []
        for _, tag in tags.items():
            if isinstance(tag, dict):
                tn = tag.get("title", "")
                td = tag.get("dir", "")
                if tn and td:
                    tag_list.append(self._clickable("tag", tn, td))
        vod["vod_actor"] = "、".join(tag_list)
        ch = v.get("channel") or {}
        if ch.get("title") and ch.get("dir"):
            vod["vod_director"] = self._clickable("folder/channels", ch["title"], ch["dir"])
        parts = []
        if v.get("description"):
            parts.append(v["description"])
        if ch.get("title"):
            parts.append("频道：" + ch["title"])
        if ch.get("videos"):
            parts.append("共" + str(ch["videos"]) + "部")
        vod["vod_content"] = "\n".join(parts)
        vod["vod_pic"] = v.get("thumb") or v.get("thumbsrc") or v.get("scr") or ""
        play = self._play_urls(vid)
        if play:
            vod["vod_play_from"] = "高清"
            vod["vod_play_url"] = "#".join(l + "$" + u for l, u in play)
        return vod

    def _play_urls(self, vid):
        data = self._j(HOST + "/api/videofile.php?video_id=%s&lifetime=8640000" % vid)
        if not isinstance(data, list):
            return []
        urls = []
        for item in data:
            if not isinstance(item, dict):
                continue
            fmt = item.get("format", "")
            if "_tr" in fmt:
                continue
            vu = item.get("video_url", "")
            if not vu:
                continue
            try:
                u = _b64dec(vu)
            except Exception:
                continue
            if not u.startswith("/get_file"):
                continue
            label = fmt.replace(".", "").upper() or "默认"
            urls.append((label, HOST + u))
        return urls

    def _list_resp(self, data):
        vids = data.get("videos") or []
        total = data.get("total_count")
        pc = 1
        if total:
            try:
                t = int(total)
                pc = int(t // _CNT) + (1 if t % _CNT else 0)
            except Exception:
                pc = 1
        return {"list": [self._to_vod(v) for v in vids], "pagecount": pc}

    def _classes(self):
        if self._cats is not None:
            return self._cats
        data = self._j(HOST + "/api/json/categories/14400/str.toptn.en.json")
        cats = data.get("categories") or []
        cls = []
        for sid, sname in (("latest-updates", "Newest"), ("top-rated", "Top Rated"),
                           ("most-viewed", "Most Viewed"), ("most-popular", "Popular"),
                           ("longest", "Longest"), ("most-commented", "Most Commented")):
            cls.append({"type_id": "sort:" + sid, "type_name": sname, "type_flag": 0})
        for c in cats:
            if not isinstance(c, dict):
                continue
            d = c.get("dir")
            if not d:
                continue
            cls.append({"type_id": d, "type_name": c.get("title") or d, "type_flag": 0})
        cls.append({"type_id": "folder/channels", "type_name": "🎬 频道", "type_flag": 0})
        cls.append({"type_id": "folder/models", "type_name": "💃 女优", "type_flag": 0})
        self._cats = cls
        return cls

    def homeContent(self, filter):
        data = self._j(HOST + "/api/json/videos2/3600/str/latest-updates/%d/.hd.1.all....json" % _CNT)
        resp = self._list_resp(data)
        resp["class"] = self._classes()
        return resp

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        if tid.startswith("folder/"):
            parts = tid.split("/")
            if len(parts) == 2:
                return self._folder_list(parts[1], pg)
            return self._folder_videos(parts[1], parts[2], pg)
        if tid.startswith("tag/"):
            q = unquote(tid.split("/", 1)[1])
            return self._search(q, pg)
        if tid.startswith("sort:"):
            sort = tid.split(":", 1)[1]
            url = HOST + "/api/json/videos2/86400/str/%s/%d/.hd.%d.all....json" % (sort, _CNT, pg)
            return self._list_resp(self._j(url))
        url = HOST + "/api/json/videos2/86400/str/latest-updates/%d/categories.%s.%d.all....json" % (_CNT, tid, pg)
        return self._list_resp(self._j(url))

    def _folder_list(self, type_, pg):
        vods = []
        if type_ == "channels":
            url = HOST + "/api/json/channels/86400/str/latest-updates-toptn/%d/..%d.json" % (_CNT, pg)
            items = (self._j(url).get("channels") or [])
            for c in items:
                if not isinstance(c, dict):
                    continue
                pic = ""
                t = c.get("toptn") or []
                if t and isinstance(t[0], dict):
                    pic = t[0].get("scr", "")
                vods.append({
                    "vod_id": "folder/channels/" + c.get("dir", ""),
                    "vod_name": c.get("title", ""),
                    "vod_pic": pic,
                    "vod_remarks": str((c.get("statistics") or {}).get("videos", "")) + "部",
                    "vod_tag": "folder",
                })
        elif type_ == "models":
            url = HOST + "/api/json/models/86400/str/filt........../most-popular/%d/%d.json" % (_CNT, pg)
            items = (self._j(url).get("models") or [])
            for m in items:
                if not isinstance(m, dict):
                    continue
                vods.append({
                    "vod_id": "folder/models/" + m.get("dir", ""),
                    "vod_name": m.get("title", ""),
                    "vod_pic": m.get("img") or "",
                    "vod_remarks": str((m.get("statistics") or {}).get("videos", "")) + "部",
                    "vod_tag": "folder",
                })
        return {"list": vods, "pagecount": 1}

    def _folder_videos(self, type_, value, pg):
        if type_ == "channels":
            url = HOST + "/api/json/videos2/86400/str/latest-updates/%d/channel.%s.%d.all....json" % (_CNT, value, pg)
        elif type_ == "models":
            url = HOST + "/api/json/videos2/86400/str/latest-updates/%d/model.%s.%d.all....json" % (_CNT, value, pg)
        else:
            return {"list": [], "pagecount": 1}
        return self._list_resp(self._j(url))

    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        if not ids:
            return {"list": []}
        vid = str(ids[0])
        if not vid.isdigit():
            vid = vid.split("_")[0]
        if not vid.isdigit():
            return {"list": []}
        n1 = int(vid) // 1000000 * 1000000
        n2 = int(vid) // 1000 * 1000
        data = self._j(HOST + "/api/json/video/86400/%d/%d/%s.json" % (n1, n2, vid))
        v = data.get("video") or {}
        if not v.get("video_id"):
            return {"list": []}
        return {"list": [self._to_vod(v, detail=True)]}

    def _search(self, key, pg):
        url = HOST + "/api/videos2.php?params=86400/str/relevance/60/search..%d.all....&s=%s" % (pg, quote(key))
        return self._list_resp(self._j(url))

    def searchContent(self, key, quick, pg="1"):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        return self._search(key, pg)

    def action(self, action):
        return {"msg": "不支持此操作"}

    def playerContent(self, flag, id, vipFlags):
        sid = str(id)
        vid = ""
        m = re.search(r"/(\d+)\.mp4/", sid)
        if m:
            vid = m.group(1)
        elif sid.isdigit():
            vid = sid
        if vid:
            urls = self._play_urls(vid)
            if urls:
                flat = []
                for l, u in urls:
                    flat.append(l)
                    flat.append(u)
                return {"parse": 0, "url": flat}
        if sid.startswith("http"):
            return {"parse": 0, "url": sid}
        return {"parse": 1, "url": ""}
