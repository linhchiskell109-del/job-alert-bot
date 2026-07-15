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
