SELECT DISTINCT
    CASE
        WHEN rct.invoice_currency_code <> 'INR'
             THEN
            'EXPWOP'
        WHEN rct.invoice_currency_code = 'INR'
             AND nvl(nvl((select zr.registration_number 
				          From zx_registrations zr
						  Where rct.third_pty_reg_id = zr.registration_id),(Select zr.registration_number -- GSTN Number
							From hz_cust_accounts hca
							,hz_parties hp
							,hz_cust_acct_sites_all hcasa
							,hz_party_sites hps
							,zx_party_tax_profile zptp
							,zx_registrations zr
							WHERE 1=1
							AND hca.party_id=hp.party_id
							AND hca.cust_account_id=hcasa.cust_account_id
							AND hcasa.party_site_id=hps.party_site_id
							AND hps.party_site_id=zptp.party_id
							AND zptp.party_tax_profile_id=zr.party_tax_profile_id
							AND zr.tax_regime_code='GST'
							AND TRUNC(SYSDATE) BETWEEN NVL(zr.effective_from,TRUNC(SYSDATE)) AND NVL(zr.effective_to,TRUNC(SYSDATE))
							AND hcasa.cust_acct_site_id=hcas.cust_acct_site_id
							)),'URP') = 'URP'
             AND (
            SELECT
                tax_amt_tax_curr
            FROM
                zx_lines
            WHERE
                    trx_line_id = rctl.customer_trx_line_id
                AND entity_code = 'TRANSACTIONS'
                AND tax = 'IGST'
        ) = '0' THEN
            'EXPWOP'
        WHEN rct.org_id = 300000003601644 THEN
            'SEZWOP'
        WHEN rct.invoice_currency_code = 'INR'
             AND rct.invoice_currency_code = 'INR'
             AND nvl(nvl((select zr.registration_number 
				          From zx_registrations zr
						  Where rct.third_pty_reg_id = zr.registration_id),(Select zr.registration_number -- GSTN Number
							From hz_cust_accounts hca
							,hz_parties hp
							,hz_cust_acct_sites_all hcasa
							,hz_party_sites hps
							,zx_party_tax_profile zptp
							,zx_registrations zr
							WHERE 1=1
							AND hca.party_id=hp.party_id
							AND hca.cust_account_id=hcasa.cust_account_id
							AND hcasa.party_site_id=hps.party_site_id
							AND hps.party_site_id=zptp.party_id
							AND zptp.party_tax_profile_id=zr.party_tax_profile_id
							AND zr.tax_regime_code='GST'
							AND TRUNC(SYSDATE) BETWEEN NVL(zr.effective_from,TRUNC(SYSDATE)) AND NVL(zr.effective_to,TRUNC(SYSDATE))
							AND hcasa.cust_acct_site_id=hcas.cust_acct_site_id
							)),
									'URP') <> 'URP'
             AND (
            SELECT
                tax_amt_tax_curr
            FROM
                zx_lines
            WHERE
                    trx_line_id = rctl.customer_trx_line_id
                AND entity_code = 'TRANSACTIONS'
                AND tax = 'IGST'
				  ) = '0' THEN
            'SEZWOP'
         WHEN rct.invoice_currency_code = 'INR'
             AND nvl(nvl((select zr.registration_number 
				          From zx_registrations zr
						  Where rct.third_pty_reg_id = zr.registration_id),(Select zr.registration_number -- GSTN Number
							From hz_cust_accounts hca
							,hz_parties hp
							,hz_cust_acct_sites_all hcasa
							,hz_party_sites hps
							,zx_party_tax_profile zptp
							,zx_registrations zr
							WHERE 1=1
							AND hca.party_id=hp.party_id
							AND hca.cust_account_id=hcasa.cust_account_id
							AND hcasa.party_site_id=hps.party_site_id
							AND hps.party_site_id=zptp.party_id
							AND zptp.party_tax_profile_id=zr.party_tax_profile_id
							AND zr.tax_regime_code='GST'
							AND TRUNC(SYSDATE) BETWEEN NVL(zr.effective_from,TRUNC(SYSDATE)) AND NVL(zr.effective_to,TRUNC(SYSDATE))
							AND hcasa.cust_acct_site_id=hcas.cust_acct_site_id
							)),
									'URP') = 'URP'
             AND rct.invoice_currency_code = 'INR' THEN
            'B2C'
        ELSE           -- Else B2B   ( UNREGISTERED and foreign customers is B2B ) 
            'B2B'
    END                                          supply_type,
    decode(nvl(rct.attribute9, 'N') , 'No' , 'N' , 'Yes' , 'Y') "REVERSE_CHARGE",
    decode(rctt.type, 'INV', 'INV', 'DM', 'DBN','CM', 'CRN', rctt.type) "DOCUMENT_TYPE",
    rct.doc_sequence_value                       "DOCUMENT_NUMBER",
		--TO_CHAR(NVL(RCTL.TAX_INVOICE_DATE,RCT.TRX_DATE),'DD/MM/YYYY')	"DOCUMENT_DATE",
    rct.trx_date           "DOCUMENT_DATE",
		--(SELECT DISTINCT TAX_REGISTRATION_NUMBER FROM ZX_LINES where TRX_ID = RCT.CUSTOMER_TRX_ID)	"SELLER_GSTIN",
    nvl((Select zr.registration_number 
	    From zx_registrations zr 
		Where rct.first_pty_reg_id = zr.registration_id),(
		Select hl.attribute2
		From hr_locations hl
	        ,hr_all_organization_units hou
		Where 1=1
		AND hl.location_id = hou.location_id
	    AND hou.organization_id = rct.org_id
	))                                          "SELLER_GSTIN",
    (
        SELECT DISTINCT
            nvl(hoi.attribute1, hou.name)
        FROM
            hr_operating_units          hou,
            hr_organization_information hoi
        WHERE
                1 = 1
            AND hou.organization_id = rct.org_id
            AND hoi.org_information_context = 'FUN_BUSINESS_UNIT'
            AND hou.organization_id = hoi.organization_id
    )                                             "SELLER_LEGALNAME",
    (
        SELECT
            name
        FROM
            hr_operating_units
        WHERE
            organization_id = rct.org_id
    )                                             "SELLER_TRADENAME",
    CASE
        WHEN rctt.type = 'CM' THEN
            (
                SELECT DISTINCT
                    hl.address1
                FROM
                    financials_system_params_all a,
                    hr_operating_units           b,
                    gl_code_combinations         c,
                    gl_ledgers                   d,
                    gl_sets_of_books             e,
                    xle_entity_profiles          xep,
                    xle_etb_profiles             xet,
                    xle_registrations            xr,
                    xle_registrations            xr_1,
                    hz_locations                 hl
                WHERE
                        1 = 1
                    AND a.org_id = rct.org_id
                    AND a.org_id = b.organization_id
                    AND a.accts_pay_code_combination_id = c.code_combination_id
                    AND b.set_of_books_id = e.set_of_books_id
                    AND xep.legal_entity_id = xet.legal_entity_id
                    AND xet.establishment_id = xr.source_id
                    AND xet.legal_entity_id = xr_1.source_id
                    AND xr_1.source_id = b.default_legal_context_id
                    AND xr.location_id = hl.location_id
                    AND xr.effective_to IS NULL
                    AND xet.effective_to IS NULL
                    AND xr.registration_number = nvl((
                        SELECT DISTINCT
                            tax_registration_number
                        FROM
                            zx_lines
                        WHERE
                                trx_id = rct.customer_trx_id
                            AND application_id = 222
                    ),(
                        SELECT DISTINCT
                            xr.registration_number
                        FROM
                            financials_system_params_all a, hr_operating_units           b, gl_code_combinations         c, gl_ledgers                   d
                            ,
                            gl_sets_of_books             e, xle_entity_profiles          xep, xle_etb_profiles             xet, xle_registrations            xr
                            , xle_registrations            xr_1,
                            hz_locations                 hl
                        WHERE
                                1 = 1
                            AND a.org_id = rct.org_id
                            AND a.org_id = b.organization_id
                            AND a.accts_pay_code_combination_id = c.code_combination_id
                            AND b.set_of_books_id = e.set_of_books_id
                            AND xep.legal_entity_id = xet.legal_entity_id
                            AND xet.establishment_id = xr.source_id
                            AND xet.legal_entity_id = xr_1.source_id
                            AND xr_1.source_id = b.default_legal_context_id
                            AND xr.location_id = hl.location_id
                            AND xr.effective_to IS NULL
                            AND xet.effective_to IS NULL
                            AND xr.registration_number LIKE '27%'
                            AND xr.registration_id = 300000004438899
                    ))
            )
        ELSE
            nvl((
                SELECT DISTINCT
                    c.address1
                FROM
                    zx_lines             zl, zx_party_tax_profile a, zx_registrations     b, hz_parties           c
                WHERE
                        1 = 1
                    AND zl.trx_id = rct.customer_trx_id
                    AND zl.tax_registration_id = b.registration_id
                    AND a.party_tax_profile_id = b.party_tax_profile_id
                    AND a.party_id = c.party_id
                    AND b.effective_to IS NULL
                    AND b.tax_regime_code = 'GST'
                    AND entity_code = 'TRANSACTIONS'
                    AND a.party_type_code = 'LEGAL_ESTABLISHMENT'
            ),(
                SELECT DISTINCT
                    hl.address1
                FROM
                    financials_system_params_all a,
                    hr_operating_units           b, gl_code_combinations         c, gl_ledgers                   d, gl_sets_of_books             e
                    , xle_entity_profiles          xep,
                    xle_etb_profiles             xet, xle_registrations            xr, xle_registrations            xr_1, hz_locations                 hl
                WHERE
                        1 = 1
                    AND a.org_id = rct.org_id
                    AND a.org_id = b.organization_id
                    AND a.accts_pay_code_combination_id = c.code_combination_id
                    AND b.set_of_books_id = e.set_of_books_id
                    AND xep.legal_entity_id = xet.legal_entity_id
                    AND xet.establishment_id = xr.source_id
                    AND xet.legal_entity_id = xr_1.source_id
                    AND xr_1.source_id = b.default_legal_context_id
                    AND xr.location_id = hl.location_id
                    AND xr.effective_to IS NULL
                    AND xet.effective_to IS NULL
                    AND xr.registration_number LIKE '27%'
                    AND xr.registration_id = 300000004438899
            ))
    END                                           "SELLER_ADDRESS1",
    CASE
        WHEN rctt.type = 'CM' THEN
            (
                SELECT DISTINCT
                    hl.address2
                FROM
                    financials_system_params_all a,
                    hr_operating_units           b,
                    gl_code_combinations         c,
                    gl_ledgers                   d,
                    gl_sets_of_books             e,
                    xle_entity_profiles          xep,
                    xle_etb_profiles             xet,
                    xle_registrations            xr,
                    xle_registrations            xr_1,
                    hz_locations                 hl
                WHERE
                        1 = 1
                    AND a.org_id = rct.org_id
                    AND a.org_id = b.organization_id
                    AND a.accts_pay_code_combination_id = c.code_combination_id
                    AND b.set_of_books_id = e.set_of_books_id
                    AND xep.legal_entity_id = xet.legal_entity_id
                    AND xet.establishment_id = xr.source_id
                    AND xet.legal_entity_id = xr_1.source_id
                    AND xr_1.source_id = b.default_legal_context_id
                    AND xr.location_id = hl.location_id
                    AND xr.effective_to IS NULL
                    AND xet.effective_to IS NULL
                    AND xr.registration_number = nvl((
                        SELECT DISTINCT
                            tax_registration_number
                        FROM
                            zx_lines
                        WHERE
                                trx_id = rct.customer_trx_id
                            AND application_id = 222
                    ),(
                        SELECT DISTINCT
                            xr.registration_number
                        FROM
                            financials_system_params_all a, hr_operating_units           b, gl_code_combinations         c, gl_ledgers                   d
                            ,
                            gl_sets_of_books             e, xle_entity_profiles          xep, xle_etb_profiles             xet, xle_registrations            xr
                            , xle_registrations            xr_1,
                            hz_locations                 hl
                        WHERE
                                1 = 1
                            AND a.org_id = rct.org_id
                            AND a.org_id = b.organization_id
                            AND a.accts_pay_code_combination_id = c.code_combination_id
                            AND b.set_of_books_id = e.set_of_books_id
                            AND xep.legal_entity_id = xet.legal_entity_id
                            AND xet.establishment_id = xr.source_id
                            AND xet.legal_entity_id = xr_1.source_id
                            AND xr_1.source_id = b.default_legal_context_id
                            AND xr.location_id = hl.location_id
                            AND xr.effective_to IS NULL
                            AND xet.effective_to IS NULL
                            AND xr.registration_number LIKE '27%'
                            AND xr.registration_id = 300000004438899
                    ))
            )
        ELSE
            nvl((
                SELECT DISTINCT
                    c.address2
                FROM
                    zx_lines             zl, zx_party_tax_profile a, zx_registrations     b, hz_parties           c
                WHERE
                        1 = 1
                    AND zl.trx_id = rct.customer_trx_id
                    AND zl.tax_registration_id = b.registration_id
                    AND a.party_tax_profile_id = b.party_tax_profile_id
                    AND a.party_id = c.party_id
                    AND b.effective_to IS NULL
                    AND b.tax_regime_code = 'GST'
                    AND entity_code = 'TRANSACTIONS'
                    AND a.party_type_code = 'LEGAL_ESTABLISHMENT'
            ),(
                SELECT DISTINCT
                    hl.address2
                FROM
                    financials_system_params_all a,
                    hr_operating_units           b, gl_code_combinations         c, gl_ledgers                   d, gl_sets_of_books             e
                    , xle_entity_profiles          xep,
                    xle_etb_profiles             xet, xle_registrations            xr, xle_registrations            xr_1, hz_locations                 hl
                WHERE
                        1 = 1
                    AND a.org_id = rct.org_id
                    AND a.org_id = b.organization_id
                    AND a.accts_pay_code_combination_id = c.code_combination_id
                    AND b.set_of_books_id = e.set_of_books_id
                    AND xep.legal_entity_id = xet.legal_entity_id
                    AND xet.establishment_id = xr.source_id
                    AND xet.legal_entity_id = xr_1.source_id
                    AND xr_1.source_id = b.default_legal_context_id
                    AND xr.location_id = hl.location_id
                    AND xr.effective_to IS NULL
                    AND xet.effective_to IS NULL
                    AND xr.registration_number LIKE '27%'
                    AND xr.registration_id = 300000004438899
            ))
    END                                           "SELLER_ADDRESS2",
    CASE
        WHEN rctt.type = 'CM' THEN
            (
                SELECT DISTINCT
                    hl.city
                FROM
                    financials_system_params_all a,
                    hr_operating_units           b,
                    gl_code_combinations         c,
                    gl_ledgers                   d,
                    gl_sets_of_books             e,
                    xle_entity_profiles          xep,
                    xle_etb_profiles             xet,
                    xle_registrations            xr,
                    xle_registrations            xr_1,
                    hz_locations                 hl
                WHERE
                        1 = 1
                    AND a.org_id = rct.org_id
                    AND a.org_id = b.organization_id
                    AND a.accts_pay_code_combination_id = c.code_combination_id
                    AND b.set_of_books_id = e.set_of_books_id
                    AND xep.legal_entity_id = xet.legal_entity_id
                    AND xet.establishment_id = xr.source_id
                    AND xet.legal_entity_id = xr_1.source_id
                    AND xr_1.source_id = b.default_legal_context_id
                    AND xr.location_id = hl.location_id
                    AND xr.effective_to IS NULL
                    AND xet.effective_to IS NULL
                    AND xr.registration_number = nvl((
                        SELECT DISTINCT
                            tax_registration_number
                        FROM
                            zx_lines
                        WHERE
                                trx_id = rct.customer_trx_id
                            AND application_id = 222
                    ),(
                        SELECT DISTINCT
                            xr.registration_number
                        FROM
                            financials_system_params_all a, hr_operating_units           b, gl_code_combinations         c, gl_ledgers                   d
                            ,
                            gl_sets_of_books             e, xle_entity_profiles          xep, xle_etb_profiles             xet, xle_registrations            xr
                            , xle_registrations            xr_1,
                            hz_locations                 hl
                        WHERE
                                1 = 1
                            AND a.org_id = rct.org_id
                            AND a.org_id = b.organization_id
                            AND a.accts_pay_code_combination_id = c.code_combination_id
                            AND b.set_of_books_id = e.set_of_books_id
                            AND xep.legal_entity_id = xet.legal_entity_id
                            AND xet.establishment_id = xr.source_id
                            AND xet.legal_entity_id = xr_1.source_id
                            AND xr_1.source_id = b.default_legal_context_id
                            AND xr.location_id = hl.location_id
                            AND xr.effective_to IS NULL
                            AND xet.effective_to IS NULL
                            AND xr.registration_number LIKE '27%'
                            AND xr.registration_id = 300000004438899
                    ))
            )
        ELSE
            nvl((
                SELECT DISTINCT
                    c.city
                FROM
                    zx_lines             zl, zx_party_tax_profile a, zx_registrations     b, hz_parties           c
                WHERE
                        1 = 1
                    AND zl.trx_id = rct.customer_trx_id
                    AND zl.tax_registration_id = b.registration_id
                    AND a.party_tax_profile_id = b.party_tax_profile_id
                    AND a.party_id = c.party_id
                    AND b.effective_to IS NULL
                    AND b.tax_regime_code = 'GST'
                    AND entity_code = 'TRANSACTIONS'
                    AND a.party_type_code = 'LEGAL_ESTABLISHMENT'
            ),(
                SELECT DISTINCT
                    hl.city
                FROM
                    financials_system_params_all a,
                    hr_operating_units           b, gl_code_combinations         c, gl_ledgers                   d, gl_sets_of_books             e
                    , xle_entity_profiles          xep,
                    xle_etb_profiles             xet, xle_registrations            xr, xle_registrations            xr_1, hz_locations                 hl
                WHERE
                        1 = 1
                    AND a.org_id = rct.org_id
                    AND a.org_id = b.organization_id
                    AND a.accts_pay_code_combination_id = c.code_combination_id
                    AND b.set_of_books_id = e.set_of_books_id
                    AND xep.legal_entity_id = xet.legal_entity_id
                    AND xet.establishment_id = xr.source_id
                    AND xet.legal_entity_id = xr_1.source_id
                    AND xr_1.source_id = b.default_legal_context_id
                    AND xr.location_id = hl.location_id
                    AND xr.effective_to IS NULL
                    AND xet.effective_to IS NULL
                    AND xr.registration_number LIKE '27%'
                    AND xr.registration_id = 300000004438899
            ))
    END                                           "SELLER_CITY",
    CASE
        WHEN rctt.type = 'CM' THEN
            (
                SELECT DISTINCT
                    hl.postal_code
                FROM
                    financials_system_params_all a,
                    hr_operating_units           b,
                    gl_code_combinations         c,
                    gl_ledgers                   d,
                    gl_sets_of_books             e,
                    xle_entity_profiles          xep,
                    xle_etb_profiles             xet,
                    xle_registrations            xr,
                    xle_registrations            xr_1,
                    hz_locations                 hl
                WHERE
                        1 = 1
                    AND a.org_id = rct.org_id
                    AND a.org_id = b.organization_id
                    AND a.accts_pay_code_combination_id = c.code_combination_id
                    AND b.set_of_books_id = e.set_of_books_id
                    AND xep.legal_entity_id = xet.legal_entity_id
                    AND xet.establishment_id = xr.source_id
                    AND xet.legal_entity_id = xr_1.source_id
                    AND xr_1.source_id = b.default_legal_context_id
                    AND xr.location_id = hl.location_id
                    AND xr.effective_to IS NULL
                    AND xet.effective_to IS NULL
                    AND xr.registration_number = nvl((
                        SELECT DISTINCT
                            tax_registration_number
                        FROM
                            zx_lines
                        WHERE
                                trx_id = rct.customer_trx_id
                            AND application_id = 222
                    ),(
                        SELECT DISTINCT
                            xr.registration_number
                        FROM
                            financials_system_params_all a, hr_operating_units           b, gl_code_combinations         c, gl_ledgers                   d
                            ,
                            gl_sets_of_books             e, xle_entity_profiles          xep, xle_etb_profiles             xet, xle_registrations            xr
                            , xle_registrations            xr_1,
                            hz_locations                 hl
                        WHERE
                                1 = 1
                            AND a.org_id = rct.org_id
                            AND a.org_id = b.organization_id
                            AND a.accts_pay_code_combination_id = c.code_combination_id
                            AND b.set_of_books_id = e.set_of_books_id
                            AND xep.legal_entity_id = xet.legal_entity_id
                            AND xet.establishment_id = xr.source_id
                            AND xet.legal_entity_id = xr_1.source_id
                            AND xr_1.source_id = b.default_legal_context_id
                            AND xr.location_id = hl.location_id
                            AND xr.effective_to IS NULL
                            AND xet.effective_to IS NULL
                            AND xr.registration_number LIKE '27%'
                            AND xr.registration_id = 300000004438899
                    ))
            )
        ELSE
            nvl((
                SELECT DISTINCT
                    c.postal_code
                FROM
                    zx_lines             zl, zx_party_tax_profile a, zx_registrations     b, hz_parties           c
                WHERE
                        1 = 1
                    AND zl.trx_id = rct.customer_trx_id
                    AND zl.tax_registration_id = b.registration_id
                    AND a.party_tax_profile_id = b.party_tax_profile_id
                    AND a.party_id = c.party_id
                    AND b.effective_to IS NULL
                    AND b.tax_regime_code = 'GST'
                    AND entity_code = 'TRANSACTIONS'
                    AND a.party_type_code = 'LEGAL_ESTABLISHMENT'
            ),(
                SELECT DISTINCT
                    hl.postal_code
                FROM
                    financials_system_params_all a,
                    hr_operating_units           b, gl_code_combinations         c, gl_ledgers                   d, gl_sets_of_books             e
                    , xle_entity_profiles          xep,
                    xle_etb_profiles             xet, xle_registrations            xr, xle_registrations            xr_1, hz_locations                 hl
                WHERE
                        1 = 1
                    AND a.org_id = rct.org_id
                    AND a.org_id = b.organization_id
                    AND a.accts_pay_code_combination_id = c.code_combination_id
                    AND b.set_of_books_id = e.set_of_books_id
                    AND xep.legal_entity_id = xet.legal_entity_id
                    AND xet.establishment_id = xr.source_id
                    AND xet.legal_entity_id = xr_1.source_id
                    AND xr_1.source_id = b.default_legal_context_id
                    AND xr.location_id = hl.location_id
                    AND xr.effective_to IS NULL
                    AND xet.effective_to IS NULL
                    AND xr.registration_number LIKE '27%'
                    AND xr.registration_id = 300000004438899
            ))
    END                                           "SELLER_PINCODE",
    nvl(nvl((select zr.registration_number 
				          From zx_registrations zr
						  Where rct.third_pty_reg_id = zr.registration_id),(Select zr.registration_number -- GSTN Number
From hz_cust_accounts hca
,hz_parties hp
,hz_cust_acct_sites_all hcasa
,hz_party_sites hps
,zx_party_tax_profile zptp
,zx_registrations zr
WHERE 1=1
AND hca.party_id=hp.party_id
AND hca.cust_account_id=hcasa.cust_account_id
AND hcasa.party_site_id=hps.party_site_id
AND hps.party_site_id=zptp.party_id
AND zptp.party_tax_profile_id=zr.party_tax_profile_id
AND zr.tax_regime_code='GST'
AND TRUNC(SYSDATE) BETWEEN NVL(zr.effective_from,TRUNC(SYSDATE)) AND NVL(zr.effective_to,TRUNC(SYSDATE))
AND hcasa.cust_acct_site_id=hcas.cust_acct_site_id
)),
        'URP')                                    "BUYER_GSTIN",
    substr(hp.party_name, 1, 100)                 "BUYER_LEGALNAME",
    substr(hp.party_name, 1, 100)                 "BUYER_TRADENAME",
    hz.address1                                   "BUYER_ADDRESS1",
    hz.address2                                   "BUYER_ADDRESS2",
    (Select SUBSTR(zr.registration_number,1,2) -- GSTN Number
From hz_cust_accounts hca
,hz_parties hp
,hz_cust_acct_sites_all hcasa
,hz_party_sites hps
,zx_party_tax_profile zptp
,zx_registrations zr
WHERE 1=1
AND hca.party_id=hp.party_id
AND hca.cust_account_id=hcasa.cust_account_id
AND hcasa.party_site_id=hps.party_site_id
AND hps.party_site_id=zptp.party_id
AND zptp.party_tax_profile_id=zr.party_tax_profile_id
AND zr.tax_regime_code='GST'
AND TRUNC(SYSDATE) BETWEEN NVL(zr.effective_from,TRUNC(SYSDATE)) AND NVL(zr.effective_to,TRUNC(SYSDATE))
AND hcasa.cust_acct_site_id=hcas.cust_acct_site_id
)                                      "BUYER_POS", --made changes to capture the data
    hz.city                                       "BUYER_CITY", --made changes to capture the data
   hz.postal_code                                          "BUYER_PINCODE", --made changes to capture the data
    (Select SUBSTR(zr.registration_number,1,2) -- GSTN Number
From hz_cust_accounts hca
,hz_parties hp
,hz_cust_acct_sites_all hcasa
,hz_party_sites hps
,zx_party_tax_profile zptp
,zx_registrations zr
WHERE 1=1
AND hca.party_id=hp.party_id
AND hca.cust_account_id=hcasa.cust_account_id
AND hcasa.party_site_id=hps.party_site_id
AND hps.party_site_id=zptp.party_id
AND zptp.party_tax_profile_id=zr.party_tax_profile_id
AND zr.tax_regime_code='GST'
AND TRUNC(SYSDATE) BETWEEN NVL(zr.effective_from,TRUNC(SYSDATE)) AND NVL(zr.effective_to,TRUNC(SYSDATE))
AND hcasa.cust_acct_site_id=hcas.cust_acct_site_id
)                                           "BUYER_STATECODE",--made changes to capture the data
    nvl(nvl((select zr.registration_number 
				          From zx_registrations zr
						  Where rct.third_pty_reg_id = zr.registration_id),(
		SELECT zr.registration_number 
		FROM hz_locations hz,
			hz_party_sites hps
			,zx_party_tax_profile zptp
            ,zx_registrations zr
		    WHERE hps.location_id = hz.location_id
			AND hps.party_id = rct.ship_to_party_id
			AND hps.party_site_id = rct.ship_to_party_address_id
			AND hps.party_site_id=zptp.party_id
            AND zptp.party_tax_profile_id=zr.party_tax_profile_id
            AND zr.tax_regime_code='GST'
            AND TRUNC(SYSDATE) BETWEEN NVL(zr.effective_from,TRUNC(SYSDATE)) AND NVL(zr.effective_to,TRUNC(SYSDATE))
		)),
        'URP')                                              "SHIPTO_GSTIN",--made changes to capture the data
    (
		SELECT hp.party_name Ship_to_party
		FROM hz_locations hz,
			hz_party_sites hps,
			hz_parties hp
		WHERE hps.location_id = hz.location_id
			AND hps.party_id = rct.ship_to_party_id
			AND hp.party_id = hps.party_id
			AND hps.party_site_id = rct.ship_to_party_address_id
		)                                             "SHIPTO_LEGALNAME",--made changes to capture the data
    (
		SELECT hz.address1 STP_Add1
		FROM hz_locations hz,
			hz_party_sites hps
		WHERE hps.location_id = hz.location_id
			AND hps.party_id = rct.ship_to_party_id
			AND hps.party_site_id = rct.ship_to_party_address_id
		)                                             "SHIPTO_ADDRESS1",--made changes to capture the data
    (
		SELECT hz.address2 Ship_to_Add2
		FROM hz_locations hz,
			hz_party_sites hps
		WHERE hps.location_id = hz.location_id
			AND hps.party_id = rct.ship_to_party_id
			AND hps.party_site_id = rct.ship_to_party_address_id
		)                                             "SHIPTO_ADDRESS2", --made changes to capture the data
    (
		SELECT hz.city Ship_to_Loc
		FROM hz_locations hz,
			hz_party_sites hps
		WHERE hps.location_id = hz.location_id
			AND hps.party_id = rct.ship_to_party_id
			AND hps.party_site_id = rct.ship_to_party_address_id
		)                                             "SHIPTO_CITY", --made changes to capture the data
    (
		SELECT
			(CASE
				WHEN hz.country <> 'IN'
				THEN '999999'
				ELSE hz.postal_code
				END)
		FROM hz_locations hz,
			hz_party_sites hps
		WHERE hps.location_id = hz.location_id
			AND hps.party_id = rct.ship_to_party_id
			AND hps.party_site_id = rct.ship_to_party_address_id
		)                                            "SHIPTO_PINCODE",
    rctl.line_number                              "SERIAL_NUMBER",
    substr(rctl.description, 1, 100)              "PRODUCT_DESCRIPTION",
    decode(
        nvl(rctl.attribute12, '0'),
        '0',
        'N',
        'Y'
    )                                             "IS_SERVICE",
    /*(
		SELECT LISTAGG(DISTINCT esib.attribute1, ',') WITHIN
		GROUP (
				ORDER BY esib.inventory_item_id
				) SAC_HSN
		FROM egp_system_items_b esib
		WHERE esib.inventory_item_id = rctl.inventory_item_id
			AND esib.ORGANIZATION_ID = esib.MASTER_ORG_ID
		) "HSN_CODE",  */
    '8314'  "HSN_CODE",
    nvl(
        abs(rctl.quantity_invoiced),
        1
    )                                             "QUANTITY",
    decode(
        nvl(rctl.uom_code, 'NOS'),
        'KG',
        'KGS',
        'GM',
        'GMS',
        'NUM',
        'NOS',
        nvl(rctl.uom_code, 'NOS')
    )                                             "UNIT",
    decode(rct.invoice_currency_code,
           'INR',
           abs(rctl.unit_selling_price),
           (
        SELECT
            SUM(abs(rctdist1.acctd_amount))
        FROM
            ra_cust_trx_line_gl_dist_all rctdist1
        WHERE
                1 = 1
            AND rctdist1.customer_trx_id = rct.customer_trx_id
            AND rctdist1.customer_trx_line_id = rctl.customer_trx_line_id
            AND rctdist1.account_class = 'REV'
    ))                                            "UNIT_PRICE",
    (
		SELECT round(sum(rctl1.EXTENDED_AMOUNT))
		FROM ra_customer_trx_lines_all rctl1
		WHERE 1 = 1
			AND rctl1.customer_trx_id = rct.customer_trx_id
	)                                          "TOTAL_AMOUNT",
    0                                             "DISCOUNT",
    ( nvl(
        abs(rctl.quantity_invoiced),
        1
    ) * decode(rct.invoice_currency_code,
               'INR',
               abs(rctl.unit_selling_price),
               (
                SELECT
                    SUM(abs(rctdist1.acctd_amount))
                FROM
                    ra_cust_trx_line_gl_dist_all rctdist1
                WHERE
                        1 = 1
                    AND rctdist1.customer_trx_id = rct.customer_trx_id
                    AND rctdist1.customer_trx_line_id = rctl.customer_trx_line_id
                    AND rctdist1.account_class = 'REV'
            )) )                                          "ASSESSABLE_AMOUNT",
    NVL((
			SELECT tl.tax_rate
			FROM ra_customer_trx_lines_all rctl1
				,zx_lines tl
				,ZX_TAXES_B tb
			WHERE 1 = 1
				AND rctl1.LINK_TO_CUST_TRX_LINE_ID = rctl.CUSTOMER_TRX_LINE_ID
				AND rctl1.tax_line_id = tl.tax_line_id
				AND tl.tax_id = tb.tax_id
				AND tb.TAX = 'CGST'
			), 0) + NVL((
			SELECT tl.tax_rate
			FROM ra_customer_trx_lines_all rctl1
				,zx_lines tl
				,ZX_TAXES_B tb
			WHERE 1 = 1
				AND rctl1.LINK_TO_CUST_TRX_LINE_ID = rctl.CUSTOMER_TRX_LINE_ID
				AND rctl1.tax_line_id = tl.tax_line_id
				AND tl.tax_id = tb.tax_id
				AND tb.TAX = 'SGST'
			), 0) + NVL((
			SELECT tl.tax_rate
			FROM ra_customer_trx_lines_all rctl1
				,zx_lines tl
				,ZX_TAXES_B tb
			WHERE 1 = 1
				AND rctl1.LINK_TO_CUST_TRX_LINE_ID = rctl.CUSTOMER_TRX_LINE_ID
				AND rctl1.tax_line_id = tl.tax_line_id
				AND tl.tax_id = tb.tax_id
				AND tb.TAX = 'IGST'
			), 0)                                      "GSTRATE",
   NVL((
			SELECT tl.tax_rate
			FROM ra_customer_trx_lines_all rctl1
				,zx_lines tl
				,ZX_TAXES_B tb
			WHERE 1 = 1
				AND rctl1.LINK_TO_CUST_TRX_LINE_ID = rctl.CUSTOMER_TRX_LINE_ID
				AND rctl1.tax_line_id = tl.tax_line_id
				AND tl.tax_id = tb.tax_id
				AND tb.TAX = 'CGST'
			), 0)                                         "CGSTRATE",
    NVL((
			SELECT tl.tax_rate
			FROM ra_customer_trx_lines_all rctl1
				,zx_lines tl
				,ZX_TAXES_B tb
			WHERE 1 = 1
				AND rctl1.LINK_TO_CUST_TRX_LINE_ID = rctl.CUSTOMER_TRX_LINE_ID
				AND rctl1.tax_line_id = tl.tax_line_id
				AND tl.tax_id = tb.tax_id
				AND tb.TAX = 'SGST'
			), 0)                                         "SGSTRATE",
    NVL((
			SELECT tl.tax_rate
			FROM ra_customer_trx_lines_all rctl1
				,zx_lines tl
				,ZX_TAXES_B tb
			WHERE 1 = 1
				AND rctl1.LINK_TO_CUST_TRX_LINE_ID = rctl.CUSTOMER_TRX_LINE_ID
				AND rctl1.tax_line_id = tl.tax_line_id
				AND tl.tax_id = tb.tax_id
				AND tb.TAX = 'IGST'
			), 0)                                         "IGSTRATE",
   0                                        "CESSRATE",
    NVL((
			SELECT tl.TAX_AMT
			FROM ra_customer_trx_lines_all rctl1
				,zx_lines tl
				,ZX_TAXES_B tb
			WHERE 1 = 1
				AND rctl1.LINK_TO_CUST_TRX_LINE_ID = rctl.CUSTOMER_TRX_LINE_ID
				AND rctl1.tax_line_id = tl.tax_line_id
				AND tl.tax_id = tb.tax_id
				AND tb.TAX = 'CGST'
			), 0)                               "CGST_AMT",
    NVL((
			SELECT tl.TAX_AMT
			FROM ra_customer_trx_lines_all rctl1
				,zx_lines tl
				,ZX_TAXES_B tb
			WHERE 1 = 1
				AND rctl1.LINK_TO_CUST_TRX_LINE_ID = rctl.CUSTOMER_TRX_LINE_ID
				AND rctl1.tax_line_id = tl.tax_line_id
				AND tl.tax_id = tb.tax_id
				AND tb.TAX = 'SGST'
			), 0)                                "SGST_AMT",
    NVL((
			SELECT tl.TAX_AMT
			FROM ra_customer_trx_lines_all rctl1
				,zx_lines tl
				,ZX_TAXES_B tb
			WHERE 1 = 1
				AND rctl1.LINK_TO_CUST_TRX_LINE_ID = rctl.CUSTOMER_TRX_LINE_ID
				AND rctl1.tax_line_id = tl.tax_line_id
				AND tl.tax_id = tb.tax_id
				AND tb.TAX = 'IGST'
			), 0)                                "IGST_AMT",
    0                                "CESS_AMT",
    decode(rctl.line_number,
           '1',
           nvl((
        SELECT
            SUM(decode(rct1.invoice_currency_code,
                       'INR',
                       abs(rctl1.unit_selling_price),
                       abs(rctdist1.acctd_amount)))
        FROM
            gl_code_combinations         gcc1,
            ra_customer_trx_all          rct1,
            ra_customer_trx_lines_all    rctl1,
            ra_cust_trx_line_gl_dist_all rctdist1
        WHERE
                1 = 1
            AND rctdist1.account_class = 'REV'
            AND gcc1.segment3 = '248662'
            AND rctdist1.customer_trx_id = rct.customer_trx_id
            AND rct1.customer_trx_id = rctl1.customer_trx_id
            AND rctl1.customer_trx_id = rctdist1.customer_trx_id
            AND rctl1.customer_trx_line_id = rctdist1.customer_trx_line_id
            AND gcc1.code_combination_id = rctdist1.code_combination_id
    ),
               0),
           0)                                     "OTHER_CHARGES",
    rctl.EXTENDED_AMOUNT + (
		SELECT SUM(tl.TAX_AMT)
		FROM ra_customer_trx_lines_all rctl1
			,zx_lines tl
			,ZX_TAXES_B tb
		WHERE 1 = 1
			AND rctl1.LINK_TO_CUST_TRX_LINE_ID = rctl.CUSTOMER_TRX_LINE_ID
			AND rctl1.tax_line_id = tl.tax_line_id
			AND tl.tax_id = tb.tax_id --and tb.TAX='IGST'
		)                                       "TOTAL_ITEM_VALUE",
    ( decode(rct.invoice_currency_code,
             'INR',
             ((
              SELECT
                  SUM(nvl(
                      abs(rctl1.quantity_invoiced),
                      1
                  ) * abs(rctl1.unit_selling_price))
              FROM
                  ra_customer_trx_all       rct1,
                  ra_customer_trx_lines_all rctl1
              WHERE
                      1 = 1
                  AND rctl1.line_type = 'LINE'
                  AND rctl1.customer_trx_id = rct.customer_trx_id
                  AND rct1.customer_trx_id = rctl1.customer_trx_id
                  AND(rctl1.customer_trx_id, rctl1.customer_trx_line_id) NOT IN(
                      SELECT
                          rctdist1.customer_trx_id, rctdist1.customer_trx_line_id
                      FROM
                          gl_code_combinations         gcc1, ra_cust_trx_line_gl_dist_all rctdist1
                      WHERE
                              1 = 1
                          AND gcc1.code_combination_id = rctdist1.code_combination_id
                          AND gcc1.segment3 = '248662'
                  )
                  AND(rctl1.customer_trx_id, rctl1.line_number) NOT IN(
                      SELECT
                          rctl1.customer_trx_id, rctl1.line_number
                      FROM
                          ra_customer_trx_all       rct1, ra_customer_trx_lines_all rctl1, ra_cust_trx_types_all     rctt1
                      WHERE
                              rct1.customer_trx_id = rct.customer_trx_id
                          AND rct1.customer_trx_id = rctl1.customer_trx_id
                          AND rctt1.cust_trx_type_seq_id = rct1.cust_trx_type_seq_id
                          AND rct1.org_id = rctt1.org_id
                          AND rctt1.type = 'INV'
                          AND rctt1.name NOT LIKE '%MPA%'
                          AND nvl(rctl1.quantity_invoiced, 1) < 0
                  )
          )),
             nvl((
              SELECT DISTINCT
                  SUM(round(
                      abs(taxable_amt_funcl_curr),
                      2
                  ))
              FROM
                  zx_lines zl
              WHERE
                      1 = 1
                  AND zl.trx_id = rct.customer_trx_id
					-- AND TRX_LINE_NUMBER=rctl.LINE_NUMBER
                  AND entity_code = 'TRANSACTIONS'
          ),
                 (
              SELECT DISTINCT
                  (round(
                      abs(taxable_amt),
                      2
                  ))
              FROM
                  zx_lines zl
              WHERE
                      1 = 1
                  AND zl.trx_id = rct.customer_trx_id
					-- AND TRX_LINE_NUMBER=rctl.LINE_NUMBER
                  AND entity_code = 'TRANSACTIONS'
          ))) )                                         "TOTAL_ASSESSABLE_VALUE",
    decode(rct.invoice_currency_code,
           'INR',
           (
        SELECT
            nvl(
                sum(abs(tax_amt_tax_curr)),
                0
            )
        FROM
            zx_lines
        WHERE
                trx_id = rct.customer_trx_id
            AND entity_code = 'TRANSACTIONS'
            AND tax IN('CGST', 'CGST RCM')
    ),
           (
        SELECT
            nvl(
                sum(abs(tax_amt_funcl_curr)),
                0
            )
        FROM
            zx_lines
        WHERE
                trx_id = rct.customer_trx_id
            AND entity_code = 'TRANSACTIONS'
            AND tax IN('CGST', 'CGST RCM')
    ))                                            "TOTAL_CGST_VALUE",
    decode(rct.invoice_currency_code,
           'INR',
           (
        SELECT
            nvl(
                sum(abs(tax_amt_tax_curr)),
                0
            )
        FROM
            zx_lines
        WHERE
                trx_id = rct.customer_trx_id
            AND entity_code = 'TRANSACTIONS'
            AND tax IN('SGST', 'SGST RCM', 'UTGST', 'UTGST RCM')
    ),
           (
        SELECT
            nvl(
                sum(abs(tax_amt_funcl_curr)),
                0
            )
        FROM
            zx_lines
        WHERE
                trx_id = rct.customer_trx_id
            AND entity_code = 'TRANSACTIONS'
            AND tax IN('SGST', 'SGST RCM', 'UTGST', 'UTGST RCM')
    ))                                            "TOTAL_SGST_VALUE",
    decode(rct.invoice_currency_code,
           'INR',
           (
        SELECT
            nvl(
                sum(abs(tax_amt_tax_curr)),
                0
            )
        FROM
            zx_lines
        WHERE
                trx_id = rct.customer_trx_id
            AND entity_code = 'TRANSACTIONS'
            AND tax IN('IGST', 'IGST RCM')
    ),
           (
        SELECT
            nvl(
                sum(abs(tax_amt_funcl_curr)),
                0
            )
        FROM
            zx_lines
        WHERE
                trx_id = rct.customer_trx_id
            AND entity_code = 'TRANSACTIONS'
            AND tax IN('IGST', 'IGST RCM')
    ))                                            "TOTAL_IGST_VALUE",
    0                                            "TOTAL_CESS_VALUE",
    nvl((
        SELECT
            SUM(decode(rct1.invoice_currency_code,
                       'INR',
                       abs(rctl1.unit_selling_price),
                       abs(rctdist1.acctd_amount)))
        FROM
            gl_code_combinations         gcc1,
            ra_customer_trx_all          rct1,
            ra_customer_trx_lines_all    rctl1,
            ra_cust_trx_line_gl_dist_all rctdist1
        WHERE
                1 = 1
            AND rctdist1.customer_trx_id = rct.customer_trx_id
            AND rct1.customer_trx_id = rctl1.customer_trx_id
            AND rctl1.customer_trx_id = rctdist1.customer_trx_id
            AND rctl1.customer_trx_line_id = rctdist1.customer_trx_line_id
            AND gcc1.code_combination_id = rctdist1.code_combination_id
            AND rctdist1.account_class = 'REV'
            AND gcc1.segment3 = '248662'
    ),
        0)                                        "OTHER_CHARGES_IF_ANY",
    round((
			NVL((
					SELECT sum(DECODE(dma.ADJUSTMENT_TYPE_CODE, 'DISCOUNT_AMOUNT', dma.ADJUSTMENT_AMOUNT, 'DISCOUNT_PERCENT', dma.ADJUSTMENT_AMOUNT / 100 * (
									SELECT DISTINCT dma1.ADJUSTMENT_AMOUNT
									FROM DOO_MANUAL_PRICE_ADJUSTMENTS dma1
										,doo_fulfill_lines_all dfl1
									WHERE 1 = 1
										AND dma1.PARENT_ENTITY_ID = dfl1.FULFILL_LINE_ID
										AND dma1.ADJUSTMENT_TYPE_CODE = 'PRICE_OVERRIDE'
										AND dma1.PARENT_ENTITY_ID = dma.PARENT_ENTITY_ID
									)))
					FROM DOO_MANUAL_PRICE_ADJUSTMENTS dma
						,doo_fulfill_lines_all dfl
					WHERE 1 = 1
						AND dma.PARENT_ENTITY_ID = dfl.FULFILL_LINE_ID
						AND dma.ADJUSTMENT_TYPE_CODE <> 'PRICE_OVERRIDE'
						AND to_char(dfl.fulfill_line_id) = rctl.interface_line_attribute5
					), 0) * rctl.quantity_invoiced
			), 2)                                        "DISCOUNT_INVOICE_VALUE",
    ( round(((decode(rct.invoice_currency_code,
                     'INR',
                     ((
                      SELECT
                          SUM(nvl(
                              abs(rctl1.quantity_invoiced),
                              1
                          ) * abs(rctl1.unit_selling_price))
                      FROM
                          ra_customer_trx_all       rct1,
                          ra_customer_trx_lines_all rctl1
                      WHERE
                              1 = 1
                          AND rctl1.line_type = 'LINE'
                          AND rctl1.customer_trx_id = rct.customer_trx_id
                          AND rct1.customer_trx_id = rctl1.customer_trx_id
                          AND(rctl1.customer_trx_id, rctl1.customer_trx_line_id) NOT IN(
                              SELECT
                                  rctdist1.customer_trx_id, rctdist1.customer_trx_line_id
                              FROM
                                  gl_code_combinations         gcc1, ra_cust_trx_line_gl_dist_all rctdist1
                              WHERE
                                      1 = 1
                                  AND gcc1.code_combination_id = rctdist1.code_combination_id
                                  AND gcc1.segment3 = '248662'
                          )
                          AND(rctl1.customer_trx_id, rctl1.line_number) NOT IN(
                              SELECT
                                  rctl1.customer_trx_id, rctl1.line_number
                              FROM
                                  ra_customer_trx_all       rct1, ra_customer_trx_lines_all rctl1, ra_cust_trx_types_all     rctt1
                              WHERE
                                      rct1.customer_trx_id = rct.customer_trx_id
                                  AND rct1.customer_trx_id = rctl1.customer_trx_id
                                  AND rctt1.cust_trx_type_seq_id = rct1.cust_trx_type_seq_id
                                  AND rct1.org_id = rctt1.org_id
                                  AND rctt1.type = 'INV'
                                  AND rctt1.name NOT LIKE '%MPA%'
                                  AND nvl(rctl1.quantity_invoiced, 1) < 0
                          )
                  )),
                     nvl((
                      SELECT DISTINCT
                          SUM(round(
                              abs(taxable_amt_funcl_curr),
                              2
                          ))
                      FROM
                          zx_lines zl
                      WHERE
                              1 = 1
                          AND entity_code = 'TRANSACTIONS'
                          AND zl.trx_id = rct.customer_trx_id
					 --AND TRX_LINE_NUMBER=rctl.LINE_NUMBER
                  ),
                         (
                      SELECT DISTINCT
                          (round(
                              abs(taxable_amt),
                              2
                          ))
                      FROM
                          zx_lines zl
                      WHERE
                              1 = 1
                          AND zl.trx_id = rct.customer_trx_id
					-- AND TRX_LINE_NUMBER=rctl.LINE_NUMBER
                          AND entity_code = 'TRANSACTIONS'
                  )))) +(nvl((decode(rct.invoice_currency_code,
                                     'INR',
                                     (
                                      SELECT
                                          nvl(
                                              sum(abs(tax_amt_tax_curr)),
                                              0
                                          )
                                      FROM
                                          zx_lines
                                      WHERE
                                              trx_id = rct.customer_trx_id
                                          AND entity_code = 'TRANSACTIONS'
                                          AND tax IN('CGST', 'CGST RCM')
                                  ),
                                     (
                                      SELECT
                                          nvl(
                                              sum(abs(tax_amt_funcl_curr)),
                                              0
                                          )
                                      FROM
                                          zx_lines
                                      WHERE
                                              trx_id = rct.customer_trx_id
                                          AND entity_code = 'TRANSACTIONS'
                                          AND tax IN('CGST', 'CGST RCM')
                                  ))),
                             0)) +(nvl((decode(rct.invoice_currency_code,
                                               'INR',
                                               (
                                                SELECT
                                                    nvl(
                                                        sum(abs(tax_amt_tax_curr)),
                                                        0
                                                    )
                                                FROM
                                                    zx_lines
                                                WHERE
                                                        trx_id = rct.customer_trx_id
                                                    AND entity_code = 'TRANSACTIONS'
                                                    AND tax IN('SGST', 'SGST RCM', 'UTGST', 'UTGST RCM')
                                            ),
                                               (
                                                SELECT
                                                    nvl(
                                                        sum(abs(tax_amt_funcl_curr)),
                                                        0
                                                    )
                                                FROM
                                                    zx_lines
                                                WHERE
                                                        trx_id = rct.customer_trx_id
                                                    AND entity_code = 'TRANSACTIONS'
                                                    AND tax IN('SGST', 'SGST RCM', 'UTGST', 'UTGST RCM')
                                            ))),
                                       0)) +(nvl((decode(rct.invoice_currency_code,
                                                         'INR',
                                                         (
                                                          SELECT
                                                              nvl(
                                                                  sum(abs(tax_amt_tax_curr)),
                                                                  0
                                                              )
                                                          FROM
                                                              zx_lines
                                                          WHERE
                                                                  trx_id = rct.customer_trx_id
                                                              AND entity_code = 'TRANSACTIONS'
                                                              AND tax IN('IGST', 'IGST RCM')
                                                      ),
                                                         (
                                                          SELECT
                                                              nvl(
                                                                  sum(abs(tax_amt_funcl_curr)),
                                                                  0
                                                              )
                                                          FROM
                                                              zx_lines
                                                          WHERE
                                                                  trx_id = rct.customer_trx_id
                                                              AND entity_code = 'TRANSACTIONS'
                                                              AND tax IN('IGST', 'IGST RCM')
                                                      ))),
                                                 0)) +(nvl((decode(rct.invoice_currency_code,
                                                                   'INR',
                                                                   (
                                                                    SELECT
                                                                        nvl(
                                                                            sum(abs(tax_amt_tax_curr)),
                                                                            0
                                                                        )
                                                                    FROM
                                                                        zx_lines
                                                                    WHERE
                                                                            trx_id = rct.customer_trx_id
                                                                        AND entity_code = 'TRANSACTIONS'
                                                                        AND tax IN('CESS', 'CESS RCM')
                                                                ),
                                                                   (
                                                                    SELECT
                                                                        nvl(
                                                                            sum(abs(tax_amt_funcl_curr)),
                                                                            0
                                                                        )
                                                                    FROM
                                                                        zx_lines
                                                                    WHERE
                                                                            trx_id = rct.customer_trx_id
                                                                        AND entity_code = 'TRANSACTIONS'
                                                                        AND tax IN('CESS', 'CESS RCM')
                                                                ))),
                                                           0))),
            0) - ( ( decode(rct.invoice_currency_code,
                            'INR',
                            ((
                             SELECT
                                 SUM(nvl(
                                     abs(rctl1.quantity_invoiced),
                                     1
                                 ) * abs(rctl1.unit_selling_price))
                             FROM
                                 ra_customer_trx_all       rct1,
                                 ra_customer_trx_lines_all rctl1
                             WHERE
                                     1 = 1
                                 AND rctl1.line_type = 'LINE'
                                 AND rctl1.customer_trx_id = rct.customer_trx_id
                                 AND rct1.customer_trx_id = rctl1.customer_trx_id
                                 AND(rctl1.customer_trx_id, rctl1.customer_trx_line_id) NOT IN(
                                     SELECT
                                         rctdist1.customer_trx_id, rctdist1.customer_trx_line_id
                                     FROM
                                         gl_code_combinations         gcc1, ra_cust_trx_line_gl_dist_all rctdist1
                                     WHERE
                                             1 = 1
                                         AND gcc1.code_combination_id = rctdist1.code_combination_id
                                         AND gcc1.segment3 = '248662'
                                 )
                                 AND(rctl1.customer_trx_id, rctl1.line_number) NOT IN(
                                     SELECT
                                         rctl1.customer_trx_id, rctl1.line_number
                                     FROM
                                         ra_customer_trx_all       rct1, ra_customer_trx_lines_all rctl1, ra_cust_trx_types_all     rctt1
                                     WHERE
                                             rct1.customer_trx_id = rct.customer_trx_id
                                         AND rct1.customer_trx_id = rctl1.customer_trx_id
                                         AND rctt1.cust_trx_type_seq_id = rct1.cust_trx_type_seq_id
                                         AND rct1.org_id = rctt1.org_id
                                         AND rctt1.type = 'INV'
                                         AND rctt1.name NOT LIKE '%MPA%'
                                         AND nvl(rctl1.quantity_invoiced, 1) < 0
                                 )
                         )),
                            nvl((
                             SELECT DISTINCT
                                 SUM(round(
                                     abs(taxable_amt_funcl_curr),
                                     2
                                 ))
                             FROM
                                 zx_lines zl
                             WHERE
                                     1 = 1
                                 AND entity_code = 'TRANSACTIONS'
                                 AND zl.trx_id = rct.customer_trx_id
					 --AND TRX_LINE_NUMBER=rctl.LINE_NUMBER
                         ),
                                (
                             SELECT DISTINCT
                                 (round(
                                     abs(taxable_amt),
                                     2
                                 ))
                             FROM
                                 zx_lines zl
                             WHERE
                                     1 = 1
                                 AND zl.trx_id = rct.customer_trx_id
					-- AND TRX_LINE_NUMBER=rctl.LINE_NUMBER
                                 AND entity_code = 'TRANSACTIONS'
                         ))) ) + ( nvl((decode(rct.invoice_currency_code,
                                               'INR',
                                               (
                                                SELECT
                                                    nvl(
                                                        sum(abs(tax_amt_tax_curr)),
                                                        0
                                                    )
                                                FROM
                                                    zx_lines
                                                WHERE
                                                        trx_id = rct.customer_trx_id
                                                    AND entity_code = 'TRANSACTIONS'
                                                    AND tax IN('CGST', 'CGST RCM')
                                            ),
                                               (
                                                SELECT
                                                    nvl(
                                                        sum(abs(tax_amt_funcl_curr)),
                                                        0
                                                    )
                                                FROM
                                                    zx_lines
                                                WHERE
                                                        trx_id = rct.customer_trx_id
                                                    AND entity_code = 'TRANSACTIONS'
                                                    AND tax IN('CGST', 'CGST RCM')
                                            ))),
                                       0) ) + ( nvl((decode(rct.invoice_currency_code,
                                                            'INR',
                                                            (
                                                             SELECT
                                                                 nvl(
                                                                     sum(abs(tax_amt_tax_curr)),
                                                                     0
                                                                 )
                                                             FROM
                                                                 zx_lines
                                                             WHERE
                                                                     trx_id = rct.customer_trx_id
                                                                 AND entity_code = 'TRANSACTIONS'
                                                                 AND tax IN('SGST', 'SGST RCM', 'UTGST', 'UTGST RCM')
                                                         ),
                                                            (
                                                             SELECT
                                                                 nvl(
                                                                     sum(abs(tax_amt_funcl_curr)),
                                                                     0
                                                                 )
                                                             FROM
                                                                 zx_lines
                                                             WHERE
                                                                     trx_id = rct.customer_trx_id
                                                                 AND entity_code = 'TRANSACTIONS'
                                                                 AND tax IN('SGST', 'SGST RCM', 'UTGST', 'UTGST RCM')
                                                         ))),
                                                    0) ) + ( nvl((decode(rct.invoice_currency_code,
                                                                         'INR',
                                                                         (
                                                                          SELECT
                                                                              nvl(
                                                                                  sum(abs(tax_amt_tax_curr)),
                                                                                  0
                                                                              )
                                                                          FROM
                                                                              zx_lines
                                                                          WHERE
                                                                                  trx_id = rct.customer_trx_id
                                                                              AND entity_code = 'TRANSACTIONS'
                                                                              AND tax IN('IGST', 'IGST RCM')
                                                                      ),
                                                                         (
                                                                          SELECT
                                                                              nvl(
                                                                                  sum(abs(tax_amt_funcl_curr)),
                                                                                  0
                                                                              )
                                                                          FROM
                                                                              zx_lines
                                                                          WHERE
                                                                                  trx_id = rct.customer_trx_id
                                                                              AND entity_code = 'TRANSACTIONS'
                                                                              AND tax IN('IGST', 'IGST RCM')
                                                                      ))),
                                                                 0) ) + ( nvl((decode(rct.invoice_currency_code,
                                                                                      'INR',
                                                                                      (
                                                                                       SELECT
                                                                                           nvl(
                                                                                               sum(abs(tax_amt_tax_curr)),
                                                                                               0
                                                                                           )
                                                                                       FROM
                                                                                           zx_lines
                                                                                       WHERE
                                                                                               trx_id = rct.customer_trx_id
                                                                                           AND entity_code = 'TRANSACTIONS'
                                                                                           AND tax IN('CESS', 'CESS RCM')
                                                                                   ),
                                                                                      (
                                                                                       SELECT
                                                                                           nvl(
                                                                                               sum(abs(tax_amt_funcl_curr)),
                                                                                               0
                                                                                           )
                                                                                       FROM
                                                                                           zx_lines
                                                                                       WHERE
                                                                                               trx_id = rct.customer_trx_id
                                                                                           AND entity_code = 'TRANSACTIONS'
                                                                                           AND tax IN('CESS', 'CESS RCM')
                                                                                   ))),
                                                                              0) ) ) )                                      "ROUNDED_OFF_AMOUNT"
                                                                              ,
    ( ( decode(rct.invoice_currency_code,
               'INR',
               ((
                SELECT
                    SUM(nvl(
                        abs(rctl1.quantity_invoiced),
                        1
                    ) * abs(rctl1.unit_selling_price))
                FROM
                    ra_customer_trx_all       rct1,
                    ra_customer_trx_lines_all rctl1
                WHERE
                        1 = 1
                    AND rctl1.line_type = 'LINE'
                    AND rctl1.customer_trx_id = rct.customer_trx_id
                    AND rct1.customer_trx_id = rctl1.customer_trx_id
                    AND(rctl1.customer_trx_id, rctl1.customer_trx_line_id) NOT IN(
                        SELECT
                            rctdist1.customer_trx_id, rctdist1.customer_trx_line_id
                        FROM
                            gl_code_combinations         gcc1, ra_cust_trx_line_gl_dist_all rctdist1
                        WHERE
                                1 = 1
                            AND gcc1.code_combination_id = rctdist1.code_combination_id
                            AND gcc1.segment3 = '248662'
                    )
                    AND(rctl1.customer_trx_id, rctl1.line_number) NOT IN(
                        SELECT
                            rctl1.customer_trx_id, rctl1.line_number
                        FROM
                            ra_customer_trx_all       rct1, ra_customer_trx_lines_all rctl1, ra_cust_trx_types_all     rctt1
                        WHERE
                                rct1.customer_trx_id = rct.customer_trx_id
                            AND rct1.customer_trx_id = rctl1.customer_trx_id
                            AND rctt1.cust_trx_type_seq_id = rct1.cust_trx_type_seq_id
                            AND rct1.org_id = rctt1.org_id
                            AND rctt1.type = 'INV'
                            AND rctt1.name NOT LIKE '%MPA%'
                            AND nvl(rctl1.quantity_invoiced, 1) < 0
                    )
            )),
               nvl((
                SELECT DISTINCT
                    SUM(round(
                        abs(taxable_amt_funcl_curr),
                        2
                    ))
                FROM
                    zx_lines zl
                WHERE
                        1 = 1
                    AND entity_code = 'TRANSACTIONS'
                    AND zl.trx_id = rct.customer_trx_id
					-- AND TRX_LINE_NUMBER=rctl.LINE_NUMBER
            ),
                   (
                SELECT DISTINCT
                    (round(
                        abs(taxable_amt),
                        2
                    ))
                FROM
                    zx_lines zl
                WHERE
                        1 = 1
                    AND zl.trx_id = rct.customer_trx_id
					-- AND TRX_LINE_NUMBER=rctl.LINE_NUMBER
                    AND entity_code = 'TRANSACTIONS'
            ))) ) + ( nvl((decode(rct.invoice_currency_code,
                                  'INR',
                                  (
                                   SELECT
                                       nvl(
                                           sum(abs(tax_amt_tax_curr)),
                                           0
                                       )
                                   FROM
                                       zx_lines
                                   WHERE
                                           trx_id = rct.customer_trx_id
                                       AND entity_code = 'TRANSACTIONS'
                                       AND tax IN('CGST', 'CGST RCM')
                               ),
                                  (
                                   SELECT
                                       nvl(
                                           sum(abs(tax_amt_funcl_curr)),
                                           0
                                       )
                                   FROM
                                       zx_lines
                                   WHERE
                                           trx_id = rct.customer_trx_id
                                       AND entity_code = 'TRANSACTIONS'
                                       AND tax IN('CGST', 'CGST RCM')
                               ))),
                          0) ) + ( nvl((decode(rct.invoice_currency_code,
                                               'INR',
                                               (
                                                SELECT
                                                    nvl(
                                                        sum(abs(tax_amt_tax_curr)),
                                                        0
                                                    )
                                                FROM
                                                    zx_lines
                                                WHERE
                                                        trx_id = rct.customer_trx_id
                                                    AND entity_code = 'TRANSACTIONS'
                                                    AND tax IN('SGST', 'SGST RCM', 'UTGST', 'UTGST RCM')
                                            ),
                                               (
                                                SELECT
                                                    nvl(
                                                        sum(abs(tax_amt_funcl_curr)),
                                                        0
                                                    )
                                                FROM
                                                    zx_lines
                                                WHERE
                                                        trx_id = rct.customer_trx_id
                                                    AND entity_code = 'TRANSACTIONS'
                                                    AND tax IN('SGST', 'SGST RCM', 'UTGST', 'UTGST RCM')
                                            ))),
                                       0) ) + ( nvl((decode(rct.invoice_currency_code,
                                                            'INR',
                                                            (
                                                             SELECT
                                                                 nvl(
                                                                     sum(abs(tax_amt_tax_curr)),
                                                                     0
                                                                 )
                                                             FROM
                                                                 zx_lines
                                                             WHERE
                                                                     trx_id = rct.customer_trx_id
                                                                 AND entity_code = 'TRANSACTIONS'
                                                                 AND tax IN('IGST', 'IGST RCM')
                                                         ),
                                                            (
                                                             SELECT
                                                                 nvl(
                                                                     sum(abs(tax_amt_funcl_curr)),
                                                                     0
                                                                 )
                                                             FROM
                                                                 zx_lines
                                                             WHERE
                                                                     trx_id = rct.customer_trx_id
                                                                 AND entity_code = 'TRANSACTIONS'
                                                                 AND tax IN('IGST', 'IGST RCM')
                                                         ))),
                                                    0) ) + ( nvl((decode(rct.invoice_currency_code,
                                                                         'INR',
                                                                         (
                                                                          SELECT
                                                                              nvl(
                                                                                  sum(abs(tax_amt_tax_curr)),
                                                                                  0
                                                                              )
                                                                          FROM
                                                                              zx_lines
                                                                          WHERE
                                                                                  trx_id = rct.customer_trx_id
                                                                              AND entity_code = 'TRANSACTIONS'
                                                                              AND tax IN('CESS', 'CESS RCM')
                                                                      ),
                                                                         (
                                                                          SELECT
                                                                              nvl(
                                                                                  sum(abs(tax_amt_funcl_curr)),
                                                                                  0
                                                                              )
                                                                          FROM
                                                                              zx_lines
                                                                          WHERE
                                                                                  trx_id = rct.customer_trx_id
                                                                              AND entity_code = 'TRANSACTIONS'
                                                                              AND tax IN('CESS', 'CESS RCM')
                                                                      ))),
                                                                 0) ) + ( ( round(((decode(rct.invoice_currency_code,
                                                                                           'INR',
                                                                                           ((
                                                                                            SELECT
                                                                                                SUM(nvl(
                                                                                                    abs(rctl1.quantity_invoiced),
                                                                                                    1
                                                                                                ) * abs(rctl1.unit_selling_price))
                                                                                            FROM
                                                                                                ra_customer_trx_all       rct1,
                                                                                                ra_customer_trx_lines_all rctl1
                                                                                            WHERE
                                                                                                    1 = 1
                                                                                                AND rctl1.line_type = 'LINE'
                                                                                                AND rctl1.customer_trx_id = rct.customer_trx_id
                                                                                                AND rct1.customer_trx_id = rctl1.customer_trx_id
                                                                                                AND(rctl1.customer_trx_id, rctl1.customer_trx_line_id
                                                                                                ) NOT IN(
                                                                                                    SELECT
                                                                                                        rctdist1.customer_trx_id, rctdist1.customer_trx_line_id
                                                                                                    FROM
                                                                                                        gl_code_combinations         gcc1
                                                                                                        , ra_cust_trx_line_gl_dist_all rctdist1
                                                                                                    WHERE
                                                                                                            1 = 1
                                                                                                        AND gcc1.code_combination_id = rctdist1.code_combination_id
                                                                                                        AND gcc1.segment3 = '248662'
                                                                                                )
                                                                                                AND(rctl1.customer_trx_id, rctl1.line_number
                                                                                                ) NOT IN(
                                                                                                    SELECT
                                                                                                        rctl1.customer_trx_id, rctl1.line_number
                                                                                                    FROM
                                                                                                        ra_customer_trx_all       rct1
                                                                                                        , ra_customer_trx_lines_all rctl1
                                                                                                        , ra_cust_trx_types_all     rctt1
                                                                                                    WHERE
                                                                                                            rct1.customer_trx_id = rct.customer_trx_id
                                                                                                        AND rct1.customer_trx_id = rctl1.customer_trx_id
                                                                                                        AND rctt1.cust_trx_type_seq_id = rct1.cust_trx_type_seq_id
                                                                                                        AND rct1.org_id = rctt1.org_id
                                                                                                        AND rctt1.type = 'INV'
                                                                                                        AND rctt1.name NOT LIKE '%MPA%'
                                                                                                        AND nvl(rctl1.quantity_invoiced
                                                                                                        , 1) < 0
                                                                                                )
                                                                                        )),
                                                                                           nvl((
                                                                                            SELECT DISTINCT
                                                                                                SUM(round(
                                                                                                    abs(taxable_amt_funcl_curr),
                                                                                                    2
                                                                                                ))
                                                                                            FROM
                                                                                                zx_lines zl
                                                                                            WHERE
                                                                                                    1 = 1
                                                                                                AND entity_code = 'TRANSACTIONS'
                                                                                                AND zl.trx_id = rct.customer_trx_id
					-- AND TRX_LINE_NUMBER=rctl.LINE_NUMBER
                                                                                        ),
                                                                                               (
                                                                                            SELECT DISTINCT
                                                                                                (round(
                                                                                                    abs(taxable_amt),
                                                                                                    2
                                                                                                ))
                                                                                            FROM
                                                                                                zx_lines zl
                                                                                            WHERE
                                                                                                    1 = 1
                                                                                                AND zl.trx_id = rct.customer_trx_id
					-- AND TRX_LINE_NUMBER=rctl.LINE_NUMBER
                                                                                                AND entity_code = 'TRANSACTIONS'
                                                                                        )))) +(nvl((decode(rct.invoice_currency_code,
                                                                                                           'INR',
                                                                                                           (
                                                                                                            SELECT
                                                                                                                nvl(
                                                                                                                    sum(abs(tax_amt_tax_curr
                                                                                                                    )),
                                                                                                                    0
                                                                                                                )
                                                                                                            FROM
                                                                                                                zx_lines
                                                                                                            WHERE
                                                                                                                    trx_id = rct.customer_trx_id
                                                                                                                AND entity_code = 'TRANSACTIONS'
                                                                                                                AND tax IN('CGST', 'CGST RCM'
                                                                                                                )
                                                                                                        ),
                                                                                                           (
                                                                                                            SELECT
                                                                                                                nvl(
                                                                                                                    sum(abs(tax_amt_funcl_curr
                                                                                                                    )),
                                                                                                                    0
                                                                                                                )
                                                                                                            FROM
                                                                                                                zx_lines
                                                                                                            WHERE
                                                                                                                    trx_id = rct.customer_trx_id
                                                                                                                AND entity_code = 'TRANSACTIONS'
                                                                                                                AND tax IN('CGST', 'CGST RCM'
                                                                                                                )
                                                                                                        ))),
                                                                                                   0)) +(nvl((decode(rct.invoice_currency_code
                                                                                                   ,
                                                                                                                     'INR',
                                                                                                                     (
                                                                                                                      SELECT
                                                                                                                          nvl(
                                                                                                                              sum(abs
                                                                                                                              (tax_amt_tax_curr
                                                                                                                              )),
                                                                                                                              0
                                                                                                                          )
                                                                                                                      FROM
                                                                                                                          zx_lines
                                                                                                                      WHERE
                                                                                                                              trx_id = rct.customer_trx_id
                                                                                                                          AND entity_code = 'TRANSACTIONS'
                                                                                                                          AND tax IN(
                                                                                                                          'SGST', 'SGST RCM'
                                                                                                                          , 'UTGST', 'UTGST RCM'
                                                                                                                          )
                                                                                                                  ),
                                                                                                                     (
                                                                                                                      SELECT
                                                                                                                          nvl(
                                                                                                                              sum(abs
                                                                                                                              (tax_amt_funcl_curr
                                                                                                                              )),
                                                                                                                              0
                                                                                                                          )
                                                                                                                      FROM
                                                                                                                          zx_lines
                                                                                                                      WHERE
                                                                                                                              trx_id = rct.customer_trx_id
                                                                                                                          AND entity_code = 'TRANSACTIONS'
                                                                                                                          AND tax IN(
                                                                                                                          'SGST', 'SGST RCM'
                                                                                                                          , 'UTGST', 'UTGST RCM'
                                                                                                                          )
                                                                                                                  ))),
                                                                                                             0)) +(nvl((decode(rct.invoice_currency_code
                                                                                                             ,
                                                                                                                               'INR',
                                                                                                                               (
                                                                                                                                SELECT
                                                                                                                                    nvl
                                                                                                                                    (
                                                                                                                                        sum
                                                                                                                                        (
                                                                                                                                        abs
                                                                                                                                        (
                                                                                                                                        tax_amt_tax_curr
                                                                                                                                        )
                                                                                                                                        )
                                                                                                                                        ,
                                                                                                                                        0
                                                                                                                                    )
                                                                                                                                FROM
                                                                                                                                    zx_lines
                                                                                                                                WHERE
                                                                                                                                        trx_id = rct.customer_trx_id
                                                                                                                                    AND
                                                                                                                                    entity_code = 'TRANSACTIONS'
                                                                                                                                    AND
                                                                                                                                    tax
                                                                                                                                    IN
                                                                                                                                    (
                                                                                                                                    'IGST'
                                                                                                                                    ,
                                                                                                                                    'IGST RCM'
                                                                                                                                    )
                                                                                                                            ),
                                                                                                                               (
                                                                                                                                SELECT
                                                                                                                                    nvl
                                                                                                                                    (
                                                                                                                                        sum
                                                                                                                                        (
                                                                                                                                        abs
                                                                                                                                        (
                                                                                                                                        tax_amt_funcl_curr
                                                                                                                                        )
                                                                                                                                        )
                                                                                                                                        ,
                                                                                                                                        0
                                                                                                                                    )
                                                                                                                                FROM
                                                                                                                                    zx_lines
                                                                                                                                WHERE
                                                                                                                                        trx_id = rct.customer_trx_id
                                                                                                                                    AND
                                                                                                                                    entity_code = 'TRANSACTIONS'
                                                                                                                                    AND
                                                                                                                                    tax
                                                                                                                                    IN
                                                                                                                                    (
                                                                                                                                    'IGST'
                                                                                                                                    ,
                                                                                                                                    'IGST RCM'
                                                                                                                                    )
                                                                                                                            ))),
                                                                                                                       0)) +(nvl((decode
                                                                                                                       (rct.invoice_currency_code
                                                                                                                       ,
                                                                                                                                'INR'
                                                                                                                                ,
                                                                                                                                (
                                                                                                                                 SELECT
                                                                                                                                     nvl
                                                                                                                                     (
                                                                                                                                         sum
                                                                                                                                         (
                                                                                                                                         abs
                                                                                                                                         (
                                                                                                                                         tax_amt_tax_curr
                                                                                                                                         )
                                                                                                                                         )
                                                                                                                                         ,
                                                                                                                                         0
                                                                                                                                     )
                                                                                                                                 FROM
                                                                                                                                     zx_lines
                                                                                                                                 WHERE
                                                                                                                                         trx_id = rct.customer_trx_id
                                                                                                                                     AND
                                                                                                                                     entity_code = 'TRANSACTIONS'
                                                                                                                                     AND
                                                                                                                                     tax
                                                                                                                                     IN
                                                                                                                                     (
                                                                                                                                     'CESS'
                                                                                                                                     ,
                                                                                                                                     'CESS RCM'
                                                                                                                                     )
                                                                                                                             ),
                                                                                                                                (
                                                                                                                                 SELECT
                                                                                                                                     nvl
                                                                                                                                     (
                                                                                                                                         sum
                                                                                                                                         (
                                                                                                                                         abs
                                                                                                                                         (
                                                                                                                                         tax_amt_funcl_curr
                                                                                                                                         )
                                                                                                                                         )
                                                                                                                                         ,
                                                                                                                                         0
                                                                                                                                     )
                                                                                                                                 FROM
                                                                                                                                     zx_lines
                                                                                                                                 WHERE
                                                                                                                                         trx_id = rct.customer_trx_id
                                                                                                                                     AND
                                                                                                                                     entity_code = 'TRANSACTIONS'
                                                                                                                                     AND
                                                                                                                                     tax
                                                                                                                                     IN
                                                                                                                                     (
                                                                                                                                     'CESS'
                                                                                                                                     ,
                                                                                                                                     'CESS RCM'
                                                                                                                                     )
                                                                                                                             ))),
                                                                                                                                0))),
                                                                                  0) - ( ( decode(rct.invoice_currency_code,
                                                                                                  'INR',
                                                                                                  ((
                                                                                                   SELECT
                                                                                                       SUM(nvl(
                                                                                                           abs(rctl1.quantity_invoiced
                                                                                                           ),
                                                                                                           1
                                                                                                       ) * abs(rctl1.unit_selling_price
                                                                                                       ))
                                                                                                   FROM
                                                                                                       ra_customer_trx_all       rct1
                                                                                                       ,
                                                                                                       ra_customer_trx_lines_all rctl1
                                                                                                   WHERE
                                                                                                           1 = 1
                                                                                                       AND rctl1.line_type = 'LINE'
                                                                                                       AND rctl1.customer_trx_id = rct.customer_trx_id
                                                                                                       AND rct1.customer_trx_id = rctl1.customer_trx_id
                                                                                                       AND(rctl1.customer_trx_id, rctl1.customer_trx_line_id
                                                                                                       ) NOT IN(
                                                                                                           SELECT
                                                                                                               rctdist1.customer_trx_id
                                                                                                               , rctdist1.customer_trx_line_id
                                                                                                           FROM
                                                                                                               gl_code_combinations         gcc1
                                                                                                               , ra_cust_trx_line_gl_dist_all rctdist1
                                                                                                           WHERE
                                                                                                                   1 = 1
                                                                                                               AND gcc1.code_combination_id = rctdist1.code_combination_id
                                                                                                               AND gcc1.segment3 = '248662'
                                                                                                       )
                                                                                                       AND(rctl1.customer_trx_id, rctl1.line_number
                                                                                                       ) NOT IN(
                                                                                                           SELECT
                                                                                                               rctl1.customer_trx_id,
                                                                                                               rctl1.line_number
                                                                                                           FROM
                                                                                                               ra_customer_trx_all       rct1
                                                                                                               , ra_customer_trx_lines_all rctl1
                                                                                                               , ra_cust_trx_types_all     rctt1
                                                                                                           WHERE
                                                                                                                   rct1.customer_trx_id = rct.customer_trx_id
                                                                                                               AND rct1.customer_trx_id = rctl1.customer_trx_id
                                                                                                               AND rctt1.cust_trx_type_seq_id = rct1.cust_trx_type_seq_id
                                                                                                               AND rct1.org_id = rctt1.org_id
                                                                                                               AND rctt1.type = 'INV'
                                                                                                               AND rctt1.name NOT LIKE
                                                                                                               '%MPA%'
                                                                                                               AND nvl(rctl1.quantity_invoiced
                                                                                                               , 1) < 0
                                                                                                       )
                                                                                               )),
                                                                                                  nvl((
                                                                                                   SELECT DISTINCT
                                                                                                       SUM(round(
                                                                                                           abs(taxable_amt_funcl_curr
                                                                                                           ),
                                                                                                           2
                                                                                                       ))
                                                                                                   FROM
                                                                                                       zx_lines zl
                                                                                                   WHERE
                                                                                                           1 = 1
                                                                                                       AND entity_code = 'TRANSACTIONS'
                                                                                                       AND zl.trx_id = rct.customer_trx_id
					 --AND TRX_LINE_NUMBER=rctl.LINE_NUMBER
                                                                                               ),
                                                                                                      (
                                                                                                   SELECT DISTINCT
                                                                                                       (round(
                                                                                                           abs(taxable_amt),
                                                                                                           2
                                                                                                       ))
                                                                                                   FROM
                                                                                                       zx_lines zl
                                                                                                   WHERE
                                                                                                           1 = 1
                                                                                                       AND zl.trx_id = rct.customer_trx_id
					-- AND TRX_LINE_NUMBER=rctl.LINE_NUMBER
                                                                                                       AND entity_code = 'TRANSACTIONS'
                                                                                               ))) ) + ( nvl((decode(rct.invoice_currency_code
                                                                                               ,
                                                                                                                     'INR',
                                                                                                                     (
                                                                                                                      SELECT
                                                                                                                          nvl(
                                                                                                                              sum(abs
                                                                                                                              (tax_amt_tax_curr
                                                                                                                              )),
                                                                                                                              0
                                                                                                                          )
                                                                                                                      FROM
                                                                                                                          zx_lines
                                                                                                                      WHERE
                                                                                                                              trx_id = rct.customer_trx_id
                                                                                                                          AND entity_code = 'TRANSACTIONS'
                                                                                                                          AND tax IN(
                                                                                                                          'CGST', 'CGST RCM'
                                                                                                                          )
                                                                                                                  ),
                                                                                                                     (
                                                                                                                      SELECT
                                                                                                                          nvl(
                                                                                                                              sum(abs
                                                                                                                              (tax_amt_funcl_curr
                                                                                                                              )),
                                                                                                                              0
                                                                                                                          )
                                                                                                                      FROM
                                                                                                                          zx_lines
                                                                                                                      WHERE
                                                                                                                              trx_id = rct.customer_trx_id
                                                                                                                          AND entity_code = 'TRANSACTIONS'
                                                                                                                          AND tax IN(
                                                                                                                          'CGST', 'CGST RCM'
                                                                                                                          )
                                                                                                                  ))),
                                                                                                             0) ) + ( nvl((decode(rct.invoice_currency_code
                                                                                                             ,
                                                                                                                                 'INR'
                                                                                                                                 ,
                                                                                                                                 (
                                                                                                                                  SELECT
                                                                                                                                      nvl
                                                                                                                                      (
                                                                                                                                          sum
                                                                                                                                          (
                                                                                                                                          abs
                                                                                                                                          (
                                                                                                                                          tax_amt_tax_curr
                                                                                                                                          )
                                                                                                                                          )
                                                                                                                                          ,
                                                                                                                                          0
                                                                                                                                      )
                                                                                                                                  FROM
                                                                                                                                      zx_lines
                                                                                                                                  WHERE
                                                                                                                                          trx_id = rct.customer_trx_id
                                                                                                                                      AND
                                                                                                                                      entity_code = 'TRANSACTIONS'
                                                                                                                                      AND
                                                                                                                                      tax
                                                                                                                                      IN
                                                                                                                                      (
                                                                                                                                      'SGST'
                                                                                                                                      ,
                                                                                                                                      'SGST RCM'
                                                                                                                                      ,
                                                                                                                                      'UTGST'
                                                                                                                                      ,
                                                                                                                                      'UTGST RCM'
                                                                                                                                      )
                                                                                                                              ),
                                                                                                                                 (
                                                                                                                                  SELECT
                                                                                                                                      nvl
                                                                                                                                      (
                                                                                                                                          sum
                                                                                                                                          (
                                                                                                                                          abs
                                                                                                                                          (
                                                                                                                                          tax_amt_funcl_curr
                                                                                                                                          )
                                                                                                                                          )
                                                                                                                                          ,
                                                                                                                                          0
                                                                                                                                      )
                                                                                                                                  FROM
                                                                                                                                      zx_lines
                                                                                                                                  WHERE
                                                                                                                                          trx_id = rct.customer_trx_id
                                                                                                                                      AND
                                                                                                                                      entity_code = 'TRANSACTIONS'
                                                                                                                                      AND
                                                                                                                                      tax
                                                                                                                                      IN
                                                                                                                                      (
                                                                                                                                      'SGST'
                                                                                                                                      ,
                                                                                                                                      'SGST RCM'
                                                                                                                                      ,
                                                                                                                                      'UTGST'
                                                                                                                                      ,
                                                                                                                                      'UTGST RCM'
                                                                                                                                      )
                                                                                                                              ))),
                                                                                                                          0) ) + ( nvl
                                                                                                                          ((decode(rct.invoice_currency_code
                                                                                                                          ,
                                                                                                                                 'INR'
                                                                                                                                 ,
                                                                                                                                 (
                                                                                                                                  SELECT
                                                                                                                                      nvl
                                                                                                                                      (
                                                                                                                                          sum
                                                                                                                                          (
                                                                                                                                          abs
                                                                                                                                          (
                                                                                                                                          tax_amt_tax_curr
                                                                                                                                          )
                                                                                                                                          )
                                                                                                                                          ,
                                                                                                                                          0
                                                                                                                                      )
                                                                                                                                  FROM
                                                                                                                                      zx_lines
                                                                                                                                  WHERE
                                                                                                                                          trx_id = rct.customer_trx_id
                                                                                                                                      AND
                                                                                                                                      entity_code = 'TRANSACTIONS'
                                                                                                                                      AND
                                                                                                                                      tax
                                                                                                                                      IN
                                                                                                                                      (
                                                                                                                                      'IGST'
                                                                                                                                      ,
                                                                                                                                      'IGST RCM'
                                                                                                                                      )
                                                                                                                              ),
                                                                                                                                 (
                                                                                                                                  SELECT
                                                                                                                                      nvl
                                                                                                                                      (
                                                                                                                                          sum
                                                                                                                                          (
                                                                                                                                          abs
                                                                                                                                          (
                                                                                                                                          tax_amt_funcl_curr
                                                                                                                                          )
                                                                                                                                          )
                                                                                                                                          ,
                                                                                                                                          0
                                                                                                                                      )
                                                                                                                                  FROM
                                                                                                                                      zx_lines
                                                                                                                                  WHERE
                                                                                                                                          trx_id = rct.customer_trx_id
                                                                                                                                      AND
                                                                                                                                      entity_code = 'TRANSACTIONS'
                                                                                                                                      AND
                                                                                                                                      tax
                                                                                                                                      IN
                                                                                                                                      (
                                                                                                                                      'IGST'
                                                                                                                                      ,
                                                                                                                                      'IGST RCM'
                                                                                                                                      )
                                                                                                                              ))),
                                                                                                                                 0) )
                                                                                                                                 + 0
                                                                                                                                  ) )
                                                                                                                                  ) )                                  "FINAL_INVOICE_VALUE",
																																 
                                                                                                                                  
    NVL((
			SELECT DISTINCT TR.PERCENTAGE_RATE
			FROM ra_customer_trx_lines_all rctl1
				,zx_lines tl
				,ZX_RATES_B TR
				,ZX_TAXES_B tb
			WHERE 1 = 1
				AND rctl1.LINK_TO_CUST_TRX_LINE_ID = rctl.CUSTOMER_TRX_LINE_ID
				AND rctl1.tax_line_id = tl.tax_line_id
				AND tl.tax_id = tb.tax_id
				AND TR.TAX = TB.TAX
				AND tr.active_flag = 'Y'
				AND TR.RATE_TYPE_CODE = 'PERCENTAGE'
				AND tb.TAX = 'TCS'
				AND trunc(rct.trx_date) BETWEEN trunc(tr.effective_from)
					AND nvl(trunc(tr.effective_to), trunc(sysdate))
			), 0) TCS_RATE
	,NVL((
			SELECT tl.TAX_AMT
			FROM ra_customer_trx_lines_all rctl1
				,zx_lines tl
				,ZX_TAXES_B tb
			WHERE 1 = 1
				AND rctl1.LINK_TO_CUST_TRX_LINE_ID = rctl.CUSTOMER_TRX_LINE_ID
				AND rctl1.tax_line_id = tl.tax_line_id
				AND tl.tax_id = tb.tax_id
				AND tb.TAX = 'TCS'
			), 0) TCS_AMT
	,(
		NVL((
				SELECT sum(tl.TAX_AMT)
				FROM ra_customer_trx_lines_all rctl1
					,zx_lines tl
					,ZX_TAXES_B tb
				WHERE 1 = 1
					AND rctl1.customer_trx_id = rct.customer_trx_id
					AND rctl1.tax_line_id = tl.tax_line_id
					AND tl.tax_id = tb.tax_id
					AND tb.TAX = 'TCS'
				), 0)
		) total_tcs,
	(
        SELECT
            name
        FROM
            ra_terms
        WHERE
            term_id = rct.term_id
    )                                             "MODEOFPAYMENT",
    (
        SELECT
            flv.attribute7
        FROM
            fnd_lookup_values flv
        WHERE
                1 = 1
            AND flv.lookup_type = 'EDEL BANK DETAILS'
            AND flv.lookup_code = rct.attribute3
            AND flv.tag = rct.org_id
    )                                             "BRANCHCODE",
    (
        SELECT
            flv.attribute6
        FROM
            fnd_lookup_values flv
        WHERE
                1 = 1
            AND flv.lookup_type = 'EDEL BANK DETAILS'
            AND flv.lookup_code = rct.attribute3
            AND flv.tag = rct.org_id
    )                                             "ACCOUNTDETAILS",
    (
        SELECT
            rctl.GLOBAL_ATTRIBUTE2
        FROM
            ra_customer_trx_all rct1
        WHERE
            customer_trx_id = rct.customer_trx_id
    )                                             "PRECEDING_INV_NO",
    (
        SELECT
            rctl.GLOBAL_ATTRIBUTE_DATE2
        FROM
            ra_customer_trx_all rct1
        WHERE
            customer_trx_id = rct.customer_trx_id
    )                                             "PRECEDING_INV_DATE",
	(Select rctla.attribute2 
	 From ra_customer_trx_lines_all rctla 
	 Where rctla.customer_trx_id = rct.customer_trx_id 
	 And rctla.ATTRIBUTE_CATEGORY = 'Eway Bill'
	 and rctla.LINE_NUMBER = 1
	)                                             "TRANSPORTER_GSTIN",
	(Select rctla.attribute3 
	 From ra_customer_trx_lines_all rctla 
	 Where rctla.customer_trx_id = rct.customer_trx_id 
	 And rctla.ATTRIBUTE_CATEGORY = 'Eway Bill'
     and rctla.LINE_NUMBER = 1	
	)                                             "TRANSPORTER_NAME",
	(Select rctla.attribute4
	 From ra_customer_trx_lines_all rctla 
	 Where rctla.customer_trx_id = rct.customer_trx_id 
	 And rctla.ATTRIBUTE_CATEGORY = 'Eway Bill'
 	 and rctla.LINE_NUMBER = 1
	)                                             "TRANSPORTER_MODE",
	(Select rctla.attribute6 
	 From ra_customer_trx_lines_all rctla 
	 Where rctla.customer_trx_id = rct.customer_trx_id 
	 And rctla.ATTRIBUTE_CATEGORY = 'Eway Bill'
	 and rctla.LINE_NUMBER = 1 
	)                                             "TRANSPORTER_DOCUMENT_NUMBER",
	(Select rctla.attribute7 
	 From ra_customer_trx_lines_all rctla 
	 Where rctla.customer_trx_id = rct.customer_trx_id 
	 And rctla.ATTRIBUTE_CATEGORY = 'Eway Bill'
	 and rctla.LINE_NUMBER = 1
	)                                             "VEHICLE_NUMBER",
	(Select rctla.attribute_date1 
	 From ra_customer_trx_lines_all rctla 
	 Where rctla.customer_trx_id = rct.customer_trx_id 
	 And rctla.ATTRIBUTE_CATEGORY = 'Eway Bill'
	 and rctla.LINE_NUMBER = 1
	)                                             "TRANSPORTER_DOCUMENT_DATE",
    rct.customer_trx_id                           "CUSTOMER_TRX_ID",
    rctl.customer_trx_line_id                     "CUSTOMER_TRX_LINE_ID",
    rctt.cust_trx_type_id                         "CUST_TRX_TYPE_ID",
    rct.set_of_books_id                           "SET_OF_BOOKS_ID",
    rct.bill_to_customer_id                       "BILL_TO_CUSTOMER_ID",
    rct.bill_to_site_use_id                       "BILL_TO_SITE_USE_ID",
    rct.ship_to_customer_id                       "SHIP_TO_CUSTOMER_ID",
    rct.ship_to_site_use_id                       "SHIP_TO_SITE_USE_ID",
    rct.doc_sequence_value                        "DOC_SEQUENCE_VALUE",
    rct.org_id                                    "ORG_ID",
    rctdist.code_combination_id                   "CODE_COMBINATION_ID",
    rct.trx_number                                "TRX_NUMBER",
    rct.trx_date                                  "TRX_DATE",
    NULL                                          "REFUND",
    rct.invoice_currency_code                     "INVOICE_CURRENCY_CODE",
    (
        SELECT
            tax_regime_code
        FROM
            zx_lines
        WHERE
                trx_line_id = rctl.customer_trx_line_id
            AND entity_code = 'TRANSACTIONS'
            AND tax_line_number = 1
    )                                             "TAX_RATE_CODE",
    rctt.name                                     "DOCUMENT_NAME",
    rct.interface_header_attribute1               "REFERENCE_NO",
	CASE 
		WHEN rct.INTERFACE_HEADER_CONTEXT = 'CONTRACT INVOICES'
			THEN 'Contract Invoices'
		WHEN rct.INTERFACE_HEADER_CONTEXT = 'DOO'
			THEN 'Distributed Order Orchestration'
		ELSE rct.INTERFACE_HEADER_CONTEXT
		END TRANSACTION_SOURCE
FROM
    hz_parties                   hp,
    hz_cust_accounts             hca,
    hz_cust_acct_sites_all       hcas,
    hz_party_sites               hps,
    hz_cust_site_uses_all        hcsu,
    hz_locations                 hz,
    ar_ref_accounts_all          araa,
    hr_operating_units           hou,
    ra_customer_trx_all          rct,
    ra_customer_trx_lines_all    rctl,
    ra_cust_trx_line_gl_dist_all rctdist,
    ra_cust_trx_types_all        rctt,
    gl_code_combinations         gcc
WHERE
        1 = 1
     AND ( trunc(rct.creation_date) >= trunc(sysdate - 100)
          OR trunc(rct.last_update_date) >= trunc(sysdate - 100) )
    AND rct.complete_flag = 'Y'     -- Completed Transactions Only 
    --AND rctl.tax_invoice_number IS NOT NULL
    AND rctl.line_type = 'LINE'
    AND hp.party_id = hca.party_id
    AND hp.party_id = hps.party_id
    AND hca.cust_account_id = hcas.cust_account_id
    AND hps.party_site_id = hcas.party_site_id
    AND hcas.cust_acct_site_id = hcsu.cust_acct_site_id
    AND hps.location_id = hz.location_id
    AND hcsu.site_use_id = araa.source_ref_account_id (+)
    AND araa.bu_id = hou.organization_id (+)
    AND rctt.cust_trx_type_seq_id = rct.cust_trx_type_seq_id
    AND hcsu.site_use_id = rct.bill_to_site_use_id
    AND hca.cust_account_id = rct.bill_to_customer_id
    AND rct.customer_trx_id = rctl.customer_trx_id
    AND rctl.customer_trx_id = rctdist.customer_trx_id
    AND rctl.customer_trx_line_id = rctdist.customer_trx_line_id
    AND gcc.code_combination_id = rctdist.code_combination_id
