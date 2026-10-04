import assert from 'node:assert/strict'
import { readFileSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const require = createRequire(resolve(root, 'frontend/package.json'))
const { build } = require('esbuild')
const bundle = await build({
  stdin: {
    contents: `export { buildIndexQuantFilterDataset } from './frontend/src/utils/quantIndicators';
      export { matchRuleGroupIndexes } from './frontend/src/utils/quantRuleGroups';
      export { BEAR_SWING_FIELDS } from './frontend/src/utils/bearSwing';`,
    resolveDir: root,
    loader: 'ts',
  },
  bundle: true,
  write: false,
  platform: 'node',
  format: 'esm',
})
const { buildIndexQuantFilterDataset, matchRuleGroupIndexes, BEAR_SWING_FIELDS } = await import(
  `data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].text).toString('base64')}`
)
const folder = resolve(root, 'runtime/reports/csi1000_bear_swing')
const rows = JSON.parse(readFileSync(resolve(folder, 'features.json'), 'utf8')).data
const report = JSON.parse(readFileSync(resolve(folder, 'report.json'), 'utf8'))
const fields = BEAR_SWING_FIELDS.map((field) => field.key)
const candles = rows.map((row) => ({ ...row, trade_date: row.index }))
const points = rows.map((row) => ({
  trade_date: row.index,
  values: Object.fromEntries(fields.map((field) => [field, row[field]])),
  as_of_at: `${row.index}T22:30:00+08:00`,
}))
const params = {
  ma: { periods: [5, 10, 20, 60] },
  macd: { fast: 12, slow: 26, signal: 9 },
  kdj: { period: 9, kSmoothing: 3, dSmoothing: 3 },
  wr: { period: 14 },
  rsi: { period: 14 },
  boll: { period: 20, multiplier: 2 },
}
const dataset = buildIndexQuantFilterDataset(candles, params, '中证1000', [], [], [], [], false, {
  bearSwingPoints: points,
})
assert.equal(dataset.snapshots.length, rows.length)
const counts = Object.fromEntries(Object.keys(report.models).map((name) => [name, { red: 0, blue: 0, purple: 0 }]))
function researchMatch(row, conditions) {
  return conditions.every(({ field, operator, value }) => {
    const actual = row[field]
    if (actual == null) return false
    if (operator === 'gte') return actual >= value
    if (operator === 'lte') return actual <= value
    if (operator === 'gt') return actual > value
    if (operator === 'lt') return actual < value
    throw new Error(`Unsupported research operator ${operator}`)
  })
}
for (const [i, snapshot] of dataset.snapshots.entries()) {
  const row = rows[i]
  assert.equal(snapshot.tradeDate, row.index)
  for (const field of [...fields, 'wr']) {
    const actual = snapshot.values[field]
    const expected = row[field]
    if (expected == null) assert.equal(actual, null, `${row.index} ${field}`)
    else assert.ok(Math.abs(actual - expected) < 1e-6, `${row.index} ${field}: ${actual} != ${expected}`)
  }
  for (const [name, model] of Object.entries(report.models)) {
    const red = matchRuleGroupIndexes(snapshot, [{ conditions: model.low.conditions }]).length > 0
    const blue = matchRuleGroupIndexes(snapshot, [{ conditions: model.high.conditions }]).length > 0
    assert.equal(red, researchMatch(row, model.low.conditions), `${name} ${row.index} red`)
    assert.equal(blue, researchMatch(row, model.high.conditions), `${name} ${row.index} blue`)
    if (row.index >= model.start_date && (red || blue)) {
      counts[name][red && blue ? 'purple' : red ? 'red' : 'blue'] += 1
    }
  }
}
const verification = { dates: rows.length, fields: [...fields, 'wr'], all_daily_signals_match: true, counts }
writeFileSync(resolve(folder, 'frontend_verification.json'), JSON.stringify(verification, null, 2) + '\n')
console.log(JSON.stringify(verification, null, 2))
