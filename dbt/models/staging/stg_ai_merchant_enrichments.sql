select
    raw_description,
    suggested_merchant,
    suggested_category,
    suggested_merchant_group,
    confidence,
    reasoning,
    model,
    created_at
from ai.merchant_enrichment_cache
