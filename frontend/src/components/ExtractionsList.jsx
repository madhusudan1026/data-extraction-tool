import React, { useState, useEffect } from 'react';
import { extractionAPIv2 } from '../services/api';
import { Loader2, Trash2, Eye, RefreshCw, Database, FileText, Globe, File, Clock, CheckCircle, XCircle, AlertCircle } from 'lucide-react';

function ExtractionsList() {
  const [extractions, setExtractions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [viewMode, setViewMode] = useState('raw'); // 'raw' or 'legacy'

  const loadExtractions = async () => {
    setLoading(true);
    try {
      if (viewMode === 'raw') {
        // Load raw extractions
        const response = await extractionAPIv2.listRawExtractions({ limit: 20, skip: (page - 1) * 20 });
        setExtractions(response.extractions || []);
        setTotalPages(Math.ceil((response.total || 0) / 20) || 1);
      } else {
        // Load legacy extractions
        const response = await extractionAPIv2.listExtractions({ page, limit: 10 });
        if (Array.isArray(response)) {
          setExtractions(response);
          setTotalPages(1);
        } else {
          setExtractions(response.data || response.results || []);
          setTotalPages(response.pagination?.pages || 1);
        }
      }
    } catch (error) {
      console.error('Failed to load extractions:', error);
      setExtractions([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadExtractions();
  }, [page, viewMode]);

  const handleDelete = async (id) => {
    if (!confirm('Are you sure you want to delete this extraction?')) return;

    try {
      await extractionAPIv2.deleteExtraction(id);
      loadExtractions();
    } catch (error) {
      console.error('Failed to delete:', error);
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'completed':
        return <span className="px-2 py-1 bg-green-100 text-green-700 rounded text-xs flex items-center gap-1"><CheckCircle size={12} /> Completed</span>;
      case 'processing':
        return <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs flex items-center gap-1"><Loader2 size={12} className="animate-spin" /> Processing</span>;
      case 'failed':
        return <span className="px-2 py-1 bg-red-100 text-red-700 rounded text-xs flex items-center gap-1"><XCircle size={12} /> Failed</span>;
      default:
        return <span className="px-2 py-1 bg-gray-100 text-gray-700 rounded text-xs">{status || 'Unknown'}</span>;
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="animate-spin text-blue-600" size={40} />
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl shadow-lg p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Database className="text-blue-600" />
          Extraction History
        </h2>
        <div className="flex items-center gap-3">
          {/* View mode toggle */}
          <div className="bg-gray-100 p-1 rounded-lg flex">
            <button
              onClick={() => setViewMode('raw')}
              className={`px-3 py-1 rounded text-sm font-medium transition ${
                viewMode === 'raw' 
                  ? 'bg-white shadow text-blue-600' 
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              Raw Extractions
            </button>
            <button
              onClick={() => setViewMode('legacy')}
              className={`px-3 py-1 rounded text-sm font-medium transition ${
                viewMode === 'legacy' 
                  ? 'bg-white shadow text-blue-600' 
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              Legacy
            </button>
          </div>
          <button
            onClick={loadExtractions}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition flex items-center space-x-2"
          >
            <RefreshCw size={16} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {extractions.length === 0 ? (
        <div className="text-center py-12">
          <Database size={48} className="mx-auto mb-4 text-gray-300" />
          <p className="text-gray-500 text-lg">No extractions yet</p>
          <p className="text-gray-400 text-sm mt-2">
            Start by extracting data from the Extract tab
          </p>
        </div>
      ) : viewMode === 'raw' ? (
        // Raw extractions view
        <>
          <div className="space-y-4">
            {extractions.map((extraction) => (
              <div
                key={extraction.extraction_id || extraction._id}
                className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <h3 className="font-semibold text-gray-900">
                        {extraction.card_name_hint || 'Unknown Card'}
                      </h3>
                      {getStatusBadge(extraction.status)}
                      {extraction.approved && (
                        <span className="px-2 py-1 bg-green-100 text-green-700 rounded text-xs flex items-center gap-1">
                          <CheckCircle size={12} /> Approved
                        </span>
                      )}
                    </div>
                    
                    <p className="text-sm text-gray-500 truncate max-w-2xl">
                      {extraction.primary_url}
                    </p>
                    
                    <div className="flex items-center flex-wrap gap-3 mt-3 text-sm text-gray-600">
                      <span className="flex items-center gap-1">
                        <Clock size={14} />
                        {new Date(extraction.created_at).toLocaleString()}
                      </span>
                      {extraction.bank_hint && (
                        <span className="px-2 py-0.5 bg-blue-50 text-blue-700 rounded text-xs">
                          {extraction.bank_hint}
                        </span>
                      )}
                      <span className="text-gray-500">
                        <strong>{extraction.sources_count || 0}</strong> sources
                      </span>
                      <span className="text-gray-500">
                        <strong>{extraction.keywords?.length || 0}</strong> keywords
                      </span>
                      {extraction.total_content_length && (
                        <span className="text-gray-500">
                          <strong>{(extraction.total_content_length / 1000).toFixed(1)}K</strong> chars
                        </span>
                      )}
                    </div>
                    
                    {/* Pattern counts */}
                    {extraction.patterns_detected && Object.keys(extraction.patterns_detected).length > 0 && (
                      <div className="flex flex-wrap gap-2 mt-2">
                        {Object.entries(extraction.patterns_detected).slice(0, 6).map(([type, items]) => (
                          <span key={type} className="px-2 py-0.5 bg-purple-50 text-purple-700 rounded text-xs">
                            {type}: {Array.isArray(items) ? items.length : items}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  
                  <div className="flex flex-col items-end gap-2">
                    <span className={`px-2 py-1 rounded text-xs ${
                      extraction.keyword_source === 'custom' 
                        ? 'bg-purple-100 text-purple-700' 
                        : 'bg-gray-100 text-gray-600'
                    }`}>
                      {extraction.keyword_source || 'default'} keywords
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      ) : (
        // Legacy extractions view
        <>
          <div className="space-y-4">
            {extractions.map((extraction) => (
              <div
                key={extraction._id || extraction.id}
                className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h3 className="font-semibold text-gray-900 text-lg">
                      {extraction.card_name || 'Unknown Card'}
                    </h3>
                    <p className="text-sm text-gray-500 mt-1 truncate max-w-md">
                      {extraction.source_url || extraction.source || 'No source'}
                    </p>
                    <div className="flex items-center space-x-3 mt-2">
                      <span className="text-sm text-gray-500">
                        {new Date(extraction.created_at || extraction.createdAt).toLocaleDateString()}
                      </span>
                      <span className="px-2 py-1 bg-gray-100 text-gray-700 rounded text-xs">
                        {extraction.source_type || 'url'}
                      </span>
                      <span className={`px-2 py-1 rounded text-xs ${
                        extraction.validation_status === 'validated'
                          ? 'bg-green-100 text-green-700'
                          : extraction.validation_status === 'requires_review'
                          ? 'bg-yellow-100 text-yellow-700'
                          : 'bg-gray-100 text-gray-700'
                      }`}>
                        {extraction.validation_status || 'pending'}
                      </span>
                    </div>
                    <div className="mt-3 flex items-center space-x-6 text-sm text-gray-600">
                      <span>
                        <strong>{extraction.benefits?.length || 0}</strong> benefits
                      </span>
                      <span>
                        <strong>{extraction.entitlements?.length || 0}</strong> entitlements
                      </span>
                      <span>
                        <strong>{extraction.merchants_vendors?.length || 0}</strong> merchants
                      </span>
                      <span>
                        Confidence: <strong>{Math.round((extraction.confidence_score || 0) * 100)}%</strong>
                      </span>
                    </div>
                  </div>
                  <div className="flex space-x-2">
                    <button
                      onClick={() => handleDelete(extraction._id || extraction.id)}
                      className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition"
                      title="Delete"
                    >
                      <Trash2 size={20} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center space-x-2 mt-6">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Previous
          </button>
          <span className="text-sm text-gray-600">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}

export default ExtractionsList;
