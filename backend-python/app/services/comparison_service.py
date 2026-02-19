"""
Comparison service for comparing multiple credit cards.
Provides side-by-side analysis and recommendations.
"""
from typing import List, Dict, Any, Optional
import secrets

from app.core.exceptions import ComparisonError, NotFoundError
from app.utils.logger import logger
from app.models.comparison import (
    Comparison,
    ComparisonCard,
    ComparisonResult,
    BenefitComparison,
    FeeComparison,
)
from app.models.extracted_data_v2 import ExtractedDataV2


class ComparisonService:
    """Service for card comparison operations."""

    async def create_comparison(
        self,
        comparison_name: str,
        card_ids: List[str],
        description: Optional[str] = None,
        criteria: Optional[Dict[str, Any]] = None,
        is_public: bool = False,
        tags: Optional[List[str]] = None,
    ) -> Comparison:
        """
        Create a new card comparison.

        Args:
            comparison_name: Name of the comparison.
            card_ids: List of card IDs to compare.
            description: Optional description.
            criteria: Comparison criteria.
            is_public: Whether comparison is public.
            tags: Optional tags.

        Returns:
            Created Comparison.

        Raises:
            ComparisonError: If creation fails.
        """
        try:
            # Validate cards exist
            cards = []
            for card_id in card_ids:
                card = await ExtractedDataV2.get(card_id)
                if not card:
                    raise ComparisonError(f"Card not found: {card_id}")

                cards.append(
                    ComparisonCard(
                        card_id=card_id,
                        card_name=card.card_name,
                        card_issuer=card.card_issuer,
                        display_order=len(cards),
                    )
                )

            # Generate share token if public
            share_token = secrets.token_urlsafe(16) if is_public else None

            # Create comparison
            comparison = Comparison(
                comparison_name=comparison_name,
                description=description,
                cards=cards,
                criteria=criteria or {},
                is_public=is_public,
                share_token=share_token,
                tags=tags or [],
            )

            await comparison.insert()
            logger.info(f"Created comparison: {comparison.id}")

            return comparison

        except ComparisonError:
            raise
        except Exception as e:
            logger.error(f"Failed to create comparison: {str(e)}")
            raise ComparisonError(f"Failed to create comparison: {str(e)}")

    async def analyze_comparison(self, comparison_id: str) -> ComparisonResult:
        """
        Analyze a comparison and generate results.

        Args:
            comparison_id: Comparison ID.

        Returns:
            ComparisonResult.

        Raises:
            ComparisonError: If analysis fails.
        """
        try:
            comparison = await Comparison.get(comparison_id)
            if not comparison:
                raise NotFoundError("Comparison not found")

            # Fetch all cards
            cards = {}
            for card_ref in comparison.cards:
                card = await ExtractedDataV2.get(card_ref.card_id)
                if card:
                    cards[card_ref.card_id] = card

            # Perform analysis
            benefit_comparisons = []
            fee_comparisons = []

            if comparison.criteria.compare_benefits:
                benefit_comparisons = self._compare_benefits(cards)

            if comparison.criteria.compare_fees:
                fee_comparisons = self._compare_fees(cards)

            # Determine overall winner (simple heuristic)
            overall_winner = self._determine_winner(cards)

            # Generate summary
            summary = self._generate_summary(cards, benefit_comparisons, fee_comparisons)

            # Generate recommendations
            recommendations = self._generate_recommendations(
                cards, benefit_comparisons, fee_comparisons
            )

            result = ComparisonResult(
                benefit_comparisons=benefit_comparisons,
                fee_comparisons=fee_comparisons,
                overall_winner=overall_winner,
                summary=summary,
                recommendations=recommendations,
            )

            # Save results
            await comparison.complete_analysis(result)

            logger.info(f"Completed comparison analysis: {comparison_id}")
            return result

        except NotFoundError:
            raise
        except Exception as e:
            logger.error(f"Comparison analysis failed: {str(e)}")
            raise ComparisonError(f"Comparison analysis failed: {str(e)}")

    def _compare_benefits(self, cards: Dict[str, ExtractedDataV2]) -> List[BenefitComparison]:
        """Compare benefits across cards."""
        comparisons = []
        benefit_types = set()

        # Collect all benefit types
        for card in cards.values():
            for benefit in card.benefits:
                benefit_types.add(benefit.benefit_type)

        # Compare each benefit type
        for benefit_type in benefit_types:
            card_benefits = {}
            for card_id, card in cards.items():
                benefits = [
                    benefit.description
                    for benefit in card.benefits
                    if benefit.benefit_type == benefit_type
                ]
                card_benefits[card_id] = benefits

            comparisons.append(
                BenefitComparison(
                    benefit_type=benefit_type, card_benefits=card_benefits
                )
            )

        return comparisons

    def _compare_fees(self, cards: Dict[str, ExtractedDataV2]) -> List[FeeComparison]:
        """Compare fees across cards."""
        comparisons = []
        fee_types = ["annual_fee", "interest_rate", "foreign_transaction_fee"]

        for fee_type in fee_types:
            card_fees = {}
            for card_id, card in cards.items():
                fee_value = getattr(card.fees, fee_type, None)
                card_fees[card_id] = fee_value

            comparisons.append(FeeComparison(fee_type=fee_type, card_fees=card_fees))

        return comparisons

    def _determine_winner(self, cards: Dict[str, ExtractedDataV2]) -> Optional[str]:
        """Determine overall best card (simple heuristic based on confidence)."""
        best_card_id = None
        best_score = 0

        for card_id, card in cards.items():
            score = card.confidence_score or 0
            if score > best_score:
                best_score = score
                best_card_id = card_id

        return best_card_id

    def _generate_summary(
        self,
        cards: Dict[str, ExtractedDataV2],
        benefit_comparisons: List[BenefitComparison],
        fee_comparisons: List[FeeComparison],
    ) -> str:
        """Generate comparison summary."""
        return f"Comparison of {len(cards)} credit cards across {len(benefit_comparisons)} benefit types and {len(fee_comparisons)} fee categories."

    def _generate_recommendations(
        self,
        cards: Dict[str, ExtractedDataV2],
        benefit_comparisons: List[BenefitComparison],
        fee_comparisons: List[FeeComparison],
    ) -> List[str]:
        """Generate recommendations."""
        recommendations = []

        # Example recommendations
        for card_id, card in cards.items():
            if len(card.benefits) > 5:
                recommendations.append(
                    f"{card.card_name} offers a wide range of {len(card.benefits)} benefits"
                )

        return recommendations

    async def get_comparison(self, comparison_id: str) -> Comparison:
        """Get comparison by ID."""
        comparison = await Comparison.get(comparison_id)
        if not comparison:
            raise NotFoundError("Comparison not found")
        return comparison

    async def delete_comparison(self, comparison_id: str) -> bool:
        """Delete a comparison."""
        comparison = await self.get_comparison(comparison_id)
        await comparison.delete()
        logger.info(f"Deleted comparison: {comparison_id}")
        return True


# Global comparison service instance
comparison_service = ComparisonService()
