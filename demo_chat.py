#!/usr/bin/env python3
"""Restaurant Agent - chat.

A chat window and nothing else. Prompt in, answer out, which is the interface
John asked for. The test suite is a terminal command, not a tab.

    python3 demo_chat.py

Then open http://localhost:7860

The agent and its vector store are built in a background thread the moment the
server starts, so the first question does not pay for setup. The page shows
"Warming up" until that finishes.

ON THE DISPLAY LAYER, because someone will ask.

The browser parses the agent's reply into a card - the top pick, its reason,
its dietary tags, and any alternatives - instead of printing one block of
monospace. That parsing is presentation only. It reads the exact string
answer() returned, splits it on the FIELD NAMES the agent itself writes - not on
line breaks, because the model is allowed to join the reply onto one line - and
shows nothing that is not in that string. If any line does not match the shape the
agent produces, the whole reply falls back to raw text rather than being
guessed at. The rule is the same one the agent applies to its own model: the
display never invents, and when it is unsure it defers to the original wording.

Standard library only.
"""

import json
import os
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Keep the model resident in Ollama across the whole demo. Ollama's default is
# to unload after 5 minutes idle, which puts a cold start in the middle of a
# presentation. Set before anything imports the client.
os.environ.setdefault("OLLAMA_KEEP_ALIVE", "30m")

PORT = 7860
_lock = threading.Lock()
_state = {"ready": False, "note": "Warming up - building the vector store and loading the model."}


def _warm():
    """Build the corpus, construct the agent, and take one throwaway turn.

    Everything expensive happens once, here, while nobody is watching: the
    embedding model download, the Chroma build, the deep agent construction and
    Ollama pulling the model into memory. Without this the first question of
    the demo pays for all four.
    """
    start = time.time()
    try:
        from restaurant_agent import answer
        with _lock:
            answer("vegan dinner in Aruba")          # discarded on purpose
        _state["note"] = "Ready - warmed in %.0fs" % (time.time() - start)
    except Exception:
        _state["note"] = "Warm-up failed; the first question will be slow. " + \
                         traceback.format_exc().strip().splitlines()[-1]
    _state["ready"] = True


def get_answer(task):
    try:
        from restaurant_agent import answer
    except Exception:
        return ("Could not import the agent.\n\n" + traceback.format_exc() +
                "\nRun this from the repository root, with restaurant_agent/ beside it.")
    try:
        with _lock:
            return answer(task)
    except Exception:
        return "The agent raised, which it is not supposed to:\n\n" + traceback.format_exc()


PAGE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Restaurant Agent</title>
<style>
html[data-theme="graphite"]{
  --bg:#0D0E11; --panel:#16181D; --panel2:#1E2127; --line:#2A2E36;
  --ink:#F1F3F6; --dim:#9BA2AD; --faint:#6C737E;
  --accent:#FFFFFF; --accent-d:#EDEFF2; --btn-fg:#12141A;
  --user-bg:#2A2E36; --user-fg:#F1F3F6;
  --c-price:#C3C9D2; --c-rate:#C3C9D2; --c-diet:#8FD3A8; --warn:#E4C06A;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,sans-serif;
}
:root,
html[data-theme="slate"]{
  --bg:#0A0C10; --panel:#121620; --panel2:#1A1F2B; --line:#262E3C;
  --ink:#E9EDF4; --dim:#98A2B2; --faint:#6A7484;
  --accent:#34D399; --accent-d:#10B981; --btn-fg:#06281E;
  --user-bg:#2A3646; --user-fg:#EAF0F8;
  --c-price:#7DA6F5; --c-rate:#FBBF24; --c-diet:#34D399; --warn:#FBBF24;
}
html[data-theme="navy"]{
  --bg:#0B1220; --panel:#121C2E; --panel2:#182338; --line:#22304A;
  --ink:#E8EEF8; --dim:#93A3BC; --faint:#677894;
  --accent:#F5B547; --accent-d:#E0A23A; --btn-fg:#1A1206;
  --user-bg:#1E3A5F; --user-fg:#E8EEF8;
  --c-price:#7FB0F0; --c-rate:#F5B547; --c-diet:#6FD3A6; --warn:#F5B547;
}
html[data-theme="coral"]{
  --bg:#0C0C0E; --panel:#151517; --panel2:#1D1D20; --line:#2A2A2E;
  --ink:#F0F0F2; --dim:#9A9AA2; --faint:#6B6B73;
  --accent:#FF6B5A; --accent-d:#F0503C; --btn-fg:#FFFFFF;
  --user-bg:#252528; --user-fg:#F0F0F2;
  --c-price:#FF8B7C; --c-rate:#E8B84B; --c-diet:#6FD3A6; --warn:#E8B84B;
}
html[data-theme="light"]{
  --bg:#FFFFFF; --panel:#F8F9FB; --panel2:#F1F3F7; --line:#E1E5EC;
  --ink:#0F172A; --dim:#475569; --faint:#94A3B8;
  --accent:#4F46E5; --accent-d:#4338CA; --btn-fg:#FFFFFF;
  --user-bg:#4F46E5; --user-fg:#FFFFFF;
  --c-price:#1D4ED8; --c-rate:#B45309; --c-diet:#047857; --warn:#B45309;
}
html[data-theme="paper"]{
  --bg:#FFFFFF; --panel:#FAF8F6; --panel2:#F2EFEB; --line:#E4DED7;
  --ink:#2E2A27; --dim:#5C554F; --faint:#94897F;
  --accent:#B85042; --accent-d:#A6463A; --btn-fg:#FFFFFF;
  --user-bg:#B85042; --user-fg:#FFFFFF;
  --c-price:#A6463A; --c-rate:#8A6A1F; --c-diet:#4E6B5C; --warn:#8A6A1F;
}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--ink);display:flex;flex-direction:column;
     font:15px/1.6 var(--sans);-webkit-font-smoothing:antialiased}

/* ---------------------------------------------------------------- header */
header{border-bottom:1px solid var(--line);padding:13px 24px;display:flex;
       align-items:center;gap:13px;flex:0 0 auto;background:var(--panel)}
.mark{width:26px;height:26px;border-radius:7px;background:var(--accent-d);
      display:flex;align-items:center;justify-content:center;flex:0 0 auto;
      font:600 13px var(--sans);color:#fff;letter-spacing:.02em}
header h1{font-size:15px;margin:0;font-weight:600;letter-spacing:-.005em}
header .sub{color:var(--faint);font-size:12px}
header .status{margin-left:auto;font-size:12px;color:var(--dim);display:flex;
               align-items:center;gap:8px;font-variant-numeric:tabular-nums}
#theme{background:var(--panel2);color:var(--dim);border:1px solid var(--line);
       border-radius:7px;padding:3px 7px;font:inherit;font-size:11.5px;cursor:pointer;
       margin-right:4px}
#theme:focus{outline:none;border-color:var(--accent)}
.dot{width:7px;height:7px;border-radius:50%;background:var(--warn);opacity:.9}
.dot.on{background:var(--accent);opacity:1}

/* ------------------------------------------------------------------- log */
#log{flex:1 1 auto;overflow-y:auto;padding:28px 24px 8px}
.inner{max-width:760px;margin:0 auto}
.msg{margin-bottom:22px}
.msg.u{display:flex;justify-content:flex-end}
.u .bub{max-width:78%;padding:11px 15px;border-radius:15px 15px 4px 15px;
        background:var(--user-bg);color:var(--user-fg);font-size:14.5px}

/* --------------------------------------------------------- answer blocks */
.ans{border:1px solid var(--line);border-radius:14px;background:var(--panel);overflow:hidden}
.raw{white-space:pre-wrap;font-family:var(--mono);font-size:12.5px;line-height:1.75;
     padding:15px 17px;color:var(--ink)}

.note{display:flex;gap:10px;padding:11px 16px;font-size:13px;line-height:1.55;
      border-bottom:1px solid var(--line);background:var(--panel2)}
.note .tag{font:600 10px var(--sans);letter-spacing:.09em;text-transform:uppercase;
           flex:0 0 auto;padding-top:2px}
.note.adj .tag{color:var(--accent)} .note.asm .tag{color:var(--warn)}
.note .txt{color:var(--dim)}

.pick{padding:17px 18px 15px}
.pick .name{font-size:19px;font-weight:600;letter-spacing:-.01em;margin:0 0 3px;color:var(--ink)}
.pick .where{color:var(--dim);font-size:13px;margin:0 0 12px}
.facts{display:flex;flex-wrap:wrap;gap:7px;margin:0 0 13px}
.chip{font-size:11.5px;padding:3.5px 9px;border-radius:20px;border:1px solid var(--line);
      color:var(--dim);background:var(--panel2);white-space:nowrap}
.chip.price{color:var(--c-price);border-color:currentColor}
.chip.rate{color:var(--c-rate);border-color:currentColor}
.chip.diet{color:var(--c-diet);border-color:currentColor}
.why{font-size:13.5px;line-height:1.6;color:var(--dim);margin:0;
     padding-left:11px;border-left:2px solid var(--accent)}

.alts{border-top:1px solid var(--line);padding:13px 18px 15px;background:var(--panel2)}
.alts h4{font:600 10px var(--sans);letter-spacing:.09em;text-transform:uppercase;
         color:var(--faint);margin:0 0 10px}
.alt{padding:8px 0;border-top:1px solid var(--line)}
.alt:first-of-type{border-top:0;padding-top:0}
.alt .n{font-size:14px;font-weight:600;color:var(--ink)}
.alt .w{font-size:12.5px;color:var(--faint);margin-top:1px}
.alt .facts{margin:7px 0 0;gap:6px}
.alt .chip{font-size:11px;padding:3px 8px}

.decl{padding:15px 17px;font-size:13.5px;line-height:1.65;color:var(--dim);
      border-left:3px solid var(--warn)}
.decl b{color:var(--ink);font-weight:600}

.meta{color:var(--faint);font-size:11px;margin-top:7px;font-family:var(--mono);
      display:flex;gap:12px;align-items:center}
.meta .src{color:var(--faint);opacity:.7}
.think{padding:15px 17px;font-family:var(--mono);font-size:12.5px;color:var(--dim)}

/* ----------------------------------------------------------- empty state */
.empty{max-width:600px;margin:11vh auto 0;text-align:center}
.empty h2{font-size:23px;margin:0 0 9px;font-weight:600;letter-spacing:-.015em}
.empty p{color:var(--dim);font-size:13.5px;margin:0 0 8px;line-height:1.6}
.empty .cov{color:var(--faint);font-size:12px;margin:0 0 26px}
.egs{display:flex;flex-direction:column;gap:8px}
.eg{border:1px solid var(--line);border-radius:11px;padding:11px 15px;font-size:13.5px;
    color:var(--dim);cursor:pointer;text-align:left;background:var(--panel);
    transition:border-color .12s,color .12s}
.eg:hover{color:var(--ink);border-color:var(--accent)}

/* --------------------------------------------------------------- footer */
footer{border-top:1px solid var(--line);padding:14px 24px 18px;flex:0 0 auto;background:var(--panel)}
.row{max-width:760px;margin:0 auto;display:flex;gap:9px}
#q{flex:1;background:var(--bg);border:1px solid var(--line);color:var(--ink);border-radius:11px;
   padding:12px 14px;font-family:inherit;font-size:14.5px;resize:none;line-height:1.5}
#q:focus{outline:none;border-color:var(--accent)}
#q::placeholder{color:var(--faint)}
#send{background:var(--accent-d);border:0;color:var(--btn-fg);border-radius:11px;padding:0 22px;
      font-size:14.5px;cursor:pointer;font-family:inherit;font-weight:500}
#send:hover{background:var(--accent)}
#send:disabled{opacity:.4;cursor:default}
</style></head><body>
<header>
  <span class="mark">R</span>
  <h1>Restaurant Agent</h1>
  <span class="sub">ALY 6980 &middot; DataWorksAI Travel Agency &middot; Vrushti Shah</span>
  <span class="status">
    <select id="theme" title="Colour theme">
      <option value="slate">Slate &amp; emerald</option>
      <option value="graphite">Graphite</option>
      <option value="navy">Navy &amp; amber</option>
      <option value="coral">Coral</option>
      <option value="light">Light</option>
      <option value="paper">Paper &amp; terracotta</option>
    </select>
    <span class="dot" id="dot"></span><span id="st">Warming up&hellip;</span>
  </span>
</header>

<div id="log"><div class="inner" id="inner">
  <div class="empty" id="empty">
    <h2>Ask for a restaurant</h2>
    <p>Mention a budget, a cuisine, a dietary need, an occasion &mdash; or none of them.
       The agent commits to one pick, says why, and states anything it had to assume or adjust.</p>
    <p class="cov">Coverage: Aruba &middot; Cancun &middot; Honolulu &middot; Montego Bay &middot; Nassau &middot; San Juan</p>
    <div class="egs">
      <span class="eg">Recommend a vegan gluten-free dinner in Aruba under $30</span>
      <span class="eg">Somewhere cheap and local for seafood in San Juan</span>
      <span class="eg">A romantic dinner for an anniversary in Honolulu</span>
    </div>
  </div>
</div></div>

<footer>
  <div class="row">
    <textarea id="q" rows="1" placeholder="Ask about restaurants&hellip;"></textarea>
    <button id="send">Send</button>
  </div>
</footer>

<script>
/* Colour theme. Remembered per browser; nothing here touches the agent.
   Wrapped so that a missing element or a browser with storage disabled can
   never take the rest of the page down with it. */
(function(){
  try{
    const sel=document.getElementById('theme'); if(!sel) return;
    let saved=null; try{saved=localStorage.getItem('ra-theme')}catch(e){}
    if(saved){document.documentElement.setAttribute('data-theme',saved); sel.value=saved;}
    sel.addEventListener('change',()=>{
      document.documentElement.setAttribute('data-theme',sel.value);
      try{localStorage.setItem('ra-theme',sel.value)}catch(e){}
    });
  }catch(e){}
})();

const log=document.getElementById('log'), inner=document.getElementById('inner'),
      q=document.getElementById('q'), send=document.getElementById('send'),
      dot=document.getElementById('dot'), st=document.getElementById('st');

(async function poll(){
  try{const s=await (await fetch('/status')).json();
      st.textContent=s.note; if(s.ready){dot.classList.add('on');return;}}
  catch(e){}
  setTimeout(poll,1200);
})();

/* ---------------------------------------------------------------------------
   PARSING THE AGENT'S REPLY.  Presentation only.

   Reads the exact string answer() returned and splits it on the fields the
   agent itself writes.  Shows nothing that is not in that string.  If the
   headline does not match the shape the agent produces, render() returns null
   and the caller falls back to the raw text.  The display never guesses.
--------------------------------------------------------------------------- */
const RX_ENTRY = /([A-Z][^,\n]*?)\s+[-–—]\s+([^,\n]+),\s+([^.\n]+)\.\s+About\s+\$(\d+)\s+per person,\s+rated\s+([\d.]+)\/5\.(?:\s+Dietary:\s+([^.\n]+)\.)?/g;

/* Pull every restaurant entry out of a chunk of text, wherever it sits.
   Anchored on the tool's own "About $N per person, rated R/5" shape, so it does
   not care about newlines, bullet markers or wrapping. */
function entries(chunk){
  RX_ENTRY.lastIndex = 0;
  const out = []; let m;
  while((m = RX_ENTRY.exec(chunk)) !== null){
    out.push({name:m[1].trim(), cuisine:m[2].trim(), city:m[3].trim(),
              price:m[4], rating:m[5],
              diet:m[6] ? m[6].split(/,\s*/).map(d=>d.trim()) : []});
  }
  return out;
}

/* Split the reply at the field names the agent itself writes.

   MEASURED 21 AUG, and the reason this is not a newline split any more: the
   model is allowed to join the whole reply onto one line. That is a cosmetic
   change, the guard passes it deliberately, and the previous parser - which
   split on "\n" - fell back to raw text every time it happened. The interface
   looked broken while the agent was behaving correctly. */
const RX_FIELD = /(Adjusted:|Assumption:|Coverage limit:|Recommended restaurant:|Why:|Alternatives:)/g;

function parse(text){
  if(!text || !text.trim()) return null;
  if(/Traceback \(most recent call last\)/.test(text)) return null;

  RX_FIELD.lastIndex = 0;
  const segs = []; let m, label = null, from = 0;
  while((m = RX_FIELD.exec(text)) !== null){
    if(label !== null) segs.push([label, text.slice(from, m.index).trim()]);
    label = m[1]; from = m.index + m[1].length;
  }
  if(label === null) return null;                 // no field the agent writes
  segs.push([label, text.slice(from).trim()]);

  const out = {notes:[], pick:null, why:null, alts:[], decline:null};
  for(const [tag, body] of segs){
    if(tag === 'Adjusted:')              out.notes.push({kind:'adj', text:body});
    else if(tag === 'Assumption:')       out.notes.push({kind:'asm', text:body});
    else if(tag === 'Coverage limit:'){  out.decline = text.trim(); return out; }
    else if(tag === 'Recommended restaurant:'){
      const e = entries(body);
      if(e.length !== 1) return null;             // unknown shape -> raw
      out.pick = e[0];
    }
    else if(tag === 'Why:')              out.why = body;
    else if(tag === 'Alternatives:')     out.alts = entries(body).slice(0, 2);
  }
  if(!out.pick) return null;
  return out;
}

function chips(e){
  const wrap=document.createElement('div'); wrap.className='facts';
  const add=(t,c)=>{const s=document.createElement('span');s.className='chip '+c;s.textContent=t;wrap.appendChild(s);};
  add(e.cuisine,'');
  add('$'+e.price+' per person','price');
  add(e.rating+' / 5','rate');
  e.diet.forEach(d=>add(d.replace(/\.$/,''),'diet'));
  return wrap;
}

function render(text){
  const d = parse(text);
  if(!d) return null;
  const box=document.createElement('div'); box.className='ans';

  d.notes.forEach(n=>{
    const el=document.createElement('div'); el.className='note '+n.kind;
    const tag=document.createElement('span'); tag.className='tag';
    tag.textContent = n.kind==='adj' ? 'Adjusted' : 'Assumed';
    const tx=document.createElement('span'); tx.className='txt'; tx.textContent=n.text;
    el.appendChild(tag); el.appendChild(tx); box.appendChild(el);
  });

  if(d.decline){
    const el=document.createElement('div'); el.className='decl';
    el.textContent=d.decline; box.appendChild(el); return box;
  }

  const pk=document.createElement('div'); pk.className='pick';
  const nm=document.createElement('div'); nm.className='name'; nm.textContent=d.pick.name;
  const wh=document.createElement('div'); wh.className='where'; wh.textContent=d.pick.city;
  pk.appendChild(nm); pk.appendChild(wh); pk.appendChild(chips(d.pick));
  if(d.why){ const w=document.createElement('div'); w.className='why'; w.textContent=d.why; pk.appendChild(w); }
  box.appendChild(pk);

  if(d.alts.length){
    const al=document.createElement('div'); al.className='alts';
    const h=document.createElement('h4'); h.textContent='Alternatives'; al.appendChild(h);
    d.alts.forEach(a=>{
      const r=document.createElement('div'); r.className='alt';
      const n=document.createElement('div'); n.className='n'; n.textContent=a.name;
      const w=document.createElement('div'); w.className='w'; w.textContent=a.city;
      r.appendChild(n); r.appendChild(w); r.appendChild(chips(a)); al.appendChild(r);
    });
    box.appendChild(al);
  }
  return box;
}

/* ------------------------------------------------------------------ chat */
function userMsg(text){
  const e=document.getElementById('empty'); if(e) e.remove();
  const m=document.createElement('div'); m.className='msg u';
  const b=document.createElement('div'); b.className='bub'; b.textContent=text;
  m.appendChild(b); inner.appendChild(m); log.scrollTop=log.scrollHeight;
}

function agentShell(){
  const m=document.createElement('div'); m.className='msg a';
  const box=document.createElement('div'); box.className='ans';
  const t=document.createElement('div'); t.className='think'; t.textContent='Thinking… 0.0s';
  box.appendChild(t); m.appendChild(box); inner.appendChild(m);
  log.scrollTop=log.scrollHeight;
  return {msg:m, box:box, think:t};
}

async function ask(){
  const text=q.value.trim(); if(!text) return;
  userMsg(text); q.value=''; send.disabled=true;
  const sh=agentShell();
  const t0=Date.now();
  const tick=setInterval(()=>{sh.think.textContent='Thinking… '+((Date.now()-t0)/1000).toFixed(1)+'s';},100);
  try{
    const r=await fetch('/ask',{method:'POST',body:JSON.stringify({task:text})});
    const d=await r.json();
    clearInterval(tick);
    const card=render(d.answer);
    if(card){ sh.msg.replaceChild(card, sh.box); }
    else { sh.box.innerHTML=''; const raw=document.createElement('div');
           raw.className='raw'; raw.textContent=d.answer; sh.box.appendChild(raw); }
    const meta=document.createElement('div'); meta.className='meta';
    const el=document.createElement('span');
    el.textContent=((Date.now()-t0)/1000).toFixed(1)+'s';
    const src=document.createElement('span'); src.className='src';
    src.textContent=card ? 'rendered from the agent’s own reply' : 'raw reply — unrecognised shape';
    meta.appendChild(el); meta.appendChild(src);
    sh.msg.appendChild(meta);
  }catch(e){
    clearInterval(tick); sh.think.textContent='Request failed: '+e;
  }
  send.disabled=false; q.focus(); log.scrollTop=log.scrollHeight;
}

send.onclick=ask;
q.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ask();}});
document.querySelectorAll('.eg').forEach(c=>c.onclick=()=>{q.value=c.textContent;ask();});
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        # Never cache. Measured 21 Aug: after the page was rewritten, Chrome kept
        # serving the previous version from cache, so a rebuilt interface looked
        # completely unchanged. A demo you cannot trust to be current is worse
        # than no demo.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html")
        elif self.path == "/status":
            self._send(200, json.dumps(_state))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        if self.path != "/ask":
            return self._send(404, json.dumps({"error": "not found"}))
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            task = json.loads(raw).get("task", "")
        except Exception:
            task = ""
        self._send(200, json.dumps({"answer": get_answer(task)}))


if __name__ == "__main__":
    print("\n  Restaurant Agent")
    print("  Open  http://localhost:%d" % PORT)
    print("  Warming up in the background - the page says Ready when it is.\n")
    threading.Thread(target=_warm, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
