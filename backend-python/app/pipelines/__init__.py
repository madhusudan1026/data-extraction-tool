"""
Benefit Extraction Pipelines

Individual data engineering pipelines for extracting specific benefit types
from approved raw data stored in MongoDB.

Architecture:
- BasePipeline: Abstract base class with common functionality
- BenefitPipelineRegistry: Manages all registered pipelines
- Individual pipelines: One per benefit type (cashback, lounge, rewards, etc.)

Usage:
    from app.pipelines import pipeline_registry
    
    # Run a specific pipeline
    results = await pipeline_registry.run_pipeline('cashback', raw_data_id)
    
    # Run all pipelines
    all_results = await pipeline_registry.run_all_pipelines(raw_data_id)
"""

from .base_pipeline import BasePipeline, PipelineResult, ExtractedBenefit
from .pipeline_registry import PipelineRegistry, pipeline_registry

# Import individual pipelines to register them
from .cashback_pipeline import CashbackPipeline
from .lounge_access_pipeline import LoungeAccessPipeline
from .rewards_points_pipeline import RewardsPointsPipeline
from .travel_benefits_pipeline import TravelBenefitsPipeline
from .dining_pipeline import DiningPipeline
from .insurance_pipeline import InsurancePipeline
from .fee_waiver_pipeline import FeeWaiverPipeline
from .lifestyle_pipeline import LifestylePipeline
from .golf_pipeline import GolfPipeline
from .movie_pipeline import MoviePipeline

__all__ = [
    'BasePipeline',
    'PipelineResult', 
    'ExtractedBenefit',
    'PipelineRegistry',
    'pipeline_registry',
    'CashbackPipeline',
    'LoungeAccessPipeline',
    'RewardsPointsPipeline',
    'TravelBenefitsPipeline',
    'DiningPipeline',
    'InsurancePipeline',
    'FeeWaiverPipeline',
    'LifestylePipeline',
    'GolfPipeline',
    'MoviePipeline',
]
