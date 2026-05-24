select
    normalized_merchant,
    final_category,
    cadence,
    avg_amount,
    amount_stddev,
    transaction_count,
    first_seen,
    last_seen,
    case
        when cadence = 'monthly' then avg_amount
        when cadence = 'weekly' then avg_amount * 4.33
        else null
    end as estimated_monthly_cost
from {{ ref('int_recurring_transactions') }}
where is_recurring
