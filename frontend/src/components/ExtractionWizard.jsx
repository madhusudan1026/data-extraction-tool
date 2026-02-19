/**
 * V4 Unified Extraction Wizard
 * 
 * Combines V2 (single-card, user-driven) and V3 (bank-wide discovery) 
 * while retaining ALL V2 UI workflows including:
 * - Source Type (URL / Text / PDF)
 * - Process PDFs toggle
 * - Bypass Cache toggle  
 * - Crawl Depth setting
 * - Playwright vs HTML scraping toggle (NEW)
 * - Quick examples
 * - Follow links at multiple depths
 */

import React, { useState, useEffect } from 'react';
import {
  CreditCard, Building2, Link, FileText, CheckCircle, 
  AlertCircle, Loader2, ChevronRight, ChevronLeft,
  Globe, FileDown, CheckSquare, Square, Search,
  Eye, EyeOff, X, Plus, RefreshCw, Tag, ExternalLink,
  ChevronDown, ChevronUp, Database, Save, Zap,
  Upload, Settings2, Chrome
} from 'lucide-react';

const API_BASE = 'http://localhost:8000/api/v4/extraction';

const DEFAULT_KEYWORDS = [
  'benefit', 'reward', 'cashback', 'discount', 'lounge', 'airport',
  'travel', 'insurance', 'annual fee', 'interest rate', 'eligibility',
  'minimum salary', 'points', 'miles', 'complimentary', 'free',
  'cinema', 'golf', 'concierge', 'valet', 'dining', 'shopping',
  'partner', 'merchant', 'offer', 'promotion', 'feature',
  'aed', 'usd', '%', 'per month', 'per year', 'waived',
  'mastercard', 'visa', 'diners', 'platinum', 'signature', 'world',
  'credit limit', 'supplementary', 'apply', 'requirement'
];

// Quick example URLs
const QUICK_EXAMPLES = [
  { name: 'Emirates NBD Duo', url: 'https://www.emiratesnbd.com/en/cards/credit-cards/duo-credit-card' },
  { name: 'FAB Cashback', url: 'https://www.bankfab.com/en-ae/personal/cards/credit-cards/cashback-credit-card' },
  { name: 'ADCB TouchPoints', url: 'https://www.adcb.com/en/personal/cards/credit-cards/touchpoints-platinum' },
];

export default function ExtractionWizard() {
  // Session state
  const [session, setSession] = useState(null);
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Step 1: Input mode & options
  const [mode, setMode] = useState('single_card');
  const [sourceType, setSourceType] = useState('url'); // url, text, pdf
  const [singleCardUrl, setSingleCardUrl] = useState('');
  const [textContent, setTextContent] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [selectedBank, setSelectedBank] = useState('');
  const [banks, setBanks] = useState([]);

  // Advanced Options (V2 features)
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [processPdfs, setProcessPdfs] = useState(true);
  const [bypassCache, setBypassCache] = useState(false);
  const [maxDepth, setMaxDepth] = useState(2);
  const [followLinks, setFollowLinks] = useState(true);
  const [usePlaywright, setUsePlaywright] = useState(true); // NEW: Playwright vs HTML

  // Step 2: Cards
  const [cards, setCards] = useState([]);
  const [selectedCardIds, setSelectedCardIds] = useState([]);

  // Step 3-4: URLs
  const [urls, setUrls] = useState([]);
  const [selectedUrls, setSelectedUrls] = useState([]);
  const [urlViewMode, setUrlViewMode] = useState('relevance');

  // Step 5: Keywords
  const [keywords, setKeywords] = useState([...DEFAULT_KEYWORDS]);
  const [newKeyword, setNewKeyword] = useState('');

  // Step 6-7: Sources
  const [sources, setSources] = useState([]);
  const [expandedSources, setExpandedSources] = useState(new Set());
  const [fetchStats, setFetchStats] = useState(null);

  // Load banks on mount
  useEffect(() => {
    fetchBanks();
  }, []);

  const fetchBanks = async () => {
    try {
      const res = await fetch(`${API_BASE}/banks`);
      const data = await res.json();
      setBanks(data.banks || []);
    } catch (err) {
      console.error('Failed to load banks:', err);
    }
  };

  const handleError = (msg) => { setError(msg); setLoading(false); };

  // ============= STEP 1: Create Session =============
  const createSession = async () => {
    setLoading(true);
    setError('');
    try {
      const body = { 
        mode,
        options: {
          process_pdfs: processPdfs,
          bypass_cache: bypassCache,
          max_depth: maxDepth,
          follow_links: followLinks,
          use_playwright: usePlaywright,
        }
      };
      
      if (mode === 'single_card') {
        if (sourceType === 'url') {
          if (!singleCardUrl) return handleError('Please enter a card URL');
          body.single_card_url = singleCardUrl;
        } else if (sourceType === 'text') {
          if (!textContent.trim()) return handleError('Please enter some text');
          body.text_content = textContent;
          body.source_type = 'text';
        } else if (sourceType === 'pdf') {
          if (!selectedFile) return handleError('Please select a PDF file');
          // Handle PDF upload separately
          body.source_type = 'pdf';
        }
      } else {
        if (!selectedBank) return handleError('Please select a bank');
        body.bank_key = selectedBank;
      }

      // PDF upload uses FormData multipart
      if (mode === 'single_card' && sourceType === 'pdf' && selectedFile) {
        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('mode', mode);
        formData.append('source_type', 'pdf');
        formData.append('options', JSON.stringify({
          process_pdfs: processPdfs,
          bypass_cache: bypassCache,
          max_depth: maxDepth,
          follow_links: followLinks,
          use_playwright: usePlaywright,
        }));

        const res = await fetch(`${API_BASE}/sessions/upload`, {
          method: 'POST',
          body: formData
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);
        setSession(data);
        setStep(4);
      } else {
        const res = await fetch(`${API_BASE}/sessions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail);
        
        setSession(data);
        
        // For text, skip card discovery and go to URL discovery
        if (mode === 'single_card' && sourceType !== 'url') {
          setStep(4);
        } else {
          await discoverCards(data.session_id);
        }
      }
    } catch (err) {
      handleError(err.message);
    }
  };

  // ============= STEP 2: Discover Cards =============
  const discoverCards = async (sid) => {
    try {
      await fetch(`${API_BASE}/sessions/${sid}/discover-cards`, { method: 'POST' });
      const res = await fetch(`${API_BASE}/sessions/${sid}/cards`);
      const data = await res.json();
      setCards(data.cards || []);
      setSelectedCardIds(data.cards?.filter(c => c.is_selected).map(c => c.card_id) || []);
      setStep(2);
    } catch (err) {
      handleError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // ============= STEP 2 -> 3: Select Cards & Discover URLs =============
  const selectCardsAndDiscover = async () => {
    if (!selectedCardIds.length) return handleError('Select at least one card');
    setLoading(true);
    setError('');
    try {
      await fetch(`${API_BASE}/sessions/${session.session_id}/select-cards`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ card_ids: selectedCardIds })
      });
      setStep(3);
      await discoverUrls();
    } catch (err) {
      handleError(err.message);
    }
  };

  // ============= STEP 3: Discover URLs =============
  const discoverUrls = async () => {
    try {
      // Pass options to discover-urls endpoint
      const res = await fetch(`${API_BASE}/sessions/${session.session_id}/discover-urls`, { 
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          follow_links: followLinks,
          max_depth: maxDepth,
          process_pdfs: processPdfs,
          use_playwright: usePlaywright
        })
      });
      const discoverData = await res.json();
      
      const urlsRes = await fetch(`${API_BASE}/sessions/${session.session_id}/urls`);
      const urlsData = await urlsRes.json();
      setUrls(urlsData.urls || []);
      setSelectedUrls(urlsData.urls?.filter(u => u.is_selected).map(u => u.url) || []);
      setStep(4);
    } catch (err) {
      handleError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // ============= STEP 4 -> 5: URL Selection -> Keywords =============
  const proceedToKeywords = () => {
    if (!selectedUrls.length) return setError('Select at least one URL');
    setError('');
    setStep(5);
  };

  // ============= STEP 5 -> 6: Keywords -> Fetch Content =============
  const fetchContent = async () => {
    setLoading(true);
    setError('');
    try {
      await fetch(`${API_BASE}/sessions/${session.session_id}/select-urls`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          selected_urls: selectedUrls, 
          keywords,
          options: {
            process_pdfs: processPdfs,
            use_playwright: usePlaywright,
            bypass_cache: bypassCache
          }
        })
      });

      setStep(6);

      const fetchRes = await fetch(`${API_BASE}/sessions/${session.session_id}/fetch-content`, { 
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          use_playwright: usePlaywright,
          bypass_cache: bypassCache
        })
      });
      const fetchData = await fetchRes.json();
      
      const sourcesRes = await fetch(`${API_BASE}/sessions/${session.session_id}/sources`);
      const sourcesData = await sourcesRes.json();
      setSources(sourcesData.sources || []);
      setFetchStats(fetchData);
      setStep(7);
    } catch (err) {
      handleError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // ============= STEP 7: Approve/Reject Sources =============
  const approveSource = async (sourceId) => {
    try {
      await fetch(`${API_BASE}/sessions/${session.session_id}/sources/${sourceId}/approve`, { method: 'POST' });
      setSources(prev => prev.map(s => s.source_id === sourceId ? {...s, approval_status: 'approved'} : s));
    } catch (err) {
      setError('Failed to approve source');
    }
  };

  const rejectSource = async (sourceId) => {
    try {
      await fetch(`${API_BASE}/sessions/${session.session_id}/sources/${sourceId}/reject`, { method: 'POST' });
      setSources(prev => prev.map(s => s.source_id === sourceId ? {...s, approval_status: 'rejected'} : s));
    } catch (err) {
      setError('Failed to reject source');
    }
  };

  // Approve all and save to approved_raw_data collection
  const [saveResult, setSaveResult] = useState(null);
  
  const approveAllAndSave = async () => {
    setLoading(true);
    setError('');
    try {
      // First approve all sources
      await fetch(`${API_BASE}/sessions/${session.session_id}/approve-all-sources`, { method: 'POST' });
      setSources(prev => prev.map(s => ({...s, approval_status: 'approved'})));
      
      // Then save to approved_raw_data collection
      const saveRes = await fetch(`${API_BASE}/sessions/${session.session_id}/save-approved-raw`, { method: 'POST' });
      const saveData = await saveRes.json();
      
      if (!saveRes.ok) throw new Error(saveData.detail || 'Failed to save');
      
      setSaveResult(saveData);
      // Stay on step 7 but show success
    } catch (err) {
      handleError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // ============= Keyword Management =============
  const addKeyword = () => {
    const kw = newKeyword.trim().toLowerCase();
    if (kw && !keywords.includes(kw)) {
      setKeywords([...keywords, kw]);
      setNewKeyword('');
    }
  };

  const removeKeyword = (kw) => setKeywords(keywords.filter(k => k !== kw));
  const resetKeywords = () => setKeywords([...DEFAULT_KEYWORDS]);

  // ============= Reset =============
  const reset = () => {
    setSession(null);
    setStep(1);
    setCards([]);
    setSelectedCardIds([]);
    setUrls([]);
    setSelectedUrls([]);
    setSources([]);
    setSaveResult(null);
    setFetchStats(null);
    setError('');
    setKeywords([...DEFAULT_KEYWORDS]);
    setSingleCardUrl('');
    setTextContent('');
    setSelectedFile(null);
  };

  // ============= Helpers =============
  const toggleAll = (items, selected, setSelected, key) => {
    if (selected.length === items.length) setSelected([]);
    else setSelected(items.map(i => i[key]));
  };

  const toggleExpanded = (id, set, setFn) => {
    const next = new Set(set);
    if (next.has(id)) next.delete(id); else next.add(id);
    setFn(next);
  };

  // Only 7 steps now - stops after saving approved raw data
  const stepNames = ['Input', 'Cards', 'Discover', 'URLs', 'Keywords', 'Fetch', 'Save'];

  // ============= RENDER =============
  return (
    <div className="max-w-6xl mx-auto">
      <div className="bg-white rounded-xl shadow-lg p-6">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-800 flex items-center gap-2">
              Enhanced Extraction Module
              <span className="text-xs bg-gradient-to-r from-purple-500 to-blue-500 text-white px-2 py-0.5 rounded-full">V4</span>
            </h1>
            <p className="text-sm text-gray-500">Single Card URL, Text, or PDF → Bank-Wide Discovery → Raw Data Storage</p>
          </div>
          {session && (
            <button onClick={reset} className="text-gray-500 hover:text-gray-700 flex items-center gap-1 px-3 py-1 rounded border">
              <RefreshCw size={16} /> Reset
            </button>
          )}
        </div>

        {/* Step Indicator */}
        <div className="flex items-center justify-center mb-6 overflow-x-auto pb-2">
          {stepNames.map((name, i) => (
            <React.Fragment key={i}>
              <div className={`flex flex-col items-center ${i + 1 <= step ? 'text-blue-600' : 'text-gray-400'}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium border-2 
                  ${i + 1 < step ? 'bg-blue-600 text-white border-blue-600' : 
                    i + 1 === step ? 'border-blue-600 text-blue-600 bg-blue-50' : 'border-gray-300'}`}>
                  {i + 1 < step ? '✓' : i + 1}
                </div>
                <span className="text-xs mt-1 hidden md:block whitespace-nowrap">{name}</span>
              </div>
              {i < 6 && <div className={`w-4 md:w-8 h-0.5 ${i + 1 < step ? 'bg-blue-600' : 'bg-gray-300'}`} />}
            </React.Fragment>
          ))}
        </div>

        {/* Error Display */}
        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg flex items-center gap-2 text-red-700">
            <AlertCircle size={20} /> {error}
            <button onClick={() => setError('')} className="ml-auto"><X size={16} /></button>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="animate-spin text-blue-600" size={40} />
            <span className="ml-3 text-gray-600">
              {step === 3 ? `Discovering URLs (depth: ${maxDepth}, ${usePlaywright ? 'Playwright' : 'HTML'})...` : 
               step === 6 ? 'Fetching content...' : 
               step === 7 ? 'Saving to database...' : 'Processing...'}
            </span>
          </div>
        )}

        {/* Step Content */}
        {!loading && (
          <>
            {/* ============= STEP 1: Input Mode with V2 Features ============= */}
            {step === 1 && (
              <div className="space-y-6">
                <h2 className="text-xl font-semibold">Step 1: Choose Extraction Mode</h2>
                
                {/* Mode Selection */}
                <div className="grid md:grid-cols-2 gap-4">
                  <button
                    onClick={() => setMode('single_card')}
                    className={`p-6 rounded-lg border-2 text-left transition ${
                      mode === 'single_card' ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <CreditCard className={`mb-2 ${mode === 'single_card' ? 'text-blue-600' : 'text-gray-400'}`} size={32} />
                    <h3 className="font-semibold">Single Card Extraction</h3>
                    <p className="text-sm text-gray-500">Extract from URL, text, or PDF</p>
                  </button>

                  <button
                    onClick={() => setMode('bank_wide')}
                    className={`p-6 rounded-lg border-2 text-left transition ${
                      mode === 'bank_wide' ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <Building2 className={`mb-2 ${mode === 'bank_wide' ? 'text-blue-600' : 'text-gray-400'}`} size={32} />
                    <h3 className="font-semibold">Bank-Wide Discovery</h3>
                    <p className="text-sm text-gray-500">Discover all credit cards from a bank</p>
                  </button>
                </div>

                {/* Single Card Options */}
                {mode === 'single_card' && (
                  <>
                    {/* Source Type Selection (V2 Feature) */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">Source Type</label>
                      <div className="grid grid-cols-3 gap-3">
                        <button
                          onClick={() => setSourceType('url')}
                          className={`p-3 rounded-lg border-2 flex items-center justify-center gap-2 transition ${
                            sourceType === 'url' ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-gray-200 hover:border-gray-300'
                          }`}
                        >
                          <Link size={18} /> URL
                        </button>
                        <button
                          onClick={() => setSourceType('text')}
                          className={`p-3 rounded-lg border-2 flex items-center justify-center gap-2 transition ${
                            sourceType === 'text' ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-gray-200 hover:border-gray-300'
                          }`}
                        >
                          <FileText size={18} /> Text
                        </button>
                        <button
                          onClick={() => setSourceType('pdf')}
                          className={`p-3 rounded-lg border-2 flex items-center justify-center gap-2 transition ${
                            sourceType === 'pdf' ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-gray-200 hover:border-gray-300'
                          }`}
                        >
                          <Upload size={18} /> PDF
                        </button>
                      </div>
                    </div>

                    {/* URL Input */}
                    {sourceType === 'url' && (
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Enter Credit Card Page URL</label>
                        <input
                          type="url"
                          value={singleCardUrl}
                          onChange={(e) => setSingleCardUrl(e.target.value)}
                          placeholder="https://www.bank.com/credit-cards/card-name"
                          className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        />
                        {/* Quick Examples (V2 Feature) */}
                        <div className="mt-2 flex items-center gap-2 flex-wrap">
                          <span className="text-xs text-gray-500">Quick examples:</span>
                          {QUICK_EXAMPLES.map(ex => (
                            <button
                              key={ex.name}
                              onClick={() => setSingleCardUrl(ex.url)}
                              className="text-xs px-2 py-1 bg-gray-100 hover:bg-gray-200 rounded-full text-gray-600"
                            >
                              {ex.name}
                            </button>
                          ))}
                        </div>
                        <p className="text-xs text-gray-500 mt-2">
                          Step 1: We'll discover related links (PDFs, terms, benefits pages) for you to select.
                        </p>
                      </div>
                    )}

                    {/* Text Input */}
                    {sourceType === 'text' && (
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Paste Content</label>
                        <textarea
                          value={textContent}
                          onChange={(e) => setTextContent(e.target.value)}
                          placeholder="Paste the credit card benefits text here..."
                          className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500 h-40"
                        />
                      </div>
                    )}

                    {/* PDF Input */}
                    {sourceType === 'pdf' && (
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Upload PDF</label>
                        <div className="border-2 border-dashed rounded-lg p-6 text-center">
                          <input
                            type="file"
                            accept=".pdf"
                            onChange={(e) => setSelectedFile(e.target.files[0])}
                            className="hidden"
                            id="pdf-upload"
                          />
                          <label htmlFor="pdf-upload" className="cursor-pointer">
                            <Upload className="mx-auto mb-2 text-gray-400" size={32} />
                            {selectedFile ? (
                              <p className="text-blue-600 font-medium">{selectedFile.name}</p>
                            ) : (
                              <p className="text-gray-500">Click to select PDF file</p>
                            )}
                          </label>
                        </div>
                      </div>
                    )}
                  </>
                )}

                {/* Bank Selection */}
                {mode === 'bank_wide' && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Select Bank</label>
                    <select
                      value={selectedBank}
                      onChange={(e) => setSelectedBank(e.target.value)}
                      className="w-full p-3 border rounded-lg focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="">-- Select a bank --</option>
                      {banks.map(bank => (
                        <option key={bank.key} value={bank.key}>
                          {bank.name} {bank.requires_javascript ? '(JS)' : ''}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {/* Advanced Options (V2 Feature) */}
                <div className="border rounded-lg">
                  <button
                    onClick={() => setShowAdvanced(!showAdvanced)}
                    className="w-full p-3 flex items-center justify-between text-left hover:bg-gray-50"
                  >
                    <span className="flex items-center gap-2 font-medium">
                      <Settings2 size={18} /> Advanced Options
                    </span>
                    {showAdvanced ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                  </button>
                  
                  {showAdvanced && (
                    <div className="p-4 border-t space-y-4">
                      {/* Scraping Method Toggle (NEW) */}
                      <div className="flex items-center justify-between p-3 bg-purple-50 rounded-lg">
                        <div className="flex items-center gap-3">
                          <Chrome className="text-purple-600" size={20} />
                          <div>
                            <div className="font-medium text-purple-800">Playwright/Chromium Mode</div>
                            <div className="text-xs text-purple-600">Use browser for JavaScript-rendered pages</div>
                          </div>
                        </div>
                        <button
                          onClick={() => setUsePlaywright(!usePlaywright)}
                          className={`w-12 h-6 rounded-full transition-colors ${usePlaywright ? 'bg-purple-600' : 'bg-gray-300'}`}
                        >
                          <div className={`w-5 h-5 bg-white rounded-full shadow transform transition-transform ${usePlaywright ? 'translate-x-6' : 'translate-x-0.5'}`} />
                        </button>
                      </div>

                      {/* Follow Links & Depth */}
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="font-medium">Follow Links</div>
                          <div className="text-xs text-gray-500">Crawl related pages at multiple depths</div>
                        </div>
                        <button
                          onClick={() => setFollowLinks(!followLinks)}
                          className={`w-12 h-6 rounded-full transition-colors ${followLinks ? 'bg-blue-600' : 'bg-gray-300'}`}
                        >
                          <div className={`w-5 h-5 bg-white rounded-full shadow transform transition-transform ${followLinks ? 'translate-x-6' : 'translate-x-0.5'}`} />
                        </button>
                      </div>

                      {followLinks && (
                        <div className="ml-4">
                          <label className="block text-sm font-medium text-gray-700 mb-1">
                            Crawl Depth: {maxDepth}
                          </label>
                          <input
                            type="range"
                            min="1"
                            max="5"
                            value={maxDepth}
                            onChange={(e) => setMaxDepth(parseInt(e.target.value))}
                            className="w-full"
                          />
                          <div className="flex justify-between text-xs text-gray-500">
                            <span>1 (shallow)</span>
                            <span>5 (deep)</span>
                          </div>
                        </div>
                      )}

                      {/* Process PDFs */}
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="font-medium">Process PDFs</div>
                          <div className="text-xs text-gray-500">Extract text from PDF documents</div>
                        </div>
                        <button
                          onClick={() => setProcessPdfs(!processPdfs)}
                          className={`w-12 h-6 rounded-full transition-colors ${processPdfs ? 'bg-blue-600' : 'bg-gray-300'}`}
                        >
                          <div className={`w-5 h-5 bg-white rounded-full shadow transform transition-transform ${processPdfs ? 'translate-x-6' : 'translate-x-0.5'}`} />
                        </button>
                      </div>

                      {/* Bypass Cache */}
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="font-medium">Scrape Fresh</div>
                          <div className="text-xs text-gray-500">Skip existing data in DB, re-scrape all URLs</div>
                        </div>
                        <button
                          onClick={() => setBypassCache(!bypassCache)}
                          className={`w-12 h-6 rounded-full transition-colors ${bypassCache ? 'bg-blue-600' : 'bg-gray-300'}`}
                        >
                          <div className={`w-5 h-5 bg-white rounded-full shadow transform transition-transform ${bypassCache ? 'translate-x-6' : 'translate-x-0.5'}`} />
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                <button
                  onClick={createSession}
                  className="w-full py-3 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-700 hover:to-purple-700 flex items-center justify-center gap-2"
                >
                  <Search size={20} /> Discover Related Links
                </button>
              </div>
            )}

            {/* ============= STEP 2: Card Selection ============= */}
            {step === 2 && (
              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <h2 className="text-xl font-semibold">Step 2: Select Cards ({selectedCardIds.length}/{cards.length})</h2>
                  <button onClick={() => toggleAll(cards, selectedCardIds, setSelectedCardIds, 'card_id')}
                          className="text-blue-600 hover:text-blue-800 text-sm">
                    {selectedCardIds.length === cards.length ? 'Deselect All' : 'Select All'}
                  </button>
                </div>

                <div className="max-h-96 overflow-y-auto border rounded-lg">
                  {cards.map(card => (
                    <div
                      key={card.card_id}
                      onClick={() => setSelectedCardIds(prev => 
                        prev.includes(card.card_id) ? prev.filter(id => id !== card.card_id) : [...prev, card.card_id]
                      )}
                      className={`p-3 border-b cursor-pointer hover:bg-gray-50 flex items-center gap-3 ${
                        selectedCardIds.includes(card.card_id) ? 'bg-blue-50' : ''
                      }`}
                    >
                      {selectedCardIds.includes(card.card_id) ? 
                        <CheckSquare className="text-blue-600" size={20} /> : 
                        <Square className="text-gray-400" size={20} />
                      }
                      <div className="flex-1 min-w-0">
                        <div className="font-medium">{card.card_name}</div>
                        <div className="text-xs text-gray-500 truncate">{card.card_url}</div>
                      </div>
                      <a href={card.card_url} target="_blank" rel="noopener noreferrer" 
                         onClick={e => e.stopPropagation()} className="text-gray-400 hover:text-blue-600">
                        <ExternalLink size={16} />
                      </a>
                    </div>
                  ))}
                </div>

                <div className="flex gap-3">
                  <button onClick={() => setStep(1)} className="px-4 py-2 border rounded-lg hover:bg-gray-50">
                    <ChevronLeft size={20} className="inline" /> Back
                  </button>
                  <button
                    onClick={selectCardsAndDiscover}
                    disabled={!selectedCardIds.length}
                    className="flex-1 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 flex items-center justify-center gap-2"
                  >
                    Discover URLs <ChevronRight size={20} />
                  </button>
                </div>
              </div>
            )}

            {/* ============= STEP 4: URL Selection ============= */}
            {step === 4 && (
              <div className="space-y-4">
                <div className="flex justify-between items-center flex-wrap gap-2">
                  <h2 className="text-xl font-semibold">Step 4: Select URLs ({selectedUrls.length}/{urls.length})</h2>
                  <div className="flex gap-2">
                    <select value={urlViewMode} onChange={e => setUrlViewMode(e.target.value)}
                            className="text-sm border rounded px-2 py-1">
                      <option value="relevance">Sort by Relevance</option>
                      <option value="type">Sort by Type</option>
                      <option value="depth">Sort by Depth</option>
                    </select>
                    <button onClick={() => toggleAll(urls, selectedUrls, setSelectedUrls, 'url')}
                            className="text-blue-600 hover:text-blue-800 text-sm">
                      {selectedUrls.length === urls.length ? 'Deselect All' : 'Select All'}
                    </button>
                  </div>
                </div>

                <div className="text-sm bg-blue-50 p-3 rounded-lg flex items-center gap-2">
                  <Database size={16} className="text-blue-600" />
                  <span>{urls.length} unique URLs found • Crawl depth: {maxDepth} • {usePlaywright ? 'Playwright' : 'HTML'} mode</span>
                </div>

                <div className="max-h-80 overflow-y-auto border rounded-lg divide-y">
                  {[...urls]
                    .sort((a, b) => {
                      if (urlViewMode === 'relevance') return (b.relevance_score || 0) - (a.relevance_score || 0);
                      if (urlViewMode === 'type') return (a.url_type || '').localeCompare(b.url_type || '');
                      if (urlViewMode === 'depth') return (a.depth || 0) - (b.depth || 0);
                      return 0;
                    })
                    .map(url => (
                    <div
                      key={url.url_id}
                      onClick={() => setSelectedUrls(prev => 
                        prev.includes(url.url) ? prev.filter(u => u !== url.url) : [...prev, url.url]
                      )}
                      className={`p-3 cursor-pointer hover:bg-gray-50 flex items-start gap-3 ${
                        selectedUrls.includes(url.url) ? 'bg-blue-50' : ''
                      }`}
                    >
                      {selectedUrls.includes(url.url) ? 
                        <CheckSquare className="text-blue-600 mt-0.5 flex-shrink-0" size={18} /> : 
                        <Square className="text-gray-400 mt-0.5 flex-shrink-0" size={18} />
                      }
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          {url.url_type === 'pdf' ? 
                            <FileDown size={14} className="text-red-500" /> : 
                            <Globe size={14} className="text-blue-500" />
                          }
                          <span className="font-medium truncate">{url.title}</span>
                          <span className={`text-xs px-2 py-0.5 rounded ${
                            url.relevance_level === 'high' ? 'bg-green-100 text-green-700' :
                            url.relevance_level === 'medium' ? 'bg-yellow-100 text-yellow-700' :
                            'bg-gray-100 text-gray-600'
                          }`}>
                            {url.relevance_level}
                          </span>
                          {url.depth !== undefined && (
                            <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded">
                              depth: {url.depth}
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-gray-500 truncate mt-1">{url.url}</div>
                        {url.card_names?.length > 1 && (
                          <div className="text-xs text-blue-600 mt-1">
                            Shared by {url.card_names.length} cards
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>

                <div className="flex gap-3">
                  <button onClick={() => setStep(mode === 'single_card' && (sourceType === 'text' || sourceType === 'pdf') ? 1 : 2)} className="px-4 py-2 border rounded-lg hover:bg-gray-50">
                    <ChevronLeft size={20} className="inline" /> Back
                  </button>
                  <button
                    onClick={proceedToKeywords}
                    disabled={!selectedUrls.length}
                    className="flex-1 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 flex items-center justify-center gap-2"
                  >
                    Customize Keywords <ChevronRight size={20} />
                  </button>
                </div>
              </div>
            )}

            {/* ============= STEP 5: Keywords ============= */}
            {step === 5 && (
              <div className="space-y-4">
                <h2 className="text-xl font-semibold">Step 5: Customize Keywords</h2>
                <p className="text-sm text-gray-600">
                  Keywords are used to score relevance and identify important content.
                </p>

                <div className="flex gap-2">
                  <input
                    type="text"
                    value={newKeyword}
                    onChange={e => setNewKeyword(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && addKeyword()}
                    placeholder="Add a keyword..."
                    className="flex-1 p-2 border rounded-lg"
                  />
                  <button onClick={addKeyword} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                    <Plus size={20} />
                  </button>
                  <button onClick={resetKeywords} className="px-4 py-2 border rounded-lg hover:bg-gray-50" title="Reset">
                    <RefreshCw size={20} />
                  </button>
                </div>

                <div className="flex flex-wrap gap-2 p-4 bg-gray-50 rounded-lg max-h-48 overflow-y-auto">
                  {keywords.map(kw => (
                    <span key={kw} className="inline-flex items-center gap-1 px-2 py-1 bg-white border rounded-full text-sm">
                      <Tag size={12} className="text-gray-400" />
                      {kw}
                      <button onClick={() => removeKeyword(kw)} className="text-gray-400 hover:text-red-500">
                        <X size={14} />
                      </button>
                    </span>
                  ))}
                </div>

                <div className="flex gap-3">
                  <button onClick={() => setStep(4)} className="px-4 py-2 border rounded-lg hover:bg-gray-50">
                    <ChevronLeft size={20} className="inline" /> Back
                  </button>
                  <button
                    onClick={fetchContent}
                    className="flex-1 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center justify-center gap-2"
                  >
                    <Zap size={20} /> Fetch Content
                  </button>
                </div>
              </div>
            )}

            {/* ============= STEP 7: Source Review ============= */}
            {step === 7 && (
              <div className="space-y-4">
                <h2 className="text-xl font-semibold">Step 7: Review Sources</h2>

                {/* Bank context */}
                {session?.bank_name && (
                  <div className="text-sm text-gray-500 flex items-center gap-2">
                    🏦 <span className="font-medium">{session.bank_name}</span>
                  </div>
                )}

                {/* Fetch stats */}
                {fetchStats && (
                  <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm">
                    <div className="flex items-center gap-4 flex-wrap">
                      <span className="text-blue-700"><strong>{fetchStats.sources_fetched}</strong> total fetched</span>
                      {fetchStats.sources_from_cache > 0 && (
                        <span className="text-green-700 bg-green-100 px-2 py-0.5 rounded-full text-xs">
                          ♻️ {fetchStats.sources_from_cache} from cache
                        </span>
                      )}
                      {fetchStats.sources_fresh > 0 && (
                        <span className="text-blue-700 bg-blue-100 px-2 py-0.5 rounded-full text-xs">
                          🌐 {fetchStats.sources_fresh} fresh scraped
                        </span>
                      )}
                      {fetchStats.errors > 0 && (
                        <span className="text-red-600 bg-red-100 px-2 py-0.5 rounded-full text-xs">
                          ⚠️ {fetchStats.errors} errors
                        </span>
                      )}
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-3 gap-4 text-center">
                  <div className="bg-green-50 p-3 rounded-lg">
                    <div className="text-xl font-bold text-green-600">
                      {sources.filter(s => s.approval_status === 'approved').length}
                    </div>
                    <div className="text-sm text-gray-600">Approved</div>
                  </div>
                  <div className="bg-yellow-50 p-3 rounded-lg">
                    <div className="text-xl font-bold text-yellow-600">
                      {sources.filter(s => s.approval_status === 'pending').length}
                    </div>
                    <div className="text-sm text-gray-600">Pending</div>
                  </div>
                  <div className="bg-red-50 p-3 rounded-lg">
                    <div className="text-xl font-bold text-red-600">
                      {sources.filter(s => s.approval_status === 'rejected').length}
                    </div>
                    <div className="text-sm text-gray-600">Rejected</div>
                  </div>
                </div>

                <div className="max-h-96 overflow-y-auto space-y-3">
                  {sources.map(source => (
                    <div key={source.source_id} className={`border rounded-lg overflow-hidden ${
                      source.approval_status === 'approved' ? 'border-green-300 bg-green-50' :
                      source.approval_status === 'rejected' ? 'border-red-300 bg-red-50' :
                      'border-gray-200'
                    }`}>
                      <div className="p-3 flex items-start gap-3">
                        <div className={`p-2 rounded ${source.source_type === 'pdf' ? 'bg-red-100' : 'bg-blue-100'}`}>
                          {source.source_type === 'pdf' ? 
                            <FileDown size={16} className="text-red-600" /> : 
                            <Globe size={16} className="text-blue-600" />
                          }
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="font-medium">{source.title}</div>
                          <div className="text-xs text-gray-500 truncate">{source.url}</div>
                          <div className="flex gap-2 mt-1 text-xs text-gray-500 flex-wrap">
                            <span>{source.content_length?.toLocaleString()} chars</span>
                            <span>•</span>
                            <span>{source.detected_patterns?.length || 0} patterns</span>
                            {source.depth !== undefined && (
                              <>
                                <span>•</span>
                                <span className="text-purple-600">depth: {source.depth}</span>
                              </>
                            )}
                          </div>
                        </div>
                        <div className="flex gap-2">
                          <button
                            onClick={async () => {
                              // Toggle expansion and fetch full content if needed
                              const isExpanding = !expandedSources.has(source.source_id);
                              toggleExpanded(source.source_id, expandedSources, setExpandedSources);
                              
                              // If expanding and no full content loaded, fetch it
                              if (isExpanding && !source.full_content_loaded) {
                                try {
                                  const res = await fetch(`${API_BASE}/sessions/${session.session_id}/sources/${source.source_id}/content`);
                                  const data = await res.json();
                                  if (res.ok && data.raw_content) {
                                    // Update source with full content
                                    setSources(prev => prev.map(s => 
                                      s.source_id === source.source_id 
                                        ? {...s, raw_content: data.raw_content, cleaned_content: data.cleaned_content, full_content_loaded: true}
                                        : s
                                    ));
                                  }
                                } catch (err) {
                                  console.error('Failed to fetch full content:', err);
                                }
                              }
                            }}
                            className="p-1 hover:bg-gray-200 rounded"
                            title="View full content"
                          >
                            {expandedSources.has(source.source_id) ? <EyeOff size={16} /> : <Eye size={16} />}
                          </button>
                          {source.approval_status === 'pending' && (
                            <>
                              <button onClick={() => approveSource(source.source_id)}
                                      className="p-1 hover:bg-green-200 rounded text-green-600">
                                <CheckCircle size={16} />
                              </button>
                              <button onClick={() => rejectSource(source.source_id)}
                                      className="p-1 hover:bg-red-200 rounded text-red-600">
                                <X size={16} />
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                      
                      {expandedSources.has(source.source_id) && (
                        <div className="border-t p-3 bg-white">
                          <div className="flex justify-between items-center mb-2">
                            <div className="text-xs font-medium text-gray-500">
                              {source.full_content_loaded ? 'Full Content:' : 'Content Preview (click to load full):'}
                            </div>
                            <div className="text-xs text-gray-400">
                              {source.content_length?.toLocaleString() || source.raw_content?.length || 0} characters
                            </div>
                          </div>
                          <pre className="text-xs text-gray-700 whitespace-pre-wrap max-h-96 overflow-y-auto bg-gray-50 p-2 rounded">
                            {source.full_content_loaded 
                              ? (source.raw_content || 'No content')
                              : (source.content_preview || source.raw_content?.slice(0, 1000) || 'Loading...')}
                          </pre>
                          {source.detected_patterns?.length > 0 && (
                            <div className="mt-2">
                              <div className="text-xs font-medium text-gray-500 mb-1">Detected Patterns:</div>
                              <div className="flex flex-wrap gap-1">
                                {source.detected_patterns.slice(0, 10).map((p, i) => (
                                  <span key={i} className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded">
                                    {p.type}: {p.value}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                <div className="flex gap-3">
                  <button onClick={() => setStep(5)} className="px-4 py-2 border rounded-lg hover:bg-gray-50">
                    <ChevronLeft size={20} className="inline" /> Back
                  </button>
                  <button
                    onClick={approveAllAndSave}
                    disabled={loading}
                    className="flex-1 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 flex items-center justify-center gap-2 disabled:opacity-50"
                  >
                    {loading ? (
                      <>
                        <Loader2 size={20} className="animate-spin" /> Saving...
                      </>
                    ) : (
                      <>
                        <Save size={20} /> Approve All & Save to Database
                      </>
                    )}
                  </button>
                </div>


                {/* Success Message */}
                {saveResult && (
                  <div className="mt-6 p-6 bg-green-50 border border-green-200 rounded-lg">
                    <div className="flex items-center gap-3 mb-4">
                      <div className="p-3 bg-green-100 rounded-full">
                        <CheckCircle size={32} className="text-green-600" />
                      </div>
                      <div>
                        <h3 className="text-xl font-bold text-green-800">Successfully Saved!</h3>
                        <p className="text-green-600">{saveResult.message}</p>
                      </div>
                    </div>
                    
                    <div className="grid md:grid-cols-3 gap-4 mt-4">
                      <div className="bg-white p-4 rounded-lg border border-green-200">
                        <div className="text-2xl font-bold text-green-700">{saveResult.total_sources}</div>
                        <div className="text-sm text-gray-600">Sources Saved</div>
                      </div>
                      <div className="bg-white p-4 rounded-lg border border-green-200">
                        <div className="text-2xl font-bold text-green-700">{(saveResult.total_content_length || 0).toLocaleString()}</div>
                        <div className="text-sm text-gray-600">Characters</div>
                      </div>
                      <div className="bg-white p-4 rounded-lg border border-green-200">
                        <div className="text-sm font-mono text-green-700 break-all">{saveResult.saved_id}</div>
                        <div className="text-sm text-gray-600">Saved ID</div>
                      </div>
                    </div>

                    <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                      <div className="text-xs text-gray-500">
                        <strong>Card:</strong> {saveResult.detected_card_name}
                        {saveResult.card_network && <> &middot; <span className="text-blue-600">{saveResult.card_network}</span></>}
                        {saveResult.card_tier && <> &middot; <span className="text-purple-600">{saveResult.card_tier}</span></>}
                        {saveResult.bank_name && <> &middot; <span className="text-gray-600">🏦 {saveResult.bank_name}</span></>}
                        <br/>
                        <strong>URL:</strong> {saveResult.primary_url}
                      </div>
                      <p className="text-sm text-blue-600 mt-2">
                        Data saved to MongoDB. Use the <strong>Data Store & Vectorization</strong> tab to vectorize and run pipelines.
                      </p>
                    </div>

                    <button 
                      onClick={reset}
                      className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2"
                    >
                      <Plus size={18} /> Start New Extraction
                    </button>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        </div>
      </div>
  );
}
