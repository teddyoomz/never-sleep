# never-sleep

Keep-alive service สำหรับป้องกันไม่ให้ cloud instance (เช่น AIS Cloud) เข้าสู่โหมด sleep เมื่อไม่มี request เข้ามา

## วิธีใช้

1. Deploy ขึ้น cloud
2. ตั้ง Environment Variables:

| Variable | ค่าเริ่มต้น | คำอธิบาย |
|---|---|---|
| `PORT` | `3000` | Port ที่ server จะรัน |
| `PING_INTERVAL_MINUTES` | `5` | ความถี่ในการ ping (นาที) |
| `PING_URLS` | _(ว่าง)_ | URL ที่ต้องการ ping คั่นด้วย `,` |

### ตัวอย่าง

```
PING_URLS=https://my-bot.ais.cloud/webhook,https://my-other-bot.ais.cloud/webhook
PING_INTERVAL_MINUTES=3
```

## Endpoints

- `GET /` — แสดงสถานะ
- `GET /health` — Health check (JSON)

## Deploy

```bash
git clone https://github.com/teddyoomz/never-sleep.git
cd never-sleep
npm start
```

ไม่มี dependency ภายนอก ใช้แค่ Node.js built-in modules
