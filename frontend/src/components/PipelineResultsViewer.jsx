import React, { useState } from 'react';
import { 
  ChevronDown, ChevronUp, Clock, Target, Database, Zap,
  CheckCircle, XCircle, AlertTriangle, TrendingUp, TrendingDown,
  BarChart3, Layers, FileText, Tag, Search, Filter,
  Activity, Cpu, Timer, CheckSquare, AlertCircle, Info, Trash2
} from 'lucide-react';
import { extractionAPIv2 } from '../services/api';

/**
 * Comprehensive Pipeline Results Viewer
 * 
 * Shows complete pipeline execution details including:
 * - Execution metadata (timing, sources processed)
 * - Statistics (confidence breakdown, extraction methods)
 * - Per-source processing details
 * - Benefits extracted (with delete capability)
 * - Errors and warnings
 */
export default function PipelineResultsViewer({ results, rawDataId, onBenefitDeleted }) {
  const [expandedSections, setExpandedSections] = useState({
    summary: true,
    statistics: true,
    benefits: true,
    sourceDetails: false,
    metadata: false,
    errors: false,
  });
  
  const [expandedSources, setExpandedSources] = useState(new Set());
  const [expandedBenefits, setExpandedBenefits] = useState(new Set());
  const [deletingBenefits, setDeletingBenefits] = useState(new Set());
  const [deletedBenefits, setDeletedBenefits] = useState(new Set());
  
  if (!results || !results.all_benefits) {
    return (
      <div className="text-center py-12 text-gray-500">
        <AlertCircle size={48} className="mx-auto mb-4 text-gray-400" />
        <p>No pipeline results available</p>
      </div>
    );
  }
  
  // Helper: Safely convert pipeline_results to array
  const getPipelineResultsArray = () => {
    if (!results.pipeline_results) return [];
    if (Array.isArray(results.pipeline_results)) return results.pipeline_results;
    return Object.values(results.pipeline_results);
  };
  
  const pipelineResultsArray = getPipelineResultsArray();
  
  const toggleSection = (section) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
  };
  
  const toggleSource = (index) => {
    setExpandedSources(prev => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };
  
  const toggleBenefit = (id) => {
    setExpandedBenefits(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  
  // Handle benefit deletion
  const handleDeleteBenefit = async (benefitId, benefitTitle) => {
    if (!rawDataId) {
      alert('Cannot delete: Raw data ID is not available');
      return;
    }
    
    const confirmed = window.confirm(
      `Are you sure you want to delete this benefit?\n\n"${benefitTitle}"\n\nThis action cannot be undone.`
    );
    
    if (!confirmed) return;
    
    setDeletingBenefits(prev => new Set(prev).add(benefitId));
    
    try {
      await extractionAPIv2.deleteBenefit(rawDataId, benefitId);
      
      // Mark as deleted locally
      setDeletedBenefits(prev => new Set(prev).add(benefitId));
      
      // Notify parent component if callback provided
      if (onBenefitDeleted) {
        onBenefitDeleted(benefitId);
      }
      
    } catch (error) {
      console.error('Failed to delete benefit:', error);
      alert(`Failed to delete benefit: ${error.response?.data?.detail || error.message}`);
    } finally {
      setDeletingBenefits(prev => {
        const next = new Set(prev);
        next.delete(benefitId);
        return next;
      });
    }
  };
  
  // Aggregate statistics from all pipeline results
  const aggregateStats = () => {
    const stats = {
      totalBenefits: results.all_benefits?.length || 0,
      highConfidence: results.all_benefits?.filter(b => b.confidence_level === 'high').length || 0,
      mediumConfidence: results.all_benefits?.filter(b => b.confidence_level === 'medium').length || 0,
      lowConfidence: results.all_benefits?.filter(b => b.confidence_level === 'low').length || 0,
      llmExtracted: results.all_benefits?.filter(b => b.extraction_method === 'llm').length || 0,
      patternExtracted: results.all_benefits?.filter(b => b.extraction_method === 'pattern').length || 0,
      hybridExtracted: results.all_benefits?.filter(b => b.extraction_method === 'hybrid').length || 0,
    };
    
    // Get pipeline-level stats if available - handle both array and object structures
    const pipelineResults = results.pipeline_results;
    
    if (pipelineResults) {
      // Convert to array if it's an object
      const pipelineArray = Array.isArray(pipelineResults) 
        ? pipelineResults 
        : Object.values(pipelineResults);
      
      if (pipelineArray.length > 0) {
        stats.pipelinesRun = pipelineArray.length;
        stats.totalSources = pipelineArray.reduce((sum, p) => sum + (p?.statistics?.sources_total || 0), 0);
        stats.relevantSources = pipelineArray.reduce((sum, p) => sum + (p?.statistics?.sources_relevant || 0), 0);
        stats.processedSources = pipelineArray.reduce((sum, p) => sum + (p?.statistics?.sources_processed || 0), 0);
        stats.llmExtractions = pipelineArray.reduce((sum, p) => sum + (p?.statistics?.llm_extractions || 0), 0);
        stats.patternExtractions = pipelineArray.reduce((sum, p) => sum + (p?.statistics?.pattern_extractions || 0), 0);
        stats.totalDuration = pipelineArray.reduce((sum, p) => sum + (p?.timing?.duration_seconds || 0), 0);
      }
    }
    
    // Also check for quality_metrics at the top level
    if (results.quality_metrics) {
      stats.highConfidence = results.quality_metrics.high_confidence || stats.highConfidence;
      stats.mediumConfidence = results.quality_metrics.medium_confidence || stats.mediumConfidence;
      stats.lowConfidence = results.quality_metrics.low_confidence || stats.lowConfidence;
    }
    
    return stats;
  };
  
  const stats = aggregateStats();
  
  // Section Header Component
  const SectionHeader = ({ icon: Icon, title, badge, section, color = 'blue' }) => (
    <button
      onClick={() => toggleSection(section)}
      className="w-full flex items-center justify-between p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
    >
      <div className="flex items-center gap-3">
        <div className={`p-2 bg-${color}-100 rounded-lg`}>
          <Icon className={`text-${color}-600`} size={20} />
        </div>
        <span className="font-semibold text-gray-800">{title}</span>
        {badge !== undefined && (
          <span className={`px-2 py-0.5 bg-${color}-100 text-${color}-700 rounded-full text-sm font-medium`}>
            {badge}
          </span>
        )}
      </div>
      {expandedSections[section] ? <ChevronUp size={20} className="text-gray-400" /> : <ChevronDown size={20} className="text-gray-400" />}
    </button>
  );
  
  // Stat Card Component
  const StatCard = ({ icon: Icon, label, value, subtext, color = 'blue' }) => (
    <div className="bg-white border border-gray-200 rounded-lg p-4">
      <div className="flex items-center gap-3 mb-2">
        <div className={`p-2 bg-${color}-100 rounded-lg`}>
          <Icon className={`text-${color}-600`} size={18} />
        </div>
        <span className="text-sm text-gray-500">{label}</span>
      </div>
      <div className="text-2xl font-bold text-gray-800">{value}</div>
      {subtext && <div className="text-xs text-gray-500 mt-1">{subtext}</div>}
    </div>
  );
  
  // Confidence Badge
  const ConfidenceBadge = ({ level }) => {
    const colors = {
      high: 'bg-green-100 text-green-700',
      medium: 'bg-yellow-100 text-yellow-700',
      low: 'bg-red-100 text-red-700',
    };
    return (
      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${colors[level] || colors.low}`}>
        {level}
      </span>
    );
  };
  
  // Method Badge
  const MethodBadge = ({ method }) => {
    const colors = {
      llm: 'bg-purple-100 text-purple-700',
      pattern: 'bg-blue-100 text-blue-700',
      hybrid: 'bg-indigo-100 text-indigo-700',
    };
    const icons = {
      llm: <Cpu size={12} />,
      pattern: <Search size={12} />,
      hybrid: <Zap size={12} />,
    };
    return (
      <span className={`px-2 py-0.5 rounded-full text-xs font-medium flex items-center gap-1 ${colors[method] || colors.pattern}`}>
        {icons[method]}
        {method}
      </span>
    );
  };
  
  return (
    <div className="space-y-6">
      {/* SUMMARY SECTION */}
      <div className="space-y-3">
        <SectionHeader 
          icon={BarChart3} 
          title="Execution Summary" 
          badge={`${stats.totalBenefits} benefits`}
          section="summary"
          color="blue"
        />
        
        {expandedSections.summary && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-4 bg-gray-50 rounded-lg">
            <StatCard 
              icon={CheckCircle} 
              label="Total Benefits" 
              value={stats.totalBenefits}
              color="green"
            />
            <StatCard 
              icon={TrendingUp} 
              label="High Confidence" 
              value={stats.highConfidence}
              subtext={`${Math.round(stats.highConfidence / stats.totalBenefits * 100)}%`}
              color="green"
            />
            <StatCard 
              icon={Activity} 
              label="LLM Extracted" 
              value={stats.llmExtracted}
              subtext={`${stats.hybridExtracted} hybrid`}
              color="purple"
            />
            <StatCard 
              icon={Search} 
              label="Pattern Extracted" 
              value={stats.patternExtracted}
              color="blue"
            />
          </div>
        )}
      </div>
      
      {/* STATISTICS SECTION */}
      <div className="space-y-3">
        <SectionHeader 
          icon={Activity} 
          title="Processing Statistics" 
          section="statistics"
          color="indigo"
        />
        
        {expandedSections.statistics && (
          <div className="p-4 bg-gray-50 rounded-lg space-y-4">
            {/* Confidence Distribution */}
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                <Target size={16} className="text-indigo-600" />
                Confidence Distribution
              </h4>
              <div className="grid grid-cols-3 gap-3">
                <div className="bg-white p-3 rounded border border-green-200">
                  <div className="text-xs text-gray-500 mb-1">High Confidence</div>
                  <div className="text-2xl font-bold text-green-600">{stats.highConfidence}</div>
                  <div className="text-xs text-gray-400">
                    {stats.totalBenefits > 0 ? Math.round(stats.highConfidence / stats.totalBenefits * 100) : 0}%
                  </div>
                </div>
                <div className="bg-white p-3 rounded border border-yellow-200">
                  <div className="text-xs text-gray-500 mb-1">Medium Confidence</div>
                  <div className="text-2xl font-bold text-yellow-600">{stats.mediumConfidence}</div>
                  <div className="text-xs text-gray-400">
                    {stats.totalBenefits > 0 ? Math.round(stats.mediumConfidence / stats.totalBenefits * 100) : 0}%
                  </div>
                </div>
                <div className="bg-white p-3 rounded border border-red-200">
                  <div className="text-xs text-gray-500 mb-1">Low Confidence</div>
                  <div className="text-2xl font-bold text-red-600">{stats.lowConfidence}</div>
                  <div className="text-xs text-gray-400">
                    {stats.totalBenefits > 0 ? Math.round(stats.lowConfidence / stats.totalBenefits * 100) : 0}%
                  </div>
                </div>
              </div>
            </div>
            
            {/* Extraction Methods */}
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                <Zap size={16} className="text-indigo-600" />
                Extraction Methods
              </h4>
              <div className="grid grid-cols-3 gap-3">
                <div className="bg-white p-3 rounded border border-purple-200">
                  <div className="text-xs text-gray-500 mb-1 flex items-center gap-1">
                    <Cpu size={12} /> LLM
                  </div>
                  <div className="text-2xl font-bold text-purple-600">{stats.llmExtracted}</div>
                </div>
                <div className="bg-white p-3 rounded border border-blue-200">
                  <div className="text-xs text-gray-500 mb-1 flex items-center gap-1">
                    <Search size={12} /> Pattern
                  </div>
                  <div className="text-2xl font-bold text-blue-600">{stats.patternExtracted}</div>
                </div>
                <div className="bg-white p-3 rounded border border-indigo-200">
                  <div className="text-xs text-gray-500 mb-1 flex items-center gap-1">
                    <Zap size={12} /> Hybrid
                  </div>
                  <div className="text-2xl font-bold text-indigo-600">{stats.hybridExtracted}</div>
                </div>
              </div>
            </div>
            
            {/* Source Processing */}
            {stats.totalSources > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                  <Database size={16} className="text-indigo-600" />
                  Source Processing
                </h4>
                <div className="bg-white p-4 rounded border border-gray-200">
                  <div className="grid grid-cols-3 gap-4 text-sm">
                    <div>
                      <div className="text-gray-500">Total Sources</div>
                      <div className="text-lg font-semibold text-gray-800">{stats.totalSources}</div>
                    </div>
                    <div>
                      <div className="text-gray-500">Relevant</div>
                      <div className="text-lg font-semibold text-green-600">{stats.relevantSources}</div>
                      <div className="text-xs text-gray-400">
                        {Math.round(stats.relevantSources / stats.totalSources * 100)}% relevance
                      </div>
                    </div>
                    <div>
                      <div className="text-gray-500">Processed</div>
                      <div className="text-lg font-semibold text-blue-600">{stats.processedSources}</div>
                    </div>
                  </div>
                </div>
              </div>
            )}
            
            {/* Performance */}
            {stats.totalDuration > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                  <Timer size={16} className="text-indigo-600" />
                  Performance
                </h4>
                <div className="bg-white p-4 rounded border border-gray-200">
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <div className="text-gray-500">Total Duration</div>
                      <div className="text-lg font-semibold text-gray-800">
                        {stats.totalDuration.toFixed(2)}s
                      </div>
                    </div>
                    <div>
                      <div className="text-gray-500">Avg per Benefit</div>
                      <div className="text-lg font-semibold text-gray-800">
                        {(stats.totalDuration / stats.totalBenefits).toFixed(2)}s
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
      
      {/* BENEFITS SECTION */}
      <div className="space-y-3">
        <SectionHeader 
          icon={CheckSquare} 
          title="Extracted Benefits" 
          badge={stats.totalBenefits - deletedBenefits.size}
          section="benefits"
          color="green"
        />
        
        {expandedSections.benefits && (
          <div className="space-y-3">
            {results.all_benefits
              .filter(benefit => !deletedBenefits.has(benefit.benefit_id))
              .map((benefit, idx) => {
              const isExpanded = expandedBenefits.has(benefit.benefit_id);
              const isDeleting = deletingBenefits.has(benefit.benefit_id);
              
              return (
                <div key={benefit.benefit_id || idx} className={`bg-white border border-gray-200 rounded-lg overflow-hidden ${isDeleting ? 'opacity-50' : ''}`}>
                  {/* Benefit Header */}
                  <div className="flex items-start">
                    <button
                      onClick={() => toggleBenefit(benefit.benefit_id)}
                      className="flex-1 p-4 flex items-start justify-between hover:bg-gray-50 transition-colors text-left"
                    >
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <h4 className="font-semibold text-gray-800">{benefit.title}</h4>
                          <ConfidenceBadge level={benefit.confidence_level} />
                          <MethodBadge method={benefit.extraction_method} />
                        </div>
                        <p className="text-sm text-gray-600 line-clamp-2">{benefit.description}</p>
                        {benefit.value && (
                          <div className="mt-2 text-lg font-bold text-green-600">{benefit.value}</div>
                        )}
                      </div>
                      {isExpanded ? <ChevronUp size={20} className="text-gray-400 flex-shrink-0" /> : <ChevronDown size={20} className="text-gray-400 flex-shrink-0" />}
                    </button>
                    
                    {/* Delete Button */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteBenefit(benefit.benefit_id, benefit.title);
                      }}
                      disabled={isDeleting}
                      className="p-4 text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors border-l border-gray-200"
                      title="Delete this benefit"
                    >
                      {isDeleting ? (
                        <div className="w-5 h-5 border-2 border-red-300 border-t-red-600 rounded-full animate-spin" />
                      ) : (
                        <Trash2 size={20} />
                      )}
                    </button>
                  </div>
                  
                  {/* Benefit Details */}
                  {isExpanded && (
                    <div className="px-4 pb-4 border-t border-gray-100 bg-gray-50">
                      <div className="grid grid-cols-2 gap-4 mt-4">
                        {/* Left Column */}
                        <div className="space-y-3">
                          {benefit.conditions && benefit.conditions.length > 0 && (
                            <div>
                              <div className="text-xs font-semibold text-gray-500 mb-1 flex items-center gap-1">
                                <AlertTriangle size={12} /> Conditions
                              </div>
                              <ul className="text-xs text-gray-600 space-y-1">
                                {benefit.conditions.map((c, i) => (
                                  <li key={i} className="flex items-start gap-1">
                                    <span className="text-gray-400">•</span>
                                    {c}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                          
                          {benefit.merchants && benefit.merchants.length > 0 && (
                            <div>
                              <div className="text-xs font-semibold text-gray-500 mb-1">Merchants</div>
                              <div className="flex flex-wrap gap-1">
                                {benefit.merchants.map((m, i) => (
                                  <span key={i} className="px-2 py-0.5 bg-orange-100 text-orange-700 text-xs rounded">
                                    {m}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                          
                          {benefit.eligible_categories && benefit.eligible_categories.length > 0 && (
                            <div>
                              <div className="text-xs font-semibold text-gray-500 mb-1">Categories</div>
                              <div className="flex flex-wrap gap-1">
                                {benefit.eligible_categories.map((c, i) => (
                                  <span key={i} className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded">
                                    {c}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                        
                        {/* Right Column */}
                        <div className="space-y-3">
                          <div className="bg-white p-3 rounded border border-gray-200 text-xs">
                            <div className="grid grid-cols-2 gap-2">
                              <div>
                                <div className="text-gray-500">Confidence</div>
                                <div className="font-semibold">{Math.round(benefit.confidence * 100)}%</div>
                              </div>
                              <div>
                                <div className="text-gray-500">Method</div>
                                <div className="font-semibold capitalize">{benefit.extraction_method}</div>
                              </div>
                              {benefit.frequency && (
                                <div>
                                  <div className="text-gray-500">Frequency</div>
                                  <div className="font-semibold">{benefit.frequency}</div>
                                </div>
                              )}
                              {benefit.minimum_spend && (
                                <div>
                                  <div className="text-gray-500">Min Spend</div>
                                  <div className="font-semibold">{benefit.minimum_spend}</div>
                                </div>
                              )}
                            </div>
                          </div>
                          
                          {benefit.source_url && (
                            <div>
                              <div className="text-xs font-semibold text-gray-500 mb-1">Source</div>
                              <a 
                                href={benefit.source_url} 
                                target="_blank" 
                                rel="noopener noreferrer"
                                className="text-xs text-blue-600 hover:underline flex items-center gap-1"
                              >
                                {benefit.source_title || benefit.source_url}
                                <FileText size={12} />
                              </a>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
      
      {/* SOURCE DETAILS SECTION */}
      {pipelineResultsArray.length > 0 && (
        <div className="space-y-3">
          <SectionHeader 
            icon={Layers} 
            title="Source Processing Details" 
            badge={`${pipelineResultsArray.length} pipelines`}
            section="sourceDetails"
            color="blue"
          />
          
          {expandedSections.sourceDetails && (
            <div className="space-y-4">
              {pipelineResultsArray.map((pipelineResult, pIdx) => (
                <div key={pIdx} className="bg-gray-50 rounded-lg p-4">
                  <div className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
                    <Tag className="text-blue-600" size={16} />
                    {pipelineResult.pipeline_name} Pipeline
                    <span className="text-sm text-gray-500">
                      ({pipelineResult.source_results?.length || 0} sources)
                    </span>
                  </div>
                  
                  {pipelineResult.source_results && pipelineResult.source_results.map((source, sIdx) => {
                    const isExpanded = expandedSources.has(`${pIdx}-${sIdx}`);
                    
                    return (
                      <div key={sIdx} className="bg-white rounded border border-gray-200 mb-2 overflow-hidden">
                        <button
                          onClick={() => toggleSource(`${pIdx}-${sIdx}`)}
                          className="w-full p-3 flex items-center justify-between hover:bg-gray-50 transition-colors"
                        >
                          <div className="flex items-center gap-3 flex-1">
                            <div className={`w-2 h-2 rounded-full ${source.is_relevant ? 'bg-green-500' : 'bg-gray-300'}`} />
                            <div className="text-left">
                              <div className="text-sm font-medium text-gray-800 truncate">
                                {source.source_title}
                              </div>
                              <div className="text-xs text-gray-500">
                                Relevance: {Math.round(source.relevance_score * 100)}% | 
                                LLM: {source.llm_benefits_count} | 
                                Pattern: {source.pattern_benefits_count} | 
                                Merged: {source.merged_benefits_count}
                              </div>
                            </div>
                          </div>
                          {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                        </button>
                        
                        {isExpanded && (
                          <div className="px-3 pb-3 bg-gray-50 border-t border-gray-200">
                            <div className="grid grid-cols-3 gap-3 mt-3 text-xs">
                              <div>
                                <div className="text-gray-500 mb-1">LLM Duration</div>
                                <div className="font-semibold">{source.llm_duration_ms?.toFixed(0)}ms</div>
                              </div>
                              <div>
                                <div className="text-gray-500 mb-1">Benefits Found</div>
                                <div className="font-semibold">{source.merged_benefits_count}</div>
                              </div>
                              <div>
                                <div className="text-gray-500 mb-1">Source Index</div>
                                <div className="font-semibold">#{source.source_index}</div>
                              </div>
                            </div>
                            {source.llm_error && (
                              <div className="mt-2 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-700">
                                <AlertCircle size={12} className="inline mr-1" />
                                LLM Error: {source.llm_error}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      
      {/* METADATA SECTION */}
      {pipelineResultsArray.length > 0 && (
        <div className="space-y-3">
          <SectionHeader 
            icon={Info} 
            title="Execution Metadata" 
            section="metadata"
            color="gray"
          />
          
          {expandedSections.metadata && (
            <div className="p-4 bg-gray-50 rounded-lg">
              {pipelineResultsArray.map((pr, idx) => (
                <div key={idx} className="mb-4 last:mb-0">
                  <div className="text-sm font-semibold text-gray-700 mb-2">{pr.pipeline_name}</div>
                  <div className="bg-white p-3 rounded border border-gray-200 text-xs font-mono">
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                      <div><span className="text-gray-500">Pipeline:</span> {pr.pipeline_name}</div>
                      <div><span className="text-gray-500">Type:</span> {pr.benefit_type}</div>
                      <div><span className="text-gray-500">Success:</span> {pr.success ? '✅ Yes' : '❌ No'}</div>
                      <div><span className="text-gray-500">Benefits:</span> {pr.statistics?.total_found || 0}</div>
                      {pr.timing && (
                        <>
                          <div><span className="text-gray-500">Duration:</span> {pr.timing.duration_seconds?.toFixed(2)}s</div>
                          <div><span className="text-gray-500">Started:</span> {new Date(pr.timing.started_at).toLocaleTimeString()}</div>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      
      {/* ERRORS & WARNINGS */}
      {pipelineResultsArray.some(pr => pr.errors?.length > 0 || pr.warnings?.length > 0) && (
        <div className="space-y-3">
          <SectionHeader 
            icon={AlertCircle} 
            title="Errors & Warnings" 
            badge={pipelineResultsArray.reduce((sum, pr) => sum + (pr.errors?.length || 0) + (pr.warnings?.length || 0), 0)}
            section="errors"
            color="red"
          />
          
          {expandedSections.errors && (
            <div className="space-y-2">
              {pipelineResultsArray.map((pr, idx) => (
                <div key={idx}>
                  {pr.errors && pr.errors.length > 0 && (
                    <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                      <div className="text-sm font-semibold text-red-800 mb-2">
                        {pr.pipeline_name} - Errors
                      </div>
                      {pr.errors.map((err, i) => (
                        <div key={i} className="text-xs text-red-700">{err}</div>
                      ))}
                    </div>
                  )}
                  {pr.warnings && pr.warnings.length > 0 && (
                    <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
                      <div className="text-sm font-semibold text-yellow-800 mb-2">
                        {pr.pipeline_name} - Warnings
                      </div>
                      {pr.warnings.map((warn, i) => (
                        <div key={i} className="text-xs text-yellow-700">{warn}</div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
