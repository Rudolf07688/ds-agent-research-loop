# Synthetic data generation — statistical method

How `ds_agent_loop.data_gen.generate_rows` produces synthetic delivery records. The
goal is data that is **realistic and correlated**, yet **deterministic, reproducible,
and anchored** (Principle V — no LLM in the expansion path).

There are two independent layers:

1. **Features** — drawn from a *Gaussian copula* so each column has a realistic marginal
   distribution *and* the columns are correlated with one another.
2. **Target** (`delivery_time_minutes`) — a fixed, readable function of the features plus
   spec-controlled Gaussian noise. This is the relationship the models learn.

Only layer 1 changed recently; the target has always been patterned (that is what makes
the regression task learnable).

## Layer 1 — features via a Gaussian copula

A Gaussian copula separates *dependence structure* from *marginal shape*:

1. Draw correlated latent normals `z ~ N(0, C)`, where `C` is the latent correlation
   matrix (`_LATENT_CORR`, symmetric positive-definite).
2. Map to correlated uniforms by the probability-integral transform: `u = Φ(z)`,
   column-wise, so each `u_j ∈ (0,1)` but the columns stay dependent.
3. Map each `u_j` through its feature's inverse CDF (`F_j⁻¹`) to get the realistic marginal.

```
z ~ N(0, C)  ──Φ──▶  u (correlated uniforms)  ──F_j⁻¹──▶  feature_j
```

### Latent correlation matrix (`_LATENT_CORR`)

Feature order: `[item_count, distance_km, traffic_level, is_raining, hour_of_day]`.

|             | item | dist | traf | rain | hour |
|-------------|------|------|------|------|------|
| item_count  | 1.00 | 0.45 | 0.00 | 0.00 | 0.00 |
| distance_km | 0.45 | 1.00 | 0.30 | 0.00 | 0.20 |
| traffic     | 0.00 | 0.30 | 1.00 | 0.25 | 0.50 |
| is_raining  | 0.00 | 0.00 | 0.25 | 1.00 | 0.00 |
| hour_of_day | 0.00 | 0.20 | 0.50 | 0.00 | 1.00 |

The intent behind the non-zero entries:

- **distance ↔ item_count** — bigger trips tend to carry more items.
- **traffic ↔ hour_of_day** — congestion peaks at commute hours.
- **traffic ↔ distance / rain** — longer and wetter trips see worse traffic.

These are *latent* (Gaussian) correlations. The copula preserves the **sign** and
monotonic direction, but the realized correlation on the transformed marginals is
somewhat attenuated. Measured on 20k rows (seed 0):

| pair                  | realized corr |
|-----------------------|--------------:|
| distance ↔ item_count |        ~0.41  |
| traffic ↔ hour_of_day |        ~0.44  |
| traffic ↔ distance    |        ~0.24  |

### Marginal distributions (`F_j`)

| feature        | distribution                              | params |
|----------------|-------------------------------------------|--------|
| `item_count`   | Poisson(λ) + 1, clamped `[1, 10]`         | `λ = _ITEM_COUNT_LAMBDA = 2.0` |
| `distance_km`  | log-normal, clamped `[0.5, 30]`, 2 dp     | `σ = 0.6`, median `= 3.0` km |
| `traffic_level`| categorical via cumulative thresholds     | weights `(0.4, 0.4, 0.2)` for 3 categories, else uniform |
| `is_raining`   | Bernoulli                                 | `P = _RAIN_PROB = 0.3` |
| `hour_of_day`  | bimodal commute mixture over `0..23`      | equal-weight normals at `8h` and `18h`, `sd = 2.5` |

Notes:

- `item_count` / `distance_km` use `scipy.stats.poisson.ppf` / `lognorm.ppf`.
- `traffic_level` thresholds come from `np.cumsum(weights)`; categories are taken from the
  saved `data_spec` (`spec.categories["traffic_level"]`), so the spec stays the source of truth.
- `hour_of_day` uses a discrete pmf (`_hour_pmf`): an equal mixture of two Gaussians centred
  on the commute peaks, normalized over the 24 integer hours, inverted by `searchsorted` on its
  cumulative distribution. This yields the two characteristic morning/evening peaks with a
  midday trough and near-empty small hours.

## Layer 2 — anchored target

`delivery_time_minutes` is unchanged and remains a fixed function of the features:

```
delivery_time = 8.0
              + 2.5 · distance_km · traffic_factor   (interaction)
              + 1.5 · item_count
              + 6.0 · is_raining
              + 5.0 · rush_hour
              + N(0, spec.noise_level)               (clipped at 0)
```

where `traffic_factor ∈ {low: 1.0, medium: 1.5, high: 2.2}` and `rush_hour` is 1 for
hours `{7,8,9,17,18,19}`. Because the features are now correlated, the *joint* distribution
of `(features, target)` is more realistic — e.g. high-traffic rush-hour long-haul trips
co-occur — without changing what the model has to learn.

## Determinism & reproducibility

- All randomness flows through a single `numpy.random.Generator` passed into `generate_rows`;
  `Φ` and the inverse CDFs are pure functions. Same seed + same `n` ⇒ byte-identical rows.
- `n = 0` short-circuits to an empty, correctly-columned frame.
- The incremental CLI (`add_records`) offsets the RNG seed by the existing row total, so
  repeated `ds-agent-data add` runs append *distinct* rows while a fixed base seed + starting
  state reproduces the whole sequence.

## Where to tune it

All parameters are module-level constants at the top of `src/ds_agent_loop/data_gen.py`:
`_LATENT_CORR`, `_ITEM_COUNT_LAMBDA`, `_ITEM_COUNT_MAX`, `_DISTANCE_SIGMA`,
`_DISTANCE_MEDIAN`, `_DISTANCE_MAX`, `_RAIN_PROB`, `_HOUR_PEAKS`, `_HOUR_SD`,
`_DEFAULT_TRAFFIC_WEIGHTS`. If `_LATENT_CORR` is edited, keep it symmetric and
positive-definite (check `np.linalg.eigvalsh(C) > 0`).

> Scope note: this describes the **expandable synthetic flow** (`data_gen.py`,
> `state/{train,val,test}.csv`). The **frozen benchmark suite** (`benchmark.py`,
> `_make_delivery_time`) is a separate, deliberately fixed generator and is not affected.
