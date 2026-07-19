bl_info = {
    "name": "CurveArrayObjects",
    "author": "Zack3D",
    "version": (3, 3, 1),
    "blender": (4, 3, 0),
    "location": "View3D > N-panel > Curve Array",
    "description": "Array objects or a whole collection along a curve, following it live, with random scatter and deform-along-curve",
    "category": "Object",
}

import bpy
import bisect
import math
import random
from bpy.app.handlers import persistent
from bpy.props import (BoolProperty, IntProperty, FloatProperty,
                       FloatVectorProperty, PointerProperty)
from bpy.types import Operator, Panel, PropertyGroup
from mathutils import Vector, Euler, Matrix
from mathutils.geometry import interpolate_bezier


# ─────────────────────────────────────────────────────────────
# 介面翻譯（i18n）：UI 字串用英文當原文，附繁中譯文表，跟隨 Blender 語言。
#   英文介面 → 英文；繁中／簡中介面 → 都顯示繁體（不出簡體）。
# 掛在專屬翻譯 context（避免「Object」「Curve」等通用字被 Blender 內建翻譯蓋掉）。
# 繁中同時掛四代碼：zh_HANT/zh_TW（繁）、zh_HANS/zh_CN（簡也顯示繁）。
# ─────────────────────────────────────────────────────────────
I18N_CTX = "CurveArrayObjects"

_ZH = {
    # 屬性名稱
    "Object to Array": "選擇物件",
    "Collection": "選擇集合",
    "Random Pick": "隨機挑選",
    "Pick Seed": "隨機種子",
    "Scatter Seed": "隨機種子",
    "Count": "數量",
    "Object Size": "物件大小",
    "Spacing by Curve Size": "間距隨曲線大小",
    "Start": "開始位置",
    "End": "結束位置",
    "Align to Curve": "對齊曲線方向",
    "Flip": "反轉",
    "Deform Along Curve": "沿曲線變形",
    "Object Spin": "物件自轉",
    "Random Offset": "隨機位移",
    "Random Rotation": "隨機旋轉",
    "Random Scale": "隨機縮放",
    "Auto Update (follow curve)": "自動更新（跟隨曲線）",
    # 區塊標題（與部分屬性同字）
    "Source": "來源",
    "Layout": "排列",
    "Object": "物件",
    "Curve Look": "曲線外觀",
    "Random Scatter": "隨機散佈",
    # 面板內短標籤
    "Seed": "種子",
    "Curve Thickness": "曲線粗細",
    "Show in Front": "顯示在前面",
    "Curve Caps": "曲線封口",
    "Following Curve": "跟隨曲線中",
    "Unlocked · Editable": "已解鎖・可編輯",
    "Sync Modifiers": "同步修改器",
    "Clear": "清除",
    # 屬性說明（tooltip）
    "The object to array along the curve. Disabled when a collection is chosen below":
        "要沿曲線排列的物件。選了下面的集合時這裡會失效",
    "Array a whole collection instead: its objects are placed along the curve in turn (or at random)":
        "改用整個集合排列：裡面的物件會輪流（或隨機）沿曲線擺放",
    "Pick from the collection at random instead of cycling in order":
        "從集合裡隨機挑，而不是照順序輪流",
    "Change the number for a different set of which object is picked (does not affect random scatter)":
        "換數字＝換一組「從集合挑哪個物件」的組合（不影響隨機散佈）",
    "Change the number for a different random scatter result (does not affect the collection pick)":
        "換數字＝換一組隨機散佈結果（不影響集合的隨機挑選）",
    "How many objects to place along the curve": "沿曲線擺放幾個物件",
    "Overall scale of all objects (on top of the source object's own size)":
        "所有物件的整體縮放倍率（在來源物件自己的尺寸之上）",
    "Adjust spacing by curve radius (thickness). Positive = wider where the radius is large, "
    "tighter where small; negative = the opposite; 0 = even":
        "依曲線半徑(粗細)調整間距。正值＝半徑大處間距大、小處間距小；負值反之；0＝等距",
    "Where along the curve the array starts (0 = curve start, 1 = end)":
        "陣列從曲線的哪裡開始（0＝曲線起點、1＝終點）",
    "Where along the curve the array ends (0 = curve start, 1 = end)":
        "陣列到曲線的哪裡結束（0＝曲線起點、1＝終點）",
    "Make objects follow the curve's direction; turn off to keep the source object's original orientation":
        "讓物件順著曲線的走向擺；關掉則維持來源物件原本的朝向",
    "Turn objects to face the other end of the curve (without flipping them upside down)":
        "讓物件掉頭面向曲線的另一端（不會上下顛倒）",
    "0 = objects placed as-is; 1 = each object bends along the curve's arc. "
    "When on, each mesh is independent (the source's modifiers are baked in automatically)":
        "0＝物件保持原狀直接擺放；1＝物件本身跟著曲線弧度彎曲。"
        "開啟後每顆網格獨立（來源的修改器會自動烘進去，不再另外同步）",
    "After aligning to the curve, spin each object by a fixed angle":
        "在對齊曲線之後，再把每個物件轉一個固定角度",
    "Expand / collapse the random scatter settings": "展開／收合隨機散佈設定",
    "Range of random offset per object (±). X = along the curve, Y/Z = sideways":
        "每個物件隨機位移的範圍（±）。X＝沿曲線、Y/Z＝側向",
    "Range of random rotation per object (±)": "每個物件隨機旋轉的範圍（±）",
    "Amount of random scale per object (± ratio, 0.3 = ±30%)":
        "每個物件隨機縮放的幅度（±比例，0.3＝±30%）",
    "On = the array follows the curve live and its contents are locked (not selectable); "
    "Off = unlocked, edit individual objects in the array (no longer follows the curve)":
        "開啟＝拉動曲線時陣列即時跟隨，內容鎖定不可選取；關閉＝解鎖，可單獨編輯陣列裡的物件（此時不再跟隨曲線）",
    # 操作按鈕（label / 說明 / 回報）
    "Create Curve Array": "創建曲線陣列",
    "Create an array on this curve, then choose the object or collection to array above":
        "在這條曲線上建立陣列，接著在上方指定要排列的物件或集合",
    "Regenerate": "重新產生",
    "Rebuild the whole array. Use when the view didn't keep up, or to force a refresh after changing the source object":
        "整個重建陣列。畫面沒跟上、或改了來源物件後想強制刷新時用",
    "Sync Modifiers from Source": "與來源同步修改器",
    "Re-sync the source object's current modifier stack to every object in the array "
    "(overwrites per-object modifier tweaks)":
        "把來源物件目前的修改器堆疊重新同步到陣列裡的所有物件（會覆蓋你對個別物件的修改器調整）",
    "Synced modifiers on %d objects": "已同步 %d 個物件的修改器",
    "Apply": "套用",
    "Keep the current objects and stop following the curve (bake into independent, selectable objects)":
        "保留目前的物件、停止跟隨曲線（烘焙成獨立物件、解鎖可選）",
    "Applied (objects kept, no longer following)": "已套用（物件保留、停止跟隨）",
    "Clear Curve Array": "清除曲線陣列",
    "Delete all objects the array generated (the curve and source object are kept)":
        "刪除陣列產生的所有物件（曲線與來源物件都會保留）",
    # 面板／分頁
    "Curve Array": "曲線陣列",
    # 附加元件清單說明
    "Array objects or a whole collection along a curve, following it live, with random scatter and deform-along-curve":
        "沿曲線陣列複製物件或整個集合，可即時跟隨曲線，並支援隨機散佈與沿曲線變形",
}

_ZH_CTX = {(I18N_CTX, en): zh for en, zh in _ZH.items()}
# N 面板右側那條直立分頁（bl_category）由 Blender 用「預設 context」翻譯，不吃自訂 context，
# 所以「Curve Array」要再掛一份到預設 context（"*"），分頁標籤才會跟著變中文。
_ZH_CTX[("*", "Curve Array")] = "曲線陣列"
translations_dict = {"zh_HANT": _ZH_CTX, "zh_TW": _ZH_CTX,
                     "zh_HANS": _ZH_CTX, "zh_CN": _ZH_CTX}


def _t(msgid):
    """把英文原文翻成目前介面語言（英文介面回傳原文）。"""
    return bpy.app.translations.pgettext_iface(msgid, I18N_CTX)


# ─────────────────────────────────────────────────────────────
# 曲線 → polyline（世界座標，每點帶 tilt / radius）＋ 弧長取點
# ─────────────────────────────────────────────────────────────
def _nurbs_knots(n, order, cyclic, endpoint):
    """n＝控制點數（迴圈時已含尾端補點）。回傳 n+order 個節點。"""
    if cyclic or not endpoint:
        return [float(i) for i in range(n + order)]
    inner = [float(i) for i in range(1, n - order + 1)]
    return [0.0] * order + inner + [float(n - order + 1)] * order


def _nurbs_span(n, p, u, U):
    if u >= U[n]:
        return n - 1
    if u <= U[p]:
        return p
    lo, hi = p, n
    mid = (lo + hi) // 2
    while u < U[mid] or u >= U[mid + 1]:
        if u < U[mid]:
            hi = mid
        else:
            lo = mid
        mid = (lo + hi) // 2
    return mid


def _nurbs_basis(i, u, p, U):
    """Cox–de Boor：回傳該 span 上 p+1 個非零基底函數。"""
    N = [0.0] * (p + 1)
    left = [0.0] * (p + 1)
    right = [0.0] * (p + 1)
    N[0] = 1.0
    for j in range(1, p + 1):
        left[j] = u - U[i + 1 - j]
        right[j] = U[i + j] - u
        saved = 0.0
        for r in range(j):
            denom = right[r + 1] + left[j - r]
            temp = N[r] / denom if abs(denom) > 1e-12 else 0.0
            N[r] = saved + right[r + 1] * temp
            saved = left[j - r] * temp
        N[j] = saved
    return N


def _nurbs_polyline(spline, mw, res=16):
    """自己求值 NURBS（Blender 的 to_curve 不會求值，to_mesh 又會被 bevel 汙染）。"""
    cps = [(Vector(p.co[:3]), p.tilt, p.radius, p.co[3]) for p in spline.points]
    if len(cps) < 2:
        return []
    cyclic = spline.use_cyclic_u
    order = max(2, min(spline.order_u, len(cps)))
    if cyclic:
        cps = cps + cps[:order - 1]
    n = len(cps)
    if n < order:
        return []
    p = order - 1
    U = _nurbs_knots(n, order, cyclic, spline.use_endpoint_u)
    u0, u1 = U[p], U[n]
    if u1 - u0 <= 1e-9:
        return []

    segs = len(spline.points) if cyclic else len(spline.points) - 1
    steps = max(2, int(res * max(1, segs)))
    out = []
    for k in range(steps + 1):
        u = u0 + (u1 - u0) * k / steps
        if u > u1:
            u = u1
        i = _nurbs_span(n, p, u, U)
        N = _nurbs_basis(i, u, p, U)
        pos = Vector((0.0, 0.0, 0.0))
        tilt = rad = wsum = 0.0
        for j in range(order):
            cp = cps[i - p + j]
            nw = N[j] * cp[3]
            pos += cp[0] * nw
            tilt += cp[1] * nw
            rad += cp[2] * nw
            wsum += nw
        if abs(wsum) < 1e-12:
            continue
        out.append((mw @ (pos / wsum), tilt / wsum, rad / wsum))
    return out


def _first_polyline(curve_obj, res=16):
    mw = curve_obj.matrix_world
    for spline in curve_obj.data.splines:
        pts = []  # (world_pos, tilt, radius)
        cyclic = spline.use_cyclic_u
        if spline.type == 'BEZIER':
            bp = spline.bezier_points
            n = len(bp)
            if n < 2:
                continue
            segs = n if cyclic else n - 1
            for i in range(segs):
                a = bp[i]
                b = bp[(i + 1) % n]
                co = interpolate_bezier(a.co, a.handle_right, b.handle_left, b.co, res)
                for k, v in enumerate(co):
                    t = k / (res - 1) if res > 1 else 0.0
                    pts.append((mw @ v,
                                a.tilt + (b.tilt - a.tilt) * t,
                                a.radius + (b.radius - a.radius) * t))
        elif spline.type == 'NURBS':
            pts = _nurbs_polyline(spline, mw, res)
        else:
            for p in spline.points:
                pts.append((mw @ Vector(p.co[:3]), p.tilt, p.radius))
            if cyclic and len(pts) >= 2:
                pts.append(pts[0])          # 封閉：補回起點把迴圈接起來
        if len(pts) >= 2:
            return pts, cyclic
    return [], False


def _frames(poly, cyclic):
    """平行移動框架：沿曲線把「上方向」一路帶著走。每個「點」一組 (切線, 上方向)。

    不用世界軸當參考，所以曲線走垂直時不會退化翻面（to_track_quat 的老問題），
    而且扭轉量最小——跟 Blender 自己算曲線法線的原理相同。

    存在「點」上而不是「段」上，是為了讓 _at 能連續內插：段常數的框架會在段與段
    之間跳一下，位置連續、方向不連續 → 變形時跨在交界上的頂點會被甩開，物件面數
    一多就在轉彎處裂開。
    """
    n = len(poly)
    if n < 2:
        return []
    pts = [p[0] for p in poly]
    m = n - 1 if cyclic else n          # 封閉時最後一點與第一點重合

    tans = []
    for i in range(n):
        if cyclic:
            a, b = pts[(i - 1) % m], pts[(i + 1) % m]
        else:
            a, b = pts[max(0, i - 1)], pts[min(n - 1, i + 1)]
        t = b - a
        tans.append(t.normalized() if t.length > 1e-12 else Vector((1.0, 0.0, 0.0)))

    up = Vector((0.0, 0.0, 1.0))
    if abs(tans[0].dot(up)) > 0.99:     # 起點就垂直 → 換一個參考軸
        up = Vector((1.0, 0.0, 0.0))
    v = up - tans[0] * up.dot(tans[0])
    nrms = [v.normalized() if v.length > 1e-9 else Vector((0.0, 0.0, 1.0))]
    for i in range(1, n):
        v = tans[i - 1].rotation_difference(tans[i]) @ nrms[-1]
        v = v - tans[i] * v.dot(tans[i])          # 重新正交化，避免累積漂移
        nrms.append(v.normalized() if v.length > 1e-9 else nrms[-1])

    if cyclic:
        # 繞一圈後上方向接不回起點 → 把落差平均分攤掉，否則接縫處會扭一下
        c = nrms[-1] - tans[0] * nrms[-1].dot(tans[0])
        if c.length > 1e-9:
            c.normalize()
            ang = nrms[0].angle(c)
            if tans[0].dot(nrms[0].cross(c)) > 0:
                ang = -ang
            for i in range(n):
                f = i / (n - 1)
                nrms[i] = (Matrix.Rotation(ang * f, 3, tans[i]) @ nrms[i]).normalized()
    return list(zip(tans, nrms))


def _curve_data(obj):
    poly, cyclic = _first_polyline(obj)
    if len(poly) < 2:
        return None
    # 濾掉幾乎重合的點：貝茲每段的接點會被前後兩段各加一次，因浮點誤差不會剛好相等
    # （相距 ~1e-7），拿這種線段算切線會得到數值垃圾 → 物件方向亂翻。用相對閾值才擋得住。
    step = max((poly[i + 1][0] - poly[i][0]).length for i in range(len(poly) - 1))
    eps = max(1e-9, step * 1e-3)
    clean = [poly[0]]
    for p in poly[1:]:
        if (p[0] - clean[-1][0]).length > eps:
            clean.append(p)
    poly = clean
    if len(poly) < 2:
        return None
    cum = [0.0]
    for i in range(1, len(poly)):
        cum.append(cum[-1] + (poly[i][0] - poly[i - 1][0]).length)
    return poly, cum, cum[-1], cyclic, _frames(poly, cyclic)


def _at(poly, cum, total, d, frames=None):
    d = max(0.0, min(total, d))
    j = bisect.bisect_right(cum, d) - 1
    j = max(0, min(j, len(poly) - 2))
    seg = cum[j + 1] - cum[j]
    lf = 0.0 if seg <= 0 else (d - cum[j]) / seg
    p0, p1 = poly[j], poly[j + 1]
    pos = p0[0].lerp(p1[0], lf)
    tilt = p0[1] + (p1[1] - p0[1]) * lf
    rad = p0[2] + (p1[2] - p0[2]) * lf

    if frames and j + 1 < len(frames):
        # 在兩個點的框架之間連續內插，方向才不會在段交界上跳（變形裂縫的來源）
        t0, n0 = frames[j]
        t1, n1 = frames[j + 1]
        tan = t0.lerp(t1, lf)
        tan = tan.normalized() if tan.length > 1e-9 else t0.copy()
        nrm = n0.lerp(n1, lf)
        nrm = nrm.normalized() if nrm.length > 1e-9 else n0.copy()
    else:
        tan = p1[0] - p0[0]
        if tan.length > 0:
            tan.normalize()
        nrm = None
    return pos, tan, tilt, rad, nrm


# ─────────────────────────────────────────────────────────────
# 來源物件
# ─────────────────────────────────────────────────────────────
def _sources(s):
    owner = s.id_data          # 這條曲線自己，絕不能當來源（會無限迴圈）
    if s.source_collection:
        objs = [o for o in s.source_collection.all_objects
                if not o.get("_curve_array_child") and o is not owner]
        if objs:
            return objs
    if s.target and s.target is not owner:
        return [s.target]
    return []


def _pick(s, sources, i):
    if len(sources) == 1:
        return sources[0]
    if s.random_pick:
        return random.Random(s.pick_seed * 100003 + i).choice(sources)
    return sources[i % len(sources)]


# ─────────────────────────────────────────────────────────────
# 排列點：等距，或依「曲線半徑(大小)」調整間距
# 回傳 [(pos, tan, tilt, rad, src_object), ...]
# ─────────────────────────────────────────────────────────────
def _placements(obj):
    s = obj.curve_array
    data = _curve_data(obj)
    if not data:
        return []
    poly, cum, total, cyclic, frames = data
    if total <= 0:
        return []
    sources = _sources(s)
    if not sources:
        return []
    count = s.count
    srcs = [_pick(s, sources, i) for i in range(count)]

    d0 = s.start * total
    d1 = s.end * total
    span = max(1e-6, d1 - d0)

    if count == 1:
        dists = [d0]
    else:
        # 封閉曲線且用整條時，尾＝頭：要用 count 等分（留一段繞回起點），否則首尾會重疊
        loop = cyclic and s.start <= 1e-6 and s.end >= 1.0 - 1e-6
        ngaps = count if loop else count - 1
        even = [d0 + span * i / ngaps for i in range(count)]
        w = s.spacing_by_size
        if abs(w) > 1e-6:
            radii = [_at(poly, cum, total, d, frames)[3] for d in even]
            mean_r = sum(radii) / len(radii)
            if abs(mean_r) < 1e-6:
                mean_r = 1.0
            raw = []
            for i in range(ngaps):
                a = radii[i]
                b = radii[(i + 1) % count]      # 迴圈時最後一段接回第一個
                rr = max(0.05, ((a + b) / 2.0) / mean_r)
                raw.append(rr ** w)             # w>0：半徑大處 → 間距大（正比）
            tot = sum(raw) or 1.0
            scale = span / tot
            dists = [d0]
            d = d0
            for st in raw[:count - 1]:          # 只擺 count 個點；迴圈的最後一段留空繞回
                d += st * scale
                dists.append(d)
        else:
            dists = even

    out = []
    for i, dd in enumerate(dists):
        pos, tan, tilt, rad, nrm = _at(poly, cum, total, dd, frames)
        out.append((pos, tan, tilt, rad, srcs[i], dd, nrm))
    return out


# ─────────────────────────────────────────────────────────────
# 產生 / 更新 / 清除
# ─────────────────────────────────────────────────────────────
_busy = False
_pending = set()        # 只重新定位（拉曲線用，維持順暢）
_pending_sync = set()   # 來源幾何/修改器變動 → 同步修改器＋定位


def _sync_modifiers(src, dup):
    """把來源物件的修改器堆疊同步到複製物件（讓外面改、裡面即時跟）。"""
    try:
        if [m.type for m in dup.modifiers] != [m.type for m in src.modifiers]:
            dup.modifiers.clear()
            for m in src.modifiers:
                dup.modifiers.new(m.name, m.type)
        for sm, dm in zip(src.modifiers, dup.modifiers):
            for prop in sm.bl_rna.properties:
                pid = prop.identifier
                if prop.is_readonly or pid in {'rna_type', 'type', 'name', 'is_active'}:
                    continue
                try:
                    setattr(dm, pid, getattr(sm, pid))
                except Exception:
                    pass
    except Exception:
        pass


def _ensure_collection(obj):
    s = obj.curve_array
    if s.collection is not None:
        s.collection["_ca_owned"] = True
        return s.collection
    coll = bpy.data.collections.new("曲線陣列_" + obj.name)
    coll["_ca_owned"] = True
    bpy.context.scene.collection.children.link(coll)
    s.collection = coll
    return coll


def _clear(coll):
    for o in list(coll.objects):
        me = o.data if o.get("_ca_deformed") else None    # 變形模式的網格是獨立的，要一起收
        bpy.data.objects.remove(o, do_unlink=True)
        if me is not None and me.users == 0:
            try:
                bpy.data.meshes.remove(me)
            except Exception:
                pass


def _orphan_collections():
    """曲線被刪掉後，留下來沒有主人的陣列集合。"""
    tagged = [c for c in bpy.data.collections if c.get("_ca_owned")]
    if not tagged:
        return []
    owned = set()
    for o in bpy.data.objects:
        if o.type == 'CURVE':
            s = getattr(o, 'curve_array', None)
            if s and s.collection:
                owned.add(s.collection.name)
    return [c for c in tagged if c.name not in owned]


def _purge_orphans():
    for coll in _orphan_collections():
        _clear(coll)
        try:
            bpy.data.collections.remove(coll)
        except Exception:
            pass


def _frame(tan, tilt, align, nrm=None, flip=False):
    """曲線的區域座標框（X＝沿線方向、Z＝上方向、Y＝側向），含 Ctrl+T 傾斜。

    flip＝繞上方向轉 180°：物件掉頭面向另一端，但不會上下顛倒。
    """
    if align and tan.length > 0:
        if nrm is not None:
            z = nrm - tan * nrm.dot(tan)
            if z.length > 1e-9:
                z.normalize()
                y = z.cross(tan)
                mat = Matrix(((tan.x, y.x, z.x),
                              (tan.y, y.y, z.y),
                              (tan.z, y.z, z.z)))
                mat = mat @ Matrix.Rotation(tilt, 3, 'X')
                return mat @ Matrix.Rotation(math.pi, 3, 'Z') if flip else mat
        mat = tan.to_track_quat('X', 'Z').to_matrix() @ Matrix.Rotation(tilt, 3, 'X')
        return mat @ Matrix.Rotation(math.pi, 3, 'Z') if flip else mat
    mat = Matrix.Rotation(tilt, 3, 'Z') if tilt else Matrix.Identity(3)
    return mat @ Matrix.Rotation(math.pi, 3, 'Z') if flip else mat


def _at_ext(poly, cum, total, d, frames=None, cyclic=False):
    """超出曲線範圍時：封閉曲線繞回去，開放曲線沿切線外推（否則會被壓扁在端點）。"""
    if cyclic and total > 1e-9:
        d = d % total
    if d < 0.0:
        pos, tan, tilt, rad, nrm = _at(poly, cum, total, 0.0, frames)
        return pos + tan * d, tan, tilt, rad, nrm
    if d > total:
        pos, tan, tilt, rad, nrm = _at(poly, cum, total, total, frames)
        return pos + tan * (d - total), tan, tilt, rad, nrm
    return _at(poly, cum, total, d, frames)


def _base_meshes(dg, srcs):
    """每個來源取一份「修改器已套用」的網格當模板（一次更新只算一次）。"""
    out = {}
    for src in set(srcs):
        if src.type != 'MESH':
            continue
        try:
            out[src.name] = bpy.data.meshes.new_from_object(src.evaluated_get(dg))
        except Exception:
            pass
    return out


def _apply_transforms(obj, dups, items):
    s = obj.curve_array
    off = Euler((s.rot_offset[0], s.rot_offset[1], s.rot_offset[2]), 'XYZ').to_matrix()
    use_rand = (any(abs(v) > 1e-6 for v in s.rand_loc)
                or any(abs(v) > 1e-6 for v in s.rand_rot)
                or s.rand_scale > 1e-6)

    # ── 變形模式：把每顆網格自己沿曲線彎過去（滑桿＝0 時完全不走這條路）
    df = s.deform
    bases = {}
    cdata = None
    if df > 1e-6:
        cdata = _curve_data(obj)
        if cdata:
            dg = bpy.context.evaluated_depsgraph_get()
            bases = _base_meshes(dg, [it[4] for it in items])

    for idx, (dup, item) in enumerate(zip(dups, items)):
        pos, tan, tilt, rad, _src_ref, di, nrm = item
        src = bpy.data.objects.get(dup.get("_ca_src", ""))
        src_rot = src.rotation_euler.to_matrix() if src else Matrix.Identity(3)
        src_scale = Vector(src.scale) if src else Vector((1.0, 1.0, 1.0))

        rmat = _frame(tan, tilt, s.align, nrm, s.flip)

        m = s.size * rad          # 全域大小 × 曲線半徑(Alt+S)
        loc = pos.copy()
        rnd = Matrix.Identity(3)
        ofs = Vector((0.0, 0.0, 0.0))

        if use_rand:
            # 依種子＋序號產生：結果可重現，不會每次刷新就亂跳
            rng = random.Random(s.seed * 7919 + idx)
            ofs = Vector((rng.uniform(-s.rand_loc[0], s.rand_loc[0]),
                          rng.uniform(-s.rand_loc[1], s.rand_loc[1]),
                          rng.uniform(-s.rand_loc[2], s.rand_loc[2])))
            if ofs.length > 0:
                loc = loc + (rmat @ ofs)          # 位移在曲線的區域座標
            rnd = Euler((rng.uniform(-s.rand_rot[0], s.rand_rot[0]),
                         rng.uniform(-s.rand_rot[1], s.rand_rot[1]),
                         rng.uniform(-s.rand_rot[2], s.rand_rot[2])), 'XYZ').to_matrix()
            if s.rand_scale > 1e-6:
                m *= 1.0 + rng.uniform(-s.rand_scale, s.rand_scale)

        base = bases.get(src.name) if (src and cdata) else None
        if base is not None:
            _deform_dup(dup, base, cdata, s, di,
                        (src_rot @ off @ rnd), Vector((src_scale.x * m,
                                                       src_scale.y * m,
                                                       src_scale.z * m)),
                        ofs, pos, rmat, df)
            continue

        dup.location = loc
        dup.scale = (src_scale.x * m, src_scale.y * m, src_scale.z * m)
        dup.rotation_euler = (rmat @ src_rot @ off @ rnd).to_euler()

    for me in bases.values():                     # 模板用完就丟，不留孤兒資料
        try:
            bpy.data.meshes.remove(me)
        except Exception:
            pass


def _deform_dup(dup, base, cdata, s, di, rot3, scale, ofs, pos0, rmat0, df):
    """把 base 的每個頂點依它在曲線上的落點重新擺放，再與「不變形」的結果混合。"""
    poly, cum, total, cyc, frames = cdata
    sgn = -1.0 if s.flip else 1.0
    n = len(base.vertices)
    if len(dup.data.vertices) != n or not dup.get("_ca_deformed"):
        old = dup.data
        dup.data = base.copy()
        dup["_ca_deformed"] = 1
        dup.modifiers.clear()                     # 修改器已烘進網格，不能再套一次
        if old and old.users == 0:
            try:
                bpy.data.meshes.remove(old)
            except Exception:
                pass

    src_co = [0.0] * (n * 3)
    base.vertices.foreach_get("co", src_co)
    out = [0.0] * (n * 3)
    for i in range(n):
        v = Vector((src_co[i * 3], src_co[i * 3 + 1], src_co[i * 3 + 2]))
        p = rot3 @ Vector((v.x * scale.x, v.y * scale.y, v.z * scale.z)) + ofs
        rigid = pos0 + rmat0 @ p
        # 反轉時物件的 +X 對到的是曲線的反方向，沿線位移也要跟著反號才不會對不上
        pos2, tan2, tilt2, _r2, nrm2 = _at_ext(poly, cum, total, di + sgn * p.x, frames, cyc)
        bent = pos2 + _frame(tan2, tilt2, s.align, nrm2, s.flip) @ Vector((0.0, p.y, p.z))
        w = rigid.lerp(bent, df)
        out[i * 3], out[i * 3 + 1], out[i * 3 + 2] = w.x, w.y, w.z

    dup.data.vertices.foreach_set("co", out)
    dup.data.update()
    dup.matrix_world = Matrix.Identity(4)         # 座標已經是世界空間


def _update_array(obj, rebuild=True, sync_mods=False):
    if obj is None or obj.type != 'CURVE':
        return
    s = obj.curve_array
    if not s.enabled or not s.auto_update:
        return
    coll = _ensure_collection(obj)
    items = _placements(obj)
    if not items:
        _clear(coll)
        return
    existing = list(coll.objects)
    # 變形模式的網格是獨立的、非變形是連結共用 → 兩者切換時一定要重建
    mode_changed = bool(existing) and bool(existing[0].get("_ca_deformed")) != (s.deform > 1e-6)
    need_rebuild = mode_changed or (rebuild and (len(existing) != len(items)
                                                 or s.source_collection is not None))
    if need_rebuild:
        _clear(coll)
        existing = []
        for (pos, tan, tilt, rad, src, dd, nrm) in items:
            dup = src.copy()          # 連結複製：共用網格資料、並帶當下的修改器堆疊
            dup["_curve_array_child"] = 1
            dup["_ca_src"] = src.name
            dup.hide_select = True
            coll.objects.link(dup)
            existing.append(dup)
    elif sync_mods:
        for dup in existing:
            if dup.get("_ca_deformed"):
                continue              # 變形模式的修改器已烘進網格，每次更新自動重取
            src = bpy.data.objects.get(dup.get("_ca_src", ""))
            if src:
                _sync_modifiers(src, dup)
    _apply_transforms(obj, existing, items)


# ─────────────────────────────────────────────────────────────
# 即時更新
# ─────────────────────────────────────────────────────────────
def _ok(obj):
    return obj and obj.type == 'CURVE' and obj.curve_array.enabled and obj.curve_array.auto_update


def _process_pending():
    global _busy
    sync_names = set(_pending_sync)
    move_names = set(_pending) - sync_names
    _pending_sync.clear()
    _pending.clear()
    _busy = True
    try:
        for name in sync_names:                       # 原件幾何/修改器變了 → 同步修改器＋定位
            obj = bpy.data.objects.get(name)
            if _ok(obj):
                _update_array(obj, rebuild=False, sync_mods=True)
        for name in move_names:                       # 只是拉曲線/搬原件 → 只定位（快）
            obj = bpy.data.objects.get(name)
            if _ok(obj):
                _update_array(obj, rebuild=False, sync_mods=False)
        _purge_orphans()                              # 曲線被刪 → 陣列一起收掉（Ctrl+Z 可復原）
    finally:
        _busy = False
    return None


@persistent
def _depsgraph_handler(scene, depsgraph):
    if _busy:
        return
    any_ids = set()
    geo_ids = set()
    for u in depsgraph.updates:
        oid = u.id.original
        any_ids.add(oid)
        if getattr(u, 'is_updated_geometry', False):
            geo_ids.add(oid)

    hit = False
    for obj in scene.objects:
        if obj.type != 'CURVE':
            continue
        s = getattr(obj, 'curve_array', None)
        if not (s and s.enabled and s.auto_update and (s.target or s.source_collection)):
            continue
        dirty = obj.original in any_ids or (obj.data and obj.data.original in any_ids)
        src_geo = False
        for src in _sources(s):
            sdata = getattr(src, 'data', None)
            if src.original in geo_ids or (sdata and sdata.original in geo_ids):
                src_geo = True          # 原件的幾何/修改器變了
            if src.original in any_ids or (sdata and sdata.original in any_ids):
                dirty = True
        if src_geo:
            _pending_sync.add(obj.name)
            hit = True
        elif dirty:
            _pending.add(obj.name)
            hit = True
    if not hit and _orphan_collections():
        hit = True                      # 曲線被刪掉了 → 也要跑一次收尾
    if hit and not bpy.app.timers.is_registered(_process_pending):
        bpy.app.timers.register(_process_pending, first_interval=0.0)


# ─────────────────────────────────────────────────────────────
# 屬性
# ─────────────────────────────────────────────────────────────
def _prop_update(self, context):
    obj = self.id_data
    if obj and obj.type == 'CURVE' and self.enabled and self.auto_update:
        _update_array(obj, rebuild=True)


def _auto_update_toggle(self, context):
    obj = self.id_data
    if not obj or not self.collection:
        return
    for o in self.collection.objects:
        o.hide_select = self.auto_update
    if self.auto_update and obj.type == 'CURVE':
        _update_array(obj, rebuild=False)


def _target_poll(self, obj):
    if obj is self.id_data:        # 不能選這條曲線自己
        return False
    return obj.type in {'MESH', 'CURVE', 'FONT', 'SURFACE', 'META', 'EMPTY'} \
        and not obj.get("_curve_array_child")


class CurveArraySettings(PropertyGroup):
    enabled: BoolProperty(default=False)
    collection: PointerProperty(type=bpy.types.Collection)

    target: PointerProperty(name="Object to Array", type=bpy.types.Object,
                            description="The object to array along the curve. Disabled when a collection is chosen below",
                            translation_context=I18N_CTX,
                            poll=_target_poll, update=_prop_update)
    source_collection: PointerProperty(name="Collection", type=bpy.types.Collection,
                                       description="Array a whole collection instead: its objects are placed along the curve in turn (or at random)",
                                       translation_context=I18N_CTX,
                                       update=_prop_update)
    random_pick: BoolProperty(name="Random Pick", default=False,
                              description="Pick from the collection at random instead of cycling in order",
                              translation_context=I18N_CTX,
                              update=_prop_update)
    pick_seed: IntProperty(name="Pick Seed", default=0,
                           description="Change the number for a different set of which object is picked (does not affect random scatter)",
                           translation_context=I18N_CTX,
                           update=_prop_update)
    seed: IntProperty(name="Scatter Seed", default=0,
                      description="Change the number for a different random scatter result (does not affect the collection pick)",
                      translation_context=I18N_CTX,
                      update=_prop_update)

    count: IntProperty(name="Count", default=6, min=1, max=2000,
                       description="How many objects to place along the curve",
                       translation_context=I18N_CTX,
                       update=_prop_update)
    size: FloatProperty(name="Object Size", default=1.0, min=0.0,
                        description="Overall scale of all objects (on top of the source object's own size)",
                        translation_context=I18N_CTX,
                        update=_prop_update)
    spacing_by_size: FloatProperty(
        name="Spacing by Curve Size", default=0.0, min=-3.0, max=3.0,
        description="Adjust spacing by curve radius (thickness). Positive = wider where the radius is large, "
                    "tighter where small; negative = the opposite; 0 = even",
        translation_context=I18N_CTX,
        update=_prop_update)
    start: FloatProperty(name="Start", default=0.0, min=0.0, max=1.0,
                         description="Where along the curve the array starts (0 = curve start, 1 = end)",
                         translation_context=I18N_CTX,
                         update=_prop_update)
    end: FloatProperty(name="End", default=1.0, min=0.0, max=1.0,
                       description="Where along the curve the array ends (0 = curve start, 1 = end)",
                       translation_context=I18N_CTX,
                       update=_prop_update)
    align: BoolProperty(name="Align to Curve", default=True,
                        description="Make objects follow the curve's direction; turn off to keep the source object's original orientation",
                        translation_context=I18N_CTX,
                        update=_prop_update)
    flip: BoolProperty(name="Flip", default=False,
                       description="Turn objects to face the other end of the curve (without flipping them upside down)",
                       translation_context=I18N_CTX,
                       update=_prop_update)
    deform: FloatProperty(
        name="Deform Along Curve", default=0.0, min=0.0, max=1.0, subtype='FACTOR',
        description="0 = objects placed as-is; 1 = each object bends along the curve's arc. "
                    "When on, each mesh is independent (the source's modifiers are baked in automatically)",
        translation_context=I18N_CTX,
        update=_prop_update)
    rot_offset: FloatVectorProperty(name="Object Spin", subtype='EULER', size=3,
                                    description="After aligning to the curve, spin each object by a fixed angle",
                                    translation_context=I18N_CTX,
                                    default=(0.0, 0.0, 0.0), update=_prop_update)

    # 面板分區的收合狀態（純 UI）
    show_source: BoolProperty(name="Source", default=True, translation_context=I18N_CTX)
    show_layout: BoolProperty(name="Layout", default=True, translation_context=I18N_CTX)
    show_object: BoolProperty(name="Object", default=True, translation_context=I18N_CTX)
    show_curve: BoolProperty(name="Curve Look", default=False, translation_context=I18N_CTX)

    # 隨機散佈（用種子產生，可重現）
    show_random: BoolProperty(name="Random Scatter", default=False,
                              description="Expand / collapse the random scatter settings",
                              translation_context=I18N_CTX)
    rand_loc: FloatVectorProperty(name="Random Offset", subtype='TRANSLATION', size=3,
                                  default=(0.0, 0.0, 0.0), min=0.0,
                                  description="Range of random offset per object (±). X = along the curve, Y/Z = sideways",
                                  translation_context=I18N_CTX,
                                  update=_prop_update)
    rand_rot: FloatVectorProperty(name="Random Rotation", subtype='EULER', size=3,
                                  default=(0.0, 0.0, 0.0), min=0.0,
                                  description="Range of random rotation per object (±)",
                                  translation_context=I18N_CTX,
                                  update=_prop_update)
    rand_scale: FloatProperty(name="Random Scale", default=0.0, min=0.0, max=1.0,
                              description="Amount of random scale per object (± ratio, 0.3 = ±30%)",
                              translation_context=I18N_CTX,
                              update=_prop_update)

    auto_update: BoolProperty(name="Auto Update (follow curve)", default=True,
                              description="On = the array follows the curve live and its contents are locked (not selectable); "
                                          "Off = unlocked, edit individual objects in the array (no longer follows the curve)",
                              translation_context=I18N_CTX,
                              update=_auto_update_toggle)


# ─────────────────────────────────────────────────────────────
# Operators
# ─────────────────────────────────────────────────────────────
class CURVEARRAY_OT_create(Operator):
    bl_idname = "curvearray.create"
    bl_label = "Create Curve Array"
    bl_description = "Create an array on this curve, then choose the object or collection to array above"
    bl_translation_context = I18N_CTX

    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'CURVE'

    def execute(self, context):
        obj = context.object
        s = obj.curve_array
        s.enabled = True
        obj.show_in_front = True
        if not s.target and not s.source_collection:
            for o in context.selected_objects:
                if o is not obj and _target_poll(s, o):
                    s.target = o
                    break
        _update_array(obj, rebuild=True)
        return {'FINISHED'}


class CURVEARRAY_OT_update(Operator):
    bl_idname = "curvearray.update"
    bl_label = "Regenerate"
    bl_description = "Rebuild the whole array. Use when the view didn't keep up, or to force a refresh after changing the source object"
    bl_translation_context = I18N_CTX

    def execute(self, context):
        _update_array(context.object, rebuild=True)
        return {'FINISHED'}


class CURVEARRAY_OT_sync_mods(Operator):
    bl_idname = "curvearray.sync_mods"
    bl_label = "Sync Modifiers from Source"
    bl_description = ("Re-sync the source object's current modifier stack to every object in the array "
                     "(overwrites per-object modifier tweaks)")
    bl_translation_context = I18N_CTX

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'CURVE' and obj.curve_array.collection is not None

    def execute(self, context):
        s = context.object.curve_array
        n = 0
        for dup in s.collection.objects:
            src = bpy.data.objects.get(dup.get("_ca_src", ""))
            if src:
                _sync_modifiers(src, dup)
                n += 1
        self.report({'INFO'}, _t("Synced modifiers on %d objects") % n)
        return {'FINISHED'}


class CURVEARRAY_OT_apply(Operator):
    bl_idname = "curvearray.apply"
    bl_label = "Apply"
    bl_description = "Keep the current objects and stop following the curve (bake into independent, selectable objects)"
    bl_translation_context = I18N_CTX

    def execute(self, context):
        obj = context.object
        s = obj.curve_array
        if s.collection:
            for o in s.collection.objects:
                o.hide_select = False
        s.enabled = False
        s.collection = None
        obj.show_in_front = False
        self.report({'INFO'}, _t("Applied (objects kept, no longer following)"))
        return {'FINISHED'}


class CURVEARRAY_OT_clear(Operator):
    bl_idname = "curvearray.clear"
    bl_label = "Clear Curve Array"
    bl_description = "Delete all objects the array generated (the curve and source object are kept)"
    bl_translation_context = I18N_CTX

    def execute(self, context):
        obj = context.object
        s = obj.curve_array
        if s.collection:
            _clear(s.collection)
            try:
                bpy.data.collections.remove(s.collection)
            except Exception:
                pass
            s.collection = None
        s.enabled = False
        obj.show_in_front = False
        return {'FINISHED'}


# ─────────────────────────────────────────────────────────────
# 面板
# ─────────────────────────────────────────────────────────────
def _section(layout, s, prop, label, icon='NONE'):
    """畫一個可收合的深色區塊；展開時回傳 box 供填內容，收合時回傳 None。"""
    box = layout.box()
    head = box.row(align=True)
    head.prop(s, prop, text="", emboss=False,
              icon='TRIA_DOWN' if getattr(s, prop) else 'TRIA_RIGHT')
    head.label(text=_t(label), text_ctxt=I18N_CTX, icon=icon)
    return box if getattr(s, prop) else None


class CURVEARRAY_PT_panel(Panel):
    bl_label = "Curve Array"
    bl_idname = "VIEW3D_PT_curve_array_objects"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Curve Array'
    bl_translation_context = I18N_CTX

    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'CURVE'

    def draw(self, context):
        layout = self.layout
        obj = context.object
        s = obj.curve_array

        if not s.enabled:
            layout.operator("curvearray.create", icon='CURVE_DATA')
            return

        # ── 來源：要排什麼 ──
        b = _section(layout, s, "show_source", "Source", 'OBJECT_DATA')
        if b:
            row = b.row()
            row.enabled = not s.source_collection      # 有選集合時，物件欄變灰（集合優先）
            row.prop(s, "target")
            b.prop(s, "source_collection")
            if s.source_collection:
                r = b.row(align=True)
                r.prop(s, "random_pick")
                if s.random_pick:
                    r.prop(s, "pick_seed", text=_t("Seed"), text_ctxt=I18N_CTX)

        # ── 排列：排幾個、排在哪 ──
        b = _section(layout, s, "show_layout", "Layout", 'MOD_ARRAY')
        if b:
            b.prop(s, "count")
            b.prop(s, "spacing_by_size")
            row = b.row(align=True)
            row.prop(s, "start")
            row.prop(s, "end")
            rb = _section(b, s, "show_random", "Random Scatter", 'MOD_PARTICLES')
            if rb:
                rb.prop(s, "rand_loc")
                rb.prop(s, "rand_rot")
                rb.prop(s, "rand_scale")
                rb.prop(s, "seed")

        # ── 物件：排出來長怎樣 ──
        b = _section(layout, s, "show_object", "Object", 'MESH_DATA')
        if b:
            b.prop(s, "size")
            row = b.row(align=True)
            row.prop(s, "align")
            sub = row.row(align=True)
            sub.active = s.align          # 沒對齊曲線時就沒有方向可反轉
            sub.prop(s, "flip")
            b.prop(s, "deform", slider=True)
            b.prop(s, "rot_offset")

        # ── 曲線外觀：曲線自己的屬性（次要，預設收起）──
        b = _section(layout, s, "show_curve", "Curve Look", 'CURVE_DATA')
        if b:
            b.prop(obj.data, "bevel_depth", text=_t("Curve Thickness"), text_ctxt=I18N_CTX)
            row = b.row(align=True)
            row.prop(obj, "show_in_front", text=_t("Show in Front"), text_ctxt=I18N_CTX)
            row.prop(obj.data, "use_fill_caps", text=_t("Curve Caps"), text_ctxt=I18N_CTX)

        # ── 狀態：跟隨 or 解鎖編輯（狀態直接寫在按鈕上）──
        layout.separator()
        box = layout.box()
        r = box.row()
        r.scale_y = 1.3
        if s.auto_update:
            r.prop(s, "auto_update", toggle=True, icon='LOCKED',
                   text=_t("Following Curve"), text_ctxt=I18N_CTX)
        else:
            r.prop(s, "auto_update", toggle=True, icon='UNLOCKED',
                   text=_t("Unlocked · Editable"), text_ctxt=I18N_CTX)

        # ── 動作 ──
        layout.separator()
        acts = layout.column(align=True)
        row = acts.row(align=True)
        row.operator("curvearray.update", icon='FILE_REFRESH')
        row.operator("curvearray.sync_mods", text=_t("Sync Modifiers"),
                     text_ctxt=I18N_CTX, icon='MODIFIER')
        row = acts.row(align=True)
        row.operator("curvearray.apply", icon='CHECKMARK')
        row.operator("curvearray.clear", text=_t("Clear"), text_ctxt=I18N_CTX, icon='X')


classes = (
    CurveArraySettings,
    CURVEARRAY_OT_create,
    CURVEARRAY_OT_update,
    CURVEARRAY_OT_sync_mods,
    CURVEARRAY_OT_apply,
    CURVEARRAY_OT_clear,
    CURVEARRAY_PT_panel,
)


def register():
    bpy.app.translations.register(__name__, translations_dict)
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Object.curve_array = PointerProperty(type=CurveArraySettings)
    if _depsgraph_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_depsgraph_handler)


def unregister():
    if _depsgraph_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_depsgraph_handler)
    try:
        del bpy.types.Object.curve_array
    except Exception:
        pass
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    try:
        bpy.app.translations.unregister(__name__)
    except Exception:
        pass


if __name__ == "__main__":
    register()
