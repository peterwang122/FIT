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
    export { BEAR_SWING_FIELDS } from './frontend/src/utils/bearSwing';`, resolveDir: root, loader: 'ts' },
  bundle: true, write: false, platform: 'node', format: 'esm',
})
const { buildIndexQuantFilterDataset, matchRuleGroupIndexes, BEAR_SWING_FIELDS } = await import(
  `data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].text).toString('base64')}`)
const folder = resolve(root, 'runtime/reports/csi1000_bear_swing_coverage')
const rows = JSON.parse(readFileSync(resolve(folder, 'features.json'), 'utf8')).data
const report = JSON.parse(readFileSync(resolve(folder, 'report.json'), 'utf8'))
const saved = JSON.parse(readFileSync(resolve(folder, 'saved.json'), 'utf8'))
const fields = BEAR_SWING_FIELDS.map(x => x.key)
const candles = rows.map(row => ({ ...row, trade_date: row.index }))
const points = rows.map(row => ({ trade_date: row.index,
  values: Object.fromEntries(fields.map(field => [field, row[field]])), as_of_at: `${row.index}T22:30:00+08:00` }))
const results = {}
const match = (row, groups) => groups.some(g => g.conditions.every(c => {
  const v = row[c.field]
  if (v == null) return false
  return ({ gte: v >= c.value, lte: v <= c.value, gt: v > c.value, lt: v < c.value })[c.operator]
}))
for (const [name, model] of Object.entries(report.models)) {
  const params = saved.find(r => r.id === model.strategy_id).indicator_params
  const dataset = buildIndexQuantFilterDataset(candles, params, '中证1000', [], [], [], [], false, { bearSwingPoints: points })
  const colors = {}
  for (const [i,s] of dataset.snapshots.entries()) {
    const row = rows[i]
    assert.equal(s.tradeDate, row.index)
    for (const k of ['wr','rsi',...fields]) {
      if (row[k] == null) assert.equal(s.values[k], null)
      else assert.ok(Math.abs(row[k]-s.values[k])<1e-6, `${name} ${row.index} ${k}`)
    }
    const red = matchRuleGroupIndexes(s, model.rule).length > 0
    const blue = matchRuleGroupIndexes(s, model.blue_rule).length > 0
    assert.equal(red, match(row, model.rule), `${name} ${row.index} red`)
    assert.equal(blue, match(row, model.blue_rule), `${name} ${row.index} blue`)
    if (row.index >= model.start_date && (red || blue)) colors[row.index] = red && blue ? 'purple' : red ? 'red' : 'blue'
  }
  for (const bottom of model.bottoms) assert.equal(colors[bottom.date], 'red', `${name} ${bottom.date}`)
  results[name] = { dates: rows.length, extreme_red_count: model.bottoms.length, all_daily_signals_match: true }
}
writeFileSync(resolve(folder, 'frontend_verification.json'), JSON.stringify(results,null,2)+'\n')
console.log(JSON.stringify(results,null,2))
