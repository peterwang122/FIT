import assert from 'node:assert/strict'
import { readFileSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const require = createRequire(resolve(root, 'frontend/package.json'))
const { build } = require('esbuild')
const bundle = await build({
  stdin: { contents: `export { buildIndexQuantFilterDataset } from './frontend/src/utils/quantIndicators';
    export { matchRuleGroupIndexes } from './frontend/src/utils/quantRuleGroups';
    export { CSI500_SWING_FIELDS } from './frontend/src/utils/csi500Swing';`, resolveDir: root, loader: 'ts' },
  bundle: true, write: false, platform: 'node', format: 'esm',
})
const { buildIndexQuantFilterDataset, matchRuleGroupIndexes, CSI500_SWING_FIELDS } = await import(
  `data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].text).toString('base64')}`)
const folder = resolve(root, 'runtime/reports/csi500_swing')
const results = {}
for (const regime of ['bull', 'bear']) {
  const fixture = JSON.parse(readFileSync(resolve(folder, `${regime}_chart_fixture.json`), 'utf8'))
  const dataset = buildIndexQuantFilterDataset(fixture.candles, fixture.params, '中证500', [], [], [], [], false,
    { bearSwingPoints: fixture.points })
  const points = new Map(fixture.points.map(p => [p.trade_date, p.values]))
  assert.ok(CSI500_SWING_FIELDS.every(f => dataset.fields.some(x => x.key === f.key)))
  const colors = {}
  for (const s of dataset.snapshots) {
    for (const { key } of CSI500_SWING_FIELDS) {
      const expected = points.get(s.tradeDate)[key]
      if (expected == null) assert.equal(s.values[key], null)
      else assert.ok(Math.abs(expected - s.values[key]) < 1e-7, `${regime} ${s.tradeDate} ${key}`)
    }
    const red = matchRuleGroupIndexes(s, fixture.rules.red).length > 0
    const blue = matchRuleGroupIndexes(s, fixture.rules.blue).length > 0
    if (red || blue) colors[s.tradeDate] = red && blue ? 'purple' : red ? 'red' : 'blue'
  }
  assert.deepEqual(colors, fixture.expected_colors)
  const prefix = buildIndexQuantFilterDataset(fixture.candles.slice(0, -30), fixture.params, '中证500', [], [], [], [], false,
    { bearSwingPoints: fixture.points.slice(0, -30) })
  assert.deepEqual(prefix.snapshots.map(s => Object.fromEntries(CSI500_SWING_FIELDS.map(f => [f.key, s.values[f.key]]))),
    dataset.snapshots.slice(0, -30).map(s => Object.fromEntries(CSI500_SWING_FIELDS.map(f => [f.key, s.values[f.key]]))))
  results[regime] = { dates: dataset.snapshots.length, all_daily_signals_match: true, future_append_unchanged: true }
}
writeFileSync(resolve(folder, 'frontend_verification.json'), JSON.stringify(results, null, 2) + '\n')
console.log(JSON.stringify(results, null, 2))
