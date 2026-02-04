"""Commit filtering module for individual performance reports.

Filters commits to include only those on main/master/release branches
and excludes revert commits.
"""

import logging
from typing import Dict, List, Set

logger = logging.getLogger('github_metrics')


class CommitFilter:
    """Filter commits by branch and revert status."""

    def __init__(self, github_client):
        """
        Initialize commit filter.

        Args:
            github_client: GitHubClient instance for API calls
        """
        self.github_client = github_client
        self.target_branches = {'main', 'master'}  # Base target branches

    def get_commit_pull_requests(self, repo_name: str, commit_sha: str) -> List[Dict]:
        """
        Get pull requests associated with a commit using GraphQL.

        Args:
            repo_name: Repository name (e.g., 'owner/repo')
            commit_sha: Commit SHA

        Returns:
            List of PR dictionaries with baseRefName field
        """
        try:
            owner, repo = repo_name.split('/')

            query = """
            query($owner: String!, $repo: String!, $sha: GitObjectID!) {
                repository(owner: $owner, name: $repo) {
                    object(oid: $sha) {
                        ... on Commit {
                            associatedPullRequests(first: 10) {
                                nodes {
                                    number
                                    baseRefName
                                    headRefName
                                    merged
                                }
                            }
                        }
                    }
                }
            }
            """

            variables = {
                'owner': owner,
                'repo': repo,
                'sha': commit_sha
            }

            response = self.github_client.execute_query(query, variables)

            if response and 'data' in response:
                obj = response['data']['repository']['object']
                if obj and 'associatedPullRequests' in obj:
                    return obj['associatedPullRequests']['nodes']

            return []

        except Exception as e:
            logger.debug(f"Failed to get PRs for commit {commit_sha[:7]}: {e}")
            return []

    def get_commit_branches(self, repo_name: str, commit_sha: str) -> List[Dict]:
        """
        Get branches containing a commit using REST API.

        Args:
            repo_name: Repository name (e.g., 'owner/repo')
            commit_sha: Commit SHA

        Returns:
            List of branch dictionaries with 'name' field
        """
        try:
            # Use REST API: GET /repos/{owner}/{repo}/commits/{sha}/branches-where-head
            url = f"{self.github_client.base_url}/repos/{repo_name}/commits/{commit_sha}/branches-where-head"

            response = self.github_client.session.get(
                url,
                headers=self.github_client.headers,
                timeout=self.github_client.timeout
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.debug(f"Failed to get branches for commit {commit_sha[:7]}: {response.status_code}")
                return []

        except Exception as e:
            logger.debug(f"Failed to get branches for commit {commit_sha[:7]}: {e}")
            return []

    def is_main_branch_commit(self, commit: Dict, repo_name: str) -> bool:
        """
        Check if commit is on main, master, or release branch.

        Strategy: Check commit's associated pull requests first (more reliable).
        If PR's base branch is main/master/release, the commit is included.
        If commit has no PR (direct push), check branches containing commit.

        Args:
            commit: Commit dictionary with 'sha' and 'message' fields
            repo_name: Repository name (e.g., 'owner/repo')

        Returns:
            True if commit is on a target branch, False otherwise
        """
        commit_sha = commit.get('sha') or commit.get('oid')

        # Method 1: Check associated PRs (preferred for merged commits)
        prs = self.get_commit_pull_requests(repo_name, commit_sha)

        if prs:
            # Check if any PR targeted main/master/release
            for pr in prs:
                if not pr.get('merged'):
                    continue  # Only consider merged PRs

                base_branch = pr['baseRefName'].lower()

                # Check target branches
                if base_branch in self.target_branches:
                    logger.debug(f"Commit {commit_sha[:7]} merged to {base_branch} via PR #{pr['number']}")
                    return True

                # Check release branches
                if base_branch.startswith('release'):
                    logger.debug(f"Commit {commit_sha[:7]} merged to {base_branch} via PR #{pr['number']}")
                    return True

            # Has PRs but none targeted main/master/release
            return False

        # Method 2: Direct commit - check branches containing commit
        branches = self.get_commit_branches(repo_name, commit_sha)

        for branch in branches:
            branch_name = branch['name'].lower()

            if branch_name in self.target_branches:
                logger.debug(f"Commit {commit_sha[:7]} is on branch {branch_name}")
                return True

            if branch_name.startswith('release'):
                logger.debug(f"Commit {commit_sha[:7]} is on branch {branch_name}")
                return True

        return False

    def is_revert_commit(self, commit: Dict) -> bool:
        """
        Check if commit is a revert by analyzing message.

        Args:
            commit: Commit dictionary with 'message' field

        Returns:
            True if commit is a revert, False otherwise
        """
        message = commit.get('message', '').lower()

        # Common revert patterns
        revert_patterns = [
            'revert "',
            'revert:',
            'revert ',
            'reverts commit',
            'reverted',
            'revert of',
            'revert pr'
        ]

        # Check first 50 chars of message
        message_start = message[:50]

        for pattern in revert_patterns:
            if pattern in message_start:
                return True

        return False

    def filter_commits(
        self,
        commits: List[Dict],
        repo_name: str
    ) -> List[Dict]:
        """
        Filter to only main branch, non-revert commits.

        Args:
            commits: List of commit dictionaries
            repo_name: Repository name (e.g., 'owner/repo')

        Returns:
            Filtered list of commits
        """
        filtered = []
        stats = {
            'total': len(commits),
            'reverts': 0,
            'feature_branch': 0,
            'included': 0
        }

        for commit in commits:
            commit_sha = commit.get('sha') or commit.get('oid')

            # Check for revert
            if self.is_revert_commit(commit):
                stats['reverts'] += 1
                logger.debug(
                    f"Excluding revert: {commit_sha[:7]} - "
                    f"{commit.get('message', '')[:50]}"
                )
                continue

            # Check branch (this is expensive, so do it last)
            if not self.is_main_branch_commit(commit, repo_name):
                stats['feature_branch'] += 1
                logger.debug(f"Excluding feature branch: {commit_sha[:7]}")
                continue

            filtered.append(commit)
            stats['included'] += 1

        logger.info(
            f"Commit filtering for {repo_name}: {stats['included']}/{stats['total']} included "
            f"(excluded {stats['reverts']} reverts, {stats['feature_branch']} feature branch)"
        )

        return filtered

    def filter_commits_batch(
        self,
        commits_by_repo: Dict[str, List[Dict]]
    ) -> Dict[str, List[Dict]]:
        """
        Filter commits for multiple repositories.

        Args:
            commits_by_repo: Dictionary mapping repo names to commit lists

        Returns:
            Dictionary mapping repo names to filtered commit lists
        """
        filtered_by_repo = {}

        for repo_name, commits in commits_by_repo.items():
            if not commits:
                filtered_by_repo[repo_name] = []
                continue

            logger.info(f"Filtering {len(commits)} commits for {repo_name}...")
            filtered_by_repo[repo_name] = self.filter_commits(commits, repo_name)

        # Summary
        total_before = sum(len(commits) for commits in commits_by_repo.values())
        total_after = sum(len(commits) for commits in filtered_by_repo.values())

        logger.info(
            f"Overall filtering: {total_after}/{total_before} commits included "
            f"({total_before - total_after} excluded)"
        )

        return filtered_by_repo
