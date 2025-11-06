# Twitter Monitor - مستندات پروژه

## خلاصه پروژه
این پروژه یک سیستم نظارت و رصد پیشرفته برای حساب‌های توییتر است که با استفاده از Flask، feedparser و BeautifulSoup ساخته شده است.

## ساختار پروژه
```
twitter-monitor/
├── main.py                     # فایل اصلی برنامه - شامل تمام منطق backend و route handlers
├── templates/                  # قالب‌های HTML
│   ├── dashboard.html         # داشبورد اصلی نظارت
│   ├── login.html             # صفحه ورود
│   ├── register.html          # صفحه ثبت نام
│   └── tweets.html            # نمایش توییت‌های ذخیره شده
├── users.json                 # داده‌های کاربران (username + hashed password)
├── tweets_*.json              # توییت‌های ذخیره شده (هر کاربر-username ترکیب)
├── last_tweet_ids_*.json      # آخرین ID توییت‌ها برای جلوگیری از تکرار
├── pyproject.toml             # وابستگی‌های پروژه (Poetry)
└── README.md                  # مستندات کامل پروژه
```

## تکنولوژی‌های استفاده شده

### Backend
- **Flask 2.0+**: فریمورک وب Python
- **feedparser**: پارس کردن RSS feeds از سرویس‌های xcancel و nitter
- **BeautifulSoup4**: اسکرپینگ وب
- **Threading**: نظارت همزمان چندین حساب

### Authentication & Security
- **Werkzeug**: رمزنگاری رمز عبور (password hashing)
- **Flask Session**: مدیریت جلسات کاربری
- **secrets**: تولید کلید امن برای session

### Data Storage
- **JSON Files**: ذخیره‌سازی کاربران و توییت‌ها

## ویژگی‌های کلیدی
1. ✅ سیستم احراز هویت کامل (Login/Register)
2. ✅ نظارت همزمان چندین حساب توییتر
3. ✅ سه حالت نظارت: فقط توییت‌ها / توییت‌ها + پاسخ‌ها / تمام فعالیت‌ها
4. ✅ ذخیره خودکار توییت‌های جدید
5. ✅ رابط کاربری فارسی (RTL)
6. ✅ دو روش دریافت داده: RSS Feed + Web Scraping

## نحوه اجرا
برنامه به صورت خودکار روی پورت 5000 اجرا می‌شود.
```bash
python main.py
```

سپس به آدرس زیر بروید:
```
http://localhost:5000
```

## منابع داده
پروژه از دو سرویس RSS برای دریافت توییت‌ها استفاده می‌کند:
- **xcancel.com**: `https://rss.xcancel.com/search/rss`
- **nitter**: `https://nitter.privacyredirect.com/search/rss`

## نحوه استفاده
1. ثبت نام و ورود به سیستم
2. در داشبورد، نام کاربری توییتر مورد نظر را وارد کنید
3. نوع نظارت را انتخاب کنید
4. روی "شروع نظارت" کلیک کنید
5. توییت‌های جدید به صورت خودکار ذخیره می‌شوند

## توابع و کلاس‌های کلیدی

### Authentication
- `load_users()`: بارگذاری کاربران از users.json
- `save_users()`: ذخیره کاربران
- `login_required`: decorator برای محافظت از صفحات

### Monitoring Core
- `monitor_search()`: هسته اصلی نظارت - اجرا در thread جداگانه
- `start_monitoring_for_user()`: شروع نظارت برای یک کاربر
- `stop_monitoring_for_user()`: توقف نظارت

### Data Management
- `save_tweet_data()`: ذخیره توییت با جلوگیری از تکرار
- `load_tweets_for_user()`: بارگذاری توییت‌های ذخیره شده
- `scrape_nitter_tweets()`: اسکرپینگ مستقیم از نیتر

## API Endpoints
- `GET /`: صفحه اصلی (redirect به dashboard یا login)
- `POST /login`: ورود کاربر
- `POST /register`: ثبت نام کاربر جدید
- `GET /dashboard`: داشبورد اصلی
- `POST /start_monitoring`: شروع نظارت یک حساب
- `POST /stop_monitoring`: توقف نظارت
- `GET /tweets/<username>`: نمایش توییت‌های ذخیره شده

## تنظیمات
- **Port**: 5000 (قابل تغییر در خط آخر main.py)
- **Check Interval**: 5 ثانیه (قابل تغییر در monitor_search)
- **Debug Mode**: فعال (برای production باید غیرفعال شود)

## نکات امنیتی
- رمزهای عبور با Werkzeug hash می‌شوند
- Session key به صورت تصادفی تولید می‌شود
- از login_required decorator برای محافظت از صفحات استفاده می‌شود

## بهبودهای آینده
- [ ] استفاده از SQLite/PostgreSQL به جای JSON
- [ ] پشتیبانی از WebSocket برای نمایش لحظه‌ای
- [ ] افزودن فیلترهای پیشرفته برای توییت‌ها
- [ ] Export توییت‌ها به CSV/Excel
- [ ] Pagination برای نمایش توییت‌های زیاد
- [ ] افزودن تحلیل‌های آماری

## مشکلات شناخته شده
- در صورت عدم دسترسی به RSS feeds، باید از VPN استفاده کرد
- در نظارت طولانی‌مدت ممکن است مصرف حافظه افزایش یابد

## لینک‌های مفید
- [Flask Documentation](https://flask.palletsprojects.com/)
- [feedparser Documentation](https://feedparser.readthedocs.io/)
- [BeautifulSoup Documentation](https://www.crummy.com/software/BeautifulSoup/)

---

آخرین بروزرسانی: نوامبر 2025
