const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const out = path.resolve('runtime/research/market-regime-20260906');
  const options = fs.existsSync(chromium.executablePath()) ? {} : { channel: 'chrome' };
  const browser = await chromium.launch({ headless: true, ...options });
  const results = [];
  try {
    for (const [width, height] of [[1440, 900], [1280, 800], [1000, 800]]) {
      const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
      const errors = [];
      let stage = 'initial';
      page.on('pageerror', e => errors.push(`${stage}: ${e.stack || e}`));
      await page.goto('file://' + path.join(out, 'market-regime-preview.html'));
      await page.waitForFunction(() => Boolean(window.regimePreview));
      await page.screenshot({ path: path.join(out, `preview-${width}x${height}.png`), fullPage: true });
      await page.screenshot({ path: path.join(out, `preview-viewport-${width}x${height}.png`) });
      const metrics = await page.evaluate(() => ({
        overflow: document.documentElement.scrollWidth > window.innerWidth,
        canvasCount: document.querySelectorAll('canvas').length,
        title: document.querySelector('.site-header h1').textContent,
        logoLoaded: document.querySelector('.brand-logo').naturalWidth > 0,
        state: document.querySelector('#state').textContent,
        committed: document.querySelector('#confirmed-date').value,
        coloredChartPixels: Array.from(document.querySelectorAll('#chart canvas')).reduce((sum, canvas) => {
          const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
          for (let i = 0; i < pixels.length; i += 4) {
            if (pixels[i + 3] > 200 && Math.max(...pixels.slice(i, i + 3)) - Math.min(...pixels.slice(i, i + 3)) > 60) sum++;
          }
          return sum;
        }, 0),
      }));
      if (metrics.overflow || !metrics.logoLoaded || metrics.coloredChartPixels < 500) throw new Error(JSON.stringify(metrics));
      stage = 'date confirmation';
      await page.locator('#confirmed-date').fill('2025-03-19');
      await page.locator('#confirmed-date').dispatchEvent('change');
      if (!(await page.locator('#locked-date').innerText()).includes('2025-03-19')) throw new Error('Date confirmation failed');
      const box = await page.locator('#chart').boundingBox();
      stage = 'crosshair';
      await page.mouse.move(box.x + box.width * .70, box.y + 60);
      if (!(await page.locator('#locked-date').innerText()).includes('2025-03-19')) throw new Error('Hover moved evidence');
      const hoverDate = await page.locator('#date').innerText();
      if (hoverDate === '2025-03-19' || !hoverDate) throw new Error('Hover did not update summary');
      if ((await page.locator('#review-date').innerText()) !== hoverDate) throw new Error('Hover did not update review');
      await page.mouse.click(box.x + box.width * .70, box.y + 60);
      const clicked = await page.locator('#confirmed-date').inputValue();
      if (clicked !== hoverDate) throw new Error('Chart click failed to confirm');
      await page.mouse.move(0, 0);
      if (!(await page.locator('#date').innerText()).includes(clicked)) throw new Error('Mouse leave did not restore date');
      stage = 'select all share';
      await page.selectOption('#index', 'sh000985');
      if ((await page.locator('#index-name').innerText()) !== '中证全指') throw new Error('Index selection failed');
      stage = 'select csi1000';
      await page.selectOption('#index', 'sh000852');
      await page.locator('#confirmed-date').fill('2025-04-09');
      await page.locator('#confirmed-date').dispatchEvent('change');
      await page.screenshot({ path: path.join(out, `preview-history-${width}x${height}.png`), fullPage: true });
      await page.screenshot({ path: path.join(out, `preview-history-viewport-${width}x${height}.png`) });
      stage = 'event selection and zoom';
      const eventDate = await page.locator('#events tr[data-date]').first().getAttribute('data-date');
      await page.locator('#events tr[data-date]').first().click();
      if ((await page.locator('#confirmed-date').inputValue()) !== eventDate) throw new Error('Event confirmation failed');
      const zoom = await page.evaluate(() => window.regimePreview.chart.timeScale().getVisibleRange());
      if (!(zoom.from < eventDate && zoom.to > eventDate)) throw new Error('Event was not centered');
      if (errors.length) throw new Error(errors.join('\n'));
      results.push({ width, height, ...metrics, errors, interactions: 'passed' });
      await page.close();
    }
    fs.writeFileSync(path.join(out, 'preview-verification.json'), JSON.stringify(results, null, 2));
    console.log(JSON.stringify(results, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
