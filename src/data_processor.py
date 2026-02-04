"""Data processing and combination of GitHub and ticket metrics."""

import logging
from typing import Dict, List, Set
from difflib import SequenceMatcher


logger = logging.getLogger('github_metrics')


class DataCombiner:
    """Combine GitHub metrics with ticket data."""

    def __init__(self, team_member_map: Dict[str, str] = None):
        """
        Initialize data combiner.

        Args:
            team_member_map: Manual mapping from ticket names to GitHub usernames
                            Example: {"John Doe": "john-doe", "Jane Smith": "jsmith"}
        """
        self.team_member_map = team_member_map or {}

    def merge_datasets(
        self,
        github_data: Dict[str, Dict],
        ticket_data: Dict[str, Dict]
    ) -> List[Dict]:
        """
        Merge GitHub metrics with ticket data.

        Args:
            github_data: GitHub metrics by username
            ticket_data: Ticket metrics by assigned name

        Returns:
            List of combined user metrics
        """
        # Create user matching
        matches = self._match_users(
            set(github_data.keys()),
            set(ticket_data.keys())
        )

        combined_data = []

        # Process matched users
        for github_user, ticket_user in matches['matched']:
            github_metrics = github_data.get(github_user, {})
            ticket_metrics = ticket_data.get(ticket_user, {})

            combined = self._merge_user_metrics(
                github_user,
                github_metrics,
                ticket_metrics,
                'GitHub+Sheets'
            )
            combined_data.append(combined)

        # Process GitHub-only users
        for github_user in matches['github_only']:
            github_metrics = github_data.get(github_user, {})
            combined = self._merge_user_metrics(
                github_user,
                github_metrics,
                {},
                'GitHub Only'
            )
            combined_data.append(combined)

        # Process ticket-only users
        for ticket_user in matches['ticket_only']:
            ticket_metrics = ticket_data.get(ticket_user, {})
            combined = self._merge_user_metrics(
                ticket_user,  # Use ticket name as username
                {},
                ticket_metrics,
                'Sheets Only'
            )
            combined_data.append(combined)

        logger.info(f"Combined data for {len(combined_data)} team members")
        return combined_data

    def _match_users(
        self,
        github_users: Set[str],
        ticket_users: Set[str]
    ) -> Dict[str, List]:
        """
        Match GitHub usernames to ticket assigned names.

        Args:
            github_users: Set of GitHub usernames
            ticket_users: Set of ticket assigned names

        Returns:
            Dictionary with matched, github_only, and ticket_only lists
        """
        matched = []
        github_only = set(github_users)
        ticket_only = set(ticket_users)

        # Try exact matches (case-insensitive)
        for ticket_user in list(ticket_only):
            for github_user in list(github_only):
                if ticket_user.lower() == github_user.lower():
                    matched.append((github_user, ticket_user))
                    github_only.discard(github_user)
                    ticket_only.discard(ticket_user)
                    break

        # Try manual mapping
        for ticket_user in list(ticket_only):
            if ticket_user in self.team_member_map:
                github_user = self.team_member_map[ticket_user]
                if github_user in github_only:
                    matched.append((github_user, ticket_user))
                    github_only.discard(github_user)
                    ticket_only.discard(ticket_user)

        # Try fuzzy matching on remaining users
        for ticket_user in list(ticket_only):
            best_match = None
            best_ratio = 0.7  # Minimum similarity threshold

            for github_user in github_only:
                # Compare strings
                ratio = SequenceMatcher(
                    None,
                    ticket_user.lower().replace(' ', ''),
                    github_user.lower().replace('-', '').replace('_', '')
                ).ratio()

                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = github_user

            if best_match:
                matched.append((best_match, ticket_user))
                github_only.discard(best_match)
                ticket_only.discard(ticket_user)
                logger.info(f"Fuzzy matched: '{ticket_user}' -> '{best_match}' (similarity: {best_ratio:.2f})")

        return {
            'matched': matched,
            'github_only': list(github_only),
            'ticket_only': list(ticket_only)
        }

    def _merge_user_metrics(
        self,
        username: str,
        github_metrics: Dict,
        ticket_metrics: Dict,
        data_source: str
    ) -> Dict:
        """
        Merge metrics for a single user.

        Args:
            username: User identifier
            github_metrics: GitHub metrics dictionary
            ticket_metrics: Ticket metrics dictionary
            data_source: Source indicator (e.g., 'GitHub+Sheets', 'GitHub Only')

        Returns:
            Combined metrics dictionary
        """
        # Start with GitHub data
        combined = {
            'github_username': username,
            'display_name': github_metrics.get('display_name', username),
            'email': github_metrics.get('email', ''),

            # GitHub metrics
            'total_commits': github_metrics.get('total_commits', 0),
            'commit_frequency': github_metrics.get('commit_frequency', 0),
            'lines_added': github_metrics.get('lines_added', 0),
            'lines_deleted': github_metrics.get('lines_deleted', 0),
            'lines_changed': github_metrics.get('lines_changed', 0),
            'prs_created': github_metrics.get('prs_created', 0),
            'prs_merged': github_metrics.get('prs_merged', 0),
            'pr_merge_rate': github_metrics.get('pr_merge_rate', 0),
            'avg_pr_size': github_metrics.get('avg_pr_size', 0),
            'issues_closed': github_metrics.get('issues_closed', 0),
            'reviews_given': github_metrics.get('reviews_given', 0),
            'reviews_received': github_metrics.get('reviews_received', 0),
            'review_participation': github_metrics.get('review_participation', 0),
            'avg_review_time_hours': github_metrics.get('avg_review_time_hours', 0),
            'active_repos': ', '.join(github_metrics.get('active_repos', [])),

            # Ticket metrics
            'total_tickets': ticket_metrics.get('total_tickets', 0),
            'tickets_open': ticket_metrics.get('tickets_open', 0),
            'tickets_closed': ticket_metrics.get('tickets_closed', 0),
            'tickets_high_priority': ticket_metrics.get('tickets_high_priority', 0),
            'tickets_medium_priority': ticket_metrics.get('tickets_medium_priority', 0),
            'tickets_low_priority': ticket_metrics.get('tickets_low_priority', 0),
            'avg_resolution_time_hours': ticket_metrics.get('avg_resolution_time_hours', 0),
            'avg_first_response_time_hours': ticket_metrics.get('avg_first_response_time_hours', 0),
            'tickets_with_github_issue': ticket_metrics.get('tickets_with_github_issue', 0),
            'ticket_types': str(ticket_metrics.get('ticket_types', {})),

            # Metadata
            'data_sources': data_source,
            'last_active': github_metrics.get('last_active', '')
        }

        return combined

    def handle_unmatched_users(
        self,
        github_users: Set[str],
        ticket_users: Set[str]
    ) -> Dict[str, List]:
        """
        Report on users that appear in one dataset but not the other.

        Args:
            github_users: Set of GitHub usernames
            ticket_users: Set of ticket assigned names

        Returns:
            Dictionary with matched, github_only, and ticket_only lists
        """
        matches = self._match_users(github_users, ticket_users)

        logger.info(f"User matching results:")
        logger.info(f"  Matched: {len(matches['matched'])} users")
        if matches['github_only']:
            logger.info(f"  GitHub only: {len(matches['github_only'])} users - {', '.join(matches['github_only'])}")
        if matches['ticket_only']:
            logger.info(f"  Tickets only: {len(matches['ticket_only'])} users - {', '.join(matches['ticket_only'])}")

        return matches


class MetricsCalculator:
    """Calculate derived metrics from combined data."""

    @staticmethod
    def calculate_commit_frequency(commits: List[Dict], days: int) -> float:
        """
        Calculate commits per day.

        Args:
            commits: List of commit dictionaries
            days: Number of days in period

        Returns:
            Commits per day
        """
        if days <= 0:
            return 0.0
        return round(len(commits) / days, 2)

    @staticmethod
    def calculate_pr_merge_rate(prs_created: int, prs_merged: int) -> float:
        """
        Calculate percentage of PRs that were merged.

        Args:
            prs_created: Number of PRs created
            prs_merged: Number of PRs merged

        Returns:
            Merge rate as percentage
        """
        if prs_created == 0:
            return 0.0
        return round((prs_merged / prs_created) * 100, 1)

    @staticmethod
    def calculate_review_participation(reviews_given: int, reviews_received: int) -> float:
        """
        Calculate review participation ratio.

        Args:
            reviews_given: Number of reviews given
            reviews_received: Number of reviews received

        Returns:
            Ratio of reviews given to received
        """
        if reviews_received == 0:
            return 0.0
        return round(reviews_given / reviews_received, 2)

    @staticmethod
    def calculate_derived_metrics(combined_data: List[Dict]) -> List[Dict]:
        """
        Calculate additional derived metrics for all users.

        Args:
            combined_data: List of combined user metrics

        Returns:
            Enhanced data with derived metrics
        """
        for user_data in combined_data:
            # Commits per ticket ratio
            total_commits = user_data.get('total_commits', 0)
            total_tickets = user_data.get('total_tickets', 0)

            if total_tickets > 0:
                user_data['commits_per_ticket'] = round(total_commits / total_tickets, 1)
            else:
                user_data['commits_per_ticket'] = 0

            # Activity score (simple weighted formula)
            # Weights: commits (1), PRs (2), reviews (1.5), tickets (1)
            activity_score = (
                total_commits * 1 +
                user_data.get('prs_created', 0) * 2 +
                user_data.get('reviews_given', 0) * 1.5 +
                total_tickets * 1
            )
            user_data['activity_score'] = round(activity_score, 1)

            # Ticket closure rate
            tickets_closed = user_data.get('tickets_closed', 0)
            if total_tickets > 0:
                user_data['ticket_closure_rate'] = round((tickets_closed / total_tickets) * 100, 1)
            else:
                user_data['ticket_closure_rate'] = 0

        return combined_data
