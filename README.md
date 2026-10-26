# Lightroom Visual Duplicates

基于视觉的重复照片智能筛选插件 for Adobe Lightroom Classic（macOS）。

用感知哈希（dHash）对 Lightroom 预览缓存里的 JPEG 做指纹，两档分组（完全重复 / 连拍近似），再用 macOS Vision 离线分析每组里哪张最值得保留（锐度、人脸睁眼、美学评分、曝光溢出），最后把结果写回 Lightroom：建收藏夹 + 色标。**不删照片、不标 Reject，零破坏性。**

## 为什么需要它

Lightroom 自带的"查找重复照片"只做文件级比对（文件名/EXIF/字节），抓不到这几种真实场景：

- 同一张照片导入了两遍（不同文件名）
- 连拍的一组照片里，只该留表情最好/最锐的那一张
- 不同设备拍的同一场景（手机 + 相机）

这些都得**看图**才能判断——而 Lightroom 没有视觉比对能力。本插件补的就是这一层。

## 架构

```
tools/al-dedupe（Python）              Bridge.lua（Lightroom 插件）
  │                                       │
  │ 1. 读 catalog SQLite 拿照片列表        │ 4. 读 plan JSON
  │ 2. 从预览缓存取 LR 渲染的 JPEG          │    → 建 _Duplicates 收藏夹
  │ 3. dHash → 两档分组 → al-vision 选最佳  │    → 最佳标绿色 其余标黄色
  │ → 写 /tmp/al-dedupe-plan.json          │ → 不碰 pickStatus
  └─────────────────────────────────────→ ┘
              bridge/server.js（Node，127.0.0.1:8765）
                 插件每 1s GET /next 取命令，执行后 GET /result 回报
```

**为什么不在 Lua 插件里算指纹？** Lightroom SDK 里 `os.execute` 不存在、`LrFileUtils.writeFile` 为 nil，插件拿不到像素也调不动本机程序。所以视觉哈希交给本机 Python，插件只做它擅长且已验证的事：写回收藏夹和色标。预览缓存本身就是 Lightroom 渲染的 JPEG（含 develop 设定），天然满足"预览必须是修图后的样子"。

## 依赖

| 依赖 | 版本 | 用途 |
|---|---|---|
| [Pillow](https://python-pillow.org/) | ≥10.0 | JPEG 解码 + 缩放 → dHash 指纹 |
| macOS Vision 框架 | macOS 12+ | 人脸检测 / 睁眼 / 美学评分 / 显著主体（通过 `tools/al-vision`） |
| Node.js | ≥18 | bridge 服务（命令队列中转） |
| Adobe Lightroom Classic | 15.x | 插件宿主 |

Python 标准库（`sqlite3` / `subprocess` / `argparse` / `json`）随系统自带，无需额外安装。

```bash
pip install Pillow
```

## 安装

1. **装插件**

   把 `Agent Lightroom Bridge.lrplugin` 目录放进 Lightroom 的增效工具目录，或通过 Plug-in Manager → 添加。

2. **装 bridge 服务**

   ```bash
   cd /path/to/Lightroom-Duplicated
   node bridge/server.js &
   ```

3. **启动插件轮询**

   在 Lightroom 里：`文件 → 增效工具额外信息 → Agent Lightroom - Start Bridge`

   验证：
   ```bash
   curl -s http://127.0.0.1:8765/health
   # connected: true 说明插件轮询已启动
   ```

## 用法

### 基本流程（推荐：一条命令跑完）

```bash
# 扫描 → 写回 Lightroom → 自动验收（组数/标色数不一致会报错）
tools/al-dedupe-run

# 指定目录
tools/al-dedupe-run --catalog "/path/to/Catalog.lrcat"

# 只看结果不写回
tools/al-dedupe-run --skip-writeback
```

### 分步流程（需要细调时）

```bash
# 1. 扫描，生成去重计划 + 人类可读报告
tools/al-dedupe --report

# 2. 写回 Lightroom（建收藏夹 + 色标）
tools/al-cmd '{"type":"dedupe"}'
```

完成后在 Lightroom 里：
- 左侧面板出现 **`_Duplicates`** 收藏夹，包含所有重复组的照片
- 每组最佳 = **绿色色标**（保留）
- 其余 = **黄色色标**（重复候选，你去看看要不要删）
- 没有任何照片被标 Reject

### 参数

```bash
tools/al-dedupe [选项]

  --catalog PATH         指定 .lrcat（默认自动检测 Lightroom 当前打开的）
  --collection NAME      收藏夹名称（默认 _Duplicates）
  --burst-window SEC     连拍相邻间隔，秒（默认 15）
  --group-span-h H       exact 组内最大时间跨度，小时（默认 6，防跨场景误并）
  --path-map MAP         Windows 盘符映射，如 'G:/=/Volumes/G/'
                         （也可设 AL_DEDUPE_PATH_MAP 环境变量）
  --report               额外写人类可读报告到 /tmp/al-dedupe-report.txt
  --no-cache             禁用指纹缓存（默认启用，命中时全库扫描 5 秒）
  --limit N              只处理前 N 张（调试）
  --no-vision            跳过 al-vision 选最佳（只用分辨率，秒级完成）

判定阈值（由 labs/dedupe 实验标定，勿随意改）：
  exact   hist64 L1/2 ≤ 0.12 且 dHash8 ≤ 8   （synthetic 变体：召回98%，误判0%）
  burst   两级：
          L1 结构加权 4x4 区域哈希 sim ≥ 0.55 且时间连续（间隔≤15s，段≤60s）
          L2 合成分 = 0.5×哈希sim + 0.5×语义一致度(al-vision 标签) ≥ 0.63
             纯哈希精度仅 23%（≈抛硬币），加语义后 ~67%
             语义不能一票否决——Vision 会误判场景，高 sim 需能兜住
  门控   梯度能量 ≥ 3.0（排除纯天空/死黑等"黑洞"帧）

注意：
  - --no-vision 时两级校验降级为纯哈希（stats.verify_mode=hash-only，如实标注）
  - G:/ 等未挂载盘需 --path-map 映射，否则写回退化为按文件名定位，
    遇重名可能标错（脚本会告警并列出重名风险）
  --dry-run              只打印计划，不写文件
```

### 阈值调优

| 场景 | 推荐参数 | 说明 |
|---|---|---|
| 只抓完全重复（最保守） | `--burst-max 0` | 只判 distance ≤ 4 的完全重复，零误判 |
| 正常连拍选片 | 默认 | exact ≤ 4 + burst ≤ 12 且时间 ≤ 15s |
| 放宽连拍窗口 | `--burst-window 60` | 拍摄间隔大的连拍组也能抓到 |
| 快速预览（不选最佳） | `--no-vision` | 跳过 Vision 分析，按分辨率排序选最佳 |

## 两档判定原理

### 感知哈希：dHash（64-bit）

把照片缩放到 9×8 灰度，逐行比较相邻像素大小 → 64 个 bit。对缩放、JPEG 再压缩、轻微曝光变化稳健，这正是"重复导入 + 连拍"要容忍的差异。

### 完全重复（exact）

汉明距离 ≤ 4（64 bit）。同一张图的多个副本 / 重复导入，几乎零误判。不看拍摄时间（重复导入可能时间不同）。

### 连拍近似（burst）

汉明距离 ≤ 12 **且** 拍摄时间相邻 ≤ 15 秒。时间邻近做交叉验证——单靠宽松阈值会把"同一面墙拍的不同照片"误并，加上时间约束就稳了。

## 选最佳

每组重复里选出最值得保留的那一张，用 [`tools/al-vision`](tools/al-vision.swift)（macOS Vision 框架，离线、免费、无隐私外泄）对每张照片做视觉度量：

| 指标 | 来源 | 权重 |
|---|---|---|
| 人脸锐度 | Vision 人脸区域 Laplacian 方差 | ×1.2 |
| 睁眼 | Vision 人脸关键点 EAR 比值 | ×1.5（闭眼硬扣） |
| 整图锐度 | CoreImage Laplacian 方差 | ×1.0 |
| 美学评分 | Vision `VNCalculateImageAestheticsScoresRequest`（macOS 15+） | ×0.8 |
| 曝光溢出 | 高光 / 死黑像素占比 | −1.0（惩罚） |

数值参数由确定性规则给出，可解释、可复现，不靠模型编数。`reason` 字段会写明为什么选这张。

## 真机验证

2026.9 目录（49 张照片，尼康 D500 DNG + JPG 混合）：

```
目录: 2026.9.lrcat  照片 49  有预览 49  无预览 0
指纹完成 49 张  (0.6s)
分组: 4 组（完全重复 2，连拍 2）
  [exact] 2张 sim=0.94 保留 WYL_4461.JPG   锐度503 人脸1全睁眼 美学0.64
  [exact] 2张 sim=1.00 保留 IMG_1415.JPG    锐度2127 人脸1全睁眼
  [burst] 2张 sim=0.88 保留 TSY_7822.dng    锐度336 人脸3闭眼2 溢出16.3%
  [burst] 2张 sim=0.86 保留 TSY_7834.dng    锐度349 人脸1全睁眼 美学0.63
→ 写回：groups=4 in collection=_Duplicates added=8 labels=8
→ 目录色标：绿色×4（最佳）+ 黄色×4（重复候选）+ 无色标×41
```

- `IMG_1415.JPG` 与 `IMG_1415-2.JPG`：distance = 0（完全重复，重复导入）
- `TSY_7834` 锐度略低于 `TSY_7833`（349 vs 363）但美学分更高（0.63 vs 0.60）→ 被选为最佳

## 技术约束（实测，勿再假设）

本机 Lightroom Classic 15.5 SDK 实测结果：

| API | 状态 |
|---|---|
| `os.execute` / `io.popen` | **不存在** |
| `LrFileUtils.writeFile` | **nil** |
| `catalog.exportJpeg` | **nil** |
| `photo.requestJpegThumbnail`（同步） | 返回空（169 张全失败） |
| `photo:setRawMetadata('pickStatus', N)` | ✅ 可用 |
| `photo:setRawMetadata('colorNameForLabel', 'green')` | ✅ 可用 |
| `catalog:createCollection(name, nil, true)` | ✅ 可用 |
| `catalog:addPhoto(path)` | ✅ 可用 |
| `io.open` | ✅ 可用 |

这些约束决定了架构：插件不能做像素计算，只能做写回。

## 文件清单

| 文件 | 作用 |
|---|---|
| `tools/al-dedupe` | 视觉去重引擎（Python）：dHash + 两档分组 + al-vision 选最佳 |
| `tools/al-vision.swift` | macOS Vision 视觉度量（Swift，需编译为 `tools/al-vision`） |
| `tools/al-cmd` | 命令行客户端：往 bridge 发命令并等结果 |
| `bridge/server.js` | bridge 服务（Node）：命令队列 + 状态中转 |
| `Agent Lightroom Bridge.lrplugin/` | Lightroom 插件（Lua）：轮询 bridge + 执行写回 |

## 上游库

- [Pillow](https://github.com/python-pillow/Pillow) — JPEG 解码与图像缩放
- [macOS Vision](https://developer.apple.com/documentation/vision) — 人脸检测、美学评分、显著主体（Apple 系统框架，无需安装）
- [Node.js](https://nodejs.org/) — bridge 服务运行时

## 许可证

Apache License 2.0
