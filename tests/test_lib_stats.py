import numpy as np
from research.breakout_jev2.lib_stats import boot_ci, required_samples, mc_paths, mc_summary


def test_boot_ci_brackets_true_mean():
    rng = np.random.default_rng(0)
    x = rng.normal(0.01, 0.05, 4000)
    mean, lo, hi = boot_ci(x, n=2000, seed=1)
    assert lo < mean < hi
    assert abs(mean - 0.01) < 0.005


def test_required_samples_grows_when_target_shrinks():
    need = required_samples(trades_per_month=100, target_monthly=0.20, payoff=1.5,
                            fee_roundtrip=0.0014, win_rate=0.42)
    assert need > 0
    need_lo = required_samples(trades_per_month=100, target_monthly=0.05, payoff=1.5,
                               fee_roundtrip=0.0014, win_rate=0.42)
    assert need < need_lo


def test_mc_paths_reproducible_with_seed():
    r = np.array([0.01, -0.005, 0.02, -0.01, 0.003] * 20)
    a = mc_paths(r, n_steps=50, n_sims=100, seed=42)
    b = mc_paths(r, n_steps=50, n_sims=100, seed=42)
    assert np.allclose(a, b)


def test_mc_summary_reports_bankruptcy_and_percentiles():
    r = np.array([0.02, -0.03] * 100)
    s = mc_summary(mc_paths(r, n_steps=60, n_sims=500, seed=3), initial=1.0)
    for k in ("median", "p5", "p95", "bankruptcy_prob_pct",
              "maxdd_median_pct", "maxdd_p95_pct"):
        assert k in s
    assert s["maxdd_p95_pct"] >= s["maxdd_median_pct"]
