"""
Enhanced Extraction Service - Main orchestrator for comprehensive credit card data extraction.
Coordinates enhanced web scraping, multi-stage LLM extraction, and validation.
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
import hashlib
import asyncio

from app.core.exceptions import ExtractionError, BadRequestError
from app.core.banks import detect_bank_from_url, get_bank_name
from app.utils.logger import logger
from app.services.enhanced_llm_service import enhanced_llm_service
from app.services.enhanced_web_scraper_service import (
    enhanced_web_scraper_service,
    ScrapedContent
)
from app.services.pdf_service import pdf_service
from app.services.validation_service import validation_service
from app.services.cache_service import cache_service
from app.models.extracted_data_v2 import (
    ExtractedDataV2,
    SourceType,
    ExtractionMethod,
    CardIssuerInfo,
    Benefit,
    Entitlement,
    Merchant,
    MerchantOffer,
    Fees,
    Fee,
    Eligibility,
    InsuranceCoverage,
    ExtractionMetadata,
    SourceDocument,
    BenefitType,
    EntitlementType,
    MerchantCategory,
    CardNetwork,
    CardCategory,
    CardType,
    Frequency,
    Currency,
    SpendCondition,
    CapLimit,
)


class EnhancedExtractionService:
    """Enhanced service for comprehensive credit card data extraction."""

    async def extract_comprehensive(
        self,
        source_type: str,
        source: Any,
        config: Optional[Dict[str, Any]] = None
    ) -> ExtractedDataV2:
        """
        Extract comprehensive credit card data from various sources.

        Args:
            source_type: Type of source ('url', 'pdf', 'text').
            source: Source content or reference.
            config: Optional extraction configuration.

        Returns:
            ExtractedDataV2 document with comprehensive data.

        Raises:
            ExtractionError: If extraction fails.
        """
        config = config or {}
        start_time = datetime.utcnow()
        extraction_notes = []

        logger.info(f"Starting comprehensive extraction from {source_type}: {source[:100] if isinstance(source, str) else 'non-string source'}")

        try:
            # Check cache if not bypassed
            if not config.get("bypass_cache", False):
                cached_result = await cache_service.get_extraction_result(
                    str(source), source_type
                )
                if cached_result:
                    logger.info("Returning cached extraction result")
                    return await ExtractedDataV2.get(cached_result["id"])

            # Detect bank from URL
            bank_key = self._detect_bank(source if source_type == "url" else "")
            extraction_notes.append(f"Detected bank: {bank_key or 'unknown'}")

            # Extract content based on source type
            if source_type == "url":
                # Check if user provided selected URLs
                selected_urls = config.get("selected_urls", [])
                
                if selected_urls:
                    # Use user-selected URLs instead of auto-discovery
                    logger.info(f"Using {len(selected_urls)} user-selected URLs")
                    scraped_content = await enhanced_web_scraper_service.scrape_url_comprehensive(
                        source,
                        follow_links=False,  # Don't auto-discover
                        max_depth=0
                    )
                    
                    # Fetch the selected URLs
                    bank_config = enhanced_web_scraper_service._get_bank_config(source)
                    linked_content = await enhanced_web_scraper_service._fetch_related_content(
                        selected_urls,
                        bank_config
                    )
                    # Manually add linked content to scraped_content
                    scraped_content.linked_content.update(linked_content)
                    
                    extraction_notes.append(f"Scraped {len(scraped_content.raw_text)} chars from main page")
                    extraction_notes.append(f"Processing {len(selected_urls)} user-selected URLs")
                    for url in selected_urls[:5]:
                        extraction_notes.append(f"  -> {url[:80]}...")
                else:
                    # Auto-discover and follow links
                    scraped_content = await enhanced_web_scraper_service.scrape_url_comprehensive(
                        source,
                        follow_links=config.get("follow_links", True),
                        max_depth=config.get("max_depth", 1)
                    )
                    
                    extraction_notes.append(f"Scraped {len(scraped_content.raw_text)} chars from main page")
                    extraction_notes.append(f"Followed {len(scraped_content.linked_content)} related links")
                
                extraction_notes.append(f"Found {len(scraped_content.tables)} tables")
                extraction_notes.append(f"Found {len(scraped_content.pdf_links)} PDF links")
                
                # Log what links were followed
                if scraped_content.linked_content:
                    for url in list(scraped_content.linked_content.keys())[:5]:
                        extraction_notes.append(f"  -> Fetched: {url[:80]}...")
                
                # Process PDFs if enabled
                pdf_content = ""
                pdfs_to_process = []
                
                # Include PDFs from selected URLs
                for url in selected_urls:
                    if '.pdf' in url.lower():
                        pdfs_to_process.append(url)
                
                # Also include discovered PDFs if enabled
                if config.get("process_pdfs", True) and scraped_content.pdf_links:
                    for pdf_url in scraped_content.pdf_links[:3]:
                        if pdf_url not in pdfs_to_process:
                            pdfs_to_process.append(pdf_url)
                
                for pdf_url in pdfs_to_process[:5]:  # Limit to 5 PDFs
                    try:
                        logger.info(f"Processing PDF: {pdf_url}")
                        pdf_text = await pdf_service.extract_text_from_url(pdf_url)
                        if pdf_text and len(pdf_text) > 100:
                            pdf_content += f"\n\n=== PDF: {pdf_url.split('/')[-1]} ===\n{pdf_text[:5000]}"
                            extraction_notes.append(f"Extracted {len(pdf_text)} chars from PDF: {pdf_url.split('/')[-1]}")
                    except Exception as pdf_error:
                        logger.warning(f"Failed to process PDF {pdf_url}: {str(pdf_error)}")
                        extraction_notes.append(f"Failed to process PDF: {pdf_url.split('/')[-1]}")
                
                # Format content for LLM (includes linked content)
                formatted_content = enhanced_web_scraper_service.format_for_llm(scraped_content)
                
                # Append PDF content
                if pdf_content:
                    formatted_content += f"\n\n=== EXTRACTED FROM PDF DOCUMENTS ==={pdf_content}"
                
            elif source_type == "pdf":
                formatted_content = await pdf_service.extract_text_from_pdf(source)
                scraped_content = None
                extraction_notes.append(f"Extracted {len(formatted_content)} chars from PDF")
                
            elif source_type == "text":
                if not isinstance(source, str):
                    raise BadRequestError("Text source must be a string")
                formatted_content = source
                scraped_content = None
                extraction_notes.append("Using provided text content")
            else:
                raise BadRequestError(f"Invalid source type: {source_type}")

            # Extract structured data using enhanced LLM service
            extraction_method = ExtractionMethod.ENHANCED_LLM
            try:
                structured_data = await enhanced_llm_service.extract_credit_card_data(
                    formatted_content,
                    config,
                    bank_name=bank_key
                )
                extraction_notes.append("LLM extraction completed successfully")
                
                # Enhance LLM results with regex fallback for better coverage
                fallback_data = self._fallback_extraction(formatted_content, bank_key)
                structured_data = self._merge_extraction_results(structured_data, fallback_data)
                extraction_notes.append("Enhanced with regex fallback data")
                
            except Exception as llm_error:
                logger.warning(f"Enhanced LLM extraction failed: {str(llm_error)}")
                extraction_notes.append(f"LLM extraction failed: {str(llm_error)}")
                
                if config.get("enable_fallback", True):
                    structured_data = self._fallback_extraction(formatted_content, bank_key)
                    extraction_method = ExtractionMethod.FALLBACK
                    extraction_notes.append("Using fallback extraction")
                else:
                    raise ExtractionError(f"LLM extraction failed: {str(llm_error)}")

            # Calculate processing time
            processing_time_ms = int(
                (datetime.utcnow() - start_time).total_seconds() * 1000
            )

            # Build the comprehensive document
            extracted_data = self._build_extracted_data_document(
                structured_data=structured_data,
                source_type=source_type,
                source=source,
                scraped_content=scraped_content,
                extraction_method=extraction_method,
                bank_key=bank_key,
                formatted_content=formatted_content,
                processing_time_ms=processing_time_ms,
                extraction_notes=extraction_notes,
                config=config
            )

            # Calculate confidence and completeness scores
            confidence_score = self._calculate_confidence_score(extracted_data)
            extracted_data.confidence_score = confidence_score
            extracted_data.calculate_completeness_score()

            # Determine validation status
            if confidence_score >= 0.8 and extracted_data.completeness_score >= 0.7:
                extracted_data.validation_status = "validated"
            elif confidence_score >= 0.5:
                extracted_data.validation_status = "requires_review"
            else:
                extracted_data.validation_status = "pending"

            # Save to database
            await extracted_data.insert()

            logger.info(
                f"Extraction completed: id={extracted_data.id}, "
                f"confidence={confidence_score:.2f}, "
                f"completeness={extracted_data.completeness_score:.2f}, "
                f"benefits={len(extracted_data.benefits)}, "
                f"entitlements={len(extracted_data.entitlements)}, "
                f"merchants={len(extracted_data.merchants_vendors)}"
            )

            # Cache the result
            await cache_service.cache_extraction_result(
                str(source),
                source_type,
                {"id": str(extracted_data.id)},
            )

            return extracted_data

        except Exception as e:
            logger.error(f"Comprehensive extraction failed: {str(e)}")
            raise ExtractionError(f"Extraction failed: {str(e)}")

    def _detect_bank(self, url: str) -> Optional[str]:
        """Detect bank from URL (delegates to core/banks)."""
        return detect_bank_from_url(url)

    def _get_bank_name(self, bank_key: Optional[str]) -> str:
        """Get full bank name from key (delegates to core/banks)."""
        return get_bank_name(bank_key) if bank_key else "Unknown Bank"

    def _build_extracted_data_document(
        self,
        structured_data: Dict[str, Any],
        source_type: str,
        source: Any,
        scraped_content: Optional[ScrapedContent],
        extraction_method: ExtractionMethod,
        bank_key: Optional[str],
        formatted_content: str,
        processing_time_ms: int,
        extraction_notes: List[str],
        config: Dict[str, Any]
    ) -> ExtractedDataV2:
        """Build the ExtractedDataV2 document from extracted data."""
        
        # Build card issuer info
        issuer_data = structured_data.get("card_issuer", {})
        if isinstance(issuer_data, dict):
            card_issuer = CardIssuerInfo(
                bank_name=issuer_data.get("bank_name") or self._get_bank_name(bank_key),
                bank_code=bank_key,
                country=issuer_data.get("country", "UAE"),
                website=issuer_data.get("website"),
                customer_service_phone=issuer_data.get("customer_service_phone"),
            )
        else:
            card_issuer = CardIssuerInfo(
                bank_name=self._get_bank_name(bank_key),
                bank_code=bank_key,
                country="UAE"
            )

        # Build benefits list
        benefits = []
        for b_data in structured_data.get("benefits", []):
            try:
                benefit = self._build_benefit(b_data)
                benefits.append(benefit)
            except Exception as e:
                logger.warning(f"Failed to build benefit: {str(e)}")

        # Build entitlements list
        entitlements = []
        for e_data in structured_data.get("entitlements", []):
            try:
                entitlement = self._build_entitlement(e_data)
                entitlements.append(entitlement)
            except Exception as e:
                logger.warning(f"Failed to build entitlement: {str(e)}")

        # Build merchants list
        merchants = []
        for m_data in structured_data.get("merchants_vendors", []):
            try:
                merchant = self._build_merchant(m_data)
                merchants.append(merchant)
            except Exception as e:
                logger.warning(f"Failed to build merchant: {str(e)}")

        # Build fees
        fees = self._build_fees(structured_data.get("fees", {}))

        # Build eligibility
        eligibility = self._build_eligibility(structured_data.get("eligibility", {}))

        # Build insurance coverage
        insurance_coverage = []
        for i_data in structured_data.get("insurance_coverage", []):
            try:
                coverage = InsuranceCoverage(
                    coverage_name=i_data.get("coverage_name", "Unknown Coverage"),
                    coverage_type=i_data.get("coverage_type", "other"),
                    coverage_amount=i_data.get("coverage_amount"),
                    currency=Currency(i_data.get("currency", "AED")) if i_data.get("currency") else Currency.AED,
                    description=i_data.get("description"),
                    conditions=i_data.get("conditions", []),
                    exclusions=i_data.get("exclusions", []),
                )
                insurance_coverage.append(coverage)
            except Exception as e:
                logger.warning(f"Failed to build insurance coverage: {str(e)}")

        # Build extraction metadata
        extraction_metadata = ExtractionMetadata(
            extraction_timestamp=datetime.utcnow(),
            content_length=len(formatted_content),
            processing_time_ms=processing_time_ms,
            llm_model_used=config.get("model"),
            llm_temperature=config.get("temperature"),
            source_hash=hashlib.md5(formatted_content.encode()).hexdigest()[:16],
            pages_scraped=1 + (len(scraped_content.linked_content) if scraped_content else 0),
            links_followed=len(scraped_content.linked_content) if scraped_content else 0,
            pdfs_processed=0,  # TODO: Implement PDF processing
            tables_extracted=len(scraped_content.tables) if scraped_content else 0,
            extraction_notes=extraction_notes,
        )

        # Parse card network(s)
        card_network = None
        card_networks = []
        network_str = structured_data.get("card_network", "")
        networks_list = structured_data.get("card_networks", [])
        
        if networks_list:
            for n in networks_list:
                try:
                    card_networks.append(CardNetwork(n))
                except:
                    pass
            if card_networks:
                card_network = card_networks[0]
        elif network_str:
            try:
                card_network = CardNetwork(network_str)
                card_networks = [card_network]
            except:
                pass

        # Parse card category
        card_category = None
        cat_str = structured_data.get("card_category", "")
        if cat_str:
            try:
                card_category = CardCategory(cat_str)
            except:
                pass

        # Parse card type
        card_type = None
        type_str = structured_data.get("card_type", "")
        if type_str:
            try:
                card_type = CardType(type_str)
            except:
                pass

        # Build source URLs list and source documents
        source_urls = [source] if source_type == "url" else []
        source_documents = []
        
        if scraped_content:
            # Add main page as source document
            source_documents.append(SourceDocument(
                document_id=f"main_{hashlib.md5(source.encode()).hexdigest()[:8]}",
                document_type="webpage",
                url=source,
                title=scraped_content.title,
                content_length=len(scraped_content.raw_text),
                content_preview=scraped_content.raw_text[:500] if scraped_content.raw_text else None,
                fetch_status="success",
                fetched_at=datetime.utcnow()
            ))
            
            # Add linked content as source documents
            if scraped_content.linked_content:
                for link_url, link_content in scraped_content.linked_content.items():
                    source_urls.append(link_url)
                    
                    # Determine document type
                    doc_type = "webpage"
                    url_lower = link_url.lower()
                    if '.pdf' in url_lower:
                        doc_type = "pdf"
                    elif 'key-fact' in url_lower or 'keyfact' in url_lower:
                        doc_type = "key_facts"
                    elif 'terms' in url_lower or 'condition' in url_lower:
                        doc_type = "terms_conditions"
                    elif 'fee' in url_lower or 'tariff' in url_lower:
                        doc_type = "fee_schedule"
                    
                    source_documents.append(SourceDocument(
                        document_id=f"linked_{hashlib.md5(link_url.encode()).hexdigest()[:8]}",
                        document_type=doc_type,
                        url=link_url,
                        title=link_url.split('/')[-1].replace('-', ' ').title(),
                        content_length=len(link_content),
                        content_preview=link_content[:500] if link_content else None,
                        fetch_status="success",
                        fetched_at=datetime.utcnow()
                    ))
            
            # Add PDF links as source documents (even if not yet processed)
            for pdf_url in scraped_content.pdf_links:
                if pdf_url not in source_urls:
                    source_urls.append(pdf_url)
                    source_documents.append(SourceDocument(
                        document_id=f"pdf_{hashlib.md5(pdf_url.encode()).hexdigest()[:8]}",
                        document_type="pdf",
                        url=pdf_url,
                        title=pdf_url.split('/')[-1],
                        content_length=0,
                        fetch_status="pending",  # PDF not processed yet
                        fetched_at=datetime.utcnow()
                    ))

        # Create the document
        return ExtractedDataV2(
            source_url=source if source_type == "url" else None,
            source_urls=source_urls,
            source_documents=source_documents,
            source_type=SourceType(source_type),
            card_name=structured_data.get("card_name") or (scraped_content.title if scraped_content else "Unknown Card"),
            card_issuer=card_issuer,
            card_network=card_network,
            card_networks=card_networks,
            card_category=card_category,
            card_type=card_type,
            is_combo_card=structured_data.get("is_combo_card", False),
            combo_cards=structured_data.get("combo_cards", []),
            benefits=benefits,
            entitlements=entitlements,
            merchants_vendors=merchants,
            partner_programs=structured_data.get("partner_programs", []),
            fees=fees,
            eligibility=eligibility,
            insurance_coverage=insurance_coverage,
            rewards_program_name=structured_data.get("rewards_program_name"),
            rewards_earn_rate=structured_data.get("rewards_earn_rate"),
            credit_limit_min=structured_data.get("credit_limit_min"),
            credit_limit_max=structured_data.get("credit_limit_max"),
            application_url=structured_data.get("application_url"),
            extraction_method=extraction_method,
            extraction_metadata=extraction_metadata,
            raw_extracted_text=formatted_content[:50000] if config.get("store_raw_text", True) else None,
            raw_llm_response=structured_data if config.get("store_raw_response", False) else None,
            regions=["UAE"],  # Default for UAE banks
        )

    def _build_benefit(self, data: Dict[str, Any]) -> Benefit:
        """Build a Benefit object from extracted data."""
        # Build spend conditions
        spend_conditions = []
        for sc_data in data.get("spend_conditions", []):
            if isinstance(sc_data, dict):
                spend_conditions.append(SpendCondition(
                    minimum_spend=sc_data.get("minimum_spend"),
                    currency=Currency(sc_data.get("currency", "AED")),
                    period=self._parse_frequency(sc_data.get("period", "monthly")),
                    spend_categories=sc_data.get("spend_categories", []),
                    excluded_categories=sc_data.get("excluded_categories", []),
                    description=sc_data.get("description"),
                ))

        # Build caps
        caps = []
        for cap_data in data.get("caps", []):
            if isinstance(cap_data, dict):
                caps.append(CapLimit(
                    cap_type=cap_data.get("cap_type", "amount"),
                    cap_value=float(cap_data.get("cap_value", 0)),
                    currency=Currency(cap_data.get("currency", "AED")) if cap_data.get("currency") else None,
                    period=self._parse_frequency(cap_data.get("period", "monthly")),
                    description=cap_data.get("description"),
                ))

        return Benefit(
            benefit_id=data.get("benefit_id", "benefit_unknown"),
            benefit_name=data.get("benefit_name", "Unknown Benefit"),
            benefit_type=self._parse_benefit_type(data.get("benefit_type", "other")),
            benefit_value=data.get("benefit_value"),
            benefit_value_numeric=data.get("benefit_value_numeric"),
            value_type=data.get("value_type"),
            description=data.get("description", ""),
            short_description=data.get("short_description"),
            conditions=data.get("conditions", []),
            spend_conditions=spend_conditions,
            eligible_categories=data.get("eligible_categories", []),
            excluded_categories=data.get("excluded_categories", []),
            eligible_merchants=data.get("eligible_merchants", []),
            caps=caps,
            frequency=self._parse_frequency(data.get("frequency")),
            max_usage=data.get("max_usage"),
            auto_applied=data.get("auto_applied", False),
            is_promotional=data.get("is_promotional", False),
            terms_url=data.get("terms_url"),
            additional_details=data.get("additional_details"),
        )

    def _build_entitlement(self, data: Dict[str, Any]) -> Entitlement:
        """Build an Entitlement object from extracted data."""
        # Build spend conditions
        spend_conditions = []
        for sc_data in data.get("spend_conditions", []):
            if isinstance(sc_data, dict):
                spend_conditions.append(SpendCondition(
                    minimum_spend=sc_data.get("minimum_spend"),
                    currency=Currency(sc_data.get("currency", "AED")),
                    period=self._parse_frequency(sc_data.get("period", "monthly")),
                    description=sc_data.get("description"),
                ))

        # Build caps
        caps = []
        for cap_data in data.get("caps", []):
            if isinstance(cap_data, dict):
                caps.append(CapLimit(
                    cap_type=cap_data.get("cap_type", "count"),
                    cap_value=float(cap_data.get("cap_value", 0)),
                    period=self._parse_frequency(cap_data.get("period", "yearly")),
                ))

        return Entitlement(
            entitlement_id=data.get("entitlement_id", "entitlement_unknown"),
            entitlement_name=data.get("entitlement_name", "Unknown Entitlement"),
            entitlement_type=self._parse_entitlement_type(data.get("entitlement_type", "other")),
            description=data.get("description", ""),
            short_description=data.get("short_description"),
            quantity=data.get("quantity"),
            quantity_per_period=data.get("quantity_per_period"),
            monetary_value=data.get("monetary_value"),
            currency=Currency(data.get("currency", "AED")) if data.get("currency") else None,
            conditions=data.get("conditions", []),
            spend_conditions=spend_conditions,
            frequency=self._parse_frequency(data.get("frequency")),
            caps=caps,
            redemption_locations=data.get("redemption_locations", []),
            partner_networks=data.get("partner_networks", []),
            geographic_coverage=data.get("geographic_coverage"),
            supplementary_access=data.get("supplementary_access", False),
            supplementary_conditions=data.get("supplementary_conditions"),
            fallback_fee=data.get("fallback_fee"),
            fallback_fee_currency=Currency(data.get("fallback_fee_currency", "AED")) if data.get("fallback_fee") else None,
            terms_url=data.get("terms_url"),
            additional_details=data.get("additional_details"),
        )

    def _build_merchant(self, data: Dict[str, Any]) -> Merchant:
        """Build a Merchant object from extracted data."""
        # Build offers
        offers = []
        for o_data in data.get("offers", []):
            if isinstance(o_data, dict):
                # Build offer caps
                offer_caps = []
                for cap_data in o_data.get("caps", []):
                    if isinstance(cap_data, dict):
                        offer_caps.append(CapLimit(
                            cap_type=cap_data.get("cap_type", "amount"),
                            cap_value=float(cap_data.get("cap_value", 0)),
                            currency=Currency(cap_data.get("currency", "AED")) if cap_data.get("currency") else None,
                            period=self._parse_frequency(cap_data.get("period", "monthly")),
                        ))

                offers.append(MerchantOffer(
                    offer_id=o_data.get("offer_id"),
                    offer_type=o_data.get("offer_type", "discount"),
                    offer_value=o_data.get("offer_value", ""),
                    offer_value_numeric=o_data.get("offer_value_numeric"),
                    description=o_data.get("description"),
                    conditions=o_data.get("conditions", []),
                    minimum_spend=o_data.get("minimum_spend"),
                    caps=offer_caps,
                    promo_code=o_data.get("promo_code"),
                ))

        return Merchant(
            merchant_id=data.get("merchant_id"),
            merchant_name=data.get("merchant_name", "Unknown Merchant"),
            merchant_category=self._parse_merchant_category(data.get("merchant_category", "other")),
            merchant_subcategory=data.get("merchant_subcategory"),
            brand_name=data.get("brand_name"),
            parent_company=data.get("parent_company"),
            offers=offers,
            general_benefit=data.get("general_benefit"),
            redemption_method=data.get("redemption_method"),
            redemption_instructions=data.get("redemption_instructions"),
            booking_required=data.get("booking_required", False),
            booking_url=data.get("booking_url"),
            locations=data.get("locations", []),
            geographic_coverage=data.get("geographic_coverage"),
            is_online=data.get("is_online", False),
            website_url=data.get("website_url"),
            app_name=data.get("app_name"),
            additional_details=data.get("additional_details"),
        )

    def _build_fees(self, data: Dict[str, Any]) -> Fees:
        """Build Fees object from extracted data."""
        def build_fee(fee_data: Dict[str, Any], default_name: str) -> Optional[Fee]:
            if not fee_data:
                return None
            return Fee(
                fee_name=fee_data.get("fee_name", default_name),
                fee_amount=fee_data.get("fee_amount"),
                fee_percentage=fee_data.get("fee_percentage"),
                currency=Currency(fee_data.get("currency", "AED")),
                frequency=self._parse_frequency(fee_data.get("frequency", "yearly")),
                description=fee_data.get("description"),
                waiver_conditions=fee_data.get("waiver_conditions", []),
                is_waivable=fee_data.get("is_waivable", False),
            )

        return Fees(
            annual_fee=build_fee(data.get("annual_fee"), "Annual Fee") if isinstance(data.get("annual_fee"), dict) else None,
            joining_fee=build_fee(data.get("joining_fee"), "Joining Fee") if isinstance(data.get("joining_fee"), dict) else None,
            interest_rate_monthly=data.get("interest_rate_monthly"),
            interest_rate_annual=data.get("interest_rate_annual"),
            foreign_transaction_fee=build_fee(data.get("foreign_transaction_fee"), "Foreign Transaction Fee") if isinstance(data.get("foreign_transaction_fee"), dict) else None,
            cash_advance_fee=build_fee(data.get("cash_advance_fee"), "Cash Advance Fee") if isinstance(data.get("cash_advance_fee"), dict) else None,
            balance_transfer_fee=build_fee(data.get("balance_transfer_fee"), "Balance Transfer Fee") if isinstance(data.get("balance_transfer_fee"), dict) else None,
            late_payment_fee=build_fee(data.get("late_payment_fee"), "Late Payment Fee") if isinstance(data.get("late_payment_fee"), dict) else None,
            over_limit_fee=build_fee(data.get("over_limit_fee"), "Over Limit Fee") if isinstance(data.get("over_limit_fee"), dict) else None,
            supplementary_card_fee=build_fee(data.get("supplementary_card_fee"), "Supplementary Card Fee") if isinstance(data.get("supplementary_card_fee"), dict) else None,
            fee_schedule_url=data.get("fee_schedule_url"),
        )

    def _build_eligibility(self, data: Dict[str, Any]) -> Eligibility:
        """Build Eligibility object from extracted data."""
        return Eligibility(
            minimum_salary=data.get("minimum_salary"),
            minimum_salary_currency=Currency(data.get("minimum_salary_currency", "AED")),
            minimum_salary_transfer=data.get("minimum_salary_transfer"),
            minimum_bank_balance=data.get("minimum_bank_balance"),
            bank_balance_period=data.get("bank_balance_period"),
            minimum_age=data.get("minimum_age"),
            maximum_age=data.get("maximum_age"),
            employment_types=data.get("employment_types", []),
            employment_tenure=data.get("employment_tenure"),
            nationality_requirements=data.get("nationality_requirements", []),
            residency_requirements=data.get("residency_requirements", []),
            uae_national_benefits=data.get("uae_national_benefits"),
            credit_score_requirement=data.get("credit_score_requirement"),
            existing_relationship=data.get("existing_relationship"),
            required_documents=data.get("required_documents", []),
        )

    def _parse_benefit_type(self, value: str) -> BenefitType:
        """Parse benefit type string to enum."""
        try:
            return BenefitType(value.lower())
        except:
            return BenefitType.OTHER

    def _parse_entitlement_type(self, value: str) -> EntitlementType:
        """Parse entitlement type string to enum."""
        try:
            return EntitlementType(value.lower())
        except:
            return EntitlementType.OTHER

    def _parse_merchant_category(self, value: str) -> MerchantCategory:
        """Parse merchant category string to enum."""
        try:
            return MerchantCategory(value.lower())
        except:
            return MerchantCategory.OTHER

    def _parse_frequency(self, value: Optional[str]) -> Optional[Frequency]:
        """Parse frequency string to enum."""
        if not value:
            return None
        try:
            return Frequency(value.lower())
        except:
            return Frequency.OTHER

    def _calculate_confidence_score(self, data: ExtractedDataV2) -> float:
        """Calculate confidence score based on extraction quality."""
        score = 0.0
        max_score = 10.0
        
        # Card name quality (1 point)
        if data.card_name and len(data.card_name) > 5:
            score += 1.0
        
        # Issuer info (1 point)
        if data.card_issuer and data.card_issuer.bank_name != "Unknown Bank":
            score += 1.0
        
        # Benefits quality (3 points)
        if data.benefits:
            benefit_score = 0
            for b in data.benefits:
                if b.description and len(b.description) > 20:
                    benefit_score += 0.3
                if b.conditions:
                    benefit_score += 0.2
                if b.benefit_value:
                    benefit_score += 0.2
            score += min(3.0, benefit_score)
        
        # Entitlements (1.5 points)
        if data.entitlements:
            score += min(1.5, len(data.entitlements) * 0.3)
        
        # Merchants (1.5 points)
        if data.merchants_vendors:
            score += min(1.5, len(data.merchants_vendors) * 0.15)
        
        # Fees (1 point)
        if data.fees.annual_fee or data.fees.interest_rate_annual:
            score += 1.0
        
        # Eligibility (1 point)
        if data.eligibility.minimum_salary or data.eligibility.minimum_age:
            score += 1.0
        
        return min(1.0, score / max_score)

    def _merge_extraction_results(self, llm_data: Dict[str, Any], fallback_data: Dict[str, Any]) -> Dict[str, Any]:
        """Merge LLM extraction results with regex fallback for better coverage."""
        merged = llm_data.copy()
        
        # Use LLM card name if valid, otherwise fallback
        if not merged.get("card_name") or merged.get("card_name") == "Unknown Card":
            merged["card_name"] = fallback_data.get("card_name", "Unknown Card")
        
        # Merge card issuer
        if not merged.get("card_issuer"):
            merged["card_issuer"] = fallback_data.get("card_issuer", {})
        elif isinstance(merged.get("card_issuer"), str):
            # LLM sometimes returns string instead of dict
            merged["card_issuer"] = {
                "bank_name": merged["card_issuer"],
                "country": "UAE"
            }
        
        # Use fallback network if LLM didn't extract
        if not merged.get("card_network"):
            merged["card_network"] = fallback_data.get("card_network", "Other")
        
        # Merge benefits - combine unique benefits from both
        llm_benefits = merged.get("benefits", [])
        fallback_benefits = fallback_data.get("benefits", [])
        
        # Normalize LLM benefits (handle different field names)
        normalized_llm_benefits = []
        for b in llm_benefits:
            # Get benefit_value and ensure it's a string
            benefit_value = b.get("benefit_value") or b.get("value", "")
            if isinstance(benefit_value, (int, float)):
                benefit_value = f"{benefit_value}%"
            
            normalized = {
                "benefit_id": b.get("benefit_id", f"benefit_{len(normalized_llm_benefits)+1}"),
                "benefit_name": b.get("benefit_name") or b.get("name", "Unknown"),
                "benefit_type": b.get("benefit_type") or b.get("type", "other"),
                "benefit_value": str(benefit_value) if benefit_value else "",
                "description": b.get("description", ""),
                "conditions": b.get("conditions", []),
                "eligible_categories": b.get("eligible_categories", []),
                "caps": b.get("caps", []),
                "frequency": b.get("frequency", ""),
            }
            normalized_llm_benefits.append(normalized)
        
        # Add fallback benefits that aren't duplicates
        llm_benefit_names = {b["benefit_name"].lower() for b in normalized_llm_benefits}
        for fb in fallback_benefits:
            if fb.get("benefit_name", "").lower() not in llm_benefit_names:
                fb["benefit_id"] = f"benefit_{len(normalized_llm_benefits) + len(fallback_benefits) + 1}"
                normalized_llm_benefits.append(fb)
        
        merged["benefits"] = normalized_llm_benefits
        
        # Merge entitlements - prefer fallback if LLM didn't find any
        llm_entitlements = merged.get("entitlements", [])
        fallback_entitlements = fallback_data.get("entitlements", [])
        
        if not llm_entitlements:
            merged["entitlements"] = fallback_entitlements
        else:
            # Normalize and combine
            llm_ent_names = {e.get("entitlement_name", "").lower() for e in llm_entitlements}
            for fe in fallback_entitlements:
                if fe.get("entitlement_name", "").lower() not in llm_ent_names:
                    llm_entitlements.append(fe)
            merged["entitlements"] = llm_entitlements
        
        # Merge merchants - prefer fallback if LLM didn't find any
        llm_merchants = merged.get("merchants_vendors", [])
        fallback_merchants = fallback_data.get("merchants_vendors", [])
        
        if not llm_merchants:
            merged["merchants_vendors"] = fallback_merchants
        else:
            llm_merchant_names = {m.get("merchant_name", "").lower() for m in llm_merchants}
            for fm in fallback_merchants:
                if fm.get("merchant_name", "").lower() not in llm_merchant_names:
                    llm_merchants.append(fm)
            merged["merchants_vendors"] = llm_merchants
        
        # Merge fees - combine both
        llm_fees = merged.get("fees", {})
        fallback_fees = fallback_data.get("fees", {})
        
        if isinstance(llm_fees, dict) and isinstance(fallback_fees, dict):
            for key, value in fallback_fees.items():
                if key not in llm_fees or not llm_fees[key]:
                    llm_fees[key] = value
            merged["fees"] = llm_fees
        elif fallback_fees:
            merged["fees"] = fallback_fees
        
        # Merge eligibility - combine both
        llm_elig = merged.get("eligibility", {})
        fallback_elig = fallback_data.get("eligibility", {})
        
        if isinstance(llm_elig, dict) and isinstance(fallback_elig, dict):
            for key, value in fallback_elig.items():
                if key not in llm_elig or not llm_elig[key]:
                    llm_elig[key] = value
            merged["eligibility"] = llm_elig
        elif fallback_elig:
            merged["eligibility"] = fallback_elig
        
        logger.info(f"Merged results: {len(merged.get('benefits', []))} benefits, "
                   f"{len(merged.get('entitlements', []))} entitlements, "
                   f"{len(merged.get('merchants_vendors', []))} merchants")
        
        return merged

    def _fallback_extraction(self, text: str, bank_key: Optional[str]) -> Dict[str, Any]:
        """Fallback extraction using regex and heuristics (ported from JS backend)."""
        logger.info("Using fallback extraction method")
        
        return {
            "card_name": self._extract_card_name_fallback(text),
            "card_issuer": {
                "bank_name": self._extract_card_issuer(text) or self._get_bank_name(bank_key),
                "country": "UAE"
            },
            "card_network": self._extract_card_network(text),
            "benefits": self._extract_benefits_fallback(text),
            "entitlements": self._extract_entitlements_fallback(text),
            "merchants_vendors": self._extract_merchants_fallback(text),
            "fees": self._extract_fees_fallback(text),
            "eligibility": self._extract_eligibility_fallback(text),
        }

    def _extract_card_name_fallback(self, text: str) -> str:
        """Extract card name using regex patterns."""
        import re
        
        patterns = [
            r'(?:FAB|First Abu Dhabi Bank)\s+([\w\s]+)\s+(?:Credit Card|Card)',
            r'^([\w\s]+)\s+Credit Card',
            r'([\w\s]+)\s+Card\s+Benefits',
            r'([\w\s]+(?:Cashback|Rewards|Travel|Infinite|Signature|Platinum|Gold))\s+(?:Credit\s+)?Card',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                name = match.group(1).strip()
                if len(name) > 3 and len(name) < 100:
                    return name
        
        # Fallback: look for any line with "card" in first 20 lines
        lines = text.split("\n")
        for line in lines[:20]:
            line = line.strip()
            if len(line) > 5 and len(line) < 100:
                if any(kw in line.lower() for kw in ["card", "credit", "cashback", "rewards"]):
                    return line
        
        return "Unknown Card"

    def _extract_card_issuer(self, text: str) -> Optional[str]:
        """Extract card issuer from text."""
        import re
        
        issuers = [
            ('First Abu Dhabi Bank', r'First\s+Abu\s+Dhabi\s+Bank|FAB'),
            ('Emirates NBD', r'Emirates\s+NBD|ENBD'),
            ('ADCB', r'ADCB|Abu\s+Dhabi\s+Commercial\s+Bank'),
            ('Mashreq', r'Mashreq'),
            ('RAKBANK', r'RAKBANK|RAK\s+Bank'),
            ('Dubai Islamic Bank', r'Dubai\s+Islamic\s+Bank|DIB'),
            ('CBD', r'Commercial\s+Bank\s+of\s+Dubai|CBD'),
            ('Standard Chartered', r'Standard\s+Chartered'),
        ]
        
        for issuer_name, pattern in issuers:
            if re.search(pattern, text, re.IGNORECASE):
                return issuer_name
        
        return None

    def _extract_card_network(self, text: str) -> str:
        """Extract card network from text."""
        import re
        
        networks = {
            'Mastercard': r'mastercard',
            'Visa': r'visa',
            'American Express': r'american\s+express|amex',
            'Discover': r'discover',
            'Diners Club': r'diners\s+club',
        }
        
        for network, pattern in networks.items():
            if re.search(pattern, text, re.IGNORECASE):
                return network
        
        return 'Other'

    def _extract_benefits_fallback(self, text: str) -> List[Dict[str, Any]]:
        """Extract benefits using regex patterns."""
        import re
        
        benefits = []
        benefit_id = 1
        seen_benefits = set()  # Track unique benefits
        
        def add_benefit(name, benefit_type, value, description, categories=None):
            nonlocal benefit_id
            # Avoid duplicates
            key = name.lower()[:30]
            if key in seen_benefits:
                return
            seen_benefits.add(key)
            
            benefits.append({
                "benefit_id": f"benefit_{benefit_id}",
                "benefit_name": name,
                "benefit_type": benefit_type,
                "benefit_value": value,
                "description": description,
                "conditions": [],
                "eligible_categories": categories or [],
                "frequency": "per_transaction",
                "caps": [],
            })
            benefit_id += 1
        
        # Cashback patterns
        cashback_pattern = r'(\d+(?:\.\d+)?)\s*%\s*cashback\s+(?:on\s+)?([^.!?\n]+)'
        for match in re.finditer(cashback_pattern, text, re.IGNORECASE):
            percentage = match.group(1)
            category = match.group(2).strip()
            add_benefit(
                f"{percentage}% Cashback on {category[:30]}",
                "cashback",
                f"{percentage}%",
                match.group(0).strip(),
                [category]
            )
        
        # Discount patterns
        discount_pattern = r'(\d+)\s*%\s*(?:off|discount)\s+(?:on\s+)?([^.!?\n]+)'
        for match in re.finditer(discount_pattern, text, re.IGNORECASE):
            percentage = match.group(1)
            category = match.group(2).strip()
            add_benefit(
                f"{percentage}% Discount on {category[:30]}",
                "discount",
                f"{percentage}%",
                match.group(0).strip(),
                [category]
            )
        
        # Free/Complimentary patterns
        free_pattern = r'(?:free|complimentary)\s+([^.!?\n]{5,80})'
        for match in re.finditer(free_pattern, text, re.IGNORECASE):
            benefit_desc = match.group(1).strip()
            if len(benefit_desc) > 5 and len(benefit_desc) < 100:
                add_benefit(
                    f"Free {benefit_desc[:50]}",
                    "complimentary",
                    "Complimentary",
                    match.group(0).strip()
                )
        
        # Rewards points patterns
        points_pattern = r'(\d+)\s*(?:points?|miles?)\s+(?:per|for\s+every)\s+(?:AED\s+)?(\d+)'
        for match in re.finditer(points_pattern, text, re.IGNORECASE):
            points = match.group(1)
            spend = match.group(2)
            add_benefit(
                f"{points} Points per AED {spend}",
                "rewards_points",
                f"{points} points",
                match.group(0).strip()
            )
        
        # Lounge access as benefit
        lounge_patterns = [
            r'access\s+to\s+(?:over\s+)?(\d+(?:,\d+)?)\s+(?:airport\s+)?lounges?',
            r'(\d+(?:,\d+)?)\s+(?:airport\s+)?lounges?\s+(?:across|worldwide|globally)',
            r'over\s+(\d+(?:,\d+)?)\s+(?:airport\s+)?lounges?',
            r'lounge\s*key\s+(?:access|program)',
            r'priority\s+pass\s+(?:access|membership)',
            r'diners\s+club\s+lounge\s+access',
            r'mastercard\s+lounge\s+access',
        ]
        for pattern in lounge_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                count = match.group(1) if match.lastindex and match.group(1) else ""
                count = count.replace(',', '') if count else ""
                add_benefit(
                    f"Airport Lounge Access ({count} lounges)" if count else "Airport Lounge Access",
                    "lounge_access",
                    f"{count} lounges" if count else "Included",
                    match.group(0).strip()
                )
                break
        
        # Specific Diners Club lounge access
        diners_match = re.search(r'diners\s+club[^.]*?(\d+(?:,\d+)?)\s+(?:premium\s+)?lounges?', text, re.IGNORECASE)
        if diners_match:
            count = diners_match.group(1).replace(',', '')
            add_benefit(
                f"Diners Club Lounge Access ({count} lounges)",
                "lounge_access",
                f"{count} lounges",
                diners_match.group(0).strip()
            )
        
        # Specific Mastercard/LoungeKey access
        mc_match = re.search(r'(?:mastercard|loungekey)[^.]*?(\d+)\s+(?:regional|international)?[^.]*?lounges?', text, re.IGNORECASE)
        if mc_match:
            count = mc_match.group(1)
            add_benefit(
                f"LoungeKey Access ({count} lounges)",
                "lounge_access",
                f"{count} lounges",
                mc_match.group(0).strip()
            )
        
        # Golf access
        if re.search(r'golf\s+(?:course|club|access|benefit)', text, re.IGNORECASE):
            add_benefit(
                "Golf Course Access",
                "golf",
                "Complimentary",
                "Access to golf courses"
            )
        
        # Concierge service
        if re.search(r'concierge\s+(?:service|desk|team)', text, re.IGNORECASE):
            add_benefit(
                "Concierge Service",
                "concierge",
                "24/7 Service",
                "Personal concierge assistance"
            )
        
        # Airport transfers
        if re.search(r'airport\s+transfer', text, re.IGNORECASE):
            add_benefit(
                "Airport Transfer",
                "travel",
                "Complimentary",
                "Airport transfer service"
            )
        
        # Valet parking
        if re.search(r'valet\s+parking', text, re.IGNORECASE):
            add_benefit(
                "Valet Parking",
                "parking",
                "Complimentary",
                "Valet parking service"
            )
        
        # Travel insurance
        travel_insurance = re.search(r'travel\s+insurance\s+(?:up\s+to\s+)?(?:AED\s+)?([\d,]+)?', text, re.IGNORECASE)
        if travel_insurance:
            amount = travel_insurance.group(1) if travel_insurance.lastindex else ""
            add_benefit(
                "Travel Insurance",
                "insurance",
                f"AED {amount}" if amount else "Included",
                "Travel insurance coverage"
            )
        
        # Purchase protection / Credit shield
        if re.search(r'(?:purchase|credit)\s+(?:protection|shield)', text, re.IGNORECASE):
            add_benefit(
                "Purchase Protection",
                "insurance",
                "Included",
                "Purchase protection coverage"
            )
        
        # Death/Life cover - multiple patterns
        death_patterns = [
            r'(?:death|life|decease)\s+cover[^.]*?(?:up\s+to\s+)?(?:AED\s+)?([\d,]+)',
            r'up\s+to\s+(?:AED\s+)?([\d,]+)[^.]*?(?:death|decease|life)\s+cover',
            r'(?:AED\s+)?([\d,]+)[^.]*?(?:decease|death)\s+cover\s+per\s+cardholder',
        ]
        for pattern in death_patterns:
            death_cover = re.search(pattern, text, re.IGNORECASE)
            if death_cover:
                amount = death_cover.group(1).replace(',', '')
                add_benefit(
                    "Life Insurance Cover",
                    "insurance",
                    f"AED {amount}",
                    f"Death/life cover up to AED {amount}"
                )
                break
        
        # Hospitalization cover - multiple patterns
        hospital_patterns = [
            r'(?:hospital|hospitalization)[^.]*?(?:AED\s+)?([\d,]+)\s*(?:per\s+day)?',
            r'(?:AED\s+)?([\d,]+)[^.]*?(?:per\s+day|pay\s+out)[^.]*?(?:hospital|hospitalization)',
            r'pay\s+out[^.]*?(?:AED\s+)?([\d,]+)[^.]*?(?:hospital|hospitalization)',
        ]
        for pattern in hospital_patterns:
            hospital_cover = re.search(pattern, text, re.IGNORECASE)
            if hospital_cover:
                amount = hospital_cover.group(1).replace(',', '')
                add_benefit(
                    "Hospitalization Cover",
                    "insurance",
                    f"AED {amount}/day",
                    f"Hospitalization payout of AED {amount} per day"
                )
                break
        
        # Job loss cover - multiple patterns
        job_loss_patterns = [
            r'job\s+loss\s+cover[^.]*?(?:up\s+to\s+)?(?:AED\s+)?([\d,]+)?',
            r'(?:up\s+to\s+)?(?:AED\s+)?([\d,]+)[^.]*?job\s+loss\s+cover',
        ]
        for pattern in job_loss_patterns:
            job_match = re.search(pattern, text, re.IGNORECASE)
            if job_match:
                amount = job_match.group(1).replace(',', '') if job_match.lastindex and job_match.group(1) else ""
                add_benefit(
                    "Job Loss Cover",
                    "insurance",
                    f"AED {amount}" if amount else "Included",
                    "Job loss protection coverage"
                )
                break
        
        # Movie tickets / Cinema benefits
        movie_patterns = [
            r'(?:buy\s+\d+\s+get\s+\d+|b\d+g\d+)\s+(?:free\s+)?(?:movie\s+)?tickets?',
            r'movie\s+(?:tickets?|benefits?)',
            r'cinema\s+(?:tickets?|benefits?|access)',
            r'cine\s+royal',
        ]
        for pattern in movie_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                add_benefit(
                    "Cinema/Movie Benefits",
                    "entertainment",
                    "Included",
                    "Movie ticket benefits"
                )
                break
        
        # Dining benefits
        if re.search(r'dining\s+(?:benefits?|offers?|discounts?)', text, re.IGNORECASE):
            add_benefit(
                "Dining Benefits",
                "dining",
                "Various offers",
                "Dining discounts and offers"
            )
        
        # Rewards multiplier
        multiplier_pattern = r'(\d+)x\s+(?:rewards?|points?)\s+(?:on\s+)?([^.!?\n]+)?'
        for match in re.finditer(multiplier_pattern, text, re.IGNORECASE):
            multiplier = match.group(1)
            category = match.group(2).strip() if match.group(2) else "all spending"
            add_benefit(
                f"{multiplier}x Rewards on {category[:30]}",
                "rewards_multiplier",
                f"{multiplier}x",
                match.group(0).strip()
            )
        
        # Interest rate / Monthly fee
        interest_pattern = r'(\d+(?:\.\d+)?)\s*%\s*(?:monthly\s+)?(?:fee|interest|rate)'
        interest_match = re.search(interest_pattern, text, re.IGNORECASE)
        if interest_match:
            rate = interest_match.group(1)
            add_benefit(
                f"Low Interest Rate",
                "interest_rate",
                f"{rate}% monthly",
                f"Interest rate of {rate}%"
            )
        
        return benefits[:25]  # Limit to 25 benefits

    def _extract_entitlements_fallback(self, text: str) -> List[Dict[str, Any]]:
        """Extract entitlements using regex patterns."""
        import re
        
        entitlements = []
        entitlement_id = 1
        
        # Lounge access
        if re.search(r'lounge\s+access', text, re.IGNORECASE):
            lounge_count = None
            lounge_match = re.search(r'(\d+)\s*(?:free\s+)?lounge\s+(?:access|visits?)', text, re.IGNORECASE)
            if lounge_match:
                lounge_count = int(lounge_match.group(1))
            
            entitlements.append({
                "entitlement_id": f"entitlement_{entitlement_id}",
                "entitlement_name": "Airport Lounge Access",
                "entitlement_type": "lounge_access",
                "description": "Access to airport lounges worldwide",
                "quantity": lounge_count,
                "conditions": self._extract_conditions(text, "lounge"),
                "redemption_locations": ["International Airports"],
                "partner_networks": self._extract_lounge_networks(text),
            })
            entitlement_id += 1
        
        # Movie tickets
        movie_pattern = r'(\d+)\s*(?:free\s+)?movie\s+tickets?\s+(?:for\s+)?(?:AED\s+)?(\d+)?'
        movie_match = re.search(movie_pattern, text, re.IGNORECASE)
        if movie_match:
            entitlements.append({
                "entitlement_id": f"entitlement_{entitlement_id}",
                "entitlement_name": "Movie Tickets",
                "entitlement_type": "entertainment",
                "description": f"{movie_match.group(1)} movie tickets" + (f" for AED {movie_match.group(2)}" if movie_match.group(2) else ""),
                "quantity": int(movie_match.group(1)),
                "conditions": ["Monthly benefit"],
                "redemption_locations": self._extract_cinemas(text),
            })
            entitlement_id += 1
        
        # Valet parking
        if re.search(r'valet\s+parking', text, re.IGNORECASE):
            valet_match = re.search(r'(\d+)\s*(?:free\s+)?valet\s+parking', text, re.IGNORECASE)
            entitlements.append({
                "entitlement_id": f"entitlement_{entitlement_id}",
                "entitlement_name": "Valet Parking",
                "entitlement_type": "valet_parking",
                "description": "Complimentary valet parking service",
                "quantity": int(valet_match.group(1)) if valet_match else None,
                "conditions": self._extract_conditions(text, "valet"),
                "redemption_locations": [],
            })
            entitlement_id += 1
        
        # Golf access
        if re.search(r'golf\s+(?:access|green\s+fee)', text, re.IGNORECASE):
            entitlements.append({
                "entitlement_id": f"entitlement_{entitlement_id}",
                "entitlement_name": "Golf Access",
                "entitlement_type": "golf_access",
                "description": "Complimentary or discounted golf access",
                "conditions": self._extract_conditions(text, "golf"),
                "redemption_locations": [],
            })
            entitlement_id += 1
        
        # Concierge
        if re.search(r'concierge\s+service', text, re.IGNORECASE):
            entitlements.append({
                "entitlement_id": f"entitlement_{entitlement_id}",
                "entitlement_name": "Concierge Service",
                "entitlement_type": "concierge",
                "description": "24/7 Concierge service",
                "conditions": [],
                "redemption_locations": [],
            })
            entitlement_id += 1
        
        # Airport transfer
        if re.search(r'airport\s+transfer', text, re.IGNORECASE):
            entitlements.append({
                "entitlement_id": f"entitlement_{entitlement_id}",
                "entitlement_name": "Airport Transfer",
                "entitlement_type": "airport_transfer",
                "description": "Complimentary airport transfer service",
                "conditions": self._extract_conditions(text, "transfer"),
                "redemption_locations": [],
            })
            entitlement_id += 1
        
        return entitlements

    def _extract_merchants_fallback(self, text: str) -> List[Dict[str, Any]]:
        """Extract merchants using keyword matching."""
        import re
        
        merchants = []
        text_lower = text.lower()
        
        known_merchants = {
            'Carrefour': {'type': 'supermarket', 'keywords': ['carrefour']},
            'Spinneys': {'type': 'supermarket', 'keywords': ['spinneys']},
            'Lulu': {'type': 'supermarket', 'keywords': ['lulu hypermarket', 'lulu']},
            'Talabat': {'type': 'food_delivery', 'keywords': ['talabat']},
            'Deliveroo': {'type': 'food_delivery', 'keywords': ['deliveroo']},
            'Noon': {'type': 'online', 'keywords': ['noon.com', 'noon food']},
            'Amazon': {'type': 'online', 'keywords': ['amazon.ae', 'amazon']},
            'Costa Coffee': {'type': 'cafe', 'keywords': ['costa coffee', 'costa']},
            'Starbucks': {'type': 'cafe', 'keywords': ['starbucks']},
            'Reel Cinemas': {'type': 'entertainment', 'keywords': ['reel cinema']},
            'VOX Cinemas': {'type': 'entertainment', 'keywords': ['vox cinema']},
            'Cine Royal': {'type': 'entertainment', 'keywords': ['cine royal']},
            'Star Cinemas': {'type': 'entertainment', 'keywords': ['star cinema']},
            'Oscar Cinema': {'type': 'entertainment', 'keywords': ['oscar cinema']},
            'Careem': {'type': 'transportation', 'keywords': ['careem']},
            'Uber': {'type': 'transportation', 'keywords': ['uber']},
            'MakeMyTrip': {'type': 'travel', 'keywords': ['makemytrip']},
            'Booking.com': {'type': 'travel', 'keywords': ['booking.com']},
            'Agoda': {'type': 'travel', 'keywords': ['agoda']},
            'Emirates': {'type': 'airline', 'keywords': ['emirates airline', 'fly emirates']},
            'Etihad': {'type': 'airline', 'keywords': ['etihad']},
            'ENOC': {'type': 'fuel', 'keywords': ['enoc', 'eppco']},
            'ADNOC': {'type': 'fuel', 'keywords': ['adnoc']},
            'Emarat': {'type': 'fuel', 'keywords': ['emarat']},
        }
        
        for merchant_name, info in known_merchants.items():
            found = any(keyword in text_lower for keyword in info['keywords'])
            if found:
                merchants.append({
                    "merchant_name": merchant_name,
                    "merchant_category": info['type'],
                    "offers": self._extract_merchant_offers(text, merchant_name),
                    "is_online": info['type'] in ['online', 'food_delivery', 'travel'],
                    "redemption_method": "card_payment",
                })
        
        return merchants

    def _extract_fees_fallback(self, text: str) -> Dict[str, Any]:
        """Extract fees using regex patterns."""
        import re
        
        fees = {}
        
        # Annual fee
        annual_patterns = [
            r'annual\s+fee[:\s]+AED\s+([\d,]+)',
            r'annual\s+fee[:\s]+([\d,]+)\s*AED',
            r'AED\s+([\d,]+)\s+annual\s+fee',
            r'annual\s+fee[:\s]*(free|waived|nil|zero|0)',
        ]
        for pattern in annual_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1)
                if value.lower() in ['free', 'waived', 'nil', 'zero', '0']:
                    fees['annual_fee'] = 'AED 0'
                else:
                    fees['annual_fee'] = f'AED {value.replace(",", "")}'
                break
        
        # Interest rate
        interest_pattern = r'(?:interest|APR)\s+rate[:\s]+(\d+(?:\.\d+)?)\s*%'
        interest_match = re.search(interest_pattern, text, re.IGNORECASE)
        if interest_match:
            fees['interest_rate'] = f'{interest_match.group(1)}%'
        
        # Monthly fee rate (like "0.99% Monthly fee")
        monthly_rate_patterns = [
            r'(\d+(?:\.\d+)?)\s*%\s*(?:monthly\s+)?fee',
            r'monthly\s+fee[:\s]+(\d+(?:\.\d+)?)\s*%',
            r'(\d+(?:\.\d+)?)\s*%[^.]*?outstanding\s+balance',
        ]
        for pattern in monthly_rate_patterns:
            monthly_match = re.search(pattern, text, re.IGNORECASE)
            if monthly_match:
                fees['interest_rate'] = f'{monthly_match.group(1)}% monthly'
                break
        
        # Foreign transaction fee
        foreign_pattern = r'foreign\s+(?:transaction\s+)?fee[:\s]+(\d+(?:\.\d+)?)\s*%'
        foreign_match = re.search(foreign_pattern, text, re.IGNORECASE)
        if foreign_match:
            fees['foreign_transaction_fee'] = f'{foreign_match.group(1)}%'
        
        # Late payment fee
        late_pattern = r'late\s+payment\s+fee[:\s]+AED\s+([\d,]+)'
        late_match = re.search(late_pattern, text, re.IGNORECASE)
        if late_match:
            fees['late_payment_fee'] = f'AED {late_match.group(1).replace(",", "")}'
        
        # Cash advance fee
        cash_pattern = r'cash\s+advance\s+fee[:\s]+(\d+(?:\.\d+)?)\s*%'
        cash_match = re.search(cash_pattern, text, re.IGNORECASE)
        if cash_match:
            fees['cash_advance_fee'] = f'{cash_match.group(1)}%'
        
        return fees

    def _extract_eligibility_fallback(self, text: str) -> Dict[str, Any]:
        """Extract eligibility using regex patterns."""
        import re
        
        eligibility = {}
        
        # Minimum salary
        salary_patterns = [
            r'(?:minimum\s+)?salary[:\s]+AED\s+([\d,]+)',
            r'AED\s+([\d,]+)\s+(?:minimum\s+)?salary',
            r'salary\s+(?:of\s+)?(?:at\s+least\s+)?AED\s+([\d,]+)',
        ]
        for pattern in salary_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                eligibility['minimum_salary'] = f'AED {match.group(1).replace(",", "")}'
                break
        
        # Minimum spend
        spend_pattern = r'minimum\s+spend(?:\s+criteria)?[:\s]+AED\s+([\d,]+)'
        spend_match = re.search(spend_pattern, text, re.IGNORECASE)
        if spend_match:
            eligibility['minimum_spend'] = f'AED {spend_match.group(1).replace(",", "")}'
        
        # Minimum age
        age_pattern = r'(?:minimum\s+)?age[:\s]+(\d+)\s*(?:years?)?'
        age_match = re.search(age_pattern, text, re.IGNORECASE)
        if age_match:
            eligibility['minimum_age'] = age_match.group(1)
        
        # Employment type
        if re.search(r'salaried', text, re.IGNORECASE):
            eligibility['employment_type'] = 'Salaried'
        elif re.search(r'self[- ]employed', text, re.IGNORECASE):
            eligibility['employment_type'] = 'Self-employed'
        
        # UAE National benefits
        if re.search(r'UAE\s+national', text, re.IGNORECASE):
            uae_match = re.search(r'UAE\s+national[s]?[:\s]+([^.!?\n]+)', text, re.IGNORECASE)
            if uae_match:
                eligibility['uae_national_benefits'] = uae_match.group(1).strip()
        
        return eligibility

    def _extract_conditions(self, text: str, category: str) -> List[str]:
        """Extract conditions related to a category."""
        import re
        
        conditions = []
        category_lower = category.lower()
        
        # Find context around the category
        context_start = text.lower().find(category_lower)
        if context_start == -1:
            return conditions
        
        context = text[context_start:context_start + 500]
        
        patterns = [
            r'minimum\s+spend[:\s]+AED\s+[\d,]+',
            r'up\s+to\s+AED\s+[\d,]+',
            r'capped\s+at\s+AED\s+[\d,]+',
            r'maximum\s+(?:of\s+)?AED\s+[\d,]+',
            r'\d+\s+times?\s+(?:a|per)\s+month',
            r'minimum\s+order\s+AED\s+[\d,]+',
            r'valid\s+(?:until|till)\s+[^.!?\n]+',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, context, re.IGNORECASE)
            conditions.extend(matches)
        
        return list(set(conditions))[:5]

    def _extract_cap_info(self, text: str, category: str) -> List[Dict[str, Any]]:
        """Extract cap information for a benefit."""
        import re
        
        caps = []
        
        # Look for cap in context
        cap_pattern = rf'{re.escape(category)}.*?(?:up\s+to|maximum|capped\s+at)\s+AED\s+([\d,]+)'
        match = re.search(cap_pattern, text, re.IGNORECASE)
        if match:
            caps.append({
                "cap_type": "amount",
                "cap_value": int(match.group(1).replace(",", "")),
                "currency": "AED",
                "period": "monthly"
            })
        
        return caps

    def _extract_lounge_networks(self, text: str) -> List[str]:
        """Extract lounge network names."""
        import re
        
        networks = []
        if re.search(r'lounge\s*key', text, re.IGNORECASE):
            networks.append("LoungeKey")
        if re.search(r'priority\s*pass', text, re.IGNORECASE):
            networks.append("Priority Pass")
        if re.search(r'dragon\s*pass', text, re.IGNORECASE):
            networks.append("DragonPass")
        
        return networks

    def _extract_cinemas(self, text: str) -> List[str]:
        """Extract cinema names from text."""
        cinemas = ['Reel Cinemas', 'VOX Cinemas', 'Cine Royal', 'Star Cinemas', 'Oscar Cinema', 'Novo Cinemas']
        return [cinema for cinema in cinemas if cinema.lower() in text.lower()]

    def _extract_merchant_offers(self, text: str, merchant: str) -> List[Dict[str, Any]]:
        """Extract offers for a specific merchant."""
        import re
        
        offers = []
        merchant_lower = merchant.lower()
        
        # Find merchant section
        merchant_idx = text.lower().find(merchant_lower)
        if merchant_idx == -1:
            return offers
        
        section = text[merchant_idx:merchant_idx + 500]
        
        # Look for offers
        offer_patterns = [
            (r'(\d+)\s*%\s*(?:off|cashback|discount)', 'discount'),
            (r'AED\s*([\d,]+)\s*off', 'fixed_discount'),
            (r'buy\s*(\d+)\s*get\s*(\d+)', 'bogo'),
        ]
        
        for pattern, offer_type in offer_patterns:
            matches = re.findall(pattern, section, re.IGNORECASE)
            for match in matches[:2]:  # Limit to 2 offers per type
                if offer_type == 'discount':
                    offers.append({
                        "offer_type": "discount",
                        "offer_value": f"{match}% off",
                        "description": f"{match}% discount at {merchant}",
                    })
                elif offer_type == 'fixed_discount':
                    offers.append({
                        "offer_type": "fixed_discount",
                        "offer_value": f"AED {match} off",
                        "description": f"AED {match} discount at {merchant}",
                    })
                elif offer_type == 'bogo':
                    offers.append({
                        "offer_type": "bogo",
                        "offer_value": f"Buy {match[0]} Get {match[1]}",
                        "description": f"Buy {match[0]} Get {match[1]} at {merchant}",
                    })
        
        return offers[:3]  # Limit to 3 offers per merchant

    async def get_by_id(self, extraction_id: str) -> ExtractedDataV2:
        """Get extraction by ID."""
        extracted_data = await ExtractedDataV2.get(extraction_id)
        if not extracted_data:
            raise ExtractionError("Extraction not found")
        return extracted_data

    async def delete(self, extraction_id: str) -> bool:
        """Soft delete an extraction."""
        extracted_data = await self.get_by_id(extraction_id)
        await extracted_data.soft_delete()
        logger.info(f"Deleted extraction: {extraction_id}")
        return True


# Global instance
enhanced_extraction_service = EnhancedExtractionService()
