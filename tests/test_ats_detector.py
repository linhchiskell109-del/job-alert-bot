from ats_detector import _match_in


def test_detects_workday_from_url():
    url = "https://kpmg.wd3.myworkdayjobs.com/en-US/KPMG_Careers"
    match = _match_in(url)
    assert match.ats == "workday"
    assert match.params["tenant"] == "kpmg"
    assert match.params["wd_number"] == "wd3"
    assert match.params["site"] == "KPMG_Careers"


def test_detects_greenhouse_from_api_url():
    text = "some html ... boards-api.greenhouse.io/v1/boards/grab/jobs ... more"
    match = _match_in(text)
    assert match.ats == "greenhouse"
    assert match.params["board_token"] == "grab"


def test_detects_greenhouse_from_embed_script():
    text = '<script src="https://greenhouse.io/embed/job_board?for=acme"></script>'
    match = _match_in(text)
    assert match.ats == "greenhouse"
    assert match.params["board_token"] == "acme"


def test_detects_lever_from_url():
    text = "check out our jobs at https://jobs.lever.co/acme-corp"
    match = _match_in(text)
    assert match.ats == "lever"
    assert match.params["company_slug"] == "acme-corp"


def test_no_match_returns_none():
    assert _match_in("<html>just a plain career page</html>") is None


def test_detects_smartrecruiters_from_api_url():
    text = "widget loads from api.smartrecruiters.com/v1/companies/acme-corp/postings"
    match = _match_in(text)
    assert match.ats == "smartrecruiters"
    assert match.params["company_identifier"] == "acme-corp"


def test_detects_smartrecruiters_from_careers_url():
    text = "apply at https://careers.smartrecruiters.com/AcmeCorp/job-title"
    match = _match_in(text)
    assert match.ats == "smartrecruiters"
    assert match.params["company_identifier"] == "AcmeCorp"


def test_detects_successfactors_from_domain():
    text = 'career page embedded via <script src="https://career5.successfactors.com/widget.js"></script>'
    match = _match_in(text)
    assert match.ats == "successfactors"


def test_detects_successfactors_from_query_param():
    text = "https://careers.example.com/?career_ns=job_listing&company=ACME"
    match = _match_in(text)
    assert match.ats == "successfactors"


def test_detects_oracle_recruiting_from_domain():
    text = "https://eeho.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX"
    match = _match_in(text)
    assert match.ats == "oracle_recruiting"


def test_successfactors_and_oracle_have_no_adapter():
    from ats_detector import ADAPTER_SUPPORTED_ATS, DETECTED_ONLY_ATS
    assert "successfactors" in DETECTED_ONLY_ATS
    assert "oracle_recruiting" in DETECTED_ONLY_ATS
    assert "successfactors" not in ADAPTER_SUPPORTED_ATS
    assert "oracle_recruiting" not in ADAPTER_SUPPORTED_ATS
    assert "smartrecruiters" in ADAPTER_SUPPORTED_ATS
