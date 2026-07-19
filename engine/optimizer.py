from __future__ import annotations

import itertools
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Optional

import numpy as np

from engine.backtester import Backtester


def _to_native(v: Any) -> Any:
    """Coerce numpy scalars to native Python for JSON safety."""
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return float(v)
    if isinstance(v, np.bool_):
        return bool(v)
    return v


class Optimizer:
    def __init__(self, backtester: Backtester, metric: str = "sharpe_ratio", maximize: bool = True) -> None:
        self.backtester = backtester
        self.metric = metric
        self.maximize = maximize

    def grid_search(self, param_space: dict[str, Any], max_workers: int = 4) -> list[dict[str, Any]]:
        keys = list(param_space.keys())
        values = []
        for k in keys:
            p = param_space[k]
            if p["type"] == "range":
                values.append(np.arange(p["min"], p["max"] + p["step"], p["step"]))
            elif p["type"] == "choice":
                values.append(p["values"])

        combos = list(itertools.product(*values))
        results: list[dict] = []
        for combo in combos:
            params = dict(zip(keys, combo))
            params = {k: _to_native(v) for k, v in params.items()}
            try:
                self.backtester.strategy.init(params)
                result = self.backtester.run()
                metric_val = getattr(result, self.metric, 0)
            except Exception:
                result = None
                metric_val = 0.0
            results.append({"params": params, "score": metric_val, "result": result})

        results.sort(key=lambda x: x["score"], reverse=self.maximize)
        return results

    def genetic_algorithm(
        self,
        param_space: dict[str, Any],
        population_size: int = 50,
        generations: int = 20,
        mutation_rate: float = 0.1,
        crossover_rate: float = 0.7,
    ) -> list[dict]:
        pop = [self._random_sample(param_space) for _ in range(population_size)]
        best_results: list[dict] = []

        for gen in range(generations):
            scores = []
            for ind in pop:
                self.backtester.strategy.init(ind)
                try:
                    r = self.backtester.run()
                    scores.append(getattr(r, self.metric, 0))
                except Exception:
                    scores.append(0.0)

            selected = self._tournament_selection(pop, scores, k=3)
            offspring: list[dict] = []
            while len(offspring) < population_size:
                if np.random.random() < crossover_rate:
                    p1, p2 = np.random.choice(len(selected), 2, replace=False)
                    c1, c2 = self._crossover(selected[p1], selected[p2])
                    offspring.extend([c1, c2])
            if len(offspring) > population_size:
                offspring = offspring[:population_size]

            pop = [self._mutate(param_space, ind, mutation_rate) for ind in offspring]
            best_i = int(np.argmax(scores))
            best_results.append({"generation": gen, "best_params": pop[best_i], "best_score": scores[best_i]})

        return best_results

    def bayesian_optimization(
        self, param_space: dict[str, Any], n_iterations: int = 30, n_initial: int = 10
    ) -> list[dict]:
        # Lightweight pure-numpy Gaussian Process (no sklearn dependency)
        import numpy as _np

        def _rbf(x1, x2, length=1.0, sigma=1.0):
            d = _np.sum((_np.array(x1) - _np.array(x2)) ** 2)
            return sigma * _np.exp(-0.5 * d / (length ** 2))

        def _gp_predict(X, y, x_new, noise=1e-6):
            if len(X) == 0:
                return 0.0, 1.0
            K = _np.array([[_rbf(a, b) for b in X] for a in X]) + noise * _np.eye(len(X))
            k_star = _np.array([_rbf(x_new, b) for b in X])
            try:
                K_inv = _np.linalg.inv(K)
                mean = k_star @ K_inv @ _np.array(y)
                var = _rbf(x_new, x_new) - k_star @ K_inv @ k_star
                return float(mean), float(max(var, 1e-6))
            except Exception:
                return float(_np.mean(y)) if len(y) else 0.0, 1.0

        X, y = [], []
        for _ in range(n_initial):
            params = self._random_sample(param_space)
            self.backtester.strategy.init(params)
            try:
                r = self.backtester.run()
                score = getattr(r, self.metric, 0)
            except Exception:
                score = 0.0
            X.append(self._params_to_vector(params, param_space))
            y.append(score)

        results: list[dict] = []
        y_mean = _np.mean(y) if y else 0.0
        y_std = _np.std(y) if y else 1.0
        y_scaled = [(v - y_mean) / (y_std + 1e-9) for v in y]

        for _ in range(n_iterations):
            best_x, best_ucb = None, -_np.inf
            for _ in range(20):
                cand = _np.random.uniform(0, 1, len(param_space))
                mu, var = _gp_predict(X, y_scaled, cand)
                ucb = mu + 1.5 * _np.sqrt(var)
                if ucb > best_ucb:
                    best_ucb = ucb
                    best_x = cand
            if best_x is None:
                best_x = _np.random.uniform(0, 1, len(param_space))
            params = self._vector_to_params(best_x, param_space)
            self.backtester.strategy.init(params)
            try:
                r = self.backtester.run()
                score = getattr(r, self.metric, 0)
            except Exception:
                score = 0.0
            X.append(best_x)
            y.append(score)
            y_scaled.append((score - y_mean) / (y_std + 1e-9))
            results.append({"params": params, "score": score})

        results.sort(key=lambda x: x["score"], reverse=self.maximize)
        return results

    # ── helpers ──

    def _random_sample(self, space: dict) -> dict:
        s = {}
        for k, p in space.items():
            t = p["type"]
            if t in ("range", "int"):
                val = np.random.uniform(p["min"], p["max"])
                if t == "int" or p.get("step", 1) >= 1:
                    val = int(round(val))
                s[k] = val
            elif t == "float":
                s[k] = float(np.random.uniform(p["min"], p["max"]))
            elif t == "choice":
                s[k] = np.random.choice(p["values"])
        return s

    def _tournament_selection(self, pop: list, scores: list, k: int) -> list:
        selected = []
        for _ in range(len(pop)):
            contestants = np.random.choice(len(pop), k, replace=False)
            winner = contestants[np.argmax([scores[i] for i in contestants])]
            selected.append(pop[winner])
        return selected

    def _crossover(self, p1: dict, p2: dict) -> tuple[dict, dict]:
        c1, c2 = {}, {}
        for k in p1:
            if np.random.random() < 0.5:
                c1[k], c2[k] = p1[k], p2[k]
            else:
                c1[k], c2[k] = p2[k], p1[k]
        return c1, c2

    def _mutate(self, space: dict, ind: dict, rate: float) -> dict:
        m = dict(ind)
        for k, p in space.items():
            if np.random.random() < rate:
                if p["type"] == "range":
                    step = p.get("step", 1)
                    m[k] += np.random.uniform(-step, step) if step < 1 else np.random.choice([-step, step])
                    m[k] = max(p["min"], min(p["max"], m[k]))
                    if step >= 1:
                        m[k] = int(round(m[k]))
                elif p["type"] == "choice":
                    m[k] = np.random.choice(p["values"])
        return m

    def _params_to_vector(self, params: dict, space: dict) -> list:
        vec = []
        for k, p in space.items():
            if p["type"] in ("range", "int", "float"):
                vec.append((params[k] - p["min"]) / (p["max"] - p["min"] + 1e-9))
            elif p["type"] == "choice":
                vec.append(p["values"].index(params[k]) / max(len(p["values"]) - 1, 1))
        return vec

    def _vector_to_params(self, vec: list, space: dict) -> dict:
        params, idx = {}, 0
        for k, p in space.items():
            t = p["type"]
            if t in ("range", "int", "float"):
                val = vec[idx] * (p["max"] - p["min"]) + p["min"]
                if t == "int":
                    val = int(round(val))
                elif t == "float":
                    val = float(val)
                elif p.get("step", 1) >= 1:
                    val = int(round(val))
                params[k] = val
            elif t == "choice":
                i = int(round(vec[idx] * (len(p["values"]) - 1)))
                params[k] = p["values"][max(0, min(i, len(p["values"]) - 1))]
            idx += 1
        return params
