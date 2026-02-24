/**
 * Structured Extraction Wizard - V5
 *
 * Two input modes:
 *   A. Bank-Wide: Select bank, Depth 0 discovers cards with summaries
 *   B. Single Card: Paste card URL, auto-detect bank/card
 *
 * Step 1: Choose mode and input, Create session
 * Step 2: Select cards, Depth 1 sections each card page
 * Step 3: Review card sections + manage URLs, process depth 2-3
 * Step 4: Review depth 2-3 sections, Store approved to DataStore
 */

import React, { useState, useEffect } from 'react';
import {
  Zap, ChevronRight, ChevronLeft, CheckCircle, AlertCircle,
  Loader2, ExternalLink, RefreshCw, CreditCard, X, Eye,
  CheckSquare, Square, Database, Search, ChevronDown, ChevronUp,
  Layers, Globe, Link, Building2, Settings2
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

const QUICK_EXAMPLES = [
  { name: 'ENBD Duo', url: 'https://www.emiratesnbd.com/en/cards/credit-cards/duo-credit-card' },
  { name: 'ENBD Platinum MC', url: 'https://www.emiratesnbd.com/en/cards/credit-cards/mastercard-platinum-credit-card' },
  { name: 'FAB Cashback', url: 'https://www.bankfab.com/en-ae/personal/cards/credit-cards/cashback-credit-card' },
  { name: 'ADCB TouchPoints', url: 'https://www.adcb.com/en/personal/cards/credit-cards/touchpoints-platinum' },
];

export default function StructuredExtractionWizard() {
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [loadingMsg, setLoadingMsg] = useState('');
  const [error, setError] = useState('');

  // Step 1: Input mode
  const [mode, setMode] = useState('bank_wide'); // bank_wide | single_card
  const [bankKey, setBankKey] = useState('');
  const [customBankUrl, setCustomBankUrl] = useState('');
  const [singleCardUrl, setSingleCardUrl] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [usePlaywright, setUsePlaywright] = useState(true);
  const [maxDepth, setMaxDepth] = useState(3);

  // Session
  const [sessionId, setSessionId] = useState(null);
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
  const createSession = async () => {
    setError('');
    const body = { use_playwright: usePlaywright, max_depth: maxDepth };

    if (mode === 'single_card') {
      if (!singleCardUrl.trim()) { setError('Please enter a card URL'); return; }
      body.mode = 'single_card';
      body.single_card_url = singleCardUrl.trim();
    } else {
      // bank_wide
      if (!bankKey && !customBankUrl.trim()) { setError('Please select a bank or enter a bank URL'); return; }
      body.mode = 'bank_wide';
      if (bankKey) body.bank_key = bankKey;
      if (customBankUrl.trim()) body.custom_bank_url = customBankUrl.trim();
    }

    setLoading(true);
    setLoadingMsg(mode === 'single_card' ? 'Creating session for card...' : 'Discovering cards from bank listing page...');
    try {
      const res = await fetch(`${API}/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to create session');
      setSessionId(data.session_id);
      setBankName(data.bank_name);
      setCards(data.cards || []);
      // For single card, auto-select it
      if (mode === 'single_card' && data.cards?.length === 1) {
        setSelectedCardIds(new Set([data.cards[0].card_id]));
      }
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
      const selRes = await fetch(`${API}/sessions/${sessionId}/select-cards`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ card_ids: Array.from(selectedCardIds) }),
      });
      if (!selRes.ok) {
        const selData = await selRes.json();
        throw new Error(selData.detail || 'Failed to select cards');
      }

      // Process depth 1
      setLoadingMsg('Scraping card detail pages & extracting sections...');
      const res = await fetch(`${API}/sessions/${sessionId}/process-depth1`, { method: 'POST' });
      const data = await res.json();
      console.log('[V5] Depth 1 response:', data);
      if (!res.ok) throw new Error(data.detail || 'Depth 1 processing failed');
      setDepth1Results(data);

      // Auto-load sections for the first card
      if (data.results?.length) {
        const firstCard = data.results[0];
        if (firstCard.card_id && firstCard.sections > 0) {
          try {
            const secRes = await fetch(`${API}/sessions/${sessionId}/card-sections/${firstCard.card_id}`);
            const secData = await secRes.json();
            setCardSections(prev => ({ ...prev, [firstCard.card_id]: secData }));
            setExpandedCard(firstCard.card_id);
          } catch (e) { console.warn('Failed to auto-load sections:', e); }
        }
      }

      setStep(3);
    } catch (err) {
      console.error('[V5] Depth 1 error:', err);
      setError(err.message);
    }
    finally { setLoading(false); setLoadingMsg(''); }
  };

  // Load sections for a card
  const loadCardSections = async (cardId, forceReload = false) => {
    if (!forceReload && expandedCard === cardId && cardSections[cardId]) {
      setExpandedCard(null);
      return;
    }
    try {
      const res = await fetch(`${API}/sessions/${sessionId}/card-sections/${cardId}`);
      const data = await res.json();
      console.log('[V5] Card sections:', data);
      setCardSections(prev => ({ ...prev, [cardId]: data }));
      setExpandedCard(cardId);
    } catch (err) { setError(err.message); }
  };

  // Delete a section
  const deleteSection = async (sectionId, cardId) => {
    if (!window.confirm('Delete this section? Its depth-2 URLs will be skipped.')) return;
    try {
      const res = await fetch(`${API}/sessions/${sessionId}/sections/${sectionId}`, { method: 'DELETE' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Delete failed');
      // Reload sections
      await loadCardSections(cardId, true);
    } catch (err) { setError(err.message); }
  };

  // Toggle section approval
  const toggleSectionApproval = async (sectionId, cardId) => {
    try {
      const res = await fetch(`${API}/sessions/${sessionId}/sections/${sectionId}/toggle-approval`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Toggle failed');
      await loadCardSections(cardId, true);
    } catch (err) { setError(err.message); }
  };

  // ============= STEP 3: Process depth 2-3 =============
  const processDepth2 = async () => {
    setLoading(true); setLoadingMsg('Scraping & sectioning benefit pages (depth 2-3)...'); setError('');
    try {
      const res = await fetch(`${API}/sessions/${sessionId}/process-depth2`, { method: 'POST' });
      const data = await res.json();
      console.log('[V5] Depth 2-3 response:', data);
      if (!res.ok) throw new Error(data.detail || 'Depth 2 processing failed');
      setDepth2Results(data);
      // Load depth2 sections for review
      await loadDepth2Sections();
      setStep(4);
    } catch (err) { setError(err.message); }
    finally { setLoading(false); setLoadingMsg(''); }
  };

  // ============= STEP 4: Review & manage depth 2-3 sections =============
  const [d2Sections, setD2Sections] = useState(null);
  const [expandedD2Url, setExpandedD2Url] = useState(null);
  const [storeResult, setStoreResult] = useState(null);

  const loadDepth2Sections = async () => {
    try {
      const res = await fetch(`${API}/sessions/${sessionId}/depth2-sections`);
      const data = await res.json();
      setD2Sections(data);
    } catch (err) { setError(err.message); }
  };

  const deleteD2Section = async (sectionId) => {
    if (!window.confirm('Delete this section? It will not be stored.')) return;
    try {
      await fetch(`${API}/sessions/${sessionId}/depth2-sections/${sectionId}`, { method: 'DELETE' });
      await loadDepth2Sections();
    } catch (err) { setError(err.message); }
  };

  const toggleD2Section = async (sectionId) => {
    try {
      await fetch(`${API}/sessions/${sessionId}/depth2-sections/${sectionId}/toggle`, { method: 'POST' });
      await loadDepth2Sections();
    } catch (err) { setError(err.message); }
  };

  const storeApproved = async () => {
    setLoading(true); setLoadingMsg('Storing approved sections...'); setError('');
    try {
      const res = await fetch(`${API}/sessions/${sessionId}/store-approved`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Store failed');
      setStoreResult(data);
      await loadDepth2Sections();
    } catch (err) { setError(err.message); }
    finally { setLoading(false); setLoadingMsg(''); }
  };

  // ============= Helpers =============
  const resetFlow = () => {
    setStep(1); setSessionId(null); setBankKey(''); setBankName('');
    setMode('bank_wide'); setSingleCardUrl(''); setCustomBankUrl('');
    setCards([]); setSelectedCardIds(new Set());
    setDepth1Results(null); setDepth2Results(null);
    setCardSections({}); setExpandedCard(null);
    setAllBenefits(null); setCardBenefits(null); setSelectedViewCard(null);
    setD2Sections(null); setStoreResult(null); setExpandedD2Url(null);
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

      {/* ============= STEP 1: INPUT MODE ============= */}
      {step === 1 && !loading && (
        <div className="space-y-5">
          {/* Mode Selection */}
          <div className="grid md:grid-cols-2 gap-4">
            <button onClick={() => setMode('bank_wide')}
              className={`p-5 rounded-lg border-2 text-left transition-all ${
                mode === 'bank_wide' ? 'border-teal-500 bg-teal-50 ring-1 ring-teal-200' : 'border-gray-200 hover:border-gray-300'
              }`}>
              <Building2 className={`mb-2 ${mode === 'bank_wide' ? 'text-teal-600' : 'text-gray-400'}`} size={28} />
              <h3 className="font-semibold text-gray-800">Bank-Wide Discovery</h3>
              <p className="text-xs text-gray-500 mt-1">Discover all credit cards from a bank</p>
            </button>
            <button onClick={() => setMode('single_card')}
              className={`p-5 rounded-lg border-2 text-left transition-all ${
                mode === 'single_card' ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-200' : 'border-gray-200 hover:border-gray-300'
              }`}>
              <CreditCard className={`mb-2 ${mode === 'single_card' ? 'text-blue-600' : 'text-gray-400'}`} size={28} />
              <h3 className="font-semibold text-gray-800">Single Card URL</h3>
              <p className="text-xs text-gray-500 mt-1">Extract from a specific card page URL</p>
            </button>
          </div>

          {/* Bank-Wide: Bank selection + optional custom URL */}
          {mode === 'bank_wide' && (
            <div className="space-y-3">
              <label className="block text-sm font-medium text-gray-700">Select Bank</label>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {BANKS.map(bank => (
                  <button key={bank.key} onClick={() => { setBankKey(bank.key); setCustomBankUrl(''); }}
                    className={`p-3 rounded-lg border text-center transition-all ${
                      bankKey === bank.key ? 'border-teal-400 bg-teal-50 ring-2 ring-teal-200 shadow-sm' : 'bg-white hover:border-teal-200'
                    }`}>
                    <div className="text-xl mb-0.5">🏦</div>
                    <div className="font-medium text-gray-800 text-sm">{bank.name}</div>
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-2 text-xs text-gray-400">
                <div className="flex-1 h-px bg-gray-200" /> or enter a custom bank URL <div className="flex-1 h-px bg-gray-200" />
              </div>
              <input type="url" value={customBankUrl}
                onChange={(e) => { setCustomBankUrl(e.target.value); if (e.target.value) setBankKey(''); }}
                placeholder="https://www.bank.com/credit-cards"
                className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-teal-500 focus:border-teal-500 text-sm" />
            </div>
          )}

          {/* Single Card: URL input + quick examples */}
          {mode === 'single_card' && (
            <div className="space-y-3">
              <label className="block text-sm font-medium text-gray-700">Card Page URL</label>
              <input type="url" value={singleCardUrl}
                onChange={(e) => setSingleCardUrl(e.target.value)}
                placeholder="https://www.bank.com/credit-cards/card-name"
                className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm" />
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs text-gray-500">Quick examples:</span>
                {QUICK_EXAMPLES.map(ex => (
                  <button key={ex.name} onClick={() => setSingleCardUrl(ex.url)}
                    className="text-xs px-2 py-1 bg-gray-100 hover:bg-gray-200 rounded-full text-gray-600 transition-colors">
                    {ex.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Advanced Options */}
          <div className="border rounded-lg">
            <button onClick={() => setShowAdvanced(!showAdvanced)}
              className="w-full p-3 flex items-center justify-between text-left hover:bg-gray-50 rounded-lg">
              <span className="flex items-center gap-2 font-medium text-sm text-gray-700">
                <Settings2 size={16} /> Advanced Options
              </span>
              {showAdvanced ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </button>
            {showAdvanced && (
              <div className="p-4 border-t space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-medium">Playwright / Chromium</div>
                    <div className="text-xs text-gray-500">Use browser for JS-rendered pages</div>
                  </div>
                  <button onClick={() => setUsePlaywright(!usePlaywright)}
                    className={`w-11 h-6 rounded-full transition-colors ${usePlaywright ? 'bg-purple-600' : 'bg-gray-300'}`}>
                    <div className={`w-5 h-5 bg-white rounded-full shadow transform transition-transform ${usePlaywright ? 'translate-x-5' : 'translate-x-0.5'}`} />
                  </button>
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-medium">Max Crawl Depth</div>
                    <div className="text-xs text-gray-500">How many levels of links to follow</div>
                  </div>
                  <select value={maxDepth} onChange={(e) => setMaxDepth(parseInt(e.target.value))}
                    className="border rounded px-2 py-1 text-sm">
                    <option value={1}>1 (card page only)</option>
                    <option value={2}>2 (+ shared benefits)</option>
                    <option value={3}>3 (+ deeper links)</option>
                  </select>
                </div>
              </div>
            )}
          </div>

          {/* Go Button */}
          <button onClick={createSession}
            disabled={loading || (mode === 'bank_wide' && !bankKey && !customBankUrl.trim()) || (mode === 'single_card' && !singleCardUrl.trim())}
            className="w-full py-3 bg-gradient-to-r from-teal-600 to-blue-600 text-white rounded-lg hover:from-teal-700 hover:to-blue-700 flex items-center justify-center gap-2 font-medium disabled:opacity-50 transition-all">
            <Search size={20} />
            {mode === 'bank_wide' ? 'Discover Cards (Depth 0)' : 'Extract Card (Single URL)'}
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

          {!depth1Results && (
            <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg text-yellow-700 text-sm">
              No depth 1 results available. Try going back and re-processing.
            </div>
          )}

          {/* Card sections preview */}
          {depth1Results?.results?.length > 0 ? (
            depth1Results.results.map(result => (
              <div key={result.card_id} className="border rounded-lg overflow-hidden">
                <div className="p-3 bg-gray-50 flex items-center gap-2 cursor-pointer hover:bg-gray-100"
                  onClick={() => loadCardSections(result.card_id)}>
                  <CreditCard size={16} className="text-gray-400" />
                  <span className="font-medium text-gray-700">{result.card_name}</span>
                  {result.error && <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded-full">Error: {result.error}</span>}
                  <span className="text-xs bg-teal-100 text-teal-700 px-2 py-0.5 rounded-full ml-auto">{result.sections} sections</span>
                  <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full">{result.urls_discovered} URLs</span>
                  {expandedCard === result.card_id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                </div>
                {expandedCard === result.card_id && cardSections[result.card_id] && (
                  <div className="divide-y">
                    {(cardSections[result.card_id].sections || []).length === 0 && (
                      <div className="p-3 text-sm text-gray-500">No sections extracted from this card page.</div>
                    )}
                    {(cardSections[result.card_id].sections || []).map((sec, i) => {
                      const isApproved = sec.is_approved !== false;
                      const isSubSection = !!sec.parent_section;
                      return (
                        <div key={sec.section_id || i} className={`p-3 ${!isApproved ? 'opacity-50 bg-gray-50' : ''} ${isSubSection ? 'ml-6 border-l-2 border-teal-200' : ''}`}>
                          <div className="flex items-center gap-2 mb-1">
                            <button onClick={(e) => { e.stopPropagation(); toggleSectionApproval(sec.section_id, result.card_id); }}
                              className="shrink-0" title={isApproved ? 'Click to skip this section' : 'Click to include this section'}>
                              {isApproved ? <CheckSquare size={16} className="text-teal-600" /> : <Square size={16} className="text-gray-400" />}
                            </button>
                            <span>{CATEGORY_ICONS[sec.section_type] || '📄'}</span>
                            <span className="font-medium text-sm text-gray-700 flex-1">{sec.heading_text || sec.section_name}</span>
                            {sec.is_expandable && <span className="text-xs bg-orange-100 text-orange-700 px-1.5 py-0.5 rounded">expandable</span>}
                            {isSubSection && <span className="text-xs bg-teal-100 text-teal-700 px-1.5 py-0.5 rounded">sub-section</span>}
                            <span className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">{sec.section_type}</span>
                            {sec.link_count > 0 && (
                              <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">{sec.link_count} links</span>
                            )}
                            {sec.mapped_url_count > 0 && (
                              <span className="text-xs bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded">{sec.mapped_url_count} depth-2</span>
                            )}
                            <button onClick={(e) => { e.stopPropagation(); deleteSection(sec.section_id, result.card_id); }}
                              className="text-red-400 hover:text-red-600 shrink-0" title="Delete section">
                              <X size={14} />
                            </button>
                          </div>
                          <div className={isSubSection ? 'ml-2' : 'ml-7'}>
                            <p className="text-xs text-gray-600 whitespace-pre-wrap bg-white border p-2 rounded max-h-32 overflow-y-auto">{sec.content}</p>
                            {/* Mapped URLs */}
                            {sec.mapped_urls?.length > 0 && (
                              <div className="mt-2 space-y-1">
                                <span className="text-xs font-medium text-gray-500">Depth 2 URLs from this section:</span>
                                {sec.mapped_urls.map((u, ui) => (
                                  <div key={ui} className="flex items-center gap-1.5 text-xs">
                                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                                      u.status === 'skipped' ? 'bg-gray-300' : u.status === 'completed' ? 'bg-green-400' : 'bg-blue-400'
                                    }`} />
                                    <a href={u.url} target="_blank" rel="noopener noreferrer"
                                      className="text-blue-600 hover:underline truncate flex-1" title={u.url}>
                                      {u.title || u.url.split('/').pop() || u.url}
                                    </a>
                                    <span className="text-gray-400 shrink-0">{u.status}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}

                    {/* Unmapped URLs */}
                    {cardSections[result.card_id].unmapped_urls?.length > 0 && (
                      <div className="p-3 bg-yellow-50">
                        <span className="text-xs font-medium text-yellow-700">
                          {cardSections[result.card_id].unmapped_url_count} URLs not mapped to any section:
                        </span>
                        <div className="mt-1 space-y-0.5">
                          {cardSections[result.card_id].unmapped_urls.slice(0, 10).map((u, ui) => (
                            <div key={ui} className="flex items-center gap-1.5 text-xs">
                              <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 shrink-0" />
                              <a href={u.url} target="_blank" rel="noopener noreferrer"
                                className="text-blue-600 hover:underline truncate flex-1">
                                {u.title || u.url.split('/').pop() || u.url}
                              </a>
                            </div>
                          ))}
                          {cardSections[result.card_id].unmapped_url_count > 10 && (
                            <span className="text-xs text-gray-400">+{cardSections[result.card_id].unmapped_url_count - 10} more</span>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))
          ) : depth1Results && (
            <div className="p-4 bg-gray-50 border rounded-lg text-gray-500 text-sm">
              No card results returned. Check server logs for errors.
            </div>
          )}

          <div className="flex gap-3">
            <button onClick={() => setStep(2)} className="px-4 py-2 border rounded-lg hover:bg-gray-50 flex items-center gap-1">
              <ChevronLeft size={18} /> Back
            </button>
            <button onClick={processDepth2} disabled={loading || !depth1Results?.depth2_urls_discovered}
              className="flex-1 py-3 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-700 hover:to-purple-700 flex items-center justify-center gap-2 font-medium disabled:opacity-50">
              <Zap size={20} /> Process Shared Benefit Pages (Depth 2-3)
            </button>
          </div>
        </div>
      )}

      {/* ============= STEP 4: REVIEW DEPTH 2-3 SECTIONS ============= */}
      {step === 4 && !loading && (
        <div className="space-y-4">
          {/* Stats */}
          {depth2Results && (
            <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <h3 className="font-bold text-blue-800 flex items-center gap-2">
                <CheckCircle size={20} /> Depth 2-3 Scraped — Review Sections
              </h3>
              <div className="grid grid-cols-4 gap-3 mt-2 text-center">
                <div><div className="text-xl font-bold text-green-700">{depth2Results.urls_processed}</div><div className="text-xs text-gray-500">URLs Processed</div></div>
                <div><div className="text-xl font-bold text-blue-700">{depth2Results.total_sections}</div><div className="text-xs text-gray-500">Sections Found</div></div>
                <div><div className="text-xl font-bold text-purple-700">{depth2Results.depth3_urls_discovered}</div><div className="text-xs text-gray-500">Depth 3 URLs</div></div>
                <div><div className="text-xl font-bold text-gray-500">{depth2Results.urls_cached}</div><div className="text-xs text-gray-500">Cached</div></div>
              </div>
              <p className="text-xs text-blue-600 mt-2">Review sections below. Uncheck or delete unwanted ones, then click "Store Approved" to save.</p>
            </div>
          )}

          {storeResult && (
            <div className="p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm space-y-1">
              <div className="flex items-center gap-2 font-medium">
                <CheckCircle size={16} /> Stored {storeResult.stored} sections + {storeResult.total_raw_records || 0} card records to database.
              </div>
              {storeResult.raw_records?.map((r, i) => (
                <div key={i} className="text-xs text-green-600 ml-6">
                  📄 {r.card_name}: {r.sources} sections, {(r.chars || 0).toLocaleString()} chars → Data Store ready
                </div>
              ))}
              <p className="text-xs text-green-500 ml-6">Go to "Data Store & Vectorize" tab to view and vectorize this data.</p>
            </div>
          )}

          {/* Sections grouped by source URL */}
          {d2Sections?.urls?.map(urlGroup => (
            <div key={urlGroup.source_url} className="border rounded-lg overflow-hidden">
              <div className="p-3 bg-gray-50 cursor-pointer hover:bg-gray-100 flex items-center gap-2"
                onClick={() => setExpandedD2Url(expandedD2Url === urlGroup.source_url ? null : urlGroup.source_url)}>
                <ExternalLink size={14} className="text-blue-500 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-gray-700 truncate">{urlGroup.source_url}</div>
                  <div className="flex gap-2 mt-0.5 flex-wrap">
                    <span className="text-xs text-gray-500">Depth {urlGroup.source_depth}</span>
                    {urlGroup.source_d1_section && <span className="text-xs bg-teal-100 text-teal-700 px-1.5 rounded">from: {urlGroup.source_d1_section}</span>}
                    {urlGroup.source_card_names?.slice(0, 2).map((cn, i) => (
                      <span key={i} className="text-xs bg-blue-100 text-blue-700 px-1.5 rounded">{cn}</span>
                    ))}
                  </div>
                </div>
                <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full">{urlGroup.sections.length} sections</span>
                {expandedD2Url === urlGroup.source_url ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </div>

              {expandedD2Url === urlGroup.source_url && (
                <div className="divide-y">
                  {urlGroup.sections.map((sec) => {
                    const isApproved = sec.is_approved !== false;
                    const isStored = sec.is_stored === true;
                    const isSubSection = !!sec.parent_section;
                    return (
                      <div key={sec.section_id} className={`p-3 ${!isApproved ? 'opacity-50 bg-gray-50' : ''} ${isStored ? 'bg-green-50' : ''} ${isSubSection ? 'ml-5 border-l-2 border-teal-200' : ''}`}>
                        <div className="flex items-center gap-2 mb-1">
                          <button onClick={() => toggleD2Section(sec.section_id)} className="shrink-0"
                            title={isApproved ? 'Skip' : 'Include'} disabled={isStored}>
                            {isApproved ? <CheckSquare size={16} className="text-teal-600" /> : <Square size={16} className="text-gray-400" />}
                          </button>
                          <span>{CATEGORY_ICONS[sec.section_type] || '📄'}</span>
                          <span className="font-medium text-sm text-gray-700 flex-1">{sec.heading_text || sec.section_name}</span>
                          {isSubSection && <span className="text-xs bg-teal-100 text-teal-700 px-1 rounded">sub</span>}
                          <span className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">{sec.section_type}</span>
                          {sec.link_count > 0 && <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">{sec.link_count} links</span>}
                          {isStored && <span className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded">stored</span>}
                          {!isStored && (
                            <button onClick={() => deleteD2Section(sec.section_id)}
                              className="text-red-400 hover:text-red-600 shrink-0" title="Delete section">
                              <X size={14} />
                            </button>
                          )}
                        </div>
                        <div className={isSubSection ? 'ml-2' : 'ml-7'}>
                          <p className="text-xs text-gray-600 whitespace-pre-wrap bg-white border p-2 rounded max-h-40 overflow-y-auto">{sec.content}</p>
                          {sec.links?.length > 0 && (
                            <div className="mt-1 space-y-0.5">
                              <span className="text-xs font-medium text-gray-500">Links:</span>
                              {sec.links.slice(0, 5).map((l, li) => (
                                <div key={li} className="flex items-center gap-1 text-xs">
                                  <span className="w-1.5 h-1.5 rounded-full bg-blue-400 shrink-0" />
                                  <a href={l.url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline truncate">{l.title || l.url}</a>
                                </div>
                              ))}
                              {sec.links.length > 5 && <span className="text-xs text-gray-400">+{sec.links.length - 5} more</span>}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ))}

          {d2Sections && !d2Sections.urls?.length && (
            <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg text-yellow-700 text-sm">
              No depth 2-3 sections found. Check that depth 1 sections had URLs to process.
            </div>
          )}

          <div className="flex gap-3">
            <button onClick={() => setStep(3)} className="px-4 py-2 border rounded-lg hover:bg-gray-50 flex items-center gap-1">
              <ChevronLeft size={18} /> Back
            </button>
            <button onClick={storeApproved} disabled={loading || !d2Sections?.total_sections}
              className="flex-1 py-3 bg-gradient-to-r from-green-600 to-teal-600 text-white rounded-lg hover:from-green-700 hover:to-teal-700 flex items-center justify-center gap-2 font-medium disabled:opacity-50">
              <Database size={18} /> Store Approved Sections to MongoDB
            </button>
          </div>

          <button onClick={resetFlow}
            className="w-full py-2 border border-gray-300 rounded-lg hover:bg-gray-50 flex items-center justify-center gap-2 text-gray-600">
            <RefreshCw size={16} /> Start New Extraction
          </button>
        </div>
      )}
    </div>
  );
}
