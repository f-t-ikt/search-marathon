import os
import random
import time
import threading
from flask import Flask
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from slack import WebClient
from slack.errors import SlackApiError
from slackeventsapi import SlackEventAdapter

app = Flask(__name__)

client = WebClient(token=os.environ["SLACK_API_TOKEN"])
slack_events_adapter = SlackEventAdapter(signing_secret=os.environ["SLACK_SIGNING_SECRET"], endpoint="/slack/events", server=app)
service = build("customsearch", "v1", developerKey=os.environ["GOOGLE_API_KEY"])

CUSTOM_SEARCH_ENGINE_KEY = os.environ["CUSTOM_SEARCH_ENGINE_KEY"]
DEFAULT_CHANNEL = os.environ["SLACK_APP_DEFAULT_CHANNEL"]
TIME_LIMIT = 5*60
POST_LIMIT = 10
STEP = 100
HIT_LIMIT = 50000
MY_USER_ID = os.environ["SLACK_APP_USER_ID"]

on_game = False
post_count = 0
goal = 0
min_score = 0
channel = DEFAULT_CHANNEL
winner = ""
winning_score = 0
winning_word = ""
lock = threading.Lock()

@slack_events_adapter.on("app_mention")
def app_mention(event_data):
    data = event_data["event"]
    text = data["text"]
    channel = data["channel"]
    if "start" in text and not on_game:
        start_game(channel)
    elif "help" in text:
        show_help(channel)

def start_game(chan):
    global channel
    channel = chan
    game_thread = threading.Thread(target=game)
    game_thread.start()

def show_help(channel):
    text = """\
Google 検索で指定されたヒット数を目指すゲームです.
この bot 宛に "start" とメンションするとゲームが始まります.
10回検索するか, 5分経過するとゲームオーバーです.
目標件数により近い検索ワードを探しましょう.
ただし, 普通に検索するよりも結果がガバガバなので, 若干運要素も含まれます.
(おことわり: Google カスタム検索 API の無料枠のみを利用するため, 1日にそんなに多くの回数を遊ぶことが出来ません. 「基本無料」を謳うスマホゲーみたいなものだと思って諦めてください.)
"""
    send_message(channel, text)

@slack_events_adapter.on("message")
def message(event_data):
    data = event_data["event"]
    if not is_valid_message(data):
        return
    user = data["user"]
    text = data["text"]
    global post_count, min_score, winner, winning_score, winning_word
    global lock
    with lock:
        if not on_game:
            return
        result, title, link = search(text)
        if result is None:
            send_message(channel, "検索できませんでした.")
            return
        score = abs(result - goal)
        if min_score > score:
            min_score = score
            winner = "<@" + user + ">"
            winning_score = result
            winning_word = text
        send_message(channel, f"「{text}」のヒット数は {result} 件でした！\n検索結果の例: {title} {link}\n残り{POST_LIMIT-post_count-1}回です！")   
        post_count += 1
        print("count:",post_count)

def is_valid_message(data):
    if "subtype" in data or "bot_id" in data:
        return False
    if data["channel"] != channel:
        return False
    text = data["text"]
    if MY_USER_ID in text:
        return False
    
    return True

def search(text):
    # return len(text)
    try:
        response = service.cse().list(q=text, cx=CUSTOM_SEARCH_ENGINE_KEY, lr="lang_ja").execute()
        count = int(response["searchInformation"]["totalResults"])
        title = response["items"][0]["title"]
        link = response["items"][0]["link"]
    except HttpError as e:
        print(e)
        count, title, link = None, None, None
    return count, title, link

def game():
    global goal, min_score, channel
    global lock
    goal = random.randrange(1, HIT_LIMIT // STEP) * STEP
    min_score = 1<<60
    send_message(channel, f"試合開始です！\n目標件数は {goal} 件です！")
    global on_game
    on_game = True
    start_time = time.time()
    global post_count
    while post_count < POST_LIMIT and time.time() - start_time < TIME_LIMIT:
        None
    on_game = False
    global winner, winning_score, winning_word
    try:
        lock.acquire()
        client.chat_postMessage(channel=channel, text=f"試合終了です！\n{winner} さんの *「{winning_word}」* (ヒット数: {winning_score}) が勝利です！")
    except SlackApiError as e:
        error(e)
    finally:
        post_count = 0
        winner = ""
        lock.release()

def send_message(channel, text):
    try:
        client.chat_postMessage(channel=channel, text=text)
    except SlackApiError as e:
        error(e)

def error(e):
    assert e.response["ok"] is False
    assert e.response["error"]
    print(f"Got an error: {e.response['error']}")

# Start the server on port 3000
# def main():
    # slack_events_adapter.start(port=os.environ["PORT"])
@app.route("/")
def hello():
    return "Hello there!"

if __name__ == "__main__":
    app.run(debug=False, host='0.0.0.0', port=os.environ["PORT"])