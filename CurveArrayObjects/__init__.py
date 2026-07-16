bl_info = {
    "name": "CurveArrayObjects",
    "author": "Zack3D",
    "version": (2, 6, 0),
    "blender": (4, 3, 0),
    "location": "View3D > N 面板 > 曲線陣列",
    "description": "沿曲線陣列複製物件或整個集合（純 Python 版，不使用幾何節點）",
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
    if s.source_collection:
        objs = [o for o in s.source_collection.all_objects if not o.get("_curve_array_child")]
        if objs:
            return objs
    if s.target:
        return [s.target]
    return []


def _pick(s, sources, i):
    if len(sources) == 1:
        return sources[0]
    if s.random_pick:
        return random.Random(s.seed * 100003 + i).choice(sources)
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
_pending = set()


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
    for dup, item in zip(dups, items):
        pos, tan, tilt, rad, _src_ref = item
        src = bpy.data.objects.get(dup.get("_ca_src", ""))
        src_rot = src.rotation_euler.to_matrix() if src else Matrix.Identity(3)
        src_scale = Vector(src.scale) if src else Vector((1.0, 1.0, 1.0))

        m = s.size * rad          # 全域大小 × 曲線半徑(Alt+S)
        dup.scale = (src_scale.x * m, src_scale.y * m, src_scale.z * m)
        dup.location = pos
        if s.align and tan.length > 0:
            rmat = tan.to_track_quat('X', 'Z').to_matrix() @ Matrix.Rotation(tilt, 3, 'X')
        else:
            rmat = Matrix.Rotation(tilt, 3, 'Z') if tilt else Matrix.Identity(3)
        dup.rotation_euler = (rmat @ src_rot @ off).to_euler()


def _update_array(obj, rebuild=True):
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
            dup = src.copy()
            dup["_curve_array_child"] = 1
            dup["_ca_src"] = src.name
            dup.hide_select = True
            coll.objects.link(dup)
            existing.append(dup)
    _apply_transforms(obj, existing, items)


# ─────────────────────────────────────────────────────────────
# 即時更新
# ─────────────────────────────────────────────────────────────
def _process_pending():
    global _busy
    names = list(_pending)
    _pending.clear()
    _busy = True
    try:
        for name in names:
            obj = bpy.data.objects.get(name)
            if obj and obj.type == 'CURVE' and obj.curve_array.enabled and obj.curve_array.auto_update:
                _update_array(obj, rebuild=False)
    finally:
        _busy = False
    return None


@persistent
def _depsgraph_handler(scene, depsgraph):
    if _busy:
        return
    updated = {u.id.original for u in depsgraph.updates}
    hit = False
    for obj in scene.objects:
        if obj.type != 'CURVE':
            continue
        s = getattr(obj, 'curve_array', None)
        if not (s and s.enabled and s.auto_update and (s.target or s.source_collection)):
            continue
        dirty = obj.original in updated or (obj.data and obj.data.original in updated)
        if not dirty:
            for src in _sources(s):
                sdata = getattr(src, 'data', None)
                if src.original in updated or (sdata and sdata.original in updated):
                    dirty = True
                    break
        if dirty:
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
    seed: IntProperty(name="隨機種子", default=0, update=_prop_update)

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

        col = layout.column()
        col.prop(s, "target")
        col.prop(s, "source_collection")
        if s.source_collection:
            col.label(text="（有選集合時，優先用集合裡的物件排列）", icon='INFO')
            row = col.row(align=True)
            row.prop(s, "random_pick")
            if s.random_pick:
                row.prop(s, "seed")

        col.separator()
        col.prop(s, "count")
        col.prop(s, "size")
        col.prop(s, "spacing_by_size")
        col.prop(s, "align")
        col.prop(s, "rot_offset")
        row = col.row(align=True)
        row.prop(s, "start")
        row.prop(s, "end")

        col.separator()
        col.prop(obj.data, "bevel_depth", text="曲線粗細")
        col.prop(obj.data, "use_fill_caps", text="曲線封口")
        col.prop(obj, "show_in_front", text="曲線顯示在前面")

        layout.separator()
        box = layout.box()
        box.prop(s, "auto_update", icon='FILE_REFRESH')
        if not s.auto_update:
            box.label(text="已暫停跟隨，可個別編輯陣列物件", icon='UNLOCKED')

        layout.separator()
        r = layout.row(align=True)
        r.operator("curvearray.update", icon='FILE_REFRESH')
        r.operator("curvearray.apply", icon='CHECKMARK')
        layout.operator("curvearray.clear", icon='X')


classes = (
    CurveArraySettings,
    CURVEARRAY_OT_create,
    CURVEARRAY_OT_update,
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
