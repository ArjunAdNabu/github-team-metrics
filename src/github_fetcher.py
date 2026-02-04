"""GitHub API client for fetching team performance metrics using GraphQL."""

import requests
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from collections import defaultdict

from .utils import retry_with_exponential_backoff, calculate_hours_between


logger = logging.getLogger('github_metrics')


class GitHubClient:
    """GitHub API client using GraphQL for efficient data fetching."""

    def __init__(self, token: str, org_name: str, timeout: int = 30):
        """
        Initialize GitHub client.

        Args:
            token: GitHub personal access token
            org_name: Organization name
            timeout: Request timeout in seconds
        """
        self.token = token
        self.org_name = org_name
        self.timeout = timeout
        self.api_url = 'https://api.github.com/graphql'

        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/vnd.github.v4+json'
        })

    @retry_with_exponential_backoff(
        max_retries=3,
        base_delay=2.0,
        exceptions=(requests.RequestException,)
    )
    def execute_query(self, query: str, variables: Dict[str, Any] = None) -> Dict:
        """
        Execute GraphQL query.

        Args:
            query: GraphQL query string
            variables: Query variables

        Returns:
            Query response data

        Raises:
            requests.HTTPError: If request fails
        """
        response = self.session.post(
            self.api_url,
            json={'query': query, 'variables': variables or {}},
            timeout=self.timeout
        )
        response.raise_for_status()

        data = response.json()

        if 'errors' in data:
            raise Exception(f"GraphQL errors: {data['errors']}")

        return data.get('data', {})

    def check_rate_limit(self) -> Dict[str, int]:
        """
        Check GitHub API rate limit.

        Returns:
            Dict with 'limit', 'remaining', 'reset' fields
        """
        query = """
        query {
            rateLimit {
                limit
                remaining
                resetAt
            }
        }
        """

        try:
            data = self.execute_query(query)
            rate_limit = data.get('rateLimit', {})

            return {
                'limit': rate_limit.get('limit', 0),
                'remaining': rate_limit.get('remaining', 0),
                'reset': rate_limit.get('resetAt', '')
            }
        except Exception as e:
            logger.warning(f"Failed to check rate limit: {e}")
            return {'limit': 5000, 'remaining': 5000, 'reset': ''}

    def get_all_repositories(self) -> List[Dict]:
        """
        Fetch all repositories in the organization.

        Returns:
            List of repository data dictionaries
        """
        query = """
        query($org: String!, $cursor: String) {
            organization(login: $org) {
                repositories(first: 100, after: $cursor) {
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                    nodes {
                        name
                        nameWithOwner
                        isPrivate
                        isArchived
                        defaultBranchRef {
                            name
                        }
                    }
                }
            }
        }
        """

        repos = []
        cursor = None
        has_next_page = True

        logger.info(f"Fetching repositories for organization: {self.org_name}")

        while has_next_page:
            try:
                data = self.execute_query(query, {'org': self.org_name, 'cursor': cursor})

                org_data = data.get('organization')
                if not org_data:
                    logger.error(f"Organization '{self.org_name}' not found")
                    break

                repo_data = org_data.get('repositories', {})
                nodes = repo_data.get('nodes', [])

                # Filter out archived repos
                active_repos = [r for r in nodes if not r.get('isArchived')]
                repos.extend(active_repos)

                page_info = repo_data.get('pageInfo', {})
                has_next_page = page_info.get('hasNextPage', False)
                cursor = page_info.get('endCursor')

                logger.info(f"Fetched {len(repos)} repositories so far...")

            except Exception as e:
                logger.error(f"Failed to fetch repositories: {e}")
                break

        logger.info(f"Total repositories found: {len(repos)}")
        return repos

    def get_commits(
        self,
        repo_name: str,
        since: str,
        until: str,
        branch: str = None
    ) -> List[Dict]:
        """
        Fetch commits for a repository.

        Args:
            repo_name: Repository name (owner/repo format)
            since: Start date (ISO format)
            until: End date (ISO format)
            branch: Branch name (default: default branch)

        Returns:
            List of commit data dictionaries
        """
        query = """
        query($owner: String!, $repo: String!, $branch: String!, $since: GitTimestamp!, $until: GitTimestamp!, $cursor: String) {
            repository(owner: $owner, name: $repo) {
                ref(qualifiedName: $branch) {
                    target {
                        ... on Commit {
                            history(first: 100, since: $since, until: $until, after: $cursor) {
                                pageInfo {
                                    hasNextPage
                                    endCursor
                                }
                                nodes {
                                    oid
                                    committedDate
                                    author {
                                        user {
                                            login
                                            name
                                            email
                                        }
                                        name
                                        email
                                    }
                                    additions
                                    deletions
                                    message
                                }
                            }
                        }
                    }
                }
            }
        }
        """

        parts = repo_name.split('/')
        if len(parts) != 2:
            logger.warning(f"Invalid repo name format: {repo_name}")
            return []

        owner, repo = parts
        commits = []
        cursor = None
        has_next_page = True

        # Use provided branch or default to main/master
        branch_ref = branch or 'refs/heads/main'

        while has_next_page:
            try:
                data = self.execute_query(query, {
                    'owner': owner,
                    'repo': repo,
                    'branch': branch_ref,
                    'since': since,
                    'until': until,
                    'cursor': cursor
                })

                repo_data = data.get('repository')
                if not repo_data or not repo_data.get('ref'):
                    # Try master branch if main doesn't exist
                    if branch_ref == 'refs/heads/main':
                        logger.debug(f"{repo_name}: Trying master branch")
                        branch_ref = 'refs/heads/master'
                        continue
                    else:
                        logger.debug(f"{repo_name}: No commits found on branch {branch_ref}")
                        break

                history = repo_data['ref']['target'].get('history', {})
                nodes = history.get('nodes', [])
                commits.extend(nodes)

                page_info = history.get('pageInfo', {})
                has_next_page = page_info.get('hasNextPage', False)
                cursor = page_info.get('endCursor')

            except Exception as e:
                logger.warning(f"Failed to fetch commits for {repo_name}: {e}")
                break

        return commits

    def get_pull_requests(
        self,
        repo_name: str,
        since: str,
        until: str
    ) -> List[Dict]:
        """
        Fetch pull requests for a repository.

        Args:
            repo_name: Repository name (owner/repo format)
            since: Start date (ISO format)
            until: End date (ISO format)

        Returns:
            List of PR data dictionaries
        """
        query = """
        query($owner: String!, $repo: String!, $cursor: String) {
            repository(owner: $owner, name: $repo) {
                pullRequests(first: 100, after: $cursor, orderBy: {field: CREATED_AT, direction: DESC}) {
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                    nodes {
                        number
                        title
                        createdAt
                        mergedAt
                        closedAt
                        state
                        author {
                            login
                        }
                        additions
                        deletions
                        reviews(first: 10) {
                            nodes {
                                createdAt
                                author {
                                    login
                                }
                            }
                        }
                    }
                }
            }
        }
        """

        parts = repo_name.split('/')
        if len(parts) != 2:
            logger.warning(f"Invalid repo name format: {repo_name}")
            return []

        owner, repo = parts
        prs = []
        cursor = None
        has_next_page = True

        # Convert dates for comparison (handle timezone)
        from datetime import timezone

        since_dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
        if since_dt.tzinfo is None:
            since_dt = since_dt.replace(tzinfo=timezone.utc)

        until_dt = datetime.fromisoformat(until.replace('Z', '+00:00'))
        if until_dt.tzinfo is None:
            until_dt = until_dt.replace(tzinfo=timezone.utc)

        while has_next_page:
            try:
                data = self.execute_query(query, {
                    'owner': owner,
                    'repo': repo,
                    'cursor': cursor
                })

                repo_data = data.get('repository')
                if not repo_data:
                    logger.debug(f"{repo_name}: Repository not accessible")
                    break

                pr_data = repo_data.get('pullRequests', {})
                nodes = pr_data.get('nodes', [])

                # Filter PRs by date range
                for pr in nodes:
                    created_at = datetime.fromisoformat(pr['createdAt'].replace('Z', '+00:00'))
                    if since_dt <= created_at <= until_dt:
                        prs.append(pr)
                    elif created_at < since_dt:
                        # PRs are ordered by creation date desc, so we can stop
                        has_next_page = False
                        break

                if has_next_page:
                    page_info = pr_data.get('pageInfo', {})
                    has_next_page = page_info.get('hasNextPage', False)
                    cursor = page_info.get('endCursor')

            except Exception as e:
                logger.warning(f"Failed to fetch PRs for {repo_name}: {e}")
                break

        return prs

    def get_issues(
        self,
        repo_name: str,
        since: str,
        until: str
    ) -> List[Dict]:
        """
        Fetch closed issues for a repository.

        Args:
            repo_name: Repository name (owner/repo format)
            since: Start date (ISO format)
            until: End date (ISO format)

        Returns:
            List of issue data dictionaries
        """
        query = """
        query($owner: String!, $repo: String!, $cursor: String) {
            repository(owner: $owner, name: $repo) {
                issues(first: 100, after: $cursor, states: CLOSED, orderBy: {field: CREATED_AT, direction: DESC}) {
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                    nodes {
                        number
                        title
                        createdAt
                        closedAt
                        state
                        author {
                            login
                        }
                        closedBy: timelineItems(first: 1, itemTypes: CLOSED_EVENT) {
                            nodes {
                                ... on ClosedEvent {
                                    actor {
                                        login
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """

        parts = repo_name.split('/')
        if len(parts) != 2:
            logger.warning(f"Invalid repo name format: {repo_name}")
            return []

        owner, repo = parts
        issues = []
        cursor = None
        has_next_page = True

        # Convert dates for comparison (handle timezone)
        from datetime import timezone

        since_dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
        if since_dt.tzinfo is None:
            since_dt = since_dt.replace(tzinfo=timezone.utc)

        until_dt = datetime.fromisoformat(until.replace('Z', '+00:00'))
        if until_dt.tzinfo is None:
            until_dt = until_dt.replace(tzinfo=timezone.utc)

        while has_next_page:
            try:
                data = self.execute_query(query, {
                    'owner': owner,
                    'repo': repo,
                    'cursor': cursor
                })

                repo_data = data.get('repository')
                if not repo_data:
                    logger.debug(f"{repo_name}: Repository not accessible")
                    break

                issue_data = repo_data.get('issues', {})
                nodes = issue_data.get('nodes', [])

                # Filter issues by closed date
                for issue in nodes:
                    if not issue.get('closedAt'):
                        continue

                    closed_at = datetime.fromisoformat(issue['closedAt'].replace('Z', '+00:00'))
                    if since_dt <= closed_at <= until_dt:
                        issues.append(issue)
                    elif closed_at < since_dt:
                        # Issues are ordered by creation date desc, so we can stop
                        has_next_page = False
                        break

                if has_next_page:
                    page_info = issue_data.get('pageInfo', {})
                    has_next_page = page_info.get('hasNextPage', False)
                    cursor = page_info.get('endCursor')

            except Exception as e:
                logger.warning(f"Failed to fetch issues for {repo_name}: {e}")
                break

        return issues


class GitHubMetricsCollector:
    """High-level metrics collection and aggregation."""

    def __init__(self, client: GitHubClient, start_date: str, end_date: str):
        """
        Initialize metrics collector.

        Args:
            client: GitHub client instance
            start_date: Start date in ISO format
            end_date: End date in ISO format
        """
        self.client = client
        self.start_date = start_date
        self.end_date = end_date

    def collect_all_metrics(self) -> Dict:
        """
        Collect metrics from all repositories.

        Returns:
            Dictionary with repos, commits, pull_requests, issues
        """
        # Fetch all repositories
        repos = self.client.get_all_repositories()

        all_commits = []
        all_prs = []
        all_issues = []

        # Fetch commits, PRs, and issues for each repo
        for i, repo in enumerate(repos, 1):
            repo_name = repo.get('nameWithOwner', '')
            logger.info(f"[{i}/{len(repos)}] Fetching data from {repo_name}")

            try:
                # Get commits
                commits = self.client.get_commits(
                    repo_name,
                    self.start_date,
                    self.end_date,
                    branch=repo.get('defaultBranchRef', {}).get('name')
                )

                # Add repo info to each commit
                for commit in commits:
                    commit['repo'] = repo_name

                all_commits.extend(commits)
                logger.debug(f"  Found {len(commits)} commits")

                # Get PRs
                prs = self.client.get_pull_requests(
                    repo_name,
                    self.start_date,
                    self.end_date
                )

                # Add repo info to each PR
                for pr in prs:
                    pr['repo'] = repo_name

                all_prs.extend(prs)
                logger.debug(f"  Found {len(prs)} PRs")

                # Get closed issues
                issues = self.client.get_issues(
                    repo_name,
                    self.start_date,
                    self.end_date
                )

                # Add repo info to each issue
                for issue in issues:
                    issue['repo'] = repo_name

                all_issues.extend(issues)
                logger.debug(f"  Found {len(issues)} closed issues")

            except Exception as e:
                logger.warning(f"Failed to fetch data from {repo_name}: {e}")
                continue

        logger.info(f"Total commits collected: {len(all_commits)}")
        logger.info(f"Total PRs collected: {len(all_prs)}")
        logger.info(f"Total issues closed: {len(all_issues)}")

        return {
            'repos': repos,
            'commits': all_commits,
            'pull_requests': all_prs,
            'issues': all_issues
        }

    def aggregate_by_team_member(self, raw_data: Dict) -> Dict:
        """
        Aggregate metrics by team member.

        Args:
            raw_data: Raw data from collect_all_metrics()

        Returns:
            Dictionary mapping username to aggregated metrics
        """
        commits = raw_data.get('commits', [])
        prs = raw_data.get('pull_requests', [])
        issues = raw_data.get('issues', [])

        # Initialize metrics storage
        user_metrics = defaultdict(lambda: {
            'display_name': '',
            'email': '',
            'total_commits': 0,
            'commit_dates': [],
            'commit_additions': 0,
            'commit_deletions': 0,
            'prs_created': 0,
            'prs_merged': 0,
            'pr_additions': 0,
            'pr_deletions': 0,
            'issues_closed': 0,
            'reviews_given': [],
            'reviews_received': [],
            'review_times': [],
            'active_repos': set()
        })

        # Process commits
        for commit in commits:
            author = commit.get('author', {})
            user = author.get('user')

            if user and user.get('login'):
                username = user['login']
                user_metrics[username]['display_name'] = user.get('name', username)
                user_metrics[username]['email'] = user.get('email', '')
                user_metrics[username]['total_commits'] += 1
                user_metrics[username]['commit_dates'].append(commit['committedDate'])
                user_metrics[username]['commit_additions'] += commit.get('additions', 0)
                user_metrics[username]['commit_deletions'] += commit.get('deletions', 0)
                user_metrics[username]['active_repos'].add(commit['repo'])

        # Process PRs
        for pr in prs:
            author = pr.get('author', {})
            if not author:
                continue

            username = author.get('login')
            if not username:
                continue

            # PR created
            user_metrics[username]['prs_created'] += 1
            user_metrics[username]['active_repos'].add(pr['repo'])

            # PR merged
            if pr.get('mergedAt'):
                user_metrics[username]['prs_merged'] += 1

            # PR size
            user_metrics[username]['pr_additions'] += pr.get('additions', 0)
            user_metrics[username]['pr_deletions'] += pr.get('deletions', 0)

            # Process reviews
            reviews = pr.get('reviews', {}).get('nodes', [])
            for review in reviews:
                reviewer = review.get('author', {})
                if not reviewer:
                    continue

                reviewer_login = reviewer.get('login')
                if not reviewer_login:
                    continue

                # Review given
                user_metrics[reviewer_login]['reviews_given'].append({
                    'pr': pr['number'],
                    'repo': pr['repo'],
                    'reviewed_at': review['createdAt']
                })

                # Review received (by PR author)
                user_metrics[username]['reviews_received'].append({
                    'pr': pr['number'],
                    'repo': pr['repo'],
                    'reviewer': reviewer_login,
                    'reviewed_at': review['createdAt']
                })

                # Calculate review time (how long it took the reviewer to review)
                review_time = calculate_hours_between(pr['createdAt'], review['createdAt'])
                user_metrics[reviewer_login]['review_times'].append(review_time)

        # Process issues
        for issue in issues:
            # Get the user who closed the issue
            closed_by_nodes = issue.get('closedBy', {}).get('nodes', [])
            if closed_by_nodes:
                closer = closed_by_nodes[0].get('actor', {})
                if closer and closer.get('login'):
                    username = closer['login']
                    user_metrics[username]['issues_closed'] += 1
                    user_metrics[username]['active_repos'].add(issue['repo'])

        # Calculate derived metrics
        result = {}
        num_days = (datetime.fromisoformat(self.end_date) -
                   datetime.fromisoformat(self.start_date)).days or 1

        for username, metrics in user_metrics.items():
            total_commits = metrics['total_commits']
            prs_created = metrics['prs_created']
            prs_merged = metrics['prs_merged']
            reviews_given = len(metrics['reviews_given'])
            reviews_received = len(metrics['reviews_received'])

            # Calculate total lines changed (commits + PRs)
            total_additions = metrics['commit_additions'] + metrics['pr_additions']
            total_deletions = metrics['commit_deletions'] + metrics['pr_deletions']

            result[username] = {
                'display_name': metrics['display_name'] or username,
                'email': metrics['email'],
                'total_commits': total_commits,
                'commit_frequency': round(total_commits / num_days, 2),
                'lines_added': total_additions,
                'lines_deleted': total_deletions,
                'lines_changed': total_additions + total_deletions,
                'prs_created': prs_created,
                'prs_merged': prs_merged,
                'pr_merge_rate': round((prs_merged / prs_created * 100), 1) if prs_created > 0 else 0,
                'avg_pr_size': round((metrics['pr_additions'] + metrics['pr_deletions']) / prs_created) if prs_created > 0 else 0,
                'issues_closed': metrics['issues_closed'],
                'reviews_given': reviews_given,
                'reviews_received': reviews_received,
                'review_participation': round(reviews_given / reviews_received, 2) if reviews_received > 0 else 0,
                'avg_review_time_hours': round(sum(metrics['review_times']) / len(metrics['review_times']), 1) if metrics['review_times'] else 0,
                'active_repos': list(metrics['active_repos']),
                'last_active': max(metrics['commit_dates']) if metrics['commit_dates'] else None
            }

        return result
