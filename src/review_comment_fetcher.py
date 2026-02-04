"""Review comment fetcher for individual performance reports.

Fetches PR review comments to analyze code review quality.
"""

import logging
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

logger = logging.getLogger('github_metrics')


class ReviewCommentFetcher:
    """Fetch review comments from pull requests."""

    def __init__(self, github_client, sample_size: int = 5):
        """
        Initialize review comment fetcher.

        Args:
            github_client: GitHubClient instance for API calls
            sample_size: Number of reviews to sample per engineer
        """
        self.github_client = github_client
        self.sample_size = sample_size

    def get_pr_review_comments(self, repo_name: str, pr_number: int) -> List[Dict]:
        """
        Get review comments for a specific pull request using REST API.

        Args:
            repo_name: Repository name (e.g., 'owner/repo')
            pr_number: Pull request number

        Returns:
            List of review comment dictionaries:
            [{
                'id': int,
                'body': str,
                'path': str,  # File being reviewed
                'line': int,  # Line number
                'user': str,  # Reviewer username
                'created_at': str
            }]
        """
        try:
            # Use REST API: GET /repos/{owner}/{repo}/pulls/{pull_number}/comments
            url = f"{self.github_client.base_url}/repos/{repo_name}/pulls/{pr_number}/comments"

            response = self.github_client.session.get(
                url,
                headers=self.github_client.headers,
                timeout=self.github_client.timeout
            )

            if response.status_code != 200:
                logger.warning(
                    f"Failed to fetch review comments for PR #{pr_number}: "
                    f"HTTP {response.status_code}"
                )
                return []

            comments_data = response.json()

            # Extract relevant information
            comments = []
            for comment in comments_data:
                comment_data = {
                    'id': comment['id'],
                    'body': comment['body'],
                    'path': comment['path'],
                    'line': comment.get('line') or comment.get('original_line'),
                    'user': comment['user']['login'],
                    'created_at': comment['created_at']
                }
                comments.append(comment_data)

            logger.debug(
                f"Fetched {len(comments)} review comments for PR #{pr_number}"
            )

            return comments

        except Exception as e:
            logger.error(
                f"Error fetching review comments for PR #{pr_number}: {e}"
            )
            return []

    def get_pr_review_summaries(self, repo_name: str, pr_number: int) -> List[Dict]:
        """
        Get high-level review summaries for a PR (approve, request changes, comment).

        Args:
            repo_name: Repository name (e.g., 'owner/repo')
            pr_number: Pull request number

        Returns:
            List of review summary dictionaries:
            [{
                'id': int,
                'user': str,
                'state': str,  # 'APPROVED', 'CHANGES_REQUESTED', 'COMMENTED'
                'body': str,
                'submitted_at': str
            }]
        """
        try:
            # Use REST API: GET /repos/{owner}/{repo}/pulls/{pull_number}/reviews
            url = f"{self.github_client.base_url}/repos/{repo_name}/pulls/{pr_number}/reviews"

            response = self.github_client.session.get(
                url,
                headers=self.github_client.headers,
                timeout=self.github_client.timeout
            )

            if response.status_code != 200:
                logger.warning(
                    f"Failed to fetch reviews for PR #{pr_number}: "
                    f"HTTP {response.status_code}"
                )
                return []

            reviews_data = response.json()

            # Extract relevant information
            reviews = []
            for review in reviews_data:
                review_data = {
                    'id': review['id'],
                    'user': review['user']['login'],
                    'state': review['state'],
                    'body': review.get('body', ''),
                    'submitted_at': review['submitted_at']
                }
                reviews.append(review_data)

            logger.debug(f"Fetched {len(reviews)} review summaries for PR #{pr_number}")

            return reviews

        except Exception as e:
            logger.error(f"Error fetching reviews for PR #{pr_number}: {e}")
            return []

    def sample_user_reviews(
        self,
        pull_requests: List[Dict],
        user_login: str,
        repo_name: str
    ) -> List[Dict]:
        """
        Smart sampling of reviews given by a user.

        Strategy:
        1. Filter PRs where user gave reviews
        2. Exclude trivial reviews (e.g., "LGTM", "Approved")
        3. Prefer reviews with substantive comments (>50 chars)
        4. Sample up to sample_size reviews

        Args:
            pull_requests: List of PR dictionaries
            user_login: GitHub username of reviewer
            repo_name: Repository name (e.g., 'owner/repo')

        Returns:
            List of review data dictionaries:
            [{
                'pr_number': int,
                'pr_title': str,
                'review_summary': Dict,  # From get_pr_review_summaries
                'review_comments': List[Dict],  # From get_pr_review_comments
                'repo': str
            }]
        """
        logger.info(f"Sampling reviews for {user_login} in {repo_name}...")

        reviews_data = []

        for pr in pull_requests:
            pr_number = pr['number']

            # Get review summaries for this PR
            summaries = self.get_pr_review_summaries(repo_name, pr_number)

            # Check if user reviewed this PR
            user_summaries = [s for s in summaries if s['user'] == user_login]

            if not user_summaries:
                continue

            # Get review comments
            comments = self.get_pr_review_comments(repo_name, pr_number)
            user_comments = [c for c in comments if c['user'] == user_login]

            # Calculate substantiveness
            total_text = sum(len(c['body']) for c in user_comments)
            total_text += sum(len(s['body']) for s in user_summaries)

            # Skip trivial reviews
            if total_text < 50:
                logger.debug(
                    f"Skipping trivial review by {user_login} on PR #{pr_number} "
                    f"({total_text} chars)"
                )
                continue

            review_data = {
                'pr_number': pr_number,
                'pr_title': pr.get('title', ''),
                'pr_author': pr.get('author_login', ''),
                'review_summaries': user_summaries,
                'review_comments': user_comments,
                'repo': repo_name,
                'total_comment_length': total_text
            }

            reviews_data.append(review_data)

        # Sort by substantiveness (most substantive first)
        reviews_data.sort(key=lambda r: r['total_comment_length'], reverse=True)

        # Sample
        sampled = reviews_data[:self.sample_size]

        logger.info(
            f"Sampled {len(sampled)} reviews for {user_login} in {repo_name} "
            f"(from {len(reviews_data)} total)"
        )

        return sampled

    def fetch_reviews_for_user(
        self,
        pull_requests: List[Dict],
        user_login: str,
        repo_name: str
    ) -> List[Dict]:
        """
        Fetch review data for a user in a repository.

        Args:
            pull_requests: List of PR dictionaries
            user_login: GitHub username
            repo_name: Repository name (e.g., 'owner/repo')

        Returns:
            List of review data dictionaries
        """
        return self.sample_user_reviews(pull_requests, user_login, repo_name)

    def fetch_reviews_for_all_users(
        self,
        prs_by_repo: Dict[str, List[Dict]],
        user_logins: List[str],
        max_workers: int = 10
    ) -> Dict[str, List[Dict]]:
        """
        Fetch reviews for multiple users across multiple repositories (CONCURRENT).

        Args:
            prs_by_repo: Dictionary mapping repo names to PR lists
            user_logins: List of GitHub usernames
            max_workers: Number of concurrent workers

        Returns:
            Dictionary mapping usernames to lists of review data:
            {
                'user1': [review1, review2, ...],
                'user2': [review1, review2, ...],
                ...
            }
        """
        reviews_by_user = {user: [] for user in user_logins}

        # Create tasks for each (repo, user) combination
        tasks = []
        for repo_name, prs in prs_by_repo.items():
            if not prs:
                continue

            logger.info(f"Fetching reviews for {repo_name}...")

            for user_login in user_logins:
                tasks.append((repo_name, prs, user_login))

        # Fetch reviews concurrently
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.fetch_reviews_for_user, prs, user, repo): (repo, user)
                for repo, prs, user in tasks
            }

            with tqdm(total=len(futures), desc="Fetching Reviews") as pbar:
                for future in as_completed(futures):
                    repo_name, user_login = futures[future]
                    try:
                        reviews = future.result(timeout=120)  # 2 min timeout per task
                        reviews_by_user[user_login].extend(reviews)
                    except Exception as e:
                        logger.error(f"Failed to fetch reviews for {user_login} in {repo_name}: {e}")
                    finally:
                        pbar.update(1)

        # Summary
        for user_login, reviews in reviews_by_user.items():
            logger.info(f"Total reviews for {user_login}: {len(reviews)}")

        return reviews_by_user

    def summarize_review(self, review: Dict, max_chars: int = 1000) -> str:
        """
        Create a summary of a review for AI analysis.

        Args:
            review: Review data dictionary from sample_user_reviews()
            max_chars: Maximum number of characters to include

        Returns:
            Summarized review string
        """
        summary = f"PR #{review['pr_number']}: {review['pr_title']}\n"
        summary += f"Author: {review['pr_author']}\n"
        summary += f"Repository: {review['repo']}\n\n"

        # Add review summaries
        for rs in review['review_summaries']:
            summary += f"Review: {rs['state']}\n"
            if rs['body']:
                summary += f"  {rs['body']}\n"

        # Add review comments
        if review['review_comments']:
            summary += f"\nComments ({len(review['review_comments'])}):\n"

            total_chars = len(summary)

            for comment in review['review_comments']:
                comment_text = f"  {comment['path']}:{comment['line']}\n"
                comment_text += f"    {comment['body']}\n"

                if total_chars + len(comment_text) > max_chars:
                    remaining = len(review['review_comments']) - review['review_comments'].index(comment)
                    summary += f"\n  ... and {remaining} more comments\n"
                    break

                summary += comment_text
                total_chars += len(comment_text)

        return summary
