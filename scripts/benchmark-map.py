"""Repeatable offline movement workload; frame intervals are not GPU timings."""

from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path

from playwright.sync_api import sync_playwright

WORKLOAD = """async ({mode, duration}) => {
 const atlas=document.querySelector('#atlas'), frames=[], costs=[];
 let previous, start, lastLog=0;
 await new Promise(resolve => {
  function tick(t) {
   start ??= t;
   if(previous !== undefined) frames.push(t-previous);
   previous=t;
   const elapsed=t-start, begin=performance.now();
   const nextLog=.18*Math.sin(elapsed/450), delta=-(nextLog-lastLog)/.0015/4;
   lastLog=nextLog;
   for(let k=0;k<4;k++) {
    if(mode==='zoom') atlas.dispatchEvent(new WheelEvent('wheel', {
     clientX:600,clientY:450,deltaY:delta,bubbles:true,cancelable:true}));
    else atlas.dispatchEvent(new PointerEvent('pointermove', {
     clientX:600+Math.sin(elapsed/500)*180,clientY:450+Math.cos(elapsed/700)*100,
     pointerId:window.benchmarkPointerId,buttons:1,bubbles:true}));
   }
   costs.push(performance.now()-begin);
   if(elapsed<duration) requestAnimationFrame(tick); else resolve();
  }
  requestAnimationFrame(tick);
 });
 const summary=a=>{const s=[...a].sort((a,b)=>a-b);return {
  median_ms:s[Math.floor(s.length*.5)],p95_ms:s[Math.floor(s.length*.95)],
  max_ms:s.at(-1),samples:s.length,over_25ms:s.filter(x=>x>25).length}};
 return {frames:summary(frames),event_work:summary(costs)};
}"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("html", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--browser", choices=["chromium", "firefox", "webkit"], default="chromium")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--duration", type=int, default=2500)
    args = parser.parse_args()
    with sync_playwright() as p:
        browser = getattr(p, args.browser).launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000}, offline=True)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(args.html.resolve().as_uri())
        page.wait_for_function("document.documentElement.dataset.mapReady === 'true'")
        page.evaluate(
            "window.addEventListener('pointerdown',e=>window.benchmarkPointerId=e.pointerId)"
        )
        # Keep the workload comparable with earlier versions whose links defaulted on.
        if page.locator("#show-links").get_attribute("aria-pressed") == "false":
            page.locator("#show-links").click()
        chosen = page.evaluate("""() => {
          const d=JSON.parse(document.querySelector('#map-data').textContent);
          return d.projects.map((p,i)=>({i,v:p.exposure})).sort((a,b)=>b.v-a.v).slice(0,2).map(x=>x.i);
        }""")
        if page.locator("#compromise-mode").count():
            page.locator("#compromise-mode").click()
        for i in chosen:
            page.locator(f"#country-{i}").dispatch_event("click")
        results = []
        for repetition in range(args.repetitions):
            for mode in ("pan", "zoom"):
                page.get_by_role("button", name="Fit whole map").click()
                page.get_by_role("button", name="Zoom in", exact=True).click()
                page.wait_for_timeout(250)
                page.mouse.move(600, 450)
                page.locator(f"#country-{chosen[0]}").dispatch_event(
                    "pointerenter", {"clientX": 600, "clientY": 450}
                )
                if mode == "pan":
                    page.mouse.down()
                results.append(
                    {
                        "mode": mode,
                        "repetition": repetition,
                        **page.evaluate(WORKLOAD, {"mode": mode, "duration": args.duration}),
                    }
                )
                if mode == "pan":
                    page.mouse.up()
                page.wait_for_timeout(250)
        assert not errors, errors
        report = {
            "browser": args.browser,
            "version": browser.version,
            "device": platform.platform(),
            "viewport": [1600, 1000],
            "html_bytes": args.html.stat().st_size,
            "results": results,
            "note": "Headless rAF workload: four input events per frame, two compromises, scenery on. Frame intervals include browser scheduling; not a GPU profile or physical-device FPS guarantee.",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
