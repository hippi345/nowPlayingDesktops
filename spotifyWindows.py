import sys
import subprocess
import requests
import spotipy
import os
import spotipy.util as util
import time as timepass
from datetime import datetime, date, time
import ctypes


def ChangeDesktop():
    sp = spotipy.Spotify(auth=token)
    results = sp.current_user_playing_track()
    print(results['item']['album']['images'][1]['url'])
    url = results['item']['album']['images'][1]['url']

    file = 'current_artwork.jpg'
    fileDir = os.path.dirname(os.path.realpath('__file__'))
    print(fileDir)
    filePath = fileDir + file
    print(filePath)

    res = requests.get(url, stream=True)
    res.raise_for_status()
    with open(filePath, 'wb') as albumArt:
        for chunk in res.iter_content(1024):
            albumArt.write(chunk)

    SPI_SETDESKWALLPAPER = 20
    ctypes.windll.user32.SystemParametersInfoW(20, 0, filePath, 2)

    timepass.sleep(0.5)
    # os.remove(filePath)

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
        timepass.sleep(0.5)

else:
    print("Can't get token for", username)
