WITH bureau_balance_by_loan AS (
    SELECT
        SK_ID_BUREAU,
        COUNT(*) AS BB_MONTH_COUNT,
        MIN(MONTHS_BALANCE) AS BB_MONTHS_OLDEST,
        MAX(MONTHS_BALANCE) AS BB_MONTHS_MOST_RECENT,
        SUM(
            CASE
                WHEN STATUS_IS_DPD THEN 1
                WHEN STATUS_IS_DPD IS FALSE THEN 0
            END
        ) AS BB_DPD_MONTH_COUNT,
        AVG(CASE WHEN STATUS_IS_DPD IS NOT NULL THEN CAST(STATUS_IS_DPD AS INTEGER) END)
            AS BB_DPD_MONTH_RATE,
        SUM(
            CASE
                WHEN STATUS_IS_CLOSED THEN 1
                WHEN STATUS_IS_CLOSED IS FALSE THEN 0
            END
        ) AS BB_CLOSED_MONTH_COUNT
    FROM source_bureau_balance
    GROUP BY SK_ID_BUREAU
),
loan_ids AS (
    SELECT SK_ID_BUREAU FROM source_bureau
    UNION
    SELECT SK_ID_BUREAU FROM bureau_balance_by_loan
)
SELECT
    loan_ids.SK_ID_BUREAU,
    COALESCE(dim_customer.CustomerKey, -1) AS CustomerKey,
    source_bureau.CREDIT_ACTIVE,
    source_bureau.CREDIT_TYPE,
    source_bureau.DAYS_CREDIT,
    source_bureau.CREDIT_DAY_OVERDUE,
    source_bureau.AMT_CREDIT_SUM,
    source_bureau.AMT_CREDIT_SUM_DEBT,
    source_bureau.AMT_CREDIT_SUM_OVERDUE,
    source_bureau.CNT_CREDIT_PROLONG,
    source_bureau.FLAG_CLOSED_WITHOUT_END_DATE,
    source_bureau.FLAG_NEGATIVE_DEBT,
    CASE WHEN bureau_balance_by_loan.SK_ID_BUREAU IS NULL THEN 1 ELSE 0 END
        AS FLAG_NO_BUREAU_BALANCE,
    bureau_balance_by_loan.BB_MONTH_COUNT,
    bureau_balance_by_loan.BB_MONTHS_OLDEST,
    bureau_balance_by_loan.BB_MONTHS_MOST_RECENT,
    bureau_balance_by_loan.BB_DPD_MONTH_COUNT,
    bureau_balance_by_loan.BB_DPD_MONTH_RATE,
    bureau_balance_by_loan.BB_CLOSED_MONTH_COUNT
FROM loan_ids
LEFT JOIN source_bureau
    ON loan_ids.SK_ID_BUREAU = source_bureau.SK_ID_BUREAU
LEFT JOIN bureau_balance_by_loan
    ON loan_ids.SK_ID_BUREAU = bureau_balance_by_loan.SK_ID_BUREAU
LEFT JOIN dim_customer
    ON source_bureau.SK_ID_CURR = dim_customer.SK_ID_CURR
