/**
 * Data Store & Vectorization
 * 
 * 3-step flow for managing stored extraction data:
 *   Step 1: Analyze — Browse and inspect stored raw data from MongoDB
 *   Step 2: Vectorize — Chunk, preview, and index into ChromaDB  
 *   Step 3: Pipelines — Select categories → auto-map pipelines → run
 */

import React, { useState, useEffect } from 'react';
import {
  Database, ChevronRight, ChevronLeft, CheckCircle, AlertCircle,
  Loader2, ExternalLink, RefreshCw, CreditCard, X, Eye
} from 'lucide-react';

const API_BASE = 'http://localhost:8000/api/v4/extraction';
const API_V2 = 'http://localhost:8000/api/v2/extraction';
const API_VECTOR = 'http://localhost:8000/api/v4/vector';

const CATEGORY_ICONS = {
  cashback: '💰', lounge: '✈️', golf: '🏌️', dining: '🍽️',
  travel: '🌴', insurance: '🛡️', rewards: '🎁', movie: '🎬',
  fee: '💳', lifestyle: '🎭', eligibility: '📋', general: '📄',
};

export default function DataStoreVectorization() {
  // Flow
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Step 1
  const [records, setRecords] = useState([]);
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [recordDetail, setRecordDetail] = useState(null);
  const [expandedSources, setExpandedSources] = useState(new Set());

  // Step 2
  const [chunkPreview, setChunkPreview] = useState(null);
  const [vectorResult, setVectorResult] = useState(null);
  const [vectorData, setVectorData] = useState(null);
  const [expandedChunkSources, setExpandedChunkSources] = useState(new Set());
  const [reindexVectors, setReindexVectors] = useState(false);

  // Category viewing (shared between Step 2 and 3)
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [categoryChunks, setCategoryChunks] = useState([]);



  // ============= Data Loading =============
  useEffect(() => { loadRecords(); }, []);

  const loadRecords = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_V2}/approved-raw`);
      const data = await res.json();
      setRecords(data.records || []);
    } catch (err) {
      setError('Failed to load stored data: ' + err.message);
    } finally {
      setLoading(false);
    }
  };



  // ============= Step 1: Select and Analyze =============
  const selectRecord = async (record) => {
    setSelectedRecord(record);
    setLoading(true);
    try {
      const res = await fetch(`${API_V2}/approved-raw/${record.saved_id}`);
      const data = await res.json();
      setRecordDetail(data.record || data);
    } catch (err) {
      setError('Failed to load record details: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  // ============= Step 2: Vectorize =============
  const previewChunks = async () => {
    if (!selectedRecord) return;
    setLoading(true); setError('');
    try {
      // If record already vectorized and not reindexing, load existing vector data
      if (selectedRecord.vector_indexed && !reindexVectors) {
        const vRes = await fetch(`${API_VECTOR}/record-data/${selectedRecord.saved_id}`);
        if (vRes.ok) {
          const vData = await vRes.json();
          if (vData.success && vData.total_chunks > 0) {
            setVectorData(vData);
            setVectorResult({ vector_chunks: vData.total_chunks, card_name: vData.card_name });
            setStep(2);
            return;
          }
        }
      }
      // Otherwise preview fresh chunks
      const res = await fetch(`${API_VECTOR}/preview-chunks`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ saved_id: selectedRecord.saved_id })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to preview chunks');
      setChunkPreview(data);
      setStep(2);
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  };

  const indexVectors = async () => {
    setLoading(true); setError('');
    try {
      const res = await fetch(`${API_VECTOR}/index-record`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ saved_id: selectedRecord.saved_id })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Vector indexing failed');
      setVectorResult(data);
      const vRes = await fetch(`${API_VECTOR}/record-data/${selectedRecord.saved_id}`);
      if (vRes.ok) setVectorData(await vRes.json());
      loadRecords();
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  };



  // ============= Category Helpers =============
  const viewCategoryChunks = (cat) => {
    if (selectedCategory === cat) { setSelectedCategory(null); setCategoryChunks([]); return; }
    setSelectedCategory(cat);
    const source = vectorData || chunkPreview;
    if (!source) return;
    let chunks = [];
    if (source.chunks && source.chunks.length > 0 && source.chunks[0]?.metadata) {
      chunks = source.chunks.filter(c => (c.metadata?.benefit_category || 'general') === cat);
    } else if (source.sources) {
      source.sources.forEach(src => {
        (src.chunks || []).forEach(c => {
          if ((c.benefit_category || 'general') === cat) chunks.push(c);
        });
      });
    }
    setCategoryChunks(chunks);
  };



  // ============= Generic Helpers =============
  const resetFlow = () => {
    setStep(1); setSelectedRecord(null); setRecordDetail(null);
    setChunkPreview(null); setVectorResult(null); setVectorData(null);
    setSelectedCategory(null); setCategoryChunks([]);
    setExpandedSources(new Set()); setExpandedChunkSources(new Set());
    setError(''); setReindexVectors(false);
  };

  const toggle = (set, setFn, key) => {
    const n = new Set(set);
    n.has(key) ? n.delete(key) : n.add(key);
    setFn(n);
  };

  const stepLabels = ['Analyze', 'Vectorize'];

  // ============= Shared: Category Tiles =============
  const CategoryTiles = ({ breakdown, showViewButton = true }) => (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
      {Object.entries(breakdown || {}).sort((a, b) => b[1] - a[1]).map(([cat, count]) => {
        const isActive = selectedCategory === cat;
        return (
          <div key={cat} className="relative">
            <button
              onClick={() => viewCategoryChunks(cat)}
              className={`w-full p-3 rounded-lg border text-center transition-all hover:shadow-sm ${
                isActive ? 'border-purple-400 bg-purple-50 ring-2 ring-purple-200' : 'bg-white hover:border-purple-200'
              }`}
            >
              <div className="text-lg">{CATEGORY_ICONS[cat] || '📄'}</div>
              <div className="text-xl font-bold text-purple-700">{count}</div>
              <div className="text-xs text-gray-600 font-medium">{cat}</div>
            </button>
            {showViewButton && (
              <button onClick={(e) => { e.stopPropagation(); viewCategoryChunks(cat); }}
                className="absolute top-1 right-1 p-1 text-gray-400 hover:text-purple-600 rounded" title="View chunks">
                <Eye size={14} />
              </button>
            )}
          </div>
        );
      })}
    </div>
  );

  // ============= Shared: Category Chunks Viewer =============
  const CategoryChunksViewer = () => {
    if (!selectedCategory || categoryChunks.length === 0) return null;
    return (
      <div className="border border-purple-200 rounded-lg overflow-hidden">
        <div className="p-3 bg-purple-50 flex items-center gap-2">
          <span className="text-lg">{CATEGORY_ICONS[selectedCategory] || '📄'}</span>
          <span className="font-medium text-purple-800">{selectedCategory}</span>
          <span className="text-xs bg-purple-200 text-purple-700 px-2 py-0.5 rounded-full">{categoryChunks.length} chunks</span>
          <button onClick={() => { setSelectedCategory(null); setCategoryChunks([]); }} className="ml-auto text-gray-400 hover:text-gray-600"><X size={16} /></button>
        </div>
        <div className="divide-y max-h-[32rem] overflow-y-auto">
          {categoryChunks.map((chunk, i) => {
            const meta = chunk.metadata || {};
            const srcUrl = chunk.source_url || meta.source_url || '';
            const srcTitle = chunk.source_title || meta.source_title || '';
            const cardNet = chunk.card_network || meta.card_network || '';
            const cardTier = chunk.card_tier || meta.card_tier || '';
            const cardName = chunk.card_name || meta.card_name || '';
            const bankName = chunk.bank_name || meta.bank_name || '';
            const primaryUrl = chunk.primary_url || meta.primary_url || '';
            const pageType = chunk.page_type || meta.page_type || '';
            const charCount = chunk.text_length || chunk.text_full_length || meta.char_count || (chunk.text || '').length;

            return (
              <div key={i} className="p-3">
                {/* Chunk header with metadata badges */}
                <div className="flex items-center gap-1.5 mb-2 flex-wrap">
                  <span className="text-xs font-mono bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">{chunk.chunk_id || chunk.id || '#' + (chunk.chunk_index ?? i)}</span>
                  {cardName && <span className="text-xs bg-purple-50 text-purple-700 px-1.5 py-0.5 rounded">🃏 {cardName}</span>}
                  {cardNet && <span className="text-xs bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded">{cardNet}</span>}
                  {cardTier && <span className="text-xs bg-indigo-50 text-indigo-600 px-1.5 py-0.5 rounded">{cardTier}</span>}
                  {bankName && <span className="text-xs bg-gray-50 text-gray-600 px-1.5 py-0.5 rounded">🏦 {bankName}</span>}
                  {pageType && <span className="text-xs bg-yellow-50 text-yellow-700 px-1.5 py-0.5 rounded">{pageType}</span>}
                  <span className="text-xs text-gray-400">{charCount} chars</span>
                </div>
                {/* Source URLs */}
                <div className="flex flex-col gap-0.5 mb-2">
                  {srcUrl && (
                    <a href={srcUrl} target="_blank" rel="noopener noreferrer"
                      className="text-xs text-blue-500 hover:underline flex items-center gap-1 truncate">
                      <ExternalLink size={10} className="shrink-0" /> <span className="font-medium">Source:</span> {srcTitle || srcUrl}
                    </a>
                  )}
                  {primaryUrl && primaryUrl !== srcUrl && (
                    <a href={primaryUrl} target="_blank" rel="noopener noreferrer"
                      className="text-xs text-gray-500 hover:underline flex items-center gap-1 truncate">
                      <ExternalLink size={10} className="shrink-0" /> <span className="font-medium">Card URL:</span> {primaryUrl}
                    </a>
                  )}
                </div>
                {/* Full chunk text */}
                <div className="text-xs text-gray-700 leading-relaxed whitespace-pre-wrap bg-gray-50 p-2.5 rounded border border-gray-100 max-h-60 overflow-y-auto">
                  {chunk.text}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  // ============= RENDER =============
  return (
    <div className="space-y-6">
      {/* Step Indicator */}
      <div className="flex items-center gap-2">
        {stepLabels.map((label, i) => (
          <React.Fragment key={i}>
            <button onClick={() => { if (i + 1 <= step) { setSelectedCategory(null); setCategoryChunks([]); setStep(i + 1); } }}
              disabled={i + 1 > step}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                step === i + 1 ? 'bg-purple-600 text-white shadow-sm'
                  : i + 1 < step ? 'bg-purple-100 text-purple-700 hover:bg-purple-200 cursor-pointer'
                  : 'bg-gray-100 text-gray-400 cursor-not-allowed'
              }`}>
              <span className="w-6 h-6 rounded-full flex items-center justify-center text-xs border-2 border-current">
                {i + 1 < step ? '✓' : i + 1}
              </span>
              {label}
            </button>
            {i < 1 && <ChevronRight size={16} className="text-gray-300" />}
          </React.Fragment>
        ))}
        {selectedRecord && (
          <button onClick={resetFlow} className="ml-auto text-gray-400 hover:text-gray-600 text-sm flex items-center gap-1">
            <RefreshCw size={14} /> Reset
          </button>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg flex items-center gap-2 text-red-700 text-sm">
          <AlertCircle size={18} /> {error}
          <button onClick={() => setError('')} className="ml-auto"><X size={14} /></button>
        </div>
      )}

      {/* ============= STEP 1: ANALYZE ============= */}
      {step === 1 && (
        <div className="space-y-4">
          {!selectedRecord ? (
            <>
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-800">Stored Raw Data</h2>
                <button onClick={loadRecords} disabled={loading} className="text-sm text-purple-600 hover:text-purple-800 flex items-center gap-1">
                  <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
                </button>
              </div>

              {loading && !records.length ? (
                <div className="flex items-center justify-center py-12"><Loader2 size={32} className="animate-spin text-purple-600" /></div>
              ) : records.length === 0 ? (
                <div className="text-center py-12 text-gray-500">
                  <Database size={48} className="mx-auto mb-3 text-gray-300" />
                  <p>No stored data yet. Use the Enhanced Extraction tab first.</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {records.map(record => (
                    <div key={record.saved_id} onClick={() => selectRecord(record)}
                      className="p-4 border rounded-lg hover:border-purple-300 hover:bg-purple-50 cursor-pointer transition-all">
                      <div className="flex items-center gap-3">
                        <CreditCard size={20} className="text-gray-400" />
                        <div className="flex-1 min-w-0">
                          <h3 className="font-medium text-gray-800 truncate">{record.detected_card_name || record.primary_title || 'Unknown Card'}</h3>
                          <div className="flex items-center gap-2 mt-1 flex-wrap">
                            <span className="text-xs text-gray-500">{record.detected_bank}</span>
                            {record.card_network && <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 text-xs rounded">{record.card_network}</span>}
                            {record.card_tier && <span className="px-1.5 py-0.5 bg-purple-100 text-purple-700 text-xs rounded">{record.card_tier}</span>}
                            <span className="text-xs text-gray-400">{record.total_sources} sources</span>
                            <span className="text-xs text-gray-400">{(record.total_content_length || 0).toLocaleString()} chars</span>
                            {record.vector_indexed && <span className="px-1.5 py-0.5 bg-green-100 text-green-700 text-xs rounded">vectorized</span>}
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="text-xs text-gray-400">{new Date(record.stored_at).toLocaleDateString()}</div>
                          <div className="text-xs font-mono text-gray-300">{record.saved_id}</div>
                        </div>
                        <ChevronRight size={20} className="text-gray-300" />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="space-y-4">
              <button onClick={() => { setSelectedRecord(null); setRecordDetail(null); }} className="text-sm text-purple-600 hover:text-purple-800 flex items-center gap-1">
                <ChevronLeft size={16} /> Back to list
              </button>

              <div className="p-4 bg-gradient-to-r from-purple-50 to-blue-50 rounded-lg border border-purple-200">
                <div className="flex items-center gap-3">
                  <CreditCard size={24} className="text-purple-600" />
                  <div>
                    <h3 className="font-bold text-lg text-gray-800">{selectedRecord.detected_card_name || 'Unknown Card'}</h3>
                    <div className="flex gap-2 mt-1 flex-wrap">
                      {selectedRecord.card_network && <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full">{selectedRecord.card_network}</span>}
                      {selectedRecord.card_tier && <span className="px-2 py-0.5 bg-purple-100 text-purple-700 text-xs rounded-full">{selectedRecord.card_tier}</span>}
                      <span className="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded-full">{selectedRecord.detected_bank}</span>
                    </div>
                  </div>
                  <div className="ml-auto text-right"><span className="text-xs font-mono text-gray-400">{selectedRecord.saved_id}</span></div>
                </div>
              </div>

              <div className="grid grid-cols-4 gap-3">
                <div className="bg-white p-3 rounded-lg border text-center">
                  <div className="text-xl font-bold text-gray-700">{selectedRecord.total_sources}</div>
                  <div className="text-xs text-gray-500">Sources</div>
                </div>
                <div className="bg-white p-3 rounded-lg border text-center">
                  <div className="text-xl font-bold text-gray-700">{(selectedRecord.total_content_length || 0).toLocaleString()}</div>
                  <div className="text-xs text-gray-500">Characters</div>
                </div>
                <div className="bg-white p-3 rounded-lg border text-center">
                  <div className="text-xl font-bold text-gray-700">{selectedRecord.vector_indexed ? selectedRecord.vector_chunks || '✓' : '—'}</div>
                  <div className="text-xs text-gray-500">Vector Chunks</div>
                </div>
                <div className="bg-white p-3 rounded-lg border text-center">
                  <div className="text-xs text-gray-600 mt-1">{selectedRecord.status || 'stored'}</div>
                  <div className="text-xs text-gray-500">Status</div>
                </div>
              </div>

              {loading ? (
                <div className="flex items-center justify-center py-8"><Loader2 size={24} className="animate-spin text-purple-600" /></div>
              ) : recordDetail?.sources ? (
                <div className="space-y-2">
                  <h4 className="font-medium text-gray-700">Sources ({recordDetail.sources.length})</h4>
                  {recordDetail.sources.map((src, idx) => {
                    const isExp = expandedSources.has(idx);
                    const content = src.cleaned_content || src.raw_content || '';
                    return (
                      <div key={idx} className="border rounded-lg overflow-hidden">
                        <div className="p-3 bg-gray-50 cursor-pointer flex items-center gap-2 hover:bg-gray-100"
                          onClick={() => toggle(expandedSources, setExpandedSources, idx)}>
                          <ChevronRight size={16} className={`transition-transform ${isExp ? 'rotate-90' : ''}`} />
                          <span className={`px-1.5 py-0.5 text-xs rounded ${src.source_type === 'pdf' ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'}`}>
                            {src.source_type || 'web'}
                          </span>
                          {(src.depth || 0) > 0 && <span className="text-xs bg-gray-200 px-1 rounded">depth:{src.depth}</span>}
                          <span className="text-sm font-medium truncate flex-1">{src.title || src.url}</span>
                          <span className="text-xs text-gray-400">{content.length.toLocaleString()} chars</span>
                        </div>
                        {isExp && (
                          <div className="p-3 border-t">
                            <a href={src.url} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-500 hover:underline flex items-center gap-1 mb-2">
                              <ExternalLink size={12} /> {src.url}
                            </a>
                            <pre className="text-xs text-gray-600 whitespace-pre-wrap max-h-64 overflow-y-auto bg-gray-50 p-3 rounded">
                              {content.substring(0, 3000)}{content.length > 3000 ? '\n\n... [truncated]' : ''}
                            </pre>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : null}

              {/* Reuse vectors toggle - shown when record already has vectors */}
              {selectedRecord.vector_indexed && (
                <div className="p-3 bg-green-50 border border-green-200 rounded-lg flex items-center justify-between">
                  <div>
                    <div className="text-sm font-medium text-green-800">Existing vectors found ({selectedRecord.vector_chunks || '?'} chunks)</div>
                    <div className="text-xs text-green-600">This record has already been vectorized</div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-gray-500">{reindexVectors ? 'Re-index from scratch' : 'Use existing'}</span>
                    <button onClick={() => setReindexVectors(!reindexVectors)}
                      className={`w-12 h-6 rounded-full transition-colors ${reindexVectors ? 'bg-orange-500' : 'bg-green-500'}`}>
                      <div className={`w-5 h-5 bg-white rounded-full shadow transform transition-transform ${reindexVectors ? 'translate-x-6' : 'translate-x-0.5'}`} />
                    </button>
                  </div>
                </div>
              )}

              <button onClick={previewChunks} disabled={loading}
                className="w-full py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 flex items-center justify-center gap-2 font-medium disabled:opacity-50">
                {loading ? <Loader2 size={20} className="animate-spin" /> : <Database size={20} />}
                {selectedRecord.vector_indexed && !reindexVectors ? 'View Existing Vectors' : 'Preview & Vectorize'}
                <ChevronRight size={20} />
              </button>
            </div>
          )}
        </div>
      )}

      {/* ============= STEP 2: VECTORIZE ============= */}
      {step === 2 && (
        <div className="space-y-4">
          {/* Pre-index: Chunk Preview */}
          {chunkPreview && !vectorResult && (
            <div className="space-y-4">
              <div className="p-4 bg-gradient-to-r from-purple-50 to-blue-50 rounded-lg border border-purple-200">
                <div className="flex items-center gap-3">
                  <CreditCard size={24} className="text-purple-600" />
                  <div>
                    <h3 className="font-bold text-lg text-gray-800">{chunkPreview.card_name}</h3>
                    <div className="flex gap-2 mt-1 flex-wrap">
                      {chunkPreview.card_network && <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full">{chunkPreview.card_network}</span>}
                      {chunkPreview.card_tier && <span className="px-2 py-0.5 bg-purple-100 text-purple-700 text-xs rounded-full">{chunkPreview.card_tier}</span>}
                      {chunkPreview.bank_name && <span className="px-2 py-0.5 bg-gray-100 text-gray-700 text-xs rounded-full">{chunkPreview.bank_name}</span>}
                    </div>
                  </div>
                  <div className="ml-auto text-right">
                    <div className="text-3xl font-bold text-purple-600">{chunkPreview.total_chunks}</div>
                    <div className="text-sm text-gray-500">chunks ready</div>
                  </div>
                </div>
              </div>

              <div>
                <h4 className="font-medium text-gray-700 mb-2">Categories <span className="text-xs text-gray-400">(click to view chunks)</span></h4>
                <CategoryTiles breakdown={chunkPreview.category_breakdown} />
              </div>

              <CategoryChunksViewer />

              {/* Sources with chunks */}
              <div className="space-y-2">
                <h4 className="font-medium text-gray-700">Sources ({chunkPreview.total_sources})</h4>
                {chunkPreview.sources?.map(src => {
                  const isExp = expandedChunkSources.has(src.source_index);
                  const srcChunks = chunkPreview.chunks?.filter(c => c.source_index === src.source_index) || [];
                  return (
                    <div key={src.source_index} className="border rounded-lg overflow-hidden">
                      <div className="p-3 bg-gray-50 cursor-pointer flex items-center gap-2 hover:bg-gray-100"
                        onClick={() => toggle(expandedChunkSources, setExpandedChunkSources, src.source_index)}>
                        <ChevronRight size={16} className={`transition-transform ${isExp ? 'rotate-90' : ''}`} />
                        <span className={`px-1.5 py-0.5 text-xs rounded ${src.source_type === 'pdf' ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'}`}>{src.source_type}</span>
                        {src.depth > 0 && <span className="text-xs bg-gray-200 px-1 rounded">depth:{src.depth}</span>}
                        <span className="text-sm font-medium truncate flex-1">{src.title || src.url}</span>
                        <span className="text-xs text-purple-600 font-medium">{src.chunks_generated} chunks</span>
                      </div>
                      {isExp && (
                        <div className="divide-y max-h-64 overflow-y-auto">
                          {srcChunks.map(chunk => (
                            <div key={chunk.chunk_index} className="p-3 text-sm">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-xs font-mono text-gray-400">#{chunk.chunk_index}</span>
                                <span className={`px-1.5 py-0.5 text-xs rounded ${chunk.metadata.benefit_category === 'general' ? 'bg-gray-100 text-gray-600' : 'bg-purple-100 text-purple-700'}`}>
                                  {chunk.metadata.benefit_category}
                                </span>
                                <span className="text-xs text-gray-400">{chunk.text_full_length} chars</span>
                              </div>
                              <p className="text-gray-700 text-xs leading-relaxed whitespace-pre-wrap">{chunk.text}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              <div className="flex gap-3">
                <button onClick={() => setStep(1)} className="px-4 py-2 border rounded-lg hover:bg-gray-50 flex items-center gap-1">
                  <ChevronLeft size={18} /> Back
                </button>
                <button onClick={indexVectors} disabled={loading || !chunkPreview.vector_store_available}
                  className="flex-1 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 flex items-center justify-center gap-2 font-medium disabled:opacity-50">
                  {loading ? <><Loader2 size={20} className="animate-spin" /> Indexing...</> : <><Database size={20} /> Index {chunkPreview.total_chunks} Chunks into ChromaDB</>}
                </button>
              </div>
              {!chunkPreview.vector_store_available && (
                <p className="text-sm text-yellow-600 bg-yellow-50 p-3 rounded-lg">
                  ChromaDB not available. Run: <code className="bg-yellow-100 px-1 rounded">pip install chromadb</code> and <code className="bg-yellow-100 px-1 rounded">ollama pull nomic-embed-text</code>
                </p>
              )}
            </div>
          )}

          {/* Post-index: Vector Data View */}
          {vectorResult && (
            <div className="space-y-4">
              <div className="p-4 bg-green-50 border border-green-200 rounded-lg flex items-center gap-3">
                <CheckCircle size={24} className="text-green-600" />
                <div>
                  <h3 className="font-bold text-green-800">Indexed Successfully!</h3>
                  <p className="text-sm text-green-600">{vectorResult.vector_chunks} chunks stored in ChromaDB</p>
                </div>
              </div>

              {vectorData && (
                <div className="space-y-4">
                  <div className="p-4 bg-purple-50 rounded-lg border border-purple-200">
                    <div className="flex items-center gap-3 mb-3">
                      <CreditCard size={20} className="text-purple-600" />
                      <span className="font-bold text-gray-800">{vectorData.card_name}</span>
                      {vectorData.card_network && <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full">{vectorData.card_network}</span>}
                      {vectorData.card_tier && <span className="px-2 py-0.5 bg-purple-100 text-purple-700 text-xs rounded-full">{vectorData.card_tier}</span>}
                    </div>
                    <div className="grid grid-cols-3 gap-3 text-center">
                      <div><div className="text-xl font-bold text-purple-700">{vectorData.total_chunks}</div><div className="text-xs text-gray-500">Chunks</div></div>
                      <div><div className="text-xl font-bold text-blue-700">{vectorData.total_sources}</div><div className="text-xs text-gray-500">Sources</div></div>
                      <div><div className="text-xl font-bold text-green-700">{Object.keys(vectorData.category_breakdown || {}).length}</div><div className="text-xs text-gray-500">Categories</div></div>
                    </div>
                  </div>

                  <div>
                    <h4 className="font-medium text-gray-700 mb-2">Indexed Categories <span className="text-xs text-gray-400">(click to view chunks)</span></h4>
                    <CategoryTiles breakdown={vectorData.category_breakdown} />
                  </div>

                  <CategoryChunksViewer />
                </div>
              )}

              <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-700">
                Vectorization complete. Use the <strong>Pipeline Execution</strong> tab to run extraction pipelines on this data.
              </div>
              <button onClick={resetFlow}
                className="w-full py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 flex items-center justify-center gap-2 font-medium">
                <RefreshCw size={18} /> Vectorize Another Card
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
