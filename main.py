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
DEFAULT_CHANNEL = "test-search-marathon"
TIME_LIMIT = 5*60
POST_LIMIT = 10
STEP = 100
HIT_LIMIT = 50000

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
    global on_game, channel
    text = event_data["event"]["text"]
    if "start" in text and not on_game:
        channel = event_data["event"]["channel"]
        game_thread = threading.Thread(target=game)
        game_thread.start()
    elif "help" in text:
        message = """
Google 検索で指定されたヒット数を目指すゲームです.
この bot 宛に "start" とメンションするとゲームが始まります.
10回検索するか, 5分経過するとゲームオーバーです.
目標件数により近い検索ワードを探しましょう.
ただし, 普通に検索するよりも結果がガバガバなので, 若干運要素も含まれます.
(おことわり: Google カスタム検索 API の無料枠のみを利用するため, 1日にそんなに多くの回数を遊ぶことが出来ません. 「基本無料」を謳うスマホゲーみたいなものだと思って諦めてください.)
                  """
        try:
            client.chat_postMessage(channel=event_data["event"]["channel"], text=message)
        except SlackApiError as e:
            error(e)

@slack_events_adapter.on("message")
def message(event_data):
    if "bot_id" in event_data["event"]:
        return
    global channel
    if event_data["event"]["channel"] != channel:
        return
    user = event_data["event"]["user"]
    text = event_data["event"]["text"]
    try:
        global post_count, on_game, min_score, winner, winning_score, winning_word
        global lock
        lock.acquire()
        if not on_game:
            return
        result = search(text)
        if result == -1:
            client.chat_postMessage(channel=channel, text="検索できませんでした.")
            return
        score = abs(result - goal)
        if min_score > score:
            min_score = score
            winner = "<@" + user + ">"
            winning_score = result
            winning_word = text
        client.chat_postMessage(channel=channel, text=f"「{text}」のヒット数は {result} 件でした！")
        post_count += 1
        print("count:",post_count)
    except SlackApiError as e:
        error(e)
    finally:
        lock.release()

def search(text):
    # return len(text)
    count = "-1"
    try:
        response = service.cse().list(q=text, cx=CUSTOM_SEARCH_ENGINE_KEY, lr="lang_ja").execute()
        count = response["searchInformation"]["totalResults"]
    except HttpError as e:
        print(e)
    return int(count)

def game():
    global goal, min_score, channel
    global lock
    try:
        goal = random.randrange(1, HIT_LIMIT / STEP) * STEP
        min_score = 1<<60
        client.chat_postMessage(channel=channel, text=f"試合開始です！\n目標件数は {goal} 件です！")
    except SlackApiError as e:
        error(e)
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