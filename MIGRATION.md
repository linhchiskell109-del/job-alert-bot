# Migration Summary — v2 → v2.1

Bản vá này **không đổi kiến trúc** (giữ nguyên pipeline auto-detect ATS -> HTML
scraper -> Playwright fallback, giữ nguyên filtering/state/email/GitHub Actions
workflow). Thay đổi tập trung vào: URL đã verify, routing ATS tốt hơn, và hỗ trợ
shared portal.

## 1. URL career đã cập nhật (tất cả 22 công ty)

Toàn bộ URL trong `config.yaml` được thay bằng URL đã verify thủ công (danh sách
do bạn cung cấp). Không có URL nào được đoán/tạo mới — mọi domain trong config
đều là URL bạn đã xác nhận. Trước đây (v2) nhiều URL là best-effort chưa verify
và đã sai/lỗi thời (nguyên nhân khiến lần chạy Actions đầu tiên fail nhiều công ty).

| Công ty | URL cũ (best-effort, có thể sai) | URL mới (đã verify) |
|---|---|---|
| MoMo | `momo.vn/tuyen-dung` | `momo.careers/jobs-opening` |
| Shopee | `careers.shopee.vn/` | `careers.shopee.sg` |
| Grab | Greenhouse `board_token: grab` (đoán) | `grab.careers` (auto-detect lại) |
| Techcombank | `tuyendung.techcombank.com.vn/` | `techcombankjobs.com` |
| McKinsey | `mckinsey.com/careers/search-jobs` | `mckinsey.com/careers` |
| Bain | `bain.com/careers/find-a-job/` | `bain.com/careers` |
| BCG | Workday `tenant: bcg` (đoán) | `careers.bcg.com` (auto-detect lại) |
| KPMG Vietnam | Workday `tenant: kpmg` (đoán) | `kpmg.com/vn/en/home/careers.html` (auto-detect lại) |
| EY-Parthenon | Workday `tenant: ey` (đoán) | `careers.ey.com` (auto-detect lại) |
| PwC | Workday `tenant: pwc` (đoán) | `pwc.com/vn/en/careers.html` (auto-detect lại) |
| Deloitte | `apply.deloitte.com/careers` (đoán) | `jobs.sea.deloitte.com/careers.deloitte.com` |
| P&G | Workday `tenant: pg` (đoán) | `pgcareers.com` (auto-detect lại) |
| Masan | `masangroup.com/careers` (đoán) | `careers.masanconsumer.com/?locale=vi_VN` |
| Nestlé | `nestle.com/jobs` | `nestle.com/jobs` (không đổi) |
| Coca-Cola | Workday `tenant: cocacola` (đoán) | `careers.coca-colacompany.com` (auto-detect lại) |
| Vinamilk | `tuyendung.vinamilk.com.vn/` | `vinamilk.com.vn/recruitment/career-opportunities` |
| Monee | `monee.vn/careers` (chưa chắc đúng) | `careers.monee.com/careers` |
| VNG / ZaloPay | 2 mục riêng, cùng crawl `vng.careers/jobs` | 1 shared portal `career.vng.com.vn/`, phân loại theo brand (xem mục 4) |

Các URL trước đây có kèm `type`/`board_token`/`tenant` **đoán mò** (Grab,
BCG, KPMG, EY-Parthenon, PwC, P&G, Coca-Cola) đã được **bỏ hoàn toàn** — v2.1
không còn field `type` trong `config.yaml` cho bất kỳ công ty nào; toàn bộ đều
để `ats_detector.py` tự phát hiện tại runtime dựa trên URL/HTML thật, tránh rủi
ro route nhầm sang board/tenant của công ty khác.

## 2. Xác thực URL trước khi scrape (yêu cầu #2)

Thêm `src/url_utils.py::is_url_reachable()`, gọi ở đầu
`pipeline.run_for_company()`. Nếu 1 URL không truy cập được (DNS lỗi, timeout,
HTTP >= 400 sau khi đã retry với backoff):
- Log `[WARN] <company>: career URL không truy cập được (<url>) — bỏ qua công ty
  này (không tự đoán URL khác)`
- Trả về `([], "unreachable")` — company đó bị bỏ qua hoàn toàn ở lần chạy này,
  KHÔNG có bước nào thử đoán domain/path thay thế.

## 3. Routing ATS được mở rộng (yêu cầu #3, #6)

`src/ats_detector.py` giờ nhận diện thêm:
- **SmartRecruiters** — có adapter gọi API JSON public thật
  (`src/scrapers/smartrecruiters.py`, dùng `api.smartrecruiters.com`).
- **SAP SuccessFactors** — nhận diện qua domain `successfactors.com` hoặc dấu
  hiệu Career Site Builder (`career_ns=job_listing`, script `sfcareersite`...).
  KHÔNG có adapter gọi API riêng (không có endpoint public ổn định không cần xác
  thực) — route thẳng sang HTML scraper -> Playwright fallback, có log
  `[INFO] ... phát hiện ATS 'successfactors' nhưng không có public API tin cậy`.
- **Oracle Recruiting Cloud** — nhận diện qua domain
  `*.fa.*.oraclecloud.com/hcmUI/CandidateExperience` hoặc `eeho.fa.*.oraclecloud.com`.
  Tương tự SuccessFactors: route sang HTML/Playwright, không có adapter riêng.

Thứ tự ưu tiên route (không đổi so với v2, chỉ mở rộng danh sách ATS có adapter):
1. Nếu detect được ATS có adapter public API (Workday/Greenhouse/Lever/
   SmartRecruiters) -> gọi thẳng API.
2. Ngược lại (kể cả SuccessFactors/Oracle Recruiting đã detect nhưng không có
   adapter, hoặc không detect được gì) -> **HTML scraper luôn chạy trước**.
3. Chỉ khi HTML scraper trả về 0 job -> Playwright fallback.

## 4. Chuẩn hoá URL — bỏ tracking param (yêu cầu #4)

`src/url_utils.py::normalize_url()` bỏ `utm_*`, `fbclid`, `gclid`, `gclsrc`,
`srsltid`, `mc_cid`, `mc_eid`, `igshid`, `_hsenc`, `_hsmi`, `ref` khỏi query
string (và bỏ `#fragment`), giữ nguyên các param chức năng thật (vd
`?locale=vi_VN` của Masan Consumer). Áp dụng ở 2 chỗ:
- `config.py::load_config()` — chuẩn hoá URL của mọi company/portal ngay khi đọc
  `config.yaml`.
- `heuristics.py::extract_jobs_from_html()` — chuẩn hoá URL của từng job tìm
  được trước khi lưu vào state/gửi email, để state/email luôn sạch dù trang
  nguồn có gắn tracking param vào link job.

## 5. Shared portal cho VNG + ZaloPay (yêu cầu #5)

Trước đây VNG và ZaloPay là 2 mục riêng trong `companies`, cả hai đều trỏ tới
cùng 1 URL (`vng.careers/jobs`) → crawl trùng lặp và không phân biệt được job
thuộc brand nào.

v2.1 thêm cấu trúc `shared_portals` trong `config.yaml`:
```yaml
shared_portals:
  - name: "VNG Careers Portal"
    url: "https://career.vng.com.vn/"
    brands:
      - company: "ZaloPay"
        match_keywords: ["zalopay", "zalo pay", "ví zalopay"]
      - company: "VNG"
        default: true
```
`pipeline.run_for_shared_portal()` scrape portal **đúng 1 lần**, sau đó
`pipeline.classify_job_brand()` phân loại từng job vào đúng brand dựa trên từ
khoá xuất hiện trong title/department/description (không phân biệt hoa-thường/
dấu tiếng Việt). Job không khớp từ khoá ZaloPay nào sẽ rơi vào bucket mặc định
(`default: true`) — ở đây là VNG.

Zalo (`zalo.careers`) có trang career riêng biệt, **không** nằm trong shared
portal này — vẫn là 1 mục độc lập trong `companies` như trước.

`src/main.py` được sửa tối thiểu để xử lý thêm danh sách `shared_portals` song
song với `companies` (cùng `ThreadPoolExecutor`), nhưng **tái sử dụng nguyên vẹn**
hàm `_collect_new_matched()` (logic `is_new`/`mark_seen`/`job_matches` không đổi)
cho cả 2 loại nguồn.

## 6. Những gì KHÔNG đổi (yêu cầu #7)

- `src/filters.py` — logic lọc keyword/level/location: **không sửa 1 dòng**.
- `src/state.py` — hash job theo company+title+location: **không sửa 1 dòng**.
- `src/notifier.py` — email gộp theo company: **không sửa 1 dòng**.
- `.github/workflows/job-alert.yml`: **không sửa 1 dòng**.
- `src/heuristics.py` — heuristic tìm job link: chỉ thêm 1 dòng gọi
  `normalize_url()` khi build `abs_url`, còn lại nguyên vẹn.
- `src/http_client.py`, `src/concurrency.py`, `src/textnorm.py`: không đổi.

## 7. File mới / thay đổi đáng kể

| File | Thay đổi |
|---|---|
| `config.yaml` | URL đã verify cho 20 company + 1 shared portal (2 brand); bỏ hết field `type`/board_token/tenant đoán mò |
| `src/url_utils.py` | **Mới** — `normalize_url()`, `is_url_reachable()` |
| `src/scrapers/smartrecruiters.py` | **Mới** — adapter SmartRecruiters (public API) |
| `src/ats_detector.py` | Thêm pattern SmartRecruiters/SuccessFactors/Oracle Recruiting |
| `src/pipeline.py` | Thêm reachability check, routing SmartRecruiters, log SuccessFactors/Oracle, `classify_job_brand()`, `run_for_shared_portal()` |
| `src/config.py` | Chuẩn hoá URL khi load, hỗ trợ `shared_portals` |
| `src/main.py` | Xử lý thêm `shared_portals` song song với `companies` (tái dùng logic filter/state cũ) |
| `src/heuristics.py` | Chuẩn hoá URL job trước khi lưu |
| `tests/test_url_utils.py` | **Mới** — 8 test cho normalize_url |
| `tests/test_pipeline.py` | **Mới** — 5 test cho classify_job_brand |
| `tests/test_ats_detector.py` | Thêm 6 test cho SmartRecruiters/SuccessFactors/Oracle Recruiting |

**Tổng: 41/41 test pass** (`pytest tests/ -v`), bao gồm 19 test mới cho phần
vừa thêm.

## 8. Việc bạn cần tự làm sau khi nhận bản này

1. Push code lên repo, chạy thử `workflow_dispatch` 1 lần để xem log — chú ý
   dòng `[UNREACHABLE]` (URL chết) và `[NONE]` (URL sống nhưng không tìm thấy
   job) nếu có.
2. Nếu 1 công ty nào đó log `[NONE]` liên tục dù URL đúng, thử thêm từ khoá vào
   `extra_job_url_keywords` trong `config.yaml` trước khi nghĩ tới việc sửa code.
3. Với VNG/ZaloPay: nếu sau vài lần chạy thấy phân loại brand chưa chuẩn (vd
   job ZaloPay bị rơi vào bucket VNG), bổ sung thêm từ khoá vào
   `match_keywords` của brand ZaloPay trong `config.yaml` — không cần sửa code.

---

# v3 — Semantic Career Matching Engine (data-driven)

## 1. Vấn đề đang giải quyết

Bộ lọc cũ (`src/filters.py`) là keyword PASS/FAIL: job phải chứa nguyên văn 1 từ
trong `jd_keywords` (vd "product", "growth") thì mới được coi là match. Kết quả
thực tế: 60+ job scrape được, `Total 0 NEW matching jobs` — vì nhiều công ty,
đặc biệt Consulting và FMCG, không dùng các từ đó trong title (vd "Trade
Marketing Executive", "Business Analyst" không chứa "product"/"growth").

## 2. Kiến trúc mới

```
config/taxonomy.yaml                 <- industries, functions, levels + synonyms
config/scoring.yaml                  <- trọng số, ngưỡng accept, thứ tự rejection reason
config/company_industry_overrides.yaml <- ngành của từng công ty (override thủ công, optional)
        |
        v
src/matching/taxonomy.py   -- loader (YAML -> dataclass), KHÔNG có logic matching
src/matching/engine.py     -- thuật toán: detect_industry -> detect_function ->
                               detect_level -> score() -> MatchResult, dùng CHUNG
                               cho mọi ngành/function/level (đọc từ taxonomy, không
                               có tên ngành/function nào hard-code trong .py)
src/matching/report.py     -- format log "[ACCEPT]/[REJECT] ... -> lý do" theo
                               từng job + báo cáo tổng kết cuối lần chạy
```

`src/main.py` gọi `matching.engine.evaluate_job()` cho mỗi job mới (chưa có
trong `state.json`), thay vì `filters.job_matches()`. `filters.py` **được giữ
nguyên, không xoá** — chuyển `matching_engine: "legacy"` trong `config.yaml` để
dùng lại logic cũ bất cứ lúc nào, không cần sửa code.

## 3. Vì sao data-driven thay vì hard-code trong Python

- Thêm 1 ngành mới (vd Banking) hoặc 1 cách gọi title mới (vd 1 công ty gọi
  "Product Executive" là "Digital Product Champion") chỉ cần sửa
  `config/taxonomy.yaml` — không đụng `.py`, không cần review code, không risk
  làm hỏng logic đang chạy production.
- `src/matching/engine.py` chỉ chứa **thuật toán** (best-synonym-match theo độ
  dài, cộng điểm có trọng số, chọn rejection reason theo priority) — thuật toán
  này áp dụng được cho MỌI ngành/function/level miễn taxonomy khai báo đúng.
- Tách biệt "dữ liệu nghiệp vụ" (do người dùng — vốn hiểu rõ thị trường tuyển
  dụng — sở hữu và chỉnh sửa) khỏi "logic kỹ thuật" (do code sở hữu). Đây là lý
  do người dùng yêu cầu rõ trong đề bài.

## 4. Cách chấm điểm (xem chi tiết + số liệu tại `config/scoring.yaml`)

1. **Industry**: `company_industry_overrides.yaml` (nếu có khai báo công ty) ->
   nếu không, dò `industries.<id>.keywords` trong title/JD -> fallback `general`.
2. **Function**: so khớp title/JD với `functions.<id>.synonyms` trên TOÀN BỘ
   taxonomy (không giới hạn theo ngành) — synonym khớp DÀI NHẤT thắng (cụ thể
   hơn tổng quát). Function có `excluded: true` (Engineering/HR/Legal/Finance
   thuần) -> loại ngay, không cần tính điểm tiếp.
3. **Level**: tương tự, so khớp `levels.<id>.synonyms`. Level `eligible: false`
   (Manager trở lên) -> loại với lý do "Experience".
4. **Score** = `function_match * 45 + industry_alignment * 20 + level_match *
   25 + location_match * 10` (weight khai báo trong `scoring.yaml`, có thể đổi
   không cần sửa code). Function đúng ngành (nằm trong
   `industries.<id>.relevant_functions`) được full điểm alignment; function
   liên quan nhưng khác ngành (vd Marketing ở 1 công ty Consulting) chỉ được
   40% điểm alignment (`partial_industry_alignment_ratio`) — vẫn có cơ hội
   pass nếu function+level đủ mạnh, thay vì loại cứng.
5. Accept nếu `score >= accept_threshold` (mặc định 60) VÀ không dính lý do
   loại cứng nào (excluded function / location bắt buộc không khớp / level
   không eligible).

## 5. Explainability

M��i job mới được log 1 dòng, ví dụ:

```
[ACCEPT] Bain & Company — "Business Analyst" -> Business / Analyst / Consulting / Entry-level — score 100.0
[REJECT] MoMo (M_Service) — "Backend Engineer" -> Keyword (function 'Engineering (không liên quan)' không liên quan (loại hẳn))
```

Cuối lần chạy, `MatchReport.print_summary()` in breakdown:

```
=== Matching summary ===
Accepted: 12
Rejected -> Duplicate: 18 | Keyword: 10 | Score too low: 14 | Location: 3 | Experience: 5
```

`match_score` và `match_reason` cũng được đính kèm vào từng job đã accept, sẵn
sàng cho `notifier.send_email` hiển thị nếu muốn.

## 6. File mới / thay đổi

| File | Thay đổi |
|---|---|
| `config/taxonomy.yaml` | **Mới** — industries, functions, levels + synonyms |
| `config/scoring.yaml` | **Mới** — trọng số, ngưỡng accept, thứ tự rejection reason |
| `config/company_industry_overrides.yaml` | **Mới** — ngành từng công ty (optional) |
| `src/matching/taxonomy.py` | **Mới** — loader YAML -> dataclass |
| `src/matching/engine.py` | **Mới** — semantic matching algorithm (`evaluate_job`) |
| `src/matching/report.py` | **Mới** — explainability logging + summary |
| `src/main.py` | Dùng `matching.engine.evaluate_job` thay `filters.job_matches` (giữ `matching_engine: legacy` để rollback) |
| `src/config.py` | Thêm default `matching_engine: "semantic"` |
| `config.yaml` | Thêm `matching_engine` toggle, giữ nguyên `jd_keywords`/`levels`/`locations` cho chế độ legacy |
| `tests/test_matching_engine.py` | **Mới** — 9 test theo đúng ví dụ trong đề bài (Business Analyst/Consulting, Commercial Planning Associate/Consumer Tech, Trade Marketing Executive/FMCG, Backend Engineer bị loại, v.v.) |

**Không đổi**: `filters.py`, `state.py`, `notifier.send_email` (logic gửi mail
gốc), toàn bộ scraper/ATS adapter, GitHub Actions workflow.

**Tổng: 50/50 test pass** (`pytest tests/ -v`), gồm 9 test mới cho matching engine.

## 7. Cách mở rộng sau này (không cần sửa code)

- **Thêm ngành mới** (vd Banking chuyên biệt hơn "banking_fintech"): thêm block
  vào `industries:` trong `taxonomy.yaml`, khai báo `keywords` + `relevant_functions`.
- **Thêm cách gọi title mới**: thêm 1 dòng vào `synonyms:` của function/level
  tương ứng.
- **Công ty mới**: thêm vào `companies:` trong `config.yaml` như cũ; nếu muốn
  chắc chắn đúng ngành ngay từ đầu (nhanh hơn để engine tự đoán), thêm 1 dòng
  vào `company_industry_overrides.yaml`.
- **Tinh chỉnh độ khó tính**: đổi `accept_threshold` hoặc các `weights` trong
  `scoring.yaml`.

---

# v4 — Pipeline reorder, debug mode, richer logging, scraper fixes, fuzzy matching

## 1. Pipeline order đổi (duplicate detection chuyển xuống cuối)

**Trước:** `Scrape -> Duplicate detection -> (skip nếu trùng) -> Semantic matching`
**Giờ:** `Scrape -> Semantic matching -> Duplicate detection -> Notification`

Cụ thể ở `src/main.py::_process_job()`: MỌI job scrape được (kể cả đã có trong
`state.json` từ lần chạy trước) đều được đưa qua `matching.engine.evaluate_job()`
trước. Duplicate chỉ được kiểm tra SAU đó, và chỉ ảnh hưởng đến `notify` (có gửi
email hay không) — KHÔNG ảnh hưởng đến kết quả matching (`accepted`/`score`/
`reason`). `mark_seen()` vẫn chạy như cũ (để lần sau còn biết job nào đã thấy).

Lý do: debug table/summary giờ phản ánh đúng CHẤT LƯỢNG MATCHING trên toàn bộ
dữ liệu scrape được, không bị việc "đã seen từ hôm qua" che mất — 1 job có thể
vừa "Accepted" vừa "Duplicate" (không notify), thấy rõ trong bảng.

## 2. Debug mode: `DEBUG_IGNORE_DUPLICATES`

`config.yaml` có thêm `debug_ignore_duplicates: false` (mặc định); có thể
override nhanh bằng biến môi trường `DEBUG_IGNORE_DUPLICATES=true` (env var ưu
tiên hơn config.yaml). Khi bật:

- `state.json` thật KHÔNG được đọc (`load_state()` không được gọi) — dùng
  `{"seen": {}}` rỗng thay thế, nên MỌI job đều "mới" (`duplicate=False`).
- Semantic matching + scoring vẫn chạy đầy đủ như bình thường.
- `state.json` thật KHÔNG bị ghi đè (`save_state()` không được gọi) — verify
  bằng test thủ công: `load_state`/`save_state` được mock để đếm số lần gọi,
  cả 2 đều = 0 khi bật debug mode (xem lịch sử review).

=> Dùng debug mode để tune `config/taxonomy.yaml`/`scoring.yaml` lặp đi lặp lại
mà không sợ "đốt" state thật (nếu không bật debug, mỗi lần chạy thử sẽ đánh dấu
job là "đã thấy", lần sau chạy thật sẽ bị bỏ qua oan).

## 3. Debug table + summary mới (`src/matching/report.py`)

Thay vì chỉ in `Accepted: 0` / `Duplicate: 72`, giờ in bảng đầy đủ từng job:

```
Company     | Title                          | Industry   | Function | Level       | Score | Duplicate | Notify
Bain        | Business Analyst               | Consulting | Business | Entry-level | 100   | ❌         | ✅
Grab        | Commercial Planning Associate  | Consumer.. | Product  | Entry-level | 100   | ❌         | ✅
```

...rồi summary:

```
Accepted: X
Notifications sent: X
Duplicates: X
Rejected by score: X
Rejected by function: X
Rejected by experience: X
Rejected by location: X
```

`Accepted` đếm theo kết quả MATCHING (không quan tâm duplicate). `Notifications
sent` = accepted AND không duplicate — đây là con số thực sự được gửi email.

## 4. Scraper reliability — kết quả điều tra 6 công ty

Điều tra qua web search + fetch trực tiếp (KHÔNG tự đoán/tạo URL) — xem chi
tiết trong comment tại từng entry trong `config.yaml`:

| Công ty | Vấn đề tìm thấy | Fix |
|---|---|---|
| **Grab** | `grab.careers` là site JS tự build (không lỗi, nhưng chậm/không cần thiết) — Grab CŨNG có 1 careers site SmartRecruiters chính chủ, thật, có public API | Đổi URL sang `careers.smartrecruiters.com/Grab` + khai báo `ats_hint: smartrecruiters` -> gọi thẳng API, nhanh + ổn định hơn scrape HTML |
| **Shopee** | URL cũ `careers.shopee.sg` là site Singapore, không phải Vietnam | Đổi sang `careers.shopee.vn/jobs` (verified qua fanpage chính chủ). Vẫn là SPA -> playwright fallback (đã có sẵn) |
| **Zalo** | URL cũ `zalo.careers/` chỉ là trang chủ, không có job list | Đổi sang `zalo.careers/jobs` (verified qua LinkedIn chính chủ Zalo). Vẫn là SPA -> playwright fallback |
| **Monee** | URL cũ `careers.monee.com/careers` sai path | Đổi sang `www.monee.com/jobs` (verified qua job-detail link thật). SPA -> playwright fallback |
| **McKinsey** | URL cũ `mckinsey.com/careers` là trang giới thiệu, không có job list | Đổi sang `mckinsey.com/careers/search-jobs?countries=Vietnam` (filter sẵn VN). SPA -> playwright fallback |
| **Vinamilk** | URL ĐÚNG, HTML tĩnh (không cần JS), 36 job hiển thị trực tiếp lúc kiểm tra | Không đổi URL. Nếu vẫn ra 0 job, khả năng cao là bot-blocking theo User-Agent/IP (Cloudfront) — không phải lỗi heuristic hay URL |

**Cải tiến chung (không riêng công ty nào):** `src/scrapers/playwright_scraper.py`
giờ cuộn xuống đáy trang 4 lần sau khi load xong (`SCROLL_PASSES`) trước khi lấy
HTML cuối — nhiều site (Shopee/Zalo/Monee/McKinsey) chỉ render batch job đầu
tiên rồi lazy-load thêm khi cuộn. Đây là hành vi generic (giống người dùng cuộn
trang thật), áp dụng cho MỌI site dùng infinite-scroll, không phải hardcode
selector riêng cho công ty nào.

## 5. Semantic matching — giảm phụ thuộc exact keyword

`src/matching/engine.py::_match_confidence()` giờ có 3 tầng thay vì chỉ "khớp
nguyên văn cụm từ":

1. **Exact phrase** (như trước) — confidence 1.0.
2. **Token overlap** — synonym nhiều từ chỉ cần >=60% số từ xuất hiện đâu đó
   trong title/JD (không cần liền nhau/đúng thứ tự). Vd "Merchant Ops Lead"
   vẫn nhận diện được liên quan tới `operations`/`product` dù không khớp
   nguyên văn "merchant strategy".
3. **Fuzzy single-word** — dùng `difflib.SequenceMatcher` cho synonym 1 từ, bắt
   được biến thể số ít/số nhiều hoặc gần đúng chính tả (vd "Consultants" vẫn
   nhận ra tương ứng "consultant").

Match yếu (dưới `HARD_FAIL_CONFIDENCE_THRESHOLD = 0.75`) KHÔNG được dùng để
hard-reject (excluded function / experience) — tránh 1 match mờ nhạt loại oan
1 job có thể vẫn liên quan; vẫn ảnh hưởng điểm số (thấp hơn) nhưng không tự
động loại thẳng.

3 test mới minh hoạ trực tiếp: `test_reworded_title_without_exact_synonym_phrase_still_matches_via_token_overlap`,
`test_plural_variant_of_synonym_matches_via_fuzzy_single_word`,
`test_weak_fuzzy_match_does_not_hard_reject_as_excluded_function`.

## 6. File thay đổi

| File | Thay đổi |
|---|---|
| `src/main.py` | Viết lại pipeline: matching TRƯỚC duplicate detection; thêm debug mode (`DEBUG_IGNORE_DUPLICATES`) |
| `src/matching/report.py` | Viết lại: bảng debug đầy đủ (Company/Title/Industry/Function/Level/Score/Duplicate/Notify) + summary 7 chỉ số |
| `src/matching/engine.py` | Thêm `_match_confidence()` 3 tầng (exact/token-overlap/fuzzy); hard-fail chỉ áp dụng khi confidence đủ cao |
| `src/config.py` | Thêm default `debug_ignore_duplicates: false` |
| `config.yaml` | Cập nhật URL Grab/Shopee/Zalo/Monee/McKinsey (verified); thêm `ats_hint` cho Grab; thêm `debug_ignore_duplicates` |
| `src/scrapers/playwright_scraper.py` | Thêm scroll-to-bottom generic (4 lần) để bắt lazy-load/infinite-scroll |
| `tests/test_matching_engine.py` | Thêm 3 test cho fuzzy/token-overlap matching |

**Không đổi**: cấu trúc GitHub Actions, `notifier.send_email`, ATS adapters hiện
có, `filters.py` (chế độ legacy vẫn hoạt động y hệt).

**Tổng: 53/53 test pass** (`pytest tests/ -v`).

---

# v5 — Validation layer, structured Normalize, dedicated ATS/company parsers

## 1. Vấn đề đang giải quyết

Nhiều công ty (Bain, BCG, Deloitte, EY, Coca-Cola, Techcombank, VNG) đang bị
scrape nhầm TRANG ĐIỀU HƯỚNG/MENU thành Job object — vd "Work with Us",
"Explore", "Show all jobs", "Tìm công việc" — vì:
  a. `config.yaml` trỏ tới trang MARKETING/landing (nhiều nav link tình cờ
     khớp path chứa "careers"/"jobs") thay vì trang JOB LIST thật.
  b. heuristic chung (`extract_jobs_from_html`) chỉ dựa vào path chứa từ khoá
     job/careers, không phân biệt được nav link với job link thật nếu path
     không có ID cụ thể.

## 2. Pipeline order đổi — thêm Normalize + Validate

**Trước:** `Scraper -> Matching`
**Giờ:** `Scraper -> Normalize -> Validate -> Matching -> Notification`

Cả 2 bước mới đều nằm trong `pipeline.py::run_for_company()`
(`_normalize_and_validate()`), áp dụng ĐỒNG NHẤT cho MỌI nguồn job (ATS
adapter/company-specific parser/html/playwright) — không phụ thuộc vào từng
scraper tự lọc đúng.

- **Normalize** (`src/normalize.py`): tách 1 title thô dạng dính liền (vd
  `"Hồ Chí MinhFulltimeSenior Manager Product Marketing"`) thành field riêng:
  `title`, `location`, `employment_type`. Thuật toán: "camel-split" (chèn
  khoảng trắng ở ranh giới chữ_thường→Chữ_hoa — dấu hiệu 2 cụm bị dính liền do
  scraper gom text) rồi "nuốt" (consume) lần lượt địa danh/employment_type
  biết trước (config/normalize.yaml) làm prefix, phần còn lại là title thật.
  Dữ liệu địa danh/employment_type 100% trong YAML, thuật toán tách chuỗi
  dùng chung cho mọi công ty.
- **Validate** (`src/validation.py`): job phải có `title` + `url` + (`location`
  HOẶC `country`) — thiếu bị loại ngay. Sau đó kiểm tra `title` (đã chuẩn hoá)
  có TRÙNG NGUYÊN VĂN hoặc CHỈ CHỨA (sau khi bóc hết) 1 cụm trong
  `config/validation.yaml -> nav_blocklist_phrases` (đúng danh sách trong yêu
  cầu: Privacy/Cookie/Benefits/Career/Careers/Explore/Learn More/Students/
  Blog/Stories/Hiring Process/Find Jobs/Search Jobs/Work With Us/Apply Now/
  Show All Jobs + bản dịch tiếng Việt) hay không — có thì loại. Cách bóc-rồi-
  đo-độ-dài-còn-lại giúp KHÔNG loại nhầm job thật chứa 1 từ trong blocklist
  làm 1 phần tên (vd "Benefits Manager" vẫn hợp lệ).
- Job bị loại được log rõ: `[DISCARD] <company> — "<title>" -> <reason>`.

## 3. Dedicated ATS/company parser — ưu tiên CAO HƠN heuristic chung

Đúng yêu cầu "ATS/API adapter luôn ưu tiên cao nhất, chỉ fallback HTML khi
không có structured source" — thứ tự trong `pipeline.run_for_company()`:

```
ATS adapter (Workday/Greenhouse/Lever/SmartRecruiters/Avature/SuccessFactors)
  -> Company-specific parser (COMPANY_PARSER_OVERRIDES, xem bên dưới)
  -> html_scraper (heuristic chung)
  -> playwright_scraper (heuristic chung, JS-rendered)
```

**2 ATS mới được thêm vào (`ats_detector.py` + `scrapers/`), xác minh THẬT
qua web search + fetch trực tiếp 2026-07:**

| ATS | Cách nhận diện | Công ty xác minh | Adapter |
|---|---|---|---|
| **Avature** | meta tag `avature.portal.*` trong HTML (platform trắng nhãn, domain KHÔNG chứa "avature") | Bain & Company (`careers.bain.com/jobs`) | `scrapers/avature.py` — parse HTML tĩnh, job detail URL pattern `/jobs/FolderDetail/<slug>/<id_số>` (KHÔNG khớp nav link vì nav link không có ID số) |
| **SAP SuccessFactors (CSB)** | asset domain `rmkcdn.successfactors.com` hoặc text "based on the SuccessFactors software" | Deloitte SEA (`jobs.sea.deloitte.com`), EY (`careers.ey.com`, tự xác nhận "based on SuccessFactors software provided by SAP") | `scrapers/successfactors_csb.py` — "1-hop discovery" tìm link `/go/.../<id_số>/` bằng PATTERN URL (không dùng text "Show all jobs"), rồi parse bảng job tĩnh, pattern `/job/<slug>/<id_số>/` |

Trước đây SuccessFactors chỉ được NHẬN DIỆN (không có adapter, luôn rơi xuống
heuristic chung — chính là nguồn gốc lỗi nhặt nhầm "Show all jobs"/"What you
can do here"). Giờ có adapter riêng, và vì `ats_detector.py` tự động phát
hiện qua HTML nên EY tự động được fix mà không cần đổi URL hay khai báo gì
thêm trong `config.yaml`.

**Công ty chưa xác định được ATS/API (JS SPA, không quan sát được DOM thật vì
môi trường không chạy JS)** — đăng ký dùng `scrapers/strict_html.py` qua
`COMPANY_PARSER_OVERRIDES` trong `pipeline.py`:

```python
COMPANY_PARSER_OVERRIDES = {
    "Boston Consulting Group (BCG)": strict_html.fetch,
    "The Coca-Cola Company": strict_html.fetch,
    "Techcombank": strict_html.fetch,
    "VNG Careers Portal": strict_html.fetch,
}
```

`strict_html.fetch()` dùng lại `playwright_scraper.fetch()` (render JS + heuristic
chung) rồi LỌC THÊM: chỉ giữ job có URL chứa ID thật (số ≥5 chữ số hoặc UUID) —
nav link (`/careers/explore`, `/careers/students`) không bao giờ có ID nên bị
loại, ngay cả khi text hiển thị lọt qua (validation layer là lớp bảo vệ thứ 2
độc lập). Đây KHÔNG phải selector CSS bịa cho từng site — khi có điều kiện quan
sát DOM thật (vd từ log production), nên thay hàm này bằng selector chính xác
hơn; cấu trúc module giống hệt adapter khác nên thay thế không ảnh hưởng phần
còn lại.

## 4. `src/heuristics.py` — hàm trích xuất mới, dùng CHUNG cho mọi ATS-class parser

`extract_jobs_by_strict_url_pattern(html, base_url, company, url_pattern)` —
biến thể nghiêm ngặt của `extract_jobs_from_html()`, nhận 1 regex pattern URL
job THẬT (có ID) thay vì heuristic từ khoá path lỏng lẻo. `location` trả về là
RAW TEXT quanh anchor (chưa tách) — Normalize layer tách tiếp, không cần biết
trước class/id CSS của từng site.

## 5. `config.yaml` — URL cập nhật (xác minh trực tiếp 2026-07)

| Công ty | Trước | Sau | Lý do |
|---|---|---|---|
| Bain & Company | `www.bain.com/careers` (trang marketing) | `careers.bain.com/jobs` (Avature) | Trang cũ CHÍNH LÀ nguồn "Work with Us" trong báo cáo gốc |
| BCG | `careers.bcg.com` (redirect marketing) | `careers.bcg.com/global/en/search-results` (Phenom People) | Trang cũ chứa "Explore"/"Learn More" |
| Deloitte Vietnam | `jobs.sea.deloitte.com/careers.deloitte.com` | `jobs.sea.deloitte.com/` | SuccessFactors adapter tự "1-hop discovery" tìm link listing thật, không cần URL chính xác — landing URL ổn định hơn URL có ID số (có thể đổi) |
| EY-Parthenon | (giữ nguyên) | (giữ nguyên) | Adapter mới tự phát hiện SuccessFactors, không cần đổi |

## 6. File mới / thay đổi

| File | Thay đổi |
|---|---|
| `config/validation.yaml` | **Mới** — required fields + nav/menu blocklist (EN+VI) |
| `config/normalize.yaml` | **Mới** — employment_type synonyms + known_locations |
| `src/validation.py` | **Mới** — `validate_job()` |
| `src/normalize.py` | **Mới** — `normalize_job()` (camel-split + prefix consume) |
| `src/heuristics.py` | Thêm `extract_jobs_by_strict_url_pattern()` + `_nearby_raw_text()` |
| `src/scrapers/avature.py` | **Mới** — ATS adapter Avature (strict URL pattern + phân trang) |
| `src/scrapers/successfactors_csb.py` | **Mới** — ATS adapter SuccessFactors CSB (1-hop discovery + strict pattern + phân trang) |
| `src/scrapers/strict_html.py` | **Mới** — company parser "nghiêm ngặt" (lọc theo job ID) cho site JS SPA chưa rõ ATS |
| `src/ats_detector.py` | Thêm nhận diện Avature; nâng SuccessFactors từ DETECTED_ONLY lên ADAPTER_SUPPORTED |
| `src/pipeline.py` | Thêm `COMPANY_PARSER_OVERRIDES`, wire Avature/SuccessFactors adapter, thêm bước `_normalize_and_validate()` |
| `config.yaml` | Cập nhật URL Bain/BCG/Deloitte; thêm comment giải thích cho EY/Coca-Cola/Techcombank/VNG |
| `tests/test_validation.py` | **Mới** — 8 test, bao gồm đúng 7 ví dụ nav-text trong yêu cầu gốc |
| `tests/test_normalize.py` | **Mới** — 5 test, bao gồm đúng ví dụ "Hồ Chí MinhFulltimeSenior Manager..." |
| `tests/test_strict_html.py` | **Mới** — 4 test cho job-ID filter |
| `tests/test_heuristics.py` | Thêm 3 test cho `extract_jobs_by_strict_url_pattern` |
| `tests/test_ats_detector.py` | Cập nhật test theo ADAPTER_SUPPORTED_ATS mới; thêm test Avature |

**Không đổi**: `filters.py`, `matching/` (matching engine không đổi — đúng yêu
cầu "cải thiện scraping pipeline, không phải matching engine"), `state.py`,
`notifier.py`, GitHub Actions workflow.

**Tổng: 74/74 test pass** (`pytest tests/ -v`), gồm 20 test mới cho
validation/normalize/strict-pattern extraction.

## 7. Giới hạn đã biết / việc cần làm tiếp

- `strict_html.py` (BCG/Coca-Cola/Techcombank/VNG) là bộ lọc chung dựa trên
  job-ID trong URL, KHÔNG phải selector CSS riêng cho từng site (môi trường
  hiện tại không chạy được JS để quan sát DOM thật của các SPA này). Nếu vẫn
  còn lọt nav page sau validation layer, cách debug nhanh nhất là xem log
  `[DISCARD]`/`[ACCEPT]` từ 1 lần chạy thật, rồi viết selector chính xác hơn
  thay thế `strict_html.fetch()` cho riêng công ty đó trong
  `COMPANY_PARSER_OVERRIDES`.
- `scrapers/avature.py`/`successfactors_csb.py` chỉ trích `location` dạng RAW
  TEXT (Normalize layer tách tiếp) — với case phức tạp như Deloitte
  ("Kuala Lumpur, MY +1 more… Technology & Transformation" — vừa location vừa
  department dính liền), Normalize hiện chỉ tách được phần location đứng đầu;
  phần "department" phía sau tạm thời vẫn nằm trong field `location`. Có thể
  cải thiện thêm bằng cách thêm danh sách department/practice-area biết trước
  vào `config/normalize.yaml` nếu cần độ chính xác cao hơn.

---

# v6 — Parser robustness, broader taxonomy, consulting ladder, early location filter

## 1. Parser robustness — không loại job chỉ vì thiếu location/country

`src/normalize.py::normalize_job()` giờ gán `location = "Unknown"` nếu sau tất
cả các bước tách chuỗi vẫn không có location LẪN không có country — thay vì để
trống. Vì `validation.py` chỉ yêu cầu 1 trong 2 field này CÓ GIÁ TRỊ, job có
title + url hợp lệ sẽ KHÔNG BAO GIỜ bị loại chỉ vì thiếu location nữa.

## 2. Mở rộng function taxonomy (`config/taxonomy.yaml`)

Thêm 13 function mới, tất cả trong file YAML (không đụng code):
`business_strategy`, `business_planning`, `transformation` (tách riêng khỏi
`strategy`), `merchant`, `pmo`, `program`, `project`, `operations_excellence`,
`business_excellence`, `analytics`, `insights`, `marketplace`,
`customer_success`. Mỗi industry (`consulting`/`consumer_tech`/
`banking_fintech`/`fmcg`/`general`) được cập nhật `relevant_functions` cho phù
hợp (vd `merchant`/`marketplace`/`customer_success` chỉ "đúng bài" ở
`consumer_tech`, `business_planning`/`consumer_insights` ở `fmcg`). Vẫn dùng
CHUNG thuật toán fuzzy/token-overlap từ v3 (`_match_confidence`) — không có
khái niệm "khớp từ khoá chính xác" nào mới, tự động suy luận qua camel-split +
token overlap + fuzzy single-word như trước.

## 3. Consulting career ladder (`functions.consulting.synonyms`)

Thêm các cách gọi ladder tư vấn: `senior associate`, `senior consultant`,
`corporate development`, `transaction services`, `m&a`, `mergers and
acquisitions`, `digital`, `technology strategy` — tất cả được coi là function
`consulting`, full điểm `industry_alignment` khi công ty thuộc industry
`consulting` (McKinsey/Bain/BCG/Deloitte/EY/KPMG/Roland Berger đã có override
industry=consulting từ v3). Level vẫn được chấm ĐỘC LẬP như trước — "Senior
Associate"/"Senior Consultant" khớp đúng function `consulting` nhưng level
`mid_level` (không eligible) vẫn bị loại vì "experience" nếu người dùng chỉ
muốn entry-level, đúng tinh thần "high score NẾU level cũng khớp".

## 4. Early location filtering (`pipeline.py::_location_allowed`)

**Trước:** location chỉ được chấm điểm (soft) BÊN TRONG matching engine.
**Giờ:** thêm 1 bước filter CỨNG ngay trong `pipeline.run_for_company()`,
chạy NGAY SAU Normalize + Validate, TRƯỚC KHI job vào matching engine — job có
location RÕ RÀNG không thuộc `config.yaml -> locations` (giờ đã thêm "remote
vietnam", "hybrid vietnam", "saigon", "sea") bị loại thẳng, log
`[DISCARD] ... -> location_not_allowed (<location>)`.

Job có location `"Unknown"`/trống KHÔNG bị loại ở bước này (không đủ căn cứ để
nói "rõ ràng ở nước khác", nhất quán với mục 1 — parser robustness) — nhường
việc cân nhắc lại cho matching engine (vẫn dùng `locations` để chấm điểm soft
như trước nếu `matching_engine: legacy`, hoặc bỏ qua location trong scoring
semantic vì đã lọc sớm rồi).

`allowed_locations` được truyền từ `main.py` (đọc từ `config["locations"]`)
xuyên suốt `process_company` -> `run_for_company` -> `_postprocess`, và tương
tự cho shared portal.

## 5. File thay đổi

| File | Thay đổi |
|---|---|
| `src/normalize.py` | Gán `location = "Unknown"` thay vì để trống khi không tách được |
| `config/taxonomy.yaml` | Thêm 13 function mới + mở rộng `relevant_functions` mỗi industry + mở rộng ladder tư vấn trong `consulting.synonyms` |
| `config.yaml` | Thêm "remote vietnam"/"hybrid vietnam"/"saigon"/"sea" vào `locations` |
| `src/pipeline.py` | Thêm `_location_allowed()` + `_postprocess()` (gộp Normalize→Validate→Location), tham số `allowed_locations` xuyên suốt |
| `src/main.py` | Truyền `config["locations"]` làm `allowed_locations` vào `process_company`/`process_shared_portal` |
| `tests/test_location_filter.py` | **Mới** — 5 test cho early location filter |
| `tests/test_matching_engine.py` | Thêm 8 test cho taxonomy mở rộng + consulting ladder |

**Không đổi**: kiến trúc matching engine (`matching/engine.py` — thuật toán
fuzzy matching không đổi, chỉ đổi DỮ LIỆU taxonomy), `filters.py`, ATS
adapters, GitHub Actions workflow.

**Tổng: 87/87 test pass** (`pytest tests/ -v`), gồm 13 test mới cho 4 yêu cầu
lần này.

---

# v7 — Full pipeline audit: terminal status per job, observability, real bugs found & fixed

## 1. Xác minh 3 fix gần nhất (mục 1 trong audit)

Cả 3 đều đã verify bằng regression test thật (không chỉ đọc code):

1. **Pipeline và matching engine nhất quán về Unknown location** —
   `test_matching_engine_location_check_treats_unknown_as_ok` xác nhận
   `matching/engine.py::_location_ok` không tự loại lại job "Unknown" mà
   pipeline đã cho qua.
2. **Nav/accessibility text không bao giờ thành title** —
   `tests/test_validation_navtext.py` xác nhận "Opens in a new tab."/"Search &
   Apply" bị chặn.
3. **Job Unknown-location nhưng title nêu rõ nước khác bị loại an toàn** —
   `test_unknown_location_with_explicit_foreign_country_in_title_is_denied`.

**Nguyên tắc "title chỉ dùng để LOẠI, không bao giờ dùng để CHO QUA"** được áp
dụng nhất quán ở CẢ 2 nơi kiểm tra location: `pipeline.py::_location_allowed`
VÀ `matching/engine.py::_location_ok` — trước đây chỉ fix 1 chỗ, đợt audit
này rà lại và xác nhận cả 2 đều đúng.

## 2. Bug MỚI tìm được qua audit (không nằm trong 3 fix gần nhất)

### 2a. Hash collision khi location = "Unknown" (`state.py`)

Fallback "Unknown" (thêm ở v6 để không loại job thiếu location) vô tình làm
**2 job THẬT SỰ KHÁC NHAU** (cùng company + title, cả 2 đều không trích được
location — vd 2 đợt tuyển "Warehouse Coordinator" khác nhau) **có CÙNG HASH**
— job thứ 2 bị coi là trùng, không bao giờ được báo. Đây là bug ẩn, chỉ lộ ra
khi rà lại toàn bộ chuỗi `normalize -> job_hash` theo đúng yêu cầu "đừng giả
định phần còn lại đúng".

**Fix**: khi location "Unknown"/trống, hash thêm URL PATH (bỏ query string) làm
tín hiệu phụ để phân biệt — vẫn ổn định qua thay đổi tracking param, nhưng
không còn gộp nhầm 2 job khác nhau. Job có location trích được bình thường:
hash KHÔNG đổi (không ảnh hưởng `state.json` cũ đang chạy production).
Test: `test_unknown_location_does_not_collapse_different_jobs`.

### 2b. Audit duplicate detection (mục 10)

| Câu hỏi | Trả lời |
|---|---|
| Định danh dùng để dedup | `sha256(company \| title \| location [\| url_path nếu location Unknown])` — xem `state.py::job_hash` |
| Vì sao ổn định | KHÔNG dựa vào toàn bộ URL — nhiều site gắn tracking param/session id đổi mỗi lần crawl dù cùng 1 job |
| URL đổi có phá dedup không | KHÔNG (trường hợp bình thường, location trích được) — chỉ URL PATH mới ảnh hưởng, và chỉ khi location Unknown |
| Sửa description có tạo "job mới" giả không | KHÔNG — description không nằm trong hash |
| Title-only matching có gây collision không | KHÔNG dùng title-only — nhưng (company+title+location) VẪN có thể collision nếu 1 công ty đăng 2 job THẬT SỰ trùng cả title lẫn location (giới hạn đã biết, chấp nhận được — hiếm và ít rủi ro hơn báo trùng liên tục vì URL đổi) |
| Location Unknown có gây collision không | CÓ (đã tìm thấy — xem 2a), ĐÃ FIX bằng URL path fallback |

## 3. Kiến trúc mới: JobTrace — mọi job có ĐÚNG 1 terminal status

`src/job_trace.py` — mỗi job crawl được bọc thành 1 `JobTrace`, đi qua đúng
luồng:

```
CRAWLED -> NORMALIZED -> [REJECTED_VALIDATION | REJECTED_LOCATION | tiếp tục]
                                                                        |
                                                    matching engine (main.py)
                                                                        |
                        [REJECTED_FUNCTION | REJECTED_EXPERIENCE | REJECTED_SCORE | tiếp tục]
                                                                        |
                                                    duplicate check (main.py)
                                                                        |
                                          [ALREADY_NOTIFIED | NOTIFIED]
```

`pipeline.py::_trace_raw_jobs()` tạo trace cho MỌI job thô (Normalize ->
Validate -> Location prefilter), `main.py::_process_trace()` tiếp tục
(Matching -> Duplicate -> Notify). Trace nào cũng có `.job` (dict đã
normalize) dù bị reject ở đâu — để shared portal vẫn phân loại brand được, và
diagnostics vẫn tính extraction confidence được.

**Bất biến (mục 9)**: `raw = REJECTED_VALIDATION + REJECTED_LOCATION +
REJECTED_FUNCTION + REJECTED_EXPERIENCE + REJECTED_SCORE + ALREADY_NOTIFIED +
NOTIFIED` — đúng THEO THIẾT KẾ (mỗi trace nhận đúng 1 trong 7 status này).
`Diagnostics.verify_conservation()` verify RUNTIME (không chỉ tin thiết kế) —
nếu có trace nào sót lại KHÔNG terminal (bug code path nào đó quên gọi
`set_status`), in cảnh báo rõ ràng thay vì im lặng.

## 4. Parser diagnostics (mục 11) — `pipeline.py::ScrapeStatus`

Phân biệt RÕ "0 job vì thật sự không có job" với "0 job vì lỗi":

```python
ScrapeStatus(method="none", ok=True, raw_count=0, detail="...")   # thật sự không có job
ScrapeStatus(method="html", ok=False, detail="html_scraper: lỗi (Connection timeout)")  # lỗi thật
```

Khi TẤT CẢ phương pháp đều fail, `detail` liệt kê ĐẦY ĐỦ những gì đã thử (ATS
adapter/company parser/html/playwright) thay vì chỉ lỗi cuối cùng — vd:
`"ATS adapter 'successfactors': lỗi (...); html_scraper: chạy OK, trả về 0 job; playwright_scraper: lỗi (Timeout 45000ms exceeded)"`.

## 5. Observability layer — `src/diagnostics.py`

| Yêu cầu | Hàm |
|---|---|
| Company recall report (mục 5, 12) | `print_company_funnel_table()` — Raw/Parsed/Validated/Matched/AlreadyNotified/NewNotifications + scrape status mỗi công ty |
| Rejection breakdown theo công ty (mục 6) | `print_rejection_breakdown()` |
| Luôn in accepted jobs, kể cả đã notify (mục 7) | `print_accepted_jobs()` |
| Per-job decision cho job MATCHED (mục 4) | `print_per_job_decisions()` — đúng format trong yêu cầu |
| Giải thích vì sao 0 notification (mục 8) | `explain_notifications()` |
| Bất biến bảo toàn job (mục 9) | `verify_conservation()` / `print_conservation_check()` |
| Extraction confidence (mục 13) | `job_trace.py::extraction_confidence()` — trọng số title 0.4/location 0.35/department 0.15/employment_type 0.10, field nào "Unknown"/rỗng không được tính |

## 6. `--debug-company` (mục 15)

```
python src/main.py --debug-company Grab
```

Chỉ scrape + xử lý company/brand đó, in đầy đủ funnel + already-notified list +
new-notifications list + rejection breakdown + extraction confidence từng job —
xem `main.py::_filter_targets()` + `Diagnostics.print_debug_company()`. Chế độ
này **KHÔNG bao giờ ghi `state.json`** (dù load state thật để tính đúng
ALREADY_NOTIFIED) — thuần công cụ debug, không có side effect lên production.

## 7. Regression protection (mục 14)

Đã thêm: `tests/test_job_trace.py`, `tests/test_diagnostics.py`,
`tests/test_pipeline_tracing.py`, mở rộng `tests/test_state.py`. Về "CI fail
nếu 1 công ty đột nhiên chỉ ra 5 job thay vì 120" — cần dữ liệu lịch sử THẬT
(snapshot số lượng job mỗi công ty qua các lần chạy) mà môi trường phát triển
hiện tại không có quyền truy cập mạng thật để lấy — đề xuất: `main.py` có thể
ghi `job_count_history.json` mỗi lần chạy thật (số raw job/công ty), rồi thêm
1 check ở đầu `main()` so với lần chạy trước, cảnh báo nếu giảm > X% — CHƯA
implement (cần quyết định ngưỡng % hợp lý, để tránh false alarm khi công ty
thật sự giảm tin tuyển dụng).

## 8. File mới / thay đổi

| File | Thay đổi |
|---|---|
| `src/state.py` | Fix hash collision khi location Unknown (thêm URL path fallback) |
| `src/job_trace.py` | **Mới** — JobTrace, terminal statuses, extraction_confidence |
| `src/diagnostics.py` | **Mới** — company funnel, rejection breakdown, accepted jobs, per-job decisions, conservation check, debug-company report |
| `src/pipeline.py` | `run_for_company`/`run_for_shared_portal` trả về `list[JobTrace]` + `ScrapeStatus` thay vì `list[dict]` + method string; thêm `ScrapeStatus` phân biệt lỗi vs 0-job-thật |
| `src/main.py` | `_process_trace()` tiếp tục JobTrace qua matching/duplicate; thêm `--debug-company`; in đầy đủ report từ `diagnostics.py` |
| `tests/test_job_trace.py`, `test_diagnostics.py`, `test_pipeline_tracing.py` | **Mới** |
| `tests/test_state.py` | Thêm 3 test cho fix hash collision |

**Không đổi**: `matching/engine.py` thuật toán (chỉ verify lại, không sửa gì
thêm ngoài location check đã fix ở lần trước), `filters.py`, ATS adapters,
`notifier.py`, GitHub Actions workflow.

**Tổng: 115/115 test pass** (`pytest tests/ -v`), gồm 21 test mới cho đợt audit
này.

---

# v8 — Navigation Engine

## 1. Vấn đề đang giải quyết

Nhiều career site (Techcombank, PwC, KPMG, EY-Parthenon, Masan, Unilever,
Nestlé, VNG...) yêu cầu click qua 1 trang landing/marketing trước khi tới
được trang job listing/search thật. Trước đây xử lý việc này cần Playwright
logic viết riêng cho từng công ty. Navigation Engine thay thế bằng 1 lớp
CONFIG-DRIVEN dùng chung.

## 2. Kiến trúc

```
Entry URL
   |
   v
Navigation Engine (src/navigation/)  <- CHỈ chạy khi strategy=landing/search
   |
   v
Target Job URL (final_url)
   |
   v
pipeline.py CHUỖI CŨ, KHÔNG ĐỔI: ATS detect -> adapter -> company parser ->
html_scraper -> playwright_scraper -> Normalize -> Validate -> Location
prefilter -> Matching -> Notification
```

`src/navigation/`:
- `errors.py` — `NavigationFailure` (base), `SelectorNotFound`, `Timeout`,
  `TargetURLMismatch` (mang theo `final_url` thực tế), `ParserFailure`.
- `actions.py` — 11 action (`click_text/click_role/click_css/click_xpath/
  click_icon/select_option/fill/press/wait_selector/wait_networkidle/
  wait_timeout`), mỗi action `(page, params) -> None`, KHÔNG có `if company ==`
  nào. Phân biệt SelectorNotFound (element không tồn tại trong DOM) vs Timeout
  (element tồn tại nhưng action không hoàn tất kịp, vd bị che bởi overlay).
- `engine.py` — `navigate(entry_url, steps, target_url=None, keep_session=False,
  retries=2) -> NavigationResult(final_url, page, browser_context, browser,
  logs)`. `keep_session=False` (mặc định) đóng browser ngay sau khi lấy
  `final_url` — parser hiện tại chỉ cần URL string. `keep_session=True` giữ
  session sống cho parser TƯƠNG LAI cần cookie/session (chưa ai dùng, nhưng
  sẵn sàng — đúng yêu cầu "future-proof").

## 3. Config-driven — `config.yaml`

```yaml
- name: "PwC Vietnam"
  url: "https://www.pwc.com/vn/en/careers.html"
  strategy: "landing"          # "direct" (mặc định) | "landing" | "search" | "api" (dự trữ)
  navigation:
    - click_text: "Experienced Professionals"
  target_url: "https://www.pwc.com/vn/en/careers/experienced-jobs.html"
```

`strategy: "direct"` (mặc định khi bỏ trống) -> BỎ QUA Navigation Engine hoàn
toàn, hành vi Y HỆT trước khi có tính năng này (yêu cầu 8).

## 4. Áp dụng inventory (Career_Site.xlsx) — quyết định TỪNG công ty, không áp
   dụng máy móc

Đối chiếu 22 dòng trong inventory với config ĐÃ XÁC MINH TRỰC TIẾP từ các đợt
audit trước (v3-v7):

| Nhóm | Công ty | Quyết định | Lý do |
|---|---|---|---|
| Giữ direct (đã verify, URL inventory KHÁC — chưa kiểm chứng) | Bain, Zalo, Monee, Deloitte, Vinamilk | Giữ URL đã verify | URL inventory khác domain/path, KHÔNG có bằng chứng xác minh — không đánh đổi cấu hình đang chạy tốt lấy đường dẫn chưa kiểm chứng |
| Giữ direct (đã verify, KHỚP inventory) | MoMo, McKinsey, BCG, Coca-Cola | Không đổi | target_url inventory trùng khớp URL hiện tại |
| Giữ direct (API tốt hơn navigation) | Grab | Không đổi | ats_hint=smartrecruiters gọi thẳng public API, đáng tin hơn điều hướng qua browser dù cùng nguồn dữ liệu |
| Chuyển sang landing (cải thiện thật, có verify) | Techcombank | strategy=landing | target_url inventory là URL search cụ thể (dạng SuccessFactors), tốt hơn hẳn bare-domain + strict_html cũ |
| Chuyển sang landing (chưa từng verify trước đây) | PwC, KPMG, Masan, Nestlé, EY-Parthenon, VNG | strategy=landing | Config cũ chỉ là trang landing chưa qua kiểm chứng — áp dụng navigation từ inventory là cải thiện rõ ràng |
| Áp dụng URL direct mới từ inventory | Roland Berger, P&G | strategy=direct, URL mới | Inventory cho URL cụ thể hơn hẳn (đã lọc theo Vietnam/All-Jobs), URL cũ chưa từng verify |
| Landing nhưng THIẾU dữ liệu (không đoán) | Unilever | strategy=landing, `selector: null` | Inventory chỉ cho `select_option("Vietnam")`, KHÔNG có CSS selector dropdown — Navigation Engine từ chối đoán, raise `SelectorNotFound` rõ ràng ngay khi chạy. **Cần bổ sung `selector` thật trong config.yaml trước khi Unilever hoạt động qua navigation tự động** — cho tới lúc đó, công ty này ra 0 job mỗi lần chạy, lý do được ghi rõ trong `ScrapeStatus.detail`, không lặng lẽ. |

Cột "Parser" trong inventory (Eightfold/Phenom/SAP Careers/React...) được coi
là THÔNG TIN THAM KHẢO, KHÔNG map trực tiếp thành `ats_hint` — `ats_detector.py`
tự nhận diện ATS thật từ URL/HTML ĐÃ ĐIỀU HƯỚNG TỚI (content-based), đáng tin
hơn nhãn tĩnh trong 1 bảng có thể lỗi thời, và tránh phải xây thêm adapter cho
Eightfold/Phenom/SAP Careers (ngoài phạm vi yêu cầu lần này — chỉ về
navigation, không phải thêm ATS adapter mới).

## 5. Xử lý lỗi & retry

| Lỗi | Retry? | Hành vi |
|---|---|---|
| `SelectorNotFound` | KHÔNG | Config/DOM lệch — retry vô ích. `ScrapeStatus(method="navigation_failed", ok=False)`. |
| `Timeout` | CÓ (mặc định 2 lần, chạy lại TOÀN BỘ dãy step) | Có thể transient (mạng/site chậm). |
| `NavigationFailure` (chung) | CÓ | Lỗi browser không xác định cụ thể hơn — coi là transient. |
| `TargetURLMismatch` | KHÔNG (và KHÔNG fatal) | final_url THỰC TẾ vẫn được dùng tiếp — chỉ log cảnh báo, vì final_url thực tế đáng tin hơn config có thể đã cũ. |
| `ParserFailure` | KHÔNG (không nằm trong scope retry của Navigation Engine — retry chỉ bọc quanh `navigate()`, không bao giờ bọc quanh lệnh gọi parser) | Lỗi ở bước SAU navigation, xử lý y hệt cơ chế fallback parser đã có từ trước. |

Không lỗi nào bị gộp chung thành "UNREACHABLE" — `ScrapeStatus.detail` luôn
ghi rõ loại lỗi + message gốc.

## 6. Testing (yêu cầu 9)

`tests/test_navigation.py` — 12 test dùng **browser Chromium THẬT** (headless,
không cần mạng — chạy trên fixture HTML cục bộ `tests/fixtures/navigation/`
qua `file://`): successful navigation, selector not found, timeout (dùng
overlay `pointer-events` thật để buộc Playwright timeout khi click — không
giả lập), redirected URL, direct page (0 step), navigation logs, keep_session,
target URL mismatch, retry logic (mock để đếm số lần thử chính xác).

`tests/test_pipeline_navigation.py` — 10 test tích hợp vào `pipeline.py`
(mock `navigate()` — không cần browser vì mục tiêu là verify pipeline gọi
đúng chỗ/xử lý đúng lỗi, không phải verify hành vi browser lần nữa): direct
strategy KHÔNG BAO GIỜ gọi Navigation Engine, landing strategy dùng URL đã
resolve cho toàn bộ chuỗi phía sau, mỗi loại lỗi tạo `ScrapeStatus` riêng biệt
(không có "unreachable" chung chung), TargetURLMismatch không fatal.

## 7. File mới / thay đổi

| File | Thay đổi |
|---|---|
| `src/navigation/errors.py` | **Mới** — 5 loại lỗi phân biệt |
| `src/navigation/actions.py` | **Mới** — 11 action, generic, không company-specific |
| `src/navigation/engine.py` | **Mới** — `navigate()`, `NavigationResult`, retry logic |
| `src/pipeline.py` | Thêm `_resolve_entry_url()` gọi Navigation Engine trước chuỗi ATS-detect cũ; parser hiện có KHÔNG đổi 1 dòng nào |
| `config.yaml` | Thêm `strategy`/`navigation`/`target_url` cho từng công ty theo inventory (đã đối chiếu kỹ với config đã verify trước đó — xem bảng mục 4) |
| `tests/test_navigation.py`, `test_pipeline_navigation.py` | **Mới** — 22 test |
| `tests/fixtures/navigation/*.html` | **Mới** — fixture cho test browser thật |

**Không đổi**: mọi parser hiện có (`avature.py`, `successfactors_csb.py`,
`html_scraper.py`, `playwright_scraper.py`, `strict_html.py`, v.v.), matching
engine, validation, normalize, state/dedup, notifier, GitHub Actions workflow.

**Tổng: 137/137 test pass** (`pytest tests/ -v`), gồm 22 test mới cho
Navigation Engine.

## 8. Việc còn lại cần người xác nhận

- **Unilever**: cần cung cấp CSS selector thật của dropdown chọn quốc gia
  (`config.yaml -> Unilever -> navigation[0].select_option.selector`) — hiện
  đang `null` có chủ đích, sẽ báo lỗi rõ ràng mỗi lần chạy cho tới khi được
  điền.
- **Deloitte** (landing path trong inventory) cũng thiếu selector tương tự —
  đã QUYẾT ĐỊNH giữ nguyên cấu hình `direct` cũ (đã verify, có auto-discovery)
  thay vì áp dụng, nên không bị ảnh hưởng, nhưng nếu muốn dùng đúng path
  inventory sau này cũng cần bổ sung selector.
- Các discrepancy đã ghi chú trong comment `config.yaml` (Bain, Zalo, Monee,
  Vinamilk) — URL inventory khác URL đã verify, cần xác minh thủ công nếu
  muốn chuyển.

---

# v9 — Navigation config corrections (manual verification follow-up)

## 1. Techcombank — text sai

Text nút thật là **"Search Jobs"**, không phải "Search" (Playwright's
`get_by_text` không khớp substring rời rạc kiểu "Search" ⊂ "Search Jobs" theo
cách người viết config kỳ vọng). Sửa `config.yaml`.

## 2. KPMG Vietnam — thiếu 1 bước điều hướng

Xác minh trực tiếp qua fetch `kpmg.com/vn/en/careers.html`: trang này KHÔNG có
nút "Search Jobs" — chỉ có link **"Search for jobs"** (mục "Exprienced
professionals") dẫn tới `careers.kpmg.com.vn/` (xác nhận SAP SuccessFactors CSB
qua asset `rmkcdn.successfactors.com`). Trang đó CŨNG chưa phải kết quả search
— fetch tiếp thấy link thật **"View All Jobs"** → `careers.kpmg.com.vn/viewalljobs/`.
Sửa thành chuỗi 2 bước:

```yaml
navigation:
  - click_text: "Search for jobs"
  - click_text: "View All Jobs"
target_url: "https://careers.kpmg.com.vn/viewalljobs/"
```

`target_url` cũng được cập nhật theo URL THẬT quan sát được (URL `/search/?...`
trước đó chưa từng được xác minh tồn tại, chỉ là suy đoán theo pattern
SuccessFactors của Deloitte).

## 3. Unilever — combobox/autocomplete, không phải `<select>`

### 3a. Navigation Engine: thêm `select_combobox` action mới

`src/navigation/actions.py::select_combobox()` — action MỚI, dùng cho widget
combobox/autocomplete tự build (React/Vue...), khác với `<select>` gốc
(`select_option()`). Chuỗi thao tác: click/focus `input_selector` -> `fill(value)`
-> đợi debounce (`wait_after_fill_ms`, mặc định 800ms) cho danh sách gợi ý
render -> click option khớp `value` (thử `get_by_role("option", name=value)`
trước — chuẩn ARIA cho item trong listbox — fallback sang khớp text hiển thị
nếu widget không set đúng role). Vẫn giữ nguyên tắc "không tự đoán selector":
`input_selector` là bắt buộc, thiếu sẽ raise `SelectorNotFound` rõ ràng.

Test bằng browser thật với fixture combobox tự dựng
(`tests/fixtures/navigation/combobox.html`, mô phỏng đúng hành vi
type-to-filter + click option của autocomplete thật) —
`test_select_combobox_handles_autocomplete_widget_not_native_select`,
`test_select_combobox_requires_explicit_input_selector`.

### 3b. Unilever cụ thể: tìm được đường tốt hơn hẳn combobox

Qua tìm kiếm, xác nhận Unilever có board **Workday CÔNG KHAI thật**:
`unilever.wd3.myworkdayjobs.com/Unilever_Experienced_Professionals` — khớp
CHÍNH XÁC pattern URL adapter Workday hiện có
(`{tenant}.{wd_number}.myworkdayjobs.com/{site}`) đã dùng cho các công ty khác.
Thay vì chiến đấu với combobox trên `careers.unilever.com` (rủi ro DOM đổi,
chậm hơn, cần browser), chuyển Unilever sang gọi thẳng API Workday:

```yaml
- name: "Unilever"
  url: "https://unilever.wd3.myworkdayjobs.com/Unilever_Experienced_Professionals"
  strategy: "direct"
  ats_hint: "workday"
  ats_params: { tenant: "unilever", wd_number: "wd3", site: "Unilever_Experienced_Professionals" }
```

API trả về job ở MỌI quốc gia (không lọc sẵn Vietnam phía server) — pipeline
lọc Vietnam qua early location filter như mọi công ty khác, không cần thêm
logic gì. **`select_combobox` vẫn được implement đầy đủ trong engine** (đúng
yêu cầu "Navigation Engine should support combobox/autocomplete widgets") cho
các công ty tương lai thật sự cần — chỉ riêng Unilever không cần dùng tới vì
tìm được đường tắt tốt hơn.

## 4. Bug pipeline: reachability check kép gây false UNREACHABLE (PwC)

**Bug**: sau khi Navigation Engine điều hướng THÀNH CÔNG bằng browser thật
(chứng minh trang load được), `pipeline.py` vẫn gọi `is_url_reachable()`
(request HTTP thuần qua `requests`) lên URL đã resolve — 1 số site (PwC) chặn
request KHÔNG có cookie/session/User-Agent mà browser vừa có, khiến check này
báo SAI `UNREACHABLE` dù trang THỰC SỰ load được (đã tự chứng minh ngay trước
đó).

**Fix**: `run_for_company()` giờ BỎ QUA `is_url_reachable()` hoàn toàn khi
`strategy` cần điều hướng VÀ navigation đã thành công — tín hiệu từ browser
thật đáng tin hơn 1 request HTTP thuần tiếp theo. Company `strategy: "direct"`
(không qua Navigation Engine) giữ NGUYÊN hành vi cũ — luôn check
`is_url_reachable()` như trước (backward compatible).

Test: `test_pwc_style_bug_navigation_success_never_gets_marked_unreachable`,
`test_direct_strategy_still_performs_reachability_check_unaffected`.

## 5. File thay đổi

| File | Thay đổi |
|---|---|
| `src/navigation/actions.py` | Thêm `select_combobox()` |
| `src/navigation/engine.py` | Thêm mô tả log cho `select_combobox` |
| `src/pipeline.py` | Bỏ `is_url_reachable()` khi navigation đã tự chứng minh URL load được |
| `config.yaml` | Sửa Techcombank (text đúng), KPMG (2 bước đúng), Unilever (chuyển sang Workday API trực tiếp) |
| `tests/fixtures/navigation/combobox.html` | **Mới** — fixture autocomplete thật để test |
| `tests/test_navigation.py` | Thêm 2 test cho `select_combobox` |
| `tests/test_pipeline_navigation.py` | Cập nhật test theo hành vi reachability-check mới; thêm 2 test regression |

**Tổng: 141/141 test pass** (`pytest tests/ -v`).

---

# v10 — Six-company root-cause fixes (config-driven, no company branches)

Implements the fixes proposed after live investigation of each failure. Every
fix is config-driven or a generic (non-company-specific) engine/parser change
— no `if company == ...` was introduced anywhere.

## 1. KPMG — generic `optional: true` step flag (new Navigation Engine capability)

`src/navigation/engine.py::_normalize_step()` now pops an `optional` key out of
ANY step's params (usable on `click_text`, `click_css`, `fill`,
`select_option`, etc. — not hardcoded to cookie banners). In
`_run_steps_once()`, if an optional step raises **any** exception — element
not found or something else — it's logged (`⚠ Optional step bỏ qua (...) ->
tiếp tục`) and the sequence continues; only non-optional steps still abort/
retry as before.

`config.yaml` — KPMG now has an optional first step dismissing a OneTrust
cookie banner using OneTrust's fixed, documented button ID
(`#onetrust-accept-btn-handler`, standard across all OneTrust deployments —
platform-level knowledge, not a KPMG-specific guess) before the real
`"Search for jobs"` click.

**Verified with a real browser**, not just unit-mocked: built
`tests/fixtures/navigation/cookie_banner.html` that reproduces the actual
failure mode (a full-page overlay blocking the target click →
`Timeout`, confirming the original diagnosis) and proved the optional dismiss
step unblocks it.

## 2. Nestlé — `click_text` → `click_css` on the verified href

`config.yaml`: `click_css: "a[href*='nestle.com/jobs/search-jobs']"` instead
of matching display text. Avoids the whole class of text-matching fragility
(Vietnamese diacritic encoding, near-duplicate link text, possible async
rendering) since the fix targets a verified, stable URL fragment instead.

## 3. EY-Parthenon — verified direct SuccessFactors URL, no navigation

`config.yaml`: `strategy: "direct"`, `url: "https://careers.ey.com/eyp/"` —
a real, brand-scoped SuccessFactors URL found during investigation, more
precise than the previous EY-wide URL and far more reliable than clicking
through what's likely a tab toggle (not a real link) on the marketing page.
`scrapers/successfactors_csb.py`'s existing 1-hop discovery (already proven
for EY main and Deloitte) takes it from there — zero new code.

## 4 & 5. McKinsey & Vinamilk — browser becomes the reachability check

**Root cause was a bug in shared HTTP utility, not the URLs.**
`src/http_client.py::get()` calls `resp.raise_for_status()`, and
`url_utils.py::is_url_reachable()` catches *any* resulting exception and
returns `False` — collapsing "site blocked our plain HTTP client (403/bot
protection)" and "URL genuinely doesn't exist" into the same signal. Both
companies' URLs were independently reverified as live and current.

**Fix**: `config.yaml` sets `strategy: "landing"` with `navigation: []` for
both — the URL is unchanged. Per the reachability-check fix from the previous
round, when navigation runs (even with zero steps) and succeeds, `pipeline.py`
skips `is_url_reachable()` entirely and trusts the real browser instead —
which gets past bot-blocking the way a human visitor's browser does. Verified
with `test_empty_navigation_list_uses_browser_as_reachability_proof`.

**Not fixed in this round** (flagged, scope intentionally excluded per your
request to avoid bundling): `is_url_reachable()`'s inability to distinguish
"blocked" from "doesn't exist" is a systemic risk that could affect other
companies silently. Worth a dedicated fix later.

## 6. BCG — `networkidle` → `domcontentloaded` in the shared parser

`src/scrapers/playwright_scraper.py`: `wait_until="networkidle"` →
`"domcontentloaded"`. `networkidle` requires 500ms of *zero* network activity
— SPA sites with chat widgets, analytics beacons, or polling (like BCG's
Phenom-People-powered page) may never reach it, causing `goto()` to hang until
timeout even though usable content rendered long ago. This is a documented
Playwright anti-pattern, not BCG-specific, and the fix applies uniformly to
every company using this shared parser (Shopee, Zalo, Monee, and everything
routed through `strict_html.py`).

**Verified with a real local HTTP server** (not mocked) with a slow polling
endpoint that reproduces exactly this failure: confirmed `networkidle` times
out on it while `domcontentloaded` completes in milliseconds and still
extracts the job correctly (`tests/test_playwright_scraper_networkidle.py`).
The existing settle-wait (1500ms) + 4 scroll passes are unchanged, so
well-behaved sites see no reduction in effective wait time — only the
indefinite-hang failure mode is removed.

## Trade-offs

- **KPMG's `optional: true`** only suppresses failures for that one step; if
  the *real* "Search for jobs" click itself is ever wrong, the sequence still
  fails loudly as before — optional is deliberately scoped to the cookie-step
  only, not a blanket "ignore errors" mode.
- **McKinsey/Vinamilk now launch a full headless browser** on every run
  instead of a lightweight HTTP HEAD/GET, which is slower and heavier per
  company. Accepted trade-off: correctness (not silently skipping a working
  company) over speed, consistent with the "accuracy over speed" directive
  for this whole effort. `MAX_WORKERS` bounds overall concurrency so this
  doesn't scale unboundedly.
- **EY-Parthenon's new URL is brand-scoped**, which may return a narrower job
  set than the previous EY-wide URL — intentional, since narrower-but-correct
  is preferable to broader-but-fragile for this specific brand.
- **domcontentloaded fires earlier than networkidle** in general, so pages
  with genuinely important content that loads *very* late (beyond the
  existing 1500ms + scroll-pass budget) could theoretically be captured
  slightly less completely than before — mitigated by the existing settle
  wait, but not eliminated. No regression observed against any currently
  configured company's expected structure.

## Files changed

| File | Change |
|---|---|
| `src/navigation/engine.py` | Generic `optional: true` step flag |
| `src/scrapers/playwright_scraper.py` | `networkidle` → `domcontentloaded` |
| `config.yaml` | KPMG (optional cookie step), Nestlé (click_css), EY-Parthenon (direct URL), McKinsey (landing + empty nav), Vinamilk (landing + empty nav) |
| `tests/fixtures/navigation/cookie_banner.html` | **New** — real cookie-banner-blocking-click fixture |
| `tests/test_navigation.py` | +5 tests for `optional` flag (including the KPMG scenario end-to-end) |
| `tests/test_pipeline_navigation.py` | +1 test for empty-navigation reachability pattern |
| `tests/test_playwright_scraper_networkidle.py` | **New** — real local-server regression test for the BCG fix |

**Total: 147/147 tests pass** (`pytest tests/ -v`), including 24 tests exercising a real headless browser (not mocked) and 1 exercising a real local HTTP server.

---

# v11 — Follow-up fixes with concrete DOM/documented-pattern evidence

This round required actual re-fetching of live pages rather than reasoning
from earlier findings — two of the four (Nestlé, Vinamilk) turned up new
evidence that **contradicted** conclusions from the previous round. Documented
here plainly, including where confidence is still incomplete.

## 1. KPMG — cross-domain cookie consent (SAP, not OneTrust)

**Confirmed via direct fetch**: "View All Jobs" text is real (footer nav,
`careers.kpmg.com.vn/`, verbatim `[View All Jobs](.../viewalljobs/ "View All
Jobs")`). The click still failing points to the same failure class as before,
one hop later — the page explicitly states its cookie consent is delivered by
**"SAP as service provider"**, a different system than the OneTrust banner on
`kpmg.com`. Since cookies are domain-scoped, navigating from `kpmg.com` to
`careers.kpmg.com.vn` plausibly triggers a **fresh** consent banner our
existing OneTrust-only dismiss step can't see. The literal button text
**"Accept All Cookies"** was directly observed in that page's HTML — used
as-is, not guessed.

`config.yaml`: added a second `optional: true` step (`click_text: "Accept All
Cookies"`) between the domain hop and the "View All Jobs" click.

**Open / unconfirmed**: static fetch of `/viewalljobs/` shows the same
carousel/hero content as the KPMG homepage, not an obvious job-listing table —
whether this page contains extractable job data even once reached couldn't be
confirmed without JS execution. Flagged for verification against real run
logs after this fix ships.

## 2. Nestlé — the previous fix's URL was itself wrong

**Direct fetch evidence**: `nestle.com/jobs/search-jobs` (global bare domain,
what was configured after the last round) is not the real page. The actual,
live, working search page — directly fetched, showing 10 real current Vietnam
postings (Medical Brand Manager, Category Executive, etc.) — is
`www.nestle.com.vn/en/jobs/search-jobs`, same domain as the entry page. The
entry page's own nav menu links to the `/vi/` locale variant of the same URL.
`config.yaml` updated to target that verified href directly.

## 3. McKinsey — documented Chromium bug, not anti-bot

Could not reproduce the HTTP/2 handshake myself (no live network access to
mckinsey.com from this environment), so this is **documented-pattern research**,
not direct reproduction — labeled as such deliberately. Multiple independent
sources, including Playwright's own issue tracker (maintainers tagged it
"a bug in something Playwright depends on, like a browser" —
[#31240](https://github.com/microsoft/playwright/issues/31240),
[#36001](https://github.com/microsoft/playwright/issues/36001)), converge on
`net::ERR_HTTP2_PROTOCOL_ERROR` under legacy headless Chromium being fixed by
`--headless=new`. Applied to `navigation/engine.py` and, for consistency
(same underlying browser bug, not McKinsey-specific), to
`scrapers/playwright_scraper.py`.

## 4. Vinamilk — still not fully resolved, said so directly

Found real evidence the site has fragmented across three live domains
(`www.vinamilk.com.vn`, `new.vinamilk.com.vn`, `careers.vinamilk.com.vn`).
The previously-configured path (no locale prefix) did not surface in fresh
search results; the `/en/` variant did, with postings dated within the last
month. Switched to that path as the best-evidenced option available.
**I could not confirm this resolves "Playwright succeeds, 0 jobs"** — said
so explicitly rather than asserting a fix I haven't verified. Needs a real
run to confirm.

## Files changed

| File | Change |
|---|---|
| `src/navigation/engine.py` | `args=["--headless=new"]` on Chromium launch |
| `src/scrapers/playwright_scraper.py` | Same flag, applied for consistency |
| `config.yaml` | KPMG (2nd optional cookie step), Nestlé (corrected real URL), Vinamilk (corrected URL, unresolved root cause flagged) |

**Total: still 147/147 tests pass** (no new tests added this round — the
changes are config data and a one-line launch-arg fix already covered by
existing navigation/engine and playwright_scraper test suites).

## Honesty note on tooling limits

I do not have live network access to any of these four domains from this
environment (sandboxed egress is allowlisted to package registries only), and
my fetch tool does not execute JavaScript. Everything above is either (a) a
concrete match found in a real static HTML fetch, explicitly marked as such,
or (b) documented external research, explicitly marked as such — never
presented as a live browser reproduction I didn't actually perform.
