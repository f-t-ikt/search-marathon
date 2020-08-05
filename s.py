import os
import json
from googleapiclient.discovery import build

GOOGLE_API_KEY="AIzaSyCngY-f5gnHR_sRYPgIEEAHBCmqXnM2BY0"
CUSTOM_SEARCH_ENGINE_KEY="005557315732923573837:jyc0devbphq"
service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)
# b = a.cse()
text="麻倉もも"
# c = b.list(q=text, cx=CUSTOM_SEARCH_ENGINE_KEY,lr="lang_ja")
# d = c.execute()
response = service.cse().list(q=text, cx=CUSTOM_SEARCH_ENGINE_KEY, lr="lang_ja").execute()
# count = json.dumps(response)["searchInformation"]["totalResults"]
count = response["searchInformation"]["totalResults"]
print(int(count)*2)