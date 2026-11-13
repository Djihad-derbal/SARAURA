"""Rule-based plain-language findings from computed statistics. No model is involved, so every
number in the text is a number the pipeline measured and the map shows."""
from __future__ import annotations

import datetime as dt


def _nice(d: str) -> str:
    x = dt.date.fromisoformat(d)
    return f"{x.day} {x.strftime('%B %Y')}"


def from_stats(site: dict, stats: dict, dates: list[str]) -> list[str]:
    out: list[str] = []
    if stats.get("burned_baseline_ha"):
        ha = stats["burned_baseline_ha"]
        share = ha / stats["area_ha"] * 100 if stats.get("area_ha") else None
        tail = f", {share:.1f}% of the area" if share else ""
        out.append(f"The Baseline rule flags {ha:,.0f} ha as burned across the fire{tail}.")
        if stats.get("dhv_event_median_burned") is not None:
            out.append(f"Inside those areas, vegetation scattering (HV) fell by a median of {abs(stats['dhv_event_median_burned']):.1f} dB.")
    if stats.get("coseismic_max_toward_cm") is not None:
        out.append(f"Across the earthquake the ground moved up to {stats['coseismic_max_toward_cm']:.0f} cm toward the satellite and up to {abs(stats['coseismic_max_away_cm']):.0f} cm away (line of sight).")
    if stats.get("fastest_sinking_cm_month") is not None and stats["fastest_sinking_cm_month"] < -0.5:
        share = stats.get("share_sinking_1cm_month", 0) * 100
        out.append(f"The fastest-moving 1% of the area moves away from the satellite at {abs(stats['fastest_sinking_cm_month']):.1f} cm per month or more; {share:.1f}% moves faster than 1 cm per month.")
    # Vegetation-scattering change is the story for these Lenses only; elsewhere (e.g. an earthquake
    # in a seasonal forest) the dry-season leaf drop would outrank the event itself.
    # With no Lens (an open Analysis) there is no event story to drown out, so the change is reported too.
    shares = (stats.get("hv_change_share_3db") or {}) if site["lens"] in ("wildfire", "farming", "wetland", "volcano", None) else {}
    if shares:
        d, s = max(shares.items(), key=lambda kv: kv[1])
        if s > 0.001:
            out.append(f"The largest lasting change came on {_nice(d)}: vegetation scattering (HV) fell by more than 3 dB and stayed down over {s * 100:.2f}% of the area.")
    gap = dates[0] < "2026-07-27" and dates[-1] > "2026-08-10"
    note = ", every 12 days except the 27 July to 10 August 2026 instrument gap" if gap else ", one every 12 days"
    out.append(f"{len(dates)} NISAR Passes from {_nice(dates[0])} to {_nice(dates[-1])}{note}.")
    if stats.get("masked_share", 0) > 0.05:
        out.append(f"{stats['masked_share'] * 100:.0f}% of pixel values are missing (outside the radar swath or no data).")
    return out[:5]
