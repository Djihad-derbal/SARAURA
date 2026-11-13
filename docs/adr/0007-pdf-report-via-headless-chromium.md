# PDF Report rendered by headless Chromium; no CSV export

The only export is a PDF Report. A Next.js `/report` page with print CSS is rendered to PDF by Playwright (headless Chromium) running in `api/`. This reuses the app's own MapLibre and Plotly components, so every export looks the same. CSV export from the original handoff is dropped. The trade-off is that `api/` now depends on Chromium.

## Considered Options

- Browser print-to-PDF: no server dependency, but output varies by browser.
- WeasyPrint + matplotlib: no browser, but maps and plots would be redrawn and look different from the app.
