# Deployment Information

## Public URL
https://ai-agent-production-8017c0c1.up.railway.app

## Platform
Railway (Docker multi-stage từ `06-lab-complete/Dockerfile` + `06-lab-complete/railway.toml` + Railway Redis service)

## Test Commands (CP6 — 4 lệnh tự kiểm)

```bash
export BASE="https://ai-agent-production-8017c0c1.up.railway.app"
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

### Kết quả kiểm thử thực tế trên Public URL

```text
1. GET /health
{"status":"ok","environment":"production"}
HTTP 200

2. GET /ready
{"status":"ready","redis":"ok"}
HTTP 200

3. POST /ask (không có X-API-Key)
{"detail":"Invalid or missing API key"}
HTTP 401

4. POST /ask (có X-API-Key hợp lệ — đã che key)
{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","cost_usd":1.8e-05}
HTTP 200
```

## Environment Variables Set (trên Railway Dashboard)
- `PORT` (Railway tự cấp)
- `ENVIRONMENT=production`
- `REDIS_URL=${{Redis.REDIS_URL}}` (trỏ tới Railway Redis service)
- `AGENT_API_KEY` *(secret đặt trực tiếp trên Railway, không lưu trong code/Git)*
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`
- `MONTHLY_BUDGET_USD=10.0`
- `LOG_LEVEL=INFO`

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
