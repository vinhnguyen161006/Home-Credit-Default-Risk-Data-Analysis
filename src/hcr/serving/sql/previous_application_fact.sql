WITH previous_keys AS (
    SELECT SK_ID_PREV, MIN(SK_ID_CURR) AS SK_ID_CURR
    FROM (
        SELECT SK_ID_PREV, SK_ID_CURR FROM source_previous_application
        UNION ALL
        SELECT SK_ID_PREV, SK_ID_CURR FROM source_pos_cash
        UNION ALL
        SELECT SK_ID_PREV, SK_ID_CURR FROM source_installments
        UNION ALL
        SELECT SK_ID_PREV, SK_ID_CURR FROM source_credit_card
    ) AS all_previous_rows
    GROUP BY SK_ID_PREV
),
pos_cash_by_contract AS (
    SELECT
        SK_ID_PREV,
        COUNT(*) AS POS_MONTH_COUNT,
        AVG(SK_DPD) AS POS_DPD_MEAN,
        MAX(SK_DPD) AS POS_DPD_MAX,
        AVG(CNT_INSTALMENT_FUTURE) AS POS_FUTURE_INSTALMENTS_MEAN,
        SUM(CASE WHEN IS_DPD THEN 1 WHEN IS_DPD IS FALSE THEN 0 END)
            AS POS_DPD_MONTH_COUNT
    FROM source_pos_cash
    GROUP BY SK_ID_PREV
),
installments_by_contract AS (
    SELECT
        SK_ID_PREV,
        COUNT(*) AS INST_PAYMENT_COUNT,
        SUM(AMT_PAYMENT) AS INST_PAYMENT_AMOUNT_SUM,
        AVG(PAYMENT_DELAY_DAYS) AS INST_PAYMENT_DELAY_MEAN,
        MAX(PAYMENT_DELAY_DAYS) AS INST_PAYMENT_DELAY_MAX,
        AVG(CAST(IS_LATE AS INTEGER)) AS INST_LATE_PAYMENT_RATE,
        AVG(PAYMENT_RATIO) AS INST_PAYMENT_RATIO_MEAN,
        AVG(CAST(IS_UNDERPAID AS INTEGER)) AS INST_UNDERPAID_RATE
    FROM source_installments
    GROUP BY SK_ID_PREV
),
credit_card_by_contract AS (
    SELECT
        SK_ID_PREV,
        COUNT(*) AS CC_MONTH_COUNT,
        AVG(AMT_BALANCE) AS CC_BALANCE_MEAN,
        MAX(AMT_BALANCE) AS CC_BALANCE_MAX,
        AVG(UTILIZATION) AS CC_UTILIZATION_MEAN,
        MAX(UTILIZATION) AS CC_UTILIZATION_MAX,
        AVG(SK_DPD) AS CC_DPD_MEAN,
        MAX(SK_DPD) AS CC_DPD_MAX
    FROM source_credit_card
    GROUP BY SK_ID_PREV
)
SELECT
    previous_keys.SK_ID_PREV,
    COALESCE(dim_customer.CustomerKey, -1) AS CustomerKey,
    source_previous_application.NAME_CONTRACT_TYPE,
    source_previous_application.NAME_CONTRACT_STATUS,
    source_previous_application.NAME_CLIENT_TYPE,
    source_previous_application.AMT_APPLICATION,
    source_previous_application.AMT_CREDIT,
    source_previous_application.AMT_ANNUITY,
    source_previous_application.AMT_DOWN_PAYMENT,
    source_previous_application.DAYS_DECISION,
    CASE WHEN pos_cash_by_contract.SK_ID_PREV IS NULL THEN 1 ELSE 0 END
        AS FLAG_NO_POS_HISTORY,
    pos_cash_by_contract.POS_MONTH_COUNT,
    pos_cash_by_contract.POS_DPD_MEAN,
    pos_cash_by_contract.POS_DPD_MAX,
    pos_cash_by_contract.POS_FUTURE_INSTALMENTS_MEAN,
    pos_cash_by_contract.POS_DPD_MONTH_COUNT,
    CASE WHEN installments_by_contract.SK_ID_PREV IS NULL THEN 1 ELSE 0 END
        AS FLAG_NO_INSTALLMENT_HISTORY,
    installments_by_contract.INST_PAYMENT_COUNT,
    installments_by_contract.INST_PAYMENT_AMOUNT_SUM,
    installments_by_contract.INST_PAYMENT_DELAY_MEAN,
    installments_by_contract.INST_PAYMENT_DELAY_MAX,
    installments_by_contract.INST_LATE_PAYMENT_RATE,
    installments_by_contract.INST_PAYMENT_RATIO_MEAN,
    installments_by_contract.INST_UNDERPAID_RATE,
    CASE WHEN credit_card_by_contract.SK_ID_PREV IS NULL THEN 1 ELSE 0 END
        AS FLAG_NO_CREDIT_CARD_HISTORY,
    credit_card_by_contract.CC_MONTH_COUNT,
    credit_card_by_contract.CC_BALANCE_MEAN,
    credit_card_by_contract.CC_BALANCE_MAX,
    credit_card_by_contract.CC_UTILIZATION_MEAN,
    credit_card_by_contract.CC_UTILIZATION_MAX,
    credit_card_by_contract.CC_DPD_MEAN,
    credit_card_by_contract.CC_DPD_MAX
FROM previous_keys
LEFT JOIN source_previous_application
    ON previous_keys.SK_ID_PREV = source_previous_application.SK_ID_PREV
LEFT JOIN pos_cash_by_contract
    ON previous_keys.SK_ID_PREV = pos_cash_by_contract.SK_ID_PREV
LEFT JOIN installments_by_contract
    ON previous_keys.SK_ID_PREV = installments_by_contract.SK_ID_PREV
LEFT JOIN credit_card_by_contract
    ON previous_keys.SK_ID_PREV = credit_card_by_contract.SK_ID_PREV
LEFT JOIN dim_customer
    ON previous_keys.SK_ID_CURR = dim_customer.SK_ID_CURR
