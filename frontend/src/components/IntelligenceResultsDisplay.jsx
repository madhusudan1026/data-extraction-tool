import React, { useState } from 'react';
import { 
  CreditCard, Building2, Tag, AlertCircle, CheckCircle, 
  ChevronDown, ChevronRight, Star, Filter, Search,
  DollarSign, Users, Clock, MapPin, Percent, Gift,
  Shield, Plane, Coffee, ShoppingBag, Zap, ExternalLink
} from 'lucide-react';

// Category icons and colors
const categoryConfig = {
  reward: { icon: Gift, color: 'text-purple-600', bg: 'bg-purple-100' },
  access: { icon: DollarSign, color: 'text-blue-600', bg: 'bg-blue-100' },
  discount: { icon: Percent, color: 'text-green-600', bg: 'bg-green-100' },
  complimentary: { icon: Gift, color: 'text-pink-600', bg: 'bg-pink-100' },
  insurance: { icon: Shield, color: 'text-red-600', bg: 'bg-red-100' },
  service: { icon: Users, color: 'text-indigo-600', bg: 'bg-indigo-100' },
  fee: { icon: DollarSign, color: 'text-orange-600', bg: 'bg-orange-100' },
  limit: { icon: AlertCircle, color: 'text-yellow-600', bg: 'bg-yellow-100' },
  eligibility: { icon: CheckCircle, color: 'text-teal-600', bg: 'bg-teal-100' },
  partner: { icon: Building2, color: 'text-cyan-600', bg: 'bg-cyan-100' },
  promotion: { icon: Zap, color: 'text-amber-600', bg: 'bg-amber-100' },
  feature: { icon: Star, color: 'text-violet-600', bg: 'bg-violet-100' },
  program: { icon: CreditCard, color: 'text-emerald-600', bg: 'bg-emerald-100' },
  other: { icon: Tag, color: 'text-gray-600', bg: 'bg-gray-100' },
};

function IntelligenceItem({ item, isExpanded, onToggle }) {
  const config = categoryConfig[item.category] || categoryConfig.other;
  const Icon = config.icon;
  
  return (
    <div className={`border rounded-lg mb-3 ${item.is_headline ? 'border-blue-300 bg-blue-50' : 'border-gray-200'}`}>
      <div 
        className="p-4 cursor-pointer flex items-start gap-3"
        onClick={onToggle}
      >
        <div className={`p-2 rounded-lg ${config.bg}`}>
          <Icon className={config.color} size={20} />
        </div>
        
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h4 className="font-semibold text-gray-900">{item.title}</h4>
            {item.is_headline && (
              <span className="px-2 py-0.5 bg-blue-600 text-white text-xs rounded-full">
                Key Benefit
              </span>
            )}
            {item.is_conditional && (
              <span className="px-2 py-0.5 bg-yellow-100 text-yellow-700 text-xs rounded">
                Conditional
              </span>
            )}
            {item.requires_enrollment && (
              <span className="px-2 py-0.5 bg-purple-100 text-purple-700 text-xs rounded">
                Requires Enrollment
              </span>
            )}
          </div>
          
          <p className="text-sm text-gray-600 mt-1 line-clamp-2">{item.description}</p>
          
          {/* Value badge */}
          {item.value && (
            <span className="inline-block mt-2 px-3 py-1 bg-green-100 text-green-700 text-sm font-medium rounded-full">
              {item.value.raw_value}
            </span>
          )}
          
          {/* Tags */}
          {item.tags.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {item.tags.slice(0, 5).map((tag, i) => (
                <span key={i} className="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded">
                  {tag}
                </span>
              ))}
              {item.tags.length > 5 && (
                <span className="text-xs text-gray-500">+{item.tags.length - 5} more</span>
              )}
            </div>
          )}
        </div>
        
        <div className="flex-shrink-0">
          {isExpanded ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
        </div>
      </div>
      
      {/* Expanded details */}
      {isExpanded && (
        <div className="px-4 pb-4 pt-0 border-t border-gray-100">
          {/* Full description */}
          <div className="mt-3">
            <h5 className="text-sm font-medium text-gray-700">Full Details</h5>
            <p className="text-sm text-gray-600 mt-1">{item.description}</p>
          </div>
          
          {/* Conditions */}
          {item.conditions.length > 0 && (
            <div className="mt-3">
              <h5 className="text-sm font-medium text-gray-700">Conditions</h5>
              <ul className="mt-1 space-y-1">
                {item.conditions.map((cond, i) => (
                  <li key={i} className="text-sm text-gray-600 flex items-start gap-2">
                    <AlertCircle size={14} className="text-yellow-500 mt-0.5 flex-shrink-0" />
                    <span>{cond.description}</span>
                    {cond.value && (
                      <span className="text-gray-500">({String(cond.value)})</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          
          {/* Entities */}
          {item.entities.length > 0 && (
            <div className="mt-3">
              <h5 className="text-sm font-medium text-gray-700">Related Partners/Locations</h5>
              <div className="flex flex-wrap gap-2 mt-1">
                {item.entities.map((entity, i) => (
                  <span key={i} className="px-2 py-1 bg-indigo-50 text-indigo-700 text-sm rounded flex items-center gap-1">
                    <Building2 size={12} />
                    {entity.name}
                    <span className="text-indigo-400 text-xs">({entity.type})</span>
                  </span>
                ))}
              </div>
            </div>
          )}
          
          {/* Source */}
          {item.source_url && (
            <div className="mt-3 text-xs text-gray-500 flex items-center gap-1">
              <ExternalLink size={12} />
              <a href={item.source_url} target="_blank" rel="noopener noreferrer" className="hover:text-blue-600">
                Source
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function IntelligenceResultsDisplay({ data }) {
  const [expandedItems, setExpandedItems] = useState(new Set());
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [showHeadlinesOnly, setShowHeadlinesOnly] = useState(false);
  
  if (!data) return null;
  
  const toggleItem = (itemId) => {
    const newExpanded = new Set(expandedItems);
    if (newExpanded.has(itemId)) {
      newExpanded.delete(itemId);
    } else {
      newExpanded.add(itemId);
    }
    setExpandedItems(newExpanded);
  };
  
  // Filter intelligence items
  let filteredItems = data.intelligence || [];
  
  if (selectedCategory !== 'all') {
    filteredItems = filteredItems.filter(item => item.category === selectedCategory);
  }
  
  if (showHeadlinesOnly) {
    filteredItems = filteredItems.filter(item => item.is_headline);
  }
  
  if (searchQuery) {
    const query = searchQuery.toLowerCase();
    filteredItems = filteredItems.filter(item => 
      item.title.toLowerCase().includes(query) ||
      item.description.toLowerCase().includes(query) ||
      item.tags.some(t => t.toLowerCase().includes(query))
    );
  }
  
  const categories = Object.keys(data.items_by_category || {});
  
  return (
    <div className="bg-white rounded-xl shadow-lg p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">{data.card?.name || 'Credit Card'}</h2>
          <p className="text-gray-600">{data.card?.bank || 'Unknown Bank'}</p>
        </div>
        <div className="text-right">
          <div className="text-3xl font-bold text-blue-600">{data.total_items}</div>
          <div className="text-sm text-gray-500">Intelligence Items</div>
        </div>
      </div>
      
      {/* Quality metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-blue-50 rounded-lg p-3">
          <div className="text-sm text-blue-600 font-medium">Confidence</div>
          <div className="text-xl font-bold text-blue-800">
            {Math.round((data.confidence_score || 0) * 100)}%
          </div>
        </div>
        <div className="bg-green-50 rounded-lg p-3">
          <div className="text-sm text-green-600 font-medium">Completeness</div>
          <div className="text-xl font-bold text-green-800">
            {Math.round((data.completeness_score || 0) * 100)}%
          </div>
        </div>
        <div className="bg-purple-50 rounded-lg p-3">
          <div className="text-sm text-purple-600 font-medium">Sources</div>
          <div className="text-xl font-bold text-purple-800">
            {data.sources_processed?.length || 0}
          </div>
        </div>
        <div className="bg-orange-50 rounded-lg p-3">
          <div className="text-sm text-orange-600 font-medium">Categories</div>
          <div className="text-xl font-bold text-orange-800">
            {categories.length}
          </div>
        </div>
      </div>
      
      {/* Fees & Eligibility quick view */}
      <div className="grid md:grid-cols-2 gap-4 mb-6">
        {/* Fees */}
        {data.fees && (
          <div className="border rounded-lg p-4">
            <h3 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
              <DollarSign size={18} className="text-orange-600" />
              Fees
            </h3>
            <div className="space-y-2 text-sm">
              {data.fees.annual_fee && (
                <div className="flex justify-between">
                  <span className="text-gray-600">Annual Fee</span>
                  <span className="font-medium">{data.fees.annual_fee.raw_value}</span>
                </div>
              )}
              {data.fees.joining_fee && (
                <div className="flex justify-between">
                  <span className="text-gray-600">Joining Fee</span>
                  <span className="font-medium">{data.fees.joining_fee.raw_value}</span>
                </div>
              )}
              {data.fees.supplementary_card_fee && (
                <div className="flex justify-between">
                  <span className="text-gray-600">Supplementary Card</span>
                  <span className="font-medium">{data.fees.supplementary_card_fee.raw_value}</span>
                </div>
              )}
            </div>
          </div>
        )}
        
        {/* Eligibility */}
        {data.eligibility && (
          <div className="border rounded-lg p-4">
            <h3 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
              <Users size={18} className="text-teal-600" />
              Eligibility
            </h3>
            <div className="space-y-2 text-sm">
              {data.eligibility.minimum_salary && (
                <div className="flex justify-between">
                  <span className="text-gray-600">Min. Salary</span>
                  <span className="font-medium">{data.eligibility.minimum_salary.raw_value}</span>
                </div>
              )}
              {data.eligibility.minimum_age && (
                <div className="flex justify-between">
                  <span className="text-gray-600">Min. Age</span>
                  <span className="font-medium">{data.eligibility.minimum_age.raw_value}</span>
                </div>
              )}
              {data.eligibility.employment_types?.length > 0 && (
                <div className="flex justify-between">
                  <span className="text-gray-600">Employment</span>
                  <span className="font-medium">{data.eligibility.employment_types.join(', ')}</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
      
      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        {/* Search */}
        <div className="relative flex-1 min-w-[200px]">
          <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search intelligence..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>
        
        {/* Category filter */}
        <select
          value={selectedCategory}
          onChange={(e) => setSelectedCategory(e.target.value)}
          className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
        >
          <option value="all">All Categories ({data.total_items})</option>
          {categories.map(cat => (
            <option key={cat} value={cat}>
              {cat.charAt(0).toUpperCase() + cat.slice(1)} ({data.items_by_category[cat]})
            </option>
          ))}
        </select>
        
        {/* Headlines only toggle */}
        <button
          onClick={() => setShowHeadlinesOnly(!showHeadlinesOnly)}
          className={`px-4 py-2 rounded-lg font-medium transition-colors flex items-center gap-2 ${
            showHeadlinesOnly 
              ? 'bg-blue-600 text-white' 
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          }`}
        >
          <Star size={16} />
          Key Benefits Only
        </button>
      </div>
      
      {/* Results count */}
      <div className="text-sm text-gray-500 mb-4">
        Showing {filteredItems.length} of {data.total_items} items
      </div>
      
      {/* Intelligence items */}
      <div className="space-y-2">
        {filteredItems.map(item => (
          <IntelligenceItem
            key={item.item_id}
            item={item}
            isExpanded={expandedItems.has(item.item_id)}
            onToggle={() => toggleItem(item.item_id)}
          />
        ))}
        
        {filteredItems.length === 0 && (
          <div className="text-center py-8 text-gray-500">
            No intelligence items match your filters.
          </div>
        )}
      </div>
      
      {/* All entities */}
      {data.all_entities?.length > 0 && (
        <div className="mt-8 pt-6 border-t">
          <h3 className="font-semibold text-gray-900 mb-3">All Partners & Entities</h3>
          <div className="flex flex-wrap gap-2">
            {data.all_entities.map((entity, i) => (
              <span key={i} className="px-3 py-1 bg-indigo-50 text-indigo-700 rounded-full text-sm">
                {entity.name}
              </span>
            ))}
          </div>
        </div>
      )}
      
      {/* All tags */}
      {data.all_tags?.length > 0 && (
        <div className="mt-6">
          <h3 className="font-semibold text-gray-900 mb-3">All Tags</h3>
          <div className="flex flex-wrap gap-2">
            {data.all_tags.map((tag, i) => (
              <span 
                key={i} 
                className="px-2 py-1 bg-gray-100 text-gray-600 rounded text-sm cursor-pointer hover:bg-gray-200"
                onClick={() => setSearchQuery(tag)}
              >
                {tag}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default IntelligenceResultsDisplay;
