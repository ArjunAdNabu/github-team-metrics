"""PDF report generator for individual engineer performance reports.

Generates professional PDF reports with charts, AI analysis, and rankings.
"""

import logging
import io
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

logger = logging.getLogger('github_metrics')


class PDFReportGenerator:
    """Generate professional PDF performance reports."""

    def __init__(self, output_dir: str):
        """
        Initialize PDF report generator.

        Args:
            output_dir: Directory to save PDF reports
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Colors
        self.primary_color = colors.HexColor('#4472C4')
        self.secondary_color = colors.HexColor('#70AD47')
        self.gray_color = colors.HexColor('#333333')
        self.light_gray = colors.HexColor('#F2F2F2')

        # Styles
        self.styles = getSampleStyleSheet()
        self._setup_styles()

    def _setup_styles(self):
        """Setup custom paragraph styles."""
        # Title style
        self.styles.add(ParagraphStyle(
            name='ReportTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=self.primary_color,
            spaceAfter=30,
            alignment=TA_CENTER
        ))

        # Heading style
        self.styles.add(ParagraphStyle(
            name='ReportHeading',
            parent=self.styles['Heading2'],
            fontSize=16,
            textColor=self.primary_color,
            spaceAfter=12,
            spaceBefore=20
        ))

        # Subheading style
        self.styles.add(ParagraphStyle(
            name='ReportSubheading',
            parent=self.styles['Heading3'],
            fontSize=12,
            textColor=self.gray_color,
            spaceAfter=8,
            spaceBefore=10
        ))

    def generate_report(
        self,
        engineer_data: Dict,
        start_date: str,
        end_date: str
    ) -> str:
        """
        Generate complete PDF report for an engineer.

        Args:
            engineer_data: Engineer dictionary with all metrics and analysis
            start_date: Report start date (YYYY-MM-DD)
            end_date: Report end date (YYYY-MM-DD)

        Returns:
            Path to generated PDF file
        """
        username = engineer_data['github_username']
        filename = f"{username}_performance_report.pdf"
        filepath = self.output_dir / filename

        # Create PDF
        doc = SimpleDocTemplate(
            str(filepath),
            pagesize=letter,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )

        # Build content
        story = []

        # Title page
        story.extend(self._create_title_page(engineer_data, start_date, end_date))

        # Executive summary
        story.append(PageBreak())
        story.extend(self._create_executive_summary(engineer_data))

        # Quantitative metrics with charts
        story.append(PageBreak())
        story.extend(self._create_metrics_section(engineer_data))

        # AI Analysis
        story.append(PageBreak())
        story.extend(self._create_ai_analysis_section(engineer_data))

        # Strengths & Improvements
        story.append(PageBreak())
        story.extend(self._create_strengths_improvements_section(engineer_data))

        # Performance Ranking
        story.append(PageBreak())
        story.extend(self._create_ranking_section(engineer_data))

        # Build PDF
        doc.build(story)

        logger.info(f"Generated PDF report: {filepath}")
        return str(filepath)

    def _create_title_page(
        self,
        eng: Dict,
        start_date: str,
        end_date: str
    ) -> List:
        """Create title page."""
        content = []

        # Title
        title = Paragraph(
            f"Performance Report<br/>{eng.get('display_name', eng['github_username'])}",
            self.styles['ReportTitle']
        )
        content.append(title)
        content.append(Spacer(1, 0.5*inch))

        # Period
        period_text = f"<b>Period:</b> {start_date[:10]} to {end_date[:10]}"
        content.append(Paragraph(period_text, self.styles['Normal']))
        content.append(Spacer(1, 0.3*inch))

        # Summary box with key metrics
        summary_data = [
            ['Metric', 'Value'],
            ['Rank', f"#{eng.get('rank', 'N/A')} - {eng.get('rank_label', '')}"],
            ['Composite Score', f"{eng.get('composite_score', 0):.1f}/100"],
            ['Total Commits', str(eng.get('total_commits', 0))],
            ['PRs Created', str(eng.get('prs_created', 0))],
            ['Code Reviews', str(eng.get('reviews_given', 0))],
            ['Complexity Score', str(eng.get('total_complexity_score', 0))]
        ]

        summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.primary_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), self.light_gray),
            ('GRID', (0, 0), (-1, -1), 1, colors.white)
        ]))

        content.append(summary_table)
        content.append(Spacer(1, 0.5*inch))

        # Generated timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        content.append(Paragraph(
            f"<i>Generated: {timestamp}</i>",
            self.styles['Normal']
        ))

        return content

    def _create_executive_summary(self, eng: Dict) -> List:
        """Create executive summary section."""
        content = []

        content.append(Paragraph("Executive Summary", self.styles['ReportHeading']))

        # AI-generated summary
        ai_analysis = eng.get('ai_analysis', {})
        insights = ai_analysis.get('insights', {})
        summary_text = insights.get('overall_summary', 'No AI analysis available.')

        content.append(Paragraph(summary_text, self.styles['Normal']))
        content.append(Spacer(1, 0.3*inch))

        # Highlights table
        highlights_data = [
            ['Category', 'Metric', 'Value'],
            ['Code Quality', 'Quality Score', f"{ai_analysis.get('code_quality', {}).get('quality_score', 0):.1f}/10"],
            ['Code Quality', 'Maintainability', f"{ai_analysis.get('code_quality', {}).get('maintainability_score', 0):.1f}/10"],
            ['Review Quality', 'Thoroughness', f"{ai_analysis.get('review_quality', {}).get('thoroughness_score', 0):.1f}/10"],
            ['Review Quality', 'Helpfulness', f"{ai_analysis.get('review_quality', {}).get('helpfulness_score', 0):.1f}/10"],
            ['Activity', 'Commit Frequency', f"{eng.get('commit_frequency', 0):.2f}/day"],
            ['Activity', 'PR Merge Rate', f"{eng.get('pr_merge_rate', 0):.1f}%"]
        ]

        highlights_table = Table(highlights_data, colWidths=[1.5*inch, 2*inch, 1.5*inch])
        highlights_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.primary_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ]))

        content.append(highlights_table)

        return content

    def _create_metrics_section(self, eng: Dict) -> List:
        """Create quantitative metrics section with charts."""
        content = []

        content.append(Paragraph("Quantitative Metrics", self.styles['ReportHeading']))

        # Create charts
        charts = []

        # Chart 1: Activity overview (bar chart)
        activity_chart = self._create_activity_chart(eng)
        if activity_chart:
            charts.append(activity_chart)

        # Chart 2: Code changes (bar chart)
        code_chart = self._create_code_changes_chart(eng)
        if code_chart:
            charts.append(code_chart)

        # Add charts side by side
        if charts:
            chart_table = Table([charts], colWidths=[3*inch, 3*inch])
            content.append(chart_table)
            content.append(Spacer(1, 0.3*inch))

        return content

    def _create_activity_chart(self, eng: Dict) -> Image:
        """Create activity overview bar chart."""
        try:
            fig, ax = plt.subplots(figsize=(5, 3), dpi=150)

            metrics = ['Commits', 'PRs', 'Reviews', 'Tickets']
            values = [
                eng.get('total_commits', 0),
                eng.get('prs_created', 0),
                eng.get('reviews_given', 0),
                eng.get('total_tickets', 0)
            ]

            bars = ax.bar(metrics, values, color='#4472C4')
            ax.set_ylabel('Count')
            ax.set_title('Activity Overview')

            # Add value labels on bars
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{int(height)}',
                       ha='center', va='bottom')

            plt.tight_layout()

            # Convert to image
            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
            img_buffer.seek(0)
            plt.close(fig)

            return Image(img_buffer, width=3*inch, height=1.8*inch)

        except Exception as e:
            logger.error(f"Failed to create activity chart: {e}")
            return None

    def _create_code_changes_chart(self, eng: Dict) -> Image:
        """Create code changes bar chart."""
        try:
            fig, ax = plt.subplots(figsize=(5, 3), dpi=150)

            metrics = ['Added', 'Deleted']
            values = [
                eng.get('lines_added', 0),
                eng.get('lines_deleted', 0)
            ]

            colors_list = ['#70AD47', '#E74C3C']
            bars = ax.bar(metrics, values, color=colors_list)
            ax.set_ylabel('Lines of Code')
            ax.set_title('Code Changes')

            # Add value labels
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{int(height):,}',
                       ha='center', va='bottom')

            plt.tight_layout()

            # Convert to image
            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
            img_buffer.seek(0)
            plt.close(fig)

            return Image(img_buffer, width=3*inch, height=1.8*inch)

        except Exception as e:
            logger.error(f"Failed to create code changes chart: {e}")
            return None

    def _create_ai_analysis_section(self, eng: Dict) -> List:
        """Create AI analysis section."""
        content = []

        content.append(Paragraph("AI-Powered Code Analysis", self.styles['ReportHeading']))

        ai_analysis = eng.get('ai_analysis', {})
        code_quality = ai_analysis.get('code_quality', {})
        review_quality = ai_analysis.get('review_quality', {})

        # Code quality
        content.append(Paragraph("Code Quality Analysis", self.styles['ReportSubheading']))
        content.append(Paragraph(
            code_quality.get('summary', 'No code analysis available.'),
            self.styles['Normal']
        ))
        content.append(Spacer(1, 0.2*inch))

        # Best practices
        if code_quality.get('best_practices_followed'):
            content.append(Paragraph("<b>Best Practices Followed:</b>", self.styles['Normal']))
            for practice in code_quality['best_practices_followed'][:3]:
                content.append(Paragraph(f"• {practice}", self.styles['Normal']))
            content.append(Spacer(1, 0.2*inch))

        # Review quality
        content.append(Paragraph("Code Review Quality Analysis", self.styles['ReportSubheading']))
        content.append(Paragraph(
            review_quality.get('summary', 'No review analysis available.'),
            self.styles['Normal']
        ))

        return content

    def _create_strengths_improvements_section(self, eng: Dict) -> List:
        """Create strengths and improvements section."""
        content = []

        content.append(Paragraph("Performance Insights", self.styles['ReportHeading']))

        ai_analysis = eng.get('ai_analysis', {})
        insights = ai_analysis.get('insights', {})

        # Strengths
        content.append(Paragraph("Key Strengths", self.styles['ReportSubheading']))
        strengths = insights.get('strengths', [])

        if strengths:
            for i, strength in enumerate(strengths, 1):
                content.append(Paragraph(f"{i}. {strength}", self.styles['Normal']))
        else:
            content.append(Paragraph("No strengths analysis available.", self.styles['Normal']))

        content.append(Spacer(1, 0.3*inch))

        # Areas for improvement
        content.append(Paragraph("Areas for Improvement", self.styles['ReportSubheading']))
        improvements = insights.get('improvements', [])

        if improvements:
            for i, improvement in enumerate(improvements, 1):
                content.append(Paragraph(f"{i}. {improvement}", self.styles['Normal']))
        else:
            content.append(Paragraph("No improvements analysis available.", self.styles['Normal']))

        return content

    def _create_ranking_section(self, eng: Dict) -> List:
        """Create performance ranking section."""
        content = []

        content.append(Paragraph("Performance Ranking", self.styles['ReportHeading']))

        # Rank badge
        rank_text = f"""
        <b>Rank: #{eng.get('rank', 'N/A')}</b><br/>
        {eng.get('rank_label', '')}<br/>
        Percentile: {eng.get('percentile', 0):.1f}%
        """
        content.append(Paragraph(rank_text, self.styles['Normal']))
        content.append(Spacer(1, 0.2*inch))

        # Score breakdown
        breakdown_data = [
            ['Component', 'Score', 'Weight'],
            ['Complexity', f"{eng.get('complexity_component', 0):.1f}/100", '50%'],
            ['Other Metrics', f"{eng.get('other_component', 0):.1f}/100", '50%'],
            ['', '', ''],
            ['Composite Score', f"<b>{eng.get('composite_score', 0):.1f}/100</b>", '100%']
        ]

        breakdown_table = Table(breakdown_data, colWidths=[2*inch, 1.5*inch, 1*inch])
        breakdown_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.primary_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('LINEABOVE', (0, -1), (-1, -1), 2, self.primary_color),
            ('GRID', (0, 0), (-1, -2), 1, colors.grey)
        ]))

        content.append(breakdown_table)
        content.append(Spacer(1, 0.2*inch))

        # Footer note
        content.append(Paragraph(
            "<i>Note: Rankings are based on 50% complexity score + 50% other metrics "
            "(code quality, review quality, activity).</i>",
            self.styles['Normal']
        ))

        return content


def generate_all_reports_concurrently(
    engineers: List[Dict],
    output_dir: str,
    start_date: str,
    end_date: str,
    max_workers: int = 5
) -> List[str]:
    """
    Generate PDF reports for all engineers concurrently.

    Args:
        engineers: List of engineer dictionaries with all metrics
        output_dir: Directory to save PDFs
        start_date: Report start date
        end_date: Report end date
        max_workers: Number of concurrent workers

    Returns:
        List of generated PDF file paths
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from tqdm import tqdm

    generator = PDFReportGenerator(output_dir)
    generated_files = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                generator.generate_report,
                eng,
                start_date,
                end_date
            ): eng
            for eng in engineers
        }

        with tqdm(total=len(engineers), desc="Generating PDFs") as pbar:
            for future in as_completed(futures):
                engineer = futures[future]
                try:
                    pdf_path = future.result()
                    generated_files.append(pdf_path)
                    logger.info(f"✓ Generated PDF for {engineer['github_username']}")
                except Exception as e:
                    logger.error(
                        f"Failed to generate PDF for {engineer['github_username']}: {e}"
                    )
                finally:
                    pbar.update(1)

    logger.info(f"Generated {len(generated_files)} PDF reports")
    return generated_files
