"""The page's one stylesheet, inline, and the one visual language it defines.

Design direction: SLATE AND BRASS. An instrument panel, not a scroll.

The subject is a 1990s text MUD read through an agent's expedition log, and the obvious
move is parchment and sepia. That is also the look every generated page reaches for, warm
cream with a serif and a terracotta accent, so it is the one direction that says nothing.
This goes the other way: a cool slate ground the way a surveyor's board or a ship's
instrument panel is cool, ink with a blue bias, and a single brass accent for the one
thing a reader should look at first. One bold colour, spent on findings and links and
nothing else.

TYPE, three roles and no downloads. A strict offline page cannot fetch a webfont and
inlining one as a data URI would cost more than it is worth, so the pairing is built from
system stacks:

- DISPLAY is monospace, large, with tight tracking. This is a terminal program's output
  and its headings should say so, and it makes titles and numbers share one skeleton.
- BODY is the system sans, for prose and labels, where a mono would slow reading.
- DATA is monospace with tabular figures, so a column of numbers compares by eye.

SIZE. Body is 17px and content is 1rem. An earlier version had twenty of twenty-four
sizes below 1rem, which put every figure a reader came for beneath the one element nobody
reads. Small is for LABELS: eyebrows, table headers, chips. Nothing carrying data is
smaller than the body text.

Every colour is a token on ``:root`` so the dark theme redefines tokens rather than
restyling components. A theme that restyled components drifts the moment one is added.
"""

CSS = """
:root {
  color-scheme: light dark;

  /* Slate: a cool ground, deliberately not cream. */
  --paper: #eef0f2;
  --raised: #fafbfc;
  --sunken: #e2e6ea;
  --ink: #1a1f24;
  --ink-soft: #4b555f;
  --ink-faint: #7c8894;
  --rule: #cfd6dd;
  --rule-soft: #e3e8ec;

  /* Brass: the one bold colour. */
  --brass: #8a5a00;
  --brass-lit: #b8791a;
  --brass-wash: #f6ecd8;

  --good: #1f6b4f;
  --warn: #8a5a00;
  --bad: #9d2d24;
  --info: #2a5570;

  --display: ui-monospace, "SF Mono", "Cascadia Mono", "Roboto Mono", Menlo,
             Consolas, monospace;
  --sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto,
          "Helvetica Neue", sans-serif;
  --mono: ui-monospace, "SF Mono", "Cascadia Mono", "Roboto Mono", Menlo,
          Consolas, monospace;

  /* The terminal keeps the game's own colours. Slate-dark rather than black, so it
     reads as a panel set into the page instead of a hole cut through it. */
  --term-bg: #232a31;
  --term-fg: #d5dde4;
  --c-black:#3a444e; --c-red:#d1706a; --c-green:#7fa86f; --c-yellow:#c9a352;
  --c-blue:#6b9dc4; --c-magenta:#a97fb5; --c-cyan:#5fa8ac; --c-white:#d5dde4;
  --c-bright-black:#6c7883; --c-bright-red:#e88f88; --c-bright-green:#9dc78c;
  --c-bright-yellow:#e3c374; --c-bright-blue:#8fbde0; --c-bright-magenta:#c69ed1;
  --c-bright-cyan:#83c6ca; --c-bright-white:#f0f5f8;

  --step-0: 1rem;
  --step-1: 1.2rem;
  --step-2: 1.45rem;
  --step-3: 1.9rem;
}
@media (prefers-color-scheme: dark) {
  :root {
    --paper: #14181c; --raised: #1c2227; --sunken: #0f1316;
    --ink: #e4eaef; --ink-soft: #a8b4bf; --ink-faint: #76828e;
    --rule: #2c343b; --rule-soft: #222a30;
    --brass: #d6a24a; --brass-lit: #edbb63; --brass-wash: #2a2113;
    --good: #7fbf9d; --warn: #d6a24a; --bad: #e58a80; --info: #7fb4d6;
    --term-bg: #0d1114;
  }
}
:root[data-theme="dark"] {
  --paper: #14181c; --raised: #1c2227; --sunken: #0f1316;
  --ink: #e4eaef; --ink-soft: #a8b4bf; --ink-faint: #76828e;
  --rule: #2c343b; --rule-soft: #222a30;
  --brass: #d6a24a; --brass-lit: #edbb63; --brass-wash: #2a2113;
  --good: #7fbf9d; --warn: #d6a24a; --bad: #e58a80; --info: #7fb4d6;
  --term-bg: #0d1114;
}
:root[data-theme="light"] {
  --paper: #eef0f2; --raised: #fafbfc; --sunken: #e2e6ea;
  --ink: #1a1f24; --ink-soft: #4b555f; --ink-faint: #7c8894;
  --rule: #cfd6dd; --rule-soft: #e3e8ec;
  --brass: #8a5a00; --brass-lit: #b8791a; --brass-wash: #f6ecd8;
  --good: #1f6b4f; --warn: #8a5a00; --bad: #9d2d24; --info: #2a5570;
  --term-bg: #232a31;
}

* { box-sizing: border-box; }
body {
  margin: 0; background: var(--paper); color: var(--ink);
  font: 17px/1.6 var(--sans);
  -webkit-text-size-adjust: 100%;
}
a { color: var(--brass); text-decoration: none; border-bottom: 1px solid transparent; }
a:hover { border-bottom-color: var(--brass); }
a:focus-visible, summary:focus-visible, button:focus-visible,
input:focus-visible { outline: 2px solid var(--brass); outline-offset: 2px; }

h1, h2, h3 { margin: 0; font-weight: 600; text-wrap: balance; }
h1 { font: 600 var(--step-3)/1.2 var(--display); letter-spacing: -0.02em; }
h2 { font: 600 var(--step-1)/1.3 var(--display); letter-spacing: -0.01em; }
h3 { font-size: var(--step-0); }

.wrap { max-width: 84rem; margin: 0 auto; padding: 0 1.5rem 5rem; }
header.top {
  position: sticky; top: 0; z-index: 5; background: var(--paper);
  border-bottom: 2px solid var(--rule); padding: 0.9rem 0 0.8rem;
  display: flex; gap: 1.1rem; align-items: flex-end; flex-wrap: wrap;
}
header.top .grow { flex: 1 1 22rem; min-width: 0; }
.crumb {
  color: var(--ink-faint); font: 0.78rem/1.4 var(--mono);
  letter-spacing: 0.04em; margin-bottom: 0.2rem;
}
.sub { color: var(--ink-soft); font-size: var(--step-0); }
.mono { font-family: var(--mono); font-variant-numeric: tabular-nums; }
.absent { color: var(--ink-faint); }
.stack { display: flex; flex-direction: column; gap: 1.5rem; padding-top: 1.5rem; }
.row { display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap; }
.cols {
  display: grid; gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
}

section.card {
  background: var(--raised); border: 1px solid var(--rule);
  border-radius: 2px; padding: 1rem 1.1rem;
}
.eyebrow {
  font: 640 0.72rem/1.4 var(--sans); letter-spacing: 0.11em;
  text-transform: uppercase; color: var(--ink-faint); margin-bottom: 0.6rem;
}

/* One visual language. A kind's colour is set here and nowhere else. */
.chip {
  display: inline-block; padding: 0.05rem 0.45rem; border-radius: 2px;
  font: 600 0.82rem/1.5 var(--mono); border: 1px solid var(--rule);
  color: var(--ink-soft); background: var(--sunken); white-space: nowrap;
}
.k-error, .k-failure { color: var(--bad); border-color: var(--bad); }
.k-retry, .k-ceiling { color: var(--warn); border-color: var(--warn); }
.k-cost, .k-time { color: var(--brass); border-color: var(--brass); }
.k-context, .k-compaction { color: var(--info); border-color: var(--info); }
.k-call { color: var(--info); }
.k-result { color: var(--good); }
.k-reply, .k-plan, .k-reasoning { color: var(--ink-soft); }
/* The journey words, which are about the player rather than about the run. */
.k-confused { color: var(--info); border-color: var(--info); }
.k-blocked, .k-stuck { color: var(--warn); border-color: var(--warn); }
.k-bored { color: var(--ink-soft); }
.k-overpowered, .k-drained { color: var(--bad); border-color: var(--bad); }

table { width: 100%; border-collapse: collapse; font-size: var(--step-0); }
th, td {
  text-align: left; padding: 0.45rem 0.7rem;
  border-bottom: 1px solid var(--rule-soft);
}
th {
  font: 640 0.72rem/1.4 var(--sans); letter-spacing: 0.09em;
  text-transform: uppercase; color: var(--ink-faint);
  border-bottom: 1px solid var(--rule);
}
td.num, th.num {
  text-align: right; font-family: var(--mono); font-variant-numeric: tabular-nums;
}
tbody tr:hover { background: var(--sunken); }
.scroll { overflow-x: auto; }

.bar { display: inline-flex; align-items: center; gap: 0.5rem; min-width: 7rem; }
.bar .fill {
  display: inline-block; height: 0.55rem; min-width: 2px; background: var(--brass);
  border-radius: 1px;
}
.bar .fill.warn { background: var(--warn); }
.bar .fill.bad { background: var(--bad); }
.barlabel {
  font: 1rem var(--mono); color: var(--ink-soft);
  font-variant-numeric: tabular-nums;
}
.spark rect { fill: var(--brass); }
.spark rect.gap { fill: var(--ink-faint); }

/* Findings lead, so they are the loudest block on the page. */
section.card.lead { border-left: 3px solid var(--brass); }
ol.findings { list-style: none; margin: 0; padding: 0; }
ol.findings li {
  display: flex; gap: 0.7rem; align-items: baseline; flex-wrap: wrap;
  padding: 0.45rem 0; border-bottom: 1px solid var(--rule-soft);
}
ol.findings li:last-child { border-bottom: 0; }
ol.findings .grow { flex: 1 1 18rem; min-width: 0; }
ol.findings .detail { color: var(--ink-faint); font-size: 0.9rem; }

/* The turn strip: width by calls, colour by outcome. */
.strip { display: flex; gap: 3px; align-items: stretch; }
.strip a {
  display: flex; align-items: center; justify-content: center;
  min-width: 1.8rem; padding: 0.5rem 0.4rem;
  background: var(--sunken); border: 1px solid var(--rule); border-radius: 2px;
  font: 600 0.95rem/1.2 var(--mono); color: var(--ink-soft);
}
.strip a:hover { border-color: var(--brass); color: var(--brass); }
.strip a.tripped { border-color: var(--warn); color: var(--warn); }
.strip a.failed { border-color: var(--bad); color: var(--bad); }

/* Progressive disclosure. Collapsed by default, raw always one step away. */
details.leg { border-bottom: 1px solid var(--rule-soft); }
details.leg > summary {
  cursor: pointer; padding: 0.55rem 0.3rem; display: flex; gap: 0.6rem;
  align-items: baseline; flex-wrap: wrap; list-style: none;
}
details.leg > summary::-webkit-details-marker { display: none; }
details.leg > summary::before {
  content: "▸"; color: var(--ink-faint); font-size: 0.8rem; width: 0.9rem;
}
details.leg[open] > summary::before { content: "▾"; }
details.leg[open] > summary { background: var(--sunken); }
details.leg.marked > summary { box-shadow: inset 3px 0 0 var(--warn); }
details.leg.broken > summary { box-shadow: inset 3px 0 0 var(--bad); }
details.leg.broken:has(> summary .k-ceiling) > summary {
  box-shadow: inset 3px 0 0 var(--warn);
}
.legbody {
  padding: 0.4rem 0 1rem 1.5rem;
  display: flex; flex-direction: column; gap: 0.6rem;
}
.legbody h3 {
  color: var(--ink-faint); font: 640 0.72rem/1.4 var(--sans);
  letter-spacing: 0.09em; text-transform: uppercase;
}
pre {
  margin: 0; padding: 0.7rem 0.85rem; background: var(--sunken);
  border: 1px solid var(--rule); border-radius: 2px; overflow-x: auto;
  font: 1rem/1.6 var(--mono); white-space: pre-wrap; word-break: break-word;
}
pre.term {
  background: var(--term-bg); color: var(--term-fg);
  border-color: color-mix(in oklab, var(--term-bg) 75%, black);
  white-space: pre-wrap;
  max-height: 24em; overflow-y: auto;
}
pre.term .b { font-weight: 700; }
.c-black{color:var(--c-black)} .c-red{color:var(--c-red)}
.c-green{color:var(--c-green)} .c-yellow{color:var(--c-yellow)}
.c-blue{color:var(--c-blue)} .c-magenta{color:var(--c-magenta)}
.c-cyan{color:var(--c-cyan)} .c-white{color:var(--c-white)}
.c-bright-black{color:var(--c-bright-black)} .c-bright-red{color:var(--c-bright-red)}
.c-bright-green{color:var(--c-bright-green)} .c-bright-yellow{color:var(--c-bright-yellow)}
.c-bright-blue{color:var(--c-bright-blue)} .c-bright-magenta{color:var(--c-bright-magenta)}
.c-bright-cyan{color:var(--c-bright-cyan)} .c-bright-white{color:var(--c-bright-white)}

/* Lenses are links, so each is addressable and the back button works. */
nav.lenses {
  display: flex; gap: 0.2rem; flex-wrap: wrap;
  border-bottom: 2px solid var(--rule);
}
nav.lenses a {
  padding: 0.55rem 0.9rem; color: var(--ink-soft);
  font: 600 var(--step-0)/1.3 var(--sans);
  border: 1px solid transparent; border-bottom: 0;
  border-radius: 2px 2px 0 0; margin-bottom: -2px;
}
nav.lenses a[aria-current="page"] {
  color: var(--ink); background: var(--raised);
  border-color: var(--rule); border-bottom: 2px solid var(--raised);
}
nav.lenses a:hover { color: var(--brass); }

.timeline { display: flex; flex-direction: column; gap: 3px; }
.timeline .t {
  display: flex; align-items: center; gap: 0.6rem;
  font: 1rem var(--mono); font-variant-numeric: tabular-nums;
}
.timeline .t .track { flex: 1 1 auto; background: var(--sunken); border-radius: 1px; }
.timeline .t .track span {
  display: block; height: 0.7rem; background: var(--brass); border-radius: 1px;
}
.timeline .t.slow .track span { background: var(--warn); }
.timeline .t.broken .track span { background: var(--bad); }

/* The map: rooms on a grid with the path drawn through them. */
.mapwrap { overflow: auto; padding: 0.5rem 0; }
svg.map { display: block; }
/* An exit that exists is structure; the route walked is the story. Different weight
   and different colour, or the route vanishes into the graph. */
svg.map .link { stroke: var(--rule); stroke-width: 3; fill: none; }
svg.map .path {
  stroke: var(--info); stroke-width: 3; fill: none;
  stroke-linejoin: round; stroke-linecap: round;
}
svg.map .mark { stroke-width: 3; fill: var(--raised); }
svg.map .mark.from { stroke: var(--good); }
svg.map .mark.to { stroke: var(--info); }
svg.map .room { stroke: var(--rule); stroke-width: 1.5; }
svg.map .room.start { stroke: var(--good); stroke-width: 3; }
svg.map .room.blocked { stroke: var(--bad); stroke-width: 3; }
svg.map text { font: 0.72rem var(--mono); fill: var(--ink-soft); }
svg.map text.n { font: 600 0.78rem var(--mono); fill: var(--ink); }
.legend { display: flex; gap: 1.1rem; flex-wrap: wrap; font-size: 0.9rem; }
.legend span { display: inline-flex; align-items: center; gap: 0.4rem; }
.swatch {
  display: inline-block; width: 0.9rem; height: 0.9rem; border-radius: 2px;
  border: 1px solid var(--rule);
}

/* Pressure over time: prompt size against the window, compactions as cuts. */
svg.pressure { display: block; width: 100%; height: auto; }
svg.pressure .area { fill: var(--brass); opacity: 0.16; }
svg.pressure .line { stroke: var(--brass); stroke-width: 2; fill: none; }
svg.pressure .limit { stroke: var(--bad); stroke-width: 1.5; stroke-dasharray: 5 4; }
svg.pressure .thresh { stroke: var(--warn); stroke-width: 1.5; stroke-dasharray: 3 4; }
svg.pressure .cut { stroke: var(--info); stroke-width: 2; }
svg.pressure .axis { stroke: var(--rule); stroke-width: 1; }
svg.pressure text { font: 0.8rem var(--mono); fill: var(--ink-soft); }
svg.pressure text.peak { font: 600 0.85rem var(--mono); fill: var(--brass); }
svg.pressure text.cutlabel { fill: var(--info); }

.diffadd { color: var(--good); }
.diffdel { color: var(--bad); }
.kv {
  display: grid; grid-template-columns: auto 1fr; gap: 0.4rem 1rem;
  font-size: var(--step-0);
}
.kv dt { color: var(--ink-faint); }
.kv dd { margin: 0; font-family: var(--mono); font-variant-numeric: tabular-nums; }

input[type="search"] {
  font: var(--step-0) var(--sans); padding: 0.4rem 0.65rem; color: var(--ink);
  background: var(--raised); border: 1px solid var(--rule); border-radius: 2px;
  min-width: 14rem;
}
.hint { color: var(--ink-faint); font-size: 0.9rem; }
kbd {
  font: 0.85rem var(--mono); padding: 0.05rem 0.35rem;
  border: 1px solid var(--rule); border-bottom-width: 2px; border-radius: 2px;
  background: var(--raised); color: var(--ink-soft);
}
button.tool {
  font: 600 var(--step-0) var(--sans); padding: 0.4rem 0.8rem; cursor: pointer;
  color: var(--ink); background: var(--raised);
  border: 1px solid var(--rule); border-radius: 2px;
}
button.tool:hover { border-color: var(--brass); color: var(--brass); }
button.tool kbd { margin-left: 0.4rem; }
#theme {
  font: var(--step-0) var(--sans); cursor: pointer; color: var(--ink-soft);
  background: transparent; border: 1px solid var(--rule); border-radius: 2px;
  padding: 0.25rem 0.6rem;
}
#theme:hover { color: var(--brass); border-color: var(--brass); }
/* A card with nothing to say collapses, rather than taking a quarter of the page to
   print four absences. */
section.card.quiet { padding: 0.6rem 1.1rem; }
section.card.quiet .eyebrow { display: inline; margin-right: 0.7rem; }
.empty { color: var(--ink-soft); font-style: italic; }
.hidden { display: none !important; }
footer.foot {
  margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid var(--rule);
  color: var(--ink-faint); font-size: 0.9rem;
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
@media (max-width: 40rem) {
  h1 { font-size: var(--step-2); }
  .wrap { padding: 0 1rem 4rem; }
}
"""

#: In-page search, jump-to-failure, and expand-all. Small and inline on purpose: the
#: page has to work from a file with nothing fetched, and a bundle for this would be
#: dependency for its own sake.
#:
#: Deliberately SHORT. An earlier version bound j, k, o and c as well, and the right
#: question was why: the browser already scrolls and already opens a disclosure
#: triangle, and it does both without being taught. Only two things here are beyond it,
#: searching this record and jumping to the next failure, so only those two are bound.
#:
#: Everything is also a visible BUTTON. A control you can see does not need a legend,
#: and a legend that names a binding without naming its reason is the thing that
#: prompted the question.
JS = """
(function () {
  var root = document.documentElement;
  // The handler is on the document, so until something in the page has focus a
  // keypress goes nowhere. The first press after a page load was silently swallowed,
  // which reads as broken. Taking focus on load costs nothing and fixes it.
  if (document.body) { document.body.tabIndex = -1; document.body.focus(); }

  var toggle = document.getElementById("theme");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var now = root.getAttribute("data-theme");
      var dark = now ? now === "dark"
        : window.matchMedia("(prefers-color-scheme: dark)").matches;
      root.setAttribute("data-theme", dark ? "light" : "dark");
    });
  }

  function legs() {
    return Array.prototype.slice.call(document.querySelectorAll("details.leg"));
  }

  var expander = document.getElementById("expand");
  function setAll(open) {
    legs().forEach(function (leg) { leg.open = open; });
    if (expander) {
      expander.textContent = open ? "Collapse all" : "Expand all";
      expander.setAttribute("data-open", open ? "1" : "");
    }
  }
  if (expander) {
    expander.addEventListener("click", function () {
      setAll(!expander.getAttribute("data-open"));
    });
  }

  var at = -1;
  function nextBroken() {
    var all = legs();
    for (var i = at + 1; i < all.length; i++) {
      if (all[i].classList.contains("broken")) return i;
    }
    for (var j = 0; j < all.length; j++) {
      if (all[j].classList.contains("broken")) return j;
    }
    return -1;
  }
  function jumpToFailure() {
    var hit = nextBroken();
    if (hit < 0) return false;
    at = hit;
    var leg = legs()[hit];
    leg.open = true;
    leg.querySelector("summary").focus();
    leg.scrollIntoView({ block: "center" });
    return true;
  }
  var jumper = document.getElementById("nextfail");
  if (jumper) {
    jumper.addEventListener("click", function () {
      if (!jumpToFailure()) { jumper.textContent = "no failures here"; }
    });
  }

  function filter(term) {
    term = term.toLowerCase();
    var rows = document.querySelectorAll("[data-search]");
    var shown = 0;
    Array.prototype.forEach.call(rows, function (row) {
      var hit = !term ||
        row.getAttribute("data-search").toLowerCase().indexOf(term) >= 0;
      row.classList.toggle("hidden", !hit);
      if (hit) shown++;
    });
    var count = document.getElementById("searchcount");
    if (count) {
      count.textContent = term ? shown + " of " + rows.length + " match" : "";
    }
  }
  var box = document.querySelector('input[type="search"]');
  if (box) { box.addEventListener("input", function () { filter(box.value); }); }

  document.addEventListener("keydown", function (event) {
    var tag = (event.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea") {
      if (event.key === "Escape") {
        event.target.value = "";
        filter("");
        event.target.blur();
      }
      return;
    }
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    // Only the two the browser cannot do for itself.
    if (event.key === "/") {
      if (box) { box.focus(); event.preventDefault(); }
    } else if (event.key === "f") {
      if (jumpToFailure()) { event.preventDefault(); }
    }
  });
})();
"""
