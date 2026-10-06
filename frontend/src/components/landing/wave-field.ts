/**
 * Real-time 2D wave equation on the GPU (WebGL2), rendered through an inferno
 * colour map. Point emitters drive the field, a few fixed discs scatter it, the
 * pointer can excite a pulse and a 1-pixel read-back reports the field under the
 * probe. No dependencies; callers handle visibility and reduced motion.
 */

const QUAD = `#version 300 es
in vec2 a_pos;
out vec2 v_uv;
void main() {
  v_uv = a_pos * 0.5 + 0.5;
  gl_Position = vec4(a_pos, 0.0, 1.0);
}`;

// State texel: r = height now, g = height one step ago.
const STEP = `#version 300 es
precision highp float;
uniform sampler2D u_state;
uniform ivec2 u_size;
uniform float u_aspect;
uniform float u_time;
uniform vec4 u_emitters[4];
uniform vec4 u_pulse;
uniform vec4 u_scatter[5];
out vec4 o;

float height(ivec2 p) {
  return texelFetch(u_state, clamp(p, ivec2(0), u_size - 1), 0).r;
}

void main() {
  ivec2 p = ivec2(gl_FragCoord.xy);
  vec2 uv = gl_FragCoord.xy / vec2(u_size);
  vec2 q = vec2(uv.x * u_aspect, uv.y);
  vec4 s = texelFetch(u_state, p, 0);
  float lap = height(p + ivec2(1, 0)) + height(p - ivec2(1, 0)) + height(p + ivec2(0, 1)) +
    height(p - ivec2(0, 1)) - 4.0 * s.r;
  float next = 2.0 * s.r - s.g + 0.24 * lap;

  for (int i = 0; i < 4; i++) {
    vec4 e = u_emitters[i];
    vec2 d = q - vec2(e.x * u_aspect, e.y);
    next += e.z * sin(u_time * e.w) * exp(-dot(d, d) * 9000.0);
  }
  vec2 dp = q - vec2(u_pulse.x * u_aspect, u_pulse.y);
  next += u_pulse.z * exp(-dot(dp, dp) * 2200.0);

  // Soft-walled scatterers reflect the wave like small particles.
  for (int i = 0; i < 5; i++) {
    vec4 c = u_scatter[i];
    float r = length(q - vec2(c.x * u_aspect, c.y));
    next *= smoothstep(c.z * 0.82, c.z, r);
  }

  // Sponge layer: absorb at the borders so nothing echoes back.
  float edge = min(min(uv.x, 1.0 - uv.x), min(uv.y, 1.0 - uv.y));
  next *= mix(0.94, 0.9968, smoothstep(0.0, 0.08, edge));
  o = vec4(next, s.r, 0.0, 1.0);
}`;

const SHOW = `#version 300 es
precision highp float;
in vec2 v_uv;
uniform sampler2D u_state;
uniform float u_aspect;
uniform float u_gain;
uniform float u_dim;
uniform vec4 u_scatter[5];
out vec4 o;

// Polynomial fit of matplotlib's inferno (Matt Zucker, CC0).
vec3 inferno(float t) {
  const vec3 c0 = vec3(0.0002189403691192265, 0.001651004631001012, -0.01948089843709184);
  const vec3 c1 = vec3(0.1065134194856116, 0.5639564367884091, 3.932712388889277);
  const vec3 c2 = vec3(11.60249308247187, -3.972853965665698, -15.9423941062914);
  const vec3 c3 = vec3(-41.70399613139459, 17.43639888205313, 44.35414519872813);
  const vec3 c4 = vec3(77.162935699427, -33.40235894210092, -81.80730925738993);
  const vec3 c5 = vec3(-71.31942824499214, 32.62606426397723, 73.20951985803202);
  const vec3 c6 = vec3(25.13112622477341, -12.24266895238567, -23.07032500287172);
  return c0 + t * (c1 + t * (c2 + t * (c3 + t * (c4 + t * (c5 + t * c6)))));
}

void main() {
  float h = texture(u_state, v_uv).r;
  // Soft-knee tone map: strong crests saturate gently instead of clipping to a flat blob.
  float t = 1.0 - exp(-abs(h) * u_gain);
  vec3 col = inferno(t * 0.94);
  vec2 q = vec2(v_uv.x * u_aspect, v_uv.y);
  for (int i = 0; i < 5; i++) {
    vec4 c = u_scatter[i];
    float r = length(q - vec2(c.x * u_aspect, c.y));
    float ring = 1.0 - smoothstep(0.0, 0.0028, abs(r - c.z));
    col = mix(col, vec3(0.93, 0.92, 0.9), ring * 0.85);
    col *= 0.35 + 0.65 * smoothstep(c.z * 0.7, c.z, r);
  }
  // Keep the left of the screen (where the copy sits) dim.
  col *= mix(u_dim, 1.0, smoothstep(0.16, 0.64, v_uv.x));
  // Ordered noise hides banding in the dark end of the map.
  float n = fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453);
  o = vec4(col + (n - 0.5) / 255.0, 1.0);
}`;

export interface WaveFieldOptions {
  /** Simulation cells across the long side; the short side follows the aspect. */
  cells: number;
  /** Brightness kept on the left edge (0–1); the right side is always full. */
  dim: number;
}

export interface Probe {
  x: number;
  y: number;
}

type Uniforms = Record<string, WebGLUniformLocation | null>;

function compile(gl: WebGL2RenderingContext, vertex: string, fragment: string) {
  const program = gl.createProgram()!;
  for (const [type, source] of [
    [gl.VERTEX_SHADER, vertex],
    [gl.FRAGMENT_SHADER, fragment],
  ] as const) {
    const shader = gl.createShader(type)!;
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      throw new Error(gl.getShaderInfoLog(shader) ?? "shader compile failed");
    }
    gl.attachShader(program, shader);
  }
  gl.bindAttribLocation(program, 0, "a_pos");
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    throw new Error(gl.getProgramInfoLog(program) ?? "program link failed");
  }
  return program;
}

function locate(gl: WebGL2RenderingContext, program: WebGLProgram, names: string[]): Uniforms {
  return Object.fromEntries(names.map((n) => [n, gl.getUniformLocation(program, n)]));
}

// Particles in field coordinates (x and y in 0..1, radius in units of height).
const SCATTER = [
  [0.62, 0.66, 0.024],
  [0.75, 0.36, 0.019],
  [0.88, 0.7, 0.028],
  [0.57, 0.3, 0.016],
  [0.94, 0.26, 0.017],
] as const;

export class WaveField {
  private gl: WebGL2RenderingContext;
  private step: WebGLProgram;
  private show: WebGLProgram;
  private stepU: Uniforms;
  private showU: Uniforms;
  private targets: { tex: WebGLTexture; fbo: WebGLFramebuffer }[] = [];
  private current = 0;
  private width = 0;
  private height = 0;
  private time = 0;
  private pulse: [number, number, number] | null = null;
  private probeAmp = 0;
  private probe: Probe | null = null;
  private readBuffer = new Float32Array(4);
  private canRead = true;

  static create(canvas: HTMLCanvasElement, options: WaveFieldOptions): WaveField | null {
    const gl = canvas.getContext("webgl2", {
      alpha: false,
      antialias: false,
      depth: false,
      stencil: false,
      premultipliedAlpha: false,
      preserveDrawingBuffer: false,
      powerPreference: "low-power",
    });
    if (!gl || !gl.getExtension("EXT_color_buffer_float")) return null;
    try {
      return new WaveField(gl, options);
    } catch {
      return null;
    }
  }

  private constructor(
    gl: WebGL2RenderingContext,
    private options: WaveFieldOptions,
  ) {
    this.gl = gl;
    this.step = compile(gl, QUAD, STEP);
    this.show = compile(gl, QUAD, SHOW);
    this.stepU = locate(gl, this.step, [
      "u_state",
      "u_size",
      "u_aspect",
      "u_time",
      "u_emitters",
      "u_pulse",
      "u_scatter",
    ]);
    this.showU = locate(gl, this.show, ["u_state", "u_aspect", "u_gain", "u_dim", "u_scatter"]);
    const quad = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, quad);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
  }

  /** Match the simulation grid to the canvas aspect; clears the field. */
  resize(cssWidth: number, cssHeight: number) {
    const gl = this.gl;
    const long = Math.max(cssWidth, cssHeight, 1);
    const w = Math.max(32, Math.round((this.options.cells * cssWidth) / long));
    const h = Math.max(32, Math.round((this.options.cells * cssHeight) / long));
    if (w === this.width && h === this.height) return;
    this.width = w;
    this.height = h;
    for (const t of this.targets) {
      gl.deleteTexture(t.tex);
      gl.deleteFramebuffer(t.fbo);
    }
    this.targets = [0, 1].map(() => {
      const tex = gl.createTexture()!;
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, w, h, 0, gl.RGBA, gl.HALF_FLOAT, null);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      const fbo = gl.createFramebuffer()!;
      gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
      gl.clearColor(0, 0, 0, 1);
      gl.clear(gl.COLOR_BUFFER_BIT);
      return { tex, fbo };
    });
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  }

  /** Field coordinates: x, y in 0..1 with y pointing up. */
  setProbe(probe: Probe | null) {
    if (probe && this.probe) {
      const moved = Math.hypot(probe.x - this.probe.x, probe.y - this.probe.y);
      this.probeAmp = Math.min(1, this.probeAmp + moved * 18);
    }
    this.probe = probe;
  }

  excite(x: number, y: number, strength = 1.1) {
    this.pulse = [x, y, strength];
  }

  /** Advance the simulation by `steps` sub-steps. */
  advance(steps: number) {
    const gl = this.gl;
    const aspect = this.width / this.height;
    gl.useProgram(this.step);
    gl.viewport(0, 0, this.width, this.height);
    gl.uniform1i(this.stepU.u_state!, 0);
    gl.uniform2i(this.stepU.u_size!, this.width, this.height);
    gl.uniform1f(this.stepU.u_aspect!, aspect);
    gl.uniform4fv(
      this.stepU.u_scatter!,
      SCATTER.flatMap(([x, y, r]) => [x, y, r, 0]),
    );
    for (let i = 0; i < steps; i++) {
      this.time += 1;
      const t = this.time;
      // Two coherent, slowly drifting sources (a two-slit pattern), plus the pointer when it moves.
      const emitters = [
        0.8 + 0.04 * Math.sin(t * 0.0021),
        0.56 + 0.08 * Math.sin(t * 0.0013),
        0.028,
        0.22,
        0.68 + 0.04 * Math.cos(t * 0.0017),
        0.26 + 0.05 * Math.cos(t * 0.0023),
        0.024,
        0.22,
        this.probe?.x ?? -1,
        this.probe?.y ?? -1,
        0.045 * this.probeAmp,
        0.33,
        -1,
        -1,
        0,
        0,
      ];
      gl.uniform4fv(this.stepU.u_emitters!, emitters);
      gl.uniform1f(this.stepU.u_time!, t);
      const pulse = this.pulse;
      gl.uniform4f(this.stepU.u_pulse!, pulse?.[0] ?? -1, pulse?.[1] ?? -1, pulse?.[2] ?? 0, 0);
      this.pulse = null;
      const src = this.targets[this.current]!;
      const dst = this.targets[1 - this.current]!;
      gl.bindFramebuffer(gl.FRAMEBUFFER, dst.fbo);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, src.tex);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      this.current = 1 - this.current;
    }
    this.probeAmp *= 0.97;
  }

  draw(canvasWidth: number, canvasHeight: number) {
    const gl = this.gl;
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, canvasWidth, canvasHeight);
    gl.useProgram(this.show);
    gl.uniform1i(this.showU.u_state!, 0);
    gl.uniform1f(this.showU.u_aspect!, this.width / this.height);
    gl.uniform1f(this.showU.u_gain!, 1.8);
    gl.uniform1f(this.showU.u_dim!, this.options.dim);
    gl.uniform4fv(
      this.showU.u_scatter!,
      SCATTER.flatMap(([x, y, r]) => [x, y, r, 0]),
    );
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.targets[this.current]!.tex);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }

  /** Field height under a point (one texel read back from the GPU). */
  sample(x: number, y: number): number | null {
    if (!this.canRead) return null;
    const gl = this.gl;
    const px = Math.min(this.width - 1, Math.max(0, Math.floor(x * this.width)));
    const py = Math.min(this.height - 1, Math.max(0, Math.floor(y * this.height)));
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.targets[this.current]!.fbo);
    try {
      gl.readPixels(px, py, 1, 1, gl.RGBA, gl.FLOAT, this.readBuffer);
    } catch {
      this.canRead = false;
    }
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    if (gl.getError() !== gl.NO_ERROR) {
      this.canRead = false;
      return null;
    }
    return this.readBuffer[0]!;
  }

  dispose() {
    const gl = this.gl;
    for (const t of this.targets) {
      gl.deleteTexture(t.tex);
      gl.deleteFramebuffer(t.fbo);
    }
    gl.deleteProgram(this.step);
    gl.deleteProgram(this.show);
    gl.getExtension("WEBGL_lose_context")?.loseContext();
  }
}

/** Particle positions for the HUD labels (same coordinates as the shader). */
export const SCATTERERS = SCATTER;
