with txns as (
    select * from {{ ref('stg_chase_transactions') }}
),

rules as (
    select * from {{ ref('merchant_rules') }}
),

matched as (
    select
        txns.transaction_id,
        rules.normalized_merchant,
        rules.merchant_group,
        rules.default_category,
        row_number() over (
            partition by txns.transaction_id
            order by length(rules.pattern) desc
        ) as match_rank
    from txns
    left join rules
        on txns.clean_description like '%' || upper(rules.pattern) || '%'
)

select
    txns.transaction_id,
    coalesce(matched.normalized_merchant, txns.raw_description) as normalized_merchant,
    coalesce(matched.merchant_group, 'Unmapped') as merchant_group,
    matched.default_category as rule_category
from txns
left join matched
    on txns.transaction_id = matched.transaction_id
    and matched.match_rank = 1
