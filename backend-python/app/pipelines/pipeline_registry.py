"""
Pipeline Registry

Central registry for managing and running benefit extraction pipelines.
Provides:
- Pipeline registration and discovery
- Running individual or all pipelines
- Aggregating results across pipelines
- Multi-level deduplication
- Pipeline status and statistics
"""

from typing import Dict, List, Type, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field
import asyncio
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

from .base_pipeline import BasePipeline, PipelineResult, ExtractedBenefit
from ..utils.deduplication import deduplicate_across_pipelines, DeduplicationStats

logger = logging.getLogger(__name__)


@dataclass
class AggregatedResults:
    """Results from running multiple pipelines."""
    raw_data_id: str
    pipelines_run: List[str] = field(default_factory=list)
    total_benefits: int = 0
    total_benefits_before_dedup: int = 0  # Track pre-dedup count
    benefits_by_type: Dict[str, int] = field(default_factory=dict)
    all_benefits: List[ExtractedBenefit] = field(default_factory=list)
    pipeline_results: Dict[str, PipelineResult] = field(default_factory=dict)
    
    # Quality metrics
    high_confidence_total: int = 0
    medium_confidence_total: int = 0
    low_confidence_total: int = 0
    
    # Deduplication stats
    deduplication_stats: Optional[Dict[str, Any]] = None
    
    # Timing
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    total_duration_seconds: float = 0.0
    
    # Errors
    failed_pipelines: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "raw_data_id": self.raw_data_id,
            "pipelines_run": self.pipelines_run,
            "total_benefits": self.total_benefits,
            "total_benefits_before_dedup": self.total_benefits_before_dedup,
            "benefits_by_type": self.benefits_by_type,
            "all_benefits": [b.to_dict() for b in self.all_benefits],
            "pipeline_results": {k: v.to_dict() for k, v in self.pipeline_results.items()},
            "quality_metrics": {
                "high_confidence": self.high_confidence_total,
                "medium_confidence": self.medium_confidence_total,
                "low_confidence": self.low_confidence_total,
            },
            "deduplication_stats": self.deduplication_stats,
            "timing": {
                "started_at": self.started_at.isoformat(),
                "completed_at": self.completed_at.isoformat() if self.completed_at else None,
                "total_duration_seconds": self.total_duration_seconds,
            },
            "failed_pipelines": self.failed_pipelines,
            "errors": self.errors,
        }


class PipelineRegistry:
    """
    Registry for managing benefit extraction pipelines.
    
    Usage:
        registry = PipelineRegistry()
        registry.register(CashbackPipeline)
        registry.register(LoungeAccessPipeline)
        
        # Run single pipeline
        result = await registry.run_pipeline('cashback', db, raw_data_id)
        
        # Run all pipelines
        results = await registry.run_all_pipelines(db, raw_data_id)
    """
    
    def __init__(self):
        self._pipelines: Dict[str, Type[BasePipeline]] = {}
        self._instances: Dict[str, BasePipeline] = {}
    
    def register(self, pipeline_class: Type[BasePipeline]):
        """Register a pipeline class."""
        name = pipeline_class.name
        if name in self._pipelines:
            logger.warning(f"Overwriting existing pipeline '{name}'")
        self._pipelines[name] = pipeline_class
        logger.info(f"Registered pipeline: {name} ({pipeline_class.benefit_type})")
    
    def unregister(self, name: str):
        """Unregister a pipeline."""
        if name in self._pipelines:
            del self._pipelines[name]
            if name in self._instances:
                del self._instances[name]
    
    def get_pipeline(self, name: str, db: AsyncIOMotorDatabase) -> Optional[BasePipeline]:
        """Get a pipeline instance by name."""
        if name not in self._pipelines:
            return None
        
        # Create instance if not cached
        cache_key = f"{name}_{id(db)}"
        if cache_key not in self._instances:
            self._instances[cache_key] = self._pipelines[name](db)
        
        return self._instances[cache_key]
    
    def list_pipelines(self) -> List[Dict[str, str]]:
        """List all registered pipelines."""
        return [
            {
                "name": cls.name,
                "benefit_type": cls.benefit_type,
                "description": cls.description,
                "version": cls.version,
            }
            for cls in self._pipelines.values()
        ]
    
    def get_pipeline_info(self, name: str) -> Optional[Dict[str, Any]]:
        """Get detailed info about a specific pipeline."""
        if name not in self._pipelines:
            return None
        
        cls = self._pipelines[name]
        return {
            "name": cls.name,
            "benefit_type": cls.benefit_type,
            "description": cls.description,
            "version": cls.version,
            "keywords": cls.keywords,
            "patterns": list(cls.patterns.keys()),
            "url_patterns": getattr(cls, 'url_patterns', []),
            "llm_enabled": cls.llm_enabled,
        }
    
    async def _build_smart_source_mapping(
        self,
        db: AsyncIOMotorDatabase,
        raw_data_id: str,
        pipeline_names: List[str],
        source_indices: List[int]
    ) -> Dict[str, List[int]]:
        """
        Build a mapping of which pipelines should process which sources.
        
        Logic:
        1. For each source, check which pipelines match based on URL/title
        2. If a source has specific matches, only those pipelines process it
        3. If a source has NO matches, all selected pipelines process it (fallback)
        
        Args:
            db: Database connection
            raw_data_id: ID of raw data
            pipeline_names: List of pipeline names to consider
            source_indices: List of source indices to assign
            
        Returns:
            Dict mapping pipeline_name -> list of source indices to process
        """
        # Load raw data to get source URLs/titles
        collection = db.approved_raw_data
        raw_data = await collection.find_one({"saved_id": raw_data_id})
        
        if not raw_data:
            # Fallback: all pipelines get all sources
            return {name: source_indices for name in pipeline_names}
        
        sources = raw_data.get('sources', [])
        
        # Initialize mapping
        pipeline_source_map: Dict[str, List[int]] = {name: [] for name in pipeline_names}
        
        for idx in source_indices:
            if idx < 0 or idx >= len(sources):
                continue
                
            source = sources[idx]
            url = (source.get('url') or '').lower()
            title = (source.get('title') or '').lower()
            
            # Find which pipelines match this source
            matching_pipelines = []
            for name in pipeline_names:
                pipeline = self.get_pipeline(name, db)
                if pipeline and pipeline.is_relevant_for_source(url, title):
                    matching_pipelines.append(name)
            
            if matching_pipelines:
                # Only matched pipelines process this source
                for name in matching_pipelines:
                    pipeline_source_map[name].append(idx)
                logger.info(f"Source {idx} ({url[:50]}...) -> matched pipelines: {matching_pipelines}")
            else:
                # No match - all pipelines process this source (fallback)
                for name in pipeline_names:
                    pipeline_source_map[name].append(idx)
                logger.info(f"Source {idx} ({url[:50]}...) -> no match, using all pipelines")
        
        return pipeline_source_map
    
    async def run_pipeline(
        self, 
        name: str, 
        db: AsyncIOMotorDatabase, 
        raw_data_id: str,
        save_results: bool = True,
        source_indices: Optional[List[int]] = None
    ) -> Optional[PipelineResult]:
        """
        Run a specific pipeline on raw data.
        
        Args:
            name: Pipeline name
            db: MongoDB database connection
            raw_data_id: ID of approved raw data
            save_results: Whether to save results to MongoDB
            source_indices: Specific source indices to process (None = all)
            
        Returns:
            PipelineResult or None if pipeline not found
        """
        pipeline = self.get_pipeline(name, db)
        if not pipeline:
            return None
        
        result = await pipeline.run(raw_data_id, source_indices=source_indices)
        
        if save_results and result.success:
            await pipeline.save_results(raw_data_id, result)
        
        return result
    
    async def run_all_pipelines(
        self,
        db: AsyncIOMotorDatabase,
        raw_data_id: str,
        save_results: bool = True,
        parallel: bool = True,
        pipeline_names: Optional[List[str]] = None,
        source_indices: Optional[List[int]] = None,
        smart_matching: bool = True
    ) -> AggregatedResults:
        """
        Run all (or selected) pipelines on raw data with multi-level deduplication.
        
        Smart Matching:
        - If enabled, only runs pipelines on sources where the URL/title matches
        - E.g., movie pipeline only runs on sources with 'movie' or 'cinema' in URL
        - Sources with no specific match run all selected pipelines (fallback)
        
        Deduplication levels:
        - Level 1: Within each source (LLM + Pattern) - handled by each pipeline
        - Level 2: Across sources within pipeline - handled by each pipeline
        - Level 3: Across all pipelines - handled here after aggregation
        
        Args:
            db: MongoDB database connection
            raw_data_id: ID of approved raw data
            save_results: Whether to save results to MongoDB
            parallel: Run pipelines in parallel (faster) or sequential
            pipeline_names: Specific pipelines to run (None = all)
            source_indices: Specific source indices to process (None = all)
            smart_matching: Use URL-based pipeline-source matching to reduce LLM calls
            
        Returns:
            AggregatedResults with combined and deduplicated results from all pipelines
        """
        aggregated = AggregatedResults(raw_data_id=raw_data_id)
        
        # Determine which pipelines to run
        names_to_run = pipeline_names or list(self._pipelines.keys())
        
        logger.info(f"Running {len(names_to_run)} pipelines: {names_to_run}")
        if source_indices:
            logger.info(f"Filtering to source indices: {source_indices}")
        
        # Smart matching: Build pipeline-source assignments
        if smart_matching and source_indices:
            pipeline_source_map = await self._build_smart_source_mapping(
                db, raw_data_id, names_to_run, source_indices
            )
            logger.info(f"Smart matching assignments: {pipeline_source_map}")
        else:
            # No smart matching - all pipelines get all sources
            pipeline_source_map = {name: source_indices for name in names_to_run}
        
        if parallel:
            # Run all pipelines in parallel with their assigned sources
            tasks = []
            task_names = []
            for name in names_to_run:
                assigned_sources = pipeline_source_map.get(name)
                # None means "all sources", empty list [] means "no sources"
                if assigned_sources is None or len(assigned_sources) > 0:
                    tasks.append(
                        self.run_pipeline(name, db, raw_data_id, save_results, assigned_sources)
                    )
                    task_names.append(name)
                else:
                    logger.info(f"[{name}] Skipping - no relevant sources")
            
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for name, result in zip(task_names, results):
                    if isinstance(result, Exception):
                        aggregated.failed_pipelines.append(name)
                        aggregated.errors.append(f"{name}: {str(result)}")
                        logger.error(f"Pipeline {name} failed: {result}")
                    elif result:
                        self._add_to_aggregated(aggregated, name, result)
        else:
            # Run sequentially with assigned sources
            for name in names_to_run:
                assigned_sources = pipeline_source_map.get(name)
                # None means "all sources", empty list [] means "no sources"
                if assigned_sources is not None and len(assigned_sources) == 0:
                    logger.info(f"[{name}] Skipping - no relevant sources")
                    continue
                    
                try:
                    result = await self.run_pipeline(name, db, raw_data_id, save_results, assigned_sources)
                    if result:
                        self._add_to_aggregated(aggregated, name, result)
                except Exception as e:
                    aggregated.failed_pipelines.append(name)
                    aggregated.errors.append(f"{name}: {str(e)}")
                    logger.error(f"Pipeline {name} failed: {e}")
        
        # Store pre-dedup count
        aggregated.total_benefits_before_dedup = len(aggregated.all_benefits)
        logger.info(f"Total benefits before Level 3 dedup: {aggregated.total_benefits_before_dedup}")
        
        # Apply Level 3 deduplication (across all pipelines)
        if aggregated.all_benefits:
            benefits_dicts = [b.to_dict() for b in aggregated.all_benefits]
            deduped_dicts, dedup_stats = deduplicate_across_pipelines(benefits_dicts)
            
            logger.info(f"Level 3 dedup: {dedup_stats.input_count} -> {dedup_stats.output_count} "
                       f"({dedup_stats.duplicates_removed} removed)")
            
            # Convert back to ExtractedBenefit objects
            from .base_pipeline import ConfidenceLevel
            deduped_benefits = []
            for d in deduped_dicts:
                try:
                    # Handle confidence_level - could be string or enum
                    conf_level = d.get('confidence_level', 'medium')
                    if isinstance(conf_level, str):
                        conf_level = ConfidenceLevel(conf_level)
                    
                    benefit = ExtractedBenefit(
                        benefit_id=d.get('benefit_id', ''),
                        benefit_type=d.get('benefit_type', ''),
                        title=d.get('title', ''),
                        description=d.get('description', ''),
                        value=d.get('value'),
                        value_numeric=d.get('value_numeric'),
                        value_unit=d.get('value_unit'),
                        conditions=d.get('conditions', []),
                        limitations=d.get('limitations', []),
                        merchants=d.get('merchants', []),
                        partners=d.get('partners', []),
                        eligible_categories=d.get('eligible_categories', []),
                        minimum_spend=d.get('minimum_spend'),
                        maximum_benefit=d.get('maximum_benefit'),
                        frequency=d.get('frequency'),
                        validity_period=d.get('validity_period'),
                        source_url=d.get('source_url', ''),
                        source_title=d.get('source_title', ''),
                        source_index=d.get('source_index', 0),
                        extraction_method=d.get('extraction_method', 'unknown'),
                        confidence=d.get('confidence', 0.5),
                        confidence_level=conf_level,
                        pipeline_version=d.get('pipeline_version', ''),
                    )
                    deduped_benefits.append(benefit)
                except Exception as e:
                    logger.error(f"Failed to convert dict to benefit: {e}")
            
            aggregated.all_benefits = deduped_benefits
            aggregated.total_benefits = len(deduped_benefits)
            
            # Update deduplication stats
            aggregated.deduplication_stats = {
                "level3_input": dedup_stats.input_count,
                "level3_output": dedup_stats.output_count,
                "level3_removed": dedup_stats.duplicates_removed,
                "level3_merged": dedup_stats.merged_count,
                "reduction_percentage": dedup_stats.reduction_percentage,
            }
            
            # Recalculate confidence counts after dedup
            aggregated.high_confidence_total = sum(
                1 for b in aggregated.all_benefits 
                if b.confidence_level == ConfidenceLevel.HIGH
            )
            aggregated.medium_confidence_total = sum(
                1 for b in aggregated.all_benefits 
                if b.confidence_level == ConfidenceLevel.MEDIUM
            )
            aggregated.low_confidence_total = sum(
                1 for b in aggregated.all_benefits 
                if b.confidence_level == ConfidenceLevel.LOW
            )
            
            # Recalculate benefits by type
            aggregated.benefits_by_type = {}
            for b in aggregated.all_benefits:
                bt = b.benefit_type
                if bt not in aggregated.benefits_by_type:
                    aggregated.benefits_by_type[bt] = 0
                aggregated.benefits_by_type[bt] += 1
        
        # Finalize
        aggregated.completed_at = datetime.utcnow()
        aggregated.total_duration_seconds = (
            aggregated.completed_at - aggregated.started_at
        ).total_seconds()
        
        logger.info(f"Pipeline execution complete: {aggregated.total_benefits} benefits "
                   f"(from {aggregated.total_benefits_before_dedup} before dedup)")
        
        # Save aggregated results
        if save_results:
            await self._save_aggregated_results(db, aggregated)
        
        return aggregated
    
    def _add_to_aggregated(
        self, 
        aggregated: AggregatedResults, 
        pipeline_name: str, 
        result: PipelineResult
    ):
        """Add pipeline result to aggregated results."""
        aggregated.pipelines_run.append(pipeline_name)
        aggregated.pipeline_results[pipeline_name] = result
        
        # Add benefits
        aggregated.all_benefits.extend(result.benefits)
        aggregated.total_benefits += result.total_found
        
        # Update by-type count
        if result.benefit_type not in aggregated.benefits_by_type:
            aggregated.benefits_by_type[result.benefit_type] = 0
        aggregated.benefits_by_type[result.benefit_type] += result.total_found
        
        # Update confidence counts
        aggregated.high_confidence_total += result.high_confidence_count
        aggregated.medium_confidence_total += result.medium_confidence_count
        aggregated.low_confidence_total += result.low_confidence_count
        
        # Add errors/warnings
        aggregated.errors.extend([f"{pipeline_name}: {e}" for e in result.errors])
    
    async def _save_aggregated_results(
        self, 
        db: AsyncIOMotorDatabase, 
        aggregated: AggregatedResults
    ):
        """Save aggregated results to MongoDB."""
        collection = db.pipeline_aggregated_results
        
        doc = {
            "raw_data_id": aggregated.raw_data_id,
            "result": aggregated.to_dict(),
            "created_at": datetime.utcnow(),
        }
        
        await collection.update_one(
            {"raw_data_id": aggregated.raw_data_id},
            {"$set": doc},
            upsert=True
        )
    
    async def get_pipeline_results(
        self, 
        db: AsyncIOMotorDatabase, 
        raw_data_id: str,
        pipeline_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get stored pipeline results for raw data."""
        collection = db.pipeline_results
        
        query = {"raw_data_id": raw_data_id}
        if pipeline_name:
            query["pipeline_name"] = pipeline_name
        
        cursor = collection.find(query).sort("created_at", -1)
        results = await cursor.to_list(length=100)
        
        for r in results:
            r['_id'] = str(r['_id'])
        
        return results
    
    async def get_aggregated_results(
        self, 
        db: AsyncIOMotorDatabase, 
        raw_data_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get stored aggregated results for raw data."""
        collection = db.pipeline_aggregated_results
        
        result = await collection.find_one({"raw_data_id": raw_data_id})
        if result:
            result['_id'] = str(result['_id'])
        
        return result


# Global registry instance
pipeline_registry = PipelineRegistry()
