import React, { useState } from 'react';
import StructuredExtractionWizard from './components/StructuredExtractionWizard';
import DataStoreVectorization from './components/DataStoreVectorization';
import PipelineExecution from './components/PipelineExecution';
import ExtractionsList from './components/ExtractionsList';
import SystemCleanup from './components/SystemCleanup';
import { FileText, Database, Zap, Wand2, Settings } from 'lucide-react';

function App() {
  const [activeTab, setActiveTab] = useState('structured');

  const tabs = [
    { key: 'structured', label: 'Structured Extraction', icon: Zap, gradient: 'from-teal-600 to-blue-600' },
    { key: 'stored', label: 'Data Store & Vectorization', icon: Database, gradient: 'from-purple-600 to-indigo-600' },
    { key: 'pipelines', label: 'Pipeline Execution', icon: Wand2, gradient: 'from-blue-600 to-teal-600' },
    { key: 'history', label: 'History', icon: Database, gradient: 'from-gray-600 to-gray-700' },
    { key: 'cleanup', label: 'System', icon: Settings, gradient: 'from-red-600 to-orange-600' },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50">
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="bg-gradient-to-r from-blue-600 to-indigo-600 p-2 rounded-lg">
                <FileText className="text-white" size={28} />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-gray-900">Credit Card Data Extractor</h1>
                <p className="text-sm text-gray-500 flex items-center gap-1">
                  <Zap size={14} className="text-purple-500" />
                  Structured Extraction & Vectorization Pipeline
                </p>
              </div>
            </div>
            <span className="px-3 py-1 bg-green-100 text-green-700 rounded-full text-sm font-medium">● Online</span>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-6">
        <div className="bg-white rounded-lg shadow-sm p-1 inline-flex flex-wrap">
          {tabs.map(tab => {
            const Icon = tab.icon;
            return (
              <button key={tab.key} onClick={() => setActiveTab(tab.key)}
                className={`px-6 py-2 rounded-md font-medium transition-all ${
                  activeTab === tab.key
                    ? `bg-gradient-to-r ${tab.gradient} text-white shadow-sm`
                    : 'text-gray-600 hover:text-gray-900'
                }`}>
                <div className="flex items-center space-x-2">
                  <Icon size={18} />
                  <span>{tab.label}</span>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* All tabs stay mounted — hidden with CSS instead of unmounted */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div style={{ display: activeTab === 'structured' ? 'block' : 'none' }}>
          <StructuredExtractionWizard />
        </div>
        <div style={{ display: activeTab === 'stored' ? 'block' : 'none' }}>
          <DataStoreVectorization />
        </div>
        <div style={{ display: activeTab === 'pipelines' ? 'block' : 'none' }}>
          <PipelineExecution />
        </div>
        <div style={{ display: activeTab === 'history' ? 'block' : 'none' }}>
          <ExtractionsList />
        </div>
        <div style={{ display: activeTab === 'cleanup' ? 'block' : 'none' }}>
          <SystemCleanup />
        </div>
      </main>

      <footer className="mt-12 py-6 border-t border-gray-200 bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <p className="text-center text-gray-500 text-sm">
            Powered by Open-Source LLMs • MongoDB • ChromaDB • Playwright
          </p>
        </div>
      </footer>
    </div>
  );
}

export default App;
