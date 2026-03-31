---
name: elo-calculator
description: |
  Calculate and update ELO ratings using the Bradley-Terry model with bootstrap
  confidence intervals. Use when implementing or modifying the leaderboard system,
  rating updates, or win probability calculations. Based on LMSYS Chatbot Arena
  methodology. Triggers on: "ELO", "rating", "leaderboard", "ranking", "Bradley-Terry".
---

# ELO Calculator Skill

## Algorithm: Bradley-Terry Maximum Likelihood

We use Bradley-Terry (not classic online ELO) because:
- We have full match history (centralized, not distributed)
- Agent configs are static between matches
- Bootstrap provides confidence intervals
- MLE is more stable than online updates

## Implementation

```python
import numpy as np
from scipy.optimize import minimize

def bradley_terry_mle(wins_matrix: np.ndarray) -> np.ndarray:
    """
    Compute Bradley-Terry ratings from a wins matrix.

    Args:
        wins_matrix: n×n matrix where wins_matrix[i][j] = times config i beat config j

    Returns:
        Array of ratings (higher = better), normalized to mean 1500
    """
    n = wins_matrix.shape[0]

    def neg_log_likelihood(ratings: np.ndarray) -> float:
        ll = 0.0
        for i in range(n):
            for j in range(i + 1, n):
                if wins_matrix[i, j] + wins_matrix[j, i] == 0:
                    continue
                p_i = 1.0 / (1.0 + np.exp(-(ratings[i] - ratings[j])))
                ll += wins_matrix[i, j] * np.log(p_i + 1e-10)
                ll += wins_matrix[j, i] * np.log(1.0 - p_i + 1e-10)
        return -ll

    result = minimize(neg_log_likelihood, np.zeros(n), method="BFGS")
    ratings = result.x

    # Normalize to ELO-like scale (mean=1500, std≈200)
    ratings = (ratings - ratings.mean()) / (ratings.std() + 1e-10) * 200 + 1500
    return ratings


def bootstrap_confidence(wins_matrix: np.ndarray, n_bootstrap: int = 1000) -> dict:
    """Compute 95% confidence intervals via bootstrap resampling."""
    n = wins_matrix.shape[0]
    all_ratings = []

    for _ in range(n_bootstrap):
        # Resample matches with replacement
        sampled = np.zeros_like(wins_matrix)
        for i in range(n):
            for j in range(i + 1, n):
                total = int(wins_matrix[i, j] + wins_matrix[j, i])
                if total > 0:
                    p = wins_matrix[i, j] / total
                    wins = np.random.binomial(total, p)
                    sampled[i, j] = wins
                    sampled[j, i] = total - wins
        all_ratings.append(bradley_terry_mle(sampled))

    all_ratings = np.array(all_ratings)
    return {
        "mean": np.mean(all_ratings, axis=0),
        "ci_lower": np.percentile(all_ratings, 2.5, axis=0),
        "ci_upper": np.percentile(all_ratings, 97.5, axis=0),
    }
```

## Rating Granularities
Track ELO at multiple levels:
1. **Team Configuration** — "5-agent Opus-heavy" vs "5-agent Sonnet-lean"
2. **Agent Role Template** — "Opus 4.6 Architect v2" per-role rating
3. **Model Provider** — "Claude Opus 4.6" vs "GPT-5" in specific roles
4. **Challenge Category** — Per-category leaderboards
5. **Strategy Pattern** — "research-first" vs "build-fast" vs "test-driven"

## Win Probability
```python
def win_probability(rating_a: float, rating_b: float) -> float:
    """Probability that team A beats team B."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400))
```
