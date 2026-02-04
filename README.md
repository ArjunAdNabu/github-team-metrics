# GitHub Team Performance Metrics

A standalone Python tool that fetches team performance data from GitHub and Google Sheets, combining them into a comprehensive Excel report for easy analysis.

## Features

- **GitHub Metrics**: Automatically collect commits, pull requests, and code review data from all repositories in your organization
- **Ticket Tracking**: Integrate with Google Sheets for ticket/support data
- **Smart User Matching**: Automatically match GitHub users to ticket assignees
- **Comprehensive Excel Report**: Multi-sheet Excel file with summary, detailed metrics, and breakdowns
- **GraphQL Optimization**: Efficient API usage with GitHub's GraphQL API
- **On-Demand Execution**: Run manually whenever you need updated metrics

## Prerequisites

- Python 3.8 or higher
- GitHub Personal Access Token with appropriate permissions
- Google Cloud Service Account for Sheets API access
- Access to the GitHub organization ("AdNabu-Team")

## Installation

1. **Clone or navigate to the project directory:**
   ```bash
   cd /Users/arjunAdNabu-Team/Projects/github-team-metrics
   ```

2. **Create a virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

### 1. Create .env File

Copy the example environment file:
```bash
cp .env.example .env
```

Edit `.env` and fill in your credentials:
```bash
# GitHub Configuration
GITHUB_TOKEN=your_github_personal_access_token_here
GITHUB_ORG=AdNabu-Team

# Google Sheets Configuration
GOOGLE_CREDENTIALS_PATH=./credentials/google_service_account.json
GOOGLE_SHEET_ID=your_sheet_id_here
GOOGLE_SHEET_NAME=Sheet1

# Optional: Date Range (defaults to last 30 days)
# START_DATE=2025-01-01
# END_DATE=2025-01-31
```

### 2. GitHub Personal Access Token

1. Go to [GitHub Settings → Developer settings → Personal access tokens](https://github.com/settings/tokens)
2. Click "Generate new token (classic)"
3. Select the following scopes:
   - `repo` (Full control of private repositories)
   - `read:org` (Read organization membership)
   - `read:user` (Read user profile data)
4. Copy the token and add it to your `.env` file

### 3. Google Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use existing)
3. Enable the Google Sheets API:
   - Navigate to "APIs & Services" → "Library"
   - Search for "Google Sheets API" and enable it
4. Create a Service Account:
   - Go to "IAM & Admin" → "Service Accounts"
   - Click "Create Service Account"
   - Name it "github-metrics-reader"
   - Grant role: "Viewer" (or no role needed for just Sheets access)
5. Create and download a JSON key:
   - Click on the service account you just created
   - Go to "Keys" tab → "Add Key" → "Create new key"
   - Choose JSON format
   - Save the file to `credentials/google_service_account.json`
6. Share your Google Sheet:
   - Open your Google Sheet
   - Click "Share"
   - Add the service account email (found in the JSON file: `client_email`)
   - Grant "Viewer" access

### 4. Google Sheet Structure

Your Google Sheet should have the following columns (matching "Tickets and queries.xlsx"):

1. Title
2. Priority
3. Type
4. Assigned
5. Reported by
6. Reported time (M/D/Y T(24))
7. First response time (M/D/Y T(24))
8. Closed time (M/D/Y T(24))
9. Duration
10. Bucket
11. GitHub Issue
12. Notes
13. Root cause status

The script will automatically detect these columns and parse the data.

## Usage

### Basic Usage (Last 30 Days)

```bash
cd /Users/arjunAdNabu-Team/Projects/github-team-metrics
source venv/bin/activate
python main.py
```

### Custom Date Range

Edit your `.env` file to specify custom dates:
```bash
START_DATE=2025-01-01
END_DATE=2025-01-31
```

Then run:
```bash
python main.py
```

### Expected Output

```
======================================================================
GitHub Team Performance Metrics - Starting
======================================================================
Loading configuration...
Configuration loaded successfully
Initializing GitHub client for organization: AdNabu-Team
Checking GitHub API rate limits...
Rate limit: 4998/5000 requests remaining
Fetching data from 2024-12-16 to 2025-01-15
Fetching GitHub metrics (this may take several minutes)...
Please be patient while we collect data from all repositories...
[1/15] Fetching data from AdNabu-Team/AdNabu-Team-api
[2/15] Fetching data from AdNabu-Team/shopify-react
...
✓ Collected data from 15 repositories
✓ Found 342 commits
✓ Found 87 pull requests
Initializing Google Sheets client...
Reading Google Sheets (ID: 1BxiMVs...)
✓ Read 12 tickets from sheet
✓ Calculated metrics for 10 users from tickets
Aggregating GitHub metrics by team member...
✓ Aggregated metrics for 12 team members
Combining GitHub and ticket data...
User matching results:
  Matched: 10 users
  GitHub only: 2 users - bot-user, automation-account
  Tickets only: 0 users
Calculating derived metrics...
✓ Enhanced data with derived metrics
Generating Excel report: ./output/team_metrics_20250203_140532.xlsx
✓ Created Summary sheet
✓ Created Team Metrics sheet
✓ Created Repository Breakdown sheet
✓ Created Ticket Details sheet
======================================================================
✓ Report generated successfully!
======================================================================
Output file: ./output/team_metrics_20250203_140532.xlsx
Total team members: 12
Date range: 2024-12-16 to 2025-01-15
Execution time: 3.2m
======================================================================

Top 5 Contributors (by activity score):
1. John Doe - 45 commits, 12 PRs, 8 tickets
2. Jane Smith - 38 commits, 10 PRs, 6 tickets
3. Bob Johnson - 32 commits, 8 PRs, 10 tickets
4. Alice Williams - 28 commits, 9 PRs, 7 tickets
5. Charlie Brown - 25 commits, 7 PRs, 5 tickets

✓ Done!
```

## Output Structure

The generated Excel file contains multiple sheets:

### 1. Summary Sheet
- Team-wide statistics (total commits, PRs, reviews, tickets)
- Top 10 contributors by activity score
- Quick overview of team performance

### 2. Team Metrics Sheet (Main Sheet)
One row per team member with all metrics:

**GitHub Metrics:**
- Commits (total and frequency per day)
- Pull requests (created, merged, merge rate)
- Code reviews (given, received, participation ratio)
- Average review time
- Average PR size (lines changed)
- Active repositories

**Ticket Metrics:**
- Total tickets assigned
- Open vs closed tickets
- Priority breakdown (High/Medium/Low)
- Type distribution
- Average resolution time
- Average first response time
- Tickets with GitHub issue links

**Derived Metrics:**
- Commits per ticket ratio
- Activity score (weighted formula)
- Ticket closure rate

### 3. Repository Breakdown Sheet
- Metrics per repository
- Number of commits per repo
- Number of active contributors
- Repository status (Active/Archived)

### 4. Ticket Details Sheet
Individual ticket breakdown with all 13 columns from your Google Sheet:
- Title, Priority, Type, Assigned, Reported by
- Timestamps (Reported, First response, Closed)
- Duration, Bucket, GitHub Issue, Notes, Root cause status

### 5. Formatting Features
- Bold headers with colored backgrounds
- Frozen header rows
- Auto-filters on all columns
- Auto-sized columns
- Borders on all cells

## Metrics Explained

### Activity Score
A weighted metric combining multiple factors:
- Commits × 1
- Pull Requests × 2
- Code Reviews × 1.5
- Tickets × 1

Higher scores indicate more overall activity.

### Review Participation
Ratio of reviews given to reviews received. A value > 1 means the person reviews more code than they receive reviews on their own code.

### PR Merge Rate
Percentage of pull requests that were successfully merged. Higher is generally better (indicates quality contributions).

### Commit Frequency
Average commits per day during the measurement period.

## Troubleshooting

### Rate Limit Exceeded
**Error:** `HTTP 403 - Rate limit exceeded`

**Solution:**
- GitHub API has a limit of 5,000 requests per hour
- Wait for the rate limit to reset (shown in the error message)
- Or run the script at a different time
- The script uses GraphQL to minimize API calls, but large organizations with many repos can still hit limits

### Permission Denied (Google Sheets)
**Error:** `Permission denied for sheet`

**Solution:**
1. Open your Google Sheet
2. Click the "Share" button
3. Add the service account email (found in `google_service_account.json` under `client_email`)
4. Grant "Viewer" access
5. Click "Send"

### No Commits Found
**Issue:** Empty GitHub data despite having commits

**Check:**
1. Verify the organization name is correct ("AdNabu-Team")
2. Check the date range - ensure there were commits in the last 30 days
3. Verify your GitHub token has the correct scopes:
   - `repo`, `read:org`, `read:user`
4. Check if the token has expired
5. Ensure you have access to the organization's repositories

### Invalid Google Sheet Structure
**Warning:** `Unexpected Sheets error` or `Failed to parse row`

**Solution:**
- The script expects specific columns (see "Google Sheet Structure" above)
- Check that your sheet has these column headers in the first row
- Verify the sheet name matches `GOOGLE_SHEET_NAME` in `.env` (default: "Sheet1")
- If using a different structure, the script will continue with GitHub data only

### Import Errors
**Error:** `ModuleNotFoundError: No module named 'requests'`

**Solution:**
```bash
# Make sure you're in the virtual environment
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

### Date Parsing Errors
**Warning:** `Failed to parse date: ...`

**Note:** The script tries multiple date formats. If dates aren't parsing correctly, check that your Google Sheet uses one of these formats:
- `M/D/Y H:M` (e.g., "1/15/2025 14:30")
- `M/D/Y H:M:S` (e.g., "1/15/2025 14:30:00")
- `YYYY-MM-DD H:M:S` (e.g., "2025-01-15 14:30:00")

## Advanced Configuration

All configuration options in `.env`:

```bash
# Required
GITHUB_TOKEN=your_token_here
GITHUB_ORG=AdNabu-Team
GOOGLE_CREDENTIALS_PATH=./credentials/google_service_account.json
GOOGLE_SHEET_ID=your_sheet_id

# Optional
GOOGLE_SHEET_NAME=Sheet1           # Default: Sheet1
DAYS_BACK=30                       # Default: 30 days
START_DATE=YYYY-MM-DD              # Override days_back
END_DATE=YYYY-MM-DD                # Override days_back
OUTPUT_DIR=./output                # Default: ./output
OUTPUT_FILENAME=custom_name.xlsx   # Auto-generated if not set
MAX_WORKERS=5                      # Concurrent API requests
REQUEST_TIMEOUT=30                 # Request timeout in seconds
RATE_LIMIT_BUFFER=100             # Buffer for rate limits
```

## Project Structure

```
github-team-metrics/
├── README.md                       # This file
├── .env                            # Your configuration (not in git)
├── .env.example                    # Configuration template
├── .gitignore                      # Git ignore rules
├── requirements.txt                # Python dependencies
├── config.py                       # Configuration loader
├── main.py                         # Main execution script
│
├── src/
│   ├── __init__.py
│   ├── github_fetcher.py          # GitHub GraphQL API client
│   ├── sheets_reader.py           # Google Sheets API client
│   ├── data_processor.py          # Data combination & metrics
│   ├── excel_exporter.py          # Excel generation
│   └── utils.py                   # Utility functions
│
├── credentials/
│   ├── .gitkeep
│   └── google_service_account.json # Google credentials (not in git)
│
└── output/
    ├── .gitkeep
    └── *.xlsx                      # Generated reports (not in git)
```

## Security Notes

- Never commit `.env` file or `google_service_account.json` to version control
- These files are already in `.gitignore`
- Rotate your tokens/credentials periodically
- Use minimal required permissions for tokens and service accounts

## Support

For issues or questions:
1. Check the Troubleshooting section above
2. Verify your configuration in `.env`
3. Check GitHub API rate limits: https://api.github.com/rate_limit
4. Review the console output for specific error messages

## License

Internal use only - Adnabu team.
