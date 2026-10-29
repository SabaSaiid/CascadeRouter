import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
const root = fileURLToPath(new URL('..', import.meta.url));
const tools = process.env.CASCADE_TEST_TOOLS;
const require = createRequire(join(tools || root, 'package.json'));
const ts = require('typescript');
const configPath = join(root, 'tsconfig.app.json');
const config = ts.readConfigFile(configPath, ts.sys.readFile);
const parsed = ts.parseJsonConfigFileContent(config.config, ts.sys, root);
if (tools) {
  // Supplemental cache validation only: not a locked Vite production build.
  parsed.options.types = [];
  parsed.options.paths = { 'react': [join(tools, 'node_modules/@types/react/index.d.ts')], 'react/*': [join(tools, 'node_modules/@types/react/*')], 'react-dom/*': [join(tools, 'node_modules/@types/react-dom/*')] };
  const stub = join(mkdtempSync(join(tmpdir(), 'cascade-env-types-')), 'env.d.ts');
  writeFileSync(stub, 'interface ImportMeta { readonly env: { readonly VITE_API_BASE_URL?: string } }\ndeclare module "*.css" {}');
  parsed.fileNames.push(stub);
}
const program = ts.createProgram(parsed.fileNames, parsed.options);
const diagnostics = [...parsed.errors, ...ts.getPreEmitDiagnostics(program)];
for (const d of diagnostics) process.stderr.write(ts.flattenDiagnosticMessageText(d.messageText, '\n') + (d.file ? ` (${d.file.fileName}:${d.file.getLineAndCharacterOfPosition(d.start).line + 1})` : '') + '\n');
process.stdout.write(`TypeScript ${ts.version}: ${diagnostics.length} diagnostics; ${tools ? 'supplemental cached tools; Vite env declaration only' : 'configured dependencies'}\n`);
process.exitCode = diagnostics.length ? 1 : 0;
