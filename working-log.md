# Working log — ferry delay predictor

Running notes on building this with an AI agent: what I asked for, what landed,
what I redirected, and the calls I made myself. Source material for the
"Working with an AI agent" section on the project card.

## Phase 1 — data ingestion

### Decisions I made myself

- **Route: Halhjem–Sandvikvåg only (line 1018).** *My call.* This is the ferry I
  actually take travelling Lillesand → Bergen, so it's the one I care about
  getting right and can sanity-check against lived experience. The Halhjem quay
  also serves Våge (line 1021); I told the agent to drop everything except
  Sandvikvåg rather than model the quay generically. Narrow and personal beats
  broad and abstract for a portfolio piece.

### Decisions I delegated to the agent

- **Delay label = real-time convergence.** The agent's call (I asked it to
  decide): there is no public historical archive of ferry delays, so instead of
  faking one it polls Entur's real-time feed every 15 min and stores, per
  sailing, `expected − aimed` departure time. Repeated polls converge each
  sailing's expected time onto the actual one, so `delay_seconds` is correct by
  the time it sails. Cancellations are kept as a separate flag, not folded in as
  a giant delay — that's a distinct outcome to model in Phase 3. The cost of
  this choice: the dataset only starts existing once collection runs, hence the
  multi-week accrual window.

### What the agent got right immediately

- Resolved the real Entur stop-place ID (`NSR:StopPlace:58463`) via the geocoder
  instead of hard-coding a guessed value.
- met.no wiring: knew the User-Agent header is a hard 403-or-nothing requirement,
  and picked oceanforecast (wave height, sea current) alongside locationforecast
  — genuinely relevant physical features for a fjord crossing.

### What I had to redirect / what broke

- Agent misremembered the met.no timeseries JSON shape (used `properties` where
  the key is `data`). Caught immediately because it ran the code against the
  live API rather than trusting its own recollection. Verify, don't assume.
- Scheduling: agent first set the task to "run whether logged on or not" (S4U),
  which needs admin and got Access Denied. Redirected to a run-while-logged-on
  task once I explained I keep the laptop logged in permanently for RDP — no
  elevation needed, and it fits how the host actually runs.

### Host

Runs on my laptop (kept on, never sleeps, stays logged in for remote desktop).
Scheduled task `FerryDelayCollector`, every 15 min, writing to `data\ferry.db`.

## Phase 2 — protect the run + first look

- Chose **not** to just leave it unattended for two months. Added a health check
  (`healthcheck`) and a WAL-safe weekly backup (`backup`, task `FerryDelayBackup`)
  so a silent failure over weeks can't quietly cost the whole dataset.
- First EDA (`analyze`) joins each sailing to weather at its departure hour. Kept
  the join pure-stdlib on purpose — validating timezone alignment (local vs UTC)
  on ~140 hand-checkable rows now is far easier than on thousands later. pandas /
  scikit-learn deferred to Phase 3 where they earn their place.
- First-look result (calm summer weekend, ~140 sailings): 96% on-time, near-zero
  correlations. Exactly the expected null baseline — the weather signal needs
  autumn storms, so this run is proving the pipeline, not the hypothesis yet.

### Weather-station choice (my domain call)

Picked Frost stations by *checking coordinates and available elements*, not by
name. The nearest station to the crossing (Austevoll, 10.8 km) reports only air
temperature — useless here, and I'd have picked it if I'd trusted the name. No
station reports visibility, so fog stays sourced from the met.no forecast.
Chose two: **SN50395 (E39 Mobergsbrua)** as the nearest wind observation to the
Halhjem terminal, and **SN48330 (Slåtterøy fyr)**, the only gust source and an
exposed lighthouse that captures the open-sea storm regime driving swell into
the fjord. Wave height comes from the oceanforecast model, not a station.

### Storm climatology (timeline sanity check)

Pulled 3 years of hourly gusts at Slåtterøy (`climatology`) to decide how long
to collect. Findings: exposed crossing — 40% of days hit gusts >=15 m/s, ~71
days/year >=20 m/s. Seasonal: Jul is the real lull (14% rough), but Aug already
46% and Sep 40%, peaking Dec (56%). Conclusion: the Sept checkpoint is realistic;
weather events become frequent from mid-August, no need to wait for November.
Caveats carried forward: Slåtterøy (exposed lighthouse) overstates the sheltered
crossing, and rough weather != delay for a robust car ferry — that's the
hypothesis the ferry data will test, not something the climatology proves.

## Phase 3 — modelling scaffold (built ahead of the data)

Built the baseline-vs-model harness now so autumn = re-run, not rebuild.
Deliberate rigor choices: time-based split (train on earlier sailings, test on
later — never random, which would leak future weather); baseline (predict base
rate) printed every run so "did the model learn anything" is always visible;
calibrated probabilities scored with Brier / log loss + a reliability table
(accuracy is meaningless on a mostly-on-time target). Target = "disrupted"
(delay >= 3 min OR cancelled), cancellation folded into the positive class but
stored separately so it stays reversible.

Against today's thin data it correctly refuses to train (135 rows, 4 disrupted).
Validated the training branch on synthetic data with a planted signal
(0.18*gust + 1.2*wave): harness recovered wind_gust and wave_height as the top
coefficients and beat baseline on every metric — so the code path that only
fires in autumn is already known-good. pandas 3.0 / scikit-learn 1.9 on py3.14.

### Wave height is low-signal on this crossing

Checking the live demo, wave height read 0.0 m. Verified against the oceanforecast
model at several points along the route: the whole inner Bjørnafjorden is heavily
damped — ~0.0 now, only ~0.3 m max even over 48 h — while open water a few km
seaward (Austevoll, Slåtterøy) runs 1.5–1.9 m. Moving the sample point along the
route doesn't change it; you'd only get bigger numbers by sampling the fjord mouth,
which isn't where the ferry sails. So `wave_height` is a near-constant ~0 feature
here and unlikely to carry the model — this is a wind-driven crossing, and gust is
the real driver. Kept collecting wave (it's free, and winter storms may lift it),
but expectations set: don't lean on it. Demo keeps wave visible with a note
explaining the sheltered-fjord reasoning rather than hiding a flat number.
