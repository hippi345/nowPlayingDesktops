import sys
from appscript import app, mactypes
import subprocess
import requests
import spotipy
import os
import spotipy.util as util
import time as timepass
from datetime import datetime, date, time


def ChangeDesktop():
    sp = spotipy.Spotify(auth=token)
    results = sp.current_user_playing_track()
    print(results['item']['album']['images'][1]['url'])
    url = results['item']['album']['images'][1]['url']

    file = 'current_artwork' + str(datetime.now()) + '.jpg'

    with open(file, 'wb') as f:
        f.write(requests.get(url).content)
        f.close()

    app('Finder').desktop_picture.set(mactypes.File(file))
    timepass.sleep(2)
    os.remove(file)

scope = 'user-read-currently-playing'

if len(sys.argv) > 1:
    username = sys.argv[1]
else:
    print("Usage: %s username" % (sys.argv[0],))
    sys.exit()

token = util.prompt_for_user_token(username, scope, client_id='bb0abda0b2b744f49ad246369dec4dca',
                                       client_secret='eea3bcfe5e744413bb40b15d5d5c1533',
                                       redirect_uri='http://localhost/')
if token:
    while(token):
        ChangeDesktop()
        timepass.sleep(1)

else:
    print("Can't get token for", username)
