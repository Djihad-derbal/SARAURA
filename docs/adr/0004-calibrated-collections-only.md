# Calibrated NISAR collections only: PROVISIONAL + VALIDATED, never BETA

The collection decides, not the date. Any Granule in a PROVISIONAL collection (`NISAR_L2_<P>_PROVISIONAL_V1`, earliest Granules 2025-10-29) or a VALIDATED one (`NISAR_L2_<P>_V1`, from 2026-09-27 for GUNW and 2026-10-21 for GCOV) may be used, and one time series may mix the two, because both are calibrated. BETA collections are never used. The manifest records the source collection for each Pass.

## Considered Options

- **Only dates from 2026-06-17** (the original handoff's "calibrated window"). Rejected on 2026-11-13: PROVISIONAL also holds earlier Granules with the same processing version (1.0.11, CRID P05023), e.g. GUNW pairs over Venezuela from November 2025. Excluding them would lose Venezuela's pre-earthquake coherence (16 GUNW pairs from March instead of 8), Mexico City's year-long series (27 pairs from November 2025) and the US Midwest planting season. Coverage varies by region: over Kamchatka, Okavango and Algeria, PROVISIONAL still starts in June 2026, so Kamchatka's earlier eruption Passes remain BETA-only and excluded.
- **A single collection per series:** more consistent processing, but it cuts most series to about 10 Passes.
- **Adding BETA:** longer series, but it mixes in uncalibrated backscatter.
