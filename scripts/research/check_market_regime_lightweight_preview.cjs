const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const out = path.resolve('runtime/research/market_regime');
  const browser = await chromium.launch({ headless: true, ...(fs.existsSync(chromium.executablePath()) ? {} : { channel: 'chrome' }) });
  const results = [];
  try {
    for (const [width, height] of [[1440, 900], [1280, 800], [1000, 800], [390, 844]]) {
      const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.goto('file://' + path.join(out, 'lightweight-preview.html'));
      await page.waitForFunction(() => window.researchPreview);
      const before = await page.locator('#evidence').innerText();
      const box = await page.locator('#chart').boundingBox();
      await page.mouse.move(box.x + box.width * .65, box.y + 90);
      if (before !== await page.locator('#evidence').innerText()) throw new Error('Hover changed monthly evidence');
      if (await page.locator('#day').innerText() !== await page.locator('#review-day').innerText()) throw new Error('Review date mismatch');
      await page.mouse.move(0, 0);
      for (const group of ['loans', 'activity', 'profit', 'money']) {
        await page.selectOption('#group', group);
        if (!await page.locator('#evidence tr').count()) throw new Error('Empty evidence view');
      }
      const metrics = await page.evaluate(() => ({
        overflow: document.documentElement.scrollWidth > innerWidth,
        logo: document.querySelector('.brand-logo').naturalWidth > 0,
        title: document.querySelector('.site-header h1').textContent,
        coloredPixels: Array.from(document.querySelectorAll('#chart canvas')).reduce((sum, c) => {
          const data = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
          for (let i = 0; i < data.length; i += 4) {
            if (data[i + 3] > 200 && Math.max(data[i], data[i + 1], data[i + 2]) - Math.min(data[i], data[i + 1], data[i + 2]) > 60) sum++;
          }
          return sum;
        }, 0),
      }));
      if (metrics.overflow || !metrics.logo || metrics.coloredPixels < 200 || errors.length) throw new Error(JSON.stringify({ width, ...metrics, errors }));
      await page.screenshot({ path: path.join(out, `lightweight-${width}x${height}.png`), fullPage: true });
      await page.screenshot({ path: path.join(out, `lightweight-viewport-${width}x${height}.png`) });
      results.push({ width, height, ...metrics, errors, interactions: 'passed' });
      await page.close();
    }
    fs.writeFileSync(path.join(out, 'lightweight-preview-checks.json'), JSON.stringify(results, null, 2));
    console.log(JSON.stringify(results, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
