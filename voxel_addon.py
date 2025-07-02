from bpy.props import StringProperty, FloatProperty, PointerProperty
from math import floor, ceil
import math
import mathutils
import bpy

bl_info = {
    "name": "Voxel Converter (with Material)",
    "author": "Assistant",
    "version": (1, 1),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Voxel",
    "description": "Generate multi‑frame voxel meshes from a target object and assign a chosen material.",
    "category": "Object",
}


# --------------------------------------------------------
# 1) 基本関数とクラス
# --------------------------------------------------------

def calculate_bounding_box(eval_obj, mesh):
    """評価済みオブジェクトとメッシュからワールド座標AABBを計算"""
    if not mesh:
        return None
    world_verts = [eval_obj.matrix_world @ v.co for v in mesh.vertices]
    min_x = min(v.x for v in world_verts)
    max_x = max(v.x for v in world_verts)
    min_y = min(v.y for v in world_verts)
    max_y = max(v.y for v in world_verts)
    min_z = min(v.z for v in world_verts)
    max_z = max(v.z for v in world_verts)
    size_x = math.ceil(max_x - min_x)
    size_y = math.ceil(max_y - min_y)
    size_z = math.ceil(max_z - min_z)
    center_x = min_x + (size_x * 0.5)
    center_y = min_y + (size_y * 0.5)
    center_z = min_z + (size_z * 0.5)
    return {
        "size": mathutils.Vector((size_x, size_y, size_z)),
        "center": mathutils.Vector((center_x, center_y, center_z))
    }


class VoxelInfo:
    """ボクセル化に必要なパラメータを保持するクラス"""

    def __init__(self, scale, size, center):
        self.scale = scale
        self.area_size = size
        self.area_center = center
        self.count_x_line = int(size.x / scale)
        self.count_y_line = int(size.y / scale)
        self.count_z_line = int(size.z / scale)
        self.offset = mathutils.Vector((
            size.x * 0.5 - center.x,
            size.y * 0.5 - center.y,
            size.z * 0.5 - center.z
        ))

    def __repr__(self):
        return (f"VoxelInfo(scale={self.scale}, count=({self.count_x_line}, "
                f"{self.count_y_line}, {self.count_z_line}), size={self.area_size}, "
                f"center={self.area_center}, offset={self.offset})")


class Voxel:
    """1個のボクセル情報。中心位置、交差フラグ、UV（単一）を保持"""

    def __init__(self, position):
        self.position = position
        self.is_render = False
        self.uv = mathutils.Vector((0, 0))


# --------------------------------------------------------
# 2) オペレーター
# --------------------------------------------------------

class OBJECT_OT_PrintMultiFrameVoxelWithUV(bpy.types.Operator):
    """
    選択したターゲットオブジェクトの各指定フレームの形状からボクセル化を行い、
    各ボクセルに対して最寄り頂点のUVを割り当てます。
    結果は "animationVoxel" の下に、各フレームごとに voxelFrame_○ という名前で生成されます。
    """
    bl_idname = "object.print_multi_frame_voxel_with_uv"
    bl_label = "Generate Multi-Frame Voxel"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        depsgraph = context.evaluated_depsgraph_get()

        # --- プロパティから取得 ---
        target_obj = scene.voxel_target_object
        if not target_obj:
            self.report({'ERROR'}, "ターゲットオブジェクトが設定されていません。")
            return {'CANCELLED'}

        frames_string = scene.voxel_frames_string
        voxel_size = scene.voxel_size
        material = scene.voxel_material  # 追加: 使用するマテリアル

        # --- "animationVoxel" の作成（既存は削除） ---
        anim_root = bpy.data.objects.get("animationVoxel")
        if anim_root:
            bpy.ops.object.select_all(action='DESELECT')
            anim_root.select_set(True)
            for child in anim_root.children:
                child.select_set(True)
            bpy.ops.object.delete(use_global=False)
        bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
        animationVoxel_obj = context.object
        animationVoxel_obj.name = "animationVoxel"

        # --- フレームリストの解析 ---
        try:
            frames_list = [int(x.strip()) for x in frames_string.split(",")]
        except ValueError:
            self.report({'ERROR'}, "フレーム指定が不正です。例: 1,10,20")
            return {'CANCELLED'}
        frames_list.sort()
        self.report({'INFO'}, f"対象フレーム: {frames_list}")

        # --- 各フレーム処理 ---
        for frame_number in frames_list:
            scene.frame_set(frame_number)

            # 評価済みメッシュ取得
            eval_obj = target_obj.evaluated_get(depsgraph)
            eval_mesh = eval_obj.to_mesh()
            if not eval_mesh:
                self.report({'WARNING'}, f"{frame_number}フレーム: メッシュ取得失敗。")
                continue

            # UVレイヤー（あれば）取得、頂点ごとUVの記録
            uv_layer = eval_mesh.uv_layers.active if eval_mesh.uv_layers else None
            verts_uv = [None] * len(eval_mesh.vertices)
            if uv_layer:
                for poly in eval_mesh.polygons:
                    for li in poly.loop_indices:
                        vidx = eval_mesh.loops[li].vertex_index
                        if verts_uv[vidx] is None:
                            verts_uv[vidx] = uv_layer.data[li].uv.copy()
                for i in range(len(verts_uv)):
                    if verts_uv[i] is None:
                        verts_uv[i] = mathutils.Vector((0, 0))
            else:
                for i in range(len(verts_uv)):
                    verts_uv[i] = mathutils.Vector((0, 0))

            # ワールド座標とUVのリスト
            world_positions = []
            for i, v in enumerate(eval_mesh.vertices):
                wpos = eval_obj.matrix_world @ v.co
                wuv = verts_uv[i]
                world_positions.append((wpos, wuv))

            # AABB計算
            bbox = calculate_bounding_box(eval_obj, eval_mesh)
            if not bbox:
                eval_obj.to_mesh_clear()
                continue

            voxel_info = VoxelInfo(voxel_size, bbox["size"], bbox["center"])

            # 3次元グリッド上にボクセル生成
            voxels = []
            for ix in range(voxel_info.count_x_line):
                for iy in range(voxel_info.count_y_line):
                    for iz in range(voxel_info.count_z_line):
                        pos = mathutils.Vector((
                            ix * voxel_info.scale - voxel_info.offset.x,
                            iy * voxel_info.scale - voxel_info.offset.y,
                            iz * voxel_info.scale - voxel_info.offset.z
                        )) + mathutils.Vector((voxel_info.scale * 0.5,) * 3)
                        voxels.append(Voxel(pos))

            # 分離軸判定（SAT）でメッシュと交差するボクセルを特定
            polygons = eval_mesh.polygons
            vdata = eval_mesh.vertices
            for poly in polygons:
                v0 = eval_obj.matrix_world @ vdata[poly.vertices[0]].co
                v1 = eval_obj.matrix_world @ vdata[poly.vertices[1]].co
                v2 = eval_obj.matrix_world @ vdata[poly.vertices[2]].co
                min_x = min(v0.x, v1.x, v2.x)
                max_x = max(v0.x, v1.x, v2.x)
                min_y = min(v0.y, v1.y, v2.y)
                max_y = max(v0.y, v1.y, v2.y)
                min_z = min(v0.z, v1.z, v2.z)
                max_z = max(v0.z, v1.z, v2.z)
                min_xi = max(0, floor((min_x + voxel_info.offset.x) / voxel_info.scale))
                max_xi = min(voxel_info.count_x_line, ceil((max_x + voxel_info.offset.x) / voxel_info.scale))
                min_yi = max(0, floor((min_y + voxel_info.offset.y) / voxel_info.scale))
                max_yi = min(voxel_info.count_y_line, ceil((max_y + voxel_info.offset.y) / voxel_info.scale))
                min_zi = max(0, floor((min_z + voxel_info.offset.z) / voxel_info.scale))
                max_zi = min(voxel_info.count_z_line, ceil((max_z + voxel_info.offset.z) / voxel_info.scale))
                f0 = v1 - v0
                f1 = v2 - v1
                f2 = v0 - v2
                right = mathutils.Vector((1, 0, 0))
                up = mathutils.Vector((0, 1, 0))
                fwd = mathutils.Vector((0, 0, 1))
                a00 = right.cross(f0)
                a01 = right.cross(f1)
                a02 = right.cross(f2)
                a10 = up.cross(f0)
                a11 = up.cross(f1)
                a12 = up.cross(f2)
                a20 = fwd.cross(f0)
                a21 = fwd.cross(f1)
                a22 = fwd.cross(f2)
                axises = [a00, a01, a02, a10, a11, a12, a20, a21, a22, right, up, fwd]
                n = f0.cross(f1).normalized()
                axises.append(n)
                half = voxel_info.scale * 0.5
                corners = [
                    mathutils.Vector((-half, -half, -half)),
                    mathutils.Vector((half, -half, -half)),
                    mathutils.Vector((-half, -half, half)),
                    mathutils.Vector((half, -half, half)),
                    mathutils.Vector((-half, half, -half)),
                    mathutils.Vector((half, half, -half)),
                    mathutils.Vector((-half, half, half)),
                    mathutils.Vector((half, half, half)),
                ]
                for ix in range(min_xi, max_xi):
                    for iy in range(min_yi, max_yi):
                        for iz in range(min_zi, max_zi):
                            idx = (ix * voxel_info.count_y_line * voxel_info.count_z_line +
                                   iy * voxel_info.count_z_line + iz)
                            intersect = True
                            for axis in axises:
                                if axis.length == 0:
                                    continue
                                a = axis.dot(v0)
                                b = axis.dot(v1)
                                c = axis.dot(v2)
                                t_min = min(a, b, c)
                                t_max = max(a, b, c)
                                vc = voxels[idx].position
                                dlist = [axis.dot(vc + cr) for cr in corners]
                                v_min = min(dlist)
                                v_max = max(dlist)
                                if (v_min > t_max) or (t_min > v_max):
                                    intersect = False
                                    break
                            if intersect:
                                voxels[idx].is_render = True

            # メモリ解放
            eval_obj.to_mesh_clear()

            # 各交差ボクセルに対し、最寄り頂点のUVを設定
            for vx in voxels:
                if not vx.is_render:
                    continue
                min_dist = float('inf')
                near_uv = mathutils.Vector((0, 0))
                for (wpos, wuv) in world_positions:
                    d = (vx.position - wpos).length
                    if d < min_dist:
                        min_dist = d
                        near_uv = wuv
                vx.uv = near_uv

            # ボクセル毎にCube生成、生成直後にUVレイヤーとマテリアルを設定
            cubes = []
            for vx in voxels:
                if not vx.is_render:
                    continue
                bpy.ops.mesh.primitive_cube_add(
                    size=voxel_info.scale,
                    location=vx.position
                )
                cube_obj = context.object
                mesh = cube_obj.data
                # UV
                if not mesh.uv_layers:
                    mesh.uv_layers.new(name="UVMap")
                uv_data = mesh.uv_layers.active.data
                for li in range(len(uv_data)):
                    uv_data[li].uv = vx.uv
                # Material
                if material:
                    if mesh.materials:
                        mesh.materials[0] = material
                    else:
                        mesh.materials.append(material)
                cubes.append(cube_obj)

            # Cubeが生成されていれば結合
            if cubes:
                bpy.ops.object.select_all(action='DESELECT')
                for cobj in cubes:
                    cobj.select_set(True)
                context.view_layer.objects.active = cubes[0]
                bpy.ops.object.join()
                result_obj = context.object
                result_obj.name = f"voxelFrame_{frame_number}"
                result_obj.parent = animationVoxel_obj
                bpy.ops.object.convert(target='MESH')
                # 保険として結果オブジェクトにもマテリアルを設定
                if material:
                    if result_obj.data.materials:
                        result_obj.data.materials[0] = material
                    else:
                        result_obj.data.materials.append(material)
                self.report({'INFO'}, f"Frame {frame_number}: voxel mesh created.")
            else:
                self.report({'INFO'}, f"Frame {frame_number}: No intersecting voxels.")

        self.report({'INFO'}, "Multi-frame voxel generation complete!")
        return {'FINISHED'}


# --------------------------------------------------------
# 3) パネル (GUI) の定義
# --------------------------------------------------------

class VOXEL_PT_main_panel(bpy.types.Panel):
    bl_label = "Multi-Frame Voxel"
    bl_idname = "VOXEL_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Voxel"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # ターゲットオブジェクト選択 (タイプ制限は必要に応じて追加可能)
        layout.prop(scene, "voxel_target_object", text="Target Object")
        layout.prop(scene, "voxel_frames_string", text="Frames (e.g., 1,10,20)")
        layout.prop(scene, "voxel_size", text="Voxel Size")
        layout.prop(scene, "voxel_material", text="Material")  # 追加: マテリアル選択
        layout.separator()
        layout.operator("object.print_multi_frame_voxel_with_uv", text="Generate Voxels")


# --------------------------------------------------------
# 4) アドオン登録
# --------------------------------------------------------

def register():
    bpy.utils.register_class(OBJECT_OT_PrintMultiFrameVoxelWithUV)
    bpy.utils.register_class(VOXEL_PT_main_panel)
    bpy.types.Scene.voxel_frames_string = StringProperty(
        name="Frames",
        description="Comma-separated list of frames (e.g., 1,10,20)",
        default="1,10,20"
    )
    bpy.types.Scene.voxel_size = FloatProperty(
        name="Voxel Size",
        description="Size of each voxel cube",
        default=0.1,
        min=0.001
    )
    bpy.types.Scene.voxel_target_object = PointerProperty(
        name="Target Object",
        description="Object to generate voxels from",
        type=bpy.types.Object
    )
    # 追加: マテリアル選択用プロパティ
    bpy.types.Scene.voxel_material = PointerProperty(
        name="Material",
        description="Material to assign to voxel meshes",
        type=bpy.types.Material
    )


def unregister():
    del bpy.types.Scene.voxel_frames_string
    del bpy.types.Scene.voxel_size
    del bpy.types.Scene.voxel_target_object
    del bpy.types.Scene.voxel_material  # 追加
    bpy.utils.unregister_class(VOXEL_PT_main_panel)
    bpy.utils.unregister_class(OBJECT_OT_PrintMultiFrameVoxelWithUV)


if __name__ == "__main__":
    register()