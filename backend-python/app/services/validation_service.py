"""
Validation service for extracted data.
Performs comprehensive validation and quality checks.
"""
from typing import Dict, Any, List, Tuple
from app.core.config import settings
from app.utils.logger import logger
from app.models.extracted_data_v2 import BenefitType, Frequency


class ValidationService:
    """Service for data validation."""

    def __init__(self):
        self.min_confidence = settings.MIN_CONFIDENCE_SCORE
        self.auto_validate_threshold = settings.AUTO_VALIDATE_THRESHOLD

    def validate_extracted_data(self, data: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
        """
        Validate extracted credit card data.

        Args:
            data: Extracted data to validate.

        Returns:
            Tuple of (is_valid, errors, warnings).
        """
        errors = []
        warnings = []

        # Required field validation
        if not data.get("card_name"):
            errors.append("Card name is required")
        elif len(data["card_name"]) < 3:
            errors.append("Card name too short")

        # Benefits validation
        if "benefits" in data and isinstance(data["benefits"], list):
            benefit_errors, benefit_warnings = self._validate_benefits(data["benefits"])
            errors.extend(benefit_errors)
            warnings.extend(benefit_warnings)
        else:
            warnings.append("No benefits found")

        # Merchants validation
        if "merchants_vendors" in data and isinstance(data["merchants_vendors"], list):
            merchant_errors, merchant_warnings = self._validate_merchants(data["merchants_vendors"])
            errors.extend(merchant_errors)
            warnings.extend(merchant_warnings)

        # Fees validation
        if "fees" in data and isinstance(data["fees"], dict):
            fee_warnings = self._validate_fees(data["fees"])
            warnings.extend(fee_warnings)
        else:
            warnings.append("No fee information found")

        # Eligibility validation
        if "eligibility" in data and isinstance(data["eligibility"], dict):
            eligibility_warnings = self._validate_eligibility(data["eligibility"])
            warnings.extend(eligibility_warnings)

        is_valid = len(errors) == 0
        logger.info(
            f"Validation completed: valid={is_valid}, errors={len(errors)}, warnings={len(warnings)}"
        )

        return is_valid, errors, warnings

    def _validate_benefits(self, benefits: List[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
        """Validate benefits array."""
        errors = []
        warnings = []

        if not benefits:
            warnings.append("Benefits array is empty")
            return errors, warnings

        valid_types = [t.value for t in BenefitType]
        valid_frequencies = [f.value for f in Frequency]

        for i, benefit in enumerate(benefits):
            benefit_id = benefit.get("benefit_id", f"benefit_{i}")

            if not benefit.get("benefit_name"):
                errors.append(f"{benefit_id}: Benefit name is required")

            if not benefit.get("benefit_type"):
                errors.append(f"{benefit_id}: Benefit type is required")
            elif benefit["benefit_type"] not in valid_types:
                errors.append(f"{benefit_id}: Invalid benefit type '{benefit['benefit_type']}'")

            if not benefit.get("description"):
                errors.append(f"{benefit_id}: Description is required")
            elif len(benefit["description"]) < 10:
                warnings.append(f"{benefit_id}: Description seems too short")

            if benefit.get("frequency") and benefit["frequency"] not in valid_frequencies:
                warnings.append(f"{benefit_id}: Invalid frequency '{benefit['frequency']}'")

        return errors, warnings

    def _validate_merchants(self, merchants: List[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
        """Validate merchants array."""
        errors = []
        warnings = []

        if not merchants:
            warnings.append("No merchant information found")
            return errors, warnings

        for i, merchant in enumerate(merchants):
            if not merchant.get("merchant_name"):
                errors.append(f"Merchant {i + 1}: Name is required")

            if not merchant.get("merchant_type"):
                warnings.append(f"Merchant '{merchant.get('merchant_name', i + 1)}': Type not specified")

            if not merchant.get("offers") or not isinstance(merchant["offers"], list):
                warnings.append(f"Merchant '{merchant.get('merchant_name', i + 1)}': No offers specified")

        return errors, warnings

    def _validate_fees(self, fees: Dict[str, Any]) -> List[str]:
        """Validate fees object."""
        warnings = []

        if not any(fees.values()):
            warnings.append("No fee information provided")

        return warnings

    def _validate_eligibility(self, eligibility: Dict[str, Any]) -> List[str]:
        """Validate eligibility object."""
        warnings = []

        if not any(eligibility.values()):
            warnings.append("No eligibility criteria provided")

        return warnings

    def calculate_confidence_score(self, data: Dict[str, Any]) -> float:
        """
        Calculate confidence score for extracted data.

        Args:
            data: Extracted data.

        Returns:
            Confidence score between 0 and 1.
        """
        score = 0.0
        max_score = 0.0

        # Card name (20 points)
        max_score += 20
        if data.get("card_name") and len(data["card_name"]) >= 3:
            score += 20

        # Benefits (30 points)
        max_score += 30
        benefits = data.get("benefits", [])
        if benefits:
            score += 15
            complete_benefits = sum(
                1
                for b in benefits
                if b.get("benefit_name")
                and b.get("benefit_type")
                and b.get("description")
            )
            if complete_benefits > 0:
                score += 15 * (complete_benefits / len(benefits))

        # Merchants (20 points)
        max_score += 20
        merchants = data.get("merchants_vendors", [])
        if merchants:
            score += 10
            complete_merchants = sum(
                1 for m in merchants if m.get("merchant_name") and m.get("merchant_type")
            )
            if complete_merchants > 0:
                score += 10 * (complete_merchants / len(merchants))

        # Fees (15 points)
        max_score += 15
        fees = data.get("fees", {})
        if isinstance(fees, dict) and any(fees.values()):
            score += 15

        # Eligibility (15 points)
        max_score += 15
        eligibility = data.get("eligibility", {})
        if isinstance(eligibility, dict) and any(eligibility.values()):
            score += 15

        confidence = score / max_score if max_score > 0 else 0.0
        logger.debug(f"Calculated confidence score: {confidence:.2f}")
        return round(confidence, 2)

    def determine_validation_status(
        self, is_valid: bool, confidence_score: float
    ) -> str:
        """
        Determine validation status based on validation results.

        Args:
            is_valid: Whether data passed validation.
            confidence_score: Confidence score.

        Returns:
            Validation status string.
        """
        if not is_valid:
            return "rejected"

        if confidence_score >= self.auto_validate_threshold:
            return "validated"
        elif confidence_score >= self.min_confidence:
            return "requires_review"
        else:
            return "rejected"


# Global validation service instance
validation_service = ValidationService()
