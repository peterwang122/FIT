import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const runtime = process.env.CODEX_NODE_MODULES ?? '/Users/wanghequan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
const { chromium } = createRequire(resolve(runtime, 'playwright/package.json'))('playwright')
const report = JSON.parse(readFileSync(resolve(root, 'docs/research/ashare_outlook_2026-10-04.json'), 'utf8'))
const baseUrl = process.env.FIT_BROWSER_URL ?? 'http://127.0.0.1:5173'
const folder = resolve(root, 'runtime/reports/ashare_outlook/2026-10-04/browser/financing-t1-v5')
mkdirSync(folder, { recursive: true })
const result = { mode: 'isolated browser with fixture auth/API; not production deployment proof',
  report_version: report.version, checked_at: new Date().toISOString(), viewports: [] }
const browser = await chromium.launch({ channel: 'chrome', headless: true })

function user(role = 'user') {
  return { id: 999999, username: 'research-verification', role, nickname: '研究验证', phone: null,
    has_password: false, email: null, company: '', bio: '', created_at: null, last_login_at: null,
    preferences: { theme: 'light', language: 'zh-CN', notifications_enabled: false, default_homepage: '/' } }
}

async function fixture(page, state) {
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    assert.equal(route.request().method(), 'GET', `Unexpected write request: ${path}`)
    let payload
    if (path === '/api/v1/auth/me') payload = { user: user(state.role) }
    else if (path === '/api/v1/notifications') payload = { items: [], unread_count: 0 }
    else if (path === '/api/v1/research/ashare-outlook') {
      state.reportRequests++
      if (state.fail) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: '研究文件暂不可用' }) })
      payload = report
    } else {
      state.otherRequests.push(path)
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, message: 'fixture', data: {} }) })
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, message: 'fixture', data: payload }) })
  })
}

async function layout(page) {
  return page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
    chartWidth: document.querySelector('.chart-canvas')?.getBoundingClientRect().width,
    articleWidth: document.querySelector('.report-body')?.getBoundingClientRect().width,
    title: document.querySelector('.report-head h3')?.textContent }))
}

async function coloredPixels(page, selector = '.chart-canvas') {
  return page.locator(selector).evaluate(host => [...host.querySelectorAll('canvas')].reduce((count, canvas) => {
    const context = canvas.getContext('2d')
    if (!context || !canvas.width || !canvas.height) return count
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data
    for (let i = 0; i < pixels.length; i += 16) {
      const [r, g, b, a] = pixels.slice(i, i + 4)
      if (a > 0 && ((r > 160 && g < 130 && b < 140) || (g > 120 && r < 90 && b < 190) || (b > 140 && r < 90 && g < 150))) count++
    }
    return count
  }, 0))
}

try {
  for (const [width, height] of [[1440, 900], [1280, 800], [960, 800], [390, 844]]) {
    const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1 })
    const page = await context.newPage()
    const errors = []
    const state = { role: 'user', fail: false, reportRequests: 0, otherRequests: [] }
    page.on('pageerror', error => errors.push(error.message))
    await fixture(page, state)
    await page.goto(`${baseUrl}/research/ashare-outlook`, { waitUntil: 'networkidle' })
    try {
      await page.getByRole('heading', { name: report.title }).waitFor()
    } catch (error) {
      await page.screenshot({ path: resolve(folder, `failure-${width}.png`) })
      console.log(JSON.stringify({ url: page.url(), title: await page.title(), body: (await page.locator('body').innerText()).slice(0, 3000), state, errors }))
      throw error
    }
    await page.locator('.chart-canvas canvas').first().waitFor()
    assert.ok((await page.locator('.quality-notice').innerText()).includes('正常发布滞后，可用'))
    assert.equal(await page.locator('.research-section').count(), report.sections.length + 2)
    assert.equal(await page.locator('.extension-evidence').count(), report.sections.reduce((n, s) => n + (s.tables?.length ?? 0), 0))
    await page.locator('#outlook-synthesis').waitFor()
    assert.equal(await page.locator('.research-paragraph').count(), report.sections.reduce((n, s) => n + s.paragraphs.length, 0))
    const dimensions = await layout(page)
    assert.ok(dimensions.scrollWidth <= width, JSON.stringify(dimensions))
    assert.ok(dimensions.chartWidth > 200)
    const colored = await coloredPixels(page)
    assert.ok(colored > 80, `Blank chart: ${width}, ${colored}`)
    await page.screenshot({ path: resolve(folder, `top-${width}x${height}.png`) })

    for (const index of report.indexes) {
      const button = page.getByRole('button', { name: index.index_name, exact: true })
      await button.click()
      assert.equal(await button.getAttribute('aria-pressed'), 'true')
      assert.ok((await page.locator('.chart-facts').innerText()).includes(index.index_name))
      assert.ok(await coloredPixels(page) > 80)
    }
    await page.locator('.chart-canvas').scrollIntoViewIfNeeded()
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
    const legendBefore = await page.locator('.chart-legend').innerText()
    const legendTextBefore = await page.locator('.chart-legend').textContent()
    const box = await page.locator('.chart-canvas').boundingBox()
    await page.mouse.move(box.x + box.width * .4, box.y + 140, { steps: 3 })
    await page.waitForFunction(before => document.querySelector('.chart-legend')?.textContent !== before, legendTextBefore, { timeout: 3000 })
    const legendDuring = await page.locator('.chart-legend').innerText()
    assert.notEqual(legendDuring, legendBefore, 'Crosshair should update the date and values')
    await page.mouse.move(0, 0)
    assert.equal(await page.locator('.chart-legend').innerText(), legendBefore)
    const checkbox = page.getByRole('checkbox', { name: /MA60/ })
    await checkbox.uncheck()
    assert.equal(await checkbox.isChecked(), false)
    await checkbox.check()
    assert.equal(await checkbox.isChecked(), true)
    assert.equal(state.reportRequests, 1, 'Local chart interactions must not refetch the report')
    assert.deepEqual(state.otherRequests, [])

    await page.locator('#outlook-history').scrollIntoViewIfNeeded()
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
    assert.ok((await page.locator('#outlook-history').innerText()).includes('贵州茅台'))
    assert.ok((await page.locator('#outlook-history').innerText()).includes('27.08%'))
    const historyPixels = await coloredPixels(page, '.historical-canvas')
    assert.ok(historyPixels > 80, 'Historical chart must not be blank')
    const historyCheckbox = page.locator('.historical-legend').getByRole('checkbox').first()
    await historyCheckbox.uncheck()
    assert.equal(await historyCheckbox.isChecked(), false)
    await historyCheckbox.check()
    const historyDateBefore = await page.locator('.chart-date').innerText()
    const historyBox = await page.locator('.historical-canvas').boundingBox()
    await page.mouse.move(historyBox.x + historyBox.width * .5, historyBox.y + 120)
    await page.waitForFunction(before => document.querySelector('.chart-date')?.textContent !== before, historyDateBefore)
    await page.mouse.move(0, 0)
    await page.screenshot({ path: resolve(folder, `history-${width}x${height}.png`) })
    assert.ok((await layout(page)).scrollWidth <= width, 'Historical tables must not overflow the page')
    assert.equal(state.reportRequests, 1)

    await page.locator('.contents a[href="#outlook-money"]').click()
    await page.locator('#outlook-money').scrollIntoViewIfNeeded()
    assert.ok((await page.locator('#outlook-money').innerText()).includes('M1同比'))
    await page.screenshot({ path: resolve(folder, `macro-${width}x${height}.png`) })
    for (const sectionId of ['synthesis', 'relay', 'stock_funding', 'macro_transmission', 'conditional_bottom', 'cross_listing', 'policy_delivery', 'gap_audit']) {
      const section = page.locator(`#outlook-${sectionId}`)
      await section.evaluate(element => element.scrollIntoView({ block: 'start', behavior: 'instant' }))
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
      assert.ok(await section.locator('.extension-evidence').count() > 0)
      assert.ok((await section.locator('h4').boundingBox()).y >= 84, `${sectionId} heading must clear the fixed header`)
      assert.ok((await layout(page)).scrollWidth <= width, `${sectionId} must not overflow the page`)
      await page.screenshot({ path: resolve(folder, `${sectionId}-${width}x${height}.png`) })
    }
    assert.ok((await page.locator('#outlook-stock_funding').innerText()).includes('429.77'))
    assert.ok((await page.locator('#outlook-stock_funding').innerText()).includes('510500'))
    assert.ok((await page.locator('#outlook-stock_funding').innerText()).includes('正常T-1不算缺失'))
    assert.ok((await page.locator('#outlook-cross_listing').innerText()).includes('124.53'))
    assert.ok((await page.locator('#outlook-gap_audit').innerText()).includes('来源阻断'))
    assert.ok((await page.locator('#outlook-macro_transmission').innerText()).includes('60.91%'))
    await page.locator('#outlook-commodities').scrollIntoViewIfNeeded()
    assert.ok((await page.locator('#outlook-commodities').innerText()).includes('Au99.99'))
    await page.locator('#outlook-limits summary').click()
    assert.ok(await page.locator('#outlook-limits details').getAttribute('open') !== null)
    assert.ok((await page.locator('#outlook-limits').innerText()).includes('待验证'))
    await page.locator('#outlook-sources summary').first().click()
    assert.equal(await page.locator('.source-list > div').count(), report.sources.length)
    assert.ok((await page.locator('.source-list').innerText()).includes('发布时间未核验'))
    assert.deepEqual(errors, [])
    result.viewports.push({ width, height, ...dimensions, colored_pixels: colored, all_indexes_switched: true,
      hover_updates_locally: true, checkbox_works: true, history_chart_pixels: historyPixels, historical_comparison_verified: true,
      synthesis_and_extension_tables_verified: true, sources_complete: true, runtime_errors: errors })
    await context.close()
  }

  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } })
  const page = await context.newPage()
  const state = { role: 'user', fail: true, reportRequests: 0, otherRequests: [] }
  await fixture(page, state)
  await page.goto(`${baseUrl}/research/ashare-outlook`)
  await page.getByRole('alert').waitFor()
  assert.ok((await page.getByRole('alert').innerText()).includes('研究文件暂不可用'))
  state.fail = false
  await page.getByRole('button', { name: '重新加载' }).click()
  await page.getByRole('heading', { name: report.title }).waitFor()
  result.error_retry_verified = true
  await context.close()

  const guestContext = await browser.newContext()
  const guest = await guestContext.newPage()
  await fixture(guest, { role: 'guest', fail: false, reportRequests: 0, otherRequests: [] })
  await guest.goto(`${baseUrl}/research/ashare-outlook`)
  await guest.waitForURL(`${baseUrl}/`)
  result.guest_redirect_verified = true
  await guestContext.close()
  writeFileSync(resolve(folder, 'verification.json'), JSON.stringify(result, null, 2) + '\n')
  console.log(JSON.stringify(result, null, 2))
} finally {
  await browser.close()
}
