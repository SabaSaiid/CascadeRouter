// Uses the declared TypeScript/React tools. CASCADE_TEST_TOOLS may point at an
// offline cached validation installation; its versions must be reported separately.
import { createRequire } from 'node:module';
import { mkdtempSync, readdirSync, readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { tmpdir } from 'node:os';
const root = fileURLToPath(new URL('..', import.meta.url));
const tools = process.env.CASCADE_TEST_TOOLS || root;
const require = createRequire(join(tools, 'package.json'));
const ts = require('typescript');
export const React = require('react');
export const { renderToStaticMarkup } = require('react-dom/server');
const build = mkdtempSync(join(tmpdir(), 'cascade-render-'));
writeFileSync(join(build, 'package.json'), '{"type":"module"}');
function compile(folder) {
  for (const file of readdirSync(folder, { withFileTypes: true })) {
    const path = join(folder, file.name);
    if (file.isDirectory()) compile(path);
    else if (/\.tsx?$/.test(path)) {
      const destination = join(build, path.slice(resolve(root, 'src').length + 1).replace(/\.tsx?$/, '.js'));
      mkdirSync(dirname(destination), { recursive: true });
      const result = ts.transpileModule(readFileSync(path, 'utf8'), { compilerOptions: { target: ts.ScriptTarget.ES2023, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX } });
      const output = result.outputText.replace(/(from\s+['"][^'"]+)\.tsx?(['"])/g, '$1.js$2')
        .replace(/(from\s+['"])(react(?:-dom)?(?:\/[^'"]+)?)(['"])/g, (_match, before, name, after) => before + pathToFileURL(require.resolve(name)).href + after);
      writeFileSync(destination, output);
    }
  }
}
compile(resolve(root, 'src'));
export const component = async name => import(pathToFileURL(join(build, name + '.js')).href);
