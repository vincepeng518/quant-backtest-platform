from __future__ import annotations

import itertools
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Optional

import numpy as np

from engine.backtester import Backtester


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
            self.backtester.strategy.init(params)
            result = self.backtester.run()
            metric_val = getattr(result, self.metric, 0)
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
                r = self.backtester.run()
                scores.append(getattr(r, self.metric, 0))

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
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import RBF, ConstantKernel

        X, y = [], []
        for _ in range(n_initial):
            params = self._random_sample(param_space)
            self.backtester.strategy.init(params)
            r = self.backtester.run()
            X.append(self._params_to_vector(params, param_space))
            y.append(getattr(r, self.metric, 0))

        kernel = ConstantKernel(1.0) * RBF(length_scale=1.0)
        gp = GaussianProcessRegressor(kernel=kernel, n_restarts_optimizer=10)
        gp.fit(X, y)
        results: list[dict] = []

        for _ in range(n_iterations):
            best_x = self._acquisition(gp, X, y, param_space)
            params = self._vector_to_params(best_x, param_space)
            self.backtester.strategy.init(params)
            r = self.backtester.run()
            score = getattr(r, self.metric, 0)
            X.append(best_x)
            y.append(score)
            gp.fit(X, y)
            results.append({"params": params, "score": score})

        results.sort(key=lambda x: x["score"], reverse=self.maximize)
        return results

    # ── helpers ──

    def _random_sample(self, space: dict) -> dict:
        s = {}
        for k, p in space.items():
            if p["type"] == "range":
                val = np.random.uniform(p["min"], p["max"])
                if p.get("step", 1) >= 1:
                    val = int(round(val))
                s[k] = val
            elif p["type"] == "choice":
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
            if p["type"] == "range":
                vec.append((params[k] - p["min"]) / (p["max"] - p["min"] + 1e-9))
            elif p["type"] == "choice":
                vec.append(p["values"].index(params[k]) / max(len(p["values"]) - 1, 1))
        return vec

    def _vector_to_params(self, vec: list, space: dict) -> dict:
        params, idx = {}, 0
        for k, p in space.items():
            if p["type"] == "range":
                params[k] = vec[idx] * (p["max"] - p["min"]) + p["min"]
            elif p["type"] == "choice":
                i = int(round(vec[idx] * (len(p["values"]) - 1)))
                params[k] = p["values"][max(0, min(i, len(p["values"]) - 1))]
            idx += 1
        return params

    def _acquisition(self, gp, X, y, space) -> list:
        from scipy.optimize import minimize

        best = None
        best_val = np.inf
        bounds = [(0, 1)] * len(space)
        for _ in range(5):
            x0 = np.random.uniform(0, 1, len(space))
            try:
                res = minimize(lambda x: -gp.predict([x])[0], x0, bounds=bounds, method="L-BFGS-B")
                if best is None or res.fun < best_val:
                    best_val = res.fun
                    best = res.x.copy()
            except Exception:
                continue
        return best.tolist() if best is not None else np.random.uniform(0, 1, len(space)).tolist()