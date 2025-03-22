# main code for analitc x
import os
import json
import time
import threading
import random
import queue
import sqlite3
import logging
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_socketio import SocketIO, emit
import requests
from bs4 import BeautifulSoup
try:
    from lxml import html
    USE_LXML = True
except ImportError:
    USE_LXML = False
import feedparser
import re
from werkzeug.security import generate_password_hash, check_password_hash
import secrets

# تنظیم لاگینگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("twitter_monitor.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("twitter_monitor")

# تعریف اپلیکیشن Flask
app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # کلید رمزنگاری برای جلسه‌ها
socketio = SocketIO(app)

# تنظیمات پایگاه داده
DB_PATH = "twitter_monitor.db"

# لیست سرویس‌های نیتر با اولویت
NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.42l.fr",
    "https://nitter.pussthecat.org",
    "https://nitter.nixnet.services",
    "https://nitter.fdn.fr",
    "https://nitter.1d4.us",
    "https://nitter.kavin.rocks",
    "https://nitter.unixfox.eu",
    "https://nitter.domain.glass",
    "https://nitter.eu",
    "https://nitter.namazso.eu",
    "https://nitter.actionsack.com"
]

# صف پردازش توییت‌ها
tweet_queue = queue.Queue()

# وضعیت سرویس‌های نیتر
nitter_status = {instance: {"active": True, "last_check": 0, "failures": 0} for instance in NITTER_INSTANCES}

# تنظیمات زمانی برای پایش (به ثانیه)
MONITOR_INTERVALS = {
    "high_activity": 30,      # اکانت‌های پرفعالیت
    "medium_activity": 60,    # اکانت‌های با فعالیت متوسط
    "low_activity": 180       # اکانت‌های کم‌فعالیت
}

# متغیرهای گلوبال برای کنترل وضعیت
monitoring_threads = {}
active_usernames = {}  # تغییر به دیکشنری: {user_id: [twitter_usernames]}
is_monitoring_active = False
stop_event = threading.Event()

# ایجاد پایگاه داده
def init_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # جدول کاربران
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )
    ''')

    # جدول توییت‌ها
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tweets (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        twitter_username TEXT,
        tweet_id TEXT,
        title TEXT,
        link TEXT,
        published TEXT,
        type TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, twitter_username, tweet_id)
    )
    ''')

    # جدول مانیتورها
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS monitors (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        twitter_username TEXT,
        monitor_type TEXT,
        last_tweet_id TEXT,
        activity_level TEXT DEFAULT 'medium_activity',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, twitter_username)
    )
    ''')

    conn.commit()
    conn.close()

# فراخوانی تابع ایجاد پایگاه داده
init_database()

# مدیریت کاربران
def load_users():
    if os.path.exists('users.json'):
        try:
            with open('users.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_users(users):
    with open('users.json', 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)
 # save twitte
def save_tweet_data(user_id, query, feed_base_url, entry):
    """Save complete tweet data to a file"""
    filename = f"tweets_{user_id}_{query}.json"
    data = []

    # Load existing data if file exists
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except:
            data = []

    # Create tweet data object with all available information
    tweet_data = {
        "query": query,
        "source": feed_base_url,
        "id": entry.id,
        "title": entry.get('title', ''),
        "content": entry.get('summary', ''),
        "published": entry.get('published', ''),
        "link": entry.get('link', ''),
        "author": entry.get('author', ''),
        "saved_at": datetime.datetime.now().isoformat()
    }

    # Check if this tweet is already saved (avoid duplicates)
    # بررسی دقیق‌تر برای جلوگیری از ذخیره توییت‌های تکراری
    for existing_tweet in data:
        # بررسی ID
        if existing_tweet.get('id') == tweet_data['id']:
            return tweet_data

        # بررسی محتوا و لینک
        if (existing_tweet.get('title') == tweet_data['title'] and 
            existing_tweet.get('link') == tweet_data['link']):
            return tweet_data

        # بررسی محتوا و تاریخ انتشار
        if (existing_tweet.get('title') == tweet_data['title'] and 
            existing_tweet.get('published') == tweet_data['published']):
            return tweet_data

    # Add new tweet to data
    data.append(tweet_data)

    # Save updated data
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return tweet_data

def save_last_id(user_id, query, feed_base_url, last_id):
    """Save the last tweet ID to a file"""
    data = {}
    filename = f"last_tweet_ids_{user_id}.json"

    # Load existing data if file exists
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except:
            data = {}

    # Create a unique key for each query+source combination
    key = f"{query}_{feed_base_url}"

    # Update with new last ID
    data[key] = last_id

    # Save to file
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_last_id(user_id, query, feed_base_url):
    """Load the last tweet ID from file"""
    filename = f"last_tweet_ids_{user_id}.json"

    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                key = f"{query}_{feed_base_url}"
                return data.get(key)
        except:
            return None

    return None

def load_last_id(user_id, query, feed_base_url):
    """Load the last tweet ID from file"""
    filename = f"last_tweet_ids_{user_id}.json"

    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                key = f"{query}_{feed_base_url}"
                return data.get(key)
        except:
            return None

    return None

def is_original_tweet(entry, username, monitor_type='tweets_only'):
    """Check if this tweet should be included based on monitor type"""
    # Get the title of the tweet
    title = entry.get('title', '')
    author = entry.get('author', '')

    # Check if the tweet is from the user we're monitoring
    is_from_user = f"@{username}" in author

    if monitor_type == 'tweets_only':
        # Only include original tweets from the user (no retweets, no replies)
        if title.startswith('RT @') or title.startswith('@'):
            return False
        return is_from_user

    elif monitor_type == 'tweets_replies':
        # Include original tweets and replies from the user (no retweets)
        if title.startswith('RT @'):
            return False
        return is_from_user

    elif monitor_type == 'all_activity':
        # Include all activity: original tweets, replies, and mentions
        if title.startswith('RT @'):
            return False
        # For mentions, either the tweet is from the user or mentions the user
        return is_from_user or f"@{username}" in title

    # Default fallback to original tweets only
    return is_from_user and not title.startswith('RT @') and not title.startswith('@')

def parse_tweet_date(date_str):
    """Parse the tweet date string to a datetime object"""
    try:
        # Try to parse the date string
        dt = datetime.datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S %z')
        return dt
    except:
        try:
            # Try alternative format
            dt = datetime.datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S GMT')
            return dt.replace(tzinfo=datetime.timezone.utc)
        except:
            print(f"Could not parse date: {date_str}")
            return None

def monitor_search(user_id, query, feed_base_url, check_interval=5, reset_history=False, monitor_type='tweets_only'):
    """Monitor search results for a specific query"""
    # URL encode the query to handle special characters
    encoded_query = query.replace(' ', '%20')

    # Adjust feed URL parameters based on monitor type
    feed_params = "f=tweets"
    if monitor_type == 'tweets_replies':
        feed_params = "f=tweets,replies"
    elif monitor_type == 'all_activity':
        feed_params = "f=tweets,replies,mentions"

    feed_url = f"{feed_base_url}?{feed_params}&q={encoded_query}"
    print(f"Starting to monitor search for '{query}' with type '{monitor_type}' from {feed_url}...")

    # Record start time to only show tweets after script started
    start_time = datetime.datetime.now()
    start_time_utc = start_time.astimezone(datetime.timezone.utc)
    print(f"[Search: {query}] Monitoring started at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Load last tweet ID from file (or reset if requested)
    last_entry_id = None if reset_history else load_last_id(user_id, query, feed_base_url)
    if last_entry_id and not reset_history:
        print(f"[Search: {query}] Resuming from last saved tweet ID: {last_entry_id}")
    else:
        print(f"[Search: {query}] Starting fresh monitoring (no history)")

    while not stop_event.is_set():
        try:
            feed = feedparser.parse(feed_url)
            current_time = datetime.datetime.now().strftime('%H:%M:%S')
            print(f"[Search: {query}] Checking for new tweets... ({current_time})")

            if feed.entries:
                if last_entry_id is None:
                    # Find the first tweet that matches our criteria
                    for entry in feed.entries:
                        if is_original_tweet(entry, query, monitor_type):
                            last_entry_id = entry.id
                            save_last_id(user_id, query, feed_base_url, last_entry_id)
                            print(f"[Search: {query}] Found first tweet ID: {last_entry_id}")
                            break
                else:
                    new_entries = []
                    for entry in feed.entries:
                        # Stop if we reach the last processed tweet
                        if entry.id == last_entry_id:
                            break

                        # Only include tweets that match our monitoring criteria
                        if not is_original_tweet(entry, query, monitor_type):
                            continue

                        # Try to parse the published date
                        pub_date = parse_tweet_date(entry.get('published', ''))
                        if pub_date and pub_date < start_time_utc:
                            continue

                        new_entries.append(entry)

                    if new_entries:
                        print(f"\n[Search: {query}] {len(new_entries)} new tweet(s)!")
                        for entry in new_entries:
                            print(f"[Search: {query}] {entry.get('published')}: {entry.get('title')}")
                            print(f"Link: {entry.get('link')}")
                            print("-" * 50)

                            # Save complete tweet data
                            tweet_data = save_tweet_data(user_id, query, feed_base_url, entry)

                        # Update the last ID to the most recent tweet
                        for entry in feed.entries:
                            if is_original_tweet(entry, query, monitor_type):
                                last_entry_id = entry.id
                                save_last_id(user_id, query, feed_base_url, last_entry_id)
                                break

            # Sleep before next check
            time.sleep(check_interval)

        except Exception as e:
            print(f"[Search: {query}] Error: {str(e)}")
            print(f"Retrying in {check_interval} seconds...")
            time.sleep(check_interval)

    print(f"[Search: {query}] Monitoring stopped.")

# تابع برای شروع مانیتورینگ یک کاربر
def start_monitoring_for_user(user_id, username, monitor_type='tweets_only', reset_history=False):
    global active_usernames, is_monitoring_active

    if user_id not in active_usernames:
        active_usernames[user_id] = []

    # Check if already monitoring this username
    for existing in active_usernames[user_id]:
        if isinstance(existing, dict) and existing.get('username') == username:
            # Update monitor type if it changed
            existing['monitor_type'] = monitor_type
            return
        elif existing == username:  # For backward compatibility
            active_usernames[user_id].remove(existing)
            break

    # Add new monitoring with type
    active_usernames[user_id].append({
        'username': username,
        'monitor_type': monitor_type,
        'started_at': datetime.datetime.now().isoformat()
    })

    is_monitoring_active = True

    # Adjust feed URL parameters based on monitor type
    feed_params = "f=tweets"
    if monitor_type == 'tweets_replies':
        feed_params = "f=tweets,replies"
    elif monitor_type == 'all_activity':
        feed_params = "f=tweets,replies,mentions"

    # Start monitoring threads
    threads = []
    for feed_base_url in ["https://rss.xcancel.com/search/rss", "https://nitter.privacyredirect.com/search/rss"]:
        thread = threading.Thread(
            target=monitor_search,
            args=(user_id, username, feed_base_url, 5, reset_history, monitor_type),
            daemon=True
        )
        threads.append(thread)
        thread.start()

    monitoring_threads[username] = threads

# تابع برای توقف مانیتورینگ یک کاربر
def stop_monitoring_for_user(user_id, username):
    global active_usernames, is_monitoring_active

    if user_id in active_usernames:
        # حذف کاربر از لیست مانیتورینگ
        for i, user_monitor in enumerate(active_usernames[user_id]):
            if isinstance(user_monitor, dict) and user_monitor.get('username') == username:
                active_usernames[user_id].pop(i)
                break
            elif user_monitor == username:  # برای سازگاری با نسخه‌های قبلی
                active_usernames[user_id].remove(username)
                break

    # بررسی اینکه آیا هنوز کاربری در حال مانیتورینگ است
    has_active_monitors = False
    for user_monitors in active_usernames.values():
        if user_monitors:
            has_active_monitors = True
            break

    if not has_active_monitors:
        is_monitoring_active = False

# تابع برای بارگذاری توییت‌های ذخیره شده
def load_tweets_for_user(user_id, username):
    filename = f"tweets_{user_id}_{username}.json"
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

# تابع برای بررسی اینکه آیا کاربر لاگین است
def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# مسیرهای Flask
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        users = load_users()

        if username in users and check_password_hash(users[username]['password'], password):
            session['user_id'] = username
            return redirect(url_for('dashboard'))

        flash('نام کاربری یا رمز عبور اشتباه است')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        users = load_users()

        if username in users:
            flash('این نام کاربری قبلاً استفاده شده است')
            return render_template('register.html')

        users[username] = {
            'password': generate_password_hash(password),
            'created_at': datetime.datetime.now().isoformat()
        }

        save_users(users)

        session['user_id'] = username
        return redirect(url_for('dashboard'))

    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session['user_id']
    user_monitors = active_usernames.get(user_id, [])

    return render_template('dashboard.html', 
                          active_usernames=user_monitors,
                          is_monitoring_active=is_monitoring_active)

@app.route('/start_monitoring', methods=['POST'])
@login_required
def start_monitoring_route():
    user_id = session['user_id']
    username = request.form.get('username', '').strip()
    reset_history = request.form.get('reset_history') == 'on'
    monitor_type = request.form.get('monitor_type', 'tweets_only')

    if not username:
        flash('نام کاربری توییتر الزامی است')
        return redirect(url_for('dashboard'))

    # تمیز کردن نام کاربری
    username = re.sub(r'[^\x00-\x7F]+', '', username)
    username = re.sub(r'[^a-zA-Z0-9_]', '', username)

    # Check if monitor type is valid
    if monitor_type not in ['tweets_only', 'tweets_replies', 'all_activity']:
        monitor_type = 'tweets_only'  # Default to tweets only if invalid

    # Check if already monitoring
    is_already_monitoring = False
    if user_id in active_usernames:
        for existing in active_usernames[user_id]:
            if isinstance(existing, dict) and existing.get('username') == username:
                is_already_monitoring = True
                break
            elif existing == username:  # For backward compatibility
                is_already_monitoring = True
                break

    if is_already_monitoring:
        flash(f'حساب @{username} در حال حاضر مانیتور می‌شود')
        return redirect(url_for('dashboard'))

    # اگر تاریخچه را ریست می‌کنیم، فایل‌های قبلی را حذف کنیم
    if reset_history:
        if os.path.exists(f"tweets_{user_id}_{username}.json"):
            os.remove(f"tweets_{user_id}_{username}.json")
        # حذف آیدی آخرین توییت برای این کاربر از فایل
        if os.path.exists(f"last_tweet_ids_{user_id}.json"):
            try:
                with open(f"last_tweet_ids_{user_id}.json", 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key in list(data.keys()):
                        if key.startswith(f"{username}_"):
                            del data[key]
                with open(f"last_tweet_ids_{user_id}.json", 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except:
                pass

    # شروع مانیتورینگ در یک thread جدید
    start_monitoring_for_user(user_id, username, monitor_type, reset_history)

    return redirect(url_for('dashboard'))

@app.route('/stop_monitoring/<username>')
@login_required
def stop_monitoring_route(username):
    user_id = session['user_id']

    if user_id in active_usernames and username in active_usernames[user_id]:
        # توقف مانیتورینگ
        stop_monitoring_for_user(user_id, username)

    return redirect(url_for('dashboard'))

@app.route('/tweets/<username>')
@login_required
def view_tweets(username):
    user_id = session['user_id']

    # بررسی اینکه آیا این کاربر اجازه دسترسی به این توییت‌ها را دارد
    has_access = False

    if user_id in active_usernames:
        for user_monitor in active_usernames[user_id]:
            if isinstance(user_monitor, dict) and user_monitor.get('username') == username:
                has_access = True
                break
            elif user_monitor == username:  # برای سازگاری با نسخه‌های قبلی
                has_access = True
                break

    # اگر دسترسی ندارد، بررسی کنیم که آیا فایل توییت‌ها وجود دارد
    if not has_access and not os.path.exists(f"tweets_{user_id}_{username}.json"):
        flash(f'شما به توییت‌های @{username} دسترسی ندارید')
        return redirect(url_for('dashboard'))

    # نمایش توییت‌های ذخیره شده
    tweets = load_tweets_for_user(user_id, username)
    # مرتب‌سازی توییت‌ها بر اساس تاریخ (جدیدترین اول)
    tweets.sort(key=lambda x: x.get('published', ''), reverse=True)
    return render_template('tweets.html', username=username, tweets=tweets)

@app.route('/api/status')
@login_required
def get_status():
    user_id = session['user_id']
    user_monitors = active_usernames.get(user_id, [])

    # API برای دریافت وضعیت فعلی
    return jsonify({
        "active_usernames": user_monitors,
        "is_monitoring_active": is_monitoring_active
    })

# ایجاد فایل‌های HTML مورد نیاز
def create_templates():
    os.makedirs('templates', exist_ok=True)

    # استایل‌های پایه مشترک برای همه صفحات
    base_styles = """
        :root {
            --primary: #1DA1F2;
            --primary-dark: #1a91da;
            --bg: #ffffff;
            --text: #14171A;
            --text-secondary: #657786;
            --border: #E1E8ED;
            --danger: #E0245E;
            --success: #17BF63;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #f7f9fa;
            color: var(--text);
            line-height: 1.6;
            max-width: 1000px;
            margin: 0 auto;
            padding: 20px;
            direction: rtl;
        }

        h1, h2, h3 {
            color: var(--primary);
            margin-bottom: 1rem;
        }

        a {
            color: var(--primary);
            text-decoration: none;
            transition: color 0.2s;
        }

        a:hover {
            color: var(--primary-dark);
        }

        .container {
            background: white;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            padding: 2rem;
            margin-bottom: 2rem;
        }

        .form-group {
            margin-bottom: 1.5rem;
        }

        label {
            display: block;
            margin-bottom: 0.5rem;
            font-weight: 500;
            color: var(--text);
        }

        input[type="text"],
        input[type="password"] {
            width: 100%;
            padding: 0.75rem 1rem;
            border: 1px solid var(--border);
            border-radius: 4px;
            font-size: 1rem;
            transition: border 0.2s;
        }

        input[type="text"]:focus,
        input[type="password"]:focus {
            border-color: var(--primary);
            outline: none;
            box-shadow: 0 0 0 2px rgba(29,161,242,0.2);
        }

        .btn {
            background: var(--primary);
            color: white;
            border: none;
            padding: 0.75rem 1.5rem;
            border-radius: 50px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }

        .btn:hover {
            background: var(--primary-dark);
        }

        .flash-message {
            padding: 1rem;
            border-radius: 4px;
            margin-bottom: 1.5rem;
            background-color: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }

        .flash-message.error {
            background-color: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }

        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
        }

        .logout-link {
            padding: 0.5rem 1rem;
            background: rgba(29,161,242,0.1);
            border-radius: 50px;
            color: var(--primary);
            font-weight: 500;
        }

        .logout-link:hover {
            background: rgba(29,161,242,0.2);
        }
    """


    # قالب صفحه ورود
    with open('templates/login.html', 'w', encoding='utf-8') as f:
        f.write("""
    <!DOCTYPE html>
    <html dir="rtl" lang="fa">
    <head>
        <title>ورود به سیستم مانیتورینگ توییتر</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            /* استایل‌های پایه */
            :root {
                --primary: #1DA1F2;
                --primary-dark: #1a91da;
                --bg: #ffffff;
                --text: #14171A;
                --text-secondary: #657786;
                --border: #E1E8ED;
                --danger: #E0245E;
                --success: #17BF63;
            }

            * {
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }

            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #f7f9fa;
                color: var(--text);
                line-height: 1.6;
                max-width: 1000px;
                margin: 0 auto;
                padding: 20px;
                direction: rtl;
            }

            h1, h2, h3 {
                color: var(--primary);
                margin-bottom: 1rem;
            }

            a {
                color: var(--primary);
                text-decoration: none;
                transition: color 0.2s;
            }

            a:hover {
                color: var(--primary-dark);
            }

            .container {
                background: white;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                padding: 2rem;
                margin-bottom: 2rem;
            }

            .form-group {
                margin-bottom: 1.5rem;
            }

            label {
                display: block;
                margin-bottom: 0.5rem;
                font-weight: 500;
                color: var(--text);
            }

            input[type="text"],
            input[type="password"] {
                width: 100%;
                padding: 0.75rem 1rem;
                border: 1px solid var(--border);
                border-radius: 4px;
                font-size: 1rem;
                transition: border 0.2s;
            }

            input[type="text"]:focus,
            input[type="password"]:focus {
                border-color: var(--primary);
                outline: none;
                box-shadow: 0 0 0 2px rgba(29,161,242,0.2);
            }

            .btn {
                background: var(--primary);
                color: white;
                border: none;
                padding: 0.75rem 1.5rem;
                border-radius: 50px;
                font-size: 1rem;
                font-weight: 600;
                cursor: pointer;
                transition: background 0.2s;
            }

            .btn:hover {
                background: var(--primary-dark);
            }

            .flash-message {
                padding: 1rem;
                border-radius: 4px;
                margin-bottom: 1.5rem;
                background-color: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            }

            .flash-message.error {
                background-color: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }

            .login-container {
                max-width: 500px;
                margin: 5rem auto;
            }

            .register-link {
                text-align: center;
                margin-top: 2rem;
                color: var(--text-secondary);
            }

            .twitter-icon {
                color: var(--primary);
                font-size: 2.5rem;
                margin-bottom: 1rem;
                text-align: center;
            }
        </style>
    </head>
    <body>
        <div class="login-container container">
            <div class="twitter-icon">
                <svg viewBox="0 0 24 24" width="48" height="48" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M23 3a10.9 10.9 0 0 1-3.14 1.53 4.48 4.48 0 0 0-7.86 3v1A10.66 10.66 0 0 1 3 4s-4 9 5 13a11.64 11.64 0 0 1-7 2c9 5 20 0 20-11.5a4.5 4.5 0 0 0-.08-.83A7.72 7.72 0 0 0 23 3z"></path>
                </svg>
            </div>
            <h1 style="text-align: center;">ورود به سیستم مانیتورینگ توییتر</h1>

            {% with messages = get_flashed_messages() %}
                {% if messages %}
                    {% for message in messages %}
                        <div class="flash-message error">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}

            <form action="/login" method="post">
                <div class="form-group">
                    <label>نام کاربری:</label>
                    <input type="text" name="username" required>
                </div>
                <div class="form-group">
                    <label>رمز عبور:</label>
                    <input type="password" name="password" required>
                </div>
                <button type="submit" class="btn" style="width: 100%;">ورود</button>
            </form>
        </div>

        <div class="register-link">
            <p>حساب کاربری ندارید؟ <a href="/register">ثبت‌نام کنید</a></p>
        </div>
    </body>
    </html>
        """)

    # قالب داشبورد - اصلاح شده (بدون f-string)
    with open('templates/dashboard.html', 'w', encoding='utf-8') as f:
        f.write("""
    <!DOCTYPE html>
    <html dir="rtl" lang="fa">
    <head>
        <title>داشبورد مانیتورینگ توییتر</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            /* استایل‌های پایه */
            :root {
                --primary: #1DA1F2;
                --primary-dark: #1a91da;
                --bg: #ffffff;
                --text: #14171A;
                --text-secondary: #657786;
                --border: #E1E8ED;
                --danger: #E0245E;
                --success: #17BF63;
            }

            * {
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }

            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #f7f9fa;
                color: var(--text);
                line-height: 1.6;
                max-width: 1000px;
                margin: 0 auto;
                padding: 20px;
                direction: rtl;
            }

            h1, h2, h3 {
                color: var(--primary);
                margin-bottom: 1rem;
            }

            a {
                color: var(--primary);
                text-decoration: none;
                transition: color 0.2s;
            }

            a:hover {
                color: var(--primary-dark);
            }

            .container {
                background: white;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                padding: 2rem;
                margin-bottom: 2rem;
            }

            .form-group {
                margin-bottom: 1.5rem;
            }

            label {
                display: block;
                margin-bottom: 0.5rem;
                font-weight: 500;
                color: var(--text);
            }

            input[type="text"],
            input[type="password"] {
                width: 100%;
                padding: 0.75rem 1rem;
                border: 1px solid var(--border);
                border-radius: 4px;
                font-size: 1rem;
                transition: border 0.2s;
            }

            input[type="text"]:focus,
            input[type="password"]:focus {
                border-color: var(--primary);
                outline: none;
                box-shadow: 0 0 0 2px rgba(29,161,242,0.2);
            }

            .btn {
                background: var(--primary);
                color: white;
                border: none;
                padding: 0.75rem 1.5rem;
                border-radius: 50px;
                font-size: 1rem;
                font-weight: 600;
                cursor: pointer;
                transition: background 0.2s;
            }

            .btn:hover {
                background: var(--primary-dark);
            }

            .flash-message {
                padding: 1rem;
                border-radius: 4px;
                margin-bottom: 1.5rem;
                background-color: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            }

            .flash-message.error {
                background-color: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }

            .header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 2rem;
            }

            .logout-link {
                padding: 0.5rem 1rem;
                background: rgba(29,161,242,0.1);
                border-radius: 50px;
                color: var(--primary);
                font-weight: 500;
            }

            .logout-link:hover {
                background: rgba(29,161,242,0.2);
            }

            .user-list {
                margin-top: 1.5rem;
            }

            .user-item {
                padding: 1rem;
                border-bottom: 1px solid var(--border);
                display: flex;
                justify-content: space-between;
                align-items: center;
                transition: background 0.2s;
            }

            .user-item:last-child {
                border-bottom: none;
            }

            .user-item:hover {
                background: rgba(29,161,242,0.05);
            }

            .action-links a {
                margin-right: 1rem;
                padding: 0.4rem 0.8rem;
                border-radius: 4px;
                background: rgba(29,161,242,0.1);
                transition: all 0.2s;
            }

            .action-links a:hover {
                background: rgba(29,161,242,0.2);
            }

            .action-links a.stop-btn {
                background: rgba(224,36,94,0.1);
                color: var(--danger);
            }

            .action-links a.stop-btn:hover {
                background: rgba(224,36,94,0.2);
            }

            .status-container {
                background: white;
                padding: 1rem;
                border-radius: 8px;
                margin-top: 2rem;
                border: 1px solid var(--border);
                display: flex;
                justify-content: space-between;
            }

            .radio-group {
                margin-bottom: 1rem;
            }

            .radio-group label {
                display: flex;
                align-items: center;
                margin-bottom: 0.5rem;
                font-weight: normal;
            }

            .radio-group input[type="radio"] {
                margin-left: 0.5rem;
            }

            .monitor-type {
                font-size: 0.8rem;
                color: var(--text-secondary);
                margin-right: 0.5rem;
                background: rgba(101,119,134,0.1);
                padding: 0.2rem 0.5rem;
                border-radius: 4px;
            }

            .empty-state {
                text-align: center;
                padding: 2rem;
                color: var(--text-secondary);
                background: rgba(101,119,134,0.05);
                border-radius: 8px;
            }

            .username {
                display: flex;
                align-items: center;
            }

            .username svg {
                margin-left: 0.5rem;
                color: var(--primary);
            }

            .status-badge {
                padding: 0.25rem 0.75rem;
                border-radius: 50px;
                font-size: 0.8rem;
                font-weight: 500;
            }

            .status-active {
                background: rgba(23,191,99,0.1);
                color: var(--success);
            }

            .status-inactive {
                background: rgba(101,119,134,0.1);
                color: var(--text-secondary);
            }

            .checkbox-wrapper {
                display: flex;
                align-items: center;
            }

            .checkbox-wrapper input[type="checkbox"] {
                margin-left: 0.5rem;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>داشبورد مانیتورینگ توییتر</h1>
            <a href="/logout" class="logout-link">خروج</a>
        </div>

        {% with messages = get_flashed_messages() %}
            {% if messages %}
                {% for message in messages %}
                    <div class="flash-message">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        <div class="container">
            <h2>افزودن مانیتور جدید</h2>
            <form action="/start_monitoring" method="post">
                <div class="form-group">
                    <label>نام کاربری توییتر (بدون @):</label>
                    <input type="text" name="username" required placeholder="مثال: elonmusk">
                </div>
                <div class="form-group">
                    <label>نوع مانیتورینگ:</label>
                    <div class="radio-group">
                        <label class="radio-label">
                            <input type="radio" name="monitor_type" value="tweets_only" checked> 
                            <span class="radio-text">فقط توییت‌های اصلی</span>
                        </label>
                        <label class="radio-label">
                            <input type="radio" name="monitor_type" value="tweets_replies"> 
                            <span class="radio-text">توییت‌ها و ریپلای‌ها</span>
                        </label>
                        <label class="radio-label">
                            <input type="radio" name="monitor_type" value="all_activity"> 
                            <span class="radio-text">همه فعالیت‌ها (توییت‌ها، ریپلای‌ها و منشن‌ها)</span>
                        </label>
                    </div>
                </div>
                <div class="form-group">
                    <label class="checkbox-label">
                        <input type="checkbox" name="reset_history"> 
                        <span class="checkbox-text">پاک کردن تاریخچه توییت‌ها</span>
                    </label>
                </div>
                <button type="submit" class="btn">شروع مانیتورینگ</button>
            </form>
        </div>

        <div class="container">
            <h2>مانیتورهای فعال</h2>

            {% if active_usernames %}
                <div class="user-list">
                    {% for user_monitor in active_usernames %}
                        <div class="user-item">
                            {% if user_monitor is string %}
                                <div class="user-info">
                                    <span class="username">@{{ user_monitor }}</span>
                                </div>
                                <div class="action-links">
                                    <a href="/tweets/{{ user_monitor }}" class="action-btn view-btn">مشاهده توییت‌ها</a>
                                    <a href="/stop_monitoring/{{ user_monitor }}" class="action-btn stop-btn">توقف مانیتورینگ</a>
                                </div>
                            {% else %}
                                <div class="user-info">
                                    <span class="username">@{{ user_monitor.username }}</span>
                                    <span class="monitor-type">
                                        {% if user_monitor.monitor_type == 'tweets_only' %}
                                            فقط توییت‌های اصلی
                                        {% elif user_monitor.monitor_type == 'tweets_replies' %}
                                            توییت‌ها و ریپلای‌ها
                                        {% elif user_monitor.monitor_type == 'all_activity' %}
                                            همه فعالیت‌ها
                                        {% endif %}
                                    </span>
                                </div>
                                <div class="action-links">
                                    <a href="/tweets/{{ user_monitor.username }}" class="action-btn view-btn">مشاهده توییت‌ها</a>
                                    <a href="/stop_monitoring/{{ user_monitor.username }}" class="action-btn stop-btn">توقف مانیتورینگ</a>
                                </div>
                            {% endif %}
                        </div>
                    {% endfor %}
                </div>
            {% else %}
                <div class="empty-state">
                    <p>هیچ مانیتور فعالی وجود ندارد</p>
                    <p>برای شروع مانیتورینگ، نام کاربری توییتر را در فرم بالا وارد کنید</p>
                </div>
            {% endif %}
        </div>

        <div class="status-container">
            <div class="status-item">
                <span class="status-label">وضعیت:</span>
                <span class="status-value {% if is_monitoring_active %}active{% else %}inactive{% endif %}">
                    {{ 'فعال' if is_monitoring_active else 'غیرفعال' }}
                </span>
            </div>
            <div class="status-item">
                <span class="status-label">تعداد حساب‌های تحت نظر:</span>
                <span class="status-value">{{ active_usernames|length }}</span>
            </div>
        </div>
    </body>
    </html>
        """)

    # ایجاد قالب نمایش توییت‌ها
    # ایجاد قالب نمایش توییت‌ها
    with open('templates/tweets.html', 'w', encoding='utf-8') as f:
        f.write("""
    <!DOCTYPE html>
    <html dir="rtl" lang="fa">
    <head>
        <title>توییت‌های @{{ username }}</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            :root {
                --primary: #1DA1F2;
                --primary-light: rgba(29, 161, 242, 0.1);
                --primary-dark: #1a91da;
                --bg: #ffffff;
                --bg-light: #f7f9fa;
                --text: #14171A;
                --text-secondary: #657786;
                --border: #E1E8ED;
                --danger: #E0245E;
                --success: #17BF63;
                --retweet: #17BF63;
                --mention: #794BC4;
                --reply: #1DA1F2;
                --quote: #F45D22;
            }

            * {
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }

            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: var(--bg-light);
                color: var(--text);
                line-height: 1.6;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                direction: rtl;
            }

            .header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 2rem;
                background: white;
                padding: 1rem 1.5rem;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            }

            .header-title {
                display: flex;
                align-items: center;
            }

            .header-actions {
                display: flex;
                gap: 1rem;
            }

            h1 {
                color: var(--primary);
                margin: 0;
                font-size: 1.5rem;
            }

            .username-badge {
                display: inline-flex;
                align-items: center;
                background: var(--primary-light);
                color: var(--primary);
                padding: 0.3rem 0.8rem;
                border-radius: 50px;
                margin-right: 0.8rem;
                font-weight: 600;
            }

            .back-link, .refresh-btn {
                display: flex;
                align-items: center;
                color: var(--primary);
                text-decoration: none;
                font-weight: 500;
                transition: all 0.2s;
                padding: 0.5rem 1rem;
                border-radius: 50px;
                background: var(--primary-light);
            }

            .back-link:hover, .refresh-btn:hover {
                background: rgba(29, 161, 242, 0.2);
                color: var(--primary-dark);
            }

            .back-link svg, .refresh-btn svg {
                margin-left: 0.5rem;
            }

            .refresh-btn {
                cursor: pointer;
                border: none;
                font-size: 1rem;
                font-family: inherit;
            }

            .tweet-count {
                background: white;
                padding: 1rem 1.5rem;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                margin-bottom: 1.5rem;
                color: var(--text-secondary);
                font-weight: 500;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }

            .tweet-count-text {
                display: flex;
                align-items: center;
            }

            .tweet-count-text svg {
                margin-left: 0.5rem;
                color: var(--primary);
            }

            .tweet-filter {
                display: flex;
                gap: 0.5rem;
            }

            .filter-btn {
                padding: 0.3rem 0.8rem;
                border-radius: 50px;
                background: var(--primary-light);
                color: var(--primary);
                border: none;
                font-size: 0.8rem;
                cursor: pointer;
                transition: all 0.2s;
            }

            .filter-btn:hover, .filter-btn.active {
                background: var(--primary);
                color: white;
            }

            .tweet {
                background: white;
                padding: 1.5rem;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                margin-bottom: 1.5rem;
                transition: transform 0.2s, box-shadow 0.2s;
                position: relative;
                overflow: hidden;
            }

            .tweet:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            }

            .tweet-type {
                position: absolute;
                top: 0;
                right: 0;
                padding: 0.3rem 0.8rem;
                font-size: 0.7rem;
                font-weight: 600;
                border-bottom-left-radius: 8px;
                color: white;
            }

            .tweet-type-original {
                background-color: var(--primary);
            }

            .tweet-type-reply {
                background-color: var(--reply);
            }

            .tweet-type-mention {
                background-color: var(--mention);
            }

            .tweet-type-retweet {
                background-color: var(--retweet);
            }

            .tweet-type-quote {
                background-color: var(--quote);
            }

            .tweet-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 1rem;
                padding-bottom: 0.8rem;
                border-bottom: 1px solid var(--border);
            }

            .tweet-date {
                color: var(--text-secondary);
                font-size: 0.9rem;
                display: flex;
                align-items: center;
            }

            .tweet-date svg {
                margin-left: 0.5rem;
                color: var(--text-secondary);
            }

            .tweet-content {
                margin-bottom: 1.2rem;
                font-size: 1.1rem;
                line-height: 1.5;
                word-break: break-word;
            }

            .tweet-content a {
                color: var(--primary);
                text-decoration: none;
            }

            .tweet-content a:hover {
                text-decoration: underline;
            }

            .tweet-footer {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-top: 1rem;
                padding-top: 0.8rem;
                border-top: 1px solid var(--border);
            }

            .tweet-stats {
                display: flex;
                gap: 1rem;
                color: var(--text-secondary);
                font-size: 0.9rem;
            }

            .tweet-stat {
                display: flex;
                align-items: center;
            }

            .tweet-stat svg {
                margin-left: 0.3rem;
            }

            .tweet-link {
                display: inline-flex;
                align-items: center;
                color: var(--primary);
                text-decoration: none;
                font-weight: 500;
                padding: 0.5rem 1rem;
                border-radius: 50px;
                background: var(--primary-light);
                transition: background 0.2s;
            }

            .tweet-link:hover {
                background: rgba(29, 161, 242, 0.2);
            }

            .tweet-link svg {
                margin-left: 0.5rem;
            }

            .no-tweets {
                background: white;
                padding: 3rem 2rem;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                text-align: center;
                color: var(--text-secondary);
            }

            .no-tweets svg {
                color: var(--primary);
                margin-bottom: 1rem;
                opacity: 0.5;
                width: 48px;
                height: 48px;
            }

            .no-tweets p {
                font-size: 1.1rem;
                margin-bottom: 0.5rem;
            }

            .mention {
                color: var(--primary);
                font-weight: 500;
            }

            .hashtag {
                color: var(--primary);
                font-weight: 500;
            }

            /* تغییر رنگ متن برای تشخیص بهتر انواع توییت */
            .tweet-content-reply {
                border-right: 3px solid var(--reply);
                padding-right: 1rem;
            }

            .tweet-content-mention {
                border-right: 3px solid var(--mention);
                padding-right: 1rem;
            }

            .tweet-content-retweet {
                border-right: 3px solid var(--retweet);
                padding-right: 1rem;
                font-style: italic;
            }

            .tweet-content-quote {
                border-right: 3px solid var(--quote);
                padding-right: 1rem;
                font-style: italic;
            }

            .quoted-tweet {
                margin-top: 1rem;
                padding: 1rem;
                background: var(--bg-light);
                border-radius: 8px;
                border-right: 3px solid var(--quote);
                font-size: 0.9rem;
            }

            .quoted-username {
                font-weight: 600;
                color: var(--text);
                margin-bottom: 0.5rem;
            }

            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }

            .refresh-btn.loading svg {
                animation: spin 1s linear infinite;
            }

            /* فیلتر توییت‌ها با جاوااسکریپت */
            .hidden {
                display: none;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-title">
                <h1>توییت‌های</h1>
                <span class="username-badge">@{{ username }}</span>
            </div>
            <div class="header-actions">
                <button onclick="location.reload()" class="refresh-btn" id="refreshBtn">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M23 4v6h-6"></path>
                        <path d="M1 20v-6h6"></path>
                        <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10"></path>
                        <path d="M20.49 15a9 9 0 0 1-14.85 3.36L1 14"></path>
                    </svg>
                    بروزرسانی
                </button>
                <a href="/dashboard" class="back-link">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M19 12H5M12 19l-7-7 7-7"/>
                    </svg>
                    داشبورد
                </a>
            </div>
        </div>

        {% if tweets %}
            <div class="tweet-count">
                <div class="tweet-count-text">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M23 3a10.9 10.9 0 0 1-3.14 1.53 4.48 4.48 0 0 0-7.86 3v1A10.66 10.66 0 0 1 3 4s-4 9 5 13a11.64 11.64 0 0 1-7 2c9 5 20 0 20-11.5a4.5 4.5 0 0 0-.08-.83A7.72 7.72 0 0 0 23 3z"></path>
                    </svg>
                    <span>{{ tweets|length }} توییت یافت شد</span>
                </div>
                <div class="tweet-filter">
                    <button class="filter-btn active" data-filter="all">همه</button>
                    <button class="filter-btn" data-filter="original">توییت‌ها</button>
                    <button class="filter-btn" data-filter="reply">ریپلای‌ها</button>
                    <button class="filter-btn" data-filter="mention">منشن‌ها</button>
                    <button class="filter-btn" data-filter="retweet">ریتوییت‌ها</button>
                    <button class="filter-btn" data-filter="quote">نقل قول‌ها</button>
                </div>
            </div>

            <div id="tweetContainer">
            {% for tweet in tweets %}
                {% set tweet_type = 'original' %}
                {% if '"' in tweet.title and tweet.title.count('"') >= 2 %}
                    {% set tweet_type = 'quote' %}
                {% elif tweet.title.startswith('RT @') %}
                    {% set tweet_type = 'retweet' %}
                {% elif tweet.title.startswith('@') %}
                    {% set tweet_type = 'reply' %}
                {% elif '@' + username in tweet.title %}
                    {% set tweet_type = 'mention' %}
                {% endif %}

                <div class="tweet tweet-{{ tweet_type }}" data-type="{{ tweet_type }}">
                    <div class="tweet-type tweet-type-{{ tweet_type }}">
                        {% if tweet_type == 'original' %}
                            توییت
                        {% elif tweet_type == 'reply' %}
                            ریپلای
                        {% elif tweet_type == 'mention' %}
                            منشن
                        {% elif tweet_type == 'retweet' %}
                            ریتوییت
                        {% elif tweet_type == 'quote' %}
                            نقل قول
                        {% endif %}
                    </div>

                    <div class="tweet-header">
                        <div class="tweet-date">
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <circle cx="12" cy="12" r="10"></circle>
                                <polyline points="12 6 12 12 16 14"></polyline>
                            </svg>
                            {{ tweet.published }}
                        </div>
                    </div>

                    <div class="tweet-content {% if tweet_type != 'original' %}tweet-content-{{ tweet_type }}{% endif %}">
                        {% if tweet_type == 'quote' %}
                            {% set parts = tweet.title.split('"', 2) %}
                            {{ parts[0]|replace('@', '<span class="mention">@</span>')|replace('#', '<span class="hashtag">#</span>')|safe }}
                            <div class="quoted-tweet">
                                <div class="quoted-username">نقل قول:</div>
                                {{ parts[1]|replace('@', '<span class="mention">@</span>')|replace('#', '<span class="hashtag">#</span>')|safe }}
                            </div>
                        {% else %}
                            {{ tweet.title|replace('@', '<span class="mention">@</span>')|replace('#', '<span class="hashtag">#</span>')|safe }}
                        {% endif %}
                    </div>

                    <div class="tweet-footer">
                        <a href="{{ tweet.link }}" target="_blank" class="tweet-link">
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                                <polyline points="15 3 21 3 21 9"></polyline>
                                <line x1="10" y1="14" x2="21" y2="3"></line>
                            </svg>
                            مشاهده در توییتر
                        </a>
                    </div>
                </div>
            {% endfor %}
            </div>
        {% else %}
            <div class="no-tweets">
                <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M23 3a10.9 10.9 0 0 1-3.14 1.53 4.48 4.48 0 0 0-7.86 3v1A10.66 10.66 0 0 1 3 4s-4 9 5 13a11.64 11.64 0 0 1-7 2c9 5 20 0 20-11.5a4.5 4.5 0 0 0-.08-.83A7.72 7.72 0 0 0 23 3z"></path>
                </svg>
                <p>هیچ توییتی برای @{{ username }} یافت نشد</p>
                <p>لطفاً کمی صبر کنید یا مانیتورینگ را مجدداً راه‌اندازی کنید</p>
            </div>
        {% endif %}

        <script>
            // فیلتر کردن توییت‌ها
            document.addEventListener('DOMContentLoaded', function() {
                const filterButtons = document.querySelectorAll('.filter-btn');
                const tweets = document.querySelectorAll('.tweet');

                filterButtons.forEach(button => {
                    button.addEventListener('click', function() {
                        const filterType = this.getAttribute('data-filter');

                        // فعال کردن دکمه انتخاب شده
                        filterButtons.forEach(btn => btn.classList.remove('active'));
                        this.classList.add('active');

                        // نمایش یا مخفی کردن توییت‌ها بر اساس فیلتر
                        tweets.forEach(tweet => {
                            const tweetType = tweet.getAttribute('data-type');

                            if (filterType === 'all' || filterType === tweetType) {
                                tweet.classList.remove('hidden');
                            } else {
                                tweet.classList.add('hidden');
                            }
                        });
                    });
                });

                // دکمه رفرش
                const refreshBtn = document.getElementById('refreshBtn');
                if (refreshBtn) {
                    refreshBtn.addEventListener('click', function() {
                        this.classList.add('loading');
                        setTimeout(() => {
                            window.location.reload();
                        }, 500);
                    });
                }
            });
        </script>
    </body>
    </html>
            """)

    # اجرای برنامه
    if __name__ == "__main__":
        # ایجاد فایل‌های قالب
        create_templates()

        # راه‌اندازی سرور Flask با socketio
        print("Starting Twitter Monitor Web Interface...")
        print("Open your browser and navigate to http://0.0.0.0:8080")
        socketio.run(app, host='0.0.0.0', port=8080, debug=True, allow_unsafe_werkzeug=True)