#!/usr/bin/env python3
"""实验7：真实"完全重复"很难找 → 人工制造。

对同一预览做：JPEG 重压缩 q=85、缩放 95%、亮度 ±5%、轻微裁剪 2%，
构造确定性的"同图变体"正样本；负样本用不同场景图。
测每种描述子的可分性，选出 exact 档的最优组合。
"""
import json, io, os, random
import numpy as np
from PIL import Image, ImageEnhance

CACHE = "/tmp/dedupe-lab/previews.json"
random.seed(3)


def pick(entry, target=696):
    c = entry["previews"]
    return min(c, key=lambda x: (abs(x["px"] - target), -x["px"]))["p"]


def variants(im):
    """同图变体生成器"""
    out = {"orig": im.copy()}
    b = io.BytesIO(); im.save(b, "JPEG", quality=85); out["recompress"] = Image.open(b).convert("RGB")
    out["scale95"] = im.resize((int(im.width * .95), int(im.height * .95)), Image.LANCZOS)
    out["bright+5"] = ImageEnhance.Brightness(im).enhance(1.05)
    out["bright-5"] = ImageEnhance.Brightness(im).enhance(0.95)
    w, h = im.size; m = int(min(w, h) * 0.02)
    out["crop2%"] = im.crop((m, m, w - m, h - m))
    return out


def dhash8(path_or_img, hs=8):
    im = path_or_img if isinstance(path_or_img, Image.Image) else Image.open(path_or_img)
    a = np.asarray(im.convert("L").resize((hs + 1, hs), Image.LANCZOS), dtype=np.float32)
    bits = (a[:, :-1] < a[:, 1:]).flatten()
    v = 0
    for x in bits:
        v = (v << 1) | int(x)
    return v


def ham(a, b):
    return bin(int(a) ^ int(b)).count("1")


def hist64(im):
    a = np.asarray(im.resize((64, 64), Image.LANCZOS), dtype=np.float32)
    q = (a // 64).astype(np.int32)
    idx = q[:, :, 0] * 16 + q[:, :, 1] * 4 + q[:, :, 2]
    h = np.bincount(idx.flatten(), minlength=64).astype(np.float32)
    return h / h.sum()


def main():
    entries = [e for e in json.load(open(CACHE)) if e["previews"]]
    sample = random.sample(entries, 25)
    # 收集正样本（同图变体间）与负样本（不同图之间）
    pos8, neg8, posh, negh = [], [], [], []
    imgs = []
    for e in sample:
        try:
            im = Image.open(pick(e)).convert("RGB")
        except Exception:
            continue
        imgs.append(im)
    for im in imgs:
        vs = variants(im)
        keys = list(vs)
        h0 = dhash8(vs["orig"]); c0 = hist64(vs["orig"])
        for k in keys[1:]:
            pos8.append(ham(h0, dhash8(vs[k])))
            posh.append(np.abs(c0 - hist64(vs[k])).sum() / 2)
    for i in range(len(imgs)):
        for j in range(i + 1, len(imgs)):
            neg8.append(ham(dhash8(imgs[i]), dhash8(imgs[j])))
            negh.append(np.abs(hist64(imgs[i]) - hist64(imgs[j])).sum() / 2)
    pos8.sort(); posh.sort(); neg8.sort(); negh.sort()
    def st(a, tag):
        print(f"{tag:12s} min={a[0]:.3f} p50={a[len(a)//2]:.3f} p95={a[int(len(a)*.95)]:.3f} max={a[-1]:.3f}")
    print(f"正样本 {len(pos8)} 负样本 {len(neg8)}")
    st(pos8, "dHash8+"); st(neg8, "dHash8-")
    st(posh, "hist64+"); st(negh, "hist64-")
    # 找 hist 阈值：0 误判下最大召回
    for th in (0.05,0.08,0.10,0.12,0.15,0.20):
        rec = sum(1 for d in posh if d <= th)/len(posh)
        fpr = sum(1 for d in negh if d <= th)/len(negh)
        print(f"hist64 阈值 {th:.2f}: 召回 {rec*100:.0f}% 误判 {fpr*100:.2f}%")


if __name__ == "__main__":
    main()
