"""
AgentForge Arena — ELO Rating Calculator

Bradley-Terry Maximum Likelihood Estimation with bootstrap confidence intervals.
Based on LMSYS Chatbot Arena methodology.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

logger = logging.getLogger(__name__)


@dataclass
class RatingResult:
    """Result of an ELO calculation."""

    config_name: str
    rating: float
    ci_lower: float
    ci_upper: float
    matches_played: int
    wins: int
    losses: int
    win_rate: float


def bradley_terry_mle(wins_matrix: np.ndarray) -> np.ndarray:
    """Compute Bradley-Terry ratings from a wins matrix.

    Args:
        wins_matrix: n×n matrix where wins_matrix[i][j] = times config i beat config j

    Returns:
        Array of ratings normalized to ELO scale (mean=1500, std≈200)
    """
    n = wins_matrix.shape[0]
    if n < 2:
        return np.array([1500.0] * n)

    def neg_log_likelihood(ratings: np.ndarray) -> float:
        ll = 0.0
        for i in range(n):
            for j in range(i + 1, n):
                total = wins_matrix[i, j] + wins_matrix[j, i]
                if total == 0:
                    continue
                p_i = 1.0 / (1.0 + np.exp(-(ratings[i] - ratings[j])))
                ll += wins_matrix[i, j] * np.log(p_i + 1e-10)
                ll += wins_matrix[j, i] * np.log(1.0 - p_i + 1e-10)
        return -ll

    result = minimize(neg_log_likelihood, np.zeros(n), method="BFGS")
    ratings = result.x

    # Normalize to ELO-like scale
    std = ratings.std()
    if std > 0:
        ratings = (ratings - ratings.mean()) / std * 200 + 1500
    else:
        ratings = np.full(n, 1500.0)

    return ratings


def bootstrap_confidence(
    wins_matrix: np.ndarray,
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
) -> dict[str, np.ndarray]:
    """Compute confidence intervals via bootstrap resampling.

    Returns dict with keys: mean, ci_lower, ci_upper
    """
    n = wins_matrix.shape[0]
    alpha = (1 - confidence) / 2
    all_ratings = []

    for _ in range(n_bootstrap):
        sampled = np.zeros_like(wins_matrix)
        for i in range(n):
            for j in range(i + 1, n):
                total = int(wins_matrix[i, j] + wins_matrix[j, i])
                if total > 0:
                    p = wins_matrix[i, j] / total
                    wins = np.random.binomial(total, p)
                    sampled[i, j] = wins
                    sampled[j, i] = total - wins

        ratings = bradley_terry_mle(sampled)
        all_ratings.append(ratings)

    all_ratings_arr = np.array(all_ratings)
    return {
        "mean": np.mean(all_ratings_arr, axis=0),
        "ci_lower": np.percentile(all_ratings_arr, alpha * 100, axis=0),
        "ci_upper": np.percentile(all_ratings_arr, (1 - alpha) * 100, axis=0),
    }


def win_probability(rating_a: float, rating_b: float) -> float:
    """Probability that team A beats team B given their ratings."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400))


def compute_leaderboard(
    config_names: list[str],
    wins_matrix: np.ndarray,
    n_bootstrap: int = 500,
) -> list[RatingResult]:
    """Compute full leaderboard with confidence intervals.

    Args:
        config_names: Names of each team configuration
        wins_matrix: n×n wins matrix
        n_bootstrap: Number of bootstrap samples for CI

    Returns:
        Sorted list of RatingResult (highest rating first)
    """
    n = len(config_names)
    assert wins_matrix.shape == (n, n), f"Matrix shape mismatch: {wins_matrix.shape} vs ({n},{n})"

    # Compute ratings
    ratings = bradley_terry_mle(wins_matrix)

    # Compute confidence intervals
    ci = bootstrap_confidence(wins_matrix, n_bootstrap=n_bootstrap)

    # Build results
    results = []
    for i in range(n):
        total_wins = int(wins_matrix[i].sum())
        total_losses = int(wins_matrix[:, i].sum())
        total_matches = total_wins + total_losses
        win_rate = total_wins / max(total_matches, 1)

        results.append(RatingResult(
            config_name=config_names[i],
            rating=float(ratings[i]),
            ci_lower=float(ci["ci_lower"][i]),
            ci_upper=float(ci["ci_upper"][i]),
            matches_played=total_matches,
            wins=total_wins,
            losses=total_losses,
            win_rate=win_rate,
        ))

    # Sort by rating descending
    results.sort(key=lambda r: r.rating, reverse=True)
    return results
