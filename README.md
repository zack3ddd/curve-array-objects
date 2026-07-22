<!-- 封面圖：在 GitHub 網頁編輯此檔，把封面圖拖到這一行上方，會自動上傳並產生 <img> 連結 -->

# CurveArrayObjects

**English** · [繁體中文](#繁體中文)

Distribute a single object, or an entire collection, along a curve. Drag the curve and everything follows in real time. No geometry nodes: pick a curve, press one button.

> Made by Zack3D (with AI assistance).

## How is this different from the built-in Array + Curve?

The built-in combo bends one continuous mesh along a curve. This add-on places individual objects onto the curve. You can cycle through or randomly pull from a whole collection, give each its own random offset, rotation and scale, and vary the spacing with the curve's thickness.

If bending is all you want, the Deform along curve slider does that too. The difference is that each object bends on its own, and keeps all the scatter abilities above.

## Features

- Array a single object or a whole collection along a curve (cycle / random pick, reproducible seed)
- **Live follow:** drag the curve, `Ctrl+T` tilt, `Alt+S` radius, and the array re-lays out, rotates and scales instantly
- **Deform along curve:** a 0→1 slider that bends each object to the curve's arc
- **Random scatter:** random offset / rotation / scale, reproducible seed
- **Spacing by curve size:** spacing follows the curve radius (wider where it's thick, tighter where it's thin)
- Count, object size, start/end range, align to curve direction (reversible), object spin
- Curve thickness (bevel), curve caps, show curve in front
- Generated objects are non-selectable by default; turn off "Auto update" to edit the array contents individually
- Modifiers on the source object sync automatically to the array; delete the curve and the array cleans up with it
- **Apply** = bake into independent objects; **Clear** = remove the array

## Installation

1. Download the latest `.zip` from **Releases** on the right (no need to unzip)
2. Open Blender → top menu **Edit › Preferences**
3. Click **Add-ons** on the left → **Install from Disk…** (top-right)
4. Select the `.zip` you downloaded → install
5. Tick the checkbox next to "CurveArrayObjects" to enable it

## Usage

1. Select a **curve** → N-panel "Curve Array" → press "Create Curve Array"
2. Set the object to array under "Select Object" (or use "Select Collection" to cycle / randomize a whole collection)
3. Adjust count, size, spacing, alignment, etc. → updates live
4. Enter edit mode and drag the curve, `Ctrl+T`, `Alt+S` → the array follows instantly

## Changelog

### v3.2

- **New "Deform along curve":** a 0→1 slider bends the object itself to the curve's arc; stacks with random scatter and weighted spacing
- **New "Reverse":** flips objects to face the other end of the curve (without turning them upside down)
- **Fixed flipping orientation:** direction is now computed with a parallel-transport frame, so vertical curve sections no longer flip
- **Fixed direction jitter on Bézier curves:** invalid tangents from overlapping segment joints are filtered out
- **Fixed cracks during deformation:** the direction frame is now interpolated continuously, no longer worsening with face count
- **Fixed NURBS curves following the control polygon:** the true curve is now evaluated directly
- **Fixed overlap at the ends of closed curves:** now divided around the loop
- **Deleting a curve** now clears its matching array as well

### v3.0

- Random scatter (offset / rotation / scale, reproducible seed); UI reorganized into collapsible sections

### v2.x

- Full rewrite to live curve following; support for whole collections and automatic modifier sync

## Compatibility

- Blender 4.3+ / 5.2 LTS

## License

Released under the **GNU GPL**. Author: Zack3D.

---

## 繁體中文

[English ↑](#curvearrayobjects)

# CurveArrayObjects（沿曲線陣列物件）

沿曲線把「一個物件」或「整個集合」分佈排列，拉動曲線就即時跟著變。不用碰幾何節點，選一條曲線按一顆按鈕就有。

> 由 Zack3D 製作（AI 協助）。

## 跟內建的 Array + Curve 有什麼不同？

內建那套是把一整條網格沿曲線扭彎；這個外掛是把一顆一顆獨立的物件擺到曲線上。可以輪流或隨機取用整個集合、每顆各自隨機旋轉位移，間距還能依曲線粗細變化。

如果你就是想要彎曲，「沿曲線變形」滑桿也做得到。差別在於它是每顆各自彎，同時保有上面那些散佈能力。

## 功能

- 沿曲線陣列單一物件或整個集合（輪流／隨機挑選，種子可重現）
- **即時跟隨**：拉曲線、`Ctrl+T` 傾斜、`Alt+S` 半徑，陣列即時重排／旋轉／縮放
- **沿曲線變形**：0→1 滑桿，讓每顆物件自己順著曲線弧度彎曲
- **隨機散佈**：隨機位移／旋轉／縮放，種子可重現
- **間距隨曲線大小**：依曲線半徑調整間距（大處大、小處小）
- 數量、物件大小、開始／結束範圍、對齊曲線方向（可反轉）、物件自轉
- 曲線粗細（bevel）、曲線封口、曲線顯示在前面
- 生成物件預設不可選取；關掉「自動更新」即可個別編輯陣列內容
- 來源物件的修改器會自動同步到陣列；刪掉曲線，陣列會一起收乾淨
- **套用**＝烘焙成獨立物件；**清除**移除陣列

## 安裝教學

1. 到本頁右側 **Releases** 下載最新的 `.zip`（不用解壓縮）
2. 打開 Blender → 上方選單 **編輯 (Edit) › 偏好設定 (Preferences)**
3. 左側點 **附加元件 (Add-ons)** → 右上角 **從磁碟安裝 (Install from Disk…)**
4. 選剛剛下載的 `.zip` → 安裝
5. 在清單中把「CurveArrayObjects」前面的**核取方塊打勾**啟用

## 使用

1. 選一條**曲線** → N 面板「曲線陣列」→ 按「創建曲線陣列」
2. 在「選擇物件」指定要陣列的物件（或「選擇集合」用整個集合輪流／隨機排列）
3. 調數量、大小、間距、對齊等 → 即時更新
4. 進編輯模式拉曲線、`Ctrl+T`、`Alt+S` → 陣列即時跟著變

## 版本更新

### v3.2

- **新增「沿曲線變形」**：0→1 滑桿，讓物件本身跟著曲線弧度彎曲，可與隨機散佈、間距加權疊加
- **新增「反轉」**：讓物件掉頭面向曲線的另一端（不會上下顛倒）
- **修正物件方向亂翻**：改用平行移動框架算方向，曲線走垂直時不再翻面
- **修正貝茲曲線的方向抖動**：濾掉每段接點重合造成的無效切線
- **修正變形時的裂縫**：方向框架改為連續內插，不再隨面數惡化
- **修正 NURBS 曲線跟隨到控制線**：改為自行求值真正的曲線
- **修正封閉曲線首尾重疊**：改用繞圈等分
- **刪除曲線時**，對應的陣列會一起清除

### v3.0

- 隨機散佈（位移／旋轉／縮放，種子可重現）；介面重整為分區可收合

### v2.x

- 全面重寫為即時跟隨曲線；支援整個集合、修改器自動同步

## 對應版本

- Blender 4.3 以上 / 5.2 LTS

## 授權

以 **GNU GPL** 釋出。作者：Zack3D。
