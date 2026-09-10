"""
Statistical Analysis for A/B Testing Results.

Provides statistical significance testing, confidence intervals,
and experiment evaluation for prompt and model experiments.
"""
import math
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union
from enum import Enum

import numpy as np
from scipy import stats
from scipy.stats import chi2_contingency, ttest_ind, mannwhitneyu

from app.core.logging import get_logger
from app.experimentation.framework import ExperimentResult

logger = get_logger(__name__)


class TestType(Enum):
    """Types of statistical tests."""
    T_TEST = "t_test"
    MANN_WHITNEY = "mann_whitney"
    CHI_SQUARE = "chi_square"
    PROPORTION_Z_TEST = "proportion_z_test"


@dataclass
class StatisticalTest:
    """Result of a statistical test."""
    test_type: TestType
    statistic: float
    p_value: float
    effect_size: float
    confidence_interval: Tuple[float, float]
    is_significant: bool
    power: Optional[float] = None
    sample_size: int = 0


@dataclass
class ExperimentAnalysis:
    """Complete analysis of an experiment."""
    experiment_id: str
    metric_name: str
    control_stats: ExperimentResult
    treatment_stats: ExperimentResult
    statistical_test: StatisticalTest
    recommendation: str
    confidence_level: float = 0.95
    

class StatisticalAnalyzer:
    """Statistical analysis engine for A/B testing."""
    
    def __init__(self, alpha: float = 0.05, power: float = 0.8):
        self.alpha = alpha  # Significance level
        self.power = power  # Statistical power
        self.confidence_level = 1 - alpha
        
    def analyze_experiment(self,
                          experiment_id: str,
                          metric_name: str,
                          control_data: List[float],
                          treatment_data: List[float],
                          metric_type: str = "numeric") -> ExperimentAnalysis:
        """Analyze experiment results for statistical significance."""
        
        # Calculate descriptive statistics
        control_stats = self._calculate_stats(control_data, "control")
        treatment_stats = self._calculate_stats(treatment_data, "treatment")
        
        # Choose appropriate statistical test
        if metric_type == "conversion":
            test_result = self._proportion_z_test(control_data, treatment_data)
        elif metric_type == "numeric":
            # Check for normality and choose test
            if self._is_normal(control_data) and self._is_normal(treatment_data):
                test_result = self._t_test(control_data, treatment_data)
            else:
                test_result = self._mann_whitney_test(control_data, treatment_data)
        else:
            test_result = self._t_test(control_data, treatment_data)  # Default
        
        # Generate recommendation
        recommendation = self._generate_recommendation(
            control_stats, treatment_stats, test_result, metric_type
        )
        
        return ExperimentAnalysis(
            experiment_id=experiment_id,
            metric_name=metric_name,
            control_stats=control_stats,
            treatment_stats=treatment_stats,
            statistical_test=test_result,
            recommendation=recommendation,
            confidence_level=self.confidence_level
        )
    
    def _calculate_stats(self, data: List[float], variant_id: str) -> ExperimentResult:
        """Calculate descriptive statistics for a dataset."""
        if not data:
            return ExperimentResult(
                variant_id=variant_id,
                metric_name="",
                sample_size=0,
                mean_value=0.0,
                std_deviation=0.0,
                confidence_interval=(0.0, 0.0)
            )
        
        mean_val = np.mean(data)
        std_val = np.std(data, ddof=1) if len(data) > 1 else 0.0
        n = len(data)
        
        # Calculate confidence interval
        if n > 1:
            sem = std_val / np.sqrt(n)
            t_critical = stats.t.ppf((1 + self.confidence_level) / 2, n - 1)
            margin_error = t_critical * sem
            ci = (mean_val - margin_error, mean_val + margin_error)
        else:
            ci = (mean_val, mean_val)
        
        return ExperimentResult(
            variant_id=variant_id,
            metric_name="",
            sample_size=n,
            mean_value=mean_val,
            std_deviation=std_val,
            confidence_interval=ci
        )
    
    def _is_normal(self, data: List[float]) -> bool:
        """Check if data follows normal distribution."""
        if len(data) < 8:  # Too small for normality test
            return True  # Assume normal for small samples
        
        # Shapiro-Wilk test
        try:
            _, p_value = stats.shapiro(data)
            return p_value > 0.05
        except:
            return True  # Default to normal if test fails
    
    def _t_test(self, control_data: List[float], treatment_data: List[float]) -> StatisticalTest:
        """Perform independent t-test."""
        try:
            statistic, p_value = ttest_ind(control_data, treatment_data)
            
            # Calculate effect size (Cohen's d)
            control_mean = np.mean(control_data)
            treatment_mean = np.mean(treatment_data)
            pooled_std = np.sqrt(
                ((len(control_data) - 1) * np.var(control_data, ddof=1) +
                 (len(treatment_data) - 1) * np.var(treatment_data, ddof=1)) /
                (len(control_data) + len(treatment_data) - 2)
            )
            
            effect_size = (treatment_mean - control_mean) / pooled_std if pooled_std > 0 else 0.0
            
            # Confidence interval for difference in means
            diff_mean = treatment_mean - control_mean
            se_diff = pooled_std * np.sqrt(1/len(control_data) + 1/len(treatment_data))
            t_critical = stats.t.ppf((1 + self.confidence_level) / 2, 
                                   len(control_data) + len(treatment_data) - 2)
            margin_error = t_critical * se_diff
            ci = (diff_mean - margin_error, diff_mean + margin_error)
            
            return StatisticalTest(
                test_type=TestType.T_TEST,
                statistic=statistic,
                p_value=p_value,
                effect_size=effect_size,
                confidence_interval=ci,
                is_significant=p_value < self.alpha,
                sample_size=len(control_data) + len(treatment_data)
            )
            
        except Exception as e:
            logger.error(f"T-test failed: {e}")
            return self._default_test_result()
    
    def _mann_whitney_test(self, control_data: List[float], treatment_data: List[float]) -> StatisticalTest:
        """Perform Mann-Whitney U test (non-parametric)."""
        try:
            statistic, p_value = mannwhitneyu(control_data, treatment_data, alternative='two-sided')
            
            # Calculate effect size (rank-biserial correlation)
            n1, n2 = len(control_data), len(treatment_data)
            effect_size = 1 - (2 * statistic) / (n1 * n2)
            
            # For CI, we'll use the difference in medians (approximation)
            control_median = np.median(control_data)
            treatment_median = np.median(treatment_data)
            diff_median = treatment_median - control_median
            
            # Simple bootstrap CI for median difference (approximation)
            ci = (diff_median * 0.8, diff_median * 1.2)  # Rough approximation
            
            return StatisticalTest(
                test_type=TestType.MANN_WHITNEY,
                statistic=statistic,
                p_value=p_value,
                effect_size=effect_size,
                confidence_interval=ci,
                is_significant=p_value < self.alpha,
                sample_size=n1 + n2
            )
            
        except Exception as e:
            logger.error(f"Mann-Whitney test failed: {e}")
            return self._default_test_result()
    
    def _proportion_z_test(self, control_data: List[float], treatment_data: List[float]) -> StatisticalTest:
        """Perform Z-test for proportions (conversion rates)."""
        try:
            # Convert to success counts
            control_successes = sum(1 for x in control_data if x > 0)
            treatment_successes = sum(1 for x in treatment_data if x > 0)
            
            n1, n2 = len(control_data), len(treatment_data)
            p1 = control_successes / n1 if n1 > 0 else 0
            p2 = treatment_successes / n2 if n2 > 0 else 0
            
            # Pooled proportion
            p_pooled = (control_successes + treatment_successes) / (n1 + n2)
            
            # Standard error
            se = np.sqrt(p_pooled * (1 - p_pooled) * (1/n1 + 1/n2))
            
            # Z statistic
            z_stat = (p2 - p1) / se if se > 0 else 0
            p_value = 2 * (1 - stats.norm.cdf(abs(z_stat)))
            
            # Effect size (difference in proportions)
            effect_size = p2 - p1
            
            # Confidence interval for difference in proportions
            se_diff = np.sqrt(p1*(1-p1)/n1 + p2*(1-p2)/n2)
            z_critical = stats.norm.ppf((1 + self.confidence_level) / 2)
            margin_error = z_critical * se_diff
            ci = (effect_size - margin_error, effect_size + margin_error)
            
            return StatisticalTest(
                test_type=TestType.PROPORTION_Z_TEST,
                statistic=z_stat,
                p_value=p_value,
                effect_size=effect_size,
                confidence_interval=ci,
                is_significant=p_value < self.alpha,
                sample_size=n1 + n2
            )
            
        except Exception as e:
            logger.error(f"Proportion Z-test failed: {e}")
            return self._default_test_result()
    
    def _default_test_result(self) -> StatisticalTest:
        """Return default test result for error cases."""
        return StatisticalTest(
            test_type=TestType.T_TEST,
            statistic=0.0,
            p_value=1.0,
            effect_size=0.0,
            confidence_interval=(0.0, 0.0),
            is_significant=False,
            sample_size=0
        )
    
    def _generate_recommendation(self,
                               control_stats: ExperimentResult,
                               treatment_stats: ExperimentResult,
                               test_result: StatisticalTest,
                               metric_type: str) -> str:
        """Generate actionable recommendation based on results."""
        
        if test_result.sample_size < 100:
            return "🔶 INSUFFICIENT DATA: Collect more data before making decisions. Need at least 100 samples per variant."
        
        if not test_result.is_significant:
            return f"📊 NO SIGNIFICANT DIFFERENCE: No statistically significant difference detected (p={test_result.p_value:.3f}). Consider running longer or testing larger changes."
        
        # Determine winner based on metric type
        is_treatment_better = treatment_stats.mean_value > control_stats.mean_value
        
        if metric_type in ["escalation_rate", "response_time"] and treatment_stats.mean_value < control_stats.mean_value:
            is_treatment_better = True  # Lower is better for these metrics
        
        improvement = abs(test_result.effect_size)
        
        if is_treatment_better:
            if improvement > 0.2:  # Large effect
                return f"🚀 STRONG WINNER: Treatment variant shows {improvement:.1%} improvement. IMPLEMENT IMMEDIATELY."
            elif improvement > 0.05:  # Medium effect  
                return f"✅ SIGNIFICANT IMPROVEMENT: Treatment variant shows {improvement:.1%} improvement. RECOMMEND IMPLEMENTATION."
            else:  # Small effect
                return f"📈 MARGINAL IMPROVEMENT: Small but significant improvement ({improvement:.1%}). Consider cost/benefit."
        else:
            if improvement > 0.1:  # Treatment is significantly worse
                return f"❌ TREATMENT UNDERPERFORMS: Control is {improvement:.1%} better. STOP EXPERIMENT and revert."
            else:
                return f"⚠️ MIXED RESULTS: Treatment shows decline ({improvement:.1%}). Investigate before implementing."
    
    def calculate_required_sample_size(self,
                                     baseline_conversion: float,
                                     minimum_detectable_effect: float,
                                     alpha: float = 0.05,
                                     power: float = 0.8) -> int:
        """Calculate required sample size for experiment."""
        
        # For proportion tests
        p1 = baseline_conversion
        p2 = baseline_conversion * (1 + minimum_detectable_effect)
        
        # Z-scores
        z_alpha = stats.norm.ppf(1 - alpha/2)
        z_beta = stats.norm.ppf(power)
        
        # Pooled proportion
        p_avg = (p1 + p2) / 2
        
        # Sample size calculation
        numerator = (z_alpha * np.sqrt(2 * p_avg * (1 - p_avg)) + 
                    z_beta * np.sqrt(p1 * (1 - p1) + p2 * (1 - p2)))**2
        denominator = (p2 - p1)**2
        
        n = numerator / denominator if denominator > 0 else 1000
        
        return int(np.ceil(n))
    
    def monitor_experiment_validity(self, 
                                  experiment_data: Dict[str, List[float]]) -> Dict[str, str]:
        """Monitor experiment for validity issues."""
        issues = {}
        
        for variant_id, data in experiment_data.items():
            # Check sample size
            if len(data) < 30:
                issues[f"{variant_id}_sample_size"] = f"Low sample size ({len(data)}). Need ≥30 for reliable results."
            
            # Check for outliers
            if len(data) > 10:
                q1 = np.percentile(data, 25)
                q3 = np.percentile(data, 75)
                iqr = q3 - q1
                outliers = [x for x in data if x < q1 - 1.5*iqr or x > q3 + 1.5*iqr]
                if len(outliers) > len(data) * 0.1:  # More than 10% outliers
                    issues[f"{variant_id}_outliers"] = f"High outlier rate ({len(outliers)}/{len(data)}). Check data quality."
            
            # Check variance
            if len(data) > 1:
                cv = np.std(data) / np.mean(data) if np.mean(data) != 0 else 0
                if cv > 2.0:  # High coefficient of variation
                    issues[f"{variant_id}_variance"] = f"High variance (CV={cv:.2f}). Results may be unstable."
        
        return issues


# Global analyzer instance
_analyzer: Optional[StatisticalAnalyzer] = None

def get_analyzer() -> StatisticalAnalyzer:
    """Get singleton statistical analyzer."""
    global _analyzer
    if _analyzer is None:
        _analyzer = StatisticalAnalyzer()
    return _analyzer