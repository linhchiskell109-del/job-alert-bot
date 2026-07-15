# Job Alert Bot v2

Bot chạy tự động trên GitHub Actions, quét career page của ~20-30 công ty, lọc job
theo từ khoá/level/location, và gửi email khi có job mới phù hợp — **không cần
inspect DevTools hay khai báo CSS selector cho từng công ty**.

**Nguồn dữ liệu: career page chính thức của từng công ty** (không scrape LinkedIn —
LinkedIn cấm scraping trong Terms of Service và sẽ block IP/tài khoản rất nhanh).

---

## 1. Vì sao refactor so với v1

Bản v1 yêu cầu khai báo `type` (workday/greenhouse/lever/playwright) và CSS
selector thủ công cho **từng công ty** — nghĩa là mỗi khi 1 công ty đổi giao diện
career page, bot hỏng và bạn phải mở lại DevTools để tìm selector mới. Với 20-30
công ty theo dõi trong nhiều tháng, đây là gánh nặng bảo trì không nhỏ.

v2 thiết kế lại theo hướng **tự nhận diện thay vì khai báo thủ công**:

| | v1 | v2 |
|---|---|---|
| Khai báo mỗi công ty | `name`, `url`, `type`, 4 CSS selector | chỉ `name` + `url` |
| Nhận diện ATS | thủ công | tự động (`ats_detector.py`) |
| Tìm job trong HTML | CSS selector hardcode/công ty | heuristic dùng chung 1 lần cho mọi công ty (`heuristics.py`) |
| Khi site đổi giao diện | phải sửa selector | heuristic dựa trên pattern URL (`/jobs/`, `/tuyen-dung/`...) nên bền hơn nhiều với thay đổi giao diện — chỉ cần sửa khi họ đổi hẳn URL scheme |
| Nếu 1 site dùng URL pattern lạ | sửa code riêng cho site đó | thêm 1 dòng vào `extra_job_url_keywords` trong config.yaml (không đụng code) |
| Mạng lỗi tạm thời | script fail luôn | tự động retry với exponential backoff |
| Tốc độ | tuần tự, 22 công ty ~vài phút | chạy song song (ThreadPoolExecutor), nhanh hơn nhiều |
| Trùng job khi URL đổi param | báo trùng liên tục | hash dựa trên company+title+location, không chỉ URL |

## 2. Kiến trúc

```
GitHub Actions (cron mỗi 6h, chạy song song N công ty + shared portal cùng lúc)
  -> src/main.py
       -> với mỗi công ty VÀ mỗi shared portal (song song qua ThreadPoolExecutor):
            src/pipeline.py:
              0. url_utils.is_url_reachable(url)
                   -> URL chết/không truy cập được -> log WARN + BỎ QUA công ty
                      (không tự đoán URL khác)
              1. ats_detector.detect(url)
                   -> phát hiện Workday/Greenhouse/Lever/SmartRecruiters (có
                      adapter public API) hoặc SAP SuccessFactors/Oracle
                      Recruiting (chỉ nhận diện để log, không có API public tin
                      cậy) qua URL/HTML — tự động, không khai báo thủ công
              2. Nếu là ATS có adapter (Workday/Greenhouse/Lever/SmartRecruiters)
                   -> gọi thẳng API JSON công khai — nhanh, ổn định nhất
              3. Nếu không -> html_scraper.py (requests + BeautifulSoup)
                   -> heuristics.py tự nhận diện job link trong HTML tĩnh
              4. Nếu html_scraper trả về 0 job -> playwright_scraper.py
                   (render JS) -> heuristics.py áp DỤNG LẠI CÙNG heuristic
                   trên HTML đã render
            [Nếu là shared portal, vd VNG+ZaloPay]: scrape đúng 1 lần bằng pipeline
            trên rồi pipeline.classify_job_brand() phân loại từng job theo brand
            bằng từ khoá, thay vì crawl cùng 1 URL nhiều lần
       -> lọc job theo config.yaml (keyword + level + location) — KHÔNG ĐỔI
       -> so với state.json (hash company+title+location, không chỉ URL) — KHÔNG ĐỔI
       -> job MỚI + MATCH -> gửi email gộp theo công ty (src/notifier.py) — KHÔNG ĐỔI
       -> commit lại state.json vào repo
```

Mọi URL (trong `config.yaml` lẫn URL job tìm được khi scrape) đều được
`url_utils.normalize_url()` bỏ tracking param (`utm_*`, `fbclid`, `gclid`,
`srsltid`...) trước khi lưu/dùng — các query param cần thiết như `?locale=vi_VN`
được giữ nguyên.

Mọi network request (ATS API, HTML fetch, ats_detector probe, reachability
check) đều đi qua `src/http_client.py`, có retry tự động với exponential backoff
khi gặp lỗi mạng tạm thời hoặc HTTP 429/500/502/503/504.

### ATS được hỗ trợ

| ATS | Cách route | Ghi chú |
|---|---|---|
| Workday | API JSON public | `src/scrapers/workday.py` |
| Greenhouse | API JSON public | `src/scrapers/greenhouse.py` |
| Lever | API JSON public | `src/scrapers/lever.py` |
| SmartRecruiters | API JSON public | `src/scrapers/smartrecruiters.py` |
| SAP SuccessFactors | Nhận diện, route sang HTML/Playwright | không có API public tin cậy không cần xác thực |
| Oracle Recruiting Cloud | Nhận diện, route sang HTML/Playwright | không có API public tin cậy không cần xác thực |
| Khác (site tự build) | HTML scraper -> Playwright fallback | heuristic, không cần selector |

### Shared portal (1 trang career cho nhiều brand)

VNG và ZaloPay cùng đăng tuyển trên `career.vng.com.vn`. Thay vì khai báo 2 công
ty crawl cùng 1 URL (lãng phí, và không tách được job của ai), `config.yaml` khai
báo 1 mục trong `shared_portals` với danh sách `brands` + từ khoá phân loại:

```yaml
shared_portals:
  - name: "VNG Careers Portal"
    url: "https://career.vng.com.vn/"
    brands:
      - company: "ZaloPay"
        match_keywords: ["zalopay", "zalo pay", "ví zalopay"]
      - company: "VNG"
        default: true   # bucket mặc định cho job không khớp brand nào khác
```

Portal được scrape **đúng 1 lần**; mỗi job sau đó được `pipeline.classify_job_brand()`
phân loại theo brand dựa trên từ khoá xuất hiện trong title/department/description
(không phân biệt hoa-thường/dấu). Zalo có trang career riêng
(`https://zalo.careers/`) nên vẫn là 1 mục độc lập trong `companies`, không nằm
trong shared portal này.

### Vì sao ưu tiên HTML scraper trước Playwright

Nhiều trang career hiện đại — kể cả app Next.js/Nuxt — render sẵn danh sách job
ngay trong HTML trả về từ server (SSR/SSG). Ví dụ MoMo: danh sách job đã có sẵn
trong HTML ban đầu, không cần chạy JavaScript để thấy. `html_scraper.py`
(requests + BeautifulSoup) xử lý các trường hợp này nhanh hơn Playwright hàng
chục lần và không tốn tài nguyên chạy Chromium. Playwright chỉ được gọi khi
`html_scraper` thực sự trả về **0 job** — dấu hiệu trang cần JS để render list.

### Vì sao không cần CSS selector

`src/heuristics.py` tìm job bằng cách quét mọi thẻ `<a href>` trong trang và giữ
lại các href có pattern giống link job — hỗ trợ cả tiếng Anh (`/jobs/`,
`/careers/`, `/positions/`, `/openings/`, `/vacancy/`, `/roles/`) lẫn tiếng Việt
(`/tuyen-dung/`, `/viec-lam/`, `/vi-tri/`, `/co-hoi-nghe-nghiep/`...), loại các
href chỉ trỏ về trang danh sách (không có id/slug cụ thể). Title được lấy từ
heading gần nhất hoặc text của link; location được tìm bằng cách quét phần tử có
class/id chứa "location"/"place"/"dia-diem" gần đó. Cùng 1 hàm này dùng cho cả
`html_scraper` và `playwright_scraper` — sửa 1 chỗ, áp dụng cho toàn bộ 20-30
công ty.

## 3. Setup

1. Tạo repo mới trên GitHub, push toàn bộ project này lên.
2. Tạo **Gmail App Password** (không dùng mật khẩu Gmail thật):
   - Bật 2-Step Verification cho Gmail
   - Vào https://myaccount.google.com/apppasswords -> tạo app password mới
3. Vào repo -> Settings -> Secrets and variables -> Actions -> New repository
   secret, thêm 3 secrets:
   - `EMAIL_USER`: email Gmail dùng để gửi
   - `EMAIL_PASS`: app password vừa tạo ở bước 2
   - `EMAIL_TO`: email bạn muốn nhận thông báo (có thể trùng `EMAIL_USER`)
4. Vào tab **Actions** -> bật workflow nếu bị tắt mặc định.
5. Chạy thử: Actions -> "Job Alert Bot" -> "Run workflow" để test trước khi đợi
   lịch cron.

**Không có bước "tìm CSS selector" nào cả** — chỉ cần đúng URL career page trong
`config.yaml` (đã điền sẵn, verify thủ công cho 20 công ty + 1 shared portal
2 brand [VNG/ZaloPay] = 22 công ty theo yêu cầu ban đầu). Xem `MIGRATION.md` để
biết chi tiết URL nào đã được cập nhật trong lần verify gần nhất.

## 4. Khi nào cần chỉnh sửa (và chỉnh ở đâu)

Vì kiến trúc dựa trên heuristic thay vì selector cứng, bot **bền hơn nhiều** với
việc công ty đổi giao diện UI — miễn URL job vẫn theo pattern tương tự
(`/xxx/slug-id`), heuristic vẫn nhận ra dù class/CSS đổi hoàn toàn. Có 3 tình
huống thật sự cần bạn can thiệp:

**A. Log báo `[UNREACHABLE] <company>` hoặc "career URL không truy cập được"**
URL trong `config.yaml` đã chết/sai — bot **tự động bỏ qua công ty đó** thay vì
đoán mò URL khác (không có trường hợp nào bot tự tạo domain thay thế). Cách sửa
duy nhất: cập nhật lại `url` đúng trong `config.yaml`.

**B. Log báo `[NONE] <company>: 0 job(s)` liên tục**
Khác với UNREACHABLE — URL vẫn truy cập được, nhưng cả `html_scraper` lẫn
`playwright_scraper` đều không tìm thấy link nào khớp pattern job. Nguyên nhân
thường gặp và cách sửa — **không cái nào cần DevTools/CSS selector**:
- Trang dùng path pattern lạ, không có trong danh sách mặc định (vd
  `/co-hoi-viec-lam/` thay vì `/tuyen-dung/`) -> thêm từ khoá vào
  `extra_job_url_keywords` trong `config.yaml`, ví dụ:
  ```yaml
  extra_job_url_keywords:
    - "co-hoi-viec-lam"
  ```

**C. Muốn ép 1 công ty dùng thẳng ATS đã biết (tối ưu tốc độ)**
Nếu bạn tình cờ biết chắc 1 công ty dùng Workday/Greenhouse/Lever/SmartRecruiters
(vd thấy trong log `[WORKDAY]`/`[GREENHOUSE]`/`[LEVER]`/`[SMARTRECRUITERS]` ở lần
chạy trước), có thể khai báo thẳng để bỏ qua bước auto-detect (tiết kiệm 1
request), hoàn toàn tuỳ chọn:
```yaml
- name: "Some Company"
  url: "https://somecompany.com/careers"
  ats_hint: "greenhouse"
  ats_params: { board_token: "somecompany" }
```

## 5. Tuỳ chỉnh filter

Sửa trong `config.yaml`:
- `jd_keywords`: danh sách từ khoá JD (đã điền sẵn theo yêu cầu ban đầu)
- `levels`: danh sách level (đã điền sẵn)
- `locations`: danh sách địa điểm (đã điền sẵn: VN/HN/HCMC...)
- `match_mode: "AND"`: job phải khớp keyword AND level AND location. Đổi thành
  `"keyword_only"` nếu chỉ muốn lọc theo keyword.

## 6. Đổi tần suất chạy

Sửa `cron` trong `.github/workflows/job-alert.yml`:
- `"0 */6 * * *"` — mỗi 6 tiếng (mặc định)
- `"0 8,20 * * *"` — 8h sáng và 8h tối UTC (15h và 3h sáng giờ VN)
- `"0 2 * * *"` — 1 lần/ngày lúc 2h UTC (9h sáng giờ VN)

Số công ty fetch song song: env `MAX_WORKERS` trong workflow (mặc định 6). Số
browser Playwright chạy đồng thời: env `PLAYWRIGHT_MAX_CONCURRENCY` (mặc định 2,
để tránh quá tải runner miễn phí của GitHub Actions).

## 7. Chạy thử ở local

```bash
pip install -r requirements.txt
python -m playwright install --with-deps chromium

# chạy test trước khi chạy thật
pytest tests/ -v

export EMAIL_USER="you@gmail.com"
export EMAIL_PASS="app-password"
export EMAIL_TO="you@gmail.com"

python src/main.py
```

Log sẽ in ra method đã dùng cho từng công ty, ví dụ:
```
[WORKDAY   ] KPMG Vietnam: 14 job(s)
[HTML      ] MoMo (M_Service): 8 job(s)
[PLAYWRIGHT] Shopee: 22 job(s)
[NONE      ] Monee: 0 job(s)
```
`[NONE]` là dấu hiệu cần xem lại URL hoặc thêm `extra_job_url_keywords` (mục 4A).

## 8. Kiểm thử tự động

Project có bộ test (`tests/`, chạy bằng `pytest`) bao phủ:
- `test_heuristics.py`: heuristic nhận diện job link đúng với HTML tiếng Việt
  (Next.js SSR), query-string-based job link, title lẫn trong anchor có location.
- `test_ats_detector.py`: nhận diện đúng Workday/Greenhouse/Lever/SmartRecruiters/
  SAP SuccessFactors/Oracle Recruiting từ URL/HTML.
- `test_url_utils.py`: normalize_url bỏ đúng tracking param (`utm_*`, `fbclid`,
  `gclid`, `srsltid`...) và giữ nguyên param chức năng (`?locale=vi_VN`).
- `test_pipeline.py`: phân loại job theo brand cho shared portal (VNG/ZaloPay)
  đúng theo từ khoá, không phân biệt dấu/hoa-thường, fallback đúng về brand mặc định.
- `test_state.py`: hash job ổn định qua thời gian dù URL đổi query string, không
  phân biệt dấu/hoa-thường.
- `test_filters.py`: lọc keyword/level/location đúng, có word-boundary tránh
  match nhầm (vd "ops" không match trong "shops").

Workflow GitHub Actions chạy `pytest tests/` trước khi chạy `main.py` — nếu logic
lọc/hash bị lỗi do sửa code, workflow sẽ fail sớm thay vì gửi email sai.

## 9. Giới hạn đã biết (trade-off có chủ đích)

- **Dedupe theo company+title+location**: nếu 1 công ty đăng lại đúng title +
  location đó ở đợt tuyển dụng sau, bot sẽ coi là job cũ và không báo lại. Đổi
  lại, bot không bị báo trùng liên tục mỗi khi URL đổi query string/tracking
  param — trade-off được chọn có chủ đích vì trường hợp URL đổi phổ biến hơn
  nhiều so với việc đăng lại đúng 1 job.
- **Heuristic không phải 100% chính xác cho mọi trang**: 1 số trang có thể dùng
  URL pattern hoàn toàn khác biệt (không path-based, hoàn toàn dựa vào JS state
  không lộ URL) — trường hợp hiếm, nhưng nếu gặp, mục 4B trong README này áp
  dụng vẫn không đủ. Khi đó cần mở issue/tự thêm 1 adapter riêng trong
  `src/scrapers/` (project vẫn hỗ trợ escape hatch `ats_hint` cho các case đặc
  biệt).
- **SAP SuccessFactors / Oracle Recruiting Cloud**: được nhận diện (log rõ) nhưng
  không có adapter gọi API JSON trực tiếp — vì 2 nền tảng này không có endpoint
  public ổn định không cần xác thực (khác với Greenhouse/Lever/SmartRecruiters/
  Workday). Các công ty dùng 2 ATS này sẽ tự động route qua HTML scraper rồi
  Playwright fallback — hoạt động tốt trong đa số trường hợp nhưng không nhanh/
  ổn định bằng gọi API trực tiếp.
- **URL trong `config.yaml` đã được xác nhận thủ công** (không phải bot tự đoán)
  tại thời điểm cập nhật gần nhất. Sandbox chạy code này không có egress ra
  internet công khai nên không tự động re-verify được — nếu 1 công ty đổi domain
  career trong tương lai, bot sẽ tự phát hiện (log `UNREACHABLE`) và bỏ qua công
  ty đó thay vì báo sai, nhưng bạn vẫn cần tự cập nhật URL mới trong
  `config.yaml` (mục 4A).

## 10. Lưu ý pháp lý / kỹ thuật

- Bot chỉ đọc dữ liệu **public** trên trang career chính thức — không login,
  không bypass paywall/captcha.
- Kiểm tra `https://<domain>/robots.txt` của từng trang nếu muốn chắc chắn tuân
  thủ, và không set tần suất quá dày (mặc định 6h/lần là mức an toàn).
- Không dùng bot này để scrape LinkedIn trực tiếp — vi phạm Terms of Service của
  LinkedIn và dễ bị khoá tài khoản/IP.
