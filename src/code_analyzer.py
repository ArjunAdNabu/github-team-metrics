"""AI-powered code and review analysis for individual performance reports.

Multi-provider support: Gemini (default, free), Claude, ChatGPT, Ollama.
"""

import json
import logging
import hashlib
import os
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger('github_metrics')


class AIAnalyzer(ABC):
    """Abstract base class for AI providers."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize AI analyzer.

        Args:
            api_key: API key for the provider
            model: Model name to use
        """
        self.api_key = api_key
        self.model = model
        self.cache_dir = Path('./cache/ai_analysis')
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def analyze_code_quality(self, diffs: List[Dict], context: Dict) -> Dict:
        """
        Analyze code quality from diffs.

        Args:
            diffs: List of diff dictionaries from code_diff_fetcher
            context: Additional context (username, repo, etc.)

        Returns:
            {
                'quality_score': float (0-10),
                'maintainability_score': float (0-10),
                'patterns_observed': List[str],
                'best_practices_followed': List[str],
                'areas_for_improvement': List[str],
                'summary': str
            }
        """
        pass

    @abstractmethod
    def analyze_review_quality(self, reviews: List[Dict], context: Dict) -> Dict:
        """
        Analyze code review quality.

        Args:
            reviews: List of review dictionaries from review_comment_fetcher
            context: Additional context (username, repo, etc.)

        Returns:
            {
                'thoroughness_score': float (0-10),
                'helpfulness_score': float (0-10),
                'review_patterns': List[str],
                'strengths': List[str],
                'areas_for_improvement': List[str],
                'summary': str
            }
        """
        pass

    @abstractmethod
    def generate_performance_insights(
        self,
        code_analysis: Dict,
        review_analysis: Dict,
        metrics: Dict
    ) -> Dict:
        """
        Generate overall performance insights.

        Args:
            code_analysis: Output from analyze_code_quality
            review_analysis: Output from analyze_review_quality
            metrics: Quantitative metrics dictionary

        Returns:
            {
                'strengths': List[str] (3-5 items),
                'improvements': List[str] (3-5 items),
                'overall_summary': str (2-3 paragraphs)
            }
        """
        pass

    def _get_cache_key(self, provider: str, data: str) -> str:
        """Generate cache key from data hash."""
        data_hash = hashlib.sha256(data.encode()).hexdigest()[:16]
        return f"{provider}_{data_hash}.json"

    def _get_from_cache(self, cache_key: str) -> Optional[Dict]:
        """Retrieve analysis from cache."""
        cache_file = self.cache_dir / cache_key

        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    logger.debug(f"Cache hit: {cache_key}")
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read cache {cache_key}: {e}")

        return None

    def _save_to_cache(self, cache_key: str, data: Dict):
        """Save analysis to cache."""
        cache_file = self.cache_dir / cache_key

        try:
            with open(cache_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved to cache: {cache_key}")
        except Exception as e:
            logger.warning(f"Failed to save cache {cache_key}: {e}")


class GeminiAnalyzer(AIAnalyzer):
    """Google Gemini implementation (DEFAULT, FREE)."""

    def __init__(self, api_key: str, model: str = 'gemini-2.0-flash'):
        """
        Initialize Gemini analyzer.

        Args:
            api_key: Gemini API key (free, from https://makersuite.google.com/app/apikey)
            model: Gemini model name (default: gemini-2.0-flash)
        """
        super().__init__(api_key, model)

        try:
            import google.generativeai as genai
            self.genai = genai
            self.genai.configure(api_key=api_key)
            self.client = self.genai.GenerativeModel(model)
            logger.info(f"Initialized Gemini analyzer with model: {model}")
        except ImportError:
            raise ImportError(
                "google-generativeai not installed. "
                "Install with: pip install google-generativeai"
            )
        except Exception as e:
            raise Exception(f"Failed to initialize Gemini: {e}")

    def _call_gemini(self, prompt: str, cache_key: str) -> Dict:
        """Call Gemini API with caching."""
        # Check cache
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        try:
            response = self.client.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.1  # Consistent responses
                }
            )

            result = json.loads(response.text)

            # Save to cache
            self._save_to_cache(cache_key, result)

            return result

        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise

    def analyze_code_quality(self, diffs: List[Dict], context: Dict) -> Dict:
        """Analyze code quality using Gemini."""
        if not diffs:
            return self._get_empty_code_analysis()

        # Prepare prompt
        username = context.get('username', 'Unknown')
        diff_summary = self._summarize_diffs(diffs)

        prompt = f"""Analyze the code quality of commits by {username}.

Commits summary:
{diff_summary}

Evaluate the code quality on these dimensions (0-10 scale):
1. Code quality: Readability, structure, organization
2. Maintainability: Ease of future modifications, documentation

Provide your analysis in this JSON format:
{{
    "quality_score": <float 0-10>,
    "maintainability_score": <float 0-10>,
    "patterns_observed": [<list of coding patterns observed>],
    "best_practices_followed": [<list of best practices>],
    "areas_for_improvement": [<list of specific improvements>],
    "summary": "<2-3 sentence summary>"
}}

Be objective and specific. Base scores on observable code characteristics."""

        cache_key = self._get_cache_key('gemini_code', prompt)

        return self._call_gemini(prompt, cache_key)

    def analyze_review_quality(self, reviews: List[Dict], context: Dict) -> Dict:
        """Analyze review quality using Gemini."""
        if not reviews:
            return self._get_empty_review_analysis()

        # Prepare prompt
        username = context.get('username', 'Unknown')
        review_summary = self._summarize_reviews(reviews)

        prompt = f"""Analyze the code review quality of reviews by {username}.

Reviews summary:
{review_summary}

Evaluate the review quality on these dimensions (0-10 scale):
1. Thoroughness: Depth and completeness of review
2. Helpfulness: Actionable feedback, constructive suggestions

Provide your analysis in this JSON format:
{{
    "thoroughness_score": <float 0-10>,
    "helpfulness_score": <float 0-10>,
    "review_patterns": [<list of review patterns observed>],
    "strengths": [<list of review strengths>],
    "areas_for_improvement": [<list of specific improvements>],
    "summary": "<2-3 sentence summary>"
}}

Be objective and specific. Base scores on review content and quality."""

        cache_key = self._get_cache_key('gemini_review', prompt)

        return self._call_gemini(prompt, cache_key)

    def generate_performance_insights(
        self,
        code_analysis: Dict,
        review_analysis: Dict,
        metrics: Dict
    ) -> Dict:
        """Generate performance insights using Gemini."""
        prompt = f"""Generate performance insights for an engineer based on:

Code Quality Analysis:
- Quality Score: {code_analysis.get('quality_score', 0)}/10
- Maintainability Score: {code_analysis.get('maintainability_score', 0)}/10
- Summary: {code_analysis.get('summary', '')}

Review Quality Analysis:
- Thoroughness Score: {review_analysis.get('thoroughness_score', 0)}/10
- Helpfulness Score: {review_analysis.get('helpfulness_score', 0)}/10
- Summary: {review_analysis.get('summary', '')}

Quantitative Metrics:
- Total Commits: {metrics.get('total_commits', 0)}
- PRs Created: {metrics.get('prs_created', 0)}
- PR Merge Rate: {metrics.get('pr_merge_rate', 0)}%
- Reviews Given: {metrics.get('reviews_given', 0)}
- Complexity Score: {metrics.get('total_complexity_score', 0)}

Provide actionable insights in this JSON format:
{{
    "strengths": [<list of 3-5 specific strengths>],
    "improvements": [<list of 3-5 specific actionable improvements>],
    "overall_summary": "<2-3 paragraph overall assessment>"
}}

Be specific, actionable, and balanced."""

        cache_key = self._get_cache_key('gemini_insights', prompt)

        return self._call_gemini(prompt, cache_key)

    def _summarize_diffs(self, diffs: List[Dict], max_chars: int = 5000) -> str:
        """Summarize diffs for AI analysis."""
        summary = ""

        for i, diff in enumerate(diffs[:10], 1):  # Max 10 diffs
            summary += f"\nCommit {i}: {diff['message'][:100]}\n"
            summary += f"  Changes: +{diff['additions']}/-{diff['deletions']}\n"
            summary += f"  Files: {len(diff['files'])}\n"

            # Add some file details
            for file in diff['files'][:3]:  # Max 3 files per commit
                summary += f"    - {file['filename']} (+{file['additions']}/-{file['deletions']})\n"

                # Add snippet of patch
                if file.get('patch'):
                    patch_lines = file['patch'].split('\n')[:5]
                    for line in patch_lines:
                        summary += f"      {line}\n"

            if len(summary) > max_chars:
                summary += "\n... (truncated)"
                break

        return summary

    def _summarize_reviews(self, reviews: List[Dict], max_chars: int = 5000) -> str:
        """Summarize reviews for AI analysis."""
        summary = ""

        for i, review in enumerate(reviews[:5], 1):  # Max 5 reviews
            summary += f"\nReview {i}: PR #{review['pr_number']} - {review['pr_title'][:80]}\n"

            # Add review summaries
            for rs in review.get('review_summaries', []):
                summary += f"  {rs['state']}: {rs['body'][:200]}\n"

            # Add review comments
            for comment in review.get('review_comments', [])[:3]:  # Max 3 comments
                summary += f"  Comment on {comment['path']}:\n"
                summary += f"    {comment['body'][:200]}\n"

            if len(summary) > max_chars:
                summary += "\n... (truncated)"
                break

        return summary

    def _get_empty_code_analysis(self) -> Dict:
        """Return empty code analysis (no diffs available)."""
        return {
            'quality_score': 0.0,
            'maintainability_score': 0.0,
            'patterns_observed': [],
            'best_practices_followed': [],
            'areas_for_improvement': ['No code samples available for analysis'],
            'summary': 'No commits available for analysis in this period.'
        }

    def _get_empty_review_analysis(self) -> Dict:
        """Return empty review analysis (no reviews available)."""
        return {
            'thoroughness_score': 0.0,
            'helpfulness_score': 0.0,
            'review_patterns': [],
            'strengths': [],
            'areas_for_improvement': ['No code reviews available for analysis'],
            'summary': 'No code reviews available for analysis in this period.'
        }


def get_analyzer(provider: str, config) -> AIAnalyzer:
    """
    Factory function to get appropriate AI analyzer.

    Args:
        provider: Provider name ('gemini', 'claude', 'chatgpt', 'ollama', 'none')
        config: Configuration object with API keys

    Returns:
        AIAnalyzer instance

    Raises:
        ValueError: If provider is invalid or API key is missing
    """
    if provider == 'gemini':
        if not config.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY is required for Gemini provider. "
                "Get your free API key at: https://makersuite.google.com/app/apikey"
            )
        return GeminiAnalyzer(config.gemini_api_key, config.gemini_model)

    elif provider == 'claude':
        # TODO: Implement Claude analyzer
        raise NotImplementedError("Claude provider not yet implemented")

    elif provider == 'chatgpt':
        # TODO: Implement ChatGPT analyzer
        raise NotImplementedError("ChatGPT provider not yet implemented")

    elif provider == 'ollama':
        # TODO: Implement Ollama analyzer
        raise NotImplementedError("Ollama provider not yet implemented")

    elif provider == 'none':
        raise ValueError("AI analysis is disabled (provider='none')")

    else:
        raise ValueError(f"Unknown AI provider: {provider}")


def get_fallback_analysis() -> Dict:
    """Get fallback analysis when AI fails."""
    return {
        'code_quality': {
            'quality_score': 0.0,
            'maintainability_score': 0.0,
            'patterns_observed': [],
            'best_practices_followed': [],
            'areas_for_improvement': ['AI analysis unavailable'],
            'summary': 'AI analysis failed or unavailable.'
        },
        'review_quality': {
            'thoroughness_score': 0.0,
            'helpfulness_score': 0.0,
            'review_patterns': [],
            'strengths': [],
            'areas_for_improvement': ['AI analysis unavailable'],
            'summary': 'AI analysis failed or unavailable.'
        },
        'insights': {
            'strengths': ['Quantitative metrics available in report'],
            'improvements': ['Enable AI analysis for detailed insights'],
            'overall_summary': 'AI analysis was unavailable for this report. Please check configuration and try again.'
        }
    }
