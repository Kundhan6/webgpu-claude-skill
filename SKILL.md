---
name: webgpu-threejs-tsl
description: >
  Use when building real-time 3D graphics, shaders, visual effects, or GPU-accelerated
  rendering with Three.js WebGPU renderer and Three.js Shading Language (TSL). Covers
  WebGPURenderer setup, TSL node-based shader authoring, compute shaders, post-processing,
  particle systems, PBR materials, and performance optimization. Not for legacy WebGL or
  Three.js r3f / Drei patterns that predate the WebGPU backend.
trigger: >
  Triggered when the user mentions WebGPU, TSL, Three.js node materials, WebGPURenderer,
  Nodes, tsl, uniform(), attribute(), MeshStandardNodeMaterial, or any GPU compute task
  in a Three.js context.
---

# WebGPU + Three.js TSL Skill

## Renderer Setup

Always bootstrap with `WebGPURenderer`. Never fall back to `WebGLRenderer` silently — surface the capability gap explicitly.

```js
import WebGPU from 'three/addons/capabilities/WebGPU.js';
import WebGPURenderer from 'three/addons/renderers/common/WebGPURenderer.js';

if (!WebGPU.isAvailable()) {
  throw new Error('WebGPU not supported in this browser.');
}

const renderer = new WebGPURenderer({ antialias: true });
renderer.setPixelRatio(devicePixelRatio);
renderer.setSize(innerWidth, innerHeight);
await renderer.init(); // required — WebGPU init is async
```

- `await renderer.init()` is mandatory before first render
- Set `renderer.toneMapping` and `renderer.outputColorSpace` after init
- Use `renderer.setAnimationLoop(fn)` instead of `requestAnimationFrame` for WebGPU compatibility

---

## TSL — Three.js Shading Language

TSL is a node-graph shader system. Write shaders as composable JS functions — no raw WGSL or GLSL strings.

### Core imports

```js
import {
  uniform, attribute, varying, varyingProperty,
  vec2, vec3, vec4, float, int, uint, bool,
  mx_noise_float, mx_worley_noise_vec2,
  abs, sin, cos, pow, mix, clamp, step, smoothstep,
  dot, cross, normalize, length, reflect, refract,
  positionLocal, positionWorld, normalLocal, normalWorld,
  uv, time, cameraPosition,
  output, diffuseColor, emissive, roughness, metalness,
} from 'three/tsl';
```

### Uniform pattern

```js
// Declare outside render loop — update value inside
const speed  = uniform(1.0);
const colour = uniform(new THREE.Color(0xff6600));

// In animation loop:
speed.value  = elapsed * 0.5;
colour.value.setHSL(elapsed * 0.1 % 1, 1, 0.5);
```

- Never recreate `uniform()` inside the render loop — it leaks GPU memory
- Use `.value` to mutate, never replace the uniform node itself

### Attribute + Varying pattern

```js
const instanceColour = attribute('color', 'vec3');   // reads per-vertex attribute
const vColour        = varying(instanceColour);       // passes to fragment stage
```

---

## Node Materials

Use `MeshStandardNodeMaterial` (or `MeshPhysicalNodeMaterial`) for PBR. For unlit, use `MeshBasicNodeMaterial`.

```js
import { MeshStandardNodeMaterial } from 'three/nodes';

const mat = new MeshStandardNodeMaterial();

// Override colour with TSL expression
mat.colorNode = mix(
  vec3(1, 0.2, 0.05),
  vec3(0.05, 0.4, 1),
  sin(time.add(positionWorld.x)).mul(0.5).add(0.5)
);

// Override roughness
mat.roughnessNode = float(0.3);

// Custom vertex displacement
mat.positionNode = positionLocal.add(
  normalLocal.mul(mx_noise_float(positionLocal.mul(2).add(time)))
);
```

### Output override (fragment)

```js
// Full manual fragment output
mat.fragmentNode = vec4(normalWorld.mul(0.5).add(0.5), 1.0);
```

---

## Compute Shaders (GPGPU)

```js
import { computeShader, instanceIndex, storage } from 'three/tsl';
import StorageBufferNode  from 'three/src/nodes/core/StorageBufferNode.js';
import StorageInstancedBufferAttribute from 'three/src/renderers/common/StorageInstancedBufferAttribute.js';

// Create GPU-resident buffer
const count   = 100_000;
const posAttr = new StorageInstancedBufferAttribute(count, 3); // xyz
const posNode = storage(posAttr, 'vec3', count);

// Write compute kernel
const updatePositions = computeShader(() => {
  const i   = instanceIndex;
  const pos = posNode.element(i);
  pos.assign(pos.add(vec3(0, 0.001, 0)));
}, [count]);

// Dispatch per frame
renderer.compute(updatePositions);
```

- `StorageBufferNode` / `storage()` is the TSL bridge to GPU buffers
- Dispatch size must match buffer length
- Read-back to CPU is expensive — keep results on GPU when possible

---

## Post-Processing (Node-based)

```js
import { PostProcessing } from 'three/addons/postprocessing/PostProcessing.js';
import { bloom }          from 'three/addons/postprocessing/BloomNode.js';
import { pass }           from 'three/tsl';

const postProcessing = new PostProcessing(renderer);
const scenePass      = pass(scene, camera);

postProcessing.outputNode = bloom(scenePass.getTextureNode(), 0.5, 0.9);

// In animation loop — replace renderer.render():
postProcessing.render();
```

---

## Particles — Instanced + Compute

```js
// Prefer StorageInstancedBufferAttribute over Points for GPU-driven particles
const geometry = new THREE.InstancedBufferGeometry();
geometry.drawRange.count = count;

const mat = new MeshBasicNodeMaterial();
mat.colorNode = attribute('color', 'vec3');
mat.positionNode = storage(posAttr, 'vec3', count).element(instanceIndex);
```

---

## Performance Rules

- **Avoid per-frame JS uniform writes for large arrays** — use compute shaders instead
- **Prefer `instanceIndex` over manual attribute indexing** in compute kernels
- **Do not call `renderer.init()` more than once** per renderer instance
- **Cache node expressions** — declare complex TSL trees outside the render loop
- **Use `renderer.hasFeature('shader-f16')` guard** before half-precision paths
- **Avoid `renderer.readRenderTargetPixelsAsync`** in the hot path — batch or defer

---

## Anti-Patterns

- Do not mix raw GLSL `ShaderMaterial` with TSL materials in the same pass — shader graph contexts are incompatible
- Do not use `onBeforeCompile` — it is a WebGL-era hack; use node overrides instead
- Do not use `THREE.Points` with `PointsMaterial` for GPU-driven particles — use instanced geometry + compute
- Do not recreate `uniform()` / `storage()` nodes per frame
- Do not skip `await renderer.init()` — the renderer will silently fail on first draw

---

## Browser Compatibility (as of 2025)

| Browser       | WebGPU |
|---------------|--------|
| Chrome 113+   | ✅     |
| Edge 113+     | ✅     |
| Firefox 141+  | ✅ (behind flag until stable) |
| Safari 18+    | ✅     |
| iOS Safari    | ⚠️ partial |

Always gate with `WebGPU.isAvailable()` and provide a meaningful fallback message — not a silent WebGL downgrade.
