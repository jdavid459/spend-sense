with source as (
    select * from raw.chase_transactions
),

renamed as (
    select
        row_hash as transaction_id,
        strptime("Transaction Date", '%m/%d/%Y')::date as transaction_date,
        strptime("Post Date", '%m/%d/%Y')::date as post_date,
        "Description"::varchar as raw_description,
        upper(trim("Description")) as clean_description,
        "Category"::varchar as raw_category,
        "Type"::varchar as transaction_type,
        cast("Amount" as decimal(18, 2)) as amount,
        abs(cast("Amount" as decimal(18, 2))) as amount_abs,
        cast("Amount" as decimal(18, 2)) < 0 as is_debit,
        cast("Amount" as decimal(18, 2)) > 0 as is_credit,
        "Memo"::varchar as memo,
        source_row_number,
        source_file,
        source_mode,
        ingested_at
    from source
)

select * from renamed
