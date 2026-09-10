"""
Data Processing Pipeline for MLOps.

Handles data preparation, cleaning, and feature engineering
for model training and evaluation.
"""
import asyncio
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from pathlib import Path
from enum import Enum
import hashlib

from app.core.logging import get_logger
from app.core.config import settings
from app.observability.metrics import Counter, Histogram

logger = get_logger(__name__)

# Data processing metrics
data_processing_jobs = Counter(
    "mlops_data_processing_jobs_total",
    "Total data processing jobs",
    ["job_type", "status"]
)

data_processing_duration = Histogram(
    "mlops_data_processing_seconds",
    "Time spent processing data"
)


class DataSource(Enum):
    """Types of data sources."""
    USER_INTERACTIONS = "user_interactions"
    FEEDBACK_DATA = "feedback_data"
    A_B_TEST_RESULTS = "ab_test_results"
    SAFETY_VIOLATIONS = "safety_violations"
    EXTERNAL_DATASETS = "external_datasets"


class ProcessingStage(Enum):
    """Data processing pipeline stages."""
    EXTRACTION = "extraction"
    CLEANING = "cleaning"
    FEATURE_ENGINEERING = "feature_engineering"
    VALIDATION = "validation"
    SPLITTING = "splitting"
    SERIALIZATION = "serialization"


@dataclass
class DataProcessingConfig:
    """Configuration for data processing pipeline."""
    source_tables: List[str]
    target_model_type: str
    training_window_days: int = 30
    min_samples_per_class: int = 100
    max_samples_per_class: int = 10000
    test_split_ratio: float = 0.2
    validation_split_ratio: float = 0.1
    feature_columns: List[str] = None
    label_column: str = "label"
    text_columns: List[str] = None
    categorical_columns: List[str] = None
    privacy_mode: bool = True
    quality_threshold: float = 0.8


class DataProcessor:
    """
    Data processing pipeline for preparing training datasets.
    
    Features:
    - Multi-source data extraction
    - Privacy-preserving data processing
    - Quality validation and filtering
    - Balanced dataset creation
    - Feature engineering
    - Train/validation/test splitting
    """
    
    def __init__(self):
        self.processing_jobs: Dict[str, Dict[str, Any]] = {}
        
    async def process_training_data(self,
                                  config: DataProcessingConfig,
                                  output_path: str) -> Dict[str, Any]:
        """Process data for model training."""
        
        job_id = f"process_{config.target_model_type}_{int(datetime.utcnow().timestamp())}"
        
        with data_processing_duration.time():
            try:
                logger.info(f"Starting data processing job {job_id}")
                
                # Stage 1: Extract raw data
                raw_data = await self._extract_data(config)
                logger.info(f"Extracted {len(raw_data)} raw records")
                
                # Stage 2: Clean and validate data
                clean_data = await self._clean_data(raw_data, config)
                logger.info(f"Cleaned data: {len(clean_data)} records remaining")
                
                # Stage 3: Feature engineering
                featured_data = await self._engineer_features(clean_data, config)
                logger.info(f"Feature engineering complete: {len(featured_data.columns)} features")
                
                # Stage 4: Data validation
                validated_data = await self._validate_data(featured_data, config)
                logger.info(f"Data validation complete: {len(validated_data)} valid records")
                
                # Stage 5: Split datasets
                splits = await self._split_data(validated_data, config)
                
                # Stage 6: Save processed datasets
                paths = await self._save_datasets(splits, output_path, config)
                
                result = {
                    "job_id": job_id,
                    "status": "completed",
                    "dataset_paths": paths,
                    "statistics": await self._generate_statistics(splits),
                    "processing_time": datetime.utcnow().isoformat()
                }
                
                data_processing_jobs.labels(
                    job_type="training_data",
                    status="completed"
                ).inc()
                
                logger.info(f"Data processing job {job_id} completed successfully")
                return result
                
            except Exception as e:
                logger.error(f"Data processing job {job_id} failed: {e}")
                data_processing_jobs.labels(
                    job_type="training_data", 
                    status="failed"
                ).inc()
                raise
    
    async def _extract_data(self, config: DataProcessingConfig) -> pd.DataFrame:
        """Extract raw data from various sources."""
        
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=config.training_window_days)
        
        all_data = []
        
        # Extract from each source table
        for table in config.source_tables:
            if table == "user_interactions":
                data = await self._extract_user_interactions(start_date, end_date, config)
            elif table == "feedback_data":
                data = await self._extract_feedback_data(start_date, end_date, config)
            elif table == "ab_test_results":
                data = await self._extract_ab_test_data(start_date, end_date, config)
            else:
                logger.warning(f"Unknown source table: {table}")
                continue
                
            if not data.empty:
                all_data.append(data)
        
        if not all_data:
            raise ValueError("No data extracted from any source")
        
        # Combine all data sources
        combined_data = pd.concat(all_data, ignore_index=True)
        
        return combined_data
    
    async def _extract_user_interactions(self, start_date: datetime, end_date: datetime, 
                                       config: DataProcessingConfig) -> pd.DataFrame:
        """Extract user interaction data."""
        # In production, this would query the interactions database
        # For demo, create simulated interaction data
        
        import random
        import numpy as np
        
        # Simulate user interactions
        interactions = []
        base_timestamp = start_date
        
        for i in range(1000):  # 1000 sample interactions
            timestamp = base_timestamp + timedelta(
                seconds=random.randint(0, int((end_date - start_date).total_seconds()))
            )
            
            # Simulate different types of queries
            query_types = ["fee_inquiry", "fraud_report", "balance_check", "loan_question", "general_help"]
            query_type = random.choice(query_types)
            
            # Simulate user messages and responses
            user_messages = {
                "fee_inquiry": "What are the fees for my checking account?",
                "fraud_report": "I see suspicious charges on my account",
                "balance_check": "What's my current account balance?",
                "loan_question": "What are your mortgage rates?",
                "general_help": "I need help with my account"
            }
            
            agent_responses = {
                "fee_inquiry": "Your checking account has a monthly maintenance fee of $12...",
                "fraud_report": "I understand your concern about suspicious charges...",
                "balance_check": "I can help you check your account balance...",
                "loan_question": "Our current mortgage rates start at 3.5%...",
                "general_help": "I'm here to help with your banking needs..."
            }
            
            interaction = {
                "session_id": f"session_{i:06d}",
                "timestamp": timestamp,
                "user_message": user_messages[query_type],
                "agent_response": agent_responses[query_type],
                "intent": query_type,
                "confidence": random.uniform(0.6, 0.95),
                "response_time": random.uniform(0.8, 3.0),
                "escalated": random.random() < 0.15,  # 15% escalation rate
                "user_rating": random.choices([1, 2, 3, 4, 5], weights=[0.1, 0.15, 0.25, 0.35, 0.15])[0],
                "model_type": config.target_model_type
            }
            
            interactions.append(interaction)
        
        return pd.DataFrame(interactions)
    
    async def _extract_feedback_data(self, start_date: datetime, end_date: datetime,
                                   config: DataProcessingConfig) -> pd.DataFrame:
        """Extract feedback data."""
        # In production, this would query feedback database
        # For demo, create simulated feedback data
        
        import random
        
        feedback_data = []
        base_timestamp = start_date
        
        for i in range(300):  # 300 feedback entries
            timestamp = base_timestamp + timedelta(
                seconds=random.randint(0, int((end_date - start_date).total_seconds()))
            )
            
            feedback = {
                "feedback_id": f"feedback_{i:06d}",
                "session_id": f"session_{random.randint(0, 999):06d}",
                "timestamp": timestamp,
                "feedback_type": random.choice(["user_rating", "escalation", "safety_violation"]),
                "rating": random.choices([1, 2, 3, 4, 5], weights=[0.1, 0.15, 0.25, 0.35, 0.15])[0],
                "sentiment": random.choice(["positive", "negative", "neutral"]),
                "escalated": random.random() < 0.2,
                "safety_violation": random.random() < 0.05,
                "model_type": config.target_model_type
            }
            
            feedback_data.append(feedback)
        
        return pd.DataFrame(feedback_data)
    
    async def _extract_ab_test_data(self, start_date: datetime, end_date: datetime,
                                  config: DataProcessingConfig) -> pd.DataFrame:
        """Extract A/B test results."""
        # In production, this would query experiment results
        # For demo, create simulated A/B test data
        
        import random
        
        ab_data = []
        base_timestamp = start_date
        
        for i in range(200):  # 200 A/B test entries
            timestamp = base_timestamp + timedelta(
                seconds=random.randint(0, int((end_date - start_date).total_seconds()))
            )
            
            variant = random.choice(["control", "treatment_a", "treatment_b"])
            
            ab_entry = {
                "experiment_id": f"exp_{random.randint(1, 5):03d}",
                "session_id": f"session_{random.randint(0, 999):06d}",
                "timestamp": timestamp,
                "variant": variant,
                "metric_name": random.choice(["user_satisfaction", "escalation_rate", "response_quality"]),
                "metric_value": random.uniform(0.1, 0.9),
                "conversion": random.random() < 0.3,
                "model_type": config.target_model_type
            }
            
            ab_data.append(ab_entry)
        
        return pd.DataFrame(ab_data)
    
    async def _clean_data(self, data: pd.DataFrame, config: DataProcessingConfig) -> pd.DataFrame:
        """Clean and preprocess raw data."""
        
        logger.info("Starting data cleaning")
        original_count = len(data)
        
        # Remove duplicates
        data = data.drop_duplicates()
        logger.info(f"Removed {original_count - len(data)} duplicate records")
        
        # Remove records with missing critical fields
        if 'user_message' in data.columns:
            data = data.dropna(subset=['user_message'])
        if 'agent_response' in data.columns:
            data = data.dropna(subset=['agent_response'])
        
        # Filter by quality threshold
        if 'confidence' in data.columns and config.quality_threshold:
            high_quality = data['confidence'] >= config.quality_threshold
            data = data[high_quality]
            logger.info(f"Filtered to {len(data)} high-quality records (confidence >= {config.quality_threshold})")
        
        # Privacy processing
        if config.privacy_mode:
            data = await self._apply_privacy_processing(data)
        
        # Remove outliers
        data = await self._remove_outliers(data)
        
        logger.info(f"Data cleaning complete: {len(data)} records remaining")
        return data
    
    async def _apply_privacy_processing(self, data: pd.DataFrame) -> pd.DataFrame:
        """Apply privacy-preserving transformations."""
        
        # Hash or remove PII
        if 'user_id' in data.columns:
            data['user_id_hash'] = data['user_id'].apply(
                lambda x: hashlib.sha256(str(x).encode()).hexdigest()[:16] if pd.notna(x) else None
            )
            data = data.drop('user_id', axis=1)
        
        # Anonymize text content (simplified)
        for col in ['user_message', 'agent_response']:
            if col in data.columns:
                # In production, would use proper PII detection/anonymization
                data[col] = data[col].str.replace(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN]', regex=True)
                data[col] = data[col].str.replace(r'\b\d{4}-\d{4}-\d{4}-\d{4}\b', '[CARD]', regex=True)
        
        return data
    
    async def _remove_outliers(self, data: pd.DataFrame) -> pd.DataFrame:
        """Remove statistical outliers."""
        
        numeric_columns = data.select_dtypes(include=['float64', 'int64']).columns
        
        for col in numeric_columns:
            if col in ['response_time', 'confidence']:
                Q1 = data[col].quantile(0.25)
                Q3 = data[col].quantile(0.75)
                IQR = Q3 - Q1
                lower_bound = Q1 - 1.5 * IQR
                upper_bound = Q3 + 1.5 * IQR
                
                outliers = (data[col] < lower_bound) | (data[col] > upper_bound)
                outlier_count = outliers.sum()
                
                if outlier_count > 0:
                    data = data[~outliers]
                    logger.info(f"Removed {outlier_count} outliers from {col}")
        
        return data
    
    async def _engineer_features(self, data: pd.DataFrame, config: DataProcessingConfig) -> pd.DataFrame:
        """Create features for model training."""
        
        logger.info("Starting feature engineering")
        
        # Text-based features
        if 'user_message' in data.columns:
            data['message_length'] = data['user_message'].str.len()
            data['message_word_count'] = data['user_message'].str.split().str.len()
            data['has_question_mark'] = data['user_message'].str.contains(r'\?', regex=True).astype(int)
            data['has_exclamation'] = data['user_message'].str.contains(r'!', regex=True).astype(int)
            
            # Sentiment indicators (simplified)
            data['has_negative_words'] = data['user_message'].str.contains(
                r'\b(problem|issue|error|wrong|bad|terrible|awful)\b', case=False, regex=True
            ).astype(int)
            
            data['has_positive_words'] = data['user_message'].str.contains(
                r'\b(good|great|excellent|perfect|thanks|thank you)\b', case=False, regex=True
            ).astype(int)
        
        # Response-based features
        if 'agent_response' in data.columns:
            data['response_length'] = data['agent_response'].str.len()
            data['response_word_count'] = data['agent_response'].str.split().str.len()
        
        # Time-based features
        if 'timestamp' in data.columns:
            data['timestamp'] = pd.to_datetime(data['timestamp'])
            data['hour_of_day'] = data['timestamp'].dt.hour
            data['day_of_week'] = data['timestamp'].dt.dayofweek
            data['is_weekend'] = (data['day_of_week'] >= 5).astype(int)
            data['is_business_hours'] = ((data['hour_of_day'] >= 9) & (data['hour_of_day'] <= 17)).astype(int)
        
        # Interaction features
        if 'response_time' in data.columns and 'confidence' in data.columns:
            data['confidence_time_ratio'] = data['confidence'] / (data['response_time'] + 0.1)
        
        # Categorical encoding
        categorical_cols = config.categorical_columns or []
        for col in categorical_cols:
            if col in data.columns:
                # One-hot encoding for categorical variables
                dummies = pd.get_dummies(data[col], prefix=col)
                data = pd.concat([data, dummies], axis=1)
        
        logger.info(f"Feature engineering complete: {len(data.columns)} total features")
        return data
    
    async def _validate_data(self, data: pd.DataFrame, config: DataProcessingConfig) -> pd.DataFrame:
        """Validate data quality and requirements."""
        
        logger.info("Starting data validation")
        
        # Check minimum sample requirements
        if config.label_column in data.columns:
            label_counts = data[config.label_column].value_counts()
            
            # Remove classes with insufficient samples
            valid_labels = label_counts[label_counts >= config.min_samples_per_class].index
            data = data[data[config.label_column].isin(valid_labels)]
            
            logger.info(f"Validation: {len(valid_labels)} classes meet minimum sample requirement")
        
        # Check for required columns
        required_columns = [config.label_column] if config.label_column in data.columns else []
        if config.feature_columns:
            required_columns.extend([col for col in config.feature_columns if col in data.columns])
        
        missing_columns = [col for col in required_columns if col not in data.columns]
        if missing_columns:
            logger.warning(f"Missing required columns: {missing_columns}")
        
        # Data quality checks
        quality_issues = []
        
        # Check for high null percentage
        null_percentages = data.isnull().mean()
        high_null_cols = null_percentages[null_percentages > 0.5].index.tolist()
        if high_null_cols:
            quality_issues.append(f"High null percentage in: {high_null_cols}")
        
        # Check for low variance features
        numeric_cols = data.select_dtypes(include=['float64', 'int64']).columns
        low_variance_cols = []
        for col in numeric_cols:
            if data[col].var() < 0.01:  # Very low variance
                low_variance_cols.append(col)
        
        if low_variance_cols:
            quality_issues.append(f"Low variance features: {low_variance_cols}")
            # Remove low variance columns
            data = data.drop(columns=low_variance_cols)
        
        if quality_issues:
            logger.warning(f"Data quality issues detected: {quality_issues}")
        
        logger.info(f"Data validation complete: {len(data)} records validated")
        return data
    
    async def _split_data(self, data: pd.DataFrame, config: DataProcessingConfig) -> Dict[str, pd.DataFrame]:
        """Split data into train/validation/test sets."""
        
        logger.info("Starting data splitting")
        
        # Stratified split if label column exists
        if config.label_column in data.columns:
            from sklearn.model_selection import train_test_split
            
            # First split: separate test set
            train_val, test = train_test_split(
                data,
                test_size=config.test_split_ratio,
                stratify=data[config.label_column],
                random_state=42
            )
            
            # Second split: separate train and validation
            val_size = config.validation_split_ratio / (1 - config.test_split_ratio)
            train, validation = train_test_split(
                train_val,
                test_size=val_size,
                stratify=train_val[config.label_column],
                random_state=42
            )
        else:
            # Random split without stratification
            from sklearn.model_selection import train_test_split
            
            train_val, test = train_test_split(
                data,
                test_size=config.test_split_ratio,
                random_state=42
            )
            
            val_size = config.validation_split_ratio / (1 - config.test_split_ratio)
            train, validation = train_test_split(
                train_val,
                test_size=val_size,
                random_state=42
            )
        
        # Balance training data if needed
        if config.label_column in data.columns:
            train = await self._balance_dataset(train, config)
        
        splits = {
            "train": train,
            "validation": validation,
            "test": test
        }
        
        logger.info(f"Data splitting complete - Train: {len(train)}, Val: {len(validation)}, Test: {len(test)}")
        return splits
    
    async def _balance_dataset(self, data: pd.DataFrame, config: DataProcessingConfig) -> pd.DataFrame:
        """Balance dataset by class."""
        
        label_counts = data[config.label_column].value_counts()
        max_samples = min(config.max_samples_per_class, label_counts.max())
        
        balanced_dfs = []
        
        for label in label_counts.index:
            label_data = data[data[config.label_column] == label]
            
            if len(label_data) > max_samples:
                # Downsample majority classes
                label_data = label_data.sample(n=max_samples, random_state=42)
            elif len(label_data) < config.min_samples_per_class:
                # Skip classes with too few samples (already filtered in validation)
                continue
            
            balanced_dfs.append(label_data)
        
        balanced_data = pd.concat(balanced_dfs, ignore_index=True)
        
        # Shuffle the balanced dataset
        balanced_data = balanced_data.sample(frac=1, random_state=42).reset_index(drop=True)
        
        logger.info(f"Dataset balanced: {len(balanced_data)} total samples")
        return balanced_data
    
    async def _save_datasets(self, splits: Dict[str, pd.DataFrame], 
                           output_path: str, config: DataProcessingConfig) -> Dict[str, str]:
        """Save processed datasets to files."""
        
        output_dir = Path(output_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        paths = {}
        
        for split_name, split_data in splits.items():
            # Save as both CSV and JSON formats
            csv_path = output_dir / f"{split_name}.csv"
            jsonl_path = output_dir / f"{split_name}.jsonl"
            
            # Save CSV
            split_data.to_csv(csv_path, index=False)
            
            # Save JSONL for ML frameworks
            split_data.to_json(jsonl_path, orient='records', lines=True)
            
            paths[f"{split_name}_csv"] = str(csv_path)
            paths[f"{split_name}_jsonl"] = str(jsonl_path)
        
        # Save processing metadata
        metadata = {
            "config": {
                "target_model_type": config.target_model_type,
                "training_window_days": config.training_window_days,
                "test_split_ratio": config.test_split_ratio,
                "validation_split_ratio": config.validation_split_ratio,
                "quality_threshold": config.quality_threshold
            },
            "processing_timestamp": datetime.utcnow().isoformat(),
            "dataset_statistics": await self._generate_statistics(splits)
        }
        
        metadata_path = output_dir / "metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2, default=str)
        
        paths["metadata"] = str(metadata_path)
        
        logger.info(f"Datasets saved to {output_dir}")
        return paths
    
    async def _generate_statistics(self, splits: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """Generate dataset statistics."""
        
        stats = {}
        
        for split_name, split_data in splits.items():
            split_stats = {
                "total_samples": len(split_data),
                "feature_count": len(split_data.columns),
                "numeric_features": len(split_data.select_dtypes(include=['float64', 'int64']).columns),
                "categorical_features": len(split_data.select_dtypes(include=['object']).columns),
                "null_percentage": split_data.isnull().mean().mean(),
            }
            
            # Class distribution if label column exists
            label_columns = [col for col in split_data.columns if 'label' in col.lower() or col in ['intent', 'escalated']]
            if label_columns:
                label_col = label_columns[0]
                class_dist = split_data[label_col].value_counts().to_dict()
                split_stats["class_distribution"] = class_dist
            
            # Numeric feature statistics
            numeric_cols = split_data.select_dtypes(include=['float64', 'int64']).columns
            if len(numeric_cols) > 0:
                split_stats["numeric_stats"] = split_data[numeric_cols].describe().to_dict()
            
            stats[split_name] = split_stats
        
        return stats


# Global processor instance
_processor_instance = None

async def get_data_processor() -> DataProcessor:
    """Get global data processor instance."""
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = DataProcessor()
    return _processor_instance