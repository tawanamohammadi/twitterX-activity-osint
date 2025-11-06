# 🐦 Twitter Monitor - سیستم نظارت و رصد حساب‌های توییتر

<div dir="rtl">

## 📋 فهرست مطالب
- [درباره پروژه](#درباره-پروژه)
- [ویژگی‌های کلیدی](#ویژگی‌های-کلیدی)
- [معماری و ساختار فنی](#معماری-و-ساختار-فنی)
- [نصب و راه‌اندازی](#نصب-و-راه‌اندازی)
- [نحوه استفاده](#نحوه-استفاده)
- [جزئیات فنی](#جزئیات-فنی)
- [API و Endpoints](#api-و-endpoints)
- [ساختار پایگاه داده](#ساختار-پایگاه-داده)
- [تنظیمات پیشرفته](#تنظیمات-پیشرفته)
- [مشکلات رایج و راه حل](#مشکلات-رایج-و-راه-حل)

---

## 📖 درباره پروژه

**Twitter Monitor** یک سیستم نظارت و رصد پیشرفته برای حساب‌های توییتر است که به کاربران امکان می‌دهد فعالیت‌های حساب‌های مختلف توییتر را به صورت خودکار و لحظه‌ای رصد کنند.

این پروژه با استفاده از فناوری‌های مدرن وب، توییت‌های جدید حساب‌های مورد نظر را دریافت، ذخیره و به کاربر نمایش می‌دهد.

### 🎯 موارد استفاده
- **نظارت بر برندها**: رصد توییت‌های رقبا و برندهای مرتبط
- **تحلیل شبکه‌های اجتماعی**: جمع‌آوری داده برای تحلیل و پژوهش
- **پیگیری اخبار**: دنبال کردن لحظه‌ای اخبار از منابع خبری
- **مانیتورینگ شخصی**: پیگیری حساب‌های خاص بدون نیاز به ورود به توییتر

---

## ✨ ویژگی‌های کلیدی

### 🔐 سیستم احراز هویت کامل
- ثبت نام و ورود کاربران با رمزنگاری امن (Werkzeug Password Hashing)
- مدیریت جلسات کاربری با Flask Session
- محافظت از صفحات با decorator اختصاصی `@login_required`

### 📊 سه حالت نظارت
1. **فقط توییت‌ها** (`tweets_only`): رصد توییت‌های اصلی بدون ریتوییت و ریپلای
2. **توییت‌ها + پاسخ‌ها** (`tweets_replies`): شامل توییت‌ها و پاسخ‌های کاربر
3. **تمام فعالیت‌ها** (`all_activity`): شامل توییت‌ها، پاسخ‌ها و منشن‌ها

### ⚡ نظارت لحظه‌ای
- استفاده از Threading برای نظارت همزمان چندین حساب
- بررسی خودکار هر 5 ثانیه برای توییت‌های جدید
- اعلان فوری در صورت انتشار توییت جدید

### 💾 ذخیره‌سازی خودکار
- ذخیره تمام توییت‌های جدید در فایل‌های JSON
- جلوگیری از ذخیره توییت‌های تکراری
- ذخیره اطلاعات کامل: محتوا، لینک، تاریخ انتشار، نویسنده

### 🎨 رابط کاربری فارسی
- داشبورد کامل با طراحی مدرن
- صفحات ورود و ثبت نام
- صفحه نمایش توییت‌های ذخیره شده
- پشتیبانی کامل از RTL

### 🔄 دو روش دریافت داده
1. **RSS Feeds**: استفاده از سرویس‌های xcancel و nitter
2. **Web Scraping**: اسکرپینگ مستقیم از نیتر با BeautifulSoup

---

## 🏗️ معماری و ساختار فنی

### معماری کلی
```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (HTML/CSS/JS)                │
│                 Dashboard + Login/Register               │
└────────────────────┬────────────────────────────────────┘
                     │ HTTP Requests
┌────────────────────▼────────────────────────────────────┐
│              Flask Web Server (main.py)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Routes     │  │     Auth     │  │   Session    │  │
│  │  Handlers    │  │   Manager    │  │   Manager    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│              Monitoring Engine                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Threading  │  │     RSS      │  │   Scraper    │  │
│  │   Manager    │  │   Parser     │  │   (BS4)      │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│              Data Layer (JSON Files)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   users.json │  │tweets_*.json │  │last_ids.json │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### Stack فناوری

#### Backend
- **Python 3.8+**: زبان برنامه‌نویسی اصلی
- **Flask 2.0+**: فریمورک وب
- **Werkzeug**: مدیریت امنیت و رمزنگاری
- **Threading**: اجرای همزمان نظارت‌ها

#### Data Processing
- **feedparser 6.0+**: پارس کردن RSS Feeds
- **BeautifulSoup4**: اسکرپینگ وب
- **lxml**: پارسر HTML/XML
- **requests**: درخواست‌های HTTP

#### Real-time Features
- **Flask-SocketIO 5.5+**: ارتباط دوطرفه real-time
- **eventlet**: سرور async

#### Others
- **Playwright**: اسکرپینگ پیشرفته (نصب شده اما فعلاً استفاده نمی‌شود)

---

## 🚀 نصب و راه‌اندازی

### پیش‌نیازها
```bash
Python 3.8 یا بالاتر
pip یا poetry
```

### روش نصب با Poetry (توصیه می‌شود)
```bash
# کلون کردن پروژه
git clone https://github.com/your-repo/twitter-monitor.git
cd twitter-monitor

# نصب وابستگی‌ها
poetry install

# فعال کردن محیط مجازی
poetry shell

# اجرای برنامه
python main.py
```

### روش نصب با pip
```bash
# نصب وابستگی‌ها
pip install flask feedparser werkzeug beautifulsoup4 flask-socketio requests lxml eventlet playwright

# اجرای برنامه
python main.py
```

### اجرا در محیط Production
```bash
# استفاده از Gunicorn
gunicorn --bind 0.0.0.0:5000 --workers 4 main:app

# یا با eventlet برای SocketIO
gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:5000 main:app
```

---

## 📱 نحوه استفاده

### راه‌اندازی اولیه
1. برنامه را اجرا کنید: `python main.py`
2. مرورگر را باز کنید: `http://localhost:5000`
3. در صفحه ورود، روی "ثبت نام" کلیک کنید
4. نام کاربری و رمز عبور دلخواه را وارد کنید

### شروع نظارت
1. در داشبورد، نام کاربری توییتر مورد نظر را وارد کنید (مثلاً: `elonmusk`)
2. نوع نظارت را انتخاب کنید:
   - فقط توییت‌ها
   - توییت‌ها + پاسخ‌ها
   - تمام فعالیت‌ها
3. روی "شروع نظارت" کلیک کنید
4. برای مشاهده توییت‌های جمع‌آوری شده، روی "مشاهده توییت‌ها" کلیک کنید

### مدیریت نظارت‌ها
- **متوقف کردن نظارت**: روی دکمه "متوقف کردن" کنار هر حساب کلیک کنید
- **ریست تاریخچه**: قبل از شروع نظارت، گزینه "ریست تاریخچه" را فعال کنید
- **مشاهده توییت‌ها**: لیست کامل توییت‌های ذخیره شده را ببینید

---

## 🔧 جزئیات فنی

### ساختار فایل‌ها
```
twitter-monitor/
├── main.py                 # فایل اصلی برنامه
├── main1.py               # نسخه آزمایشی
├── templates/             # قالب‌های HTML
│   ├── dashboard.html     # داشبورد اصلی
│   ├── login.html         # صفحه ورود
│   ├── register.html      # صفحه ثبت نام
│   └── tweets.html        # نمایش توییت‌ها
├── users.json             # اطلاعات کاربران
├── tweets_*.json          # توییت‌های ذخیره شده
├── last_tweet_ids_*.json  # آخرین ID توییت‌ها
├── pyproject.toml         # وابستگی‌های پروژه
└── README.md              # مستندات
```

### کلاس‌ها و توابع کلیدی

#### مدیریت کاربران
```python
def load_users()
# بارگذاری لیست کاربران از users.json

def save_users(users)
# ذخیره کاربران در فایل

def login_required(f)
# Decorator برای محافظت از صفحات
```

#### مدیریت توییت‌ها
```python
def save_tweet_data(user_id, query, feed_base_url, entry)
# ذخیره توییت جدید با جلوگیری از تکرار

def load_tweets_for_user(user_id, username)
# بارگذاری توییت‌های ذخیره شده کاربر

def scrape_nitter_tweets(username)
# اسکرپینگ توییت‌ها از نیتر
```

#### موتور نظارت
```python
def monitor_search(user_id, query, feed_base_url, interval, reset_history, monitor_type)
# هسته اصلی نظارت - اجرا در Thread جداگانه

def start_monitoring_for_user(user_id, username, monitor_type, reset_history)
# راه‌اندازی نظارت برای یک کاربر

def stop_monitoring_for_user(user_id, username)
# توقف نظارت
```

#### فیلترهای توییت
```python
def is_original_tweet(entry, username, monitor_type)
# تشخیص نوع توییت (اصلی، ریپلای، ریتوییت)

def parse_tweet_date(date_string)
# پارس کردن تاریخ توییت
```

### الگوریتم نظارت

1. **مقداردهی اولیه**
   - بارگذاری آخرین ID توییت از فایل
   - تنظیم زمان شروع نظارت

2. **حلقه نظارت** (هر 5 ثانیه)
   ```python
   while not stop_event.is_set():
       feed = feedparser.parse(feed_url)
       if feed.entries:
           for entry in feed.entries:
               if entry.id == last_entry_id:
                   break
               if is_original_tweet(entry, query, monitor_type):
                   save_tweet_data(user_id, query, feed_base_url, entry)
       time.sleep(interval)
   ```

3. **جلوگیری از تکرار**
   - بررسی ID توییت
   - بررسی محتوا + لینک
   - بررسی محتوا + تاریخ انتشار

### منابع داده (RSS Feeds)

#### xcancel.com
```
https://rss.xcancel.com/search/rss?q=from:{username}&f={type}
```

#### nitter.privacyredirect.com
```
https://nitter.privacyredirect.com/search/rss?q=from:{username}&f={type}
```

پارامترهای `f`:
- `tweets`: فقط توییت‌های اصلی
- `tweets,replies`: توییت‌ها + پاسخ‌ها
- `tweets,replies,mentions`: تمام فعالیت‌ها

---

## 🌐 API و Endpoints

### Authentication Routes

#### `GET /`
- خانه اصلی
- Redirect به dashboard (اگر login باشد) یا login

#### `POST /login`
- ورود کاربر
- **Parameters**: `username`, `password`
- **Response**: Redirect به dashboard یا نمایش خطا

#### `POST /register`
- ثبت نام کاربر جدید
- **Parameters**: `username`, `password`
- **Response**: Redirect به dashboard یا نمایش خطا

#### `GET /logout`
- خروج کاربر
- پاک کردن session

### Dashboard Routes

#### `GET /dashboard`
- نمایش داشبورد اصلی
- **Auth**: Required
- **Response**: لیست حساب‌های در حال نظارت

### Monitoring Routes

#### `POST /start_monitoring`
- شروع نظارت یک حساب
- **Auth**: Required
- **Parameters**:
  - `username`: نام کاربری توییتر
  - `monitor_type`: نوع نظارت
  - `reset_history`: ریست تاریخچه (optional)
- **Response**: Redirect به dashboard

#### `POST /stop_monitoring`
- توقف نظارت یک حساب
- **Auth**: Required
- **Parameters**: `username`
- **Response**: Redirect به dashboard

### Data Routes

#### `GET /tweets/<username>`
- نمایش توییت‌های ذخیره شده
- **Auth**: Required
- **Query Params**: `scrape=true` برای اسکرپینگ لحظه‌ای
- **Response**: صفحه HTML با لیست توییت‌ها

#### `GET /api/monitoring_status`
- وضعیت کلی نظارت
- **Auth**: Required
- **Response**: JSON
```json
{
  "is_active": true,
  "active_usernames": ["username1", "username2"]
}
```

---

## 💾 ساختار پایگاه داده

### users.json
```json
{
  "username": {
    "password": "hashed_password",
    "created_at": "2024-01-01T12:00:00"
  }
}
```

### tweets_{user_id}_{username}.json
```json
[
  {
    "query": "username",
    "source": "https://rss.xcancel.com/search/rss",
    "id": "tweet_id",
    "title": "محتوای توییت",
    "content": "محتوای کامل",
    "published": "تاریخ انتشار",
    "link": "https://twitter.com/user/status/id",
    "author": "نام نویسنده",
    "saved_at": "2024-01-01T12:00:00"
  }
]
```

### last_tweet_ids_{user_id}.json
```json
{
  "username_https://rss.xcancel.com/search/rss": "last_tweet_id"
}
```

---

## ⚙️ تنظیمات پیشرفته

### تغییر فاصله زمانی بررسی
در فایل `main.py`:
```python
# خط 364
thread = threading.Thread(target=monitor_search,
                         args=(user_id, username, feed_base_url, 5, ...))
                                                                    # ↑ اینجا (ثانیه)
```

### افزودن منبع RSS جدید
```python
# خط 359-362
for feed_base_url in [
    "https://rss.xcancel.com/search/rss",
    "https://nitter.privacyredirect.com/search/rss",
    "منبع جدید شما"  # اضافه کنید
]:
```

### تغییر پورت سرور
```python
# آخر فایل main.py
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
                                    # ↑ اینجا
```

### فعال کردن HTTPS
```python
app.run(host='0.0.0.0', port=443, ssl_context='adhoc')
```

### افزودن لاگینگ
```python
import logging
logging.basicConfig(
    filename='twitter_monitor.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
```

---

## 🐛 مشکلات رایج و راه حل

### 1. خطای "Connection refused"
**علت**: سرورهای RSS در دسترس نیستند

**راه حل**:
- از VPN استفاده کنید
- منابع RSS دیگری اضافه کنید
- از حالت اسکرپینگ استفاده کنید

### 2. توییت‌های جدید دریافت نمی‌شوند
**علت**: تاریخچه ریست نشده است

**راه حل**:
- نظارت را متوقف کنید
- گزینه "ریست تاریخچه" را فعال کنید
- دوباره نظارت را شروع کنید

### 3. توییت‌های تکراری
**علت**: مشکل در سیستم فیلتر

**راه حل**:
- فایل `last_tweet_ids_*.json` را حذف کنید
- نظارت را دوباره شروع کنید

### 4. خطای Memory در نظارت طولانی‌مدت
**علت**: انباشته شدن داده در حافظه

**راه حل**:
```python
# اضافه کردن garbage collection
import gc
gc.collect()  # بعد از هر 100 توییت
```

### 5. مشکل RTL در برخی مرورگرها
**راه حل**: اضافه کردن به CSS
```css
* {
    direction: rtl !important;
}
```

---

## 📊 نکات بهینه‌سازی

### Performance
1. استفاده از connection pooling برای requests
2. کش کردن نتایج RSS با TTL
3. استفاده از SQLite به جای JSON برای داده‌های زیاد
4. Pagination برای نمایش توییت‌ها

### Security
1. استفاده از HTTPS در production
2. Rate limiting برای login attempts
3. CSRF protection
4. Input validation و sanitization

### Scalability
1. استفاده از Celery برای task queue
2. Redis برای session management
3. PostgreSQL برای database
4. Load balancing برای ترافیک بالا

---

## 📝 تاریخچه نسخه‌ها

### نسخه 0.1.0 (فعلی)
- پیاده‌سازی سیستم احراز هویت
- نظارت همزمان چندین حساب
- سه حالت نظارت مختلف
- ذخیره خودکار توییت‌ها
- رابط کاربری فارسی
- پشتیبانی از RSS و Web Scraping

---

## 🤝 مشارکت

برای مشارکت در پروژه:
1. Fork کنید
2. Branch جدید بسازید: `git checkout -b feature/AmazingFeature`
3. تغییرات را commit کنید: `git commit -m 'Add some AmazingFeature'`
4. Push کنید: `git push origin feature/AmazingFeature`
5. Pull Request باز کنید

---

## 📄 لایسنس

این پروژه تحت لایسنس MIT منتشر شده است.

---

## 📧 تماس و پشتیبانی

برای گزارش باگ یا پیشنهادات، لطفاً Issue باز کنید.

---

## 🙏 تشکرات

- [Flask](https://flask.palletsprojects.com/)
- [feedparser](https://feedparser.readthedocs.io/)
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/)
- [xcancel.com](https://xcancel.com/)
- [nitter.net](https://nitter.net/)

---

**ساخته شده با ❤️ برای جامعه توسعه‌دهندگان ایرانی**

</div>
# سیستم مانیتورینگ توییتر (Twitter Monitor)

## 📋 درباره پروژه

این پروژه یک سیستم مانیتورینگ توییتر است که به شما امکان می‌دهد فعالیت‌های حساب‌های توییتر را به صورت خودکار رصد کنید و توییت‌های جدید را ذخیره نمایید.

## ✨ امکانات

### 🔐 سیستم احراز هویت
- ثبت‌نام کاربران جدید
- ورود امن با رمزنگاری پسورد
- مدیریت جلسه کاربری

### 📊 مانیتورینگ پیشرفته
- **مانیتورینگ توییت‌های اصلی**: فقط توییت‌های اصلی کاربر
- **توییت‌ها و ریپلای‌ها**: توییت‌ها به همراه پاسخ‌ها
- **همه فعالیت‌ها**: توییت‌ها، ریپلای‌ها و منشن‌ها

### 💾 ذخیره‌سازی
- ذخیره خودکار توییت‌ها در فایل‌های JSON
- جلوگیری از ذخیره تکراری
- نگهداری تاریخچه کامل

### 🌐 رابط کاربری
- داشبورد مدیریتی
- نمایش توییت‌ها با فیلترهای مختلف
- طراحی ریسپانسیو و زیبا
- پشتیبانی کامل از زبان فارسی

## 🚀 نصب و راه‌اندازی

### پیش‌نیازها
```bash
Python 3.8+
```

### نصب وابستگی‌ها
پروژه به صورت خودکار وابستگی‌ها را نصب می‌کند:
- Flask (وب سرور)
- feedparser (پارس RSS)
- werkzeug (امنیت)
- beautifulsoup4 (اسکرپینگ)
- requests (درخواست‌های HTTP)

### اجرای پروژه
```bash
python main.py
```

سرور روی آدرس زیر اجرا می‌شود:
```
http://0.0.0.0:8080
```

## 📖 نحوه استفاده

### 1. ثبت‌نام
- به آدرس `/register` بروید
- نام کاربری و رمز عبور خود را وارد کنید

### 2. افزودن مانیتور
- در داشبورد، نام کاربری توییتر (بدون @) را وارد کنید
- نوع مانیتورینگ را انتخاب کنید:
  - **فقط توییت‌های اصلی**: برای دیدن توییت‌های اصلی
  - **توییت‌ها و ریپلای‌ها**: برای دیدن توییت‌ها و پاسخ‌ها
  - **همه فعالیت‌ها**: برای دیدن همه فعالیت‌ها
- در صورت نیاز، گزینه "پاک کردن تاریخچه" را فعال کنید

### 3. مشاهده توییت‌ها
- روی "مشاهده توییت‌ها" کلیک کنید
- توییت‌ها را با فیلترهای مختلف مشاهده کنید:
  - همه
  - توییت‌ها
  - ریپلای‌ها
  - منشن‌ها
  - ریتوییت‌ها
  - نقل قول‌ها

## 🗂️ ساختار پروژه

```
├── main.py                 # فایل اصلی برنامه
├── templates/              # قالب‌های HTML
│   ├── login.html         # صفحه ورود
│   ├── register.html      # صفحه ثبت‌نام
│   ├── dashboard.html     # داشبورد اصلی
│   └── tweets.html        # نمایش توییت‌ها
├── users.json             # اطلاعات کاربران
├── tweets_*.json          # فایل‌های توییت‌های ذخیره شده
└── last_tweet_ids_*.json  # آخرین ID توییت‌ها
```

## 🔧 تنظیمات

### تغییر پورت
در فایل `main.py`:
```python
app.run(host='0.0.0.0', port=8080, debug=True)
```

### تغییر فاصله چک کردن
در تابع `monitor_search`:
```python
time.sleep(check_interval)  # پیش‌فرض: 5 ثانیه
```

## 🛠️ فناوری‌های استفاده شده

- **Backend**: Flask (Python)
- **Frontend**: HTML, CSS, JavaScript
- **RSS Parser**: feedparser
- **Security**: werkzeug (password hashing)
- **Storage**: JSON files

## 📊 منابع داده

پروژه از دو منبع RSS استفاده می‌کند:
1. `rss.xcancel.com` - منبع اصلی
2. `nitter.privacyredirect.com` - منبع پشتیبان

## ⚠️ نکات مهم

- برای استفاده در محیط تولید، از `debug=False` استفاده کنید
- از یک سرور WSGI مانند Gunicorn در پروداکشن استفاده کنید
- فایل‌های JSON را به صورت دوره‌ای پشتیبان‌گیری کنید
- برای امنیت بیشتر، از HTTPS استفاده کنید

## 🔒 امنیت

- رمزهای عبور با الگوریتم scrypt هش می‌شوند
- کلید سشن به صورت تصادفی تولید می‌شود
- از CSRF protection پشتیبانی می‌شود

## 📝 لاگ‌ها

پروژه اطلاعات زیر را لاگ می‌کند:
- شروع و توقف مانیتورینگ
- توییت‌های جدید یافت شده
- خطاها و مشکلات اتصال

## 🤝 مشارکت

برای مشارکت در پروژه:
1. پروژه را Fork کنید
2. یک Branch جدید بسازید
3. تغییرات خود را Commit کنید
4. Pull Request ارسال کنید

## 📜 لایسنس

این پروژه تحت لایسنس MIT منتشر شده است.

## 👨‍💻 توسعه‌دهنده

ساخته شده با ❤️ برای جامعه توسعه‌دهندگان ایرانی

## 🐛 گزارش باگ

برای گزارش باگ یا پیشنهاد ویژگی جدید، لطفاً یک Issue ایجاد کنید.

## 📞 پشتیبانی

برای سوالات و پشتیبانی، از طریق Issues ارتباط برقرار کنید.

---

**نکته**: این پروژه برای اهداف آموزشی و تحقیقاتی طراحی شده است. لطفاً از آن به صورت مسئولانه استفاده کنید.
