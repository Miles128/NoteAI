import { build } from 'esbuild';

await build({
  entryPoints: ['mcp-server/src/index.js'],
  bundle: true,
  platform: 'node',
  format: 'esm',
  outfile: 'mcp-server/dist/index.js',
  banner: {
    js: "import { createRequire } from 'node:module'; const require = createRequire(import.meta.url);",
  },
});
