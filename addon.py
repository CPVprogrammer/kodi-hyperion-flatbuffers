'''
		Kodi -> Hyperion - flatbuffers

        https://github.com/google/flatbuffers/releases
        https://google.github.io/flatbuffers/flatbuffers_guide_writing_schema.html
        https://github.com/hyperion-project/hyperion.docs
        https://docs.hyperion-project.org/en/api/Detect.html
'''

import xbmc
import xbmcvfs
import xbmcaddon
import os

# Add the library path before loading Hyperion
__addon__      = xbmcaddon.Addon()
__cwd__        = __addon__.getAddonInfo('path')
sys.path.append(xbmcvfs.translatePath(os.path.join(__cwd__, 'lib')))

from settings import Settings
from hyperion import Hyperion


if __name__ == "__main__":
    # read settings
    kodi_settings = Settings()

    monitor = xbmc.Monitor()

    first_capture = True

    while not monitor.abortRequested():
        if kodi_settings.grabbing():
            if (first_capture == True):
                hyperion = Hyperion(kodi_settings)
                first_capture = False

            if (hyperion.socket_connected):
                hyperion.capture()

        else:
            if (first_capture == False):
                del hyperion

            first_capture = True
            xbmc.sleep(500)

    del kodi_settings
