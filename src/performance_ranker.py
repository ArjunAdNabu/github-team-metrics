"""Performance ranking module for individual engineer reports.

Calculates composite scores: 50% complexity + 50% other metrics.
"""

import logging
from typing import Dict, List

logger = logging.getLogger('github_metrics')


class PerformanceRanker:
    """Calculate performance rankings for engineers."""

    def __init__(self):
        """Initialize performance ranker."""
        self.complexity_weight = 0.5  # 50% weight on complexity score
        self.other_weight = 0.5  # 50% weight on other metrics

    def normalize_to_100(self, value: float, min_val: float, max_val: float) -> float:
        """
        Normalize a value to 0-100 scale.

        Args:
            value: Value to normalize
            min_val: Minimum value in dataset
            max_val: Maximum value in dataset

        Returns:
            Normalized value (0-100)
        """
        if max_val == min_val:
            return 50.0  # All same, return middle value

        normalized = ((value - min_val) / (max_val - min_val)) * 100
        return round(normalized, 2)

    def calculate_complexity_component(
        self,
        engineer_data: List[Dict]
    ) -> Dict[str, float]:
        """
        Calculate complexity component (0-100) for all engineers.

        Args:
            engineer_data: List of engineer dictionaries with metrics

        Returns:
            Dictionary mapping usernames to complexity scores (0-100)
        """
        # Extract complexity scores
        complexity_scores = {
            eng['github_username']: eng.get('total_complexity_score', 0)
            for eng in engineer_data
        }

        # Find min and max for normalization
        values = list(complexity_scores.values())
        min_complexity = min(values) if values else 0
        max_complexity = max(values) if values else 0

        # Normalize to 0-100
        normalized = {}
        for username, score in complexity_scores.items():
            normalized[username] = self.normalize_to_100(
                score,
                min_complexity,
                max_complexity
            )

        logger.info(
            f"Complexity scores: min={min_complexity}, max={max_complexity}"
        )

        return normalized

    def calculate_other_component(
        self,
        engineer_data: List[Dict]
    ) -> Dict[str, float]:
        """
        Calculate 'other metrics' component (0-100) for all engineers.

        Combines:
        - Code quality score (AI, 0-10 → 0-100)
        - Review quality score (AI, 0-10 → 0-100)
        - Commit frequency (normalized)
        - PR merge rate (0-100)
        - Review participation (normalized)

        Args:
            engineer_data: List of engineer dictionaries with metrics

        Returns:
            Dictionary mapping usernames to other scores (0-100)
        """
        # Extract metrics for normalization
        commit_frequencies = [eng.get('commit_frequency', 0) for eng in engineer_data]
        review_participations = [eng.get('review_participation', 0) for eng in engineer_data]

        min_freq = min(commit_frequencies) if commit_frequencies else 0
        max_freq = max(commit_frequencies) if commit_frequencies else 0

        min_review = min(review_participations) if review_participations else 0
        max_review = max(review_participations) if review_participations else 0

        other_scores = {}

        for eng in engineer_data:
            username = eng['github_username']

            # AI scores (already 0-10, convert to 0-100)
            ai_analysis = eng.get('ai_analysis', {})
            code_quality = ai_analysis.get('code_quality', {})
            review_quality = ai_analysis.get('review_quality', {})

            code_score = code_quality.get('quality_score', 0) * 10  # 0-10 → 0-100
            review_score = (
                (review_quality.get('thoroughness_score', 0) +
                 review_quality.get('helpfulness_score', 0)) / 2
            ) * 10  # Average of two scores, then → 0-100

            # Quantitative metrics (normalize to 0-100)
            commit_freq_norm = self.normalize_to_100(
                eng.get('commit_frequency', 0),
                min_freq,
                max_freq
            )

            pr_merge_rate = eng.get('pr_merge_rate', 0)  # Already 0-100

            review_participation_norm = self.normalize_to_100(
                eng.get('review_participation', 0),
                min_review,
                max_review
            )

            # Calculate weighted average (equal weights)
            components = [
                code_score,
                review_score,
                commit_freq_norm,
                pr_merge_rate,
                review_participation_norm
            ]

            # Filter out zero components if engineer has no data in that area
            non_zero_components = [c for c in components if c > 0]

            if non_zero_components:
                other_score = sum(non_zero_components) / len(non_zero_components)
            else:
                other_score = 0.0

            other_scores[username] = round(other_score, 2)

        logger.info(f"Calculated 'other metrics' scores for {len(other_scores)} engineers")

        return other_scores

    def calculate_composite_scores(
        self,
        engineer_data: List[Dict]
    ) -> Dict[str, Dict]:
        """
        Calculate composite scores for all engineers.

        Composite Score = (Complexity × 0.5) + (Other Metrics × 0.5)

        Args:
            engineer_data: List of engineer dictionaries with metrics

        Returns:
            Dictionary mapping usernames to score breakdowns:
            {
                'username': {
                    'complexity_component': float (0-100),
                    'other_component': float (0-100),
                    'composite_score': float (0-100)
                }
            }
        """
        complexity_scores = self.calculate_complexity_component(engineer_data)
        other_scores = self.calculate_other_component(engineer_data)

        composite_scores = {}

        for username in complexity_scores.keys():
            complexity_comp = complexity_scores[username]
            other_comp = other_scores.get(username, 0)

            composite = (
                complexity_comp * self.complexity_weight +
                other_comp * self.other_weight
            )

            composite_scores[username] = {
                'complexity_component': complexity_comp,
                'other_component': other_comp,
                'composite_score': round(composite, 2)
            }

        logger.info(f"Calculated composite scores for {len(composite_scores)} engineers")

        return composite_scores

    def rank_engineers(
        self,
        engineer_data: List[Dict]
    ) -> List[Dict]:
        """
        Rank engineers by composite score and add ranking information.

        Args:
            engineer_data: List of engineer dictionaries with metrics

        Returns:
            List of engineer dictionaries with added ranking fields:
            - composite_score: float (0-100)
            - complexity_component: float (0-100)
            - other_component: float (0-100)
            - rank: int (1, 2, 3, ...)
            - percentile: float (0-100)
            - rank_label: str ("🥇 Top Performer", etc.)
        """
        if not engineer_data:
            return []

        # Calculate composite scores
        composite_scores = self.calculate_composite_scores(engineer_data)

        # Add scores to engineer data
        for eng in engineer_data:
            username = eng['github_username']
            scores = composite_scores.get(username, {
                'complexity_component': 0,
                'other_component': 0,
                'composite_score': 0
            })

            eng['complexity_component'] = scores['complexity_component']
            eng['other_component'] = scores['other_component']
            eng['composite_score'] = scores['composite_score']

        # Sort by composite score (descending)
        ranked_engineers = sorted(
            engineer_data,
            key=lambda x: x['composite_score'],
            reverse=True
        )

        # Assign ranks and percentiles
        total_engineers = len(ranked_engineers)

        for i, eng in enumerate(ranked_engineers, 1):
            eng['rank'] = i
            eng['percentile'] = round((1 - (i - 1) / total_engineers) * 100, 1)
            eng['rank_label'] = self._get_rank_label(i, total_engineers)

        logger.info(
            f"Ranked {total_engineers} engineers. "
            f"Top performer: {ranked_engineers[0]['github_username']} "
            f"(score: {ranked_engineers[0]['composite_score']})"
        )

        return ranked_engineers

    def _get_rank_label(self, rank: int, total: int) -> str:
        """
        Get rank label based on position.

        Args:
            rank: Engineer's rank (1-based)
            total: Total number of engineers

        Returns:
            Rank label string
        """
        if rank == 1:
            return "🥇 Top Performer"
        elif rank / total <= 0.10:
            return "⭐ High Performer"
        elif rank / total <= 0.50:
            return "✓ Above Average"
        else:
            return "→ Developing"

    def get_rank_summary(self, ranked_engineers: List[Dict]) -> Dict:
        """
        Get summary statistics for rankings.

        Args:
            ranked_engineers: List of ranked engineer dictionaries

        Returns:
            Summary dictionary with statistics
        """
        if not ranked_engineers:
            return {}

        composite_scores = [eng['composite_score'] for eng in ranked_engineers]

        summary = {
            'total_engineers': len(ranked_engineers),
            'avg_composite_score': round(sum(composite_scores) / len(composite_scores), 2),
            'min_composite_score': min(composite_scores),
            'max_composite_score': max(composite_scores),
            'top_performer': ranked_engineers[0]['github_username'],
            'top_performer_score': ranked_engineers[0]['composite_score'],
            'score_distribution': {
                'top_10_percent': len([e for e in ranked_engineers if e['percentile'] >= 90]),
                'top_50_percent': len([e for e in ranked_engineers if e['percentile'] >= 50]),
                'bottom_50_percent': len([e for e in ranked_engineers if e['percentile'] < 50])
            }
        }

        logger.info(
            f"Ranking summary: avg={summary['avg_composite_score']}, "
            f"min={summary['min_composite_score']}, "
            f"max={summary['max_composite_score']}"
        )

        return summary
