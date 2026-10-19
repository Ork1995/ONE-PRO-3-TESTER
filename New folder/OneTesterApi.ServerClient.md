# Flex Tester API – שרת (SERVER) ולקוח (CLIENT) – מדריך מהיר, COM16

מדריך עבודה קצר ל-[FlexTesterApi.py](FlexTesterApi.py). המדריך המלא באנגלית נמצא ב-[FlexTesterApi.md](FlexTesterApi.md).
כל הדוגמאות כאן משתמשות ב-**COM16** (USB Serial Port, FTDI) וב-HTTP פורט **8765**.

---

## ⚡ התחלה מהירה: מה להריץ בדיוק

צריך **שני טרמינלים** פתוחים בתיקיית הפרויקט. ה-GUI סגור. **אין צורך בקבצי עזר או ב-`Set-ExecutionPolicy`**: הכול רץ דרך הפקודה `python` של הפרויקט.

**טרמינל 1 – שרת.** מריצים פעם אחת. אחרי השורה `Local tester API: ...` הטרמינל נשאר "תקוע", וזה תקין. לא נוגעים בו.
```powershell
cd "C:\Users\o29373\OneDrive - Netafim\Desktop\Netafim Projects\ONE PRO 3 TESTER"
python ".\New folder\FlexTesterApi.py" serve --port COM16 --http-port 8765
```

**טרמינל 2 – לקוח.** שולחים קובץ JSON עם הפקודה `send`:
```powershell
cd "C:\Users\o29373\OneDrive - Netafim\Desktop\Netafim Projects\ONE PRO 3 TESTER"
python ".\New folder\FlexTesterApi.py" send ".\New folder\FlexTesterApi.examples.wm-timed-30s.json" --new-id
```
- הפקודה קוראת את הקובץ, שולחת אותו לשרת (`127.0.0.1:8765` כברירת מחדל) ומדפיסה את התשובה.
- `--new-id` מחליף את ה-`RequestId` במזהה חדש. **שים אותו בכל שליחה חוזרת**, אחרת השרת מזהה את אותה בקשה ומחזיר את התשובה הישנה בלי להריץ שוב. בלעדיו הבקשה נשלחת בדיוק כפי שהיא בקובץ.
- תשובה תקינה: שורה `HTTP 200` ואחריה JSON עם `"ok": true`, `"status": "completed"`, ובתוך `result.commands[0].result` הערכים `"state": "started"` ו-`"duration_ms": 30000`. זה אומר שהלוח קיבל את הפקודה והתחיל לפעום. הפולסים נפסקים לבד אחרי 30 שניות.

**כיבוי בסוף (בטרמינל 2):**
```powershell
python ".\New folder\FlexTesterApi.py" send ".\New folder\FlexTesterApi.examples.safe-off.json" --new-id
```
ואז **Ctrl+C** בטרמינל 1 (השרת). הוא מכבה ומשחרר את COM16.

**בלי ליצור קובץ:** אפשר להדביק JSON ישירות בטרמינל ולשלוח אותו (סעיף 2.1), ולכן כל הדוגמאות בסעיף 2.3 מוכנות להדבקה.

---

```text
 טרמינל 1 = SERVER                                   טרמינל 2 = CLIENT
 ┌──────────────────────────────┐   HTTP + JSON      ┌──────────────────────────────┐
 │ FlexTesterApi.py serve       │ ◄───────────────── │ FlexTesterApi.py send        │
 │ מחזיק את COM16 (היחיד!)      │  127.0.0.1:8765    │ שולח קובץ / JSON מודבק       │
 └──────────────┬───────────────┘                    └──────────────────────────────┘
                │ Serial 115200 8N1
            ┌───▼────┐
            │ הטסטר  │
            └────────┘
```

**הכלל המרכזי:** השרת הוא התוכנית היחידה שמדברת עם ה-COM. הוא רץ בחזית ומחכה לבקשות, ולכן **הטרמינל שלו "תפוס"** וצריך טרמינל שני ללקוח. זה לא תקלה.

---

## 0. הכנה (פעם אחת)

1. סגור את ה-GUI (`FlexTesterGui.py`) או נתק אותו, כי רק תוכנה אחת יכולה להחזיק את COM16.
2. התקנת pyserial: `python -m pip install pyserial`
3. כל הפקודות מורצות **מתיקיית השורש של הפרויקט** (ONE PRO 3 TESTER):

```powershell
cd "C:\Users\o29373\OneDrive - Netafim\Desktop\Netafim Projects\ONE PRO 3 TESTER"
```

---

## 1. צד השרת – SERVER (טרמינל 1)

### 1.1 חיפוש הפורט (אופציונלי, כשלא בטוחים)

```powershell
python ".\New folder\FlexTesterApi.py" shell
```
```text
tester> PORTS
tester> EXIT
```
הטסטר הוא הפורט עם `USB Serial Port` (VID:PID=0403:6001). פורטי Bluetooth אינם רלוונטיים.

### 1.2 הפעלת השרת עם חיבור ל-COM16

```powershell
python ".\New folder\FlexTesterApi.py" serve --port COM16 --http-port 8765
```
פלט תקין:
```text
Local tester API: http://127.0.0.1:8765/api/v1/status
```
אחרי השורה הזו הטרמינל נשאר "תקוע". **זה תקין**, והשרת מחכה לבקשות. אל תקליד בו ואל תלחץ Ctrl+C עד שסיימת.

בהתחברות השרת מכבה את WM1..WM4, שולח `set vsen 0` ומוודא שכל המתחים כבויים.

### 1.3 הפעלה בחלון נפרד (הטרמינל הנוכחי נשאר חופשי)

```powershell
Start-Process powershell -ArgumentList '-NoExit','-Command','python ".\New folder\FlexTesterApi.py" serve --port COM16 --http-port 8765'
```

### 1.4 הפעלה בלי חיבור, והתחברות אחר כך מהלקוח

```powershell
python ".\New folder\FlexTesterApi.py" serve --http-port 8765
```
ובצד הלקוח (טרמינל 2) מתחברים עם:
```powershell
'{"id":"c1","action":"connection.connect","args":{"port":"COM16"}}' | python ".\New folder\FlexTesterApi.py" send - --new-id
```

### 1.5 אפשרויות

| אפשרות | ברירת מחדל | משמעות |
|---|---|---|
| `--port COM16` | מנותק | התחברות מיידית לפורט |
| `--http-port 8765` | `8765` | פורט ה-HTTP המקומי (הכתובת היא תמיד 127.0.0.1) |
| `--baudrate 115200` | `115200` | מהירות סריאל, חייבת להתאים ללוח |
| `--line-ending LF` | `LF` | סיום שורה: `LF`, `CRLF` או `CR` |

### 1.6 כיבוי השרת

לחץ **Ctrl+C** בטרמינל של השרת. הוא מבצע כיבוי מאומת של כל הפלטים לפני שהוא משחרר את COM16.
סגירת חלון בכוח, kill או ניתוק כבל לא מבטיחים כיבוי. WM רציף (`Duration_ms` 0) עלול להמשיך לפעום.

### 1.7 מה לא לעשות בצד השרת

- לא להריץ `serve` פעמיים. השני נכשל כי COM16 ופורט 8765 תפוסים.
- לא להריץ `shell --port COM16` בזמן שהשרת רץ.
- לא לפתוח את ה-GUI על אותו פורט בו-זמנית.

---

## 2. צד הלקוח – CLIENT (טרמינל 2)

פתח טרמינל שני ב-VS Code: כפתור `+` בחלון הטרמינל, או Ctrl+Shift+`. עבור שוב לתיקיית הפרויקט.

### 2.1 שליחה עם `send`

**הפקודה:**
```powershell
python ".\New folder\FlexTesterApi.py" send <קובץ או -> [--new-id] [--server http://127.0.0.1:8765]
```

| אפשרות | משמעות |
|---|---|
| `<קובץ>` | קובץ JSON לשליחה |
| `-` | קריאת ה-JSON מהקלט הסטנדרטי (הדבקה או צינור), בלי ליצור קובץ |
| `--new-id` | מחליף `RequestId` (או `id` בפורמט הישן) במזהה חדש. **שים בכל שליחה חוזרת** |
| `--server http://127.0.0.1:8765` | כתובת השרת (ברירת מחדל זו). חייבת להיות 127.0.0.1 |

**קוד יציאה:** `0` הצליח; `1` השרת דחה את הבקשה (התשובה המלאה והשגיאה מודפסות); `2` הקובץ לא נמצא או ה-JSON לא תקין (לא נשלח כלום); `3` השרת לא זמין.

**שלוש דרכים להעביר JSON:**

1. **קובץ מוכן** מהפרויקט:
   ```powershell
   python ".\New folder\FlexTesterApi.py" send ".\New folder\FlexTesterApi.examples.wm-timed-30s.json" --new-id
   ```
2. **קובץ משלך:** צור `my_request.json` בתיקיית הפרויקט ושלח אותו באותה פקודה.
3. **הדבקה ישירה, בלי קובץ** (הדוגמה למטה):

מדביקים את כל הבלוק יחד. הסימן `'@` בשורה האחרונה חייב להיות בתחילת שורה, בלי רווחים לפניו:
```powershell
@'
{ "RequestId": "demo", "Commands": [ { "Port": "WM", "PortNum": 1, "Action": "Stop" } ] }
'@ | python ".\New folder\FlexTesterApi.py" send - --new-id
```

תשובה מודפסת כ-`HTTP <קוד>` (ל-stderr) ואחריה ה-JSON המלא (ל-stdout).

### 2.2 קריאות מידע (GET, לא משנות כלום)

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/v1/status | ConvertTo-Json -Depth 10         # מצב מהמטמון
Invoke-RestMethod http://127.0.0.1:8765/api/v1/ports | ConvertTo-Json -Depth 10          # רשימת פורטים
Invoke-RestMethod http://127.0.0.1:8765/api/v1/capabilities | ConvertTo-Json -Depth 10  # פיצ'רים וגבולות
Invoke-RestMethod "http://127.0.0.1:8765/api/v1/events?after=0" | ConvertTo-Json -Depth 10  # אירועים: TX/RX, דגימות VIN, wm.stopped
```

`status` מציג את המטמון בלבד. כדי לקרוא מהלוח בפועל (גם בדיקת חיבור: חפש `"connection": "ready"` ו-`"port": "COM16"`):
```powershell
'{"id":"s1","action":"status","args":{"refresh":true}}' | python ".\New folder\FlexTesterApi.py" send - --new-id
```

### 2.3 דוגמאות JSON (batch)

כל פקודה ב-`Commands` דורשת `Port` (`VAI` / `WM` / `AI`), `PortNum` (1..4) ו-`Action`. שדות שלא רלוונטיים אפשר להשמיט או לשים `null`. כל בלוק כאן שלם: מדביקים אותו כמו שהוא בטרמינל 2 (בדוגמאות יש `--new-id`, ולכן אפשר להדביק שוב ושוב).

**א. WM1 פולסים למשך 30 שניות (מחזור 1 שנייה)** (גם בקובץ [FlexTesterApi.examples.wm-timed-30s.json](FlexTesterApi.examples.wm-timed-30s.json))

```powershell
@'
{
  "RequestId": "wm1-timed-30s",
  "Commands": [
    { "Port": "WM", "PortNum": 1, "Action": "Start", "Cycle_ms": 1000, "Duration_ms": 30000 }
  ]
}
'@ | python ".\New folder\FlexTesterApi.py" send - --new-id
```

**ב. WM רציף עד STOP** (גם בקובץ [FlexTesterApi.examples.wm-continuous.json](FlexTesterApi.examples.wm-continuous.json))

```powershell
@'
{
  "RequestId": "wm1-continuous",
  "Commands": [
    { "Port": "WM", "PortNum": 1, "Action": "Start", "Cycle_ms": 1000, "Duration_ms": 0 }
  ]
}
'@ | python ".\New folder\FlexTesterApi.py" send - --new-id
```
עצירה:
```powershell
@'
{
  "RequestId": "wm1-stop",
  "Commands": [
    { "Port": "WM", "PortNum": 1, "Action": "Stop" }
  ]
}
'@ | python ".\New folder\FlexTesterApi.py" send - --new-id
```

**ג. WM1 גבוה קבוע / נמוך**

```powershell
@'
{
  "RequestId": "wm1-on",
  "Commands": [
    { "Port": "WM", "PortNum": 1, "Action": "On" }
  ]
}
'@ | python ".\New folder\FlexTesterApi.py" send - --new-id
```
כיבוי: אותו בלוק עם `"Action": "Off"`.

**ד. כמה WM בבקשה אחת (רצים ברצף, לא בו-זמנית)**

```powershell
@'
{
  "RequestId": "two-wm",
  "Commands": [
    { "Port": "WM", "PortNum": 1, "Action": "Start", "Cycle_ms": 1000, "Duration_ms": 30000 },
    { "Port": "WM", "PortNum": 2, "Action": "Start", "Cycle_ms": 500,  "Duration_ms": 0 }
  ]
}
'@ | python ".\New folder\FlexTesterApi.py" send - --new-id
```

**ה. קריאת כניסה אנלוגית AI1**

```powershell
@'
{
  "RequestId": "ai1-read",
  "Commands": [
    { "Port": "AI", "PortNum": 1, "Action": "Read" }
  ]
}
'@ | python ".\New folder\FlexTesterApi.py" send - --new-id
```

**ו. פולס מתח לחיישן VAI1: 5000mV למשך 2 שניות**

```powershell
@'
{
  "RequestId": "vai1-pulse",
  "Commands": [
    { "Port": "VAI", "PortNum": 1, "Action": "Pulse", "Manual_voltage": 5000, "Duration_ms": 2000 }
  ]
}
'@ | python ".\New folder\FlexTesterApi.py" send - --new-id
```
התשובה היא `HTTP 202` עם `status=running` ו-ID. המעקב מתואר ב-2.5.

**ז. הגדרת VAI1 והפעלה ידנית (מתח מוגדר, ואז On)**

```powershell
@'
{
  "RequestId": "vai1-manual-on",
  "Commands": [
    { "Port": "VAI", "PortNum": 1, "Action": "Configure", "Operation_Mode": "Manual", "Manual_voltage": 5000 },
    { "Port": "VAI", "PortNum": 1, "Action": "On" }
  ]
}
'@ | python ".\New folder\FlexTesterApi.py" send - --new-id
```
כיבוי:
```powershell
@'
{
  "RequestId": "vai1-off",
  "Commands": [
    { "Port": "VAI", "PortNum": 1, "Action": "Off" }
  ]
}
'@ | python ".\New folder\FlexTesterApi.py" send - --new-id
```

**ח. סקלה הנדסית: 50 יחידות שוות 5000mV (0..100 ממופה ל-0..10000mV)**

```powershell
@'
{
  "RequestId": "vai1-scaled-on",
  "Commands": [
    { "Port": "VAI", "PortNum": 1, "Action": "Configure",
      "X1": 0, "X2": 10000, "Y1": 0, "Y2": 100,
      "Operation_Mode": "Automatic", "Output_Value": 50 },
    { "Port": "VAI", "PortNum": 1, "Action": "On" }
  ]
}
'@ | python ".\New folder\FlexTesterApi.py" send - --new-id
```

**ט. AUTO: פולס על VAI1 בכל פעם ש-AI1 עולה מעל 1000mV** (גם בקובץ [FlexTesterApi.examples.json](FlexTesterApi.examples.json))

```powershell
@'
{
  "RequestId": "auto-vai1",
  "Commands": [
    { "Port": "VAI", "PortNum": 1, "Action": "Configure",
      "X1": 0, "X2": 10000, "Y1": 0, "Y2": 100,
      "Operation_Mode": "Automatic", "Output_Value": 50,
      "Auto_Enabled": true, "Duration_ms": 5000 },
    { "Port": "WM", "PortNum": 1, "Action": "Start", "Cycle_ms": 1000, "Duration_ms": 5000 }
  ]
}
'@ | python ".\New folder\FlexTesterApi.py" send - --new-id
```
כיבוי AUTO:
```powershell
@'
{
  "RequestId": "auto-vai1-off",
  "Commands": [
    { "Port": "VAI", "PortNum": 1, "Action": "Configure", "Auto_Enabled": false }
  ]
}
'@ | python ".\New folder\FlexTesterApi.py" send - --new-id
```
כאשר AUTO פעיל, פקודות מתח ידניות נדחות. כבה אותו לפני שימוש ב-`On`.

### 2.4 פקודות ב"פורמט הישן" (action + args)

פקודה אחת בצורה `{"id": ..., "action": ..., "args": {...}}`. התבנית (מחליפים את `action` ו-`args` לפי הטבלה):
```powershell
'{"id":"x","action":"wm.stop","args":{"channel":1}}' | python ".\New folder\FlexTesterApi.py" send - --new-id
```

| מטרה | `action` | `args` |
|---|---|---|
| התחברות | `connection.connect` | `{"port":"COM16"}` |
| ניתוק | `connection.disconnect` | `{}` |
| WM גבוה / נמוך / עצירה | `wm.on` / `wm.off` / `wm.stop` | `{"channel":1}` |
| WM פולסים | `wm.start` | `{"channel":1,"cycle_ms":1000,"duration_ms":30000}` |
| חיישן On / Off / Stop | `sensor.on` / `sensor.off` / `sensor.stop` | `{"channel":1}` |
| פולס חיישן | `sensor.pulse` | `{"channel":1,"mv":5000,"duration_ms":2000}` |
| קביעת מתח ידני | `sensor.voltage` | `{"channel":1,"mv":7500}` |
| סקלה | `scaling.configure` | `{"channel":1,"x1":0,"x2":10000,"y1":0,"y2":100}` |
| מצב סקלה | `scaling.mode` | `{"channel":1,"mode":"automatic"}` |
| ערך הנדסי | `scaling.value` | `{"channel":1,"value":50}` |
| קריאת VIN | `vin.read` | `{"channel":1}` |
| בחירת ערוצי דגימה | `sampling.configure` | `{"channels":[1,2],"enabled":true}` |
| AUTO | `auto.configure` | `{"channel":1,"enabled":true,"duration_ms":5000}` |
| זמן בלוח | `time.get` / `time.set` | `{}` / `{"value":"14:30"}` |
| סטטוס מתח | `supply.status` | `{}` |
| סטטוס מהלוח | `status` | `{"refresh":true}` |
| עזרה / יכולות | `help` / `capabilities` | `{}` |
| **כיבוי חירום לוגי** | `safety.off` | `{}` |

### 2.5 מעקב אחר פולס חיישן (operation)

שולחים את הפולס (דוגמה 2.3 ו), שומרים את התשובה, ושואלים את השרת על ה-ID עד שהסטטוס מסתיים:
```powershell
$r = @'
{
  "RequestId": "vai1-pulse-track",
  "Commands": [
    { "Port": "VAI", "PortNum": 1, "Action": "Pulse", "Manual_voltage": 5000, "Duration_ms": 2000 }
  ]
}
'@ | python ".\New folder\FlexTesterApi.py" send - --new-id | ConvertFrom-Json
$id = $r.result.commands[0].result.id
Invoke-RestMethod "http://127.0.0.1:8765/api/v1/operations/$id" | ConvertTo-Json -Depth 10
```
חזור על השורה האחרונה עד ש-`result.status` הוא `completed` / `cancelled` / `failed` / `unknown`.

### 2.6 מעקב אחר עצירה עצמית של WM

אחרי ש-`Duration_ms` חלף, הלוח שולח `wm 1 stopped working ...` והוא נשמר כאירוע `wm.stopped`:
```powershell
Invoke-RestMethod "http://127.0.0.1:8765/api/v1/events?after=0" | ConvertTo-Json -Depth 10
```
או לקרוא את המצב ישירות מהלוח עם `status` + `refresh` (סעיף 2.2).

### 2.7 לקוח חלופי: shell מרוחק

אפשר להקליד פקודות קצרות במקום JSON. ה-shell מתחבר לשרת וכלל לא פותח COM:
```powershell
python ".\New folder\FlexTesterApi.py" shell --server http://127.0.0.1:8765
```
```text
tester> STATUS
tester> START WM1 CYCLE_MS 1000 DURATION_MS 30000
tester> STOP WM1
tester> PULSE VAI1 MV 5000 DURATION_MS 2000
tester> VIN AI1
tester> SAFE_OFF
tester> EXIT
```
`EXIT` ב-shell מרוחק רק מנתק את ה-shell ולא מכבה פלטים. ה-shell **לא** מקבל batch JSON; את ה-JSON שולחים עם `send`.

### 2.8 כיבוי מהלקוח

```powershell
python ".\New folder\FlexTesterApi.py" send ".\New folder\FlexTesterApi.examples.safe-off.json" --new-id
```
זה מכבה WM ומתחי חיישן ומנטרל AUTO (`safety.off`). ניתוק מלא של הלוח:
```powershell
'{"id":"d1","action":"connection.disconnect","args":{}}' | python ".\New folder\FlexTesterApi.py" send - --new-id
```

---

## 3. תרחיש מלא מההתחלה עד הסוף (COM16)

**1. טרמינל 1: שרת.** סגור את ה-GUI, ואז:
```powershell
cd "C:\Users\o29373\OneDrive - Netafim\Desktop\Netafim Projects\ONE PRO 3 TESTER"
python ".\New folder\FlexTesterApi.py" serve --port COM16 --http-port 8765
```

**2. טרמינל 2: בדיקת חיבור** (קוראת מהלוח). חפש `"connection": "ready"` ו-`"port": "COM16"`:
```powershell
cd "C:\Users\o29373\OneDrive - Netafim\Desktop\Netafim Projects\ONE PRO 3 TESTER"
'{"id":"s1","action":"status","args":{"refresh":true}}' | python ".\New folder\FlexTesterApi.py" send - --new-id
```

**3. טרמינל 2: שליחת הפולסים.**
```powershell
python ".\New folder\FlexTesterApi.py" send ".\New folder\FlexTesterApi.examples.wm-timed-30s.json" --new-id
```

**4. חכה כ-30 שניות** ושוב את הפקודה משלב 2. ודא ש-WM1 כבר לא פועל.

**5. טרמינל 2: כיבוי** (גם אם הכול כבר כבוי):
```powershell
python ".\New folder\FlexTesterApi.py" send ".\New folder\FlexTesterApi.examples.safe-off.json" --new-id
```

**6. טרמינל 1:** **Ctrl+C**. השרת מכבה ומשחרר את COM16.

---

## 4. קריאת תשובות

כל תשובה כוללת: `api_version`, `id`, `ok`, `status`, `result`, `error`, `timestamp`.

| HTTP | משמעות |
|---|---|
| 200 | הפקודות הושלמו (`ok: true`, `status: completed`) |
| 202 | פולס חיישן התקבל ועדיין רץ (`status: running`, ה-ID ב-`result.commands[i].result.id`) |
| 400 | שגיאת ולידציה. לא נשלח כלום ללוח. |
| 404 | משאב לא קיים (למשל operation id שגוי) |
| 409 | התנגשות או לא מחובר. `RequestId` זהה עם גוף אחר, חיישן שייך לערוץ אחר, או AUTO פעיל. |
| 422 | הלוח דחה או לא תומך. `Duration_ms` חיובי בפירמוור בלי `start wm_timed`. |
| 503 | לא זמין או מצב לא בטוח. בדוק `error.outcome` ו-`result.cleanup`. |
| 504 | פג זמן. הלוח לא ענה, ויש לנתק ולהתחבר מחדש. |

אם פקודה באמצע batch נכשלת, הבאות מדולגות והכלי מנסה `SAFE_OFF` אוטומטי. בדוק `result.cleanup`.

---

## 5. בעיות נפוצות

| בעיה | סיבה | פתרון |
|---|---|---|
| הטרמינל של השרת לא מגיב להקלדה | השרת רץ בחזית | תקין. עבוד בטרמינל שני. |
| `ERROR connection: Local API unavailable ... actively refused it` | השרת לא רץ, או רץ על פורט אחר | הפעל את השרת בטרמינל 1, או הוסף `--server http://127.0.0.1:<port>` |
| `ERROR validation: Cannot read ...` / `... is not valid JSON` | נתיב שגוי, או JSON עם פסיק מיותר/חסר | בדוק את הנתיב מתיקיית הפרויקט ואת ה-JSON. לא נשלח כלום לשרת. |
| תשובה ישנה בלי שהלוח הגיב | אותו `RequestId` ואותו גוף נשלחו שוב | הוסף `--new-id` |
| 409 על `RequestId` | אותו מזהה נשלח עם תוכן אחר | הוסף `--new-id` |
| `Access is denied` / לא נפתח COM16 | ה-GUI, shell אחר או שרת שני מחזיקים את הפורט | סגור אותם, או Ctrl+C על השרת הקודם |
| 422 `unsupported` על `Duration_ms` חיובי | פירמוור ישן בלי `start wm_timed` | צרוב פירמוור מעודכן, או השתמש ב-`Duration_ms: 0` |
| 409 `conflict` על `VAI On` | AUTO פעיל או חיישן אחר מחזיק את המתח | שלח `Auto_Enabled: false` (2.3 ט), או `safe-off` (2.8) |
| 409 `Disarm AUTO and finish the pulse before changing settings` | ניסית לשנות סקלה/מצב/ערך בזמן שפולס חיישן רץ או ש-AUTO פעיל | המתן לסיום הפולס (2.5), או `sensor.stop` (2.4), או `safe-off` (2.8) |
| השורה האחרונה בהדבקה לא עובדת (`'@` לא מזוהה) | יש רווחים לפני `'@`, או ההדבקה נחתכה | `'@` חייב להיות בתחילת שורה. הדבק את כל הבלוק יחד |
| `Cannot index into a null array` ב-`$r.result.commands[0]` (2.5) | הבקשה נכשלה ואין `result` | הדפס את `$r` לפני שניגשים לשדות |

---

## 6. בטיחות

- לפני `"Auto_Enabled": true` או פולס/`On` של VAI ודא שהחיווט והעומס מתאימים. זה מפעיל **מתח אמיתי על החיישן** (עד 15000mV).
- ארבעת חיישני VAI חולקים מקור מתח אחד, ולכן רק חיישן ידני אחד פעיל בכל רגע.
- `Duration_ms` חיובי ב-WM נאכף על ידי הפירמוור ולכן מסתיים גם אם המחשב נופל. WM רציף ושליטה ידנית לא.
- הכלי הזה אינו עצירת חירום חומרתית.
- המערכת נבדקה עם סריאל מדומה בלבד. עבודה עם חומרה אמיתית דורשת אישור ניסוי עם עומס בטוח.

---

## נספח: פונקציות PowerShell (אופציונלי, לא נחוץ ל-`send`)

אם מעדיפים לשלוח מ-PowerShell בלי `python` בלקוח, אפשר להדביק פונקציות עזר (`Invoke-Api`, `Send-Action`, `Send-Batch`) בטרמינל. **ההדבקה נעלמת בכל טרמינל חדש וצריך לחזור עליה.** בלי הדבקה מתקבל `The term 'Send-Batch' is not recognized`.

הדבק את הבלוק שבסוף הנספח כולו בטרמינל 2. הדבקה אינה הרצת קובץ, ולכן Windows לא חוסם אותה.

שימוש אחרי ההדבקה:
```powershell
Send-Batch @( @{ Port="WM"; PortNum=1; Action="Start"; Cycle_ms=1000; Duration_ms=30000 } )
Send-Action "safety.off"
Send-Action "status" @{ refresh = $true }
Invoke-Api "status"
```
`Send-Batch` מייצר `RequestId` חדש בכל שליחה, ו-`Send-Action` מקבל את אותם `action`/`args` מטבלת 2.4. הפונקציות מציגות גם את גוף השגיאה (409, 422 וכו') שאחרת PowerShell 5.1 מסתיר. הבלוק להדבקה:

```powershell
$Api = "http://127.0.0.1:8765/api/v1"

function Invoke-Api {                       # כללי: GET או POST עם גוף JSON
    param([string]$Path, [string]$Body, [string]$Method = $(if ($Body) { "Post" } else { "Get" }))
    try {
        if ($Method -eq "Get") { $r = Invoke-RestMethod -Uri "$Api/$Path" }
        else { $r = Invoke-RestMethod -Method Post -Uri "$Api/$Path" -ContentType "application/json" -Body $Body }
        $r | ConvertTo-Json -Depth 20
    } catch {
        $resp = $_.Exception.Response
        if ($resp -and $_.ErrorDetails.Message) {
            Write-Host ("HTTP " + [int]$resp.StatusCode) -ForegroundColor Yellow
            $_.ErrorDetails.Message | ConvertFrom-Json | ConvertTo-Json -Depth 20
        }
        else { Write-Host $_.Exception.Message -ForegroundColor Red }
    }
}

function Send-Action {                      # פורמט "legacy": action + args
    param([string]$Action, [hashtable]$Arguments = @{})
    $body = @{ id = [guid]::NewGuid().ToString(); action = $Action; args = $Arguments } | ConvertTo-Json -Depth 10
    Invoke-Api -Path "commands" -Body $body
}

function Send-Batch {                       # פורמט Commands: מספר פקודות ב-JSON אחד, RequestId חדש אוטומטית
    param([Parameter(Mandatory)][array]$Commands, [string]$RequestId = ("req-" + [guid]::NewGuid().ToString("N")))
    $body = @{ RequestId = $RequestId; Commands = $Commands } | ConvertTo-Json -Depth 10
    Invoke-Api -Path "commands" -Body $body
}
```
