import React, { useState } from 'react';
import ExtractionForm from './components/ExtractionFormV2';
import ResultsDisplay from './components/ResultsDisplayV2';
import IntelligenceResultsDisplay from './components/IntelligenceResultsDisplay';
import RawDataReviewApproval from './components/RawDataReviewApproval';
import ExtractionsList from './components/ExtractionsList';
import PipelineResultsViewer from './components/PipelineResultsViewer';
import ExtractionWizard from './components/ExtractionWizard';
import DataStoreVectorization from './components/DataStoreVectorization';
import PipelineExecution from './components/PipelineExecution';
import StructuredExtractionWizard from './components/StructuredExtractionWizard';
import { FileText, Database, Zap, CheckCircle, Wand2 } from 'lucide-react';
import { extractionAPIv2 } from './services/api';

function App() {
  const [activeTab, setActiveTab] = useState('wizard');
  const [extractionResult, setExtractionResult] = useState(null);
  const [rawExtractionData, setRawExtractionData] = useState(null);
  const [usedKeywords, setUsedKeywords] = useState([]);
  const [showRawReview, setShowRawReview] = useState(false);
  const [approvalSuccess, setApprovalSuccess] = useState(null);

  // Handle regular extraction results
  const handleResult = (result) => {
    setExtractionResult(result);
    setRawExtractionData(null);
    setShowRawReview(false);
    setApprovalSuccess(null);
  };

  // Handle intelligence extraction results - show raw data for review
  const handleIntelligenceResult = (result, keywords = []) => {
    // Store the raw extraction data for review
    setRawExtractionData(result);
    setUsedKeywords(keywords);
    setShowRawReview(true);  // Show raw data review screen
    setExtractionResult(null);
    setApprovalSuccess(null);
  };

  // Handle approval of raw data - save to MongoDB
  const handleApproveRawData = async (approvedData) => {
    try {
      // Call API to save approved raw data
      const response = await extractionAPIv2.saveApprovedRawData(approvedData);
      
      setApprovalSuccess({
        message: `Successfully stored ${approvedData.total_sources} sources (${approvedData.total_content_length.toLocaleString()} characters)`,
        savedId: response.saved_id,
        sourcesCount: approvedData.total_sources
      });
      setShowRawReview(false);
      
    } catch (error) {
      console.error('Failed to save:', error);
      throw error;
    }
  };

  // Handle cancel review
  const handleCancelReview = () => {
    setShowRawReview(false);
    setRawExtractionData(null);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="bg-gradient-to-r from-blue-600 to-indigo-600 p-2 rounded-lg">
                <FileText className="text-white" size={28} />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-gray-900">
                  Credit Card Data Extractor
                </h1>
                <p className="text-sm text-gray-500 flex items-center gap-1">
                  <Zap size={14} className="text-purple-500" />
                  Raw Data Extraction & Storage
                </p>
              </div>
            </div>
            <div className="flex items-center space-x-2">
              <span className="px-3 py-1 bg-green-100 text-green-700 rounded-full text-sm font-medium">
                ● Online
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Navigation Tabs */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-6">
        <div className="bg-white rounded-lg shadow-sm p-1 inline-flex flex-wrap">
          <button
            onClick={() => setActiveTab('structured')}
            className={`px-6 py-2 rounded-md font-medium transition-all ${
              activeTab === 'structured'
                ? 'bg-gradient-to-r from-teal-600 to-blue-600 text-white shadow-sm'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            <div className="flex items-center space-x-2">
              <Zap size={18} />
              <span>Structured (V5)</span>
            </div>
          </button>
          <button
            onClick={() => setActiveTab('wizard')}
            className={`px-6 py-2 rounded-md font-medium transition-all ${
              activeTab === 'wizard'
                ? 'bg-gradient-to-r from-purple-600 to-blue-600 text-white shadow-sm'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            <div className="flex items-center space-x-2">
              <Wand2 size={18} />
              <span>Enhanced Extraction</span>
            </div>
          </button>
          <button
            onClick={() => setActiveTab('extract')}
            className={`px-6 py-2 rounded-md font-medium transition-all ${
              activeTab === 'extract'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            <div className="flex items-center space-x-2">
              <Zap size={18} />
              <span>Single Card (V2)</span>
            </div>
          </button>
          <button
            onClick={() => setActiveTab('stored')}
            className={`px-6 py-2 rounded-md font-medium transition-all ${
              activeTab === 'stored'
                ? 'bg-gradient-to-r from-purple-600 to-indigo-600 text-white shadow-sm'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            <div className="flex items-center space-x-2">
              <Database size={18} />
              <span>Data Store & Vectorization</span>
            </div>
          </button>
          <button
            onClick={() => setActiveTab('pipelines')}
            className={`px-6 py-2 rounded-md font-medium transition-all ${
              activeTab === 'pipelines'
                ? 'bg-gradient-to-r from-blue-600 to-teal-600 text-white shadow-sm'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            <div className="flex items-center space-x-2">
              <Zap size={18} />
              <span>Pipeline Execution</span>
            </div>
          </button>
          <button
            onClick={() => setActiveTab('history')}
            className={`px-6 py-2 rounded-md font-medium transition-all ${
              activeTab === 'history'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            <div className="flex items-center space-x-2">
              <Database size={18} />
              <span>History</span>
            </div>
          </button>
        </div>
      </div>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* V5 Structured Extraction Tab */}
        {activeTab === 'structured' && (
          <StructuredExtractionWizard />
        )}

        {/* V4 Wizard Tab */}
        {activeTab === 'wizard' && (
          <ExtractionWizard />
        )}

        {activeTab === 'extract' && (
          <>
            {/* Success Message */}
            {approvalSuccess && (
              <div className="mb-6 bg-green-50 border border-green-200 rounded-lg p-4 flex items-center gap-3">
                <CheckCircle className="text-green-600" size={24} />
                <div>
                  <p className="font-medium text-green-800">{approvalSuccess.message}</p>
                  <p className="text-sm text-green-600">
                    Stored ID: <code className="bg-green-100 px-2 py-0.5 rounded">{approvalSuccess.savedId}</code>
                  </p>
                </div>
              </div>
            )}

            {/* Raw Data Review Mode */}
            {showRawReview && rawExtractionData && (
              <RawDataReviewApproval
                extractionData={rawExtractionData}
                keywords={usedKeywords}
                onApprove={handleApproveRawData}
                onCancel={handleCancelReview}
              />
            )}

            {/* Normal Mode - Extraction Form */}
            {!showRawReview && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <ExtractionForm 
                  onResult={handleResult} 
                  onIntelligenceResult={handleIntelligenceResult}
                />
                
                {extractionResult && (
                  <ResultsDisplay result={extractionResult} />
                )}
              </div>
            )}
          </>
        )}

        {activeTab === 'stored' && <DataStoreVectorization />}

        {activeTab === 'pipelines' && <PipelineExecution />}
        
        {activeTab === 'history' && <ExtractionsList />}
      </main>

      {/* Footer */}
      <footer className="mt-12 py-6 border-t border-gray-200 bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <p className="text-center text-gray-500 text-sm">
            Powered by Open-Source LLMs • MongoDB • Raw Data Storage Pipeline
          </p>
        </div>
      </footer>
    </div>
  );
}


export default App;
