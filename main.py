"""Main script for GitHub Team Performance Metrics."""

import argparse
import sys
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

from config import load_config, validate_config, load_user_mapping
from src.utils import (
    setup_logging,
    calculate_date_range,
    generate_output_filename,
    format_duration
)
from src.github_fetcher import GitHubClient, GitHubMetricsCollector
from src.sheets_reader import GoogleSheetsClient, SheetsDataProcessor, TicketMetricsCalculator
from src.data_processor import DataCombiner, MetricsCalculator
from src.excel_exporter import ExcelExporter

# Individual reports modules
from src.commit_filter import CommitFilter
from src.code_diff_fetcher import CodeDiffFetcher
from src.review_comment_fetcher import ReviewCommentFetcher
from src.code_analyzer import get_analyzer, get_fallback_analysis
from src.performance_ranker import PerformanceRanker
from src.pdf_report_generator import generate_all_reports_concurrently


def generate_individual_reports(
    enhanced_data,
    github_data,
    github_client,
    config,
    start_date,
    end_date
):
    """
    Generate individual performance reports for each engineer.

    Args:
        enhanced_data: List of engineer dictionaries with combined metrics
        github_data: Raw GitHub data (commits, PRs, etc.)
        github_client: GitHubClient instance
        config: Configuration object
        start_date: Report start date
        end_date: Report end date
    """
    logger = setup_logging(config.log_level if hasattr(config, 'log_level') else 'INFO')

    logger.info("=" * 70)
    logger.info("Generating Individual Performance Reports")
    logger.info("=" * 70)

    # Step 1: Filter commits to main/master/release branches only
    logger.info("Step 1: Filtering commits to production branches...")
    commit_filter = CommitFilter(github_client)

    # Group commits by repo
    commits_by_repo = {}
    for commit in github_data['commits']:
        repo = commit.get('repo')
        if repo not in commits_by_repo:
            commits_by_repo[repo] = []
        commits_by_repo[repo].append(commit)

    # Filter commits
    filtered_commits_by_repo = commit_filter.filter_commits_batch(commits_by_repo)

    # Step 2: Fetch code diffs and review comments for each engineer
    logger.info("Step 2: Fetching code diffs and review comments...")

    # Filter out bot accounts
    def is_bot_account(username: str) -> bool:
        """Check if username is a bot account."""
        username_lower = username.lower()

        # Known bot accounts (exact match)
        bot_accounts = [
            'claude',
            'dependabot',
            'github-code-quality',
            'renovate',
            'snyk',
            'greenkeeper',
            'codecov',
            'sonarcloud'
        ]

        # Check exact match first
        if username_lower in bot_accounts:
            return True

        # Known bot patterns (substring match)
        bot_patterns = [
            '[bot]',
            '-bot',
            'bot-',
            'bot_'
        ]

        # Check if username matches bot patterns
        for pattern in bot_patterns:
            if pattern in username_lower:
                return True

        # Check if username ends with 'bot' or 'agent' (but not part of a real name)
        if username_lower.endswith('bot') or username_lower.endswith('agent'):
            return True

        return False

    # Get human users only
    all_user_logins = [eng['github_username'] for eng in enhanced_data]
    bot_users = [user for user in all_user_logins if is_bot_account(user)]

    if bot_users:
        logger.info(f"Excluding {len(bot_users)} bot accounts: {', '.join(bot_users)}")

    # Filter enhanced_data to only include human users
    enhanced_data = [eng for eng in enhanced_data if not is_bot_account(eng['github_username'])]
    user_logins = [eng['github_username'] for eng in enhanced_data]

    logger.info(f"Generating reports for {len(user_logins)} human users")

    diff_fetcher = CodeDiffFetcher(github_client, config.sample_size_commits)
    diffs_by_user = diff_fetcher.fetch_diffs_for_all_users(
        filtered_commits_by_repo,
        user_logins
    )

    # Group PRs by repo
    prs_by_repo = {}
    for pr in github_data['pull_requests']:
        repo = pr.get('repo')
        if repo not in prs_by_repo:
            prs_by_repo[repo] = []
        prs_by_repo[repo].append(pr)

    review_fetcher = ReviewCommentFetcher(github_client, config.sample_size_reviews)
    reviews_by_user = review_fetcher.fetch_reviews_for_all_users(
        prs_by_repo,
        user_logins,
        max_workers=config.max_workers_data_fetching
    )

    # Step 3: AI Analysis (concurrent)
    logger.info("Step 3: Running AI analysis...")

    if config.enable_ai_analysis and config.ai_provider != 'none':
        try:
            analyzer = get_analyzer(config.ai_provider, config)

            # Concurrent AI analysis
            def analyze_single_engineer(eng):
                """Run AI analysis for one engineer."""
                username = eng['github_username']

                try:
                    diffs = diffs_by_user.get(username, [])
                    reviews = reviews_by_user.get(username, [])

                    # Analyze code quality
                    code_analysis = analyzer.analyze_code_quality(
                        diffs,
                        context={'username': username}
                    )

                    # Analyze review quality
                    review_analysis = analyzer.analyze_review_quality(
                        reviews,
                        context={'username': username}
                    )

                    # Generate insights
                    insights = analyzer.generate_performance_insights(
                        code_analysis,
                        review_analysis,
                        eng
                    )

                    return {
                        'code_quality': code_analysis,
                        'review_quality': review_analysis,
                        'insights': insights
                    }

                except Exception as e:
                    logger.error(f"AI analysis failed for {username}: {e}")
                    return get_fallback_analysis()

            # Run concurrently
            with ThreadPoolExecutor(max_workers=config.max_workers_ai_analysis) as executor:
                futures = {
                    executor.submit(analyze_single_engineer, eng): eng
                    for eng in enhanced_data
                }

                with tqdm(total=len(enhanced_data), desc="AI Analysis") as pbar:
                    for future in as_completed(futures):
                        engineer = futures[future]
                        try:
                            result = future.result(timeout=60)
                            engineer['ai_analysis'] = result
                        except Exception as e:
                            logger.error(f"AI analysis timeout for {engineer['github_username']}: {e}")
                            engineer['ai_analysis'] = get_fallback_analysis()
                        finally:
                            pbar.update(1)

            logger.info(f"✓ Completed AI analysis for {len(enhanced_data)} engineers")

        except Exception as e:
            logger.error(f"Failed to initialize AI analyzer: {e}")
            logger.warning("Continuing without AI analysis...")
            for eng in enhanced_data:
                eng['ai_analysis'] = get_fallback_analysis()
    else:
        logger.info("AI analysis disabled")
        for eng in enhanced_data:
            eng['ai_analysis'] = get_fallback_analysis()

    # Step 4: Calculate performance rankings
    logger.info("Step 4: Calculating performance rankings...")
    ranker = PerformanceRanker()
    ranked_engineers = ranker.rank_engineers(enhanced_data)

    rank_summary = ranker.get_rank_summary(ranked_engineers)
    logger.info(
        f"✓ Ranked {rank_summary['total_engineers']} engineers. "
        f"Top performer: {rank_summary['top_performer']} "
        f"(score: {rank_summary['top_performer_score']:.1f})"
    )

    # Step 5: Generate PDF reports (concurrent)
    logger.info("Step 5: Generating PDF reports...")

    output_dir = f"{config.output_dir}/individual_reports"

    pdf_files = generate_all_reports_concurrently(
        ranked_engineers,
        output_dir,
        start_date,
        end_date,
        max_workers=config.max_workers_pdf_generation
    )

    logger.info(f"✓ Generated {len(pdf_files)} PDF reports in {output_dir}")

    # Summary
    logger.info("=" * 70)
    logger.info("✓ Individual Reports Generated Successfully!")
    logger.info("=" * 70)
    logger.info(f"Reports directory: {output_dir}")
    logger.info(f"Total engineers: {len(ranked_engineers)}")
    logger.info(f"Top performer: {rank_summary['top_performer']} (score: {rank_summary['top_performer_score']:.1f})")
    logger.info("=" * 70)


def main():
    """Main execution flow."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='GitHub Team Performance Metrics')
    parser.add_argument(
        '--individual-reports',
        action='store_true',
        help='Generate individual performance reports for each engineer (PDF)'
    )
    args = parser.parse_args()

    start_time = time.time()

    # Setup logging
    logger = setup_logging('INFO')

    logger.info("=" * 70)
    logger.info("GitHub Team Performance Metrics - Starting")
    logger.info("=" * 70)

    try:
        # 1. Load and validate configuration
        logger.info("Loading configuration...")
        config = load_config()
        validate_config(config)
        logger.info("Configuration loaded successfully")

        # 2. Initialize GitHub client
        logger.info(f"Initializing GitHub client for organization: {config.github_org}")
        github_client = GitHubClient(
            token=config.github_token,
            org_name=config.github_org,
            timeout=config.request_timeout
        )

        # 3. Check GitHub rate limits
        logger.info("Checking GitHub API rate limits...")
        rate_limit = github_client.check_rate_limit()
        logger.info(
            f"Rate limit: {rate_limit['remaining']}/{rate_limit['limit']} requests remaining"
        )

        if rate_limit['remaining'] < config.rate_limit_buffer:
            logger.warning(
                f"Low rate limit remaining ({rate_limit['remaining']}). "
                f"Consider running later to avoid hitting limits."
            )
            response = input("Continue anyway? (y/n): ")
            if response.lower() != 'y':
                logger.info("Execution cancelled by user")
                return

        # 4. Calculate date range
        start_date, end_date = calculate_date_range(
            config.days_back,
            config.start_date,
            config.end_date
        )
        logger.info(f"Fetching data from {start_date[:10]} to {end_date[:10]}")

        # 5. Fetch GitHub metrics
        logger.info("Fetching GitHub metrics (this may take several minutes)...")
        logger.info("Please be patient while we collect data from all repositories...")

        metrics_collector = GitHubMetricsCollector(
            github_client,
            start_date,
            end_date
        )

        try:
            github_data = metrics_collector.collect_all_metrics()
            logger.info(f"✓ Collected data from {len(github_data['repos'])} repositories")
            logger.info(f"✓ Found {len(github_data['commits'])} commits")
            logger.info(f"✓ Found {len(github_data['pull_requests'])} pull requests")
            logger.info(f"✓ Found {len(github_data['issues'])} issues closed")
        except Exception as e:
            logger.error(f"Failed to fetch GitHub data: {e}")
            raise

        # 6. Fetch Google Sheets data
        logger.info(f"Initializing Google Sheets client...")
        sheets_client = GoogleSheetsClient(config.google_credentials_path)

        logger.info(f"Reading Google Sheets (ID: {config.google_sheet_id})...")
        tickets = []
        ticket_metrics = {}

        try:
            sheet_data = sheets_client.read_sheet(
                config.google_sheet_id,
                config.google_sheet_name
            )

            sheets_processor = SheetsDataProcessor()
            tickets = sheets_processor.normalize_data(sheet_data)

            logger.info(f"✓ Read {len(tickets)} tickets from sheet")

            # Calculate ticket metrics
            if tickets:
                ticket_calculator = TicketMetricsCalculator(tickets)
                ticket_metrics = ticket_calculator.calculate_metrics_by_user()
                logger.info(f"✓ Calculated metrics for {len(ticket_metrics)} users from tickets")
            else:
                logger.warning("No tickets found in sheet")

        except Exception as e:
            logger.warning(f"Failed to read Google Sheets: {e}")
            logger.warning("Continuing with GitHub data only...")
            tickets = []
            ticket_metrics = {}

        # 7. Aggregate GitHub data by team member
        logger.info("Aggregating GitHub metrics by team member...")
        aggregated_github = metrics_collector.aggregate_by_team_member(github_data)
        logger.info(f"✓ Aggregated metrics for {len(aggregated_github)} team members")

        # 8. Combine datasets
        logger.info("Combining GitHub and ticket data...")

        # Load user mapping
        user_mapping = load_user_mapping(config.user_mapping_file)
        if user_mapping:
            logger.info(f"Loaded {len(user_mapping)} manual user mappings")

        data_combiner = DataCombiner(team_member_map=user_mapping)
        combined_data = data_combiner.merge_datasets(
            aggregated_github,
            ticket_metrics
        )

        # Report on user matching
        match_report = data_combiner.handle_unmatched_users(
            set(aggregated_github.keys()),
            set(ticket_metrics.keys())
        )

        # 9. Calculate derived metrics
        logger.info("Calculating derived metrics...")
        enhanced_data = MetricsCalculator.calculate_derived_metrics(combined_data)
        logger.info(f"✓ Enhanced data with derived metrics")

        # 10. Generate Excel report
        output_filename = config.output_filename or generate_output_filename(
            start_date,
            end_date
        )
        output_path = f"{config.output_dir}/{output_filename}"

        logger.info(f"Generating Excel report: {output_path}")
        exporter = ExcelExporter(output_path)

        # Create sheets
        exporter.create_summary_sheet(enhanced_data)
        logger.info("✓ Created Summary sheet")

        exporter.create_team_metrics_sheet(enhanced_data)
        logger.info("✓ Created Team Metrics sheet")

        exporter.create_repository_breakdown_sheet(
            github_data['repos'],
            github_data['commits']
        )
        logger.info("✓ Created Repository Breakdown sheet")

        if tickets:
            exporter.create_ticket_details_sheet(tickets)
            logger.info("✓ Created Ticket Details sheet")

        exporter.apply_formatting()
        exporter.save()

        # 11. Print summary
        elapsed = time.time() - start_time
        logger.info("=" * 70)
        logger.info("✓ Report generated successfully!")
        logger.info("=" * 70)
        logger.info(f"Output file: {output_path}")
        logger.info(f"Total team members: {len(enhanced_data)}")
        logger.info(f"Date range: {start_date[:10]} to {end_date[:10]}")
        logger.info(f"Execution time: {format_duration(elapsed)}")
        logger.info("=" * 70)

        # Print top contributors
        logger.info("\nTop 5 Contributors (by activity score):")
        sorted_data = sorted(
            enhanced_data,
            key=lambda x: x.get('activity_score', 0),
            reverse=True
        )

        for i, user in enumerate(sorted_data[:5], 1):
            logger.info(
                f"{i}. {user.get('display_name', 'Unknown')} - "
                f"{user.get('total_commits', 0)} commits, "
                f"{user.get('prs_created', 0)} PRs, "
                f"{user.get('total_tickets', 0)} tickets"
            )

        logger.info("\n✓ Done!")

        # Generate individual reports if requested
        if args.individual_reports:
            logger.info("\n" + "=" * 70)
            logger.info("Starting Individual Performance Reports Generation...")
            logger.info("=" * 70)

            generate_individual_reports(
                enhanced_data,
                github_data,
                github_client,
                config,
                start_date,
                end_date
            )

    except KeyboardInterrupt:
        logger.info("\nExecution cancelled by user")
        sys.exit(1)

    except Exception as e:
        logger.error(f"\n✗ Execution failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
