bl_info = {
    "name": "CurveArrayObjects",
    "author": "Zack3D",
    "version": (3, 0, 5),
    "blender": (4, 3, 0),
    "location": "View3D > N 面板 > 曲線陣列",
    "description": "沿曲線陣列複製物件或整個集合，可即時跟隨曲線",
    "category": "Object",
}

import bpy
import bisect
import random
from bpy.app.handlers import persistent
from bpy.props import (BoolProperty, IntProperty, FloatProperty,
                       FloatVectorProperty, PointerProperty)
from bpy.types import Operator, Panel, PropertyGroup
from mathutils import Vector, Euler, Matrix
from mathutils.geometry import interpolate_bezier


# ─────────────────────────────────────────────────────────────
# 曲線 → polyline（世界座標，每點帶 tilt / radius）＋ 弧長取點
# ─────────────────────────────────────────────────────────────
def _first_polyline(curve_obj, res=16):
    mw = curve_obj.matrix_world
    for spline in curve_obj.data.splines:
        pts = []  # (world_pos, tilt, radius)
        if spline.type == 'BEZIER':
            bp = spline.bezier_points
            n = len(bp)
            if n < 2:
                continue
            segs = n if spline.use_cyclic_u else n - 1
            for i in range(segs):
                a = bp[i]
                b = bp[(i + 1) % n]
                co = interpolate_bezier(a.co, a.handle_right, b.handle_left, b.co, res)
                for k, v in enumerate(co):
                    t = k / (res - 1) if res > 1 else 0.0
                    pts.append((mw @ v,
                                a.tilt + (b.tilt - a.tilt) * t,
                                a.radius + (b.radius - a.radius) * t))
        else:
            for p in spline.points:
                pts.append((mw @ Vector(p.co[:3]), p.tilt, p.radius))
        if len(pts) >= 2:
            return pts
    return []


def _curve_data(obj):
    poly = _first_polyline(obj)
    if len(poly) < 2:
        return None
    cum = [0.0]
    for i in range(1, len(poly)):
        cum.append(cum[-1] + (poly[i][0] - poly[i - 1][0]).length)
    return poly, cum, cum[-1]


def _at(poly, cum, total, d):
    d = max(0.0, min(total, d))
    j = bisect.bisect_right(cum, d) - 1
    j = max(0, min(j, len(poly) - 2))
    seg = cum[j + 1] - cum[j]
    lf = 0.0 if seg <= 0 else (d - cum[j]) / seg
    p0, p1 = poly[j], poly[j + 1]
    pos = p0[0].lerp(p1[0], lf)
    tan = (p1[0] - p0[0])
    if tan.length > 0:
        tan.normalize()
    tilt = p0[1] + (p1[1] - p0[1]) * lf
    rad = p0[2] + (p1[2] - p0[2]) * lf
    return pos, tan, tilt, rad


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
    poly, cum, total = data
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
        even = [d0 + span * i / (count - 1) for i in range(count)]
        w = s.spacing_by_size
        if abs(w) > 1e-6:
            radii = [_at(poly, cum, total, d)[3] for d in even]
            mean_r = sum(radii) / len(radii)
            if abs(mean_r) < 1e-6:
                mean_r = 1.0
            raw = []
            for i in range(count - 1):
                rr = max(0.05, ((radii[i] + radii[i + 1]) / 2.0) / mean_r)
                raw.append(rr ** w)      # w>0：半徑大處 → 間距大（正比）
            tot = sum(raw) or 1.0
            scale = span / tot
            dists = [d0]
            d = d0
            for st in raw:
                d += st * scale
                dists.append(d)
        else:
            dists = even

    out = []
    for i, dd in enumerate(dists):
        pos, tan, tilt, rad = _at(poly, cum, total, dd)
        out.append((pos, tan, tilt, rad, srcs[i]))
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
        return s.collection
    coll = bpy.data.collections.new("曲線陣列_" + obj.name)
    bpy.context.scene.collection.children.link(coll)
    s.collection = coll
    return coll


def _clear(coll):
    for o in list(coll.objects):
        bpy.data.objects.remove(o, do_unlink=True)


def _apply_transforms(obj, dups, items):
    s = obj.curve_array
    off = Euler((s.rot_offset[0], s.rot_offset[1], s.rot_offset[2]), 'XYZ').to_matrix()
    use_rand = (any(abs(v) > 1e-6 for v in s.rand_loc)
                or any(abs(v) > 1e-6 for v in s.rand_rot)
                or s.rand_scale > 1e-6)

    for idx, (dup, item) in enumerate(zip(dups, items)):
        pos, tan, tilt, rad, _src_ref = item
        src = bpy.data.objects.get(dup.get("_ca_src", ""))
        src_rot = src.rotation_euler.to_matrix() if src else Matrix.Identity(3)
        src_scale = Vector(src.scale) if src else Vector((1.0, 1.0, 1.0))

        # 曲線的區域座標框（X＝沿線方向、Y/Z＝側向），含 Ctrl+T 傾斜
        if s.align and tan.length > 0:
            rmat = tan.to_track_quat('X', 'Z').to_matrix() @ Matrix.Rotation(tilt, 3, 'X')
        else:
            rmat = Matrix.Rotation(tilt, 3, 'Z') if tilt else Matrix.Identity(3)

        m = s.size * rad          # 全域大小 × 曲線半徑(Alt+S)
        loc = pos.copy()
        rnd = Matrix.Identity(3)

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

        dup.location = loc
        dup.scale = (src_scale.x * m, src_scale.y * m, src_scale.z * m)
        dup.rotation_euler = (rmat @ src_rot @ off @ rnd).to_euler()


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
    need_rebuild = rebuild and (len(existing) != len(items) or s.source_collection is not None)
    if need_rebuild:
        _clear(coll)
        existing = []
        for (pos, tan, tilt, rad, src) in items:
            dup = src.copy()          # 連結複製：共用網格資料、並帶當下的修改器堆疊
            dup["_curve_array_child"] = 1
            dup["_ca_src"] = src.name
            dup.hide_select = True
            coll.objects.link(dup)
            existing.append(dup)
    elif sync_mods:
        for dup in existing:
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

    target: PointerProperty(name="選擇物件", type=bpy.types.Object,
                            poll=_target_poll, update=_prop_update)
    source_collection: PointerProperty(name="選擇集合", type=bpy.types.Collection,
                                       update=_prop_update)
    random_pick: BoolProperty(name="隨機挑選", default=False, update=_prop_update)
    pick_seed: IntProperty(name="隨機種子", default=0,
                           description="換數字＝換一組「從集合挑哪個物件」的組合（不影響隨機散佈）",
                           update=_prop_update)
    seed: IntProperty(name="隨機種子", default=0,
                      description="換數字＝換一組隨機散佈結果（不影響集合的隨機挑選）",
                      update=_prop_update)

    count: IntProperty(name="數量", default=6, min=1, max=2000, update=_prop_update)
    size: FloatProperty(name="物件大小", default=1.0, min=0.0, update=_prop_update)
    spacing_by_size: FloatProperty(
        name="間距隨曲線大小", default=0.0, min=-3.0, max=3.0,
        description="依曲線半徑(粗細)調整間距。正值＝半徑大處間距大、小處間距小；負值反之；0＝等距",
        update=_prop_update)
    start: FloatProperty(name="開始位置", default=0.0, min=0.0, max=1.0, update=_prop_update)
    end: FloatProperty(name="結束位置", default=1.0, min=0.0, max=1.0, update=_prop_update)
    align: BoolProperty(name="對齊曲線方向", default=True, update=_prop_update)
    rot_offset: FloatVectorProperty(name="物件自轉", subtype='EULER', size=3,
                                    default=(0.0, 0.0, 0.0), update=_prop_update)

    # 面板分區的收合狀態（純 UI）
    show_source: BoolProperty(name="來源", default=True)
    show_layout: BoolProperty(name="排列", default=True)
    show_object: BoolProperty(name="物件", default=True)
    show_curve: BoolProperty(name="曲線外觀", default=False)

    # 隨機散佈（用種子產生，可重現）
    show_random: BoolProperty(name="隨機散佈", default=False,
                              description="展開／收合隨機散佈設定")
    rand_loc: FloatVectorProperty(name="隨機位移", subtype='TRANSLATION', size=3,
                                  default=(0.0, 0.0, 0.0), min=0.0,
                                  description="每個物件隨機位移的範圍（±）。X＝沿曲線、Y/Z＝側向",
                                  update=_prop_update)
    rand_rot: FloatVectorProperty(name="隨機旋轉", subtype='EULER', size=3,
                                  default=(0.0, 0.0, 0.0), min=0.0,
                                  description="每個物件隨機旋轉的範圍（±）",
                                  update=_prop_update)
    rand_scale: FloatProperty(name="隨機縮放", default=0.0, min=0.0, max=1.0,
                              description="每個物件隨機縮放的幅度（±比例，0.3＝±30%）",
                              update=_prop_update)

    auto_update: BoolProperty(name="自動更新（跟隨曲線）", default=True,
                              update=_auto_update_toggle)


# ─────────────────────────────────────────────────────────────
# Operators
# ─────────────────────────────────────────────────────────────
class CURVEARRAY_OT_create(Operator):
    bl_idname = "curvearray.create"
    bl_label = "創建曲線陣列"

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
    bl_label = "重新產生"

    def execute(self, context):
        _update_array(context.object, rebuild=True)
        return {'FINISHED'}


class CURVEARRAY_OT_sync_mods(Operator):
    bl_idname = "curvearray.sync_mods"
    bl_label = "與來源同步修改器"
    bl_description = "把來源物件目前的修改器堆疊重新同步到陣列裡的所有物件（會覆蓋你對個別物件的修改器調整）"

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
        self.report({'INFO'}, "已同步 %d 個物件的修改器" % n)
        return {'FINISHED'}


class CURVEARRAY_OT_apply(Operator):
    bl_idname = "curvearray.apply"
    bl_label = "套用"
    bl_description = "保留目前的物件、停止跟隨曲線（烘焙成獨立物件、解鎖可選）"

    def execute(self, context):
        obj = context.object
        s = obj.curve_array
        if s.collection:
            for o in s.collection.objects:
                o.hide_select = False
        s.enabled = False
        s.collection = None
        obj.show_in_front = False
        self.report({'INFO'}, "已套用（物件保留、停止跟隨）")
        return {'FINISHED'}


class CURVEARRAY_OT_clear(Operator):
    bl_idname = "curvearray.clear"
    bl_label = "清除曲線陣列"

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
    head.label(text=label, icon=icon)
    return box if getattr(s, prop) else None


class CURVEARRAY_PT_panel(Panel):
    bl_label = "曲線陣列"
    bl_idname = "VIEW3D_PT_curve_array_objects"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = '曲線陣列'

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
        b = _section(layout, s, "show_source", "來源", 'OBJECT_DATA')
        if b:
            row = b.row()
            row.enabled = not s.source_collection      # 有選集合時，物件欄變灰（集合優先）
            row.prop(s, "target")
            b.prop(s, "source_collection")
            if s.source_collection:
                r = b.row(align=True)
                r.prop(s, "random_pick")
                if s.random_pick:
                    r.prop(s, "pick_seed", text="種子")

        # ── 排列：排幾個、排在哪 ──
        b = _section(layout, s, "show_layout", "排列", 'MOD_ARRAY')
        if b:
            b.prop(s, "count")
            b.prop(s, "spacing_by_size")
            row = b.row(align=True)
            row.prop(s, "start")
            row.prop(s, "end")
            rb = _section(b, s, "show_random", "隨機散佈", 'MOD_PARTICLES')
            if rb:
                rb.prop(s, "rand_loc")
                rb.prop(s, "rand_rot")
                rb.prop(s, "rand_scale")
                rb.prop(s, "seed")

        # ── 物件：排出來長怎樣 ──
        b = _section(layout, s, "show_object", "物件", 'MESH_DATA')
        if b:
            b.prop(s, "size")
            b.prop(s, "align")
            b.prop(s, "rot_offset")

        # ── 曲線外觀：曲線自己的屬性（次要，預設收起）──
        b = _section(layout, s, "show_curve", "曲線外觀", 'CURVE_DATA')
        if b:
            b.prop(obj.data, "bevel_depth", text="曲線粗細")
            row = b.row(align=True)
            row.prop(obj, "show_in_front", text="顯示在前面")
            row.prop(obj.data, "use_fill_caps", text="曲線封口")

        # ── 狀態：跟隨 or 解鎖編輯（狀態直接寫在按鈕上）──
        layout.separator()
        box = layout.box()
        r = box.row()
        r.scale_y = 1.3
        if s.auto_update:
            r.prop(s, "auto_update", toggle=True, icon='LOCKED', text="跟隨曲線中")
        else:
            r.prop(s, "auto_update", toggle=True, icon='UNLOCKED', text="已解鎖・可編輯")

        # ── 動作 ──
        layout.separator()
        acts = layout.column(align=True)
        row = acts.row(align=True)
        row.operator("curvearray.update", icon='FILE_REFRESH')
        row.operator("curvearray.sync_mods", text="同步修改器", icon='MODIFIER')
        row = acts.row(align=True)
        row.operator("curvearray.apply", icon='CHECKMARK')
        row.operator("curvearray.clear", text="清除", icon='X')


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


if __name__ == "__main__":
    register()
