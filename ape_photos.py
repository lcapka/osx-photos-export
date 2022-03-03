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

    QUERY_VERSIONS = [
                """
                SELECT
                    link.Z_27ALBUMS,
                    zga.Z_PK,
                    zga.ZDIRECTORY,
                    zga.ZFILENAME,
                    zga.ZUUID,
                    zaaa.ZORIGINALFILENAME,
                    zga.ZHASADJUSTMENTS,
                    zaaa.ZVIDEOCPDISPLAYVALUE,
                    zga.ZLATITUDE,
                    zga.ZLONGITUDE,
                    zga.ZFAVORITE,
                    group_concat(k.Z_38KEYWORDS)
                FROM Z_27ASSETS link
                LEFT JOIN ZASSET zga ON link.Z_3ASSETS = zga.Z_PK
                LEFT JOIN ZADDITIONALASSETATTRIBUTES zaaa ON zaaa.ZASSET = link.Z_3ASSETS
                LEFT JOIN ZEXTENDEDATTRIBUTES zea ON zea.Z_PK = zga.ZEXTENDEDATTRIBUTES
                LEFT JOIN Z_1KEYWORDS k ON k.Z_1ASSETATTRIBUTES = zaaa.Z_PK
                WHERE zga.ZTRASHEDSTATE=0
                GROUP BY link.Z_27ALBUMS, zga.Z_PK
                """,
                """
                SELECT
                    link.Z_26ALBUMS,
                    zga.Z_PK,
                    zga.ZDIRECTORY,
                    zga.ZFILENAME,
                    zga.ZUUID,
                    zaaa.ZORIGINALFILENAME,
                    zga.ZHASADJUSTMENTS,
                    zaaa.ZVIDEOCPDISPLAYVALUE,
                    zga.ZLATITUDE,
                    zga.ZLONGITUDE,
                    zga.ZFAVORITE,
                    group_concat(k.Z_37KEYWORDS)
                FROM Z_26ASSETS link
                LEFT JOIN ZGENERICASSET zga ON link.Z_34ASSETS = zga.Z_PK
                LEFT JOIN ZADDITIONALASSETATTRIBUTES zaaa ON zaaa.ZASSET = link.Z_34ASSETS
                LEFT JOIN ZEXTENDEDATTRIBUTES zea ON zea.Z_PK = zga.ZEXTENDEDATTRIBUTES
                LEFT JOIN Z_1KEYWORDS k ON k.Z_1ASSETATTRIBUTES = zaaa.Z_PK
                WHERE zga.ZTRASHEDSTATE=0
                GROUP BY link.Z_26ALBUMS, zga.Z_PK
                """,
                """
                SELECT
                    link.Z_26ALBUMS,
                    link.Z_3ASSETS,
                    zga.ZDIRECTORY,
                    zga.ZFILENAME,
                    zga.ZUUID,
                    zaaa.ZORIGINALFILENAME,
                    zga.ZHASADJUSTMENTS,
                    zaaa.ZVIDEOCPDISPLAYVALUE,
                    zga.ZLATITUDE,
                    zga.ZLONGITUDE,
                    zga.ZFAVORITE,
                    group_concat(k.Z_36KEYWORDS)
                FROM Z_26ASSETS link
                LEFT JOIN ZASSET zga ON link.Z_3ASSETS = zga.Z_PK
                LEFT JOIN ZADDITIONALASSETATTRIBUTES zaaa ON zaaa.ZASSET = link.Z_3ASSETS
                LEFT JOIN ZEXTENDEDATTRIBUTES zea ON zea.Z_PK = zga.ZEXTENDEDATTRIBUTES
                LEFT JOIN Z_1KEYWORDS k ON k.Z_1ASSETATTRIBUTES = zaaa.Z_PK
                WHERE zga.ZTRASHEDSTATE=0
                GROUP BY link.Z_26ALBUMS, zga.Z_PK
                """
    ]

    def __init__(self, photos_library_path):
        db_filename = os.path.join(photos_library_path, 'database', 'Photos.sqlite')
        try:
            self._db = sqlite3.connect(db_filename)
        except sqlite3.OperationalError:
            raise GenericExportError("The database file wasn't not found (%s)." % db_filename)
        self._db.text_factory = lambda x: unicodedata.normalize("NFC", x.decode("utf-8"))

    def _parse_tree(self, parent_id, album_temp, photo_temp, keywords_temp):
        keywords_map = {i:j for i,j in keywords_temp}

        items = []
        for i in album_temp:
            if i[1] != parent_id:
                continue

            # Child tree element
            child = {
                'id': i[0],
                'uuid': i[2],
                'name': i[3]
            }

            # Add photos (if exist)
            photos = []
            for photo in photo_temp:
                if photo[0] != i[0]:
                    continue

                # Check data
                latitude, longitude = photo[8:10]
                gps_valid = isinstance(latitude, (int, float,)) and isinstance(longitude, (int, float,)) and (-90 <= latitude <= 90) and (-180 <= longitude <= 80)
                if not gps_valid:
                    latitude = longitude = None
                keywords_list = [kw for kw in [keywords_map.get(int(i), None) for i in str(photo[11] or '').split(',') if i] if kw]

                photos.append({
                    'id': photo[1],
                    'uuid': photo[4],
                    'directory': photo[2],
                    'filename': photo[3],
                    'originalfilename': photo[5],
                    'adjusted': not not photo[6],
                    'live': photo[7] > 0,
                    # Additional metadata
                    'latitude': latitude,
                    'longitude': longitude,
                    'favourite': photo[10],
                    'keywords': keywords_list,
                    'has_exif_data': any(keywords_list) or gps_valid
                    })

            if photos:
                child['photos'] = photos

            # Add sub-folders (if exist)
            children = self._parse_tree(i[0], album_temp, photo_temp, keywords_temp)
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
        log.debug("%s albums found...", len(album_temp))

        # Fetch keywords
        cursor.execute("SELECT Z_PK, ZTITLE FROM ZKEYWORD")
        keywords_temp = cursor.fetchall()
        log.debug("%s keywords found...", len(keywords_temp))

        # Fetch photo data
        # Note: The ZHASADJUSTMENTS columns contains value 1 for all modified photos. But this doesn't mean location.
        #       Probably - the ZEXTENDEDATTRIBUTES table contains original location while ZGENERICASSET contains current location information.
        #       Apple probably somehow extends values in ZGENERICASSET, while ZEXTENDEDATTRIBUTES seems to have 8 decimal places only.
        #       That's why there is that crazy multiplication+round.
        error = None
        for query in ApePhotos.QUERY_VERSIONS:
            try:
                cursor.execute(query)
                photo_temp = cursor.fetchall()
                break
            except sqlite3.OperationalError as e:
                error = e
        if error is not None:
            raise error
        log.debug("%s photo records found...", len(photo_temp))

        # Merge loaded information
        log.debug("Parsing album tree with root id %s", root_id)
        return self._parse_tree(root_id, album_temp, photo_temp, keywords_temp)
