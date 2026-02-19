/**
 * Structured Extraction Wizard (V5)
 *
 * Step 1: Select bank → Depth 0 discovers cards with summaries
 * Step 2: Select cards → Depth 1 sections each card page
 * Step 3: Review card sections + auto-process depth 2-3 (shared benefits)
 * Step 4: Review all extracted benefits by card
 */

import React, { useState, useEffect } from 'react';
import {
  Zap, ChevronRight, ChevronLeft, CheckCircle, AlertCircle,
  Loader2, ExternalLink, RefreshCw, CreditCard, X, Eye,
  CheckSquare, Square, Database, Search, ChevronDown, ChevronUp,
  Layers, Globe
} from 'lucide-react';

const API = 'http://localhost:8000/api/v5/extraction';

const CATEGORY_ICONS = {
  cashback: '💰', lounge: '✈️', golf: '🏌️', dining: '🍽️',
  travel: '🌴', insurance: '🛡️', rewards: '🎁', movie: '🎬',
  fee: '💳', lifestyle: '🎭', general: '📄', overview: '📋',
  benefits: '⭐', requirements: '📝', fees: '💵',
};

const BANKS = [
  { key: 'emirates_nbd', name: 'Emirates NBD' },
  { key: 'fab', name: 'First Abu Dhabi Bank' },
  { key: 'adcb', name: 'Abu Dhabi Commercial Bank' },
  { key: 'mashreq', name: 'Mashreq Bank' },
];

export default function StructuredExtractionWizard() {
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [loadingMsg, setLoadingMsg] = useState('');
  const [error, setError] = useState('');

  // Session
  const [sessionId, setSessionId] = useState(null);
  const [bankKey, setBankKey] = useState('');
  const [bankName, setBankName] = useState('');

  // Step 1: Cards
  const [cards, setCards] = useState([]);
  const [selectedCardIds, setSelectedCardIds] = useState(new Set());

  // Step 2: Card sections (depth 1)
  const [depth1Results, setDepth1Results] = useState(null);
  const [expandedCard, setExpandedCard] = useState(null);
  const [cardSections, setCardSections] = useState({});

  // Step 3: Shared benefits (depth 2-3)
  const [depth2Results, setDepth2Results] = useState(null);

  // Step 4: All benefits by card
  const [selectedViewCard, setSelectedViewCard] = useState(null);
  const [cardBenefits, setCardBenefits] = useState(null);
  const [allBenefits, setAllBenefits] = useState(null);

  const [expandedSections, setExpandedSections] = useState(new Set());

  // ============= STEP 1: Create session & discover cards =============
  const discoverCards = async () => {
    if (!bankKey) { setError('Please select a bank'); return; }
    setLoading(true); setLoadingMsg('Discovering cards from bank listing page...'); setError('');
    try {
      const res = await fetch(`${API}/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bank_key: bankKey, use_playwright: true, max_depth: 3 }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to discover cards');
      setSessionId(data.session_id);
      setBankName(data.bank_name);
      setCards(data.cards || []);
      setStep(2);
    } catch (err) { setError(err.message); }
    finally { setLoading(false); setLoadingMsg(''); }
  };

  // ============= STEP 2: Select cards & process depth 1 =============
  const toggleCard = (cardId) => {
    const next = new Set(selectedCardIds);
    next.has(cardId) ? next.delete(cardId) : next.add(cardId);
    setSelectedCardIds(next);
  };

  const processDepth1 = async () => {
    if (!selectedCardIds.size) { setError('Select at least one card'); return; }
    setLoading(true); setLoadingMsg('Selecting cards...'); setError('');
    try {
      // Select cards
      await fetch(`${API}/sessions/${sessionId}/select-cards`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ card_ids: Array.from(selectedCardIds) }),
      });

      // Process depth 1
      setLoadingMsg('Scraping card detail pages & extracting sections...');
      const res = await fetch(`${API}/sessions/${sessionId}/process-depth1`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Depth 1 processing failed');
      setDepth1Results(data);
      setStep(3);
    } catch (err) { setError(err.message); }
    finally { setLoading(false); setLoadingMsg(''); }
  };

  // Load sections for a card
  const loadCardSections = async (cardId) => {
    if (cardSections[cardId]) { setExpandedCard(expandedCard === cardId ? null : cardId); return; }
    try {
      const res = await fetch(`${API}/sessions/${sessionId}/card-sections/${cardId}`);
      const data = await res.json();
      setCardSections(prev => ({ ...prev, [cardId]: data.sections || [] }));
      setExpandedCard(cardId);
    } catch (err) { setError(err.message); }
  };

  // ============= STEP 3: Process depth 2-3 =============
  const processDepth2 = async () => {
    setLoading(true); setLoadingMsg('Processing shared benefit pages (depth 2-3)...'); setError('');
    try {
      const res = await fetch(`${API}/sessions/${sessionId}/process-depth2`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Depth 2 processing failed');
      setDepth2Results(data);
      // Load all benefits
      const benRes = await fetch(`${API}/sessions/${sessionId}/benefits`);
      const benData = await benRes.json();
      setAllBenefits(benData);
      setStep(4);
    } catch (err) { setError(err.message); }
    finally { setLoading(false); setLoadingMsg(''); }
  };

  // ============= STEP 4: View benefits by card =============
  const loadBenefitsForCard = async (cardName) => {
    setSelectedViewCard(cardName);
    try {
      const res = await fetch(`${API}/sessions/${sessionId}/benefits/by-card/${encodeURIComponent(cardName)}`);
      const data = await res.json();
      setCardBenefits(data);
    } catch (err) { setError(err.message); }
  };

  // ============= Helpers =============
  const resetFlow = () => {
    setStep(1); setSessionId(null); setBankKey(''); setBankName('');
    setCards([]); setSelectedCardIds(new Set());
    setDepth1Results(null); setDepth2Results(null);
    setCardSections({}); setExpandedCard(null);
    setAllBenefits(null); setCardBenefits(null); setSelectedViewCard(null);
    setError('');
  };

  const toggle = (set, key) => {
    const n = new Set(set); n.has(key) ? n.delete(key) : n.add(key);
    return n;
  };

  const stepLabels = ['Discover Cards', 'Select & Scrape', 'Shared Benefits', 'Review All'];

  // ============= RENDER =============
  return (
    <div className="space-y-6">
      {/* Step Indicator */}
      <div className="flex items-center gap-2 flex-wrap">
        {stepLabels.map((label, i) => (
          <React.Fragment key={i}>
            <button onClick={() => { if (i + 1 <= step) setStep(i + 1); }}
              disabled={i + 1 > step}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                step === i + 1 ? 'bg-gradient-to-r from-teal-600 to-blue-600 text-white shadow-sm'
                  : i + 1 < step ? 'bg-teal-100 text-teal-700 hover:bg-teal-200 cursor-pointer'
                  : 'bg-gray-100 text-gray-400 cursor-not-allowed'
              }`}>
              <span className="w-5 h-5 rounded-full flex items-center justify-center text-xs border-2 border-current">
                {i + 1 < step ? '✓' : i + 1}
              </span>
              {label}
            </button>
            {i < 3 && <ChevronRight size={14} className="text-gray-300" />}
          </React.Fragment>
        ))}
        {sessionId && (
          <button onClick={resetFlow} className="ml-auto text-gray-400 hover:text-gray-600 text-sm flex items-center gap-1">
            <RefreshCw size={14} /> Reset
          </button>
        )}
      </div>

      {/* Session badge */}
      {sessionId && bankName && (
        <div className="px-3 py-1.5 bg-teal-50 border border-teal-200 rounded-lg inline-flex items-center gap-2 text-sm">
          <span>🏦</span> <strong>{bankName}</strong>
          <span className="text-gray-400">|</span>
          <span className="text-xs text-gray-500">{sessionId}</span>
        </div>
      )}

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2 text-red-700 text-sm">
          <AlertCircle size={18} className="shrink-0 mt-0.5" />
          <pre className="whitespace-pre-wrap font-sans flex-1">{error}</pre>
          <button onClick={() => setError('')} className="shrink-0"><X size={14} /></button>
        </div>
      )}

      {loading && (
        <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg flex items-center gap-3">
          <Loader2 size={24} className="animate-spin text-blue-600" />
          <span className="text-blue-700 font-medium">{loadingMsg || 'Processing...'}</span>
        </div>
      )}

      {/* ============= STEP 1: SELECT BANK ============= */}
      {step === 1 && !loading && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-gray-800 flex items-center gap-2">
            <Globe size={20} /> Select Bank
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {BANKS.map(bank => (
              <button key={bank.key} onClick={() => setBankKey(bank.key)}
                className={`p-4 rounded-lg border text-center transition-all ${
                  bankKey === bank.key ? 'border-teal-400 bg-teal-50 ring-2 ring-teal-200 shadow-sm' : 'bg-white hover:border-teal-200'
                }`}>
                <div className="text-2xl mb-1">🏦</div>
                <div className="font-medium text-gray-800 text-sm">{bank.name}</div>
              </button>
            ))}
          </div>
          <button onClick={discoverCards} disabled={!bankKey || loading}
            className="w-full py-3 bg-gradient-to-r from-teal-600 to-blue-600 text-white rounded-lg hover:from-teal-700 hover:to-blue-700 flex items-center justify-center gap-2 font-medium disabled:opacity-50">
            <Search size={20} /> Discover Cards (Depth 0)
          </button>
        </div>
      )}

      {/* ============= STEP 2: SELECT CARDS ============= */}
      {step === 2 && !loading && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-800">
              {cards.length} Cards Discovered — Select cards to scrape
            </h2>
            <div className="flex gap-2 text-xs">
              <button onClick={() => setSelectedCardIds(new Set(cards.map(c => c.card_id)))}
                className="text-teal-600 hover:text-teal-800">Select All</button>
              <button onClick={() => setSelectedCardIds(new Set())}
                className="text-gray-500 hover:text-gray-700">Clear</button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {cards.map(card => {
              const isSelected = selectedCardIds.has(card.card_id);
              return (
                <div key={card.card_id}
                  onClick={() => toggleCard(card.card_id)}
                  className={`p-4 border rounded-lg cursor-pointer transition-all ${
                    isSelected ? 'border-teal-400 bg-teal-50 ring-2 ring-teal-200' : 'hover:border-teal-200'
                  }`}>
                  <div className="flex items-start gap-3">
                    {isSelected ? <CheckSquare size={18} className="text-teal-600 mt-0.5 shrink-0" /> : <Square size={18} className="text-gray-300 mt-0.5 shrink-0" />}
                    <div className="flex-1 min-w-0">
                      <h4 className="font-medium text-gray-800 text-sm">{card.card_name}</h4>
                      <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                        {card.card_network && <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 text-xs rounded">{card.card_network}</span>}
                        {card.card_tier && <span className="px-1.5 py-0.5 bg-purple-100 text-purple-700 text-xs rounded">{card.card_tier}</span>}
                      </div>
                      {card.summary_benefits && (
                        <p className="text-xs text-gray-500 mt-1.5 line-clamp-2">{card.summary_benefits}</p>
                      )}
                    </div>
                    {card.card_image_url && <img src={card.card_image_url} alt="" className="w-16 h-10 object-contain rounded" />}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="flex gap-3">
            <button onClick={() => setStep(1)} className="px-4 py-2 border rounded-lg hover:bg-gray-50 flex items-center gap-1">
              <ChevronLeft size={18} /> Back
            </button>
            <button onClick={processDepth1} disabled={!selectedCardIds.size || loading}
              className="flex-1 py-3 bg-gradient-to-r from-teal-600 to-blue-600 text-white rounded-lg hover:from-teal-700 hover:to-blue-700 flex items-center justify-center gap-2 font-medium disabled:opacity-50">
              <Layers size={20} /> Scrape {selectedCardIds.size} Card{selectedCardIds.size !== 1 ? 's' : ''} (Depth 1)
            </button>
          </div>
        </div>
      )}

      {/* ============= STEP 3: REVIEW DEPTH 1 + PROCESS DEPTH 2-3 ============= */}
      {step === 3 && !loading && (
        <div className="space-y-4">
          {depth1Results && (
            <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
              <h3 className="font-bold text-green-800 flex items-center gap-2">
                <CheckCircle size={20} /> Depth 1 Complete
              </h3>
              <div className="grid grid-cols-3 gap-3 mt-2 text-center">
                <div><div className="text-xl font-bold text-green-700">{depth1Results.cards_processed}</div><div className="text-xs text-gray-500">Cards Processed</div></div>
                <div><div className="text-xl font-bold text-blue-700">{depth1Results.total_sections}</div><div className="text-xs text-gray-500">Sections Found</div></div>
                <div><div className="text-xl font-bold text-purple-700">{depth1Results.depth2_urls_discovered}</div><div className="text-xs text-gray-500">Depth 2 URLs</div></div>
              </div>
            </div>
          )}

          {/* Card sections preview */}
          {depth1Results?.results?.map(result => (
            <div key={result.card_id} className="border rounded-lg overflow-hidden">
              <div className="p-3 bg-gray-50 flex items-center gap-2 cursor-pointer hover:bg-gray-100"
                onClick={() => loadCardSections(result.card_id)}>
                <CreditCard size={16} className="text-gray-400" />
                <span className="font-medium text-gray-700">{result.card_name}</span>
                <span className="text-xs bg-teal-100 text-teal-700 px-2 py-0.5 rounded-full ml-auto">{result.sections} sections</span>
                {expandedCard === result.card_id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </div>
              {expandedCard === result.card_id && cardSections[result.card_id] && (
                <div className="divide-y">
                  {cardSections[result.card_id].map((sec, i) => (
                    <div key={i} className="p-3">
                      <div className="flex items-center gap-2 mb-1">
                        <span>{CATEGORY_ICONS[sec.section_type] || '📄'}</span>
                        <span className="font-medium text-sm text-gray-700">{sec.section_name}</span>
                        <span className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">{sec.section_type}</span>
                      </div>
                      <p className="text-xs text-gray-600 whitespace-pre-wrap bg-gray-50 p-2 rounded max-h-32 overflow-y-auto">{sec.content}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}

          <button onClick={processDepth2} disabled={loading}
            className="w-full py-3 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-700 hover:to-purple-700 flex items-center justify-center gap-2 font-medium disabled:opacity-50">
            <Zap size={20} /> Process Shared Benefit Pages (Depth 2-3)
          </button>
        </div>
      )}

      {/* ============= STEP 4: REVIEW ALL BENEFITS ============= */}
      {step === 4 && !loading && (
        <div className="space-y-4">
          {depth2Results && (
            <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
              <h3 className="font-bold text-green-800 flex items-center gap-2">
                <CheckCircle size={20} /> All Depths Complete
              </h3>
              <div className="grid grid-cols-4 gap-3 mt-2 text-center">
                <div><div className="text-xl font-bold text-green-700">{depth2Results.urls_processed}</div><div className="text-xs text-gray-500">URLs Processed</div></div>
                <div><div className="text-xl font-bold text-blue-700">{depth2Results.urls_cached}</div><div className="text-xs text-gray-500">URLs Cached</div></div>
                <div><div className="text-xl font-bold text-purple-700">{depth2Results.benefits_extracted}</div><div className="text-xs text-gray-500">Benefits Found</div></div>
                <div><div className="text-xl font-bold text-orange-700">{depth2Results.depth3_urls_discovered}</div><div className="text-xs text-gray-500">Depth 3 URLs</div></div>
              </div>
            </div>
          )}

          {/* Category breakdown */}
          {allBenefits?.category_breakdown && (
            <div>
              <h3 className="font-medium text-gray-700 mb-2">Benefits by Category</h3>
              <div className="flex flex-wrap gap-2">
                {Object.entries(allBenefits.category_breakdown).sort((a, b) => b[1] - a[1]).map(([cat, count]) => (
                  <span key={cat} className="inline-flex items-center gap-1 px-3 py-1.5 bg-white border rounded-full text-sm">
                    <span>{CATEGORY_ICONS[cat] || '📄'}</span>
                    <span className="font-medium">{cat}</span>
                    <span className="text-xs text-gray-400">{count}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* View by card */}
          <div>
            <h3 className="font-medium text-gray-700 mb-2">View Benefits by Card</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {cards.filter(c => selectedCardIds.has(c.card_id)).map(card => (
                <button key={card.card_id} onClick={() => loadBenefitsForCard(card.card_name)}
                  className={`p-3 border rounded-lg text-left transition-all ${
                    selectedViewCard === card.card_name ? 'border-teal-400 bg-teal-50' : 'hover:border-teal-200'
                  }`}>
                  <div className="flex items-center gap-2">
                    <CreditCard size={16} className="text-gray-400" />
                    <span className="font-medium text-sm">{card.card_name}</span>
                    {card.card_network && <span className="text-xs bg-blue-100 text-blue-700 px-1 rounded">{card.card_network}</span>}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Card benefits display */}
          {cardBenefits && selectedViewCard && (
            <div className="border rounded-lg overflow-hidden">
              <div className="p-3 bg-teal-50 border-b border-teal-200">
                <h4 className="font-bold text-teal-800">{selectedViewCard}</h4>
                <p className="text-xs text-teal-600 mt-0.5">
                  {cardBenefits.card_sections?.length || 0} card sections · {cardBenefits.shared_benefits?.length || 0} shared benefits
                </p>
              </div>

              {/* Card-specific sections (depth 1) */}
              {cardBenefits.card_sections?.length > 0 && (
                <div className="p-3 border-b">
                  <h5 className="text-sm font-medium text-gray-700 mb-2">📄 Card-Specific Sections (Depth 1)</h5>
                  <div className="space-y-2">
                    {cardBenefits.card_sections.map((sec, i) => (
                      <details key={i} className="bg-gray-50 rounded border">
                        <summary className="p-2 cursor-pointer text-sm font-medium flex items-center gap-2">
                          <span>{CATEGORY_ICONS[sec.section_type] || '📄'}</span>
                          {sec.section_name}
                          <span className="text-xs text-gray-400 ml-auto">{sec.section_type}</span>
                        </summary>
                        <div className="p-2 text-xs text-gray-600 whitespace-pre-wrap border-t">{sec.content}</div>
                      </details>
                    ))}
                  </div>
                </div>
              )}

              {/* Shared benefits (depth 2-3) */}
              {cardBenefits.shared_benefits?.length > 0 && (
                <div className="p-3">
                  <h5 className="text-sm font-medium text-gray-700 mb-2">🔗 Shared Benefits (Depth 2-3)</h5>
                  <div className="space-y-2">
                    {cardBenefits.shared_benefits.map((ben, i) => (
                      <details key={i} className="bg-gray-50 rounded border">
                        <summary className="p-2 cursor-pointer text-sm flex items-center gap-2">
                          <span>{CATEGORY_ICONS[ben.benefit_category] || '📄'}</span>
                          <span className="font-medium">{ben.benefit_name}</span>
                          <span className="text-xs bg-blue-100 text-blue-700 px-1 rounded ml-auto">{ben.benefit_category}</span>
                        </summary>
                        <div className="p-2 border-t space-y-2">
                          <p className="text-xs text-gray-600 whitespace-pre-wrap">{ben.benefit_text}</p>
                          {ben.eligible_card_names?.length > 0 && (
                            <div>
                              <span className="text-xs font-medium text-gray-500">Eligible Cards:</span>
                              <div className="flex flex-wrap gap-1 mt-1">
                                {ben.eligible_card_names.map((cn, ci) => (
                                  <span key={ci} className={`px-1.5 py-0.5 text-xs rounded ${
                                    cn === selectedViewCard ? 'bg-teal-100 text-teal-700 font-medium' : 'bg-gray-100 text-gray-600'
                                  }`}>{cn}</span>
                                ))}
                              </div>
                            </div>
                          )}
                          {ben.conditions?.length > 0 && (
                            <div>
                              <span className="text-xs font-medium text-gray-500">Conditions:</span>
                              {ben.conditions.map((c, ci) => <p key={ci} className="text-xs text-yellow-700 mt-0.5">• {c}</p>)}
                            </div>
                          )}
                          {ben.validity && <p className="text-xs text-purple-600">📅 {ben.validity}</p>}
                          {ben.source_url && (
                            <a href={ben.source_url} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-500 hover:underline flex items-center gap-1">
                              <ExternalLink size={10} /> {ben.source_url}
                            </a>
                          )}
                        </div>
                      </details>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="flex gap-3">
            <button onClick={() => setStep(3)} className="px-4 py-2 border rounded-lg hover:bg-gray-50 flex items-center gap-1">
              <ChevronLeft size={18} /> Back
            </button>
            <button onClick={resetFlow}
              className="flex-1 py-3 bg-gradient-to-r from-teal-600 to-blue-600 text-white rounded-lg hover:from-teal-700 hover:to-blue-700 flex items-center justify-center gap-2 font-medium">
              <RefreshCw size={18} /> Start New Extraction
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
