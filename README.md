# Ferry Delay Predictor

Predicting delays on the Halhjem-Sandvikvåg ferry (E39, across Bjørnafjorden)
from live weather, using data the project collects itself.

Live demo: [bakketvedt.no/demo/ferry](https://bakketvedt.no/demo/ferry/)

## The problem

Ferry reliability in rough fjord weather is a real, relatable problem on the west
coast of Norway. The obstacle is that there is no public historical dataset of
ferry delays to learn from. Entur publishes real-time departures, but nothing
archives what actually happened. So the dataset has to be built before the
question can be answered.

That constraint shapes the whole project: a collector runs continuously, pairing
each sailing with the weather on the crossing, and the model waits until there is
enough rough-weather data to be worth training on.

## How it works

```
met.no  (wind, gusts, wave height, fog)  ─┐
                                          ├─→  collector (every 15 min)  ─→  SQLite
Entur   (real-time ferry departures)     ─┘                                    │
                                                                               ▼
                                                          analyze  →  features  →  model
```

**Delay labels come from real-time convergence.** Each poll stores
`expectedDepartureTime - aimedDepartureTime` per sailing. Repeated polls converge
the expected time onto the actual one, so the label is correct by the time the
ferry sails. Cancellations are stored as a separate flag rather than folded in as
a huge delay, since they are a distinct outcome.

**Weather comes from two met.no products**: `locationforecast` for wind, gusts and
fog, `oceanforecast` for wave height and sea current, both sampled at the middle
of the crossing rather than at the quay.

## Modules

| Command | What it does |
| --- | --- |
| `python -m ferrydelay.collector` | One poll: weather + sailings into SQLite. Runs on a schedule. |
| `python -m ferrydelay.healthcheck` | Reports OK or STALE based on the last write. |
| `python -m ferrydelay.backup` | WAL-safe database snapshot, keeps the newest 8. |
| `python -m ferrydelay.analyze` | Joins sailings to weather, prints delay stats and correlations. |
| `python -m ferrydelay.climatology` | Frost gust history for the crossing, used to plan the collection window. |
| `python -m ferrydelay.model` | Baseline against a calibrated model, honest metrics. |
| `python -m ferrydelay.lookup` | Resolves Entur stop places and Frost station IDs. |

## Modelling approach

The harness was built before the data existed, so that autumn means re-running it
rather than rebuilding it. The choices that matter:

- **Time-based split.** Train on earlier sailings, test on later ones. A random
  split would leak future weather into the training set and flatter the model.
- **Baseline first.** Every run prints the score for predicting the base rate. A
  model that cannot beat it has learned nothing.
- **Calibrated probabilities.** Scored with Brier and log loss plus a reliability
  table. Accuracy is meaningless on a target that is mostly on-time, and "30%
  chance of delay" has to actually mean 30%.
- **It refuses to train on too little.** Below a row and positive-case threshold
  the harness stops and says so, rather than producing a confident-looking model
  from noise.

## Status

Collecting since 3 July 2026. The delay model activates once autumn storms have
produced enough disrupted sailings; summer on this route is almost entirely
on-time, so an early model would be fitting noise.

Two findings from the data so far:

- **Storm climatology** at Slåtterøy fyr (3 years of Frost gust history) shows
  July is the lull at 14% rough days, rising to 46% in August and peaking at 56%
  in December. That set the collection timeline.
- **Wave height is low-signal here.** Bjørnafjorden is an inner fjord, sheltered
  from ocean swell, so modelled wave height sits near zero while open water a few
  km seaward runs 1.5 to 1.9 m. This is a wind-driven crossing. Wave height is
  still collected, but the expectation is that gusts carry the signal.

[`working-log.md`](working-log.md) documents the build as it happened, including
the decisions made, what was delegated to an AI coding agent, and what had to be
corrected.

## Running it

```bash
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Fill in `.env`. The one hard requirement is `METNO_USER_AGENT`, since met.no
rejects requests without a User-Agent identifying the caller. `FROST_CLIENT_ID`
is only needed for historical observations and is free to register.

Find the stop place ID for a quay:

```bash
.\.venv\Scripts\python.exe -m ferrydelay.lookup stop "Halhjem"
```

Then collect once to verify, and register the scheduled task:

```bash
.\.venv\Scripts\python.exe -m ferrydelay.collector
powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Background
```

`-Background` requires an elevated PowerShell and registers the task to run
whether you are logged on or not, so reboots do not pause collection. Without it
the task only runs while logged on. Both variants use `pythonw.exe`, so no
console window appears on each run.

## Stack

Python, SQLite, pandas, scikit-learn. Data from
[met.no](https://api.met.no/) and [Entur](https://developer.entur.org/).
