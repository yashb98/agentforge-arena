"""Tests for the Bradley-Terry ELO calculator."""

from __future__ import annotations

import numpy as np
import pytest

from packages.core.src.elo.calculator import (
    RatingResult,
    bootstrap_confidence,
    bradley_terry_mle,
    compute_leaderboard,
    win_probability,
)


class TestBradleyTerryMLE:
    """Tests for the Bradley-Terry MLE rating computation."""

    def test_two_equal_teams_get_equal_ratings(self):
        """Two teams with equal wins should get equal ratings."""
        wins = np.array([
            [0, 5],
            [5, 0],
        ])
        ratings = bradley_terry_mle(wins)
        assert abs(ratings[0] - ratings[1]) < 1.0  # Should be nearly equal

    def test_dominant_team_gets_higher_rating(self):
        """A team that wins more should get a higher rating."""
        wins = np.array([
            [0, 8],
            [2, 0],
        ])
        ratings = bradley_terry_mle(wins)
        assert ratings[0] > ratings[1]

    def test_ratings_centered_around_1500(self):
        """Ratings should be normalized around 1500."""
        wins = np.array([
            [0, 3, 5],
            [7, 0, 4],
            [5, 6, 0],
        ])
        ratings = bradley_terry_mle(wins)
        mean_rating = np.mean(ratings)
        assert abs(mean_rating - 1500.0) < 1.0

    def test_single_config_returns_1500(self):
        """Single config should get default 1500 rating."""
        wins = np.array([[0]])
        ratings = bradley_terry_mle(wins)
        assert ratings[0] == 1500.0

    def test_three_teams_with_clear_hierarchy(self):
        """Three teams with A > B > C should produce ordered ratings."""
        wins = np.array([
            [0, 8, 9],   # Team A: beats B 8 times, beats C 9 times
            [2, 0, 7],   # Team B: beats A 2 times, beats C 7 times
            [1, 3, 0],   # Team C: beats A 1 time, beats B 3 times
        ])
        ratings = bradley_terry_mle(wins)
        assert ratings[0] > ratings[1] > ratings[2]

    def test_zero_matches_handled(self):
        """Teams with no head-to-head matches should still get ratings."""
        wins = np.array([
            [0, 5, 0],
            [5, 0, 5],
            [0, 5, 0],
        ])
        ratings = bradley_terry_mle(wins)
        assert len(ratings) == 3
        assert all(np.isfinite(ratings))


class TestWinProbability:
    """Tests for win probability calculation."""

    def test_equal_ratings_give_50_percent(self):
        """Equal ratings should give 50% win probability."""
        prob = win_probability(1500.0, 1500.0)
        assert abs(prob - 0.5) < 0.001

    def test_higher_rating_gives_higher_probability(self):
        """Higher-rated team should have >50% win probability."""
        prob = win_probability(1700.0, 1500.0)
        assert prob > 0.5

    def test_lower_rating_gives_lower_probability(self):
        """Lower-rated team should have <50% win probability."""
        prob = win_probability(1300.0, 1500.0)
        assert prob < 0.5

    def test_400_point_gap_gives_about_90_percent(self):
        """400 point rating gap should give ~90% win probability."""
        prob = win_probability(1900.0, 1500.0)
        assert abs(prob - 0.909) < 0.01

    def test_symmetry(self):
        """P(A beats B) + P(B beats A) should equal 1."""
        prob_a = win_probability(1600.0, 1500.0)
        prob_b = win_probability(1500.0, 1600.0)
        assert abs(prob_a + prob_b - 1.0) < 0.001


class TestBootstrapConfidence:
    """Tests for bootstrap confidence interval computation."""

    def test_confidence_intervals_contain_mle(self):
        """CI should contain the MLE estimate."""
        wins = np.array([
            [0, 7],
            [3, 0],
        ])
        ci = bootstrap_confidence(wins, n_bootstrap=100)

        mle = bradley_terry_mle(wins)
        for i in range(2):
            assert ci["ci_lower"][i] <= mle[i] <= ci["ci_upper"][i]

    def test_wider_ci_with_fewer_matches(self):
        """Fewer matches should produce wider confidence intervals."""
        # Many matches
        wins_many = np.array([[0, 70], [30, 0]])
        ci_many = bootstrap_confidence(wins_many, n_bootstrap=100)

        # Few matches
        wins_few = np.array([[0, 7], [3, 0]])
        ci_few = bootstrap_confidence(wins_few, n_bootstrap=100)

        width_many = (ci_many["ci_upper"] - ci_many["ci_lower"]).mean()
        width_few = (ci_few["ci_upper"] - ci_few["ci_lower"]).mean()

        assert width_few > width_many


class TestComputeLeaderboard:
    """Tests for the full leaderboard computation."""

    def test_leaderboard_sorted_by_rating(self):
        """Leaderboard should be sorted by rating descending."""
        names = ["All-Opus", "Balanced", "Budget"]
        wins = np.array([
            [0, 8, 9],
            [2, 0, 7],
            [1, 3, 0],
        ])

        results = compute_leaderboard(names, wins, n_bootstrap=50)

        assert len(results) == 3
        assert results[0].rating >= results[1].rating >= results[2].rating

    def test_leaderboard_win_rates_correct(self):
        """Win rates should be correctly calculated."""
        names = ["A", "B"]
        wins = np.array([[0, 8], [2, 0]])

        results = compute_leaderboard(names, wins, n_bootstrap=50)

        # Find Team A's result
        team_a = next(r for r in results if r.config_name == "A")
        assert team_a.wins == 8
        assert team_a.losses == 2
        assert team_a.matches_played == 10
        assert abs(team_a.win_rate - 0.8) < 0.001

    def test_leaderboard_has_confidence_intervals(self):
        """Each entry should have confidence intervals."""
        names = ["A", "B"]
        wins = np.array([[0, 6], [4, 0]])

        results = compute_leaderboard(names, wins, n_bootstrap=50)

        for result in results:
            assert result.ci_lower <= result.rating <= result.ci_upper

    def test_matrix_shape_mismatch_raises(self):
        """Mismatched names and matrix should raise."""
        names = ["A", "B"]
        wins = np.array([[0, 5, 3], [5, 0, 2], [7, 8, 0]])

        with pytest.raises(AssertionError):
            compute_leaderboard(names, wins)
