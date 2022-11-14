#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Apple Photos Export - ApeExporter class

The ApeExporter class provides methods to export photos from the Apple Photos to the output directory.

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

import subprocess, logging, os, shutil, re, json
from ape_errors import *

try:
    import exiftool
    exif_tool = exiftool.ExifTool()
except ModuleNotFoundError:
    exif_tool = None

log = logging.getLogger("ape_exporter")

re_jpeg = re.compile(r'\.jpg$', re.IGNORECASE)
re_movies = re.compile(r'\.(mov|mp4)$', re.IGNORECASE)


class ApeExporter:
    """Implements photo handling methods using AppleScript and direct file access."""

    def __init__(self, photos_library_path, temp_directory, originals_subdir_name='Originals', update_exif=False):
        self._photos_library_path = photos_library_path
        self._temp_directory = temp_directory
        self._originals_subdir_name = originals_subdir_name
        self._update_exif = not not update_exif and exif_tool

        if not not update_exif and exif_tool is None:
            raise GenericExportError("The pyexiftool package is missing to update EXIF information. See http://smarnach.github.io/pyexiftool/")

        if os.listdir(temp_directory):
            raise GenericExportError("The temporary directory must be empty (%s)." % temp_directory)

        if not originals_subdir_name:
            raise GenericExportError("The originals sub-directory must be set.")

        if not exif_tool.running:
            if 'start' in dir(exif_tool):
                exif_tool.start()
            elif 'run' in dir(exif_tool):
                exif_tool.run()

    def _export_internal(self, target_path, folder):
        target_path = os.path.join(target_path, folder['name'])

        # Recursive walk
        if 'children' in folder:
            for child in folder['children']:
                self._export_internal(target_path, child)

        # Export photos
        if 'photos' in folder:
            # Create output path, with the sub-directory if needed
            if any(photo['adjusted'] for photo in folder['photos']):
                os.makedirs(os.path.join(target_path, self._originals_subdir_name), exist_ok=True)
            else:
                os.makedirs(os.path.join(target_path), exist_ok=True)

            # Export originals directly from the photoslibrary (if possible)
            failed_direct_access = []
            for photo in folder['photos']:
                # Well, I don't know how to link the live photo .mov file
                if photo['live']:
                    failed_direct_access.append(photo)
                    continue

                source_filename = os.path.join(self._photos_library_path, 'originals', photo['directory'], photo['filename'])

                # Use temporary file to do the EXIF update below, if needed.
                temp_filename = os.path.join(self._temp_directory, photo['originalfilename'])

                # Store originals for adjusted/modified photos in the Originals sub-directory.
                if photo['adjusted']:
                    target_filename = os.path.join(target_path, self._originals_subdir_name, photo['originalfilename'])
                else:
                    target_filename = os.path.join(target_path, photo['originalfilename'])

                request_exif_update = self._update_exif and photo['has_exif_data']

                try:
                    to_filename = temp_filename if request_exif_update else target_filename
                    log.debug("Copying %s to %s", source_filename, to_filename)
                    shutil.copyfile(source_filename, to_filename)
                except FileNotFoundError:
                    log.error("Export has failed for %s", photo)
                    failed_direct_access.append(photo)
                    continue

                # If exif update required...
                if request_exif_update:
                    self._run_update_exif([{
                            'latitude': photo['latitude'],
                            'longitude': photo['longitude'],
                            'keywords': photo['keywords'],
                            'filename': temp_filename
                        }])
                    log.debug("Moving %s to %s", temp_filename, target_filename)
                    shutil.move(temp_filename, target_filename)

            # Export missing originals and adjusted photos using AppleScript call of Apple Photos application
            export_current = tuple(photo for photo in folder['photos'] if photo['adjusted'])
            self._export_media(export_current, export_originals=failed_direct_access, target_path=target_path)

    def _run_applescript(self, apple_script):
        proc = subprocess.Popen(['osascript', '-'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        proc.communicate(apple_script)

    def _run_export_applescript(self, uuid_list, options=''):
        # Note: The long timeout is needed, otherwise the script sometimes fails with following error:
        #           Photos got an error: AppleEvent timed out. (-1712)
        apple_script = b'''
            on run
                set thepath to "%s" as POSIX file as text
                with timeout of 6000 seconds
                    tell application "Photos"
                        set thelist to {%s}
                        export thelist to (thepath as alias) %s
                    end tell
                end timeout
            end run
            ''' % (self._temp_directory.encode('utf-8'), b", ".join(b'media item id "%s"' % uuid.encode('utf-8') for uuid in uuid_list), options.encode('utf-8'))

        # Run export AppleScript
        self._run_applescript(apple_script)

    def _run_update_exif(self, data_list):
        if not self._update_exif:
            return

        for data in data_list:
            filename = data['filename']
            if re_movies.match(filename):
                continue

            flags = []

            latitude = data['latitude']
            longitude = data['longitude']
            keywords = data['keywords']

            if latitude is not None and longitude is not None:
                lat_ref = 'N' if latitude > 0 else 'S'
                long_ref = 'E' if longitude > 0 else 'W'

                flags += [
                    '-EXIF:GPSLatitude=%f' % abs(latitude),
                    '-EXIF:GPSLatitudeRef=%s' % lat_ref,
                    '-EXIF:GPSLongitude=%f' % abs(longitude),
                    '-EXIF:GPSLongitudeRef=%s' % long_ref
                ]

            if keywords:
                flags += ["-Subject=%s" % keyword for keyword in keywords]

            if flags:
                flags += ['-overwrite_original_in_place', '-P', filename]
                try:
                    log.debug("Setting EXIF data %s", ' '.join(flag for flag in flags))
                    r = exif_tool.execute(*flags)
                    if ('1 image files updated' not in r) and ('1 image files unchanged' not in r):
                        raise ValueError(r)
                except json.decoder.JSONDecodeError:
                    pass
                except ValueError as e:
                    log.error("EXIF setting has failed - %s - for %s." % (e, filename,))

    def _move_temp_files(self, target_path):
        # Move fresh Photos's export to the target directory
        files = os.listdir(self._temp_directory)
        for f in files:
            source_filename = os.path.join(self._temp_directory, f)
            log.debug("Moving scripted export %s to %s", source_filename, target_path)
            shutil.move(source_filename, target_path)

    def _validate_filename(self, expected_filename):
        if os.path.isfile(expected_filename):
            return expected_filename

        # A new Apple Photos exports .jpeg if the original photo has .jpg extension. Try this one if original filename wasn't found.
        return re_jpeg.sub('.jpeg', expected_filename)

    def _export_media(self, export_current, target_path, export_originals=None):
        # Export the last version of photos
        if export_current:
            self._run_export_applescript((photo['uuid'] for photo in export_current))
            self._run_update_exif([{
                    'latitude': photo['latitude'],
                    'longitude': photo['longitude'],
                    'keywords': photo['keywords'],
                    'filename': self._validate_filename(os.path.join(self._temp_directory, photo['originalfilename']))
                } for photo in export_current if photo['has_exif_data']])
            self._move_temp_files(target_path)

        # If needed, export also missing originals
        if export_originals:
            # Export modified originals to the sub-directory
            photo_list = [photo for photo in export_originals if photo['adjusted']]
            if photo_list:
                self._run_export_applescript((photo['uuid'] for photo in photo_list), 'with using originals')
                self._run_update_exif([{
                        'latitude': photo['latitude'],
                        'longitude': photo['longitude'],
                        'keywords': photo['keywords'],
                        'filename': self._validate_filename(os.path.join(self._temp_directory, photo['originalfilename']))
                    } for photo in photo_list if photo['has_exif_data']])
                self._move_temp_files(os.path.join(target_path, self._originals_subdir_name))
            # Export unmodified originals directly to the target directory
            photo_list = [photo for photo in export_originals if not photo['adjusted']]
            if photo_list:
                self._run_export_applescript((photo['uuid'] for photo in photo_list), 'with using originals')
                self._run_update_exif([{
                        'latitude': photo['latitude'],
                        'longitude': photo['longitude'],
                        'keywords': photo['keywords'],
                        'filename': self._validate_filename(os.path.join(self._temp_directory, photo['originalfilename']))
                    } for photo in photo_list if photo['has_exif_data']])
                self._move_temp_files(target_path)

    def export_photos(self, album_tree, target_path):
        """Exports album tree to the specific target directory."""
        log.info("Exporting album tree...")
        for folder in album_tree:
            self._export_internal(target_path, folder)
