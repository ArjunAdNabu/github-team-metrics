"""Main script for GitHub Team Performance Metrics."""

import sys
import time
from datetime import datetime

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


def main():
    """Main execution flow."""
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

    except KeyboardInterrupt:
        logger.info("\nExecution cancelled by user")
        sys.exit(1)

    except Exception as e:
        logger.error(f"\n✗ Execution failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
