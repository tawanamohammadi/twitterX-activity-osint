import feedparser
import time
import datetime
import threading
import json
import os
import re
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import secrets

# تعریف اپلیکیشن Flask
app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # کلید رمزنگاری برای جلسه‌ها

# متغیرهای گلوبال برای کنترل وضعیت
monitoring_threads = {}
active_usernames = {}  # تغییر به دیکشنری: {user_id: [twitter_usernames]}
is_monitoring_active = False
stop_event = threading.Event()

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
    for existing_tweet in data:
        if existing_tweet.get('id') == tweet_data['id']:
            return tweet_data

    # Add to data array
    data.append(tweet_data)

    # Save to file
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Tweet saved to {filename}")
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

    # Create base styles that will be used across all templates
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
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            transition: all 0.2s ease;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 2rem;
        }
        .container {
            width: 100%;
            max-width: 900px;
            margin: 0 auto;
            padding: 2rem;
            background: white;
            border-radius: 16px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.05);
        }
        h1, h2 {
            color: var(--text);
            font-weight: 700;
            letter-spacing: -0.025em;
            margin-bottom: 1.5rem;
        }
        h1 {
            font-size: 2.5rem;
            text-align: center;
        }
        .btn {
            padding: 0.75rem 1.5rem;
            font-size: 1rem;
            font-weight: 600;
            color: white;
            background: var(--primary);
            border: none;
            border-radius: 50px;
            cursor: pointer;
            box-shadow: 0 4px 14px rgba(29,161,242,0.2);
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(29,161,242,0.3);
            background: var(--primary-dark);
        }
        input[type="text"], input[type="password"] {
            width: 100%;
            padding: 1rem;
            font-size: 1rem;
            border: 2px solid var(--border);
            border-radius: 12px;
            margin-bottom: 1rem;
            transition: all 0.3s ease;
        }
        input[type="text"]:focus, input[type="password"]:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(29,161,242,0.2);
        }
        .form-group {
            margin-bottom: 1.5rem;
        }
        label {
            display: block;
            font-weight: 600;
            margin-bottom: 0.5rem;
            color: var(--text);
        }
        .flash-message {
            padding: 1rem;
            border-radius: 12px;
            margin-bottom: 1.5rem;
            background: #FEE2E2;
            color: #991B1B;
            border: 1px solid #FCA5A5;
            text-align: center;
        }
        .action-links {
            display: flex;
            gap: 1rem;
            align-items: center;
        }
        .action-links a {
            color: var(--primary);
            text-decoration: none;
            font-weight: 500;
            padding: 0.5rem 1rem;
            border-radius: 50px;
        }
        .action-links a:hover {
            background: rgba(29,161,242,0.1);
        }
    """

    # ایجاد قالب صفحه ورود
    with open('templates/login.html', 'w', encoding='utf-8') as f:
        f.write(f"""
        <!DOCTYPE html>
        <html dir="rtl" lang="fa">
        <head>
            <title>ورود به سیستم مانیتورینگ توییتر</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                {base_styles}
                .login-container {
                    max-width: 450px;
                    width: 100%;
                    margin: 2rem auto;
                    padding: 2.5rem;
                    background: white;
                    border-radius: 20px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                }
                .welcome-text {
                    text-align: center;
                    color: var(--text-secondary);
                    margin-bottom: 2rem;
                }
                .register-link {
                    text-align: center;
                    margin-top: 2rem;
                    padding-top: 1.5rem;
                    border-top: 1px solid var(--border);
                }
                .register-link a {
                    color: var(--primary);
                    text-decoration: none;
                    font-weight: 500;
                }
                .register-link a:hover {
                    text-decoration: underline;
                }
                .btn-login {
                    width: 100%;
                    margin-top: 1rem;
                }
            </style>
        </head>
        <body>
            <div class="login-container">
            <h1>ورود به سیستم مانیتورینگ توییتر</h1>

            {% with messages = get_flashed_messages() %}
                {% if messages %}
                    {% for message in messages %}
                        <div class="flash-message">{{ message }}</div>
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
                <button type="submit" class="btn">ورود</button>
            </form>

            <div class="register-link">
                <p>حساب کاربری ندارید؟ <a href="/register">ثبت‌نام کنید</a></p>
            </div>
        </body>
        </html>
        """)

    # ایجاد قالب صفحه ثبت‌نام
    with open('templates/register.html', 'w', encoding='utf-8') as f:
        f.write("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>ثبت‌نام در سیستم مانیتورینگ توییتر</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
                .form-group { margin-bottom: 15px; }
                .btn { padding: 8px 15px; background: #1DA1F2; color: white; border: none; cursor: pointer; border-radius: 4px; }
                h1 { color: #1DA1F2; }
                input[type="text"], input[type="password"] { padding: 8px; width: 100%; max-width: 300px; border: 1px solid #ddd; border-radius: 4px; }
                label { display: block; margin-bottom: 5px; font-weight: bold; }
                .flash-message { padding: 10px; background-color: #f8d7da; color: #721c24; border-radius: 4px; margin-bottom: 15px; }
                .login-link { margin-top: 20px; }
            </style>
        </head>
        <body>
            <h1>ثبت‌نام در سیستم مانیتورینگ توییتر</h1>

            {% with messages = get_flashed_messages() %}
                {% if messages %}
                    {% for message in messages %}
                        <div class="flash-message">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}

            <form action="/register" method="post">
                <div class="form-group">
                    <label>نام کاربری:</label>
                    <input type="text" name="username" required>
                </div>
                <div class="form-group">
                    <label>رمز عبور:</label>
                    <input type="password" name="password" required>
                </div>
                <button type="submit" class="btn">ثبت‌نام</button>
            </form>

            <div class="login-link">
                <p>قبلاً ثبت‌نام کرده‌اید؟ <a href="/login">وارد شوید</a></p>
            </div>
        </body>
        </html>
        """)

    # ایجاد قالب داشبورد
    with open('templates/dashboard.html', 'w', encoding='utf-8') as f:
        f.write(f"""
<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
    <title>داشبورد مانیتورینگ توییتر</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        {base_styles}
        .dashboard-container {
            display: grid;
            gap: 2rem;
            width: 100%;
            max-width: 1100px;
            margin: 0 auto;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 2px solid var(--border);
        }
        .monitor-card {
            background: white;
            border-radius: 16px;
            padding: 2rem;
            box-shadow: 0 4px 20px rgba(0,0,0,0.05);
            margin-bottom: 2rem;
        }
        .user-list {
            display: grid;
            gap: 1rem;
        }
        .user-item {
            background: white;
            padding: 1.5rem;
            border-radius: 12px;
            border: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: all 0.3s ease;
        }
        .user-item:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0,0,0,0.1);
        }
        .username {
            font-weight: 600;
            font-size: 1.1rem;
        }
        .monitor-type {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            background: rgba(29,161,242,0.1);
            color: var(--primary);
            border-radius: 50px;
            font-size: 0.875rem;
            margin-right: 0.5rem;
        }
        .status-card {
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            color: white;
            padding: 1.5rem;
            border-radius: 16px;
            margin-top: 2rem;
        }
        .status-card p {
            margin: 0.5rem 0;
            opacity: 0.9;
        }
        .radio-group {
            display: grid;
            gap: 0.75rem;
            margin: 1rem 0;
        }
        .radio-group label {
            display: flex;
            align-items: center;
            padding: 0.75rem;
            border: 1px solid var(--border);
            border-radius: 8px;
            cursor: pointer;
        }
        .radio-group label:hover {
            background: rgba(29,161,242,0.05);
        }
        .radio-group input[type="radio"] {
            margin-left: 0.75rem;
        }
        .logout-link {
            color: var(--danger);
            text-decoration: none;
            padding: 0.5rem 1rem;
            border-radius: 50px;
            font-weight: 500;
        }
        .logout-link:hover {
            background: rgba(224,36,94,0.1);
        }
        .form-group { margin-bottom: 15px; }
        .btn { padding: 8px 15px; background: #1DA1F2; color: white; border: none; cursor: pointer; border-radius: 4px; }
        .user-list { margin-top: 30px; }
        .user-item { padding: 10px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; }
        .action-links a { margin-left: 10px; color: #1DA1F2; text-decoration: none; }
        .action-links a:hover { text-decoration: underline; }
        h1, h2 { color: #1DA1F2; }
        input[type="text"] { padding: 8px; width: 100%; max-width: 300px; border: 1px solid #ddd; border-radius: 4px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        .status { padding: 10px; background-color: #f8f9fa; border-radius: 4px; margin-top: 20px; }
        .flash-message { padding: 10px; background-color: #d4edda; color: #155724; border-radius: 4px; margin-bottom: 15px; }
        .logout-link { float: right; }
        .header { display: flex; justify-content: space-between; align-items: center; }
        .radio-group { margin-bottom: 10px; }
        .radio-group label { display: inline-block; margin-right: 15px; font-weight: normal; }
        .monitor-type { font-size: 0.8em; color: #666; margin-left: 5px; }
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

    <form action="/start_monitoring" method="post">
        <div class="form-group">
            <label>نام کاربری توییتر (بدون @):</label>
            <input type="text" name="username" required>
        </div>
        <div class="form-group">
            <label>نوع مانیتورینگ:</label>
            <div class="radio-group">
                <label>
                    <input type="radio" name="monitor_type" value="tweets_only" checked> 
                    فقط توییت‌های اصلی
                </label><br>
                <label>
                    <input type="radio" name="monitor_type" value="tweets_replies"> 
                    توییت‌ها و ریپلای‌ها
                </label><br>
                <label>
                    <input type="radio" name="monitor_type" value="all_activity"> 
                    همه فعالیت‌ها (توییت‌ها، ریپلای‌ها و منشن‌ها)
                </label>
            </div>
        </div>
        <div class="form-group">
            <label>
                <input type="checkbox" name="reset_history"> پاک کردن تاریخچه توییت‌ها
            </label>
        </div>
        <button type="submit" class="btn">شروع مانیتورینگ</button>
    </form>

    <div class="user-list">
        <h2>مانیتورهای فعال</h2>
        {% if active_usernames %}
            {% for user_monitor in active_usernames %}
                <div class="user-item">
                    {% if user_monitor is string %}
                        <span>@{{ user_monitor }}</span>
                        <div class="action-links">
                            <a href="/tweets/{{ user_monitor }}">مشاهده توییت‌ها</a> | 
                            <a href="/stop_monitoring/{{ user_monitor }}">توقف مانیتورینگ</a>
                        </div>
                    {% else %}
                        <span>
                            @{{ user_monitor.username }}
                            <span class="monitor-type">
                                {% if user_monitor.monitor_type == 'tweets_only' %}
                                    (فقط توییت‌های اصلی)
                                {% elif user_monitor.monitor_type == 'tweets_replies' %}
                                    (توییت‌ها و ریپلای‌ها)
                                {% elif user_monitor.monitor_type == 'all_activity' %}
                                    (همه فعالیت‌ها)
                                {% endif %}
                            </span>
                        </span>
                        <div class="action-links">
                            <a href="/tweets/{{ user_monitor.username }}">مشاهده توییت‌ها</a> | 
                            <a href="/stop_monitoring/{{ user_monitor.username }}">توقف مانیتورینگ</a>
                        </div>
                    {% endif %}
                </div>
            {% endfor %}
        {% else %}
            <p>هیچ مانیتور فعالی وجود ندارد</p>
        {% endif %}
    </div>

    <div class="status">
        <p>وضعیت: {{ 'فعال' if is_monitoring_active else 'غیرفعال' }}</p>
        <p>در حال مانیتورینگ {{ active_usernames|length }} حساب</p>
    </div>
</body>
</html>
        """)

    # ایجاد قالب نمایش توییت‌ها
    with open('templates/tweets.html', 'w', encoding='utf-8') as f:
        f.write(f"""
        <!DOCTYPE html>
        <html dir="rtl" lang="fa">
        <head>
            <title>توییت‌های @{{ username }}</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                {base_styles}
                .tweets-container {
                    max-width: 800px;
                    width: 100%;
                    margin: 0 auto;
                }
                .tweet {
                    background: white;
                    padding: 1.5rem;
                    border-radius: 16px;
                    margin-bottom: 1rem;
                    border: 1px solid var(--border);
                    transition: all 0.3s ease;
                }
                .tweet:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 6px 20px rgba(0,0,0,0.1);
                }
                .tweet-header {
                    color: var(--text-secondary);
                    font-size: 0.9rem;
                    margin-bottom: 0.75rem;
                }
                .tweet-content {
                    font-size: 1.1rem;
                    line-height: 1.5;
                    margin-bottom: 1rem;
                }
                .tweet-link {
                    display: inline-flex;
                    align-items: center;
                    color: var(--primary);
                    text-decoration: none;
                    font-weight: 500;
                    padding: 0.5rem 1rem;
                    border-radius: 50px;
                    background: rgba(29,161,242,0.1);
                }
                .tweet-link:hover {
                    background: rgba(29,161,242,0.2);
                }
                .back-link {
                    display: inline-flex;
                    align-items: center;
                    color: var(--text-secondary);
                    text-decoration: none;
                    font-weight: 500;
                    margin-bottom: 2rem;
                }
                .back-link:hover {
                    color: var(--text);
                }
                .stats {
                    background: white;
                    padding: 1rem 1.5rem;
                    border-radius: 12px;
                    margin-bottom: 2rem;
                    border: 1px solid var(--border);
                    color: var(--text-secondary);
                }
                .tweet { padding: 15px; border: 1px solid #eee; margin-bottom: 15px; border-radius: 5px; }
                .tweet:hover { background-color: #f8f9fa; }
                .tweet-header { margin-bottom: 10px; color: #666; font-size: 0.9em; }
                .tweet-content { margin-bottom: 10px; }
                .tweet-link { color: #1DA1F2; text-decoration: none; display: inline-block; margin-top: 5px; }
                .tweet-link:hover { text-decoration: underline; }
                .back-link { display: inline-block; margin-bottom: 20px; color: #1DA1F2; text-decoration: none; }
                .back-link:hover { text-decoration: underline; }
                h1 { color: #1DA1F2; }
                .no-tweets { padding: 20px; background-color: #f8f9fa; border-radius: 5px; text-align: center; }
            </style>
        </head>
        <body>
            <a href="/dashboard" class="back-link">← بازگشت به داشبورد</a>
            <h1>توییت‌های @{{ username }}</h1>

            {% if tweets %}
                <p>{{ tweets|length }} توییت یافت شد</p>
                {% for tweet in tweets %}
                    <div class="tweet">
                        <div class="tweet-header">
                            {{ tweet.published }}
                        </div>
                        <div class="tweet-content">
                            {{ tweet.title }}
                        </div>
                        <a href="{{ tweet.link }}" target="_blank" class="tweet-link">مشاهده در توییتر</a>
                    </div>
                {% endfor %}
            {% else %}
                <div class="no-tweets">
                    <p>هیچ توییتی برای @{{ username }} یافت نشد</p>
                </div>
            {% endif %}
        </body>
        </html>
        """)

# اجرای برنامه
if __name__ == "__main__":
    # ایجاد فایل‌های قالب
    create_templates()

    # راه‌اندازی سرور Flask
    print("Starting Twitter Monitor Web Interface...")
    print("Open your browser and navigate to http://127.0.0.1:8080")
    app.run(host='0.0.0.0', port=8080, debug=True)