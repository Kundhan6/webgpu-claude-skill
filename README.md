# webgpu-claude-skill

Claude Code skill for **Three.js WebGPU renderer + TSL (Three.js Shading Language)**.

## Install

```bash
npx skills add Kundhan6/webgpu-claude-skill
```

## What it covers

- `WebGPURenderer` async init and configuration
- TSL node authoring — uniforms, attributes, varyings
- `MeshStandardNodeMaterial` / `MeshPhysicalNodeMaterial` overrides
- Compute shaders with `StorageBufferNode`
- Node-based post-processing (bloom, passes)
- GPU-driven instanced particles
- Performance rules and anti-patterns
- Browser compatibility table

## Other content in this repository

`kuro-blender-suite/` is an unrelated project (a set of Blender add-ons)
that was built inside this repo on the `claude/second-addon-dev-yoe3vz`
branch because a dedicated repository wasn't available at the time — see
`kuro-blender-suite/DECISIONS.md`. It has no connection to the WebGPU/TSL
skill above.
