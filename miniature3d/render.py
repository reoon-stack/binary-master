"""moderngl(ソフトウェア OpenGL)で描画する。Blender 不要・GPU 不要。

- 太陽光 + シャドウマップ(やわらかい影)
- 空と床の色を混ぜた環境光
- 夕方になると点く、暖色の点光源(スタンドライト)
- 色の 4 つ目の値で発光(窓・画面・ライトのかさ)
"""

from __future__ import annotations

import math
import os

import moderngl
import numpy as np

VS = """
#version 330
in vec3 in_pos; in vec3 in_nrm; in vec4 in_col;
uniform mat4 u_model; uniform mat4 u_vp; uniform mat4 u_light_vp;
out vec3 v_world; out vec3 v_nrm; out vec4 v_col; out vec4 v_light;
void main() {
    vec4 w = u_model * vec4(in_pos, 1.0);
    v_world = w.xyz;
    v_nrm = normalize(mat3(u_model) * in_nrm);
    v_col = in_col;
    v_light = u_light_vp * w;
    gl_Position = u_vp * w;
}
"""

FS = """
#version 330
in vec3 v_world; in vec3 v_nrm; in vec4 v_col; in vec4 v_light;
uniform sampler2D u_shadow;
uniform vec3 u_sun_dir; uniform vec3 u_sun_col;
uniform vec3 u_sky; uniform vec3 u_ground;
uniform int u_nl; uniform vec3 u_lp[16]; uniform vec3 u_lc[16]; uniform float u_falloff;
uniform float u_glow; uniform float u_flash; uniform vec3 u_cam; uniform float u_spec; uniform float u_shadow_floor;
out vec4 f;
float shadow() {
    vec3 p = v_light.xyz / v_light.w * 0.5 + 0.5;
    if (p.x < 0.0 || p.x > 1.0 || p.y < 0.0 || p.y > 1.0) return 1.0;
    float s = 0.0;
    vec2 texel = 1.0 / vec2(textureSize(u_shadow, 0));
    for (int x = -2; x <= 2; x++)
        for (int y = -2; y <= 2; y++) {
            float d = texture(u_shadow, p.xy + vec2(x, y) * texel).r;
            s += (p.z - 0.0025 > d) ? 0.0 : 1.0;
        }
    return s / 25.0;
}
void main() {
    vec3 n = normalize(v_nrm);
    vec3 base = v_col.rgb;
    float diff = max(dot(n, normalize(u_sun_dir)), 0.0);
    vec3 amb = mix(u_ground, u_sky, n.y * 0.5 + 0.5);
    float sh = shadow();
    vec3 col = base * (amb + u_sun_col * diff * (u_shadow_floor + (1.0 - u_shadow_floor) * sh));
    for (int i = 0; i < u_nl; i++) {
        vec3 L = u_lp[i] - v_world;
        float dist = length(L);
        float ld = max(dot(n, L / dist), 0.0) * 0.6 + 0.4;
        col += base * u_lc[i] * ld / (1.0 + u_falloff * dist * dist);
    }
    col = mix(col, base * (1.0 + 0.6 * u_glow), clamp(v_col.a * u_glow, 0.0, 1.0));
    vec3 V = normalize(u_cam - v_world);
    vec3 Hh = normalize(normalize(u_sun_dir) + V);
    float sp = pow(max(dot(n, Hh), 0.0), 48.0) * u_spec * sh;
    col += u_sun_col * sp;
    col += vec3(u_flash);
    f = vec4(pow(col, vec3(1.0 / 1.15)), 1.0);
}
"""

SHADOW_VS = """
#version 330
in vec3 in_pos;
uniform mat4 u_model; uniform mat4 u_light_vp;
void main() { gl_Position = u_light_vp * u_model * vec4(in_pos, 1.0); }
"""
SHADOW_FS = "#version 330\nvoid main() {}"

BG_VS = """
#version 330
out vec2 uv;
void main() {
    vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    uv = p; gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}
"""
BG_FS = """
#version 330
in vec2 uv; uniform vec3 u_top; uniform vec3 u_bottom; uniform float u_stars; uniform float u_time;
out vec4 f;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
void main() {
    float v = clamp(uv.y, 0.0, 1.0);
    vec3 c = mix(u_bottom, u_top, v);
    if (u_stars > 0.0) {
        vec2 g = floor(uv * vec2(90.0, 160.0));
        float h = hash(g);
        if (h > 0.985) {
            float tw = 0.6 + 0.4 * sin(u_time * 3.0 + h * 100.0);
            c += vec3(1.0, 0.97, 0.9) * u_stars * tw * smoothstep(0.25, 0.7, v);
        }
    }
    float r = length((uv - 0.5) * vec2(0.9, 1.3));
    c *= 1.0 - 0.25 * smoothstep(0.35, 0.9, r);
    f = vec4(c, 1.0);
}
"""


def perspective(fov, aspect, near, far):
    t = 1 / math.tan(fov / 2)
    return np.array([[t / aspect, 0, 0, 0], [0, t, 0, 0],
                     [0, 0, (far + near) / (near - far), 2 * far * near / (near - far)],
                     [0, 0, -1, 0]], dtype="f4")


def ortho(l, r, b, t, n, f):
    return np.array([[2 / (r - l), 0, 0, -(r + l) / (r - l)], [0, 2 / (t - b), 0, -(t + b) / (t - b)],
                     [0, 0, -2 / (f - n), -(f + n) / (f - n)], [0, 0, 0, 1]], dtype="f4")


def look_at(eye, target, up=(0, 1, 0)):
    eye, target, up = map(lambda v: np.array(v, dtype="f4"), (eye, target, up))
    f = target - eye
    f /= np.linalg.norm(f)
    s = np.cross(f, up)
    s /= np.linalg.norm(s)
    u = np.cross(s, f)
    m = np.eye(4, dtype="f4")
    m[0, :3], m[1, :3], m[2, :3] = s, u, -f
    m[:3, 3] = -m[:3, :3] @ eye
    return m


def translate(x, y, z):
    m = np.eye(4, dtype="f4")
    m[:3, 3] = (x, y, z)
    return m


def scale(sx, sy, sz):
    return np.diag([sx, sy, sz, 1.0]).astype("f4")


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0, 0], [s, c, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], dtype="f4")


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0, 0], [0, c, -s, 0], [0, s, c, 0], [0, 0, 0, 1]], dtype="f4")


def rot_axis(axis, a):
    x, y, z = np.asarray(axis, dtype="f8") / (np.linalg.norm(axis) or 1.0)
    c, s, t = math.cos(a), math.sin(a), 1 - math.cos(a)
    m = np.eye(4, dtype="f4")
    m[:3, :3] = [[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
                 [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
                 [t * x * z - s * y, t * y * z + s * x, t * z * z + c]]
    return m


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s, 0], [0, 1, 0, 0], [-s, 0, c, 0], [0, 0, 0, 1]], dtype="f4")


class Renderer:
    def __init__(self, width, height, samples=4):
        self.w, self.h = width, height
        backend = os.environ.get("MODERNGL_BACKEND", "egl")
        self.ctx = moderngl.create_standalone_context(backend=backend)
        self.prog = self.ctx.program(vertex_shader=VS, fragment_shader=FS)
        self.sprog = self.ctx.program(vertex_shader=SHADOW_VS, fragment_shader=SHADOW_FS)
        self.bg = self.ctx.program(vertex_shader=BG_VS, fragment_shader=BG_FS)
        self.bg_vao = self.ctx.vertex_array(self.bg, [])
        self.fbo = self.ctx.framebuffer(
            color_attachments=[self.ctx.renderbuffer((width, height), samples=samples)],
            depth_attachment=self.ctx.depth_renderbuffer((width, height), samples=samples))
        self.out = self.ctx.simple_framebuffer((width, height))
        self.shadow_tex = self.ctx.depth_texture((2048, 2048))
        self.shadow_tex.compare_func = ""          # 深度をそのまま読む(sampler2D で使う)
        self.shadow_tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self.shadow_fbo = self.ctx.framebuffer(depth_attachment=self.shadow_tex)
        self.meshes = {}

    def add_mesh(self, key, data: np.ndarray):
        vbo = self.ctx.buffer(data.tobytes())
        vao = self.ctx.vertex_array(self.prog, [(vbo, "3f 3f 4f", "in_pos", "in_nrm", "in_col")])
        svao = self.ctx.vertex_array(self.sprog, [(vbo, "3f 12x 16x", "in_pos")])
        self.meshes[key] = (vao, svao)

    def render(self, draws, cam_eye, cam_target, fov, light, bg) -> bytes:
        """draws: [(mesh_key, model 行列)]  light: dict  bg: (上の色, 下の色)"""
        sun = np.array(light["sun_dir"], dtype="f4")
        sun /= np.linalg.norm(sun)
        center = np.array(light.get("center", (0, 1, 0)), dtype="f4")
        lview = look_at(center + sun * 12, center)
        ext = light.get("shadow_extent", 7)
        light_vp = ortho(-ext, ext, -ext, ext, 1, 30) @ lview

        # 影
        self.shadow_fbo.use()
        self.shadow_fbo.clear(depth=1.0)
        self.ctx.enable(moderngl.DEPTH_TEST)
        self.sprog["u_light_vp"].write(light_vp.T.copy())
        for d_ in draws:
            key, model = d_[0], d_[1]
            self.sprog["u_model"].write(model.T.copy())
            if len(d_) > 2:
                if d_[2] > 0:
                    self.meshes[key][1].render(vertices=d_[2])
            else:
                self.meshes[key][1].render()

        # 本番
        self.fbo.use()
        self.fbo.clear(0, 0, 0)
        self.ctx.disable(moderngl.DEPTH_TEST)
        self.bg["u_top"].value, self.bg["u_bottom"].value = bg[0], bg[1]
        if "u_stars" in self.bg:
            self.bg["u_stars"].value = bg[2] if len(bg) > 2 else 0.0
            self.bg["u_time"].value = bg[3] if len(bg) > 3 else 0.0
        self.bg_vao.render(vertices=3)
        self.ctx.enable(moderngl.DEPTH_TEST)
        vp = perspective(fov, self.w / self.h, 0.1, 100) @ look_at(cam_eye, cam_target)
        p = self.prog
        p["u_vp"].write(vp.T.copy())
        p["u_light_vp"].write(light_vp.T.copy())
        p["u_sun_dir"].value = tuple(sun)
        p["u_sun_col"].value = light["sun_col"]
        p["u_sky"].value = light["sky"]
        p["u_ground"].value = light["ground"]
        lamps = light.get("lamps")
        if lamps is None:
            k = light.get("lamp", 0.0)
            lamps = [(light["lamp_pos"], tuple(c * k for c in light["lamp_col"]))] if k > 0 else []
        lamps = lamps[:16]
        p["u_nl"].value = len(lamps)
        p["u_falloff"].value = light.get("falloff", 0.35)
        if lamps:
            pos = np.zeros((16, 3), "f4")
            col = np.zeros((16, 3), "f4")
            for i, (lp, lc) in enumerate(lamps):
                pos[i], col[i] = lp, lc
            p["u_lp"].write(pos.tobytes())
            p["u_lc"].write(col.tobytes())
        p["u_glow"].value = light["glow"]
        p["u_flash"].value = light.get("flash", 0.0)
        p["u_cam"].value = tuple(float(v) for v in cam_eye)
        p["u_shadow_floor"].value = light.get("shadow_floor", 0.0)
        spec = light.get("spec", {})
        self.shadow_tex.use(0)
        p["u_shadow"].value = 0
        for d_ in draws:
            key, model = d_[0], d_[1]
            p["u_model"].write(model.T.copy())
            p["u_spec"].value = spec.get(key, light.get("spec_default", 0.12))
            if len(d_) > 2:                       # (key, 行列, 頂点数): 先頭から一部だけ描く
                if d_[2] > 0:
                    self.meshes[key][0].render(vertices=d_[2])
            else:
                self.meshes[key][0].render()
        self.ctx.copy_framebuffer(self.out, self.fbo)
        return self.out.read(components=3)
