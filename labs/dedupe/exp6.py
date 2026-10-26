#!/usr/bin/env python3
"""实验6：V2 指纹。

教训（exp4/5）：全局 16x16 dHash 对"低结构图"（纯天空/海/黑帧）失去判别力。
V2 思路：
  1. 4x4=16 个区域，每区域 6x6 dHash（共 576bit）——保留空间排布信息，
     两张图必须"每个区域都像"才算重复。
  2. 每区域梯度能量（结构量）：低结构区域（天空/海/黑）的哈希是噪声，
     配对时按结构量加权——两个低结构区域即使哈希碰巧相近也不加分。
  3. 时间约束仍然保留：exact 候选需同一拍摄日（防跨场景长尾误并）。
组合分：S = Σ w_i * (1 - d_i/36) / Σ w_i，w_i = 区域结构量。
"""
import json, os, sys, time
import numpy as np
from PIL import Image

CACHE = "/tmp/dedupe-lab/previews.json"
PX = 696
GRID = 4          # 4x4 区域
PH = 6            # 每区域 dHash 6x6 => 36 bit


def pick(entry, target=PX):
    c = entry["previews"]
    return min(c, key=lambda x: (abs(x["px"] - target), -x["px"]))["p"]


def fingerprint(path):
    try:
        with Image.open(path) as im:
            g = np.asarray(im.convert("L").resize((192, 128), Image.LANCZOS), dtype=np.float32)
    except Exception:
        return None
    H, W = g.shape
    gh, gw = H // GRID, W // GRID
    bits = np.zeros((GRID, GRID, PH * PH), dtype=bool)
    energy = np.zeros((GRID, GRID), dtype=np.float32)
    for r in range(GRID):
        for c in range(GRID):
            patch = g[r * gh:(r + 1) * gh, c * gw:(c + 1) * gw]
            small = np.asarray(Image.fromarray(patch.astype(np.uint8)).resize((PH + 1, PH), Image.LANCZOS),
                               dtype=np.float32)
            bits[r, c] = (small[:, :-1] < small[:, 1:]).flatten()
            gx = np.abs(np.diff(patch, axis=1)).mean()
            gy = np.abs(np.diff(patch, axis=0)).mean()
            energy[r, c] = gx + gy
    return bits.reshape(GRID * GRID, PH * PH), energy.reshape(GRID * GRID)


def sim(fp_a, fp_b):
    ba, ea = fp_a
    bb, eb = fp_b
    d = (ba != bb).sum(axis=1).astype(np.float32)   # (16,) 每区域汉明距离
    w = np.minimum(ea, eb) + 1e-6                    # 任一方是天空/纯色 → 该区域不可信
    s = (1.0 - d / (PH * PH)) * w
    return float(s.sum() / w.sum())


def main():
    entries = json.load(open(CACHE))
    t0 = time.time()
    fps, names = [], []
    ENERGY_FLOOR = 3.0   # 全图平均梯度能量下限：低于此 = 空白/死黑帧，不参与配对
    for e in entries:
        if not e["previews"]:
            continue
        p = pick(e)
        if not p:
            continue
        fp = fingerprint(p)
        if fp is not None and fp[1].mean() >= ENERGY_FLOOR:
            fps.append(fp)
            names.append(e["name"])
    n = len(names)
    print(f"V2 指纹 {n} 张 用时 {time.time()-t0:.1f}s", file=sys.stderr)

    S = np.zeros((n, n), dtype=np.float32)
    for i in range(n):
        for j in range(i + 1, n):
            S[i, j] = S[j, i] = sim(fps[i], fps[j])
    print(f"相似度矩阵完成 {time.time()-t0:.1f}s", file=sys.stderr)

    for th in (0.80, 0.85, 0.88, 0.90):
        m = S >= th
        np.fill_diagonal(m, False)
        pairs = np.argwhere(np.triu(m))
        print(f"\n=== 阈值 {th}: 候选对 {len(pairs)} ===")
        for i, j in pairs[:50]:
            print(f"  {names[i]:24s} {names[j]:24s} S={S[i,j]:.4f}")
    np.save("/tmp/dedupe-lab/S2.npy", S)
    json.dump(names, open("/tmp/dedupe-lab/names2.json", "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
