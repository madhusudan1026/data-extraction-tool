import React, { useState } from 'react';
import { 
  CreditCard, Gift, Building2, DollarSign, UserCheck, Shield,
  ChevronDown, ChevronUp, CheckCircle, AlertTriangle, Info,
  Percent, MapPin, Clock, Tag, ExternalLink, Store
} from 'lucide-react';

function ResultsDisplay({ result }) {
  const [expandedSections, setExpandedSections] = useState({
    benefits: true,
    entitlements: true,
    merchants: false,
    fees: false,
    eligibility: false,
    insurance: false,
  });

  const toggleSection = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  if (!result) return null;

  // Detect if this is V2 data
  const isV2 = result.isV2 || result.extraction_metadata || result.entitlements;

  // Score indicator component
  const ScoreIndicator = ({ score, label }) => {
    const percentage = Math.round((score || 0) * 100);
    const color = percentage >= 70 ? 'text-green-600' : percentage >= 40 ? 'text-yellow-600' : 'text-red-600';
    const bgColor = percentage >= 70 ? 'bg-green-100' : percentage >= 40 ? 'bg-yellow-100' : 'bg-red-100';
    
    return (
      <div className={`px-3 py-1 ${bgColor} rounded-full flex items-center gap-1`}>
        <span className={`text-sm font-medium ${color}`}>{percentage}%</span>
        <span className="text-xs text-gray-500">{label}</span>
      </div>
    );
  };

  // Section header component
  const SectionHeader = ({ icon: Icon, title, count, section, color = 'blue' }) => (
    <button
      onClick={() => toggleSection(section)}
      className="w-full flex items-center justify-between p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
    >
      <div className="flex items-center gap-3">
        <div className={`p-2 bg-${color}-100 rounded-lg`}>
          <Icon className={`text-${color}-600`} size={20} />
        </div>
        <span className="font-semibold text-gray-800">{title}</span>
        {count !== undefined && (
          <span className="px-2 py-0.5 bg-gray-200 rounded-full text-sm text-gray-600">
            {count}
          </span>
        )}
      </div>
      {expandedSections[section] ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
    </button>
  );

  // Benefit card component
  const BenefitCard = ({ benefit }) => (
    <div className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-2">
        <div>
          <h4 className="font-semibold text-gray-800">{benefit.benefit_name}</h4>
          <span className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full">
            {benefit.benefit_type}
          </span>
        </div>
        {benefit.benefit_value && (
          <span className="text-lg font-bold text-green-600">{benefit.benefit_value}</span>
        )}
      </div>
      
      <p className="text-sm text-gray-600 mb-3">{benefit.description}</p>
      
      {/* Conditions */}
      {benefit.conditions && benefit.conditions.length > 0 && (
        <div className="mb-2">
          <p className="text-xs font-medium text-gray-500 mb-1">Conditions:</p>
          <ul className="text-xs text-gray-600 space-y-1">
            {benefit.conditions.slice(0, 3).map((condition, i) => (
              <li key={i} className="flex items-start gap-1">
                <AlertTriangle size={12} className="text-yellow-500 mt-0.5 flex-shrink-0" />
                {condition}
              </li>
            ))}
            {benefit.conditions.length > 3 && (
              <li className="text-gray-400">+{benefit.conditions.length - 3} more</li>
            )}
          </ul>
        </div>
      )}

      {/* Caps */}
      {benefit.caps && benefit.caps.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-2">
          {benefit.caps.map((cap, i) => (
            <span key={i} className="text-xs px-2 py-1 bg-orange-50 text-orange-700 rounded">
              Cap: {cap.cap_value} {cap.currency}/{cap.period}
            </span>
          ))}
        </div>
      )}

      {/* Categories */}
      {benefit.eligible_categories && benefit.eligible_categories.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2">
          {benefit.eligible_categories.map((cat, i) => (
            <span key={i} className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded">
              {cat}
            </span>
          ))}
        </div>
      )}
    </div>
  );

  // Entitlement card component
  const EntitlementCard = ({ entitlement }) => (
    <div className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-2">
        <div>
          <h4 className="font-semibold text-gray-800">{entitlement.entitlement_name}</h4>
          <span className="text-xs px-2 py-0.5 bg-purple-100 text-purple-700 rounded-full">
            {entitlement.entitlement_type}
          </span>
        </div>
        {entitlement.quantity_per_period && (
          <span className="text-sm font-medium text-purple-600">
            {entitlement.quantity_per_period}
          </span>
        )}
      </div>
      
      <p className="text-sm text-gray-600 mb-3">{entitlement.description}</p>
      
      {/* Partner Networks */}
      {entitlement.partner_networks && entitlement.partner_networks.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {entitlement.partner_networks.map((network, i) => (
            <span key={i} className="text-xs px-2 py-1 bg-indigo-50 text-indigo-700 rounded flex items-center gap-1">
              <Building2 size={12} />
              {network}
            </span>
          ))}
        </div>
      )}

      {/* Geographic Coverage */}
      {entitlement.geographic_coverage && (
        <div className="flex items-center gap-1 text-xs text-gray-500">
          <MapPin size={12} />
          {entitlement.geographic_coverage}
        </div>
      )}

      {/* Fallback Fee */}
      {entitlement.fallback_fee && (
        <div className="mt-2 text-xs text-orange-600 flex items-center gap-1">
          <AlertTriangle size={12} />
          Fee if conditions not met: AED {entitlement.fallback_fee}
        </div>
      )}
    </div>
  );

  // Merchant card component
  const MerchantCard = ({ merchant }) => (
    <div className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-2">
        <div>
          <h4 className="font-semibold text-gray-800">{merchant.merchant_name}</h4>
          <span className="text-xs px-2 py-0.5 bg-green-100 text-green-700 rounded-full">
            {merchant.merchant_category}
          </span>
        </div>
        {merchant.is_online && (
          <span className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full">
            Online
          </span>
        )}
      </div>
      
      {/* Offers */}
      {merchant.offers && merchant.offers.length > 0 && (
        <div className="space-y-2">
          {merchant.offers.map((offer, i) => (
            <div key={i} className="bg-gray-50 rounded p-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-800">{offer.offer_value}</span>
                <span className="text-xs text-gray-500">{offer.offer_type}</span>
              </div>
              {offer.description && (
                <p className="text-xs text-gray-600 mt-1">{offer.description}</p>
              )}
              {offer.promo_code && (
                <span className="inline-block mt-1 text-xs px-2 py-0.5 bg-yellow-100 text-yellow-800 rounded font-mono">
                  {offer.promo_code}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );

  return (
    <div className="bg-white rounded-xl shadow-lg p-6 space-y-6">
      {/* Header with Card Info */}
      <div className="border-b border-gray-200 pb-4">
        <div className="flex items-start justify-between mb-3">
          <div>
            <h2 className="text-2xl font-bold text-gray-900">{result.card_name}</h2>
            <p className="text-gray-600">
              {/* Handle both V1 (string) and V2 (object) card_issuer */}
              {typeof result.card_issuer === 'object' 
                ? result.card_issuer?.bank_name 
                : result.card_issuer || 'Unknown Issuer'}
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            {result.confidence_score && (
              <ScoreIndicator score={result.confidence_score} label="Confidence" />
            )}
            {result.completeness_score && (
              <ScoreIndicator score={result.completeness_score} label="Completeness" />
            )}
          </div>
        </div>

        {/* Card badges */}
        <div className="flex flex-wrap gap-2">
          {result.card_network && (
            <span className="px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-sm font-medium">
              {result.card_network}
            </span>
          )}
          {result.card_category && (
            <span className="px-3 py-1 bg-purple-100 text-purple-700 rounded-full text-sm font-medium">
              {result.card_category}
            </span>
          )}
          {result.card_type && (
            <span className="px-3 py-1 bg-green-100 text-green-700 rounded-full text-sm font-medium">
              {result.card_type}
            </span>
          )}
          {result.is_combo_card && (
            <span className="px-3 py-1 bg-orange-100 text-orange-700 rounded-full text-sm font-medium">
              Combo Card
            </span>
          )}
        </div>

        {/* Extraction metadata */}
        {result.extraction_metadata && (
          <div className="mt-3 flex flex-wrap gap-4 text-xs text-gray-500">
            <span className="flex items-center gap-1">
              <Clock size={12} />
              {result.extraction_metadata.processing_time_ms}ms
            </span>
            <span className="flex items-center gap-1">
              <ExternalLink size={12} />
              {result.extraction_metadata.links_followed} links followed
            </span>
            <span className="flex items-center gap-1">
              <Tag size={12} />
              {result.extraction_metadata.tables_extracted} tables extracted
            </span>
          </div>
        )}
      </div>

      {/* Benefits Section */}
      {result.benefits && result.benefits.length > 0 && (
        <div>
          <SectionHeader 
            icon={Gift} 
            title="Benefits" 
            count={result.benefits.length}
            section="benefits"
            color="blue"
          />
          {expandedSections.benefits && (
            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
              {result.benefits.map((benefit, i) => (
                <BenefitCard key={benefit.benefit_id || i} benefit={benefit} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Entitlements Section (V2 only) */}
      {result.entitlements && result.entitlements.length > 0 && (
        <div>
          <SectionHeader 
            icon={Shield} 
            title="Entitlements" 
            count={result.entitlements.length}
            section="entitlements"
            color="purple"
          />
          {expandedSections.entitlements && (
            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
              {result.entitlements.map((entitlement, i) => (
                <EntitlementCard key={entitlement.entitlement_id || i} entitlement={entitlement} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Merchants Section */}
      {result.merchants_vendors && result.merchants_vendors.length > 0 && (
        <div>
          <SectionHeader 
            icon={Store} 
            title="Partner Merchants" 
            count={result.merchants_vendors.length}
            section="merchants"
            color="green"
          />
          {expandedSections.merchants && (
            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {result.merchants_vendors.map((merchant, i) => (
                <MerchantCard key={i} merchant={merchant} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Fees Section */}
      {result.fees && (
        <div>
          <SectionHeader 
            icon={DollarSign} 
            title="Fees & Charges" 
            section="fees"
            color="yellow"
          />
          {expandedSections.fees && (
            <div className="mt-4 grid grid-cols-2 md:grid-cols-3 gap-4">
              {/* Handle both V1 (string) and V2 (object) formats for annual_fee */}
              {(result.fees.annual_fee || result.fees.annual_fee === 0) && (
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500">Annual Fee</p>
                  <p className="text-xl font-bold text-gray-800">
                    {typeof result.fees.annual_fee === 'object' 
                      ? (result.fees.annual_fee?.fee_amount 
                          ? `${result.fees.annual_fee.currency || 'AED'} ${result.fees.annual_fee.fee_amount}`
                          : 'N/A')
                      : result.fees.annual_fee || 'N/A'}
                  </p>
                  {typeof result.fees.annual_fee === 'object' && 
                   result.fees.annual_fee?.waiver_conditions && 
                   result.fees.annual_fee.waiver_conditions.length > 0 && (
                    <p className="text-xs text-green-600 mt-1">
                      {result.fees.annual_fee.waiver_conditions[0]}
                    </p>
                  )}
                </div>
              )}
              {/* Handle both V1 (interest_rate) and V2 (interest_rate_annual) */}
              {(result.fees.interest_rate_annual || result.fees.interest_rate) && (
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500">Annual Interest Rate</p>
                  <p className="text-xl font-bold text-gray-800">
                    {result.fees.interest_rate_annual 
                      ? `${result.fees.interest_rate_annual}%`
                      : result.fees.interest_rate || 'N/A'}
                  </p>
                </div>
              )}
              {/* Handle both V1 (string) and V2 (object) formats for foreign_transaction_fee */}
              {result.fees.foreign_transaction_fee && (
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500">Foreign Transaction</p>
                  <p className="text-xl font-bold text-gray-800">
                    {typeof result.fees.foreign_transaction_fee === 'object'
                      ? (result.fees.foreign_transaction_fee?.fee_percentage 
                          ? `${result.fees.foreign_transaction_fee.fee_percentage}%`
                          : 'N/A')
                      : result.fees.foreign_transaction_fee || 'N/A'}
                  </p>
                </div>
              )}
              {/* V1 specific fields */}
              {result.fees.late_payment_fee && typeof result.fees.late_payment_fee === 'string' && (
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500">Late Payment Fee</p>
                  <p className="text-xl font-bold text-gray-800">
                    {result.fees.late_payment_fee}
                  </p>
                </div>
              )}
              {result.fees.cash_advance_fee && typeof result.fees.cash_advance_fee === 'string' && (
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500">Cash Advance Fee</p>
                  <p className="text-xl font-bold text-gray-800">
                    {result.fees.cash_advance_fee}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Eligibility Section */}
      {result.eligibility && (
        <div>
          <SectionHeader 
            icon={UserCheck} 
            title="Eligibility" 
            section="eligibility"
            color="indigo"
          />
          {expandedSections.eligibility && (
            <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4">
              {/* Handle both V1 (string) and V2 (number) minimum_salary */}
              {result.eligibility.minimum_salary && (
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500">Minimum Salary</p>
                  <p className="text-lg font-bold text-gray-800">
                    {typeof result.eligibility.minimum_salary === 'number'
                      ? `${result.eligibility.minimum_salary_currency || 'AED'} ${result.eligibility.minimum_salary?.toLocaleString()}`
                      : result.eligibility.minimum_salary}
                  </p>
                </div>
              )}
              {/* Handle both V1 (string) and V2 (number) minimum_age */}
              {result.eligibility.minimum_age && (
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500">Minimum Age</p>
                  <p className="text-lg font-bold text-gray-800">
                    {typeof result.eligibility.minimum_age === 'number'
                      ? `${result.eligibility.minimum_age} years`
                      : result.eligibility.minimum_age}
                  </p>
                </div>
              )}
              {/* V1 has minimum_spend */}
              {result.eligibility.minimum_spend && (
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500">Minimum Spend</p>
                  <p className="text-lg font-bold text-gray-800">
                    {result.eligibility.minimum_spend}
                  </p>
                </div>
              )}
              {/* Handle both V1 (employment_type) and V2 (employment_types) */}
              {((result.eligibility.employment_types && result.eligibility.employment_types.length > 0) ||
                (result.eligibility.employment_type && result.eligibility.employment_type.length > 0)) && (
                <div className="bg-gray-50 rounded-lg p-4 col-span-2">
                  <p className="text-sm text-gray-500">Employment Types</p>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {(result.eligibility.employment_types || result.eligibility.employment_type || []).map((type, i) => (
                      <span key={i} className="text-xs px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded">
                        {type}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {result.eligibility.nationality_requirements && result.eligibility.nationality_requirements.length > 0 && (
                <div className="bg-gray-50 rounded-lg p-4 col-span-2">
                  <p className="text-sm text-gray-500">Nationality Requirements</p>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {result.eligibility.nationality_requirements.map((req, i) => (
                      <span key={i} className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded">
                        {req}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {result.eligibility.required_documents && result.eligibility.required_documents.length > 0 && (
                <div className="bg-gray-50 rounded-lg p-4 col-span-2 md:col-span-4">
                  <p className="text-sm text-gray-500 mb-2">Required Documents</p>
                  <ul className="text-sm text-gray-700 space-y-1">
                    {result.eligibility.required_documents.map((doc, i) => (
                      <li key={i} className="flex items-center gap-2">
                        <CheckCircle size={14} className="text-green-500" />
                        {doc}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Insurance Section (V2 only) */}
      {result.insurance_coverage && result.insurance_coverage.length > 0 && (
        <div>
          <SectionHeader 
            icon={Shield} 
            title="Insurance Coverage" 
            count={result.insurance_coverage.length}
            section="insurance"
            color="red"
          />
          {expandedSections.insurance && (
            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
              {result.insurance_coverage.map((insurance, i) => (
                <div key={i} className="border border-gray-200 rounded-lg p-4">
                  <h4 className="font-semibold text-gray-800">{insurance.coverage_name}</h4>
                  {insurance.coverage_amount && (
                    <p className="text-lg font-bold text-green-600 mt-1">
                      {insurance.currency || 'AED'} {insurance.coverage_amount?.toLocaleString()}
                    </p>
                  )}
                  {insurance.description && (
                    <p className="text-sm text-gray-600 mt-2">{insurance.description}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Source URL */}
      {result.source_url && (
        <div className="pt-4 border-t border-gray-200">
          <a 
            href={result.source_url} 
            target="_blank" 
            rel="noopener noreferrer"
            className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1"
          >
            <ExternalLink size={14} />
            View source page
          </a>
        </div>
      )}
    </div>
  );
}

export default ResultsDisplay;
