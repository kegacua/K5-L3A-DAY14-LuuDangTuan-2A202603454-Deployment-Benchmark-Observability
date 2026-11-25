# Day 14 Lab — Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns tìm thấy trong `01-localhost-vs-production/develop/app.py`

1. **Hardcode secrets trong source code** (dòng 17–18): `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`. Nếu push lên Git, key và mật khẩu sẽ lộ vĩnh viễn trong lịch sử commit. (`production/app.py` sửa bằng cách đọc qua `config.settings` từ biến môi trường.)
2. **Không có config management theo môi trường** (dòng 21–22): `DEBUG = True`, `MAX_TOKENS = 500` viết cứng trong code, không thể đổi giữa dev / staging / production mà không sửa code.
3. **Dùng `print()` thay cho structured logging và log lộ secret** (dòng 33–34, 38): `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` vừa khó parse/tìm kiếm trên hệ thống log tập trung, vừa làm rò rỉ API key ra stdout. (`production/app.py` dùng `logging` định dạng JSON và không log secret.)
4. **Thiếu endpoint health check (`/health`) và readiness (`/ready`)** (dòng 42–43): platform/orchestrator không biết process còn sống hay đã sẵn sàng nhận traffic để tự restart hoặc tách khỏi load balancer. (`production/app.py` bổ sung `/health` ở dòng 135 và `/ready` ở dòng 152.)
5. **Bind `host="localhost"` và hardcode `port=8000`** (dòng 51–52): trong container hoặc trên cloud, `localhost` chặn kết nối từ bên ngoài, còn port cứng xung đột với biến `PORT` do Railway/Render cấp. (`production/app.py` đọc `settings.host` = `0.0.0.0` và `settings.port` từ `PORT`.)
6. **Bật `reload=True` khi chạy** (dòng 53): auto-reload tốn CPU/file watcher và gây rủi ro không ổn định trên production.
7. **Không có graceful shutdown**: không có `lifespan` hay xử lý `SIGTERM`, khi tắt server các request đang xử lý bị cắt ngang đột ngột.

### Exercise 1.2: Kết quả chạy bản `develop`

```bash
curl -sS -i -X POST "http://localhost:8000/ask?question=Hello"
```

```text
HTTP 200
{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

### Exercise 1.3: Bảng so sánh `develop` vs `production`

| Feature | Develop (`develop/app.py`) | Production (`production/app.py`) | Tại sao quan trọng? |
| --- | --- | --- | --- |
| **Config & Secrets** | Hardcode trực tiếp (`OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG=True`) | Đọc từ biến môi trường qua `config.py` (12-Factor) | Dùng chung 1 artifact/image cho dev, staging, prod; tránh lộ secret trong Git |
| **Logging** | `print()` plain text, còn in cả `OPENAI_API_KEY` | Structured JSON logging qua `logging`, không log secret | Log aggregator (Loki/Datadog/ELK) dễ parse, lọc theo field, không rò rỉ thông tin nhạy cảm |
| **Health / Readiness** | Không có | Có `GET /health` (liveness) và `GET /ready` (readiness) | Platform tự restart khi app treo và load balancer ngừng route traffic khi app chưa sẵn sàng |
| **Host & Port** | `localhost:8000` cố định | `0.0.0.0` và đọc `PORT` từ env | Container/cloud cần lắng nghe mọi interface và dùng port động do platform cấp |
| **Graceful Shutdown** | Không xử lý, tắt đột ngột | FastAPI `lifespan` + xử lý `SIGTERM` | Hoàn tất request in-flight và đóng kết nối DB/Redis an toàn, không làm lỗi người dùng khi deploy/restart |
| **Debug / Reload** | `reload=True` cố định | Chỉ bật khi `DEBUG=true` | Tránh overhead và hành vi bất thường trên production |
| **CORS & Validation** | Nhận query param thô, không giới hạn CORS | `CORSMiddleware` giới hạn origin, validate body trả HTTP 422 | Bảo vệ API khỏi request không hợp lệ và truy cập cross-origin trái phép |

---

## Part 2: Docker

### Exercise 2.1: Trả lời 4 câu hỏi về Dockerfile

1. **Base image:** `python:3.11` (bản `develop`, full Debian + build tools ~1 GB) hoặc `python:3.11-slim` (bản `production`, gọn nhẹ hơn nhiều). Base image cung cấp hệ điều hành nền và Python runtime để chạy ứng dụng.
2. **Working directory (`WORKDIR /app`):** đặt thư mục làm việc mặc định bên trong container là `/app`; mọi lệnh `COPY`, `RUN`, `CMD` sau đó đều chạy tương đối từ `/app`, giúp cấu trúc container sạch và nhất quán.
3. **Tại sao `COPY requirements.txt` đứng trước `COPY . .`:** để tận dụng **Docker layer cache**. Code ứng dụng thay đổi thường xuyên còn `requirements.txt` ít đổi; nếu copy `requirements.txt` và chạy `pip install` trước, mỗi lần sửa code Docker chỉ rebuild từ layer `COPY . .` mà không phải tải lại toàn bộ thư viện.
4. **`CMD` vs `ENTRYPOINT`:** `ENTRYPOINT` cố định tiến trình chính luôn chạy khi khởi động container, còn `CMD` cung cấp lệnh hoặc tham số mặc định (dễ bị ghi đè khi truyền thêm tham số vào `docker run`). Trong production nên dùng exec form (`["uvicorn", ...]`) hoặc `sh -c "exec uvicorn ..."` để tiến trình app là PID 1 và nhận được `SIGTERM`.

### Exercise 2.2: Build và chạy container `my-agent:develop`

Build từ gốc repo:
```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -d --rm -p 18000:8000 my-agent:develop
curl -sS -X POST "http://localhost:18000/ask?question=Hello"
```

Kết quả:
```json
{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

### Exercise 2.3: So sánh kích thước image (`docker images my-agent`)

```text
REPOSITORY   TAG        SIZE
my-agent     advanced   163MB
my-agent     develop    1.15GB
```

- **Develop (`my-agent:develop`):** `1.15 GB` (~1150 MB)
- **Production (`my-agent:advanced`):** `163 MB`
- **Chênh lệch:** giảm **~85.8%** (nhỏ hơn khoảng 7 lần).
- **Lợi ích multi-stage build:** Stage `builder` cài compiler (`gcc`, `libpq-dev`) và compile thư viện Python; stage `runtime` dùng `python:3.11-slim` chỉ copy phần site-packages đã cài và source code, loại bỏ hoàn toàn compiler/cache, chạy bằng non-root user `appuser` nên image vừa nhẹ, deploy nhanh, vừa giảm bề mặt tấn công (attack surface).

### Exercise 2.4: Kiến trúc Docker Compose stack (`02-docker/production/docker-compose.yml`)

```text
Client
  │  (HTTP :80 / HTTPS :443)
  ▼
Nginx (reverse proxy & load balancer)
  │  (internal network, :8000)
  ▼
Agent (FastAPI, target=runtime)
  ├──► Redis (:6379)  — session cache & rate limiting (volume: redis_data)
  └──► Qdrant (:6333) — vector database cho RAG (volume: qdrant_data)
```

Chỉ `nginx` mở port ra ngoài host (`80`, `443`); `agent`, `redis`, `qdrant` nằm hoàn toàn trong mạng nội bộ `internal`, và `agent` dùng `depends_on` với điều kiện `service_healthy` của `redis` và `qdrant`.

---

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deploy agent Part 6 (`06-lab-complete/`)

- **Platform chính:** Railway (hoặc Render) — chi tiết URL, biến môi trường và kết quả kiểm thử 4 lệnh CP6 được ghi trong [DEPLOYMENT.md](DEPLOYMENT.md).
- **So sánh `railway.toml` và `render.yaml`:**

| Tiêu chí | `railway.toml` (Railway) | `render.yaml` (Render Blueprint) |
| --- | --- | --- |
| **Định dạng & phạm vi** | TOML, cấu hình chủ yếu build & deploy cho 1 service hiện tại (`[build]`, `[deploy]`). | YAML (Infrastructure-as-Code), khai báo cả danh sách `services:` (web, worker, redis/db) và `envVars` trong cùng 1 file. |
| **Build & Healthcheck** | `builder = "DOCKERFILE"`, `dockerfilePath = "Dockerfile"`, `healthcheckPath = "/health"`. | `type: web`, `runtime: docker`, `dockerfilePath: ./Dockerfile`, `healthCheckPath: /health`. |
| **Quản lý biến môi trường & secret** | Biến môi trường và secret (`AGENT_API_KEY`, `REDIS_URL`) đặt trực tiếp trên Dashboard/CLI của Railway (hỗ trợ reference giữa các service). | Khai báo schema biến ngay trong `render.yaml`; secret không hardcode mà dùng `generateValue: true` (tự sinh) hoặc `sync: false` (nhập tay trên dashboard). |
| **Khởi động lại / Policy** | Hỗ trợ `restartPolicyType = "ON_FAILURE"` và `restartPolicyMaxRetries`. | Render tự quản lý restart dựa trên `healthCheckPath` và hỗ trợ khai báo plan/region/autoDeploy trực tiếp trong blueprint. |

### Exercise 3.3: GCP Cloud Run CI/CD Pipeline (`cloudbuild.yaml` & `service.yaml`)

- Pipeline trong `03-cloud-deployment/production-cloud-run/cloudbuild.yaml` gồm 4 bước tuần tự khi push lên `main`:
  1. **`test`**: chạy container `python:3.11-slim`, cài dependencies và chạy `pytest tests/`.
  2. **`build`**: build Docker image với layer cache (`--cache-from`), gắn 2 tag `$COMMIT_SHA` và `latest`.
  3. **`push`**: đẩy toàn bộ tag image lên Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
  4. **`deploy`**: gọi `gcloud run deploy` triển khai image vừa build lên Cloud Run (`asia-southeast1`), cấu hình `min-instances=1` (tránh cold start), `max-instances=10`, `512Mi` RAM / `1` CPU và nạp `OPENAI_API_KEY` từ Secret Manager.
- File `service.yaml` mô tả cấu hình dịch vụ theo chuẩn Knative IaC: `containerConcurrency: 80`, `minScale: 1` / `maxScale: 10`, nạp secret qua `secretKeyRef`, và khai báo `livenessProbe` (`/health`) cùng `startupProbe` (`/ready`).

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/`)

Chạy với `AGENT_API_KEY=secret-key-123`:

- **Không có API key → HTTP 401:**
```text
HTTP 401
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

- **Có API key hợp lệ (`X-API-Key: secret-key-123`) → HTTP 200:**
```text
HTTP 200
{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production/`)

- Lấy JWT token qua `POST /auth/token` với tài khoản `student` / `demo123`:
```text
-- /auth/token -> HTTP 200
token_type=bearer, token=eyJhbGciOiJIUzI1...<REDACTED>
```

- Gửi liên tiếp 12 request tới `POST /ask` với `Authorization: Bearer <REDACTED>` (giới hạn 10 req/phút cho `student`):
```text
Req  1 -> HTTP 200
Req  2 -> HTTP 200
Req  3 -> HTTP 200
Req  4 -> HTTP 200
Req  5 -> HTTP 200
Req  6 -> HTTP 200
Req  7 -> HTTP 200
Req  8 -> HTTP 200
Req  9 -> HTTP 200
Req 10 -> HTTP 200
Req 11 -> HTTP 429
-- 429 headers: Retry-After=59
-- 429 body: {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Exercise 4.4: Cách thiết kế Cost Guard

- **Tại sao cần cả Rate Limit và Cost Guard:** Rate limit kiểm soát **tốc độ** request (chống spam/DDoS, ví dụ 10 req/phút), nhưng một số ít request có prompt/response rất dài hoặc chạy đều đặn cả ngày vẫn có thể đốt hết ngân sách LLM. Cost guard kiểm soát trực tiếp **số tiền (USD)** đã tiêu.
- **Cách triển khai (trong `06-lab-complete/app/cost_guard.py`):**
  1. Lưu tổng chi phí ngày (`cost:daily:YYYY-MM-DD`) và tháng (`cost:monthly:YYYY-MM`) trong **Redis** để mọi worker/instance dùng chung và không mất khi restart.
  2. **Trước khi gọi LLM (`check_budget()`):** đọc tổng chi phí hiện tại; nếu `>= DAILY_BUDGET_USD` hoặc `>= MONTHLY_BUDGET_USD` thì chặn ngay và trả **HTTP 402 Payment Required**.
  3. **Sau khi gọi LLM (`record_cost()`):** tính chi phí theo số input/output tokens và bảng giá model, cộng dồn nguyên tử bằng `INCRBYFLOAT` kèm `EXPIRE` tự dọn key cũ.

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Liveness (`/health`) vs Readiness (`/ready`)

- **`GET /health` (Liveness):** kiểm tra process của ứng dụng còn sống và không bị deadlock. Luôn trả `200` kể cả khi Redis tạm mất kết nối — nếu `/health` trả lỗi khi Redis chết, orchestrator sẽ restart container agent liên tục một cách vô ích (restart loop).
- **`GET /ready` (Readiness):** kiểm tra ứng dụng đã sẵn sàng phục vụ traffic hay chưa (ví dụ ping Redis thành công). Nếu Redis không kết nối được, trả **`503`** để load balancer tạm ngừng gửi traffic vào instance đó mà không kill container.

### Exercise 5.2: Graceful Shutdown

- Khi deploy mới hoặc scale down, platform gửi tín hiệu **`SIGTERM`** tới PID 1 của container.
- Ứng dụng dùng `uvicorn` làm PID 1 (`exec uvicorn ...` trong Dockerfile) kết hợp FastAPI `lifespan`: khi nhận `SIGTERM`, uvicorn ngừng nhận kết nối mới, đợi các request in-flight xử lý xong (trả `200`), chạy phần cleanup đóng kết nối Redis rồi thoát với exit code `0` trong < 10 giây (tránh bị `SIGKILL` / exit code `137`).

### Exercise 5.3: Thiết kế Stateless

- Nếu lưu session/rate limit/cost trong RAM của process Python, khi chạy nhiều instance sau load balancer (round-robin), request 1 vào instance A còn request 2 vào instance B sẽ không thấy state của nhau, và khi restart container mọi state sẽ mất trắng.
- Giải pháp: chuyển toàn bộ shared state (session history, sliding-window rate limit, cost counter) sang **Redis**, giữ các instance agent hoàn toàn stateless để có thể scale ngang tự do.

### Exercise 5.4 & 5.5: Kết quả chạy stack 3 replicas + `test_stateless.py`

Chạy trong `05-scaling-reliability/production/`:
```bash
docker compose -p k5-day14-scaling up -d --build --scale agent=3
python test_stateless.py
docker compose -p k5-day14-scaling down -v
```

Kết quả thực tế:
```text
============================================================
Stateless Scaling Demo
============================================================

Session ID: 2d323faf-a6b3-4bb6-a14b-8ff2dc1db6f2

Request 1: [instance-da3a21]
  Q: What is Docker?
  A: Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!...

Request 2: [instance-643f7f]
  Q: Why do we need containers?
  A: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận....

Request 3: [instance-f095f8]
  Q: What is Kubernetes?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

Request 4: [instance-da3a21]
  Q: How does load balancing work?
  A: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận....

Request 5: [instance-643f7f]
  Q: What is Redis used for?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

------------------------------------------------------------
Total requests: 5
Instances used: {'instance-da3a21', 'instance-643f7f', 'instance-f095f8'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
  [user]: What is Docker?...
  [assistant]: Container là cách đóng gói app để chạy ở mọi nơi. Build once...
  [user]: Why do we need containers?...
  [assistant]: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã đư...
  [user]: What is Kubernetes?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...
  [user]: How does load balancing work?...
  [assistant]: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã đư...
  [user]: What is Redis used for?...
  [assistant]: Đây là câu trả lời từ AI agent (mock). Trong production, đây...

✅ Session history preserved across all instances via Redis!
```

**Giải thích:** Nginx phân phối 5 request vòng tròn (round-robin) tới cả 3 instance (`instance-da3a21`, `instance-643f7f`, `instance-f095f8`), nhưng khi gọi `GET /chat/{session_id}/history` vẫn thu đủ 10 tin nhắn (5 user + 5 assistant) vì toàn bộ lịch sử được lưu tập trung trong Redis.

---

## Part 6: Kết quả `check_production_ready.py`

Chạy đầy đủ (tĩnh + runtime + SIGTERM + Docker build/run/stop) trong `06-lab-complete/`:

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

---

## AI Log

- **Công cụ sử dụng:** Antigravity AI Assistant.
- **Nội dung hỏi / hỗ trợ:**
  1. Kiểm tra yêu cầu setup môi trường (Python, Docker, WSL2, Railway CLI) và cài đặt các công cụ còn thiếu.
  2. Gợi ý triển khai các module TODO trong `06-lab-complete/` (`config.py`, `redis_client.py`, `auth.py`, `rate_limiter.py`, `cost_guard.py`, `main.py`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`) theo đúng hợp đồng trong `06-lab-complete/README.md`.
  3. Gợi ý cấu trúc trình bày câu trả lời `MISSION_ANSWERS.md` và phân tích số liệu `BENCHMARK_REPORT.md`.
- **Tự kiểm tra & xác minh:**
  - Chạy trực tiếp `check_production_ready.py` đầy đủ (bao gồm Docker build 160 MB, container `/health`, `docker stop` exit code 0 trong 1.0s, Redis stateless restart, SIGTERM in-flight request 200) đạt `PASS 12/12` (43/43 checks).
  - Chạy thực tế từng bài tập Part 1, 2, 4, 5 và đối chiếu toàn bộ số đo (kích thước image, mã HTTP 401/200/429, kết quả 3 replicas `test_stateless.py`).
  - Chạy thực tế toàn bộ load test, eval (`v1`, `v2`, `v2_fixed` 23/23), Locust headless (`scale_1`, `scale_3`), Jaeger trace và Prometheus alerts cho Part 7; mọi con số trong báo cáo đều khớp trực tiếp với file JSON/CSV sinh ra.
