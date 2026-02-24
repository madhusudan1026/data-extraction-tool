import React, { useState, useEffect } from 'react';
import {
  Trash2, RefreshCw, Loader2, AlertTriangle, CheckCircle, Database,
  ChevronDown, ChevronUp, Shield
} from 'lucide-react';

import { API_V5 as API } from '../config';

const GROUPS = [
  {
    key: 'clean_v5', label: 'V5 Structured Extraction',
    desc: 'Sessions, cards, sections, benefits, URLs',
    collections: ['v5_sessions', 'v5_cards', 'v5_card_sections', 'v5_benefit_sections', 'v5_scraped_urls', 'v5_discovered_urls', 'v5_depth2_sections'],
    color: 'teal',
  },
  {
    key: 'clean_v4', label: 'V4 Enhanced Extraction (Legacy)',
    desc: 'Old wizard sessions and discovered cards',
    collections: ['v4_sessions', 'session_cards'],
    color: 'purple',
  },
  {
    key: 'clean_v2', label: 'V2 Single Card (Legacy)',
    desc: 'Old extraction sessions and raw data',
    collections: ['extraction_sessions', 'raw_extractions'],
    color: 'blue',
  },
  {
    key: 'clean_approved_raw', label: 'Approved Raw Data (DataStore)',
    desc: 'Stored card data ready for vectorization',
    collections: ['approved_raw_data'],
    color: 'orange',
  },
  {
    key: 'clean_vectors', label: 'ChromaDB Vectors',
    desc: 'All vectorized chunk embeddings',
    collections: ['chromadb_vectors'],
    color: 'red',
  },
  {
    key: 'clean_pipelines', label: 'Pipeline Results',
    desc: 'Extracted benefits and pipeline outputs',
    collections: ['pipeline_results', 'aggregated_pipeline_results', 'approved_benefits', 'approved_intelligence'],
    color: 'green',
  },
  {
    key: 'clean_redis', label: 'Redis Cache',
    desc: 'Cached scrape results and LLM responses',
    collections: ['redis_keys'],
    color: 'yellow',
  },
];

export default function SystemCleanup() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [cleaning, setCleaning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(() => {
    const s = {};
    GROUPS.forEach(g => s[g.key] = true);
    return s;
  });
  const [confirmText, setConfirmText] = useState('');

  const loadStats = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/system/stats`);
      const data = await res.json();
      setStats(data.stats || {});
    } catch (err) {
      setError('Failed to load stats: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadStats(); }, []);

  const totalSelected = () => {
    if (!stats) return 0;
    let total = 0;
    GROUPS.forEach(g => {
      if (selected[g.key]) {
        g.collections.forEach(c => { total += (stats[c] || 0); });
      }
    });
    return total;
  };

  const runCleanup = async () => {
    if (confirmText !== 'DELETE ALL') return;
    setCleaning(true); setError(''); setResult(null);
    try {
      const params = new URLSearchParams();
      GROUPS.forEach(g => params.append(g.key, selected[g.key]));
      const res = await fetch(`${API}/system/cleanup?${params.toString()}`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Cleanup failed');
      setResult(data);
      setConfirmText('');
      await loadStats();
    } catch (err) {
      setError(err.message);
    } finally {
      setCleaning(false);
    }
  };

  const groupCount = (group) => {
    if (!stats) return 0;
    return group.collections.reduce((sum, c) => sum + (stats[c] || 0), 0);
  };

  const totalDocs = stats ? Object.values(stats).reduce((s, v) => s + (typeof v === 'number' ? v : 0), 0) : 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-red-100 rounded-lg"><Shield size={24} className="text-red-600" /></div>
          <div>
            <h2 className="text-lg font-bold text-gray-800">System Cleanup</h2>
            <p className="text-sm text-gray-500">Clear collections, vectors, and caches for a fresh start</p>
          </div>
        </div>
        <button onClick={loadStats} disabled={loading}
          className="px-3 py-1.5 border rounded-lg text-sm hover:bg-gray-50 flex items-center gap-1">
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />} Refresh
        </button>
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm flex items-center gap-2">
          <AlertTriangle size={16} /> {error}
        </div>
      )}

      {result && (
        <div className="p-4 bg-green-50 border border-green-200 rounded-lg space-y-2">
          <div className="flex items-center gap-2 text-green-700 font-medium">
            <CheckCircle size={18} /> Cleanup complete — {result.total_documents_deleted} documents deleted
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {Object.entries(result.report || {}).map(([k, v]) => (
              <div key={k} className="text-xs bg-white px-2 py-1 rounded border">
                <span className="text-gray-500">{k}:</span> <span className="font-medium">{typeof v === 'number' ? v : v}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Summary bar */}
      {stats && (
        <div className="p-3 bg-gray-50 border rounded-lg flex items-center justify-between">
          <span className="text-sm text-gray-600">
            Total data: <strong className="text-gray-800">{totalDocs.toLocaleString()}</strong> documents + vectors
          </span>
          <span className="text-sm text-red-600 font-medium">
            Selected for deletion: <strong>{totalSelected().toLocaleString()}</strong>
          </span>
        </div>
      )}

      {/* Group toggles */}
      <div className="space-y-2">
        {GROUPS.map(group => {
          const count = groupCount(group);
          const isOn = selected[group.key];
          return (
            <div key={group.key}
              className={`p-3 rounded-lg border flex items-center justify-between transition-all ${
                isOn ? 'border-red-200 bg-red-50/50' : 'border-gray-200 bg-white'
              }`}>
              <div className="flex items-center gap-3">
                <button onClick={() => setSelected(s => ({ ...s, [group.key]: !s[group.key] }))}
                  className={`w-10 h-5 rounded-full transition-colors ${isOn ? 'bg-red-500' : 'bg-gray-300'}`}>
                  <div className={`w-4 h-4 bg-white rounded-full shadow transform transition-transform ${isOn ? 'translate-x-5' : 'translate-x-0.5'}`} />
                </button>
                <div>
                  <div className="text-sm font-medium text-gray-800">{group.label}</div>
                  <div className="text-xs text-gray-500">{group.desc}</div>
                </div>
              </div>
              <div className="text-right">
                <div className={`text-lg font-bold ${count > 0 ? 'text-gray-800' : 'text-gray-300'}`}>{count.toLocaleString()}</div>
                <div className="text-xs text-gray-400">docs</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Confirm + Execute */}
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg space-y-3">
        <div className="flex items-center gap-2 text-red-700 font-medium">
          <AlertTriangle size={18} /> This action is irreversible
        </div>
        <div className="flex items-center gap-3">
          <input
            type="text"
            value={confirmText}
            onChange={e => setConfirmText(e.target.value)}
            placeholder='Type "DELETE ALL" to confirm'
            className="flex-1 px-3 py-2 border border-red-300 rounded-lg text-sm focus:ring-2 focus:ring-red-500 focus:border-red-500 bg-white"
          />
          <button onClick={runCleanup}
            disabled={cleaning || confirmText !== 'DELETE ALL' || totalSelected() === 0}
            className="px-6 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 flex items-center gap-2 font-medium disabled:opacity-40 disabled:cursor-not-allowed transition-all">
            {cleaning ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
            {cleaning ? 'Cleaning...' : `Delete ${totalSelected().toLocaleString()} Items`}
          </button>
        </div>
      </div>
    </div>
  );
}
