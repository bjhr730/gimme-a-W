"""Small numpy models with closed-form or Newton fits. No scikit-learn needed yet."""

from __future__ import annotations

import numpy as np


class Ridge:
    """Linear regression with L2 penalty (intercept unpenalized)."""

    def __init__(self, alpha: float = 1.0) -> None:
        self.alpha = alpha
        self.coef_: np.ndarray | None = None
        self.intercept_: float = 0.0

    def fit(self, x: np.ndarray, y: np.ndarray) -> Ridge:
        xb = np.hstack([np.ones((x.shape[0], 1)), x])
        penalty = self.alpha * np.eye(xb.shape[1])
        penalty[0, 0] = 0.0
        beta = np.linalg.solve(xb.T @ xb + penalty, xb.T @ y)
        self.intercept_ = float(beta[0])
        self.coef_ = beta[1:]
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        assert self.coef_ is not None
        return self.intercept_ + x @ self.coef_

    def residual_sd(self, x: np.ndarray, y: np.ndarray) -> float:
        r = y - self.predict(x)
        return float(np.sqrt(np.mean(r * r)))


class Logistic:
    """Logistic regression fit by Newton's method with a light L2 penalty."""

    def __init__(self, alpha: float = 0.5, iterations: int = 25) -> None:
        self.alpha = alpha
        self.iterations = iterations
        self.coef_: np.ndarray | None = None
        self.intercept_: float = 0.0

    def fit(
        self, x: np.ndarray, y: np.ndarray, sample_weight: np.ndarray | None = None
    ) -> Logistic:
        xb = np.hstack([np.ones((x.shape[0], 1)), x])
        w = np.ones(xb.shape[0]) if sample_weight is None else sample_weight
        beta = np.zeros(xb.shape[1])
        penalty = self.alpha * np.eye(xb.shape[1])
        penalty[0, 0] = 0.0
        for _ in range(self.iterations):
            p = 1.0 / (1.0 + np.exp(-(xb @ beta)))
            gradient = xb.T @ (w * (y - p)) - penalty @ beta
            s = w * p * (1 - p)
            hessian = (xb * s[:, None]).T @ xb + penalty
            step = np.linalg.solve(hessian, gradient)
            beta = beta + step
            if float(np.max(np.abs(step))) < 1e-8:
                break
        self.intercept_ = float(beta[0])
        self.coef_ = beta[1:]
        return self

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        assert self.coef_ is not None
        z = self.intercept_ + x @ self.coef_
        return 1.0 / (1.0 + np.exp(-z))


def log_loss(y: np.ndarray, p: np.ndarray, eps: float = 1e-6) -> float:
    p = np.clip(p, eps, 1 - eps)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def multiclass_log_loss(y_index: np.ndarray, probs: np.ndarray, eps: float = 1e-6) -> float:
    p = np.clip(probs[np.arange(len(y_index)), y_index], eps, 1.0)
    return float(-np.mean(np.log(p)))
