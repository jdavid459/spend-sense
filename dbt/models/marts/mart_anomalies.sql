select
    transaction_id,
    transaction_date,
    normalized_merchant,
    final_category,
    amount_abs,
    anomaly_reason,
    greatest(coalesce(zscore_vs_merchant, 0), coalesce(zscore_vs_category, 0)) as severity_score
from {{ ref('fct_transactions') }}
where is_anomaly
