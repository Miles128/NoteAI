import * as esbuild from 'esbuild';

await esbuild.build({
  entryPoints: ['webui/js/tiptap-bundle-entry.mjs'],
  bundle: true,
  format: 'iife',
  globalName: 'TiptapBundle',
  outfile: 'webui/lib/tiptap-bundle.js',
  minify: true,
  sourcemap: false,
  target: ['es2020'],
});
