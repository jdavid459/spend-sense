with txns as (
    select * from {{ ref('stg_chase_transactions') }}
),

rules as (
    select * from {{ ref('merchant_rules') }}
),

ai_enrichments as (
    select * from {{ ref('stg_ai_merchant_enrichments') }}
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
),

best_match as (
    select *
    from matched
    where match_rank = 1
),

resolved as (
    select
        txns.transaction_id,
        coalesce(
            best_match.normalized_merchant,
            case when ai_enrichments.confidence >= 0.70 then ai_enrichments.suggested_merchant end,
            txns.raw_description
        ) as normalized_merchant,
        coalesce(
            best_match.merchant_group,
            case when ai_enrichments.confidence >= 0.70 then ai_enrichments.suggested_merchant_group end,
            'Unmapped'
        ) as merchant_group,
        best_match.default_category as rule_category,
        case when ai_enrichments.confidence >= 0.70 then ai_enrichments.suggested_category end as ai_category,
        ai_enrichments.confidence as ai_confidence,
        ai_enrichments.reasoning as ai_reasoning,
        case
            when best_match.normalized_merchant is not null then 'seed_rule'
            when ai_enrichments.confidence >= 0.70 then 'cohere_cache'
            else 'fallback'
        end as merchant_source,
        case
            when best_match.default_category is not null then 'seed_rule'
            when ai_enrichments.confidence >= 0.70 and ai_enrichments.suggested_category is not null then 'cohere_cache'
            else 'chase_raw'
        end as category_source
    from txns
    left join best_match
        on txns.transaction_id = best_match.transaction_id
    left join ai_enrichments
        on txns.raw_description = ai_enrichments.raw_description
)

select * from resolved
