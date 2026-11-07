# Current Windows environment

Python 3.12.10 and Node 24.22.1 were found. Docker and npm were not on PATH. A bundled pnpm executable is available at:

```powershell
$pnpm = 'C:\Users\N.ASRITHAREDDY\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\pnpm\bin\pnpm.cjs'
cd frontend
node $pnpm install --store-dir .pnpm-store --config.node-linker=hoisted --config.package-import-method=copy
node node_modules/typescript/bin/tsc --noEmit
node node_modules/vite/bin/vite.js build
node node_modules/vite/bin/vite.js --host 127.0.0.1
```

The installation requires registry access. A workspace-local store avoids sandbox restrictions on the default store path. If pnpm reports ignored esbuild build scripts, the platform-specific optional binary can still support Vite; confirm the build result before changing dependency script policy. Do not automatically approve arbitrary package scripts.
