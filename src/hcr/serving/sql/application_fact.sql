WITH application_bands AS (
    SELECT
        *,
        CASE
            WHEN AGE_YEARS IS NULL THEN 'Unknown'
            WHEN AGE_YEARS < 25 THEN '<25'
            WHEN AGE_YEARS < 35 THEN '25-34'
            WHEN AGE_YEARS < 45 THEN '35-44'
            WHEN AGE_YEARS < 55 THEN '45-54'
            WHEN AGE_YEARS < 65 THEN '55-64'
            ELSE '65+'
        END AS AGE_BAND,
        CASE
            WHEN AMT_INCOME_TOTAL IS NULL THEN 'Unknown'
            WHEN AMT_INCOME_TOTAL < 50000 THEN '<50K'
            WHEN AMT_INCOME_TOTAL < 100000 THEN '50K-<100K'
            WHEN AMT_INCOME_TOTAL < 150000 THEN '100K-<150K'
            WHEN AMT_INCOME_TOTAL < 250000 THEN '150K-<250K'
            ELSE '250K+'
        END AS INCOME_BAND
    FROM source_application
)
SELECT
    application_bands.SK_ID_CURR,
    dim_customer.CustomerKey,
    dim_occupation.OccupationKey,
    dim_organization.OrgKey,
    dim_education.EducationKey,
    dim_contract_type.ContractKey,
    dim_housing_type.HousingKey,
    dim_family_status.FamilyKey,
    dim_age_band.AgeBandKey,
    dim_income_band.IncomeBandKey,
    dim_risk_band.RiskBandKey,
    application_bands.AMT_CREDIT,
    application_bands.AMT_ANNUITY,
    application_bands.AMT_INCOME_TOTAL,
    application_bands.AMT_GOODS_PRICE,
    application_bands.AMT_CREDIT / NULLIF(application_bands.AMT_INCOME_TOTAL, 0)
        AS CREDIT_INCOME_RATIO,
    application_bands.AMT_ANNUITY / NULLIF(application_bands.AMT_INCOME_TOTAL, 0)
        AS ANNUITY_INCOME_RATIO,
    application_bands.TARGET,
    NULL::DOUBLE AS PD_Predicted,
    NULL::INTEGER AS CreditScore,
    NULL::VARCHAR AS Model_Version,
    NULL::BOOLEAN AS IsHoldout
FROM application_bands
LEFT JOIN dim_customer
    ON application_bands.SK_ID_CURR = dim_customer.SK_ID_CURR
LEFT JOIN dim_occupation
    ON COALESCE(NULLIF(application_bands.OCCUPATION_TYPE, 'Unknown'), 'Unknown')
        = dim_occupation.OCCUPATION_TYPE
LEFT JOIN dim_organization
    ON COALESCE(application_bands.ORGANIZATION_TYPE, 'Unknown')
        = dim_organization.ORGANIZATION_TYPE
LEFT JOIN dim_education
    ON COALESCE(application_bands.NAME_EDUCATION_TYPE, 'Unknown')
        = dim_education.NAME_EDUCATION_TYPE
LEFT JOIN dim_contract_type
    ON COALESCE(application_bands.NAME_CONTRACT_TYPE, 'Unknown')
        = dim_contract_type.NAME_CONTRACT_TYPE
LEFT JOIN dim_housing_type
    ON COALESCE(application_bands.NAME_HOUSING_TYPE, 'Unknown')
        = dim_housing_type.NAME_HOUSING_TYPE
LEFT JOIN dim_family_status
    ON COALESCE(application_bands.NAME_FAMILY_STATUS, 'Unknown')
        = dim_family_status.NAME_FAMILY_STATUS
LEFT JOIN dim_age_band
    ON application_bands.AGE_BAND = dim_age_band.AGE_BAND
LEFT JOIN dim_income_band
    ON application_bands.INCOME_BAND = dim_income_band.INCOME_BAND
CROSS JOIN dim_risk_band
