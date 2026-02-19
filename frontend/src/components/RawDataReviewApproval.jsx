import React, { useState, useEffect } from 'react';
import { 
  FileText, Globe, File, Clock, Link, Tag, Search,
  CheckCircle, XCircle, Eye, EyeOff, ChevronDown, ChevronUp,
  Database, Save, Filter, ExternalLink, Hash, AlertTriangle,
  Loader2, Check, X, RefreshCw, Download, Trash2
} from 'lucide-react';

// Source type icons
const sourceTypeConfig = {
  web: { icon: Globe, color: 'text-blue-600', bg: 'bg-blue-100', label: 'Web Page' },
  pdf: { icon: File, color: 'text-red-600', bg: 'bg-red-100', label: 'PDF Document' },
  api: { icon: Database, color: 'text-purple-600', bg: 'bg-purple-100', label: 'API' },
};

// Individual Source Card Component
function SourceCard({ 
  source, 
  index, 
  isExpanded, 
  onToggleExpand, 
  isSelected, 
  onToggleSelect,
  keywords 
}) {
  const config = sourceTypeConfig[source.source_type] || sourceTypeConfig.web;
  const Icon = config.icon;
  
  // Calculate keyword matches in this source
  const keywordMatches = keywords.filter(kw => 
    source.cleaned_content?.toLowerCase().includes(kw.toLowerCase())
  );

  // Detect patterns in content
  const hasNumbers = /\d+/.test(source.cleaned_content || '');
  const hasCurrency = /aed|usd|eur|\$|£|€/i.test(source.cleaned_content || '');
  const hasPercentage = /\d+%/.test(source.cleaned_content || '');

  return (
    <div className={`border rounded-lg mb-4 overflow-hidden transition-all ${
      isSelected 
        ? 'border-green-400 bg-green-50' 
        : 'border-gray-200 bg-white'
    }`}>
      {/* Header */}
      <div className="p-4 flex items-start gap-3">
        {/* Selection checkbox */}
        <div className="pt-1">
          <input
            type="checkbox"
            checked={isSelected}
            onChange={() => onToggleSelect(index)}
            className="w-5 h-5 rounded border-gray-300 text-green-600 focus:ring-green-500"
          />
        </div>

        {/* Source type icon */}
        <div className={`p-2 rounded-lg ${config.bg} flex-shrink-0`}>
          <Icon className={config.color} size={20} />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`px-2 py-0.5 text-xs rounded ${config.bg} ${config.color}`}>
              {config.label}
            </span>
            {source.depth > 0 && (
              <span className="px-2 py-0.5 text-xs rounded bg-gray-100 text-gray-600">
                Depth: {source.depth}
              </span>
            )}
            {source.fetch_error && (
              <span className="px-2 py-0.5 text-xs rounded bg-red-100 text-red-600">
                Error
              </span>
            )}
          </div>
          
          {/* URL */}
          <a 
            href={source.url} 
            target="_blank" 
            rel="noopener noreferrer"
            className="text-sm text-blue-600 hover:text-blue-800 hover:underline block mt-1 truncate"
          >
            {source.url}
          </a>

          {/* Title if available */}
          {source.title && (
            <p className="text-sm font-medium text-gray-800 mt-1 truncate">
              {source.title}
            </p>
          )}

          {/* Metadata row */}
          <div className="flex flex-wrap gap-3 mt-2 text-xs text-gray-500">
            <span className="flex items-center gap-1">
              <FileText size={12} />
              {source.cleaned_content_length?.toLocaleString() || 0} chars
            </span>
            <span className="flex items-center gap-1">
              <Clock size={12} />
              {source.fetch_timestamp ? new Date(source.fetch_timestamp).toLocaleString() : 'N/A'}
            </span>
            <span className="flex items-center gap-1">
              <Tag size={12} />
              {keywordMatches.length} keywords matched
            </span>
          </div>

          {/* Pattern indicators */}
          <div className="flex gap-2 mt-2">
            {hasCurrency && (
              <span className="px-2 py-0.5 text-xs bg-green-100 text-green-700 rounded">
                💰 Has Currency
              </span>
            )}
            {hasPercentage && (
              <span className="px-2 py-0.5 text-xs bg-blue-100 text-blue-700 rounded">
                📊 Has Percentages
              </span>
            )}
            {keywordMatches.length > 5 && (
              <span className="px-2 py-0.5 text-xs bg-purple-100 text-purple-700 rounded">
                ⭐ High Relevance
              </span>
            )}
          </div>

          {/* Parent URL */}
          {source.parent_url && (
            <div className="mt-2 text-xs text-gray-500 flex items-center gap-1">
              <Link size={12} />
              Parent: <span className="text-gray-700 truncate">{source.parent_url}</span>
            </div>
          )}
        </div>

        {/* Expand/Collapse button */}
        <button
          onClick={() => onToggleExpand(index)}
          className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded"
        >
          {isExpanded ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
        </button>
      </div>

      {/* Expanded content */}
      {isExpanded && (
        <div className="border-t bg-gray-50 p-4">
          {/* Keyword matches */}
          {keywordMatches.length > 0 && (
            <div className="mb-4">
              <h4 className="text-sm font-medium text-gray-700 mb-2">Matched Keywords:</h4>
              <div className="flex flex-wrap gap-1">
                {keywordMatches.map((kw, i) => (
                  <span key={i} className="px-2 py-0.5 bg-yellow-100 text-yellow-800 text-xs rounded">
                    {kw}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Raw content preview */}
          <div>
            <h4 className="text-sm font-medium text-gray-700 mb-2">Content Preview:</h4>
            <div className="bg-white border rounded p-3 max-h-96 overflow-y-auto">
              <pre className="text-xs text-gray-700 whitespace-pre-wrap font-mono">
                {source.cleaned_content?.substring(0, 5000) || 'No content available'}
                {source.cleaned_content?.length > 5000 && (
                  <span className="text-gray-400">
                    {'\n\n... [Content truncated. Full length: ' + source.cleaned_content.length.toLocaleString() + ' characters]'}
                  </span>
                )}
              </pre>
            </div>
          </div>

          {/* Error message if any */}
          {source.fetch_error && (
            <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded">
              <p className="text-sm text-red-700">
                <AlertTriangle className="inline mr-1" size={14} />
                Error: {source.fetch_error}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Main Raw Data Review Component
function RawDataReviewApproval({ 
  extractionData, 
  onApprove, 
  onCancel,
  keywords = []
}) {
  const [sources, setSources] = useState([]);
  const [selectedSources, setSelectedSources] = useState(new Set());
  const [expandedSources, setExpandedSources] = useState(new Set());
  const [saving, setSaving] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState('all');
  const [showSelectedOnly, setShowSelectedOnly] = useState(false);

  // Initialize sources from extraction data
  useEffect(() => {
    if (extractionData?.sources) {
      setSources(extractionData.sources);
      // Auto-select sources without errors
      const validSources = new Set(
        extractionData.sources
          .map((s, i) => (!s.fetch_error && s.cleaned_content_length > 100 ? i : null))
          .filter(i => i !== null)
      );
      setSelectedSources(validSources);
    }
  }, [extractionData]);

  // Filter sources
  const filteredSources = sources.filter((source, index) => {
    // Search filter
    const matchesSearch = !searchQuery || 
      source.url.toLowerCase().includes(searchQuery.toLowerCase()) ||
      source.title?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      source.cleaned_content?.toLowerCase().includes(searchQuery.toLowerCase());
    
    // Type filter
    const matchesType = filterType === 'all' || source.source_type === filterType;
    
    // Selected filter
    const matchesSelected = !showSelectedOnly || selectedSources.has(index);
    
    return matchesSearch && matchesType && matchesSelected;
  });

  // Handlers
  const handleToggleSelect = (index) => {
    const newSelected = new Set(selectedSources);
    if (newSelected.has(index)) {
      newSelected.delete(index);
    } else {
      newSelected.add(index);
    }
    setSelectedSources(newSelected);
  };

  const handleToggleExpand = (index) => {
    const newExpanded = new Set(expandedSources);
    if (newExpanded.has(index)) {
      newExpanded.delete(index);
    } else {
      newExpanded.add(index);
    }
    setExpandedSources(newExpanded);
  };

  const handleSelectAll = () => {
    setSelectedSources(new Set(sources.map((_, i) => i)));
  };

  const handleSelectNone = () => {
    setSelectedSources(new Set());
  };

  const handleSelectValid = () => {
    const validSources = new Set(
      sources
        .map((s, i) => (!s.fetch_error && s.cleaned_content_length > 100 ? i : null))
        .filter(i => i !== null)
    );
    setSelectedSources(validSources);
  };

  const handleExpandAll = () => {
    setExpandedSources(new Set(sources.map((_, i) => i)));
  };

  const handleCollapseAll = () => {
    setExpandedSources(new Set());
  };

  const handleApprove = async () => {
    setSaving(true);
    try {
      // Get selected sources with their data
      const approvedSources = sources
        .filter((_, i) => selectedSources.has(i))
        .map(source => ({
          ...source,
          approved: true,
          approved_at: new Date().toISOString(),
          // Ensure cleaned_content_length is set
          cleaned_content_length: source.cleaned_content_length || 
            (source.cleaned_content ? source.cleaned_content.length : 0)
        }));
      
      // Calculate total content length properly
      const totalContentLength = approvedSources.reduce((sum, s) => {
        return sum + (s.cleaned_content_length || 
          (s.cleaned_content ? s.cleaned_content.length : 0) || 
          (s.raw_content ? s.raw_content.length : 0) || 0);
      }, 0);
      
      const approvalData = {
        primary_url: extractionData.primary_url,
        primary_title: extractionData.primary_title,
        detected_card_name: extractionData.detected_card_name,
        detected_bank: extractionData.detected_bank,
        keywords_used: keywords,
        sources: approvedSources,
        total_sources: approvedSources.length,
        total_content_length: totalContentLength,
        raw_extraction_id: extractionData.extraction_id || extractionData.raw_extraction_id
      };

      await onApprove(approvalData);
    } catch (error) {
      console.error('Approval failed:', error);
      alert('Failed to save: ' + error.message);
    } finally {
      setSaving(false);
    }
  };

  // Calculate stats
  const totalSources = sources.length;
  const selectedCount = selectedSources.size;
  const totalChars = sources
    .filter((_, i) => selectedSources.has(i))
    .reduce((sum, s) => sum + (s.cleaned_content_length || 0), 0);
  const errorCount = sources.filter(s => s.fetch_error).length;

  return (
    <div className="bg-white rounded-xl shadow-lg p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6 pb-4 border-b">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Database className="text-blue-600" />
            Review Raw Extracted Data
          </h2>
          <p className="text-gray-600 mt-1">
            Review and approve raw content from each source before storing to database
          </p>
        </div>
        <div className="text-right">
          <div className="text-sm text-gray-500">Primary URL</div>
          <a 
            href={extractionData?.primary_url} 
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-blue-600 hover:underline flex items-center gap-1"
          >
            {extractionData?.primary_url?.substring(0, 50)}...
            <ExternalLink size={12} />
          </a>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="bg-blue-50 rounded-lg p-4">
          <div className="text-2xl font-bold text-blue-700">{totalSources}</div>
          <div className="text-sm text-blue-600">Total Sources</div>
        </div>
        <div className="bg-green-50 rounded-lg p-4">
          <div className="text-2xl font-bold text-green-700">{selectedCount}</div>
          <div className="text-sm text-green-600">Selected</div>
        </div>
        <div className="bg-purple-50 rounded-lg p-4">
          <div className="text-2xl font-bold text-purple-700">{totalChars.toLocaleString()}</div>
          <div className="text-sm text-purple-600">Characters Selected</div>
        </div>
        <div className="bg-red-50 rounded-lg p-4">
          <div className="text-2xl font-bold text-red-700">{errorCount}</div>
          <div className="text-sm text-red-600">Errors</div>
        </div>
      </div>

      {/* Keywords Used */}
      {keywords.length > 0 && (
        <div className="mb-6 p-4 bg-yellow-50 rounded-lg">
          <h4 className="text-sm font-medium text-yellow-800 mb-2 flex items-center gap-2">
            <Tag size={16} />
            Keywords Used for Extraction ({keywords.length})
          </h4>
          <div className="flex flex-wrap gap-1">
            {keywords.slice(0, 30).map((kw, i) => (
              <span key={i} className="px-2 py-0.5 bg-yellow-100 text-yellow-800 text-xs rounded">
                {kw}
              </span>
            ))}
            {keywords.length > 30 && (
              <span className="px-2 py-0.5 bg-yellow-200 text-yellow-800 text-xs rounded">
                +{keywords.length - 30} more
              </span>
            )}
          </div>
        </div>
      )}

      {/* Filters and Actions */}
      <div className="flex flex-wrap gap-3 mb-4 items-center">
        {/* Search */}
        <div className="flex-1 min-w-64 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={18} />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search sources..."
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {/* Type filter */}
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
        >
          <option value="all">All Types</option>
          <option value="web">Web Pages</option>
          <option value="pdf">PDFs</option>
        </select>

        {/* Show selected only */}
        <label className="flex items-center gap-2 px-3 py-2 border rounded-lg cursor-pointer hover:bg-gray-50">
          <input
            type="checkbox"
            checked={showSelectedOnly}
            onChange={(e) => setShowSelectedOnly(e.target.checked)}
            className="rounded border-gray-300"
          />
          <span className="text-sm">Selected Only</span>
        </label>
      </div>

      {/* Selection Actions */}
      <div className="flex flex-wrap gap-2 mb-4 pb-4 border-b">
        <span className="text-sm text-gray-600 py-1">Selection:</span>
        <button onClick={handleSelectAll} className="text-sm text-blue-600 hover:text-blue-800 px-2 py-1 rounded hover:bg-blue-50">
          All
        </button>
        <button onClick={handleSelectNone} className="text-sm text-blue-600 hover:text-blue-800 px-2 py-1 rounded hover:bg-blue-50">
          None
        </button>
        <button onClick={handleSelectValid} className="text-sm text-blue-600 hover:text-blue-800 px-2 py-1 rounded hover:bg-blue-50">
          Valid Only
        </button>
        <span className="text-gray-300">|</span>
        <span className="text-sm text-gray-600 py-1">View:</span>
        <button onClick={handleExpandAll} className="text-sm text-blue-600 hover:text-blue-800 px-2 py-1 rounded hover:bg-blue-50">
          Expand All
        </button>
        <button onClick={handleCollapseAll} className="text-sm text-blue-600 hover:text-blue-800 px-2 py-1 rounded hover:bg-blue-50">
          Collapse All
        </button>
      </div>

      {/* Sources List */}
      <div className="max-h-[50vh] overflow-y-auto mb-6">
        {filteredSources.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <FileText size={48} className="mx-auto mb-4 opacity-50" />
            <p>No sources found</p>
            {searchQuery && <p className="text-sm">Try a different search term</p>}
          </div>
        ) : (
          filteredSources.map((source, displayIndex) => {
            // Find actual index in original array
            const actualIndex = sources.findIndex(s => s.url === source.url && s.source_id === source.source_id);
            return (
              <SourceCard
                key={source.source_id || displayIndex}
                source={source}
                index={actualIndex}
                isExpanded={expandedSources.has(actualIndex)}
                onToggleExpand={handleToggleExpand}
                isSelected={selectedSources.has(actualIndex)}
                onToggleSelect={handleToggleSelect}
                keywords={keywords}
              />
            );
          })
        )}
      </div>

      {/* Action Buttons */}
      <div className="flex items-center justify-between pt-4 border-t">
        <div className="text-sm text-gray-600">
          <span className="font-medium">{selectedCount}</span> of <span className="font-medium">{totalSources}</span> sources selected
          {selectedCount > 0 && (
            <span className="ml-2">
              ({totalChars.toLocaleString()} characters)
            </span>
          )}
        </div>
        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="px-6 py-2.5 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 flex items-center gap-2"
          >
            <X size={18} />
            Cancel
          </button>
          <button
            onClick={handleApprove}
            disabled={saving || selectedCount === 0}
            className={`px-6 py-2.5 rounded-lg flex items-center gap-2 ${
              saving || selectedCount === 0
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-green-600 text-white hover:bg-green-700'
            }`}
          >
            {saving ? (
              <>
                <Loader2 size={18} className="animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Database size={18} />
                Approve & Store ({selectedCount} sources)
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export default RawDataReviewApproval;
