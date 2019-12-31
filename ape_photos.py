#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Apple Photos Export - ApePhotos class

The ApePhotos class provides methods to work with Apple Photos database.

--- License ---

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
this program. If not, see <http://www.gnu.org/licenses/>.
"""

import sqlite3, logging, os, unicodedata
from ape_errors import *

log = logging.getLogger("ape_photos")

class ApePhotos:
    """Implements Photos related method"""

    def __init__(self, photos_library_path):
        db_filename = os.path.join(photos_library_path, 'database', 'Photos.sqlite')
        try:
            self._db = sqlite3.connect(db_filename)
        except sqlite3.OperationalError:
            raise GenericExportError("The database file wasn't not found (%s)." % db_filename)
        self._db.text_factory = lambda x: unicodedata.normalize("NFC", x.decode("utf-8"))

    def _parse_tree(self, parent_id, album_temp, photo_temp):
        items = []
        for i in album_temp:
            if i[1] == parent_id:
                child = {
                    'id': i[0],
                    'uuid': i[2],
                    'name': i[3]
                }

                # Add photos
                photos = [{'id': photo[1], 'uuid': photo[4], 'directory': photo[2], 'filename': photo[3], 'originalfilename': photo[5], 'adjusted': not not photo[6], 'live': photo[7] > 0} for photo in photo_temp if photo[0] == i[0]]
                if photos:
                    child['photos'] = photos

                # Add sub-folders
                children = self._parse_tree(i[0], album_temp, photo_temp)
                if children:
                    child['children'] = children

                if photos or children:
                    items.append(child)

        return sorted(items, key=lambda child: child['name'])

    def fetch_albums(self):
        cursor = self._db.cursor()

        # Unsure how to identify root album. The ZKIND columns seems to be a bad idea, not sure if the ZCLOUDGUID column is better.
        # cursor.execute('SELECT Z_PK FROM ZGENERICALBUM WHERE ZKIND = 3999')
        cursor.execute("SELECT Z_PK FROM ZGENERICALBUM WHERE ZCLOUDGUID = '----Root-Folder----'")

        root_id = cursor.fetchone()
        if not root_id:
            raise GenericExportError("The root folder wasn't found.")
        else:
            root_id = root_id[0]

        # Fetch album data
        cursor.execute("SELECT Z_PK, ZPARENTFOLDER, ZUUID, ZTITLE FROM ZGENERICALBUM WHERE ZTITLE IS NOT NULL")
        album_temp = cursor.fetchall()

        # Fetch photo data
        cursor.execute("""
            SELECT link.Z_26ALBUMS, zga.Z_PK, zga.ZDIRECTORY, zga.ZFILENAME, zga.ZUUID, zaa.ZORIGINALFILENAME, zga.ZHASADJUSTMENTS, zaa.ZVIDEOCPDISPLAYVALUE
            FROM ZGENERICASSET zga
            LEFT JOIN Z_26ASSETS link ON link.Z_34ASSETS = zga.Z_PK
            LEFT JOIN ZADDITIONALASSETATTRIBUTES zaa ON zaa.ZASSET = zga.Z_PK
            """)
        photo_temp = cursor.fetchall()

        # Merge loaded information
        log.debug("Parse album tree with root id %s", root_id)
        return self._parse_tree(root_id, album_temp, photo_temp)
