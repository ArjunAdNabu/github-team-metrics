"""Code diff fetcher for individual performance reports.

Fetches commit diffs via GitHub REST API with smart sampling strategy.
"""

import logging
from typing import Dict, List
from datetime import datetime

logger = logging.getLogger('github_metrics')


class CodeDiffFetcher:
    """Fetch code diffs for commits."""

    def __init__(self, github_client, sample_size: int = 10):
        """
        Initialize code diff fetcher.

        Args:
            github_client: GitHubClient instance for API calls
            sample_size: Number of commits to sample per engineer
        """
        self.github_client = github_client
        self.sample_size = sample_size

    def get_commit_diff(self, repo_name: str, commit_sha: str) -> Dict:
        """
        Get diff for a specific commit using REST API.

        Args:
            repo_name: Repository name (e.g., 'owner/repo')
            commit_sha: Commit SHA

        Returns:
            Dictionary with diff information:
            {
                'sha': str,
                'message': str,
                'additions': int,
                'deletions': int,
                'files': List[{
                    'filename': str,
                    'status': str,  # 'added', 'modified', 'deleted'
                    'additions': int,
                    'deletions': int,
                    'patch': str  # The actual diff patch
                }]
            }
        """
        try:
            # Use REST API: GET /repos/{owner}/{repo}/commits/{sha}
            url = f"{self.github_client.base_url}/repos/{repo_name}/commits/{commit_sha}"

            response = self.github_client.session.get(
                url,
                headers=self.github_client.headers,
                timeout=self.github_client.timeout
            )

            if response.status_code != 200:
                logger.warning(
                    f"Failed to fetch diff for commit {commit_sha[:7]}: "
                    f"HTTP {response.status_code}"
                )
                return None

            data = response.json()

            # Extract relevant information
            commit_data = {
                'sha': data['sha'],
                'message': data['commit']['message'],
                'additions': data['stats']['additions'],
                'deletions': data['stats']['deletions'],
                'total_changes': data['stats']['total'],
                'files': []
            }

            # Extract file diffs
            for file in data.get('files', []):
                file_data = {
                    'filename': file['filename'],
                    'status': file['status'],
                    'additions': file['additions'],
                    'deletions': file['deletions'],
                    'changes': file['changes'],
                    'patch': file.get('patch', '')  # Patch may not exist for binary files
                }
                commit_data['files'].append(file_data)

            logger.debug(
                f"Fetched diff for {commit_sha[:7]}: "
                f"{commit_data['additions']}+/{commit_data['deletions']}- "
                f"across {len(commit_data['files'])} files"
            )

            return commit_data

        except Exception as e:
            logger.error(f"Error fetching diff for commit {commit_sha[:7]}: {e}")
            return None

    def sample_user_commits(
        self,
        commits: List[Dict],
        user_login: str
    ) -> List[Dict]:
        """
        Smart sampling of commits for a user.

        Strategy:
        1. Filter out merge commits (message starts with "Merge")
        2. Filter out file deletions (only deletions, no additions)
        3. Prioritize recent commits (last 30% of time period)
        4. Prefer moderate-size commits (not too small, not too large)
        5. Sample up to sample_size commits

        Args:
            commits: List of commit dictionaries
            user_login: GitHub username

        Returns:
            List of sampled commit dictionaries
        """
        if not commits:
            return []

        # Filter commits for this user
        user_commits = [
            c for c in commits
            if c.get('author_login') == user_login or c.get('committer_login') == user_login
        ]

        if not user_commits:
            return []

        logger.info(f"Sampling commits for {user_login}: {len(user_commits)} total")

        # Filter out merge commits
        non_merge = [
            c for c in user_commits
            if not c.get('message', '').startswith('Merge')
        ]

        logger.debug(f"  After filtering merge commits: {len(non_merge)}")

        if not non_merge:
            non_merge = user_commits  # Fallback to all commits if all are merges

        # Sort by date (most recent first)
        sorted_commits = sorted(
            non_merge,
            key=lambda c: c.get('committed_date') or c.get('authored_date') or '',
            reverse=True
        )

        # Prefer recent commits (last 30% of period)
        recent_count = max(1, int(len(sorted_commits) * 0.3))
        recent_commits = sorted_commits[:recent_count]

        # If we don't have enough recent commits, take from all
        if len(recent_commits) < self.sample_size:
            candidates = sorted_commits
        else:
            candidates = recent_commits

        # Prefer moderate-size commits (10-500 lines changed)
        # This filters out trivial commits and massive refactors
        moderate_commits = [
            c for c in candidates
            if 10 <= (c.get('additions', 0) + c.get('deletions', 0)) <= 500
        ]

        if len(moderate_commits) >= self.sample_size:
            sampled = moderate_commits[:self.sample_size]
        elif moderate_commits:
            # Take moderate commits + some from candidates to reach sample_size
            sampled = moderate_commits + [
                c for c in candidates
                if c not in moderate_commits
            ][:self.sample_size - len(moderate_commits)]
        else:
            # No moderate commits, just take the most recent
            sampled = candidates[:self.sample_size]

        logger.info(
            f"Sampled {len(sampled)} commits for {user_login} "
            f"(from {len(user_commits)} total)"
        )

        return sampled

    def fetch_diffs_for_user(
        self,
        commits: List[Dict],
        user_login: str,
        repo_name: str
    ) -> List[Dict]:
        """
        Fetch diffs for sampled commits of a user.

        Args:
            commits: List of all commit dictionaries
            user_login: GitHub username
            repo_name: Repository name (e.g., 'owner/repo')

        Returns:
            List of commit diff dictionaries
        """
        # Sample commits
        sampled = self.sample_user_commits(commits, user_login)

        if not sampled:
            logger.warning(f"No commits to sample for {user_login}")
            return []

        # Fetch diffs for sampled commits
        diffs = []

        for commit in sampled:
            commit_sha = commit.get('sha') or commit.get('oid')

            diff = self.get_commit_diff(repo_name, commit_sha)

            if diff:
                # Add metadata from original commit
                diff['authored_date'] = commit.get('authored_date')
                diff['committed_date'] = commit.get('committed_date')
                diff['author_login'] = commit.get('author_login')
                diff['repo'] = repo_name

                diffs.append(diff)

        logger.info(
            f"Fetched {len(diffs)} diffs for {user_login} in {repo_name}"
        )

        return diffs

    def fetch_diffs_for_all_users(
        self,
        commits_by_repo: Dict[str, List[Dict]],
        user_logins: List[str]
    ) -> Dict[str, List[Dict]]:
        """
        Fetch diffs for multiple users across multiple repositories.

        Args:
            commits_by_repo: Dictionary mapping repo names to commit lists
            user_logins: List of GitHub usernames

        Returns:
            Dictionary mapping usernames to lists of diff dictionaries:
            {
                'user1': [diff1, diff2, ...],
                'user2': [diff1, diff2, ...],
                ...
            }
        """
        diffs_by_user = {user: [] for user in user_logins}

        for repo_name, commits in commits_by_repo.items():
            if not commits:
                continue

            logger.info(f"Fetching diffs for {repo_name}...")

            for user_login in user_logins:
                diffs = self.fetch_diffs_for_user(commits, user_login, repo_name)
                diffs_by_user[user_login].extend(diffs)

        # Summary
        for user_login, diffs in diffs_by_user.items():
            logger.info(f"Total diffs for {user_login}: {len(diffs)}")

        return diffs_by_user

    def summarize_diff(self, diff: Dict, max_lines: int = 100) -> str:
        """
        Create a summary of a diff for AI analysis.

        Truncates large diffs to focus on the most important changes.

        Args:
            diff: Diff dictionary from get_commit_diff()
            max_lines: Maximum number of diff lines to include

        Returns:
            Summarized diff string
        """
        summary = f"Commit: {diff['message']}\n"
        summary += f"Changes: +{diff['additions']}/-{diff['deletions']}\n"
        summary += f"Files modified: {len(diff['files'])}\n\n"

        # Add file changes
        total_lines = 0

        for file in diff['files']:
            if total_lines >= max_lines:
                summary += f"\n... and {len(diff['files']) - diff['files'].index(file)} more files\n"
                break

            summary += f"File: {file['filename']} ({file['status']})\n"
            summary += f"  +{file['additions']}/-{file['deletions']}\n"

            # Add patch if available and not too large
            if file['patch']:
                patch_lines = file['patch'].split('\n')
                lines_to_add = min(len(patch_lines), max_lines - total_lines)

                summary += '\n'.join(patch_lines[:lines_to_add]) + '\n'
                total_lines += lines_to_add

                if lines_to_add < len(patch_lines):
                    summary += f"  ... ({len(patch_lines) - lines_to_add} more lines)\n"

            summary += '\n'

        return summary
