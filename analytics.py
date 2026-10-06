"""Analytics: detection patterns, appeal rates, signal agreement. Spec: planning.md S4."""

from html import escape

import storage

ATTRIBUTIONS = ("likely_ai", "uncertain", "likely_human")
CONTENT_TYPES = ("text", "image")


def _pct(part, whole):
    return round(100 * part / whole, 1) if whole else 0.0


def _avg(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def compute():
    content = storage.all_content()
    appeals = storage.all_appeals()
    events = storage.count_events()
    total = len(content)
    by_id = {c["content_id"]: c for c in content}

    counts = {a: sum(1 for c in content if c["attribution"] == a) for a in ATTRIBUTIONS}
    by_type = {}
    for t in CONTENT_TYPES:
        items = [c for c in content if c["content_type"] == t]
        by_type[t] = {
            "total": len(items),
            "attribution_counts": {a: sum(1 for c in items if c["attribution"] == a) for a in ATTRIBUTIONS},
        }

    signal_names = sorted({name for c in content for name in c["signals"]})
    signal_averages = {
        name: _avg(c["signals"][name].get("ai_probability") for c in content if name in c["signals"])
        for name in signal_names
    }

    appealed_attr = [by_id[a["content_id"]]["attribution"] for a in appeals if a["content_id"] in by_id]
    appeal_rate_by_attr = {a: _pct(appealed_attr.count(a), counts[a]) for a in ATTRIBUTIONS}

    adjustment_names = sorted({adj for c in content for adj in c["adjustments"]})
    adjustment_counts = {adj: sum(1 for c in content if adj in c["adjustments"]) for adj in adjustment_names}
    conflicts = adjustment_counts.get("signal_conflict", 0)

    issued = events.get("certificate_issued", 0)
    failed = events.get("certificate_failed", 0)

    return {
        "totals": {"classifications": total, "appeals": len(appeals), "certificates_issued": issued},
        "detection_patterns": {
            "attribution_counts": counts,
            "attribution_percent": {a: _pct(counts[a], total) for a in ATTRIBUTIONS},
            "by_content_type": by_type,
            "average_ai_score": _avg(c["ai_score"] for c in content),
            "average_signal_scores": signal_averages,
            "average_confidence_by_attribution": {
                a: _avg(c["confidence"] for c in content if c["attribution"] == a) for a in ATTRIBUTIONS
            },
        },
        "appeals": {
            "appeal_rate_percent": _pct(len(appeals), total),
            "appeal_rate_by_attribution_percent": appeal_rate_by_attr,
        },
        "signal_agreement": {
            "agreement_rate_percent": _pct(total - conflicts, total),
            "adjustment_counts": adjustment_counts,
        },
        "certificates": {
            "issued": issued,
            "failed": failed,
            "pass_rate_percent": _pct(issued, issued + failed),
        },
    }


def _bar_rows(values, total=None, suffix="", scale=100):
    rows = []
    for name, value in values.items():
        shown = "n/a" if value is None else f"{value}{suffix}"
        width = 0 if value is None else max(0, min(100, 100 * value / scale)) if scale else 0
        if total is not None:
            width = _pct(value, total)
            shown = f"{value} ({width}%)"
        rows.append(
            f'<div class="row"><span class="name">{escape(name.replace("_", " "))}</span>'
            f'<span class="track"><span class="fill" style="width:{width}%"></span></span>'
            f'<span class="val">{escape(shown)}</span></div>'
        )
    return "\n".join(rows) or '<p class="muted">No data yet.</p>'


def render_html(data):
    d = data["detection_patterns"]
    total = data["totals"]["classifications"]
    stat = lambda label, value: f'<div class="stat"><div class="num">{escape(str(value))}</div><div class="lbl">{escape(label)}</div></div>'
    max_adj = max(data["signal_agreement"]["adjustment_counts"].values(), default=0)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Provenance Guard Analytics</title>
<style>
:root {{ --bg:#f7f7f5; --card:#ffffff; --text:#1d1d1b; --muted:#6b6b66; --track:#e7e6e1; --fill:#3d6b8c; --border:#e2e1dc; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#161615; --card:#1f1f1d; --text:#ecebe6; --muted:#9a9993; --track:#2e2e2b; --fill:#7fa9c8; --border:#2e2e2b; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text); font:15px/1.5 system-ui,-apple-system,sans-serif; }}
main {{ max-width:960px; margin:0 auto; padding:24px 16px 48px; }}
h1 {{ font-size:22px; margin:0 0 4px; }}
h2 {{ font-size:15px; margin:0 0 12px; }}
.muted {{ color:var(--muted); }}
.stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:12px; margin:20px 0; }}
.stat, .card {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:14px 16px; }}
.num {{ font-size:26px; font-weight:600; font-variant-numeric:tabular-nums; }}
.lbl {{ color:var(--muted); font-size:13px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr)); gap:12px; }}
.row {{ display:grid; grid-template-columns:130px 1fr 90px; gap:10px; align-items:center; margin:6px 0; font-size:14px; }}
.track {{ background:var(--track); border-radius:4px; height:10px; overflow:hidden; }}
.fill {{ display:block; height:100%; background:var(--fill); border-radius:4px; }}
.val {{ text-align:right; font-variant-numeric:tabular-nums; }}
.note {{ font-size:13px; color:var(--muted); margin-top:8px; }}
</style>
</head>
<body>
<main>
<h1>Provenance Guard Analytics</h1>
<p class="muted">Computed from the audit database on each page load. JSON version: <a href="/analytics">/analytics</a></p>
<div class="stats">
{stat("Classifications", total)}
{stat("Appeal rate", f'{data["appeals"]["appeal_rate_percent"]}%')}
{stat("Signal agreement", f'{data["signal_agreement"]["agreement_rate_percent"]}%')}
{stat("Average AI score", d["average_ai_score"] if d["average_ai_score"] is not None else "n/a")}
{stat("Certificates issued", data["certificates"]["issued"])}
</div>
<div class="grid">
<section class="card"><h2>Detection results</h2>{_bar_rows(d["attribution_counts"], total=total)}</section>
<section class="card"><h2>Appeal rate by original result</h2>{_bar_rows(data["appeals"]["appeal_rate_by_attribution_percent"], suffix="%")}
<p class="note">Appeals concentrated on "likely ai" suggest false positives.</p></section>
<section class="card"><h2>Average score per signal</h2>{_bar_rows(d["average_signal_scores"], scale=1)}
<p class="note">0 = human, 1 = AI.</p></section>
<section class="card"><h2>Average confidence by result</h2>{_bar_rows(d["average_confidence_by_attribution"], scale=1)}</section>
<section class="card"><h2>Score adjustments applied</h2>{_bar_rows(data["signal_agreement"]["adjustment_counts"], scale=max_adj)}
<p class="note">Frequent signal conflicts mean the signals are diverging on real traffic.</p></section>
<section class="card"><h2>Content types</h2>{_bar_rows({t: v["total"] for t, v in d["by_content_type"].items()}, total=total)}</section>
</div>
</main>
</body>
</html>"""
