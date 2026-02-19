/**
 * Pipeline Execution
 * 
 * Separated pipeline flow operating on vectorized data:
 *   Step 1: Select bank → select card (from session_cards master collection)
 *   Step 2: View all vector chunks for this card, select categories/pipelines
 *   Step 3: Run pipelines, view extracted benefits
 */

import React, { useState, useEffect } from 'react';
import {
  Zap, ChevronRight, ChevronLeft, CheckCircle, AlertCircle,
  Loader2, ExternalLink, RefreshCw, CreditCard, X, Eye,
  CheckSquare, Square, Database, Search
} from 'lucide-react';

const API_BASE = 'http://localhost:8000/api/v4/extraction';
const API_V2 = 'http://localhost:8000/api/v2/extraction';
const API_VECTOR = 'http://localhost:8000/api/v4/vector';

const CATEGORY_PIPELINE_MAP = {
  cashback: ['cashback'], lounge: ['lounge_access'], golf: ['golf'],
  dining: ['dining'], travel: ['travel_benefits'], insurance: ['insurance'],
  rewards: ['rewards_points'], movie: ['movie'], fee: ['fee_waiver'],
  lifestyle: ['lifestyle'], eligibility: [], general: [],
};

const CATEGORY_ICONS = {
  cashback: '💰', lounge: '✈️', golf: '🏌️', dining: '🍽️',
  travel: '🌴', insurance: '🛡️', rewards: '🎁', movie: '🎬',
  fee: '💳', lifestyle: '🎭', eligibility: '📋', general: '📄',
};

export default function PipelineExecution() {
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Step 1: Bank & Card from master collection
  const [banks, setBanks] = useState([]);
  const [selectedBank, setSelectedBank] = useState(null);
  const [selectedCard, setSelectedCard] = useState(null);

  // Step 2: Vector chunks for the selected card
  const [cardChunks, setCardChunks] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [categoryChunks, setCategoryChunks] = useState([]);
  const [selectedCategories, setSelectedCategories] = useState(new Set());
  const [selectedPipelines, setSelectedPipelines] = useState(new Set());
  const [pipelines, setPipelines] = useState([]);

  // Step 3: Results
  const [pipelineResults, setPipelineResults] = useState(null);
  const [expandedResults, setExpandedResults] = useState(new Set());

  // ============= Load Data =============
  useEffect(() => { loadBanks(); loadPipelines(); }, []);

  const loadBanks = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_VECTOR}/banks`);
      const data = await res.json();
      if (!data.success) throw new Error('Failed to load banks');
      setBanks(data.banks || []);
    } catch (err) {
      setError('Failed to load banks and cards: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadPipelines = async () => {
    try {
      const res = await fetch(`${API_BASE}/pipelines`);
      const data = await res.json();
      setPipelines(data.pipelines || []);
    } catch (err) {
      console.error('Failed to load pipelines:', err);
    }
  };

  // ============= Step 1 → 2: Select card & load its chunks =============
  const selectCard = async (card) => {
    setSelectedCard(card);
    setLoading(true);
    setError('');
    try {
      const bankKey = selectedBank?.bank_key || '';
      const cardUrl = card.card_url || '';
      const params = new URLSearchParams();
      if (bankKey) params.append('bank_key', bankKey);
      if (cardUrl) params.append('card_url', cardUrl);
      const url = `${API_VECTOR}/card-chunks/${encodeURIComponent(card.card_name)}?${params.toString()}`;
      const res = await fetch(url);
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.detail || 'Failed to load card chunks');
      
      if (data.total_chunks === 0) {
        // Fetch diagnostic info to help debug
        let debugInfo = '';
        try {
          const debugRes = await fetch(`${API_VECTOR}/debug/all-metadata?limit=100`);
          const debugData = await debugRes.json();
          const cardNamesInDB = Object.keys(debugData.unique_card_names || {}).join(', ');
          const bankKeysInDB = Object.keys(debugData.unique_bank_keys || {}).join(', ');
          debugInfo = `\n\nVector DB contains ${debugData.total_chunks} total chunks.\nCard names in DB: ${cardNamesInDB || 'none'}\nBank keys in DB: ${bankKeysInDB || 'none'}`;
        } catch (e) { /* ignore debug errors */ }
        
        setError(`No vector chunks found for "${card.card_name}" (bank: ${bankKey || 'unknown'}).${debugInfo}\n\nEnsure the card data is vectorized in the Data Store tab.`);
        setSelectedCard(null);
        return;
      }
      
      setCardChunks(data);
      setStep(2);
    } catch (err) {
      setError(err.message);
      setSelectedCard(null);
    } finally {
      setLoading(false);
    }
  };

  // ============= Step 2: Category & Pipeline Selection =============
  const viewCategoryChunks = (cat) => {
    if (selectedCategory === cat) { setSelectedCategory(null); setCategoryChunks([]); return; }
    setSelectedCategory(cat);
    setCategoryChunks(cardChunks?.categories?.[cat] || []);
  };

  const toggleCategory = (cat) => {
    const next = new Set(selectedCategories);
    next.has(cat) ? next.delete(cat) : next.add(cat);
    setSelectedCategories(next);
    const mapped = new Set();
    next.forEach(c => (CATEGORY_PIPELINE_MAP[c] || []).forEach(p => mapped.add(p)));
    setSelectedPipelines(mapped);
  };

  const selectAllCategories = () => {
    if (!cardChunks?.category_breakdown) return;
    const all = new Set(Object.keys(cardChunks.category_breakdown));
    setSelectedCategories(all);
    const mapped = new Set();
    all.forEach(c => (CATEGORY_PIPELINE_MAP[c] || []).forEach(p => mapped.add(p)));
    setSelectedPipelines(mapped);
  };

  // ============= Step 3: Run Pipelines =============
  const runPipelines = async () => {
    if (!selectedCard || !cardChunks) return;
    setLoading(true); setError(''); setPipelineResults(null);
    try {
      // Find the approved_raw_data record(s) that contain data for this card
      // Use the first source's primary_url to find the saved_id
      const approvedRes = await fetch(`${API_V2}/approved-raw`);
      const approvedData = await approvedRes.json();
      const records = approvedData.records || [];
      
      // Find record matching this card (by card name or bank)
      const bankKey = selectedBank?.bank_key || '';
      const cardName = selectedCard.card_name;
      let matchedRecord = records.find(r =>
        r.detected_card_name === cardName ||
        (r.bank_key === bankKey && r.detected_card_name?.includes(cardName))
      );
      
      // Fallback: find any record from same bank that's vectorized
      if (!matchedRecord) {
        matchedRecord = records.find(r =>
          r.vector_indexed && (r.bank_key === bankKey || r.detected_bank === selectedBank?.bank_name)
        );
      }
      
      if (!matchedRecord) {
        throw new Error('Could not find approved raw data record for this card. Ensure the data is saved and vectorized.');
      }
      
      const res = await fetch(
        `${API_V2}/pipelines/run-all/${matchedRecord.saved_id}?save_results=true&parallel=true`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pipeline_names: Array.from(selectedPipelines) }) }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Pipeline execution failed');
      setPipelineResults(data.result || data);
      setStep(3);
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  };

  // ============= Helpers =============
  const resetFlow = () => {
    setStep(1); setSelectedBank(null); setSelectedCard(null);
    setCardChunks(null); setSelectedCategory(null); setCategoryChunks([]);
    setSelectedCategories(new Set()); setSelectedPipelines(new Set());
    setPipelineResults(null); setExpandedResults(new Set()); setError('');
  };

  const toggle = (set, setFn, key) => {
    const n = new Set(set); n.has(key) ? n.delete(key) : n.add(key); setFn(n);
  };

  const stepLabels = ['Select Card', 'Choose Pipelines', 'Results'];
  const bankCards = selectedBank?.cards || [];

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
                step === i + 1 ? 'bg-blue-600 text-white shadow-sm'
                  : i + 1 < step ? 'bg-blue-100 text-blue-700 hover:bg-blue-200 cursor-pointer'
                  : 'bg-gray-100 text-gray-400 cursor-not-allowed'
              }`}>
              <span className="w-6 h-6 rounded-full flex items-center justify-center text-xs border-2 border-current">
                {i + 1 < step ? '✓' : i + 1}
              </span>
              {label}
            </button>
            {i < 2 && <ChevronRight size={16} className="text-gray-300" />}
          </React.Fragment>
        ))}
        {step > 1 && (
          <button onClick={resetFlow} className="ml-auto text-gray-400 hover:text-gray-600 text-sm flex items-center gap-1">
            <RefreshCw size={14} /> Reset
          </button>
        )}
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2 text-red-700 text-sm">
          <AlertCircle size={18} className="shrink-0 mt-0.5" />
          <pre className="whitespace-pre-wrap font-sans flex-1">{error}</pre>
          <button onClick={() => setError('')} className="shrink-0"><X size={14} /></button>
        </div>
      )}

      {/* ============= STEP 1: SELECT BANK & CARD ============= */}
      {step === 1 && (
        <div className="space-y-4">
          {loading && !banks.length ? (
            <div className="flex items-center justify-center py-12"><Loader2 size={32} className="animate-spin text-blue-600" /></div>
          ) : banks.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <Database size={48} className="mx-auto mb-3 text-gray-300" />
              <p className="font-medium">No banks or cards found</p>
              <p className="text-sm mt-1">Use the Enhanced Extraction tab to discover cards, then vectorize in Data Store.</p>
            </div>
          ) : (
            <>
              {/* Bank Selection */}
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-800">Select Bank</h2>
                <button onClick={loadBanks} disabled={loading} className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1">
                  <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
                </button>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {banks.map(bank => (
                  <button key={bank.bank_name} onClick={() => { setSelectedBank(bank); setSelectedCard(null); }}
                    className={`p-4 rounded-lg border text-center transition-all ${
                      selectedBank?.bank_name === bank.bank_name
                        ? 'border-blue-400 bg-blue-50 ring-2 ring-blue-200 shadow-sm'
                        : 'bg-white hover:border-blue-200 hover:shadow-sm'
                    }`}>
                    <div className="text-2xl mb-1">🏦</div>
                    <div className="font-medium text-gray-800 text-sm">{bank.bank_name}</div>
                    <div className="text-xs text-gray-500 mt-1">{bank.cards.length} card{bank.cards.length !== 1 ? 's' : ''} discovered</div>
                  </button>
                ))}
              </div>

              {/* Card Selection */}
              {selectedBank && (
                <div className="space-y-3">
                  <h3 className="font-medium text-gray-700 flex items-center gap-2">
                    <CreditCard size={18} /> Cards — {selectedBank.bank_name}
                    <span className="text-xs text-gray-400">({bankCards.length})</span>
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {bankCards.map(card => (
                      <div key={card.card_id || card.card_name}
                        onClick={() => selectCard(card)}
                        className={`p-4 border rounded-lg cursor-pointer transition-all hover:shadow-sm ${
                          loading && selectedCard?.card_name === card.card_name
                            ? 'border-blue-300 bg-blue-50'
                            : 'hover:border-blue-300 hover:bg-blue-50'
                        }`}>
                        <div className="flex items-center gap-3">
                          {card.card_image?.thumbnail ? (
                            <img src={card.card_image.thumbnail} alt="" className="w-12 h-8 object-contain rounded" />
                          ) : (
                            <CreditCard size={20} className="text-gray-400" />
                          )}
                          <div className="flex-1 min-w-0">
                            <h4 className="font-medium text-gray-800 text-sm">{card.card_name}</h4>
                            <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                              {card.card_network && <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 text-xs rounded">{card.card_network}</span>}
                              {card.card_tier && <span className="px-1.5 py-0.5 bg-purple-100 text-purple-700 text-xs rounded">{card.card_tier}</span>}
                            </div>
                          </div>
                          {loading && selectedCard?.card_name === card.card_name
                            ? <Loader2 size={20} className="animate-spin text-blue-500" />
                            : <ChevronRight size={20} className="text-gray-300" />}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ============= STEP 2: REVIEW CHUNKS & SELECT PIPELINES ============= */}
      {step === 2 && cardChunks && (
        <div className="space-y-4">
          {/* Card & bank context */}
          <div className="p-4 bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg border border-blue-200">
            <div className="flex items-center gap-3">
              {selectedCard?.card_image?.thumbnail ? (
                <img src={selectedCard.card_image.thumbnail} alt="" className="w-16 h-10 object-contain rounded" />
              ) : (
                <CreditCard size={24} className="text-blue-600" />
              )}
              <div>
                <h3 className="font-bold text-lg text-gray-800">{selectedCard?.card_name}</h3>
                <div className="flex gap-2 mt-1 flex-wrap">
                  {selectedCard?.card_network && <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full">{selectedCard.card_network}</span>}
                  {selectedCard?.card_tier && <span className="px-2 py-0.5 bg-purple-100 text-purple-700 text-xs rounded-full">{selectedCard.card_tier}</span>}
                  {selectedBank?.bank_name && <span className="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded-full">🏦 {selectedBank.bank_name}</span>}
                </div>
              </div>
              <div className="ml-auto text-right">
                <div className="text-2xl font-bold text-blue-600">{cardChunks.total_chunks}</div>
                <div className="text-xs text-gray-500">chunks found</div>
                <div className="text-xs text-gray-400">{cardChunks.total_sources} sources</div>
              </div>
            </div>
          </div>

          {/* Category selection */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-medium text-gray-700">Select Categories to Process</h3>
              <div className="flex gap-2">
                <button onClick={selectAllCategories} className="text-xs text-blue-600 hover:text-blue-800 font-medium">Select All</button>
                {selectedCategories.size > 0 && (
                  <button onClick={() => { setSelectedCategories(new Set()); setSelectedPipelines(new Set()); }}
                    className="text-xs text-gray-500 hover:text-gray-700">Clear</button>
                )}
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {Object.entries(cardChunks.category_breakdown || {}).sort((a, b) => b[1] - a[1]).map(([cat, count]) => {
                const isChecked = selectedCategories.has(cat);
                const mapped = CATEGORY_PIPELINE_MAP[cat] || [];
                return (
                  <div key={cat} className="relative">
                    <button onClick={() => toggleCategory(cat)}
                      className={`w-full p-3 rounded-lg border text-center transition-all hover:shadow-sm ${
                        isChecked ? 'border-blue-400 bg-blue-50 ring-2 ring-blue-200' : 'bg-white border-gray-200 hover:border-blue-200'
                      }`}>
                      <div className="flex items-center justify-center gap-1">
                        {isChecked ? <CheckSquare size={14} className="text-blue-600" /> : <Square size={14} className="text-gray-300" />}
                        <span className="text-lg">{CATEGORY_ICONS[cat] || '📄'}</span>
                      </div>
                      <div className="text-xl font-bold text-blue-700">{count}</div>
                      <div className="text-xs text-gray-600 font-medium">{cat}</div>
                      {mapped.length > 0 && (
                        <div className="text-xs text-blue-500 mt-1">→ {mapped.join(', ').replace(/_/g, ' ')}</div>
                      )}
                    </button>
                    <button onClick={(e) => { e.stopPropagation(); viewCategoryChunks(cat); }}
                      className="absolute top-1 right-1 p-1 text-gray-400 hover:text-blue-600 rounded" title="View chunks">
                      <Eye size={14} />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Category chunks viewer */}
          {selectedCategory && categoryChunks.length > 0 && (
            <div className="border border-blue-200 rounded-lg overflow-hidden">
              <div className="p-3 bg-blue-50 flex items-center gap-2">
                <span className="text-lg">{CATEGORY_ICONS[selectedCategory] || '📄'}</span>
                <span className="font-medium text-blue-800">{selectedCategory}</span>
                <span className="text-xs bg-blue-200 text-blue-700 px-2 py-0.5 rounded-full">{categoryChunks.length} chunks</span>
                <button onClick={() => { setSelectedCategory(null); setCategoryChunks([]); }} className="ml-auto text-gray-400 hover:text-gray-600"><X size={16} /></button>
              </div>
              <div className="divide-y max-h-[28rem] overflow-y-auto">
                {categoryChunks.map((chunk, i) => (
                  <div key={i} className="p-3">
                    <div className="flex items-center gap-1.5 mb-2 flex-wrap">
                      <span className="text-xs font-mono bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">{chunk.chunk_id}</span>
                      {chunk.card_name && <span className="text-xs bg-purple-50 text-purple-700 px-1.5 py-0.5 rounded">🃏 {chunk.card_name}</span>}
                      {chunk.card_network && <span className="text-xs bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded">{chunk.card_network}</span>}
                      {chunk.page_type && <span className="text-xs bg-yellow-50 text-yellow-700 px-1.5 py-0.5 rounded">{chunk.page_type}</span>}
                      <span className="text-xs text-gray-400">{chunk.text_length} chars</span>
                    </div>
                    {chunk.source_url && (
                      <a href={chunk.source_url} target="_blank" rel="noopener noreferrer"
                        className="text-xs text-blue-500 hover:underline flex items-center gap-1 mb-1 truncate">
                        <ExternalLink size={10} className="shrink-0" /> {chunk.source_title || chunk.source_url}
                      </a>
                    )}
                    <div className="text-xs text-gray-700 leading-relaxed whitespace-pre-wrap bg-gray-50 p-2.5 rounded border border-gray-100 max-h-48 overflow-y-auto">
                      {chunk.text}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Sources summary */}
          {cardChunks.sources?.length > 0 && (
            <details className="text-xs">
              <summary className="text-gray-500 cursor-pointer hover:text-gray-700 font-medium">
                Sources ({cardChunks.sources.length})
              </summary>
              <div className="mt-2 space-y-1">
                {cardChunks.sources.map((src, i) => (
                  <div key={i} className="flex items-center gap-2 p-2 bg-gray-50 rounded">
                    {src.page_type && <span className="text-xs bg-blue-100 text-blue-700 px-1 rounded">{src.page_type}</span>}
                    <a href={src.source_url} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-500 hover:underline truncate flex-1">
                      {src.source_title || src.source_url}
                    </a>
                    <span className="text-xs text-gray-400">{src.chunk_count} chunks</span>
                  </div>
                ))}
              </div>
            </details>
          )}

          {/* Mapped pipelines */}
          {selectedPipelines.size > 0 && (
            <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
              <h4 className="text-sm font-medium text-blue-800 mb-2">
                Mapped Pipelines ({selectedPipelines.size}) from {selectedCategories.size} categories:
              </h4>
              <div className="flex flex-wrap gap-2">
                {Array.from(selectedPipelines).map(p => {
                  const pInfo = pipelines.find(pi => pi.name === p);
                  return (
                    <span key={p} className="inline-flex items-center gap-1 px-2.5 py-1 bg-white border border-blue-200 rounded-full text-xs text-blue-700">
                      <span>{pInfo?.icon || '📋'}</span> {(p || '').replace(/_/g, ' ')}
                      <button onClick={() => toggle(selectedPipelines, setSelectedPipelines, p)} className="text-blue-400 hover:text-red-500 ml-0.5"><X size={12} /></button>
                    </span>
                  );
                })}
              </div>
            </div>
          )}

          {/* Manual pipeline add */}
          {pipelines.filter(p => !selectedPipelines.has(p.name)).length > 0 && selectedCategories.size > 0 && (
            <details className="text-xs">
              <summary className="text-gray-500 cursor-pointer hover:text-gray-700">Add more pipelines manually</summary>
              <div className="flex flex-wrap gap-2 mt-2">
                {pipelines.filter(p => !selectedPipelines.has(p.name)).map(p => (
                  <button key={p.name} onClick={() => toggle(selectedPipelines, setSelectedPipelines, p.name)}
                    className="px-2 py-1 border border-gray-200 rounded-full text-gray-500 hover:border-blue-300 hover:text-blue-600 flex items-center gap-1">
                    <span>{p.icon}</span> {p.display_name}
                  </button>
                ))}
              </div>
            </details>
          )}

          {/* Actions */}
          <div className="flex gap-3">
            <button onClick={() => { setSelectedCategory(null); setCategoryChunks([]); setCardChunks(null); setSelectedCard(null); setSelectedCategories(new Set()); setSelectedPipelines(new Set()); setStep(1); }}
              className="px-4 py-2 border rounded-lg hover:bg-gray-50 flex items-center gap-1">
              <ChevronLeft size={18} /> Back
            </button>
            <button onClick={runPipelines} disabled={loading || selectedPipelines.size === 0}
              className="flex-1 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center justify-center gap-2 font-medium disabled:opacity-50">
              {loading
                ? <><Loader2 size={20} className="animate-spin" /> Running {selectedPipelines.size} pipelines...</>
                : <><Zap size={20} /> Run {selectedPipelines.size} Pipelines on {selectedCategories.size} Categories</>}
            </button>
          </div>
        </div>
      )}

      {/* ============= STEP 3: RESULTS ============= */}
      {step === 3 && pipelineResults && (
        <div className="space-y-4">
          {/* Card context */}
          <div className="p-4 bg-blue-50 rounded-lg border border-blue-200 flex items-center gap-3">
            <CreditCard size={20} className="text-blue-600" />
            <span className="font-bold text-gray-800">{selectedCard?.card_name}</span>
            {selectedCard?.card_network && <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full">{selectedCard.card_network}</span>}
            {selectedCard?.card_tier && <span className="px-2 py-0.5 bg-purple-100 text-purple-700 text-xs rounded-full">{selectedCard.card_tier}</span>}
            {selectedBank?.bank_name && <span className="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded-full">🏦 {selectedBank.bank_name}</span>}
          </div>

          {/* Summary */}
          <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
            <h3 className="font-bold text-green-800 flex items-center gap-2"><CheckCircle size={20} /> Pipeline Execution Complete</h3>
            <div className="grid grid-cols-3 gap-3 mt-3 text-center">
              <div><div className="text-xl font-bold text-green-700">{pipelineResults.total_benefits || 0}</div><div className="text-xs text-gray-500">Benefits Found</div></div>
              <div><div className="text-xl font-bold text-blue-700">{pipelineResults.pipelines_run || 0}</div><div className="text-xs text-gray-500">Pipelines Run</div></div>
              <div><div className="text-xl font-bold text-purple-700">{((pipelineResults.overall_confidence || 0) * 100).toFixed(0)}%</div><div className="text-xs text-gray-500">Confidence</div></div>
            </div>
          </div>

          {/* Per-pipeline results */}
          {pipelineResults.pipeline_results?.map((pr, idx) => {
            const isExp = expandedResults.has(idx);
            const benefits = pr.benefits || [];
            return (
              <div key={idx} className="border rounded-lg overflow-hidden">
                <div className="p-3 bg-gray-50 cursor-pointer flex items-center gap-2 hover:bg-gray-100"
                  onClick={() => toggle(expandedResults, setExpandedResults, idx)}>
                  <ChevronRight size={16} className={`transition-transform ${isExp ? 'rotate-90' : ''}`} />
                  <span className="text-lg">{pr.icon || '📋'}</span>
                  <span className="font-medium text-gray-700">{(pr.pipeline_name || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</span>
                  <span className={`ml-auto px-2 py-0.5 text-xs rounded-full ${benefits.length > 0 ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                    {benefits.length} benefits
                  </span>
                </div>
                {isExp && benefits.length > 0 && (
                  <div className="divide-y max-h-80 overflow-y-auto">
                    {benefits.map((b, bi) => (
                      <div key={bi} className="p-3">
                        <div className="font-medium text-sm text-gray-800">{b.benefit_name || b.name || 'Unnamed Benefit'}</div>
                        {b.description && <p className="text-xs text-gray-600 mt-1">{b.description}</p>}
                        <div className="flex items-center gap-2 mt-1 flex-wrap">
                          {b.value && <span className="text-xs text-purple-600 font-medium bg-purple-50 px-1.5 py-0.5 rounded">{b.value}</span>}
                          {b.confidence && <span className="text-xs text-gray-400">{(b.confidence * 100).toFixed(0)}% conf</span>}
                        </div>
                        {b.conditions && b.conditions.length > 0 && (
                          <div className="mt-1 flex flex-wrap gap-1">
                            {b.conditions.map((cond, ci) => <span key={ci} className="px-1.5 py-0.5 bg-yellow-50 text-yellow-700 text-xs rounded">{cond}</span>)}
                          </div>
                        )}
                        {b.merchants && b.merchants.length > 0 && (
                          <div className="mt-1 flex flex-wrap gap-1">
                            {b.merchants.map((m, mi) => <span key={mi} className="px-1.5 py-0.5 bg-blue-50 text-blue-700 text-xs rounded">{m}</span>)}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}

          {/* Actions */}
          <div className="flex gap-3">
            <button onClick={() => { setPipelineResults(null); setExpandedResults(new Set()); setStep(2); }}
              className="px-4 py-2 border rounded-lg hover:bg-gray-50 flex items-center gap-1">
              <ChevronLeft size={18} /> Re-run with different pipelines
            </button>
            <button onClick={resetFlow}
              className="flex-1 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center justify-center gap-2 font-medium">
              <RefreshCw size={18} /> Process Another Card
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
