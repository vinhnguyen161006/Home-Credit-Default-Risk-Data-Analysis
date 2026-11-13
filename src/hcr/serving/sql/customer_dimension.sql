WITH customer_ids AS (
    SELECT SK_ID_CURR FROM source_application
    UNION
    SELECT SK_ID_CURR FROM source_bureau
    UNION
    SELECT SK_ID_CURR FROM source_previous_application
    UNION
    SELECT SK_ID_CURR FROM source_pos_cash
    UNION
    SELECT SK_ID_CURR FROM source_installments
    UNION
    SELECT SK_ID_CURR FROM source_credit_card
),
numbered_customers AS (
    SELECT
        CAST(ROW_NUMBER() OVER (ORDER BY customer_ids.SK_ID_CURR) AS INTEGER) AS CustomerKey,
        customer_ids.SK_ID_CURR
    FROM customer_ids
    WHERE customer_ids.SK_ID_CURR IS NOT NULL
)
SELECT
    numbered_customers.CustomerKey,
    numbered_customers.SK_ID_CURR,
    COALESCE(source_application.CODE_GENDER, 'Unknown') AS CODE_GENDER,
    COALESCE(source_application.FLAG_OWN_CAR, 'Unknown') AS FLAG_OWN_CAR,
    COALESCE(source_application.FLAG_OWN_REALTY, 'Unknown') AS FLAG_OWN_REALTY
FROM numbered_customers
LEFT JOIN source_application
    ON numbered_customers.SK_ID_CURR = source_application.SK_ID_CURR
UNION ALL
SELECT
    -1 AS CustomerKey,
    NULL::BIGINT AS SK_ID_CURR,
    'Unknown' AS CODE_GENDER,
    'Unknown' AS FLAG_OWN_CAR,
    'Unknown' AS FLAG_OWN_REALTY
