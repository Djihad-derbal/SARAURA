"""PDF Report (ADR-0007): headless Chromium (Playwright) prints the frontend's /report/<id> page.

The page sets data-report-ready on <body> when its maps and charts have loaded; the PDF is taken then.
Install once: python -m playwright install chromium. The frontend must be running at config.FRONTEND_URL.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Response

from saraura import config

from .study import manifest

router = APIRouter()
READY = "body[data-report-ready]"
TIMEOUT_MS = 90_000


def render_pdf(url: str) -> bytes:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1240, "height": 1754})
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            except PlaywrightError as e:
                raise HTTPException(503, f"The frontend is not reachable at {config.FRONTEND_URL} ({str(e).splitlines()[0][:120]}). Start it with npm run dev in frontend/.")
            try:
                page.wait_for_selector(READY, state="attached", timeout=TIMEOUT_MS)
            except PlaywrightError:
                raise HTTPException(504, "The Report page did not finish loading its maps and charts in time")
            page.emulate_media(media="print")
            return page.pdf(format="A4", print_background=True, prefer_css_page_size=True,
                            margin={"top": "14mm", "bottom": "14mm", "left": "12mm", "right": "12mm"})
        finally:
            browser.close()


@router.post("/report/{study_id}")
def report(study_id: str):
    """The study as a PDF: summary, one section per layer, Model vs Baseline, data sources. No Assistant text."""
    m = manifest(study_id)
    pdf = render_pdf(f"{config.FRONTEND_URL.rstrip('/')}/report/{study_id}")
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", m.get("name") or study_id)[:60]
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="SARAURA_{name}.pdf"'})
