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
