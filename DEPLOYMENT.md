# Deployment Information

> **Lưu ý:** Điền URL public thật sau khi chạy `railway up` (hoặc deploy Render) cho thư mục `06-lab-complete/` và cập nhật 3 ảnh `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png`.

## Public URL
`https://<your-agent-service>.up.railway.app`

## Platform
Railway (Docker deploy từ `06-lab-complete/Dockerfile` + `06-lab-complete/railway.toml` + Redis service)

## Test Commands (CP6 — 4 lệnh tự kiểm)

```bash
export BASE="https://<your-agent-service>.up.railway.app"
export AGENT_API_KEY="<YOUR_AGENT_API_KEY>"

# 1. Health check (Expected: 200)
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"

# 2. Readiness check với Redis (Expected: 200)
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"

# 3. Ask không có API key (Expected: 401)
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Hello"}'

# 4. Ask có API key hợp lệ (Expected: 200)
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
```

## Environment Variables Set
- `PORT` (do nền tảng tự cấp)
- `ENVIRONMENT=production`
- `REDIS_URL` (trỏ tới Redis service trên Railway/Render)
- `AGENT_API_KEY` (secret đặt trên dashboard nền tảng, không ghi trong code)
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`
- `MONTHLY_BUDGET_USD=10.0`
- `LOG_LEVEL=INFO`

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
