import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// V1 Extraction API (original)
export const extractionAPI = {
  extractFromText: async (text, config = {}) => {
    const response = await api.post('/api/extraction/text', { text, config });
    return response.data;
  },

  extractFromURL: async (url, config = {}) => {
    const response = await api.post('/api/extraction/url', { url, config });
    return response.data;
  },

  extractFromPDF: async (file, config = {}) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('config', JSON.stringify(config));

    const response = await api.post('/api/extraction/pdf', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  getExtraction: async (id) => {
    const response = await api.get(`/api/extraction/${id}`);
    return response.data;
  },

  listExtractions: async (params = {}) => {
    const response = await api.get('/api/extraction', { params });
    return response.data;
  },

  deleteExtraction: async (id) => {
    const response = await api.delete(`/api/extraction/${id}`);
    return response.data;
  },
};

// V2 Enhanced Extraction API (new)
export const extractionAPIv2 = {
  // Step 1: Discover related URLs
  discoverUrls: async (url) => {
    const response = await api.post('/api/v2/extraction/discover', { url });
    return response.data;
  },

  // Step 2: Extract with selected URLs
  extractWithSelectedUrls: async (url, selectedUrls, config = {}) => {
    const response = await api.post('/api/v2/extraction/extract-with-urls', {
      url,
      selected_urls: selectedUrls,
      config: {
        follow_links: true,
        process_pdfs: config.processPdfs ?? true,
        bypass_cache: config.bypassCache ?? false,
        store_raw_text: true,
        ...config
      }
    });
    return response.data;
  },

  extractFromText: async (text, config = {}) => {
    const response = await api.post('/api/v2/extraction/text', { 
      text, 
      config: {
        follow_links: config.followLinks ?? true,
        max_depth: config.maxDepth ?? 1,
        bypass_cache: config.bypassCache ?? false,
        store_raw_text: true,
        ...config
      }
    });
    return response.data;
  },

  extractFromURL: async (url, config = {}) => {
    const response = await api.post('/api/v2/extraction/url', { 
      url, 
      config: {
        follow_links: config.followLinks ?? true,
        max_depth: config.maxDepth ?? 1,
        bypass_cache: config.bypassCache ?? false,
        store_raw_text: true,
        ...config
      }
    });
    return response.data;
  },

  extractFromPDF: async (file, config = {}) => {
    const formData = new FormData();
    formData.append('file', file);

    const params = new URLSearchParams({
      follow_links: config.followLinks ?? false,
      bypass_cache: config.bypassCache ?? false,
    });

    const response = await api.post(`/api/v2/extraction/pdf?${params}`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  getExtraction: async (id) => {
    const response = await api.get(`/api/v2/extraction/${id}`);
    return response.data;
  },

  listExtractions: async (params = {}) => {
    const response = await api.get('/api/v2/extraction', { params });
    return response.data;
  },

  deleteExtraction: async (id) => {
    const response = await api.delete(`/api/v2/extraction/${id}`);
    return response.data;
  },

  search: async (searchParams = {}) => {
    const response = await api.post('/api/v2/extraction/search', searchParams);
    return response.data;
  },

  getByBank: async (bankName, limit = 50) => {
    const response = await api.get(`/api/v2/extraction/by-bank/${encodeURIComponent(bankName)}`, {
      params: { limit }
    });
    return response.data;
  },

  getByMerchant: async (merchantName, limit = 50) => {
    const response = await api.get(`/api/v2/extraction/by-merchant/${encodeURIComponent(merchantName)}`, {
      params: { limit }
    });
    return response.data;
  },

  // Flexible intelligence extraction from URL
  extractIntelligence: async (url, selectedUrls = [], config = {}) => {
    const response = await api.post('/api/v2/extraction/extract-intelligence', {
      url,
      selected_urls: selectedUrls,
      process_pdfs: config.processPdfs ?? true,
      bypass_cache: config.bypassCache ?? false,
      keywords: config.keywords ?? null  // Custom keywords for relevance scoring
    });
    return response.data;
  },

  // Flexible intelligence extraction from TEXT
  extractIntelligenceFromText: async (text, sourceName = 'Pasted Text', config = {}) => {
    const response = await api.post('/api/v2/extraction/extract-intelligence-text', {
      text,
      source_name: sourceName,
      keywords: config.keywords ?? null
    });
    return response.data;
  },

  // Flexible intelligence extraction from PDF file
  extractIntelligenceFromPDF: async (file, config = {}) => {
    const formData = new FormData();
    formData.append('file', file);
    
    // Add keywords as query parameter
    const params = new URLSearchParams();
    if (config.keywords && config.keywords.length > 0) {
      params.append('keywords', config.keywords.join(','));
    }
    
    const url = params.toString() 
      ? `/api/v2/extraction/extract-intelligence-pdf?${params}`
      : '/api/v2/extraction/extract-intelligence-pdf';
    
    const response = await api.post(url, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  // Save approved/edited intelligence to database
  saveApprovedIntelligence: async (approvedData) => {
    const response = await api.post('/api/v2/extraction/save-approved', approvedData);
    return response.data;
  },

  // Save approved raw data to database (before LLM processing)
  saveApprovedRawData: async (approvedData) => {
    const response = await api.post('/api/v2/extraction/save-approved-raw', approvedData);
    return response.data;
  },

  // List approved raw data
  listApprovedRawData: async (params = {}) => {
    const response = await api.get('/api/v2/extraction/approved-raw', { params });
    return response.data;
  },

  // Get specific approved raw data
  getApprovedRawData: async (savedId) => {
    const response = await api.get(`/api/v2/extraction/approved-raw/${savedId}`);
    return response.data;
  },

  // Get raw extraction data
  getRawExtraction: async (extractionId, includeContent = false) => {
    const response = await api.get(`/api/v2/extraction/raw-extractions/${extractionId}`, {
      params: { include_content: includeContent }
    });
    return response.data;
  },

  // List raw extractions
  listRawExtractions: async (params = {}) => {
    const response = await api.get('/api/v2/extraction/raw-extractions', { params });
    return response.data;
  },

  // Get detected patterns from raw extraction
  getRawExtractionPatterns: async (extractionId) => {
    const response = await api.get(`/api/v2/extraction/raw-extractions/${extractionId}/patterns`);
    return response.data;
  },

  // Get sections from raw extraction
  getRawExtractionSections: async (extractionId, selectedOnly = false, minScore = 0) => {
    const response = await api.get(`/api/v2/extraction/raw-extractions/${extractionId}/sections`, {
      params: { selected_only: selectedOnly, min_score: minScore }
    });
    return response.data;
  },

  // =========== Pipeline API ===========
  
  // List available pipelines
  listPipelines: async () => {
    const response = await api.get('/api/v2/extraction/pipelines');
    return response.data;
  },

  // Get pipeline info
  getPipelineInfo: async (pipelineName) => {
    const response = await api.get(`/api/v2/extraction/pipelines/${pipelineName}`);
    return response.data;
  },

  // Run single pipeline on raw data
  runPipeline: async (pipelineName, rawDataId, saveResults = true) => {
    const response = await api.post(
      `/api/v2/extraction/pipelines/run/${pipelineName}/${rawDataId}`,
      null,
      { params: { save_results: saveResults } }
    );
    return response.data;
  },

  // Run multiple/all pipelines on raw data
  runAllPipelines: async (rawDataId, options = {}) => {
    const response = await api.post(
      `/api/v2/extraction/pipelines/run-all/${rawDataId}`,
      {
        pipeline_names: options.pipelineNames || null,
        source_indices: options.sourceIndices || null
      },
      { 
        params: { 
          save_results: options.saveResults ?? true,
          parallel: options.parallel ?? true
        } 
      }
    );
    return response.data;
  },

  // Get pipeline results for a raw data record
  getPipelineResults: async (rawDataId, pipelineName = null) => {
    const params = pipelineName ? { pipeline_name: pipelineName } : {};
    const response = await api.get(`/api/v2/extraction/pipelines/results/${rawDataId}`, { params });
    return response.data;
  },

  // Get aggregated results from all pipelines
  getAggregatedResults: async (rawDataId) => {
    const response = await api.get(`/api/v2/extraction/pipelines/aggregated/${rawDataId}`);
    return response.data;
  },

  // Save approved pipeline results
  saveApprovedPipelineResults: async (approvedData) => {
    const response = await api.post('/api/v2/extraction/save-approved-benefits', approvedData);
    return response.data;
  },

  // Delete a specific benefit from pipeline results
  deleteBenefit: async (rawDataId, benefitId) => {
    const response = await api.delete(`/api/v2/extraction/pipelines/benefit/${rawDataId}/${benefitId}`);
    return response.data;
  },
};

export const batchAPI = {
  createBatch: async (items, config = {}) => {
    const response = await api.post('/api/batch/create', { items, config });
    return response.data;
  },

  getBatchStatus: async (jobId) => {
    const response = await api.get(`/api/batch/${jobId}`);
    return response.data;
  },

  getBatchResults: async (jobId) => {
    const response = await api.get(`/api/batch/${jobId}/results`);
    return response.data;
  },
};

export default api;
