"""Test cho matching/engine.py — dùng đúng config/taxonomy.yaml + scoring.yaml +
company_industry_overrides.yaml thật trong repo (không mock), để bảo đảm bộ
config đi kèm repo luôn hoạt động đúng với các ví dụ nêu trong yêu cầu gốc."""
from matching.engine import evaluate_job
from matching.taxonomy import load_company_overrides, load_scoring, load_taxonomy

TAXONOMY = load_taxonomy()
SCORING = load_scoring()
OVERRIDES = load_company_overrides()


def _evaluate(company_name: str, title: str, description: str = "", locations=None):
    job = {"company": company_name, "title": title, "description": description, "location": "Ho Chi Minh"}
    company_cfg = {"name": company_name}
    return evaluate_job(job, company_cfg, locations or [], TAXONOMY, SCORING, OVERRIDES)


def test_business_analyst_at_consulting_firm_is_accepted():
    result = _evaluate("Bain & Company", "Business Analyst")
    assert result.accepted
    assert result.industry == "consulting"
    assert result.function == "business"
    assert result.level == "entry_level"


def test_commercial_planning_associate_at_consumer_tech_is_accepted():
    result = _evaluate("MoMo (M_Service)", "Commercial Planning Associate")
    assert result.accepted
    assert result.industry == "consumer_tech"
    assert result.function == "product"


def test_trade_marketing_executive_at_fmcg_is_accepted():
    result = _evaluate("Unilever", "Trade Marketing Executive")
    assert result.accepted
    assert result.industry == "fmcg"
    assert result.function == "trade_marketing"
    assert result.level == "entry_level"


def test_backend_engineer_is_rejected_as_excluded_function():
    result = _evaluate("MoMo (M_Service)", "Backend Engineer")
    assert not result.accepted
    assert result.reason in ("excluded_function", "keyword")
    assert result.function == "engineering"


def test_unrelated_role_with_no_function_keyword_is_rejected_as_keyword():
    result = _evaluate("Vinamilk", "Office Cleaning Staff")
    assert not result.accepted
    assert result.reason == "keyword"
    assert result.function is None


def test_senior_manager_role_is_rejected_as_experience():
    result = _evaluate("Grab", "Senior Product Manager")
    assert not result.accepted
    assert result.reason == "experience"
    assert result.level == "senior_level"


def test_location_filter_rejects_job_outside_target_locations():
    job = {"company": "Grab", "title": "Product Executive", "description": "", "location": "Singapore"}
    result = evaluate_job(job, {"name": "Grab"}, ["hanoi", "ho chi minh"], TAXONOMY, SCORING, OVERRIDES)
    assert not result.accepted
    assert result.reason == "location"


def test_company_override_takes_priority_over_keyword_industry_detection():
    result = _evaluate("Unilever", "Innovation Executive")
    # Unilever bị override cứng -> fmcg, dù "innovation" trong taxonomy gắn với
    # nhóm strategy/consumer_tech theo keyword thường
    assert result.industry == "fmcg"


def test_industry_without_override_falls_back_to_keyword_or_general():
    result = _evaluate("Some Random Startup", "Growth Associate")
    assert result.industry in TAXONOMY.industries


def test_reworded_title_without_exact_synonym_phrase_still_matches_via_token_overlap():
    # "Digital Product Ownership Lead" không khớp NGUYÊN VĂN synonym nào trong
    # taxonomy.yaml ("digital product", "product owner"...), nhưng chứa đủ token
    # để engine nhận ra đây vẫn là function Product qua token-overlap fuzzy match.
    result = _evaluate("MoMo (M_Service)", "Digital Product Ownership Lead")
    assert result.accepted
    assert result.function == "product"


def test_plural_variant_of_synonym_matches_via_fuzzy_single_word():
    # "Junior Consultants" (số nhiều) không khớp nguyên văn synonym "junior
    # consultant" (số ít) hay "consultant" — engine vẫn nhận ra qua fuzzy
    # single-word match (không cần đúng chính tả/số ít số nhiều tuyệt đối).
    result = _evaluate("Bain & Company", "Junior Consultants")
    assert result.accepted
    assert result.function == "consulting"


def test_weak_fuzzy_match_does_not_hard_reject_as_excluded_function():
    # Match yếu (dưới ngưỡng HARD_FAIL_CONFIDENCE_THRESHOLD) vào 1 excluded
    # function không được phép tự động loại thẳng job — tránh false positive.
    result = _evaluate("Grab", "Platform Growth Champion")
    assert result.accepted
    assert result.function == "growth"


def test_consulting_ladder_transaction_services_recognized():
    result = _evaluate("Bain & Company", "Transaction Services Analyst")
    assert result.accepted
    assert result.function == "consulting"
    assert result.industry == "consulting"


def test_consulting_ladder_corporate_development_recognized():
    result = _evaluate("Boston Consulting Group (BCG)", "Corporate Development Associate")
    assert result.accepted
    assert result.function == "consulting"


def test_consulting_ladder_senior_associate_recognized_but_level_gated():
    # "Senior Associate" khớp function consulting NHƯNG level mid_level không
    # eligible -> vẫn bị loại vì kinh nghiệm, đúng yêu cầu "high score NẾU
    # level cũng khớp" (level không khớp thì vẫn loại).
    result = _evaluate("McKinsey & Company", "Senior Associate")
    assert result.function == "consulting"
    assert result.level == "mid_level"
    assert not result.accepted
    assert result.reason == "experience"


def test_merchant_function_recognized_at_consumer_tech():
    result = _evaluate("Grab", "Merchant Operations Lead")
    assert result.accepted
    assert result.function == "merchant"


def test_marketplace_function_recognized():
    result = _evaluate("Grab", "Marketplace Strategy Associate")
    assert result.accepted
    assert result.function == "marketplace"


def test_customer_success_function_recognized():
    result = _evaluate("MoMo (M_Service)", "Customer Success Executive")
    assert result.accepted
    assert result.function == "customer_success"


def test_consumer_insights_and_business_planning_recognized_at_fmcg():
    r1 = _evaluate("Unilever", "Consumer Insights Analyst")
    assert r1.accepted and r1.function == "consumer_insights"
    r2 = _evaluate("Unilever", "Business Planning Executive")
    assert r2.accepted and r2.function == "business_planning"


def test_business_excellence_and_pmo_functions_recognized():
    r1 = _evaluate("Techcombank", "Business Excellence Associate")
    assert r1.accepted and r1.function == "business_excellence"
    r2 = _evaluate("Grab", "PMO Analyst")
    assert r2.accepted
