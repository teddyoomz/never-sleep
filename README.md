# never-sleep

ป้องกันไม่ให้ Windows บน Cloud (เช่น AIS Cloud) เข้าสู่โหมด Sleep เมื่อไม่มี request เข้ามา

## วิธีใช้

1. โหลด repo นี้ หรือก็อปไฟล์ `never-sleep.bat` + `never-sleep.ps1` ไปวางในเครื่อง
2. ดับเบิลคลิก `never-sleep.bat`
3. จบ — เครื่องจะไม่ sleep อีก

> ⚠️ อย่าปิดหน้าต่าง CMD ที่ขึ้นมา ให้ minimize ไว้

## ตั้งค่าเพิ่มเติม (ไม่จำเป็น)

ถ้าอยาก ping URL ของ bot/extension ด้วย ให้ตั้ง Environment Variable ก่อนรัน:

| Variable | ค่าเริ่มต้น | คำอธิบาย |
|---|---|---|
| `PING_INTERVAL_MINUTES` | `5` | ความถี่ในการทำงาน (นาที) |
| `PING_URLS` | _(ว่าง)_ | URL ที่ต้องการ ping คั่นด้วย `,` |

### ตัวอย่าง ตั้ง env แล้วรัน

```bat
set PING_URLS=https://my-bot.example.com/webhook,https://other-bot.example.com/webhook
set PING_INTERVAL_MINUTES=3
never-sleep.bat
```

## หลักการทำงาน

- ใช้ Windows API `SetThreadExecutionState` บอก Windows ว่า "ยังมีงานทำอยู่ อย่า sleep"
- วนลูปเรียก API นี้ทุก 5 นาที เพื่อให้ Windows ไม่หลุด
- ถ้าตั้ง `PING_URLS` ไว้ จะ ping URL เหล่านั้นด้วย เพื่อกัน extension/bot sleep ไปพร้อมกัน

## ต้องการอะไร

- Windows (มี PowerShell อยู่แล้ว)
- ไม่ต้องติดตั้งอะไรเพิ่ม
