#!/usr/bin/env python3
"""实验3：用 ground truth 标定指纹与阈值。

正样本：77 组派生副本（同 base name）之间的所有配对 —— 必须被判为重复
负样本：随机配对里「时间相隔 > 6 小时 且 base name 不同」的配对 —— 绝不能被判为重复
目标：找到能完全分开正负样本的 (指纹, 阈值)。
"""
import json, os, random, re, sys, time
from datetime import datetime
from PIL import Image

CACHE = "/tmp/dedupe-lab/previews.json"
random.seed(7)


def parse_dt(v):
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v))
        return d.replace(tzinfo=None) if d.tzinfo else d
    except ValueError:
        return None


def base_key(name):
    stem = name.rsplit(".", 1)[0]
    for _ in range(3):
        stem = re.sub(r"-\d+$", "", stem)
        stem = re.sub(r"-(已增强|降噪|编辑|副本|copy|Enhanced|NR)$", "", stem, flags=re.I)
    return stem


def pick_preview(entry, target_px):
    cands = entry["previews"]
    if not cands:
        return None
    return min(cands, key=lambda c: (abs(c["px"] - target_px), -c["px"]))["p"]


def dhash(path, hash_size):
    try:
        with Image.open(path) as img:
            img = img.convert("L").resize((hash_size + 1, hash_size), Image.LANCZOS)
            px = list(img.getdata())
    except Exception:
        return None
    bits = 0
    for r in range(hash_size):
        row = r * (hash_size + 1)
        for c in range(hash_size):
            bits = (bits << 1) | (1 if px[row + c] < px[row + c + 1] else 0)
    return bits


def ham(a, b):
    return bin(a ^ b).count("1")


def main():
    entries = json.load(open(CACHE))
    by_name = {e["name"]: e for e in entries}

    # 正样本
    gt = json.load(open("/tmp/dedupe-lab/gt_derived.json"))
    pos = []
    for base, names in gt.items():
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                pos.append((names[i], names[j]))
    # 负样本
    names_all = [e["name"] for e in entries if e["previews"]]
    neg = []
    tries = 0
    while len(neg) < 4000 and tries < 60000:
        tries += 1
        a, b = random.sample(names_all, 2)
        ta, tb = parse_dt(by_name[a]["cap"]), parse_dt(by_name[b]["cap"])
        if ta is None or tb is None:
            continue
        if abs((ta - tb).total_seconds()) < 6 * 3600:
            continue
        if base_key(a) == base_key(b):
            continue
        neg.append((a, b))
    print(f"正样本 {len(pos)} 对，负样本 {len(neg)} 对")

    for px in (696, 1392):
        print(f"\n########## 预览 {px}px ##########")
        cache = {}
        for e in entries:
            p = pick_preview(e, px)
            if p:
                cache[e["name"]] = p
        for hs in (8, 12, 16):
            t = time.time()
            hashes = {}
            for n, p in cache.items():
                hashes[n] = dhash(p, hs)
            dec = time.time() - t
            pd = [ham(hashes[a], hashes[b]) for a, b in pos if a in hashes and b in hashes]
            nd = [ham(hashes[a], hashes[b]) for a, b in neg if a in hashes and b in hashes]
            pd.sort(); nd.sort()
            nbits = hs * hs
            print(f"\n-- {hs}x{hs} ({nbits} bits) 解码全库 {dec:.1f}s ({dec/len(cache)*1000:.1f}ms/张)")
            print(f"   正样本距离: min={pd[0]} p50={pd[len(pd)//2]} p90={pd[int(len(pd)*0.9)]} max={pd[-1]}")
            print(f"   负样本距离: min={nd[0]} p1={nd[int(len(nd)*0.01)]} p50={nd[len(nd)//2]} max={nd[-1]}")
            # 找一个阈值：召回正样本 & 排除负样本
            best = None
            for th in range(0, nbits // 2):
                rec = sum(1 for d in pd if d <= th) / len(pd)
                fpr = sum(1 for d in nd if d <= th) / len(nd)
                if fpr == 0 and rec >= 0.95:
                    best = (th, rec, fpr)
                    break
            if best:
                print(f"   ✅ 阈值 dist<={best[0]}: 召回 {best[1]*100:.1f}% 负样本误判 {best[2]*100:.2f}%")
            else:
                # 报告最好的折中
                for th in range(0, nbits // 2):
                    rec = sum(1 for d in pd if d <= th) / len(pd)
                    if rec >= 0.95:
                        fpr = sum(1 for d in nd if d <= th) / len(nd)
                        print(f"   ⚠️ 召回95%需 dist<={th}，此时负样本误判 {fpr*100:.2f}% (不可接受)")
                        break


if __name__ == "__main__":
    main()
