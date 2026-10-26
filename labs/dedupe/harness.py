#!/usr/bin/env python3
"""实验底座：把「目录 → 预览路径」和「预览 → 指纹」两步缓存下来，
后续每轮算法实验直接读缓存，秒级迭代（原本每轮要 60s 扫盘 + 45s 解码）。"""
import json, os, re, sqlite3, sys, time
from datetime import datetime

CAT = "/Users/tristan/Downloads/Windows/ToMac/Lightroom Catalog.lrcat"
BASE = os.path.splitext(CAT)[0] + " Previews.lrdata"
CACHE = "/tmp/dedupe-lab/previews.json"

PREVIEW_SIZES = re.compile(r"_(\d+)$")


def load_photos(catalog=CAT):
    con = sqlite3.connect(f"file:{catalog}?mode=ro", uri=True, timeout=15)
    try:
        return con.execute(
            "SELECT f.idx_filename, f.id_global, i.captureTime "
            "FROM AgLibraryFile f JOIN Adobe_images i ON i.rootFile = f.id_local "
            "WHERE f.id_global IS NOT NULL").fetchall()
    finally:
        con.close()


def build_index():
    """一次遍历整个 lrdata，建 uuid -> [(path,size,mtime)] 索引（比逐张 glob 快几十倍）。"""
    idx = {}
    t = time.time()
    for root, dirs, files in os.walk(BASE):
        for fn in files:
            m = PREVIEW_SIZES.search(fn)
            if not m:
                continue
            uuid = fn[:36]
            idx.setdefault(uuid, []).append(
                (os.path.join(root, fn), int(m.group(1)), os.path.getmtime(os.path.join(root, fn))))
    print(f"索引 {len(idx)} 个 uuid，用时 {time.time()-t:.1f}s", file=sys.stderr)
    return idx


def main():
    rows = load_photos()
    idx = build_index()
    out = []
    for name, uuid, cap in rows:
        cands = idx.get(uuid) or []
        out.append({"name": name, "uuid": uuid, "cap": cap,
                    "previews": [{"p": p, "px": s, "mt": mt} for p, s, mt in cands]})
    miss = sum(1 for e in out if not e["previews"])
    print(f"照片 {len(out)}，无预览 {miss}", file=sys.stderr)
    with open(CACHE, "w") as fh:
        json.dump(out, fh)
    print(f"写入 {CACHE}", file=sys.stderr)


if __name__ == "__main__":
    main()
