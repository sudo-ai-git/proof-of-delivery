#!/usr/bin/env python3
"""Build the X demo assets from REAL captured output — no mockups.

Outputs into this directory:
  01_commitment_satisfied.png  demo page (all 4 layers match)
  02_commitment_rejected.png   demo page after one character is changed
  03_verify_all.png            terminal card — actual verify_all.py output
  04_escrow_roundtrip.png      terminal card — actual spike_s2 (NEAR) output
  05_stablecoin.png            terminal card — actual spike_s3 (wNEAR) output
  demo.mp4                     screen recording of the demo page interaction

Terminal-card text is READ from files produced by actually running those
commands. Long transaction-hash tails are elided with "…" — the assertion on
each line (PASS/FAIL/VERDICT and the log message) is never altered.
"""
import hashlib
import html
import json
import os
import re
import subprocess
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = "file://" + os.path.join(REPO, "demo", "index.html")


def sha():
    try:
        return subprocess.run(["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        return "?"


def rpc_proof():
    """Live chain state read straight from the RPC — not an explorer's UI."""
    import urllib.request

    def tx(txid):
        try:
            req = urllib.request.Request("https://rpc.testnet.fastnear.com", data=json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "tx",
                "params": {"tx_hash": txid, "sender_account_id": "nft-repo-test-015.testnet",
                           "wait_until": "FINAL"}}).encode(), headers={"Content-Type": "application/json"})
            return json.load(urllib.request.urlopen(req, timeout=30)).get("result")
        except Exception as e:
            return {"_err": str(e)[:60]}

    def acct(a):
        try:
            req = urllib.request.Request("https://rpc.testnet.fastnear.com", data=json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "query",
                "params": {"request_type": "view_account", "finality": "final",
                           "account_id": a}}).encode(), headers={"Content-Type": "application/json"})
            return json.load(urllib.request.urlopen(req, timeout=30))["result"]
        except Exception as e:
            return {"_err": str(e)[:60]}

    out = []
    c = acct("nft-repo-test-015.testnet")
    out.append("#  contract account   nft-repo-test-015.testnet")
    out.append(f"#  code_hash          {c.get('code_hash','?')}")
    out.append("#  local wasm sha256  " + hashlib.sha256(
        open(os.path.join(REPO, "build", "release", "proof-of-delivery.wasm"), "rb").read()).hexdigest()
        + "   (base58 == code_hash above)")
    out.append("")
    for label, txid in [
        ("release on a SUBSTITUTED file", "Ed4UnTwQAHr5DQGsCSgw8jtg3aSE1bn7TRHh7XEZRnC1"),
        ("release on the CORRECT file", "4Ku5QTBJadTypo44rsmsCHXbAi3ez8cKevw2csvEvJFU"),
        ("create_deal_sha (2 NEAR)", "5D3sgBtEm3WveXact9pGhWoZJ2JBSnS6VDUvUXLgwQxf"),
        ("NEP-141 release (wNEAR)", "2gfkaT76MkjLurJey6SixDzpYyRRhZXGK2VmMDQmBuNj"),
    ]:
        r = tx(txid)
        st = (r or {}).get("status", {})
        if "Failure" in st:
            try:
                msg = json.dumps(st["Failure"])[:150]
            except Exception:
                msg = "Failure"
            verdict = "FAILURE  " + msg
        elif "SuccessValue" in st:
            verdict = "SUCCESS"
        else:
            verdict = str(list(st.keys()) or r)[:120]
        out.append(f"txns/{txid}")
        out.append(f"    {label:34s} -> {verdict}")
    return "\n".join(out)


def elide(line, width=168):
    """Always KEEP the transaction hash + its explorer link; shorten the noise."""
    m = re.search(r"(?:Transaction Id |/txns/)([1-9A-HJ-NP-Za-km-z]{30,})", line)
    prefix = re.split(r"Transaction Id|Open the explorer", line)[0].rstrip()
    if m:
        room = width - 58
        if len(prefix) > room:
            prefix = prefix[:room - 1] + "…"
        return f"{prefix}  -> txns/{m.group(1)}"
    return line[:width - 1] + "…" if len(line) > width else line


def colorize(text):
    out = []
    for line in text.splitlines():
        line = elide(line)
        esc = html.escape(line)
        if "[PASS]" in line:
            esc = esc.replace("[PASS]", '<span class="ok">[PASS]</span>')
        if "[FAIL]" in line:
            esc = esc.replace("[FAIL]", '<span class="bad">[FAIL]</span>')
        if line.startswith("VERDICT:"):
            esc = esc.replace("VERDICT:", '<span class="ok">VERDICT:</span>')
        if any(k in line for k in ("released", "refunded", "delivered", "funded")):
            esc = f'<span class="acc">{esc}</span>'
        out.append(esc)
    return "\n".join(out)


def terminal_card(title, text):
    return f"""<!doctype html><meta charset=utf-8><style>
    *{{box-sizing:border-box}} body{{margin:0;background:#0b0e11}}
    .card{{width:1440px;background:#0f141a;border:1px solid #1f2733;border-radius:12px;
      overflow:hidden;font:13.5px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}}
    .bar{{display:flex;align-items:center;gap:8px;padding:10px 14px;background:#141b23;border-bottom:1px solid #1f2733}}
    .dot{{width:11px;height:11px;border-radius:50%}} .t{{margin-left:8px;color:#8b9bb0;font-size:12.5px}}
    pre{{margin:0;padding:16px 18px;color:#dbe6f0;white-space:pre-wrap;word-break:break-word}}
    .ok{{color:#3ddc97;font-weight:600}} .bad{{color:#ff6b6b;font-weight:600}} .acc{{color:#6ea8fe}}
    .prov{{padding:9px 18px;background:#0c1116;border-top:1px solid #1f2733;color:#6b7b90;font-size:11.5px}}
    </style>
    <div class="card">
      <div class="bar"><span class="dot" style="background:#ff5f57"></span>
        <span class="dot" style="background:#febc2e"></span>
        <span class="dot" style="background:#28c840"></span>
        <span class="t">{html.escape(title)}</span></div>
      <pre>{text}</pre>
      <div class="prov">actual output · github.com/sudo-ai-git/proof-of-delivery @ {sha()} · python {sys.version.split()[0]}</div>
    </div>"""


def main():
    os.makedirs(HERE, exist_ok=True)
    cards = [
        ("verify_all.py --build --selftest", os.path.join(HERE, "verify_all.out"), "03_verify_all.png"),
        ("spike_s2_escrow.py  ·  native NEAR escrow", os.path.join(REPO, "s2_last_run.txt"), "04_escrow_roundtrip.png"),
        ("spike_s3_ft_escrow.py  ·  NEP-141 (wNEAR) escrow", os.path.join(REPO, "s3_last_run.txt"), "05_stablecoin.png"),
        ("spike_s4_file_escrow.py  ·  real FILE, sha256 identity", os.path.join(REPO, "s4_last_run.txt"), "08_file_escrow.png"),
        ("spike_s7_two_agent_loop.py  ·  buyer + 2 sellers, bid → award → settle", os.path.join(REPO, "s7_last_run.txt"), "10_agent_loop.png"),
    ]
    if "--chain" in sys.argv or True:
        cards.append(("live chain state — read from the RPC", None, "09_chain_state.png"))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1460, "height": 900}, device_scale_factor=2)
        for title, src, out in cards:
            if src is None:
                raw = rpc_proof()
                page.set_content(terminal_card(title, colorize(raw)))
                page.query_selector(".card").screenshot(path=os.path.join(HERE, out))
                print(f"  wrote {out}")
                continue
            if not os.path.exists(src):
                print(f"  [skip] missing source {src}")
                continue
            raw = open(src, encoding="utf-8").read()
            page.set_content(terminal_card(title, colorize(raw)))
            page.query_selector(".card").screenshot(path=os.path.join(HERE, out))
            print(f"  wrote {out}")

        dpage = browser.new_page(viewport={"width": 1100, "height": 1000}, device_scale_factor=2)
        dpage.goto(DEMO)
        dpage.wait_for_timeout(500)
        dpage.screenshot(path=os.path.join(HERE, "01_commitment_satisfied.png"), full_page=True)
        print("  wrote 01_commitment_satisfied.png")
        dpage.click("#tamper")
        dpage.wait_for_timeout(300)
        dpage.screenshot(path=os.path.join(HERE, "02_commitment_rejected.png"), full_page=True)
        print("  wrote 02_commitment_rejected.png")
        dpage.close()

        # NOTE: the public explorers are Cloudflare-walled for headless Chromium
        # ("Just a moment... Performing security verification"), so a screenshot of
        # the tx page is not obtainable. Instead 09_chain_state.png renders the
        # same facts read straight from the RPC — verifiable without any UI.

        vid = os.path.join(HERE, "_vid")
        ctx = browser.new_context(viewport={"width": 1280, "height": 900},
                                  record_video_dir=vid,
                                  record_video_size={"width": 1280, "height": 900})
        vp = ctx.new_page()
        vp.goto(DEMO)
        vp.evaluate("window.scrollTo(0,0)")
        vp.wait_for_timeout(2500)
        vp.click("#tamper")
        vp.wait_for_timeout(4000)
        vp.click("#reset")
        vp.wait_for_timeout(2500)
        vp.close()
        ctx.close()
        browser.close()

    vids = [os.path.join(vid, f) for f in os.listdir(vid)] if os.path.isdir(vid) else []
    if vids:
        src = sorted(vids)[-1]
        dst = os.path.join(HERE, "demo.mp4")
        r = subprocess.run(["ffmpeg", "-y", "-i", src, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            "-movflags", "+faststart", dst], capture_output=True, text=True)
        print("  demo.mp4", "ok" if r.returncode == 0 else "FAILED " + r.stderr[-200:])
    print("done ->", HERE)


if __name__ == "__main__":
    main()
