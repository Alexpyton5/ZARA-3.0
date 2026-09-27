const path = require('node:path');
const ts = require(path.join(process.cwd(), 'node_modules', 'typescript'));
console.log(JSON.stringify({
  type: typeof ts,
  keys: Object.keys(ts).slice(0, 20),
  hasScriptTarget: Boolean(ts && ts.ScriptTarget),
  hasModuleKind: Boolean(ts && ts.ModuleKind),
  version: ts && ts.version,
}, null, 2));
