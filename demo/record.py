"""Record the SARAURA demo, scene by scene, as JPEG frames with timestamps (Chrome DevTools screencast).

Each scene is loaded first, then recorded, so no loading time is filmed. A drawn cursor and captions are
added to the page; the app itself is unchanged. build.py turns the frames into the final video.
"""
import base64
import json
import math
import shutil
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
FRAMES = HERE / "frames"
BASE = "http://localhost:3001"
W, H = 1920, 1080
ONLY = set(sys.argv[1:])

INIT = r"""
(() => {
  const css = `
    nextjs-portal{display:none!important}
    #demo-cursor{position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;width:30px;height:30px;
      transform:translate(-100px,-100px);filter:drop-shadow(0 2px 4px rgba(0,0,0,.6))}
    .demo-ripple{position:fixed;z-index:2147483646;pointer-events:none;width:16px;height:16px;margin:-8px 0 0 -8px;
      border-radius:50%;border:3px solid #2dd4bf;animation:demo-rip .6s ease-out forwards}
    @keyframes demo-rip{to{transform:scale(4.5);opacity:0}}
    #demo-cap{position:fixed;z-index:2147483645;pointer-events:none;bottom:92px;transform:translateX(-50%);
      max-width:1080px;padding:16px 28px 16px 24px;border-radius:14px;background:rgba(4,17,26,.86);
      border:1px solid rgba(45,212,191,.35);box-shadow:0 10px 40px rgba(0,0,0,.5);backdrop-filter:blur(8px);
      color:#ecfeff;font:500 27px/1.3 var(--font-plex-sans),system-ui,sans-serif;letter-spacing:.005em;
      display:flex;gap:16px;align-items:center;opacity:0;transition:opacity .35s ease}
    #demo-cap::before{content:"";flex:none;width:5px;align-self:stretch;border-radius:3px;background:#2dd4bf}
    #demo-cap small{display:block;font-size:17px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:#5eead4;margin-bottom:3px}
    #demo-end{position:fixed;inset:0;z-index:2147483640;pointer-events:none;display:flex;flex-direction:column;
      align-items:center;justify-content:center;gap:22px;background:radial-gradient(ellipse at center,rgba(6,40,58,.94),rgba(2,8,12,.98));
      color:#ecfeff;text-align:center;opacity:0;transition:opacity .7s ease}
    #demo-end h1{font:700 104px/1 var(--font-orbitron),var(--font-display),system-ui;letter-spacing:.06em;margin:0;
      background:linear-gradient(180deg,#e6fffb,#2dd4bf);-webkit-background-clip:text;color:transparent}
    #demo-end .t{font:500 24px var(--font-plex-mono),monospace;letter-spacing:.32em;color:#5eead4;text-transform:uppercase}
    #demo-end .l{font:400 30px/1.45 var(--font-plex-sans),system-ui;color:#cffafe;max-width:1200px}
    #demo-end .s{font:500 20px var(--font-plex-mono),monospace;letter-spacing:.12em;color:#7dd3c8;margin-top:10px}
  `;
  const add = () => {
    if (document.getElementById('demo-cursor')) return;
    const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
    const c = document.createElement('div'); c.id = 'demo-cursor';
    c.innerHTML = '<svg viewBox="0 0 24 24" width="30" height="30"><path d="M4 2l15 10.5-6.6 1.2 3.9 7.3-2.9 1.5-3.9-7.4L4 19.5z" fill="#fff" stroke="#0b1d26" stroke-width="1.4" stroke-linejoin="round"/></svg>';
    document.documentElement.appendChild(c);
    const pos = window.__demoPos || [-100, -100];
    c.style.transform = `translate(${pos[0] - 4}px,${pos[1] - 2}px)`;
    document.addEventListener('mousemove', e => { window.__demoPos = [e.clientX, e.clientY]; c.style.transform = `translate(${e.clientX - 4}px,${e.clientY - 2}px)`; }, true);
    document.addEventListener('mousedown', e => { const r = document.createElement('div'); r.className = 'demo-ripple';
      r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px'; document.documentElement.appendChild(r); setTimeout(() => r.remove(), 700); }, true);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', add); else add();
  window.__demoCaption = (html, x) => {
    let el = document.getElementById('demo-cap');
    if (!el) { el = document.createElement('div'); el.id = 'demo-cap'; document.documentElement.appendChild(el); }
    if (!html) { el.style.opacity = 0; return; }
    el.style.left = (x || innerWidth / 2) + 'px';
    if (el.style.opacity === '1') { el.style.opacity = 0; setTimeout(() => { el.innerHTML = '<div>' + html + '</div>'; el.style.opacity = 1; }, 300); }
    else { el.innerHTML = '<div>' + html + '</div>'; requestAnimationFrame(() => el.style.opacity = 1); }
  };
  window.__demoEnd = (html) => {
    const el = document.createElement('div'); el.id = 'demo-end'; el.innerHTML = html;
    document.documentElement.appendChild(el); requestAnimationFrame(() => requestAnimationFrame(() => el.style.opacity = 1));
    const cap = document.getElementById('demo-cap'); if (cap) cap.style.opacity = 0;
    const cur = document.getElementById('demo-cursor'); if (cur) cur.style.opacity = 0;
  };
})();
"""


class Scene:
    def __init__(self, pg, name):
        self.pg, self.name = pg, name
        self.dir = FRAMES / name
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir(parents=True)
        self.frames = []
        self.cdp = pg.context.new_cdp_session(pg)

    def _frame(self, p):
        self.frames.append((p["metadata"]["timestamp"], p["data"]))
        try:
            self.cdp.send("Page.screencastFrameAck", {"sessionId": p["sessionId"]})
        except Exception:
            pass

    def __enter__(self):
        self.cdp.on("Page.screencastFrame", self._frame)
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 93, "maxWidth": W, "maxHeight": H, "everyNthFrame": 1})
        self.t0 = time.time()
        return self

    def __exit__(self, *a):
        self.cdp.send("Page.stopScreencast")
        index = []
        for i, (ts, data) in enumerate(self.frames):
            f = f"{i:05d}.jpg"
            (self.dir / f).write_bytes(base64.b64decode(data))
            index.append([f, ts])
        (self.dir / "index.json").write_text(json.dumps({"start": self.t0, "end": time.time(), "frames": index}))
        span = index[-1][1] - index[0][1] if index else 0
        print(f"{self.name}: {len(index)} frames over {span:.1f}s ({len(index) / max(span, 0.01):.0f} fps)")


def glide(pg, x, y, ms=700):
    """Move the drawn cursor smoothly to (x, y)."""
    x0, y0 = pg.evaluate("window.__demoPos || [960, 540]")
    t0 = time.time()
    while True:
        t = min(1.0, (time.time() - t0) * 1000 / ms)
        e = 0.5 - 0.5 * math.cos(math.pi * t)
        pg.mouse.move(x0 + (x - x0) * e, y0 + (y - y0) * e)
        if t >= 1.0:
            break
        pg.wait_for_timeout(8)


def centre(loc):
    b = loc.bounding_box()
    return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2


def glide_click(pg, loc, ms=700, dx=0, dy=0):
    loc.scroll_into_view_if_needed()
    x, y = centre(loc)
    glide(pg, x + dx, y + dy, ms)
    pg.wait_for_timeout(120)
    pg.mouse.click(x + dx, y + dy)


def cap(pg, html, x=None):
    pg.evaluate("([h, x]) => window.__demoCaption(h, x)", [html, x])


def load(pg, path, settle=2500, at=(960, 700)):
    pg.goto(BASE + path, wait_until="networkidle", timeout=180_000)
    pg.wait_for_timeout(1500)
    pg.get_by_text("Drawing the answer map").first.wait_for(state="hidden", timeout=120_000)
    pg.wait_for_timeout(settle)
    pg.mouse.move(*at)
    pg.evaluate("([x, y]) => { window.__demoPos = [x, y]; }", list(at))
    pg.mouse.move(at[0] + 1, at[1])


def flood_spot(pg):
    """A spot inside the flood ("open water most of the season", #2563eb) near the middle of the map."""
    import io
    import numpy as np
    from PIL import Image
    from scipy import ndimage
    a = np.asarray(Image.open(io.BytesIO(pg.screenshot())).convert("RGB")).astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    hit = (b > 120) & (b - r > 80) & (r < 90)  # the two darker blues: water most of / all season
    hit[:, 1480:] = False
    hit[:220] = False
    hit[860:] = False
    hit[:, :420] = False
    dense = ndimage.uniform_filter(hit.astype(float), 25)
    yy, xx = np.mgrid[: dense.shape[0], : dense.shape[1]]
    score = dense - 0.0004 * np.hypot(xx - 850, yy - 560)
    y, x = np.unravel_index(np.argmax(score), score.shape)
    print("flood spot", x, y, round(float(dense[y, x]), 2))
    return float(x), float(y)


MAPX = 750  # middle of the map on place pages (the right panel is 420 px wide)


def scene_intro(pg):
    load(pg, "/", settle=5000, at=(1250, 760))
    with Scene(pg, "1_intro"):
        cap(pg, "<small>NASA-ISRO NISAR · L-band radar</small>Sees the ground through cloud, smoke and night, every 12 days.")
        pg.wait_for_timeout(3000)
        glide_click(pg, pg.get_by_text("Explore the Earth").first, ms=600)
        pg.wait_for_timeout(700)
        cap(pg, "<small>SARAURA</small>Turns it into plain answers, for the people who must decide.")
        pg.wait_for_timeout(900)
        glide(pg, 1730, 165, 700)
        pg.wait_for_timeout(1300)


def scene_jijel(pg):
    load(pg, "/place/algeria_ne_wildfire", at=(1100, 520))
    with Scene(pg, "2_jijel"):
        cap(pg, "<small>Jijel, Algeria · after the August fires</small>Which burned slopes could send mud onto villages this winter?", MAPX)
        pg.wait_for_timeout(700)
        glide_click(pg, pg.get_by_text("Civil protection", exact=True).first, ms=600)
        pg.wait_for_timeout(2200)
        row = pg.get_by_text("Ouled Messaoud", exact=True).last
        glide_click(pg, row, ms=600)
        pg.wait_for_timeout(500)
        cap(pg, "<small>Any village, road or spot</small>The answer there, why, and what to do about it.", MAPX)
        pg.wait_for_timeout(3200)


def scene_okavango(pg):
    load(pg, "/place/okavango_wetland", at=(1100, 560))
    spot = flood_spot(pg)
    with Scene(pg, "3_okavango"):
        cap(pg, "<small>Okavango Delta, Botswana · 11 radar passes</small>Where did the flood reach this season, camp by camp?", MAPX)
        pg.wait_for_timeout(700)
        glide_click(pg, pg.get_by_text("Safari camp or lodge operator", exact=True).first, ms=600)
        pg.wait_for_timeout(1900)
        x, y = spot
        glide(pg, x, y, 700)
        pg.wait_for_timeout(120)
        pg.mouse.click(x, y)
        pg.wait_for_timeout(500)
        cap(pg, "<small>Tap any spot</small>How often it was under water this season, and what to do.", MAPX)
        pg.wait_for_timeout(3200)


def scene_mexico(pg):
    load(pg, "/place/mexico_city_subsidence", at=(1100, 560))
    with Scene(pg, "4_mexico"):
        cap(pg, "<small>Mexico City · parts sink over 2 cm a month</small>Is it safe to build here?", MAPX)
        pg.wait_for_timeout(600)
        glide_click(pg, pg.get_by_text("Home buyer or family", exact=True).first, ms=600)
        pg.wait_for_timeout(2200)
        pg.evaluate("h => window.__demoEnd(h)", END)
        pg.wait_for_timeout(4300)


END = """
<div class="t">NISAR radar, explained</div>
<h1>SARAURA</h1>
<div class="l">20 questions answered from radar, in 4 places.<br>Every answer shows how it was worked out.<br>Every AI Model is scored against a simple Baseline.</div>
<div class="s">WILDFIRE · FLOOD · SUBSIDENCE · EARTHQUAKE</div>
"""

SCENES = [scene_intro, scene_jijel, scene_okavango, scene_mexico]

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", args=["--use-angle=d3d11", "--enable-gpu", "--hide-scrollbars"])
    ctx = b.new_context(viewport={"width": W, "height": H}, device_scale_factor=1)
    ctx.add_init_script(INIT)
    ctx.route("http://127.0.0.1:8000/**", lambda r: r.continue_(url=r.request.url.replace(":8000", ":8001", 1)))
    pg = ctx.new_page()
    pg.on("console", lambda m: m.type == "error" and print("console:", m.text[:160]))
    for s in SCENES:
        if not ONLY or any(k in s.__name__ for k in ONLY):
            s(pg)
    b.close()
