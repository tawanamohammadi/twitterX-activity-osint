import feedparser
import time
import datetime
import threading
import json
import os
import re
from flask import Flask, render_template, request, jsonify, redirect, url_for

# تعریف اپلیکیشن Flask
app = Flask(__name__)

# متغیرهای گلوبال برای کنترل وضعیت
monitoring_threads = {}
active_usernames = []
is_monitoring_active = False
stop_event = threading.Event()

def save_tweet_data(query, feed_base_url, entry):
    """Save complete tweet data to a file"""
    filename = f"tweets_{query}.json"
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

def save_last_id(query, feed_base_url, last_id):
    """Save the last tweet ID to a file"""
    data = {}
    filename = "last_tweet_ids.json"

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

def load_last_id(query, feed_base_url):
    """Load the last tweet ID from file"""
    filename = "last_tweet_ids.json"

    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                key = f"{query}_{feed_base_url}"
                return data.get(key)
        except:
            return None

    return None

def is_original_tweet(entry, username):
    """
    Check if a tweet is an original tweet from the specified user (not a mention or reply)

    Returns True only if:
    1. The author is the username we're tracking
    2. The tweet is not a reply (doesn't start with 'R to @')
    3. The tweet URL contains the username
    """
    # Check if the author matches our username
    author = entry.get('author', '')
    if not author or not author.startswith(f"@{username}"):
        return False

    # Check if it's not a reply
    title = entry.get('title', '')
    if title.startswith('R to @'):
        return False

    # Check if the URL contains the username (to ensure it's from the user)
    link = entry.get('link', '')
    if not link or f"/{username}/status/" not in link:
        return False

    return True

def parse_tweet_date(date_str):
    """Parse tweet date string to datetime object"""
    try:
        return datetime.datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S %z')
    except:
        return None

def monitor_search(query, feed_base_url, check_interval=5, reset_history=False):
    """Monitor search results for a specific query"""
    # URL encode the query to handle special characters
    encoded_query = query.replace(' ', '%20')
    feed_url = f"{feed_base_url}?f=tweets&q={encoded_query}"
    print(f"Starting to monitor search for '{query}' from {feed_url}...")

    # Record start time to only show tweets after script started
    start_time = datetime.datetime.now()
    start_time_utc = start_time.astimezone(datetime.timezone.utc)
    print(f"[Search: {query}] Monitoring started at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[Search: {query}] Only showing original tweets from @{query} posted after this time")

    # Load last tweet ID from file (or reset if requested)
    last_entry_id = None if reset_history else load_last_id(query, feed_base_url)
    if last_entry_id and not reset_history:
        print(f"[Search: {query}] Resuming from last saved tweet ID: {last_entry_id}")
    else:
        print(f"[Search: {query}] Starting fresh monitoring (no history)")

    # Initial fetch to get the latest tweet ID but don't save old tweets
    try:
        feed = feedparser.parse(feed_url)
        if feed.entries:
            # Find the latest original tweet from the user
            for entry in feed.entries:
                if is_original_tweet(entry, query):
                    last_entry_id = entry.id
                    save_last_id(query, feed_base_url, last_entry_id)
                    print(f"[Search: {query}] Found latest original tweet ID: {last_entry_id}")
                    break
    except Exception as e:
        print(f"[Search: {query}] Error during initial fetch: {str(e)}")

    while not stop_event.is_set():
        try:
            feed = feedparser.parse(feed_url)
            current_time = datetime.datetime.now().strftime('%H:%M:%S')
            print(f"[Search: {query}] Checking for new tweets... ({current_time})")

            if feed.entries:
                if last_entry_id is None:
                    # Find the first original tweet from the user
                    for entry in feed.entries:
                        if is_original_tweet(entry, query):
                            last_entry_id = entry.id
                            save_last_id(query, feed_base_url, last_entry_id)
                            print(f"[Search: {query}] Found first original tweet ID: {last_entry_id}")
                            break
                else:
                    new_entries = []
                    for entry in feed.entries:
                        # Stop if we reach the last processed tweet
                        if entry.id == last_entry_id:
                            break

                        # Only include original tweets from the user
                        if not is_original_tweet(entry, query):
                            continue

                        # Try to parse the published date
                        pub_date = parse_tweet_date(entry.get('published', ''))
                        if pub_date and pub_date < start_time_utc:
                            continue

                        new_entries.append(entry)

                    if new_entries:
                        print(f"\n[Search: {query}] {len(new_entries)} new original tweet(s)!")
                        for entry in new_entries:
                            print(f"[Search: {query}] {entry.get('published')}: {entry.get('title')}")
                            print(f"Link: {entry.get('link')}")
                            print("-" * 50)

                            # Save complete tweet data
                            tweet_data = save_tweet_data(query, feed_base_url, entry)

                        # Update the last ID to the most recent tweet
                        for entry in feed.entries:
                            if is_original_tweet(entry, query):
                                last_entry_id = entry.id
                                save_last_id(query, feed_base_url, last_entry_id)
                                break
            else:
                print(f"[Search: {query}] No tweets found in feed. Checking again in {check_interval} seconds...")

            # Check if we should stop every check_interval seconds
            for _ in range(check_interval):
                if stop_event.is_set():
                    break
                time.sleep(1)

        except Exception as e:
            print(f"[Search: {query}] Error: {str(e)}")
            print(f"Retrying in {check_interval} seconds...")
            time.sleep(check_interval)

    print(f"[Search: {query}] Monitoring stopped.")

# تابع برای شروع مانیتورینگ یک کاربر
def start_monitoring_for_user(username, reset_history=False):
    global active_usernames, is_monitoring_active

    if username in active_usernames:
        return

    active_usernames.append(username)
    is_monitoring_active = True

    # راه‌اندازی thread‌های مانیتورینگ
    threads = []
    for feed_base_url in ["https://rss.xcancel.com/search/rss", "https://nitter.privacyredirect.com/search/rss"]:
        thread = threading.Thread(
            target=monitor_search,
            args=(username, feed_base_url, 5, reset_history),
            daemon=True
        )
        threads.append(thread)
        thread.start()

    monitoring_threads[username] = threads

# تابع برای توقف مانیتورینگ یک کاربر
def stop_monitoring_for_user(username):
    global active_usernames, is_monitoring_active

    if username in active_usernames:
        active_usernames.remove(username)

    if not active_usernames:
        is_monitoring_active = False

# تابع برای بارگذاری توییت‌های ذخیره شده
def load_tweets_for_user(username):
    filename = f"tweets_{username}.json"
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

# مسیرهای Flask
@app.route('/')
def index():
    # صفحه اصلی با فرم ورود نام کاربری
    return render_template('index.html', active_usernames=active_usernames)

@app.route('/start_monitoring', methods=['POST'])
def start_monitoring_route():
    username = request.form.get('username', '').strip()
    reset_history = request.form.get('reset_history') == 'on'

    if not username:
        return jsonify({"error": "Username is required"}), 400

    # تمیز کردن نام کاربری
    username = re.sub(r'[^\x00-\x7F]+', '', username)
    username = re.sub(r'[^a-zA-Z0-9_]', '', username)

    if username in active_usernames:
        return jsonify({"error": f"Already monitoring @{username}"}), 400

    # اگر تاریخچه را ریست می‌کنیم، فایل‌های قبلی را حذف کنیم
    if reset_history:
        if os.path.exists(f"tweets_{username}.json"):
            os.remove(f"tweets_{username}.json")
        # حذف آیدی آخرین توییت برای این کاربر از فایل
        if os.path.exists("last_tweet_ids.json"):
            try:
                with open("last_tweet_ids.json", 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key in list(data.keys()):
                        if key.startswith(f"{username}_"):
                            del data[key]
                with open("last_tweet_ids.json", 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except:
                pass

    # شروع مانیتورینگ در یک thread جدید
    start_monitoring_for_user(username, reset_history)

    return redirect(url_for('index'))

@app.route('/stop_monitoring/<username>')
def stop_monitoring_route(username):
    if username in active_usernames:
        # توقف مانیتورینگ
        stop_monitoring_for_user(username)

    return redirect(url_for('index'))

@app.route('/tweets/<username>')
def view_tweets(username):
    # نمایش توییت‌های ذخیره شده
    tweets = load_tweets_for_user(username)
    # مرتب‌سازی توییت‌ها بر اساس تاریخ (جدیدترین اول)
    tweets.sort(key=lambda x: x.get('published', ''), reverse=True)
    return render_template('tweets.html', username=username, tweets=tweets)

@app.route('/api/status')
def get_status():
    # API برای دریافت وضعیت فعلی
    return jsonify({
        "active_usernames": active_usernames,
        "is_monitoring_active": is_monitoring_active
    })

# ایجاد فایل‌های HTML مورد نیاز
def create_templates():
    os.makedirs('templates', exist_ok=True)

    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Twitter Monitor</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                :root {
                    --primary: #1DA1F2;
                    --bg: #ffffff;
                    --text: #14171A;
                    --secondary-bg: #f8f9fa;
                    --border: #E1E8ED;
                }
                body { 
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                    background: var(--bg);
                    color: var(--text);
                }
                .form-group {
                    margin-bottom: 20px;
                    background: var(--secondary-bg);
                    padding: 20px;
                    border-radius: 12px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                }
                .btn {
                    padding: 12px 24px;
                    background: var(--primary);
                    color: white;
                    border: none;
                    cursor: pointer;
                    border-radius: 50px;
                    font-weight: 600;
                    transition: all 0.2s;
                }
                .btn:hover {
                    transform: translateY(-1px);
                    box-shadow: 0 4px 8px rgba(29,161,242,0.2);
                }
                .user-list {
                    margin-top: 48px;
                }
                .user-item {
                    padding: 20px;
                    background: var(--bg);
                    border: 1px solid var(--border);
                    margin-bottom: 16px;
                    border-radius: 12px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    transition: all 0.2s;
                }
                .user-item:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 4px 12px rgba(0,0,0,0.05);
                }
                .action-links a {
                    margin-left: 15px;
                    color: var(--primary);
                    text-decoration: none;
                    font-weight: 500;
                    padding: 6px 12px;
                    border-radius: 50px;
                    transition: all 0.2s;
                }
                .action-links a:hover {
                    background: rgba(29,161,242,0.1);
                }
                h1, h2 {
                    color: var(--text);
                    font-weight: 700;
                    letter-spacing: -0.025em;
                    margin-bottom: 1.5em;
                }
                input[type="text"] {
                    padding: 12px;
                    width: 100%;
                    max-width: 300px;
                    border: 2px solid var(--border);
                    border-radius: 8px;
                    font-size: 16px;
                    transition: all 0.2s;
                }
                input[type="text"]:focus {
                    border-color: var(--primary);
                    outline: none;
                    box-shadow: 0 0 0 3px rgba(29,161,242,0.2);
                }
                label {
                    display: block;
                    margin-bottom: 8px;
                    font-weight: 600;
                    color: var(--text);
                }
                .status {
                    padding: 15px;
                    background: var(--secondary-bg);
                    border-radius: 12px;
                    margin-top: 30px;
                    border: 1px solid var(--border);
                }
                .checkbox-wrapper {
                    display: flex;
                    align-items: center;
                    margin-top: 10px;
                }
                input[type="checkbox"] {
                    margin-right: 8px;
                }
            </style>
        </head>
        <body>
            <h1>Twitter Monitor</h1>
            <form action="/start_monitoring" method="post">
                <div class="form-group">
                    <label>Twitter Username (without @):</label>
                    <input type="text" name="username" required>
                </div>
                <div class="form-group">
                    <label>
                        <input type="checkbox" name="reset_history"> Reset tweet history
                    </label>
                </div>
                <button type="submit" class="btn">Start Monitoring</button>
            </form>

            <div class="user-list">
                <h2>Active Monitors</h2>
                {% if active_usernames %}
                    {% for username in active_usernames %}
                        <div class="user-item">
                            <span>@{{ username }}</span>
                            <div class="action-links">
                                <a href="/tweets/{{ username }}">View Tweets</a> | 
                                <a href="/stop_monitoring/{{ username }}">Stop Monitoring</a>
                            </div>
                        </div>
                    {% endfor %}
                {% else %}
                    <p>No active monitors</p>
                {% endif %}
            </div>

            <div class="status">
                <p>Status: {{ 'Active' if is_monitoring_active else 'Idle' }}</p>
                <p>Monitoring {{ active_usernames|length }} account(s)</p>
            </div>
        </body>
        </html>
        """)

    with open('templates/tweets.html', 'w', encoding='utf-8') as f:
        f.write("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Tweets for @{{ username }}</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                :root {
                    --primary: #1DA1F2;
                    --bg: #ffffff;
                    --text: #14171A;
                    --secondary-text: #657786;
                    --secondary-bg: #f8f9fa;
                    --border: #E1E8ED;
                }
                body {
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                    background: var(--bg);
                    color: var(--text);
                }
                .tweet {
                    padding: 20px;
                    border: 1px solid var(--border);
                    margin-bottom: 20px;
                    border-radius: 16px;
                    transition: all 0.2s;
                    background: var(--bg);
                }
                .tweet:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 4px 12px rgba(0,0,0,0.05);
                }
                .tweet-header {
                    margin-bottom: 12px;
                    color: var(--secondary-text);
                    font-size: 0.9em;
                    display: flex;
                    align-items: center;
                }
                .tweet-content {
                    margin-bottom: 15px;
                    line-height: 1.5;
                    font-size: 16px;
                }
                .tweet-link {
                    color: var(--primary);
                    text-decoration: none;
                    display: inline-block;
                    padding: 8px 16px;
                    border-radius: 50px;
                    font-weight: 500;
                    transition: all 0.2s;
                    font-size: 0.9em;
                }
                .tweet-link:hover {
                    background: rgba(29,161,242,0.1);
                }
                .back-link {
                    display: inline-flex;
                    align-items: center;
                    margin-bottom: 30px;
                    color: var(--primary);
                    text-decoration: none;
                    font-weight: 600;
                    padding: 8px 16px;
                    border-radius: 50px;
                    transition: all 0.2s;
                }
                .back-link:hover {
                    background: rgba(29,161,242,0.1);
                }
                h1 {
                    color: var(--text);
                    font-weight: 700;
                    letter-spacing: -0.025em;
                    margin: 20px 0 30px;
                }
                .no-tweets {
                    padding: 40px;
                    background: var(--secondary-bg);
                    border-radius: 16px;
                    text-align: center;
                    border: 1px solid var(--border);
                }
                .tweet-count {
                    color: var(--secondary-text);
                    margin-bottom: 20px;
                    font-size: 0.9em;
                }
            </style>
        </head>
        <body>
            <a href="/" class="back-link">← Back to Monitor</a>
            <h1>Tweets for @{{ username }}</h1>

            {% if tweets %}
                <p>Found {{ tweets|length }} tweets</p>
                {% for tweet in tweets %}
                    <div class="tweet">
                        <div class="tweet-header">
                            {{ tweet.published }}
                        </div>
                        <div class="tweet-content">
                            {{ tweet.title }}
                        </div>
                        <a href="{{ tweet.link }}" target="_blank" class="tweet-link">View on Twitter</a>
                    </div>
                {% endfor %}
            {% else %}
                <div class="no-tweets">
                    <p>No tweets found for @{{ username }}</p>
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
    print("Open your browser and navigate to http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=8080, debug=True)