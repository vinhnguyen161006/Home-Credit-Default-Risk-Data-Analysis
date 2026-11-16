SELECT
    SK_ID_CURR,
    {select_list}
FROM previous_application
LEFT JOIN pos_cash_balance_stage_one USING (SK_ID_PREV)
LEFT JOIN installments_payments_stage_one USING (SK_ID_PREV)
LEFT JOIN credit_card_balance_stage_one USING (SK_ID_PREV)
GROUP BY SK_ID_CURR
