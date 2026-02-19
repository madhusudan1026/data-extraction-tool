import React, { useState } from 'react';
import { extractionAPIv2 } from '../services/api';
import { 
  FileText, Link, Upload, Loader2, CheckCircle, AlertCircle,
  Zap, Settings2, ChevronDown, ChevronUp, Search, ExternalLink,
  FileDown, Globe, CheckSquare, Square, Brain, Tag, Plus, X, RotateCcw
} from 'lucide-react';

// Default keywords for relevance scoring
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

function ExtractionFormV2({ onResult, onIntelligenceResult }) {
  const [inputType, setInputType] = useState('url');
  const [inputValue, setInputValue] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [discovering, setDiscovering] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  
  // Two-step extraction state (now three steps with keywords)
  const [step, setStep] = useState(1); // 1 = input, 2 = select URLs, 2.5 = keywords, 3 = extracting
  const [discoveryResult, setDiscoveryResult] = useState(null);
  const [selectedUrls, setSelectedUrls] = useState([]);
  
  // Keywords for relevance scoring
  const [keywords, setKeywords] = useState([...DEFAULT_KEYWORDS]);
  const [newKeyword, setNewKeyword] = useState('');
  const [showKeywordStep, setShowKeywordStep] = useState(false);
  
  // Advanced options
  const [processPdfs, setProcessPdfs] = useState(true);
  const [bypassCache, setBypassCache] = useState(false);
  
  // NEW: Flexible intelligence mode
  const [useFlexibleExtraction, setUseFlexibleExtraction] = useState(true);

  // Keyword management functions
  const addKeyword = () => {
    const kw = newKeyword.trim().toLowerCase();
    if (kw && !keywords.includes(kw)) {
      setKeywords([...keywords, kw]);
      setNewKeyword('');
    }
  };

  const removeKeyword = (keyword) => {
    setKeywords(keywords.filter(k => k !== keyword));
  };

  const resetKeywords = () => {
    setKeywords([...DEFAULT_KEYWORDS]);
  };

  const handleKeywordKeyPress = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addKeyword();
    }
  };

  // Handle URL discovery (Step 1 -> Step 2)
  const handleDiscover = async (e) => {
    e.preventDefault();
    if (!inputValue.trim()) {
      setError('Please enter a URL');
      return;
    }
    
    setDiscovering(true);
    setError('');
    
    try {
      const result = await extractionAPIv2.discoverUrls(inputValue);
      setDiscoveryResult(result);
      
      // Auto-select high relevance links
      const highRelevance = [
        ...result.discovered_links.filter(l => l.relevance === 'high').map(l => l.url),
        ...result.pdf_links.filter(l => l.relevance === 'high').map(l => l.url)
      ];
      setSelectedUrls(highRelevance);
      
      setStep(2);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Discovery failed');
    } finally {
      setDiscovering(false);
    }
  };

  // Handle moving from URL selection to keywords step
  const handleProceedToKeywords = () => {
    if (useFlexibleExtraction) {
      setShowKeywordStep(true);
    } else {
      handleExtract();
    }
  };

  // Handle final extraction (Step 2/Keywords -> Results)
  const handleExtract = async () => {
    setLoading(true);
    setError('');
    setSuccess(false);
    setStep(3);
    setShowKeywordStep(false);

    try {
      let result;
      
      if (useFlexibleExtraction) {
        // Use new flexible intelligence extraction with custom keywords
        result = await extractionAPIv2.extractIntelligence(
          inputValue,
          selectedUrls,
          { processPdfs, bypassCache, keywords }
        );
        
        setSuccess(true);
        // Call the intelligence result handler with keywords for raw data review
        if (onIntelligenceResult) {
          // Pass keywords as second argument for raw data review
          onIntelligenceResult(result, keywords);
        } else if (onResult) {
          onResult({ ...result, isIntelligence: true, keywords });
        }
      } else {
        // Use legacy extraction
        result = await extractionAPIv2.extractWithSelectedUrls(
          inputValue,
          selectedUrls,
          { processPdfs, bypassCache }
        );
        
        setSuccess(true);
        onResult({ ...result.data, isV2: true });
      }
      
      setStep(1);
      setDiscoveryResult(null);
      setSelectedUrls([]);
      setShowKeywordStep(false);
      
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Extraction failed');
      setStep(2);
      setShowKeywordStep(false);
    } finally {
      setLoading(false);
    }
  };

  // Handle direct extraction (for text and PDF - now with raw data storage)
  const handleDirectExtract = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setSuccess(false);

    try {
      let result;
      
      if (inputType === 'text') {
        if (!inputValue.trim()) {
          throw new Error('Please enter some text');
        }
        
        if (useFlexibleExtraction) {
          // Use new intelligence extraction with raw data storage
          result = await extractionAPIv2.extractIntelligenceFromText(
            inputValue, 
            'Pasted Text',
            { keywords, bypassCache }
          );
          
          setSuccess(true);
          // Call the intelligence result handler with keywords for raw data review
          if (onIntelligenceResult) {
            onIntelligenceResult(result, keywords);
          } else if (onResult) {
            onResult({ ...result, isIntelligence: true, keywords });
          }
          return;
        } else {
          // Legacy extraction
          result = await extractionAPIv2.extractFromText(inputValue, { bypassCache });
        }
      } else if (inputType === 'pdf') {
        if (!selectedFile) {
          throw new Error('Please select a PDF file');
        }
        
        if (useFlexibleExtraction) {
          // Use new intelligence extraction with raw data storage
          result = await extractionAPIv2.extractIntelligenceFromPDF(
            selectedFile,
            { keywords, bypassCache }
          );
          
          setSuccess(true);
          // Call the intelligence result handler with keywords for raw data review
          if (onIntelligenceResult) {
            onIntelligenceResult(result, keywords);
          } else if (onResult) {
            onResult({ ...result, isIntelligence: true, keywords });
          }
          return;
        } else {
          // Legacy extraction
          result = await extractionAPIv2.extractFromPDF(selectedFile, { bypassCache });
        }
      }

      setSuccess(true);
      onResult({ ...result.data, isV2: true });
      
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Extraction failed');
    } finally {
      setLoading(false);
    }
  };

  // Toggle URL selection
  const toggleUrlSelection = (url) => {
    setSelectedUrls(prev => 
      prev.includes(url) 
        ? prev.filter(u => u !== url)
        : [...prev, url]
    );
  };

  // Select/deselect all
  const selectAllUrls = () => {
    if (!discoveryResult) return;
    const allUrls = [
      ...discoveryResult.discovered_links.map(l => l.url),
      ...discoveryResult.pdf_links.map(l => l.url)
    ];
    setSelectedUrls(allUrls);
  };

  const deselectAllUrls = () => {
    setSelectedUrls([]);
  };

  // Example URLs
  const exampleUrls = [
    { name: 'Emirates NBD Duo', url: 'https://www.emiratesnbd.com/en/cards/credit-cards/duo-credit-cards' },
    { name: 'FAB Cashback', url: 'https://www.bankfab.com/en-ae/personal/credit-cards/cashback-credit-card' },
  ];

  // Render URL selection step
  if (step === 2 && discoveryResult) {
    return (
      <div className="bg-white rounded-xl shadow-lg p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-gray-900">Select URLs to Process</h2>
            <p className="text-sm text-gray-600 mt-1">
              Found {discoveryResult.total_links_found} related links
            </p>
          </div>
          <button
            onClick={() => { setStep(1); setDiscoveryResult(null); }}
            className="text-gray-500 hover:text-gray-700"
          >
            ← Back
          </button>
        </div>

        {/* Main page info */}
        <div className="mb-6 p-4 bg-blue-50 rounded-lg">
          <div className="flex items-start gap-3">
            <Globe className="text-blue-600 mt-1" size={20} />
            <div>
              <p className="font-semibold text-blue-900">{discoveryResult.page_title}</p>
              <p className="text-sm text-blue-700">{discoveryResult.main_url}</p>
              {discoveryResult.bank_detected && (
                <span className="inline-block mt-2 px-2 py-1 bg-blue-200 text-blue-800 rounded text-xs">
                  {discoveryResult.bank_detected}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Selection controls */}
        <div className="flex items-center justify-between mb-4">
          <span className="text-sm text-gray-600">
            {selectedUrls.length} URLs selected
          </span>
          <div className="flex gap-2">
            <button
              onClick={selectAllUrls}
              className="text-sm text-blue-600 hover:text-blue-800"
            >
              Select All
            </button>
            <span className="text-gray-300">|</span>
            <button
              onClick={deselectAllUrls}
              className="text-sm text-blue-600 hover:text-blue-800"
            >
              Deselect All
            </button>
          </div>
        </div>

        {/* Web pages */}
        {discoveryResult.discovered_links.length > 0 && (
          <div className="mb-6">
            <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
              <Globe size={18} />
              Web Pages ({discoveryResult.discovered_links.length})
            </h3>
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {discoveryResult.discovered_links.map((link) => (
                <div
                  key={link.url}
                  onClick={() => toggleUrlSelection(link.url)}
                  className={`p-3 rounded-lg border cursor-pointer transition-all ${
                    selectedUrls.includes(link.url)
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    {selectedUrls.includes(link.url) ? (
                      <CheckSquare className="text-blue-600 mt-0.5" size={18} />
                    ) : (
                      <Square className="text-gray-400 mt-0.5" size={18} />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="font-medium text-gray-900 truncate">{link.title}</p>
                        <span className={`px-2 py-0.5 rounded text-xs ${
                          link.relevance === 'high' 
                            ? 'bg-green-100 text-green-700'
                            : link.relevance === 'medium'
                            ? 'bg-yellow-100 text-yellow-700'
                            : 'bg-gray-100 text-gray-600'
                        }`}>
                          {link.relevance}
                        </span>
                      </div>
                      <p className="text-xs text-gray-500 truncate">{link.url}</p>
                      <p className="text-xs text-gray-400 mt-1">{link.description}</p>
                    </div>
                    <a
                      href={link.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="text-gray-400 hover:text-blue-600"
                    >
                      <ExternalLink size={14} />
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* PDF documents */}
        {discoveryResult.pdf_links.length > 0 && (
          <div className="mb-6">
            <h3 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
              <FileDown size={18} />
              PDF Documents ({discoveryResult.pdf_links.length})
            </h3>
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {discoveryResult.pdf_links.map((link) => (
                <div
                  key={link.url}
                  onClick={() => toggleUrlSelection(link.url)}
                  className={`p-3 rounded-lg border cursor-pointer transition-all ${
                    selectedUrls.includes(link.url)
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    {selectedUrls.includes(link.url) ? (
                      <CheckSquare className="text-blue-600 mt-0.5" size={18} />
                    ) : (
                      <Square className="text-gray-400 mt-0.5" size={18} />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="font-medium text-gray-900 truncate">{link.title}</p>
                        <span className={`px-2 py-0.5 rounded text-xs ${
                          link.link_type === 'key_facts_pdf'
                            ? 'bg-purple-100 text-purple-700'
                            : link.link_type === 'terms_pdf'
                            ? 'bg-orange-100 text-orange-700'
                            : 'bg-red-100 text-red-700'
                        }`}>
                          {link.link_type.replace(/_/g, ' ')}
                        </span>
                      </div>
                      <p className="text-xs text-gray-500 truncate">{link.url}</p>
                    </div>
                    <a
                      href={link.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="text-gray-400 hover:text-blue-600"
                    >
                      <ExternalLink size={14} />
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* No links found message */}
        {discoveryResult.total_links_found === 0 && (
          <div className="text-center py-8 text-gray-500">
            <Search size={40} className="mx-auto mb-2 opacity-50" />
            <p>No related links found on this page.</p>
            <p className="text-sm">You can still proceed to extract from the main page.</p>
          </div>
        )}

        {/* Action buttons */}
        <div className="flex gap-3 mt-6">
          <button
            onClick={() => { setStep(1); setDiscoveryResult(null); setShowKeywordStep(false); }}
            className="flex-1 py-3 px-6 border border-gray-300 rounded-lg font-semibold text-gray-700 hover:bg-gray-50 transition-all"
          >
            Cancel
          </button>
          <button
            onClick={handleProceedToKeywords}
            disabled={loading}
            className="flex-1 bg-gradient-to-r from-blue-600 to-indigo-600 text-white py-3 px-6 rounded-lg font-semibold hover:from-blue-700 hover:to-indigo-700 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <Loader2 className="animate-spin" size={20} />
                <span>Extracting...</span>
              </>
            ) : useFlexibleExtraction ? (
              <>
                <Tag size={20} />
                <span>Configure Keywords ({selectedUrls.length + 1} URLs)</span>
              </>
            ) : (
              <>
                <Zap size={20} />
                <span>Extract from {selectedUrls.length + 1} URLs</span>
              </>
            )}
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
            <AlertCircle className="text-red-600 flex-shrink-0 mt-0.5" size={20} />
            <div>
              <p className="font-semibold text-red-800">Error</p>
              <p className="text-sm text-red-700">{error}</p>
            </div>
          </div>
        )}

        {/* Keywords Step Modal/Panel */}
        {showKeywordStep && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-hidden">
              <div className="p-6 border-b border-gray-200">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-purple-100 rounded-lg">
                      <Tag className="text-purple-600" size={24} />
                    </div>
                    <div>
                      <h3 className="text-xl font-bold text-gray-900">Relevance Keywords</h3>
                      <p className="text-sm text-gray-500">Configure keywords used to prioritize content sections</p>
                    </div>
                  </div>
                  <button 
                    onClick={() => setShowKeywordStep(false)}
                    className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                  >
                    <X size={20} className="text-gray-500" />
                  </button>
                </div>
              </div>

              <div className="p-6 overflow-y-auto max-h-[50vh]">
                {/* Add new keyword */}
                <div className="flex gap-2 mb-4">
                  <input
                    type="text"
                    value={newKeyword}
                    onChange={(e) => setNewKeyword(e.target.value)}
                    onKeyPress={handleKeywordKeyPress}
                    placeholder="Add new keyword..."
                    className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                  />
                  <button
                    onClick={addKeyword}
                    disabled={!newKeyword.trim()}
                    className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                  >
                    <Plus size={18} />
                    Add
                  </button>
                  <button
                    onClick={resetKeywords}
                    className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors flex items-center gap-2"
                    title="Reset to defaults"
                  >
                    <RotateCcw size={18} />
                  </button>
                </div>

                {/* Keywords count */}
                <p className="text-sm text-gray-500 mb-3">
                  {keywords.length} keywords active • Click a keyword to remove it
                </p>

                {/* Keywords grid */}
                <div className="flex flex-wrap gap-2">
                  {keywords.map((keyword, index) => (
                    <button
                      key={index}
                      onClick={() => removeKeyword(keyword)}
                      className="group px-3 py-1.5 bg-purple-50 text-purple-700 rounded-full text-sm font-medium hover:bg-red-50 hover:text-red-700 transition-colors flex items-center gap-1"
                    >
                      {keyword}
                      <X size={14} className="opacity-0 group-hover:opacity-100 transition-opacity" />
                    </button>
                  ))}
                </div>

                {keywords.length === 0 && (
                  <div className="text-center py-8 text-gray-500">
                    <Tag size={32} className="mx-auto mb-2 opacity-50" />
                    <p>No keywords defined</p>
                    <p className="text-sm">Add keywords or reset to defaults</p>
                  </div>
                )}
              </div>

              <div className="p-6 border-t border-gray-200 bg-gray-50">
                <div className="flex gap-3">
                  <button
                    onClick={() => setShowKeywordStep(false)}
                    className="flex-1 py-3 px-6 border border-gray-300 rounded-lg font-semibold text-gray-700 hover:bg-white transition-all"
                  >
                    Back to URL Selection
                  </button>
                  <button
                    onClick={handleExtract}
                    disabled={loading || keywords.length === 0}
                    className="flex-1 bg-gradient-to-r from-purple-600 to-indigo-600 text-white py-3 px-6 rounded-lg font-semibold hover:from-purple-700 hover:to-indigo-700 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    {loading ? (
                      <>
                        <Loader2 className="animate-spin" size={20} />
                        <span>Extracting...</span>
                      </>
                    ) : (
                      <>
                        <Brain size={20} />
                        <span>Extract Intelligence</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // Render extracting step
  if (step === 3) {
    return (
      <div className="bg-white rounded-xl shadow-lg p-6">
        <div className="text-center py-12">
          <Loader2 className="animate-spin mx-auto mb-4 text-blue-600" size={48} />
          <h3 className="text-xl font-semibold text-gray-900 mb-2">Extracting Intelligence...</h3>
          <p className="text-gray-600">
            Processing {selectedUrls.length + 1} URLs with {keywords.length} keywords.
          </p>
          <p className="text-gray-500 text-sm mt-2">
            This may take 1-3 minutes depending on content size.
          </p>
        </div>
      </div>
    );
  }

  // Render input step (Step 1)
  return (
    <div className="bg-white rounded-xl shadow-lg p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Extract Data</h2>
        <span className="px-3 py-1 bg-purple-100 text-purple-700 rounded-full text-sm font-medium flex items-center gap-1">
          <Zap size={14} />
          Enhanced V2
        </span>
      </div>

      <form onSubmit={inputType === 'url' ? handleDiscover : handleDirectExtract} className="space-y-6">
        {/* Input Type Selection */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-3">
            Source Type
          </label>
          <div className="grid grid-cols-3 gap-3">
            <button
              type="button"
              onClick={() => setInputType('url')}
              className={`flex items-center justify-center space-x-2 px-4 py-3 rounded-lg border-2 transition-all ${
                inputType === 'url'
                  ? 'border-blue-600 bg-blue-50 text-blue-700'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <Link size={20} />
              <span className="font-medium">URL</span>
            </button>
            <button
              type="button"
              onClick={() => setInputType('text')}
              className={`flex items-center justify-center space-x-2 px-4 py-3 rounded-lg border-2 transition-all ${
                inputType === 'text'
                  ? 'border-blue-600 bg-blue-50 text-blue-700'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <FileText size={20} />
              <span className="font-medium">Text</span>
            </button>
            <button
              type="button"
              onClick={() => setInputType('pdf')}
              className={`flex items-center justify-center space-x-2 px-4 py-3 rounded-lg border-2 transition-all ${
                inputType === 'pdf'
                  ? 'border-blue-600 bg-blue-50 text-blue-700'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <Upload size={20} />
              <span className="font-medium">PDF</span>
            </button>
          </div>
        </div>

        {/* URL Input */}
        {inputType === 'url' && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Enter Credit Card Page URL
            </label>
            <input
              type="url"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="https://www.bank.com/credit-cards/card-name"
            />
            <div className="mt-2 flex flex-wrap gap-2">
              <span className="text-xs text-gray-500">Quick examples:</span>
              {exampleUrls.map((example) => (
                <button
                  key={example.name}
                  type="button"
                  onClick={() => setInputValue(example.url)}
                  className="text-xs px-2 py-1 bg-gray-100 hover:bg-gray-200 rounded text-gray-600 transition-colors"
                >
                  {example.name}
                </button>
              ))}
            </div>
            <p className="mt-2 text-sm text-gray-500">
              Step 1: We'll discover related links (PDFs, terms, benefits pages) for you to select.
            </p>
          </div>
        )}

        {/* Text Input */}
        {inputType === 'text' && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Paste Text Content
            </label>
            <textarea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              rows={8}
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
              placeholder="Paste credit card benefits, terms, or any document text here..."
            />
          </div>
        )}

        {/* PDF Input */}
        {inputType === 'pdf' && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Upload PDF File
            </label>
            <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center hover:border-blue-500 transition-colors">
              <input
                type="file"
                accept=".pdf"
                onChange={(e) => setSelectedFile(e.target.files[0])}
                className="hidden"
                id="pdf-upload"
              />
              <label htmlFor="pdf-upload" className="cursor-pointer">
                <Upload className="mx-auto text-gray-400 mb-2" size={40} />
                <p className="text-sm text-gray-600">
                  {selectedFile ? (
                    <span className="text-blue-600 font-medium">{selectedFile.name}</span>
                  ) : (
                    <>Click to upload or drag and drop<br />
                    <span className="text-xs text-gray-500">PDF (max 50MB)</span></>
                  )}
                </p>
              </label>
            </div>
          </div>
        )}

        {/* Keywords Configuration for Text/PDF (when flexible extraction is enabled) */}
        {(inputType === 'text' || inputType === 'pdf') && useFlexibleExtraction && (
          <div className="border border-purple-200 rounded-lg p-4 bg-purple-50/50">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Tag className="text-purple-600" size={18} />
                <h4 className="font-medium text-gray-800">Relevance Keywords</h4>
              </div>
              <button
                type="button"
                onClick={resetKeywords}
                className="text-xs text-purple-600 hover:text-purple-800 flex items-center gap-1"
              >
                <RotateCcw size={12} />
                Reset to defaults
              </button>
            </div>
            
            <p className="text-sm text-gray-500 mb-3">
              These keywords are used to score and prioritize content sections.
            </p>
            
            {/* Add keyword input */}
            <div className="flex gap-2 mb-3">
              <input
                type="text"
                value={newKeyword}
                onChange={(e) => setNewKeyword(e.target.value)}
                onKeyPress={handleKeywordKeyPress}
                placeholder="Add a keyword..."
                className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
              />
              <button
                type="button"
                onClick={addKeyword}
                disabled={!newKeyword.trim()}
                className="px-3 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Plus size={16} />
              </button>
            </div>
            
            {/* Keywords list */}
            <div className="flex flex-wrap gap-2 max-h-32 overflow-y-auto">
              {keywords.slice(0, 20).map((keyword) => (
                <span
                  key={keyword}
                  className="group px-2 py-1 bg-white text-purple-700 rounded-full text-xs font-medium border border-purple-200 hover:bg-red-50 hover:text-red-700 hover:border-red-200 transition-colors flex items-center gap-1 cursor-pointer"
                  onClick={() => removeKeyword(keyword)}
                >
                  {keyword}
                  <X size={12} className="opacity-50 group-hover:opacity-100" />
                </span>
              ))}
              {keywords.length > 20 && (
                <span className="px-2 py-1 text-xs text-gray-500">
                  +{keywords.length - 20} more
                </span>
              )}
            </div>
          </div>
        )}

        {/* Advanced Options */}
        <div className="border border-gray-200 rounded-lg">
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="w-full px-4 py-3 flex items-center justify-between text-left"
          >
            <div className="flex items-center gap-2">
              <Settings2 size={18} className="text-gray-500" />
              <span className="font-medium text-gray-700">Advanced Options</span>
            </div>
            {showAdvanced ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
          </button>
          
          {showAdvanced && (
            <div className="px-4 pb-4 space-y-4 border-t border-gray-200 pt-4">
              {/* Flexible Intelligence Mode - NEW */}
              <div className="flex items-center justify-between p-3 bg-gradient-to-r from-purple-50 to-indigo-50 rounded-lg">
                <div className="flex items-center gap-3">
                  <Brain size={20} className="text-purple-600" />
                  <div>
                    <p className="font-medium text-gray-800">Flexible Intelligence Mode</p>
                    <p className="text-sm text-gray-500">Extract all intelligence without rigid categories</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setUseFlexibleExtraction(!useFlexibleExtraction)}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                    useFlexibleExtraction ? 'bg-purple-600' : 'bg-gray-300'
                  }`}
                >
                  <span className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${
                    useFlexibleExtraction ? 'translate-x-5' : 'translate-x-1'
                  }`} />
                </button>
              </div>
              
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-gray-800">Process PDFs</p>
                  <p className="text-sm text-gray-500">Extract text from PDF documents</p>
                </div>
                <button
                  type="button"
                  onClick={() => setProcessPdfs(!processPdfs)}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                    processPdfs ? 'bg-blue-600' : 'bg-gray-300'
                  }`}
                >
                  <span className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${
                    processPdfs ? 'translate-x-5' : 'translate-x-1'
                  }`} />
                </button>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-gray-800">Bypass Cache</p>
                  <p className="text-sm text-gray-500">Force fresh extraction</p>
                </div>
                <button
                  type="button"
                  onClick={() => setBypassCache(!bypassCache)}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                    bypassCache ? 'bg-blue-600' : 'bg-gray-300'
                  }`}
                >
                  <span className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${
                    bypassCache ? 'translate-x-5' : 'translate-x-1'
                  }`} />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Submit Button */}
        <button
          type="submit"
          disabled={loading || discovering}
          className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 text-white py-3 px-6 rounded-lg font-semibold hover:from-blue-700 hover:to-indigo-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-2"
        >
          {discovering ? (
            <>
              <Loader2 className="animate-spin" size={20} />
              <span>Discovering links...</span>
            </>
          ) : loading ? (
            <>
              <Loader2 className="animate-spin" size={20} />
              <span>Extracting...</span>
            </>
          ) : inputType === 'url' ? (
            <>
              <Search size={20} />
              <span>Discover Related Links</span>
            </>
          ) : (
            <>
              <Zap size={20} />
              <span>Extract Data</span>
            </>
          )}
        </button>

        {/* Error Message */}
        {error && (
          <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-start space-x-3">
            <AlertCircle className="text-red-600 flex-shrink-0 mt-0.5" size={20} />
            <div>
              <p className="font-semibold text-red-800">Error</p>
              <p className="text-sm text-red-700">{error}</p>
            </div>
          </div>
        )}

        {/* Success Message */}
        {success && (
          <div className="p-4 bg-green-50 border border-green-200 rounded-lg flex items-start space-x-3">
            <CheckCircle className="text-green-600 flex-shrink-0 mt-0.5" size={20} />
            <div>
              <p className="font-semibold text-green-800">Success!</p>
              <p className="text-sm text-green-700">Data extracted successfully. Check results →</p>
            </div>
          </div>
        )}
      </form>
    </div>
  );
}

export default ExtractionFormV2;