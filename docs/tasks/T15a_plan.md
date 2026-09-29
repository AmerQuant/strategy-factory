# T15a — plan: measurements, the questions, the design

Stream A's plan for `docs/tasks/T15a_orchestrator_synthetic_report.md` (D-403). The task file is
the supervisor's and is not edited. Decisions: **D-652 … D-656** (recorded from T15a §2), D-004,
D-008, D-031, D-160, D-305, D-306, D-334, D-351, D-352, D-354, D-400, D-401, D-402, D-602, D-607,
D-610, D-615 … D-618, D-621, D-629, D-644, D-647, D-651, D-802, D-804, D-805, D-807, ADR-008.
Open questions: **P-124 … P-132** (`docs/decisions/pending.md`).

Features: **F-X.1** (orchestrator), **F-X.2** (CLI), **F-X.3** (Persian HTML report framework),
**F-X.4** (stage 1–3 report), **F-X.5** (false-positive self-test), all MVP and assigned to T15;
**F-X.6** (planted-edge self-test, P1, pulled in by T15a §4). Touched: F-0.7.1, F-0.7.3, F-0.7.4
(reproduction), F-0.8.2 (funnel config), F-0.3.7 (executor, P-104), and F-1.9 / F-2.7 / F-3.7,
whose artifacts the report draws. F-X.8 (calibration) is T15b's (D-652).

**Measure before proposing.** Every number below comes from read-only scripts: development bars
only (`DataAccess`), the real stages as **dry runs** (no registry row), artifacts under a scratch
folder, nothing written to `SFAC_DATA_ROOT`, no threshold changed.

| script | what it measures |
|---|---|
| `scripts/analysis/T15a_null_fit.py` | **M1** — on six real series, the null's candidate generators against the real drift, volatility, gap share, range, ATR, tails and clustering, 200 seeds each |
| `scripts/analysis/T15a_null_stage1.py` | **M2** — the real stage 1 on a sample of null series (120 daily, 60 hourly symbols), probe percentiles and passes, against T12's real and control artifacts for the same symbols |
| `scripts/analysis/T15a_null_funnel.py` | **M4** — the calibrated null through **stages 1 → 2 → 3** at T12's full scope, today's thresholds: D-656's number |
| `scripts/analysis/T15a_planted.py` | **M3** — a planted MR / TF edge on the null over a strength ladder: its own statistic and stage 1's power |

| file | content |
|---|---|
| `docs/reviews/T15a_plan_null_fit.csv` | M1: per series × variant, the real value and the null's mean and 95 % band per statistic |
| `docs/reviews/T15a_plan_null_stage1_{1D,1H}.csv` | M2: probe percentile mean and share ≥ 90 per edge type and direction; profiles, ESS ≥ 50, passes |
| `docs/reviews/T15a_plan_null_funnel.csv` | M4: every null candidate at every stage, with its verdict and failing criteria |
| `docs/reviews/T15a_plan_planted.csv` | M3: per strength, the own statistic and stage 1's pass rate by type and direction |

> **Read with two caveats.** (1) The null is synthetic by construction: **every pass on it is a
> false positive**, and counts of a few are Poisson-noisy. (2) **D-335 / D-336 are unverified
> against TradingView (D-802)**; D-336 is the research default and shapes every MR run here.

## 1. The headline: today's funnel on the calibrated null (M4, D-656)

The calibrated null of §2 (`t_vp`) through the real stages 1 → 2 → 3, T12's full scope, today's
thresholds, beside the merged real runs and their reshuffled-returns controls:

| | real (T12–T14) | reshuffled control (D-615) | **calibrated null** |
|---|---|---|---|
| **1D** (486 symbols) — stage 1 passes, profiles / symbols | 14 / 13 | 0 / 0 | **15 / 13** |
| stage 2 selected methods / symbols | 25 / 13 | 0 | **27 / 11** |
| stage 3 passes, candidates / symbols | 2 / 2 | 0 | **7 / 6** |
| **end-of-stage-3 symbol share (D-656: ≤ 1 %)** | 0.41 % | 0 % | **1.23 %** |
| **1H** (367 symbols) — stage 1 passes, profiles / symbols | 4 / 4 | 1 / 1 | **7 / 7** |
| stage 2 selected / symbols | 6 / 4 | 0 | **7 / 7** |
| stage 3 passes / symbols | 4 / 3 | 0 | **1 / 1** |
| **end-of-stage-3 symbol share** | 0.82 % | 0 % | **0.27 %** |

Stated plainly, as T15a §6 asks:

1. **With today's thresholds the 1D funnel misses D-656's 1 %**: 6 of 486 null symbols reach the
   end of stage 3 (1.23 %). **1H meets it** (1 of 367, 0.27 %) — but see item 5.
2. **The null ends stage 3 with more daily symbols than the real data (6 against 2).** On today's
   thresholds, the count of the daily real passes (SHW, TXN) is not distinguishable from what a
   driftless-in-timing random walk with each symbol's own drift and volatility produces. This does
   not say the two are false; it says the funnel cannot yet tell.
3. **The reshuffled-returns control is far more conservative than the calibrated null** — 0 at
   every stage against 15 / 27 / 7. §2 measures why: it breaks the bar shapes (the gap variance
   is 1.3–1.7× the whole return variance, ATR is inflated 17–30 %). T12 said its zeros were a
   lower bound; through the whole funnel the gap is this large. **The control stays the stage
   reviews' headline (D-644, D-653), but it cannot be the calibration target** — the null is
   (D-654, D-656).
4. **Where the false positives enter (1D):** stage 1 passes the null at the real rate (15 vs 14
   profiles; 13 MR, **2 TF long** — the real 1D has no TF pass); stage 2 keeps 11 of 13 symbols;
   **stage 3 passes 7 of its 27 null candidates (26 %) against 2 of 25 real (8 %)**. Of the null
   passes: BBY and PSX TF long `tf_kama_cross`, CFG and FTI long `mr_n_day_low`, EMN short
   `mr_connors_rsi`, GM long `mr_keltner_lower` and `mr_stochastic_k`. For T15b this says stage 3's
   gate does least of the filtering on the null, and stage 1 passes it at the real rate.
5. **1H: the null reproduces the shape of the real hourly finding.** Stage 1 passes 7 null
   profiles, **all TF long** — as all 4 real hourly passes are (T12 §3); stage 2 keeps all 7; stage 3
   passes one (DELL `tf_supertrend`). On 1H stage 1 is not calibrated on a random walk (§3: TF long
   percentiles 53 / 11 % on the null), so the null's TF-long passes are the stage's bias, and **the
   four real hourly passes are what the null produces at that stage** — which supports keeping them
   `unconfirmed` (D-621, D-645). The end-of-stage-3 share is small here because stage 3's 100-trade
   minimum per half (D-647) holds on hourly TF, not because stage 1 is right.
6. **Gaussian sensitivity (§2):** the constant-volatility Gaussian null on 1D passes **6 / 13 / 4**
   (stage 1 profiles / stage 2 selections / stage 3 candidates) — **4 of 486 symbols, 0.82 %**,
   against `t_vp`'s 1.23 %. Two symbols apart, inside Poisson noise; both nulls sit at D-656's
   line, and on both **stage 3 passes about a quarter to a third of the null candidates it receives**
   (7 of 27, 4 of 13). The Gaussian passes are MR only (GE short `mr_daily_drop`, MELI long
   `mr_ma_distance_pct`, PH and USB long `mr_n_day_low`). T15b's target should be read on the
   calibrated null (P-126) over several seeds: a count near 5 has a Poisson standard deviation
   near 2 (not measured across seeds here), about 0.5 % of 486 symbols — the size of the margin
   that decides D-656.

This is T15b's starting point, not a verdict (T15a §6). T15a changes no threshold (D-652).

## 2. The calibrated null (D-654), shown on real symbols first (M1)

T15a asks for the null's fit to be shown on real symbols before anything is built on it. Six
development segments: SHW, TXN, AAPL, EEM (1D) and TSLA, BAC (1H). Per series the generator fits
its parameters **per session slot** — a bar's position within its UTC trading date (1D: one slot;
1H: 7 regular slots, and the first carries the overnight gap: its volatility is 2.8–2.9× the
others') — and splits each bar into a **gap** (previous close → open) and a **body** (open → close),
with the real gap–body correlation. Every generated variant has **exact moments**: per slot the
gap and body are rescaled so their mean and standard deviation equal the real ones, so the
realised drift and volatility of every seed are the real ones (a plain random walk with the real
μ wanders ±20 %/yr in realised drift from seed to seed, 95 % band). High and low come from a
Brownian bridge over the body, scaled per slot so the mean wick equals the real one; OHLC is
consistent in every bar of every seed. The calendar is the real one: the null reuses the real
timestamps (sessions, early closes, holidays) and the real first close, so it also **ends at the
real last close** (exact drift).

Three candidates and the control, mean over 200 seeds (full table with 95 % bands:
`docs/reviews/T15a_plan_null_fit.csv`):

| series | variant | drift %/yr | vol %/yr | gap share | ATR % | excess kurt. | ac1 \|r\| |
|---|---|---|---|---|---|---|---|
| SHW 1D | **real** | 15.80 | 27.64 | 0.350 | 1.94 | 16.5 | 0.216 |
| | control (D-615) | 15.80 | 27.64 | **1.666** | **2.48** | 16.5 | −0.003 |
| | gauss | 15.80 | 27.60 | 0.351 | 2.43 | 0.0 | 0.000 |
| | t | 15.80 | 27.66 | 0.350 | 2.29 | 3.7 | −0.002 |
| | **t_vp** | **15.80** | **27.63** | **0.350** | **1.96** | 11.9 | 0.163 |
| TXN 1D | **real** | 15.73 | 28.93 | 0.377 | 2.14 | 4.8 | 0.267 |
| | control | 15.73 | 28.93 | **1.601** | **2.65** | 4.8 | −0.001 |
| | **t_vp** | **15.73** | **28.92** | **0.377** | **2.18** | 6.1 | 0.139 |
| AAPL 1D | **real** | 26.55 | 29.77 | 0.409 | 2.06 | 5.6 | 0.222 |
| | **t_vp** | **26.55** | **29.72** | **0.411** | **2.10** | 5.9 | 0.141 |
| EEM 1D | **real** | 3.87 | 21.48 | 0.690 | 1.38 | 8.4 | 0.280 |
| | **t_vp** | **3.87** | **21.48** | **0.690** | **1.36** | 9.3 | 0.143 |
| TSLA 1H | **real** | 29.48 | 55.41 | 0.400 | 1.41 | 19.8 | 0.154 |
| | control | 29.48 | 55.41 | **1.644** | **1.79** | 19.8 | 0.000 |
| | **t_vp** | **29.48** | **55.38** | **0.400** | **1.49** | 20.6 | 0.071 |
| BAC 1H | **real** | 10.54 | 31.78 | 0.405 | 0.78 | 26.8 | 0.186 |
| | **t_vp** | **10.54** | **31.76** | **0.405** | **0.81** | 27.6 | 0.082 |

1H slot volatility (bp per bar), real / `t_vp`: TSLA slot 0 **263 / 263**, slots 1–6 **93.6 /
93.6**; BAC **153 / 153**, **52.6 / 52.6**. The control flattens it (TSLA 132 / 132).

What this shows:

- **Drift and volatility match exactly**, by construction, in every variant (the D-654 requirement).
- **The bar's shape matters, and only `t_vp` gets it right.** ATR — the unit of every probe, stop,
  magnitude and slippage — is 15–25 % too high on the constant-volatility variants (`gauss` 2.43
  against SHW's 1.94): real volatility clusters, so the median ATR sits below the mean, and an
  i.i.d. series has no calm stretches. `t_vp` multiplies the i.i.d. Student-t innovations by the
  real series' **own volatility path** — a causal EWMA of the real squared returns up to the
  previous bar (half-life 20 daily bars; 140 hourly), normalised to RMS 1 per slot — and matches
  ATR within 1–2 % on 1D and 4–5 % on 1H, the tails, and about two thirds (1D) or half (1H) of the
  clustering. **Direction stays i.i.d.**: the path is a scale, so it carries the real volatility
  regimes (2020 included) and no edge. Lag-1 return autocorrelation is 0 in every null (real
  1D: −0.09 to −0.19 — the short-horizon reversal the real data shows and a null must not have).
- **The control breaks the bar shape.** It keeps each bar's own open/high/low ratios and moves
  them onto a permuted close path, so the gap from the previous close is incoherent: the gap
  variance becomes **1.3–1.7× the whole return variance** (real 0.35–0.69), ATR is **17–30 % too
  high**, and the hourly session profile is gone. That is the measured reason it is conservative
  (T12 §2, calibration item 5).

**Proposal (P-126): the calibrated null of D-654 is `t_vp`**, with `gauss` computed as a reported
sensitivity; its constants (innovation family, df bounds 4.5–60, the EWMA half-life, the slot rule,
the wick-calibration draws) in `configs/synthetic/null.yaml` (rule 1).

## 3. Is the null calibrated for stage 1? (M2)

A calibrated null should give stage-1 probe percentiles near 50 with about 10 % at or above 90
(the probe gate's threshold, T12 §2). M2 runs the real stage 1 (dry) on the null of a seeded sample
and reads T12's real and control artifacts for the same symbols
(`docs/reviews/T15a_plan_null_stage1_{1D,1H}.csv`):

| sample | real | control | gauss | t | **t_vp** |
|---|---|---|---|---|---|
| 1D, 120 symbols: mean percentile / share ≥ 90 | 49.0 / 9.9 % | 43.8 / 6.2 % | 48.0 / 9.0 % | 49.4 / 8.7 % | **49.7 / 10.1 %** |
| 1D: MR short | 58.1 / 17.3 % | 41.9 / 6.7 % | 48.2 / 9.7 % | 52.9 / 12.3 % | **52.3 / 13.9 %** |
| 1D: profiles passing (of 480) | 3 | 0 | 2 | 1 | **5** |
| 1H, 60 symbols: mean / share ≥ 90 | 45.0 / 9.4 % | 31.8 / 3.6 % | 52.4 / 11.0 % | 58.6 / 13.6 % | **57.0 / 12.5 %** |
| 1H: MR short | 47.4 / 14.3 % | 33.1 / 4.8 % | 56.6 / 16.5 % | 60.4 / 16.9 % | **60.9 / 17.4 %** |
| 1H: profiles passing (of 240) | 1 | 0 | 1 | 1 | **1** |

- **1D: the null is calibrated for stage 1** in pooled terms (`t_vp` 49.7 / 10.1 %). MR short sits a
  little high on the fat-tailed nulls (52 / 14 %), part of what T12 saw on real data (58 / 17 %).
- **1H: stage 1 is not calibrated on a random walk with the real session profile** — even the
  Gaussian null gives 52 / 11 %, MR short 57 / 17 %; fat tails push it to 57–61. The real 1H data
  sits *below* its null (45 / 9.4 %). The null is not at fault — it is a random walk; the matched
  baseline is: it places random entries uniformly in time, while the probes enter at particular
  session slots after particular bars (the overnight-gap slot has 2.8× the volatility). **This is
  a new item for T15b's list (item 13): the stage-1 baseline is not matched on intraday timing.**
  T15a reports it and changes nothing (D-652).
- The 1D sample happened to contain three of T12's 14 real passes (MSFT, SHW, AAPL); every null
  pass is MR. Counts of 1–5 do not separate the variants; M4 (§1) is the full-scope measurement.

## 4. The planted edge (D-654, F-X.6) (M3)

TBD-M3

## 5. The orchestrator (F-X.1, F-X.2)

### 5.1 The funnel config (F-0.8.2)

`configs/funnel/<name>.yaml`, validated by a frozen Pydantic model (`pipeline/funnel_config.py`):

```yaml
source: {kind: real}            # real | null | planted (D-654); null/planted add seed + generator
symbol_scope: broker            # as the stage-1 configs (D-616)
timeframes: [1D, 1H]
stages: [s01_edge, s02_screen, s03_entry]
control: true                   # D-653; `--no-control` overrides and is recorded
seed: 42
report: true                    # D-655: one report per funnel run
```

Shipped: `configs/funnel/mvp.yaml` (real), `null.yaml`, `planted.yaml` (with
`configs/synthetic/null.yaml` and `planted.yaml`). The orchestrator builds each stage's
`PipelineConfig` in memory from the funnel config — the same fields the hand-written
`configs/pipeline/s0*_*.yaml` carry today, with `stage_inputs` set to the upstream stage run —
so a stage run inside a funnel is an ordinary registry run with its own `config_hash` and
artifacts (`sfac run` keeps working on single-stage configs).

### 5.2 Arms, and how the control is chained (D-653, P-124)

Per timeframe the funnel runs six stage runs, in order: `s01 real`, `s01 control`, `s02 real`,
`s02 control`, `s03 real`, `s03 control`. **Each stage's control arm re-runs the real arm's inputs
of that stage on reshuffled bars** — stage 1 on every symbol, stage 2 on the *real* stage-1
passes, stage 3 on the *real* stage-2 selections — exactly as T13 and T14 ran it (D-651 (b)); the
stages already refuse a control run as input. This is what reproduces the merged T12–T14
results, which T15a §6 requires. The other reading of "chained through the same stages" — a
control-only chain (control stage 1 → control stage 2 …) — would feed stage 2 with the control's
own 0–1 passes and measure little; the calibrated null (§1) is the end-to-end false-positive
measure. **P-124** asks which reading D-653 means.

On a synthetic funnel the real arm runs on the synthetic series and the control arm on the same
synthetic series reshuffled.

### 5.3 The funnel-run link (P-125)

A new Alembic migration `0002_funnel_runs` (stream A owns migrations; one head, D-357 (4)):

| table / column | content |
|---|---|
| `funnel_runs` | `id` (uuid), `config` (jsonb), `config_hash`, `funnel_key`, `code_version`, `seed`, `source` (`real` / `null` / `planted`), `control` (bool — `false` only with `--no-control`, D-653), `status`, `started_at`, `finished_at`, `notes` |
| `funnel_stage_runs` | (`funnel_run_id`, `timeframe`, `stage`, `arm` `real`/`control`) primary key; `stage_key`; `run_id` → `pipeline_runs`; `status` (`running`, `done`, `failed`, `empty`); `inputs` (count) |
| `pipeline_runs.source` | new column, `real` by default, `null` / `planted` for synthetic stage runs (D-654: "marked as such in its run row"), with a check constraint |

The alternative — a nullable `funnel_run_id` column on `pipeline_runs` plus the arm and timeframe
in `notes` — needs no second table but cannot hold a stage that was skipped as `empty` or its
`stage_key`, and makes resume a text search. Recommended: the tables.

### 5.4 Resume (F-X.1: "interrupt and resume give the same result")

- **`stage_key`** = sha256 of the canonical JSON of: the stage's resolved `config_hash` (which
  includes `stage_inputs`, i.e. the upstream run ids), the stage-config file's hash, the gate
  file's hash, the synthetic generator's hash (if any), and `code_version`. It is content-addressed
  as D-805 / D-807 ask: a changed threshold, stage config or upstream run is a different key.
- `sfac funnel run <cfg>` computes the **funnel key** (the funnel config's hash with every
  referenced file's hash and the code version). If an unfinished funnel run with that key exists,
  it **resumes** it: a stage whose row is `done` with the same `stage_key` is skipped (its run id
  feeds the next stage), the first unfinished one re-runs from scratch. `--fresh` forces a new
  funnel run. **A dirty working tree never resumes** (`<sha>-dirty` does not identify the code,
  D-352): it starts fresh and says so.
- Granularity is the stage run (minutes); the design's per-(candidate, stage) resume (§10) is not
  needed at this size and would duplicate the stages' own batching.
- **Empty stages**: a stage with no input (no pass upstream) is recorded `empty`, runs nothing and
  is shown as 0 — today `sfac run` raises on it.
- Test: a funnel interrupted inside stage 2's real arm (an injected failure) and resumed gives
  artifacts identical to an uninterrupted run (every `summary.json` and `index.csv`, with run ids
  and timestamps normalised), and stage 1 is not re-run (its run id is reused).

### 5.5 Reproduce (F-0.7.4, F-X.2)

`sfac funnel reproduce <funnel-run-id>` reads the funnel row and its stage rows, **refuses** when the
recorded `code_version` is dirty or differs from the checkout (reproduction needs the same code),
re-runs every stage run from its recorded config into a **new** funnel run, and compares every
artifact with the original (run ids, `code_version` fields and timestamps normalised): identical →
exit 0; otherwise the differing files are listed and the exit code is 1. Candidate ids carry no run
id (D-805, D-651 (c)), so the rerun's candidates are the same ids.

### 5.6 CLI (F-X.2)

`sfac funnel run <cfg> [--no-control] [--fresh] [--workers N]`, `sfac funnel status <id>`,
`sfac funnel reproduce <id>`, `sfac funnel report <id>` (rebuild the report from the artifacts).
`sfac run` (one stage) and `sfac reproduce --trial` stay. With these, every MVP operation of stages
1–3 runs from the CLI (F-X.2's acceptance; a test walks the command tree).

## 6. Synthetic series inside the stages (D-654)

- **Module** `strategy_factory/synthetic/` (NumPy): `null.py` (fit, volatility path, generate),
  `planted.py` (plant, record), `access.py` — `SyntheticDataAccess`, a `DataAccess` whose
  `arrays(symbol, timeframe)` returns the synthetic version of the real **development** bars,
  generated in memory, deterministically from (the source seed, symbol, timeframe). The stages
  are unchanged: they already take their bars from `ctx.data`. Nothing is written to
  `SFAC_DATA_ROOT`; the planted positions are written under the funnel's artifacts folder.
- **Identity** (P-132): `source` (`real`, or `null:<hash12>` / `planted:<hash12>` of the generator
  config and seed) joins the stage identities and the candidate-id payload **only when it is not
  `real`**, and `PipelineConfig` gets an optional `source` left out of the canonical JSON when real
  — so **no existing config hash or candidate id changes** (the pattern of `stage_inputs`, T13), and
  a synthetic candidate can never collide with a real one. Stages 2 and 3 **refuse** an input run
  whose source differs from their own (D-654: never mixed); `pipeline_runs.source` marks the run.
- **Costs** are the real symbol's profile (T15a §4). US equities pay a basis-point spread, so a
  synthetic series pays the same relative spread; the per-share commission follows the synthetic
  price path, which starts and ends at the real prices (exact drift).
- **Tests:** drift and volatility per slot equal the source's (exact); OHLC consistent; ATR within
  a stated tolerance of the source on the M1 series (fixtures); determinism by seed; a different
  seed gives a different series; the planted effect detectable in its own statistic at the strong
  end and absent (its 95 % band contains 0) from the null; nothing under `SFAC_DATA_ROOT` changes.

## 7. The report (D-655, F-X.3, F-X.4)

### 7.1 Build

`reports/` (Jinja2 + Plotly, ADR-008, D-400): `read.py` loads a funnel run's artifacts and
registry rows into a plain context (a pure reader: every number comes from an artifact or a
registry row; counts are counts of artifact rows), `figures.py` builds Plotly figures from that
context, `templates/funnel.html.j2` lays it out, `render.py` writes
`<artifacts>/<funnel_run_id>/report.html`. Plotly's bundle is inlined once
(`include_plotlyjs=True` on the first figure, `False` after), the font is inlined as a `data:`
URI, all CSS and JS inline; `displaylogo: false`, no MathJax, no topojson.

### 7.2 Content (T15a §5)

- **First page:** the funnel table — per stage and timeframe, real against control side by side
  (for a synthetic run, against the truth: planted symbols and what reached each stage); banners:
  the control status (D-653), **D-802** (D-335 / D-336 unverified against TradingView), a synthetic
  run (D-654, on every page), `--no-control` if used; the run's ids, config hash, code version,
  seed.
- **Per stage:** counts; the gate's failing criteria by frequency; stage 1's pass rate by data-
  quality status and timeframe (T12 §4); stage 1's universe heatmap of ESS (D-617, F-1.9).
- **Per candidate that entered stage 3** (passes first): lineage (profile → method → parameters);
  stage 1's probe table and ESS breakdown; stage 2's grid heatmap and family score; stage 3's
  half-1 and half-2 surfaces with the plateau outlined and the selected cell marked (grids of three
  axes: the two-axis slices through the selected cell; one axis: a line), the SPP histogram (the
  surface cells' after-cost targets, binned — presentation of stored values, not a recomputation),
  zero-cost against after-cost, the overlaps, the caveats (D-610), `unconfirmed`.
- **Synthetic runs:** the truth — null: every pass is a false positive, the end-of-stage-3 share
  against D-656; planted: power per (type, direction, strength) at each stage.
- A candidate cap per run (`report.max_candidate_sections`, config) moves the rest into a table,
  should a null run send many candidates to stage 3.

### 7.3 Font and direction (P-128)

**Proposal: Vazirmatn** — CLAUDE.md and the spec (§0.7) name it; design §2 plans
`reports/assets/fonts/Vazirmatn`. Measured from the file installed on this machine
(`%LOCALAPPDATA%\Microsoft\Windows\Fonts\Vazirmatn-VariableFont_wght.ttf`, its `name` table):
**version 33.003, "Copyright 2015 The Vazirmatn Project Authors
(https://github.com/rastikerdar/vazirmatn)", licensed under the SIL Open Font License 1.1**; no
Reserved Font Name in the copyright line. One variable TTF covers every weight: **240,164 bytes**
(≈ 320 KB as base64), sha256 `5d466469…4fd2f4b1`. The OFL permits embedding the font in documents
and redistributing it with its licence; the repository carries the font file and `OFL.txt` side by
side under `src/strategy_factory/reports/assets/fonts/`, and the report's footer names the font and
its licence.

- **Getting the files (D-031):** the OFL text is not on this machine, and Claude Code makes no
  download. A PowerShell script `scripts/fetch_vazirmatn.ps1` (run by the user) fetches the
  official v33.003 release from `github.com/rastikerdar/vazirmatn`, extracts the variable TTF and
  `OFL.txt`, and checks the TTF's sha256 against the installed file's; the files are then committed
  unchanged (binary; `OFL.txt` byte-identical under a `-text` rule if it is CRLF).
- **Direction:** `<html lang="fa" dir="rtl">`; every number, symbol, method name, parameter, id and
  date passes through one template filter that wraps it in `<bdi dir="ltr">`. **Digits are Latin**
  (tabular), so numbers read and copy the same as in the artifacts and the reviews — Persian digits
  are a CSS switch if preferred (P-128).
- No subsetting (it would need `fonttools`, a new dependency).

### 7.4 Tests (T15a §5)

- **Every number on the first page equals its artifact value**: the table cells carry
  `data-source` attributes naming their artifact and field; the test parses the HTML (stdlib
  `html.parser`), reads each named value from the artifacts, and compares.
- **The surface is drawn in the artifact's axis order** (the T14 transposition must not come back):
  the embedded figure JSON of one surface is compared cell by cell with the artifact's `surface`
  under `grid.axes` (a non-square 2-D grid and a 3-axis grid, so a transposition cannot pass).
- **No external reference**: no `src=`, `href=`, `url(` or `@import` whose target is not `data:`,
  `#…` or empty — checked on the parsed HTML and CSS, not by a text search (Plotly's inlined bundle
  contains URL strings in code that are never fetched).
- **Offline rendering**: a headless Chromium (Chrome or Edge — no new dependency; both CI images
  and this machine have one) opens the file with `--log-net-log`; the test asserts no network
  request other than the file itself and that every figure rendered (`.plot-container` present).
  If no browser is found locally the test is skipped with the reason; **CI fails on that skip**, as
  it does for `db` (0 skipped).
- **RTL / LTR**: every text node containing Latin letters or digits sits inside a `dir="ltr"`
  element; the root is `dir="rtl"`; mutation-checked by removing the filter from one field.
- **The font licence is in the repository** next to the font, and the embedded font's sha256 equals
  the committed file's.

## 8. The clean-up from T13 (calibration item 9)

- `stages/screen.py` and `stages/optimize.py` stop importing stage 1's private `_cost_arrays` and
  `_require_research_engine`: both move to `stages/common.py` as `cost_arrays(...)` and
  `require_research_engine(ctx, stage)`, whose message names the calling stage (today it says
  "stage 1" in stages 2 and 3). `UnsupportedSymbol` moves with them.
- `components/entries/methods_tf.py` stops importing `_float`, `_float_param`, `_int`,
  `_int_param`, `_Method` from `methods_mr.py`: they move to `components/entries/method_base.py`
  under public names; both method modules import from there.
- No behaviour changes: T12–T14's tests and the real funnel's reproduction (acceptance) prove it.

## 9. P-104: the executor budget (calibration item 7)

Measured incidentally so far, all on 6 workers × 1 Numba thread: stage 1 on the 486 daily null
series in **520 s** (T12's full 1D run: 22 min under `auto` = 4 workers × 5 threads, partly on
efficiency cores before D-804); the 120-symbol sample in 119 s. Stage 1 is single-threaded per
unit, so `auto`'s five Numba threads per worker idle. **Proposal (P-129):** in the implementation,
measure stage 1 (1D, full scope) and stage 3 (1H, the largest grids) at workers ∈ {auto, 8, 12, 16}
× 1 thread **while stream B is idle** (benchmarks take every core), and propose a per-stage default
from the numbers; the budget is operational (never hashed, D-351), so no result changes. Not
changed alone.

## 10. What the features' acceptance means here

- **F-X.5** — "the stage-3 pass rate is within statistical expectation, and reported": the
  expectation is D-656's ≤ 1 % of symbols, which T15b calibrates to; **T15a reports it** (§1) and its
  test proves the measurement (a null funnel on fixtures reports the share it computes from the
  artifacts). Recorded as the reading in P-131.
- **F-X.6** (P1) — "the edge is found and the parameter found is close to the planted value": T15a
  measures **power** per strength; "the parameter close to the planted value" has no direct meaning
  for entry rules whose parameters are not the planted quantity (a pullback of *s* × ATR is not an
  RSI threshold). Proposal (P-131): report, per stage-3 candidate on a planted symbol, the share of
  its trades that enter within the planted events' reversion window (precision) and the share of
  events it trades (recall), from the candidate's stored trades; the parameter question stays with
  F-X.8.

## 11. Tests (summary)

F-X.1: resume after an injected failure = uninterrupted (artifacts), a finished stage not re-run,
dirty tree never resumes, empty stages. F-X.2: the command tree covers run / status / reproduce /
report; `--no-control` recorded in the row and on page one. F-0.7.4: `funnel reproduce` identical on
a small fixture funnel and failing on a changed artifact (mutation). Migration: upgrade / downgrade,
one head, the db suite (0 skipped). D-654: the synthetic tests of §6; no store write (the store's
file listing unchanged); a synthetic input refused by a real stage and vice versa; old config
hashes and candidate ids unchanged (recomputed from T12–T14 artifacts). D-655: §7.4. The clean-up:
the existing suites. Leakage: the synthetic generator only reads development bars; the stages are
unchanged, so their truncation tests stand.

## 12. Acceptance runs, cost, stops

1. **Real:** `sfac funnel run configs/funnel/mvp.yaml` (1D and 1H, with the control) — the same
   passes as T12–T14 at every stage (14 / 25 / 2 on 1D, 4 / 6 / 4 on 1H) and 0 control passes at
   stages 2 and 3; the wall time stated. Expected ≈ 2 h (stage 1 dominates).
2. **Null** and **planted**: full funnel runs, both timeframes, today's thresholds; the null's
   end-of-stage-3 share against D-656 and the planted power curve, per stage.
3. One report per funnel run; the reports and their sizes in the review.
4. Fast suite, parity / leakage / oracle, db (0 skipped), slow, ruff, format, mypy (Windows and
   `--platform linux`), stream guards; the `acceptance-reviewer`; D-802 stated; **stop for
   "Approved"**.

**New dependencies (to be listed in the review): `plotly` and `jinja2`** — ADR-008 and D-400 chose
them; neither is installed today. No other.
