# Benchmark & Observability Report — Day 14

**Họ tên:** Luu Dang Tuan (MSSV: 2A202603454)  
**Ngày chạy:** 2026-11-25  
**Môi trường:** Windows 11 + WSL2 Ubuntu 24.04 (Python 3.12.3), Docker Desktop 29.9.3 / Docker Compose v5.7.0

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
| --- | --- | --- |
| p95 latency `/ask` | `< 500 ms` | Đảm bảo trải nghiệm phản hồi tức thời cho 95% người dùng (tương ứng cấu hình mặc định trong `load_test.py`) |
| Error rate `/ask` | `< 2.0 %` | Cho phép một phần lỗi upstream nhỏ (1% mock error rate) nhưng cảnh báo ngay khi vượt ngưỡng ổn định |
| Accuracy trên golden dataset | `≥ 95 %` (mục tiêu `100 %`) | Đảm bảo agent trả lời chính xác kiến thức cốt lõi và không bị regression khi thay đổi prompt/KB |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

Số liệu khớp trực tiếp với `reports/load_v2_c1.json` → `reports/load_v2_c100.json` (300 requests/mức):

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 3.94 | 194.9 | 228.2 | 1706.0 | 0.33% | ✅ PASS |
| 10 | 34.29 | 201.6 | 288.9 | 1718.2 | 1.00% | ✅ PASS |
| 50 | 64.61 | 294.5 | 1623.1 | 2519.0 | 1.33% | ❌ FAIL (`p95 > 500ms`) |
| 100 | 40.86 | 792.6 | 5091.3 | 5394.5 | 1.00% | ❌ FAIL (`p95 > 500ms`) |

**Nhận xét:** RPS **không** tăng tuyến tính theo concurrency. Từ concurrency 1 → 10 → 50, RPS tăng từ 3.94 → 34.29 → 64.61 req/s, nhưng đến concurrency 100 thì RPS **giảm** còn 40.86 req/s trong khi p95 vọt lên `5091.3 ms`. Nguyên nhân là một process `uvicorn` đơn bị bão hòa (event loop & socket queueing + context switching) khi quá nhiều request đồng thời tranh chấp tài nguyên, làm hàng đợi kéo dài theo định luật Little.

### 2.2 Tail latency

Số liệu khớp trực tiếp với `reports/load_v2_slow_0.json`, `reports/load_v2_slow_0.03.json`, `reports/load_v2_slow_0.1.json` (300 requests, `concurrency=20`):

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
| --- | ---: | ---: | ---: |
| `0` | 199.9 | 246.3 | 279.6 |
| `0.03` (mặc định) | 260.6 | 249.9 | 1704.8 |
| `0.1` | 397.0 | 1692.7 | 1719.2 |

**Nhận xét:** **p99** (và khi tỷ lệ chậm ≥ 5% thì cả **p95**) nhạy nhất với request chậm. Khi `MOCK_SLOW_RATE=0.03`, `avg` chỉ tăng nhẹ từ `199.9 ms` lên `260.6 ms` (che giấu hoàn toàn sự cố), trong khi `p99` nhảy vọt hơn 6 lần lên `1704.8 ms`. Vì vậy SLO phải đặt theo p95/p99 để phản ánh đúng trải nghiệm của nhóm người dùng bị chậm (tail latency).

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Số liệu khớp trực tiếp với `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json`:

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
| --- | --- | --- | --- |
| Accuracy | 4.35% (1/23) | 91.3% (21/23) | **100.0% (23/23)** |
| Avg tokens / câu | 57.7 | 109.1 | 113.1 |
| Tổng cost (USD) | $0.000413 | $0.000762 | $0.000786 |
| Cost / câu đúng (USD) | $0.00041295 | $0.00003627 | **$0.00003417** |
| Quality gate | ❌ FAIL | ✅ PASS (≥ 80%) | ✅ PASS (≥ 100%, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
| --- | --- | --- |
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry về JWT (`["jwt", "xác thực"]`) vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py`) |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry về Kubernetes HPA (`["hpa", "kubernetes"]`) vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py`) |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**
- `v1` nhanh hơn một chút (`p95=183.5 ms`, `57.7 tokens/câu`) và tổng cost thấp hơn (`$0.000413`), nhưng chỉ đúng `1/23` câu (`4.35%`) vì không có retrieval.
- `v2` tốn thêm bước retrieve (~20 ms) và gần gấp đôi token (`113.1 tokens/câu`, tổng cost `$0.000786`), nhưng độ chính xác tăng lên `100% (23/23)`. Nhờ vậy **cost / câu đúng** của `v2` (`$0.00003417`) rẻ hơn **12 lần** so với `v1` (`$0.00041295`).
- **CI/CD Quality Gate:** Chạy `python eval/run_eval.py --min-accuracy 1.0 --baseline reports/eval_v2.json` trong pipeline CI (GitHub Actions / Cloud Build); script trả **exit code `1`** nếu accuracy dưới ngưỡng hoặc có bất kỳ câu nào bị regression, giúp CI tự động chặn merge PR trước khi deploy.

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): [grafana-dashboard.png](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian): [jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (có event `exception`): [jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với 2 alerts đang **firing**: [prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
| --- | --- | --- | --- | --- |
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`> 5%`, `for: 1m`) | ~`70s` (pending sau ~10s + `for: 1m`) | **Error rate** (vọt lên ~`20.9%`) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`> 1s`, `for: 2m`) | ~`2m15s` (theo rule `for: 2m`) | **Latency p95** (vượt `1.5s`) |
| C | `LLM_MODEL=mock-llm-large` / tải cao | `LLMCostBurnRateHigh` (`> $2/giờ`, `for: 2m`) | ~`2m` (đã ghi nhận firing lúc `09:01:42Z` trong đợt tải cao) | **LLM cost (1h)** |
| D | `docker pause` 1 instance (`agent-2`) | `AgentInstanceDown` (`up == 0`, `for: 30s`) | ~`45s` (scrape fail sau ~15s + `for: 30s`) | **Instances up** (giảm `2 → 1`) |
| E | `AGENT_VERSION=v1` | Không có alert nào firing | N/A | Không panel infra nào báo lỗi (HTTP vẫn 200) |

**Thí nghiệm E không làm alert nào firing. Cách phát hiện loại sự cố này trong production:**
1. **Offline CI/CD eval gate:** chạy `eval/run_eval.py` trên golden dataset ở mọi PR/release; chặn deploy nếu accuracy giảm hoặc có regression.
2. **Online quality monitoring:** lấy mẫu (sampling) các hội thoại production chạy qua LLM-as-a-judge / kiểm tra citation/keyword, theo dõi tín hiệu người dùng (thumbs down, tỷ lệ hỏi lại/retry), và chạy **canary deployment** so sánh chất lượng giữa phiên bản mới và cũ trước khi roll out 100%.

### 4.3 Debug bằng trace

Trace chậm nhất tìm được trong Jaeger & log:

- `trace_id`: `c7ab784d3cfe956ba7a89dd8b0225aa8`
- Tổng thời gian: `2631.9 ms` (HTTP middleware log: `2621.6 ms`)
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-small`** (`1796.2 ms`, chiếm **68.2%** tổng trace và **94.8%** thời gian của `agent.run` `1895.2 ms`; trong khi `agent.retrieve_context` chỉ tốn `98.7 ms` ~ 3.7%)
- Dòng log JSON tương ứng (khớp `trace_id`):

```json
{"ts": "2026-11-25T09:02:57.018315+00:00", "level": "INFO", "service": "observable-agent", "instance": "4076ef6c01ba", "event": "http_request", "trace_id": "c7ab784d3cfe956ba7a89dd8b0225aa8", "span_id": "f0d8eb3c48eca44b", "request_id": "f9b4d9a8ef2d", "method": "POST", "route": "/ask", "status": 200, "ms": 2621.6}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu khớp trực tiếp với `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv` (hàng `Aggregated`; trong ngoặc là riêng `POST /ask`):

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 62.78 *(57.20)* | 200 *(210)* | 880 *(960)* | 1800 *(1800)* | 74 (1.00%) |
| 3 | 61.09 *(55.87)* | 210 *(210)* | 1200 *(1300)* | 1800 *(1800)* | 63 (0.87%) |

**Giải thích kết quả:** Scale từ 1 lên 3 instance **không** làm giảm p95/p99 hay tăng RPS trong bài đo này. Lý do là nút thắt không nằm ở CPU của FastAPI (vốn chạy async I/O rất nhẹ) mà nằm ở:
1. **Upstream LLM latency & tail latency** (`MOCK_LATENCY_MS=120`, `MOCK_SLOW_RATE=0.03` cộng `+1500 ms` vào mỗi request chậm → p99 luôn xoay quanh ~`1800 ms` dù có bao nhiêu instance).
2. **Giới hạn tải đầu vào từ Locust** (100 user với thời gian chờ giữa các request khiến tổng RPS tối đa chỉ quanh ~61–63 req/s — 1 instance async vẫn gánh được mức tải này, còn chạy 3 container cùng lúc trên cùng 1 máy host Docker Desktop còn chia sẻ chung CPU/network host).

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. Không bao giờ đánh giá hiệu năng chỉ bằng latency trung bình — phải đo theo **p95/p99** để thấy tail latency và đặt SLO rõ ràng.
  2. **Cost / câu đúng** kết hợp với **eval quality gate** quan trọng hơn nhiều so với chỉ nhìn chi phí thô hoặc hạ tầng (HTTP 200 không đồng nghĩa câu trả lời đúng).
  3. Ba trụ cột **Metrics (Prometheus/Grafana) + Traces (Jaeger/OTel) + Structured JSON Logs** liên kết qua `trace_id` giúp rút ngắn thời gian tìm nguyên nhân gốc (root cause) từ hàng giờ xuống vài giây.
- **Nếu đưa agent lên production thật, sẽ thêm metric / alert:**
  - **TTFT (Time-To-First-Token)** và **tokens/giây** cho streaming response.
  - **Cache hit rate / Retrieval relevance score** (phát hiện suy giảm chất lượng RAG sớm).
  - **Rate-limit rejection rate (`429`)** & **Budget exhaustion (`402`)** theo từng tenant/API key.
  - **Redis latency & connection pool saturation** để phát hiện nghẽn ở tầng lưu trữ state.
