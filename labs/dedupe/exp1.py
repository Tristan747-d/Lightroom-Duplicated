#!/usr/bin/env python3
"""实验1：指纹判别力。对比 8x8 / 12x12 / 16x16 dHash 在不同预览尺寸下
对「真重复」与「误并样本」的区分能力。"""
import json, os, sys, time
from PIL import Image

CACHE = "/tmp/dedupe-lab/previews.json"


def pick_preview(entry, target_px):
    """取最接近 target_px 的预览；没有就取最大的。"""
    cands = entry["previews"]
    if not cands:
        return None
    best = min(cands, key=lambda c: (abs(c["px"] - target_px), -c["px"]))
    return best["p"]


def dhash(path, hash_size, box_frac=1.0):
    try:
        with Image.open(path) as img:
            img = img.convert("L")
            if box_frac < 1.0:
                w, h = img.size
                m = int(min(w, h) * (1 - box_frac) / 2)
                img = img.crop((m, m, w - m, h - m))
            img = img.resize((hash_size + 1, hash_size), Image.LANCZOS)
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

    # 误并样本：跨 16 小时、明显不同场景，却被 8x8 dHash 判成 exact
    false_group = ["_TSY5132-2.JPG", "DSC_0218-2.JPG", "DSC_0301-2.JPG", "DSC_0491-2.JPG"]
    # 真重复样本：上一轮被正确判为 exact 的对
    true_pairs = [("DSC_0028-2.NEF", "DSC_0165-2.JPG"),
                  ("_TSY7457.JPG", "_TSY7458.JPG")]

    for px in (696, 1392):
        print(f"\n=== 预览目标尺寸 {px}px ===")
        for hs in (8, 12, 16):
            t = time.time()
            names = false_group + [n for p in true_pairs for n in p]
            hashes = {}
            for n in names:
                p = pick_preview(by_name[n], px)
                hashes[n] = dhash(p, hs)
            el = time.time() - t
            print(f"-- dHash {hs}x{hs} ({hs*hs} bits) 解码{el*1000:.0f}ms/张≈{el/len(names)*1000:.0f}ms")
            print("   [误并组] 距离矩阵:")
            for i in range(len(false_group)):
                for j in range(i + 1, len(false_group)):
                    a, b = false_group[i], false_group[j]
                    d = ham(hashes[a], hashes[b])
                    print(f"     {a:18s} {b:18s} dist={d:3d}  ratio={d/(hs*hs):.3f}")
            print("   [真重复对]:")
            for a, b in true_pairs:
                d = ham(hashes[a], hashes[b])
                print(f"     {a:18s} {b:18s} dist={d:3d}  ratio={d/(hs*hs):.3f}")


if __name__ == "__main__":
    main()
