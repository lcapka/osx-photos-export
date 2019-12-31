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

import subprocess, logging, os, shutil
from ape_errors import *

log = logging.getLogger("ape_exporter")

class ApeExporter:
    """Implements photo handling methods using AppleScript and direct file access."""

    def __init__(self, photos_library_path, temp_directory, originals_subdir_name='Originals'):
        self._photos_library_path = photos_library_path
        self._temp_directory = temp_directory
        self._originals_subdir_name = originals_subdir_name

        if os.listdir(temp_directory):
            raise GenericExportError("The temporary directory must be empty (%s)." % temp_directory)

        if not originals_subdir_name:
            raise GenericExportError("The originals sub-directory must be set.")

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
                    failed_direct_access.append((photo['uuid'], photo['adjusted'],))
                    continue

                source_filename = os.path.join(self._photos_library_path, 'originals', photo['directory'], photo['filename'])
                # Store originals for adjusted/modified photos in the Originals sub-directory.
                if photo['adjusted']:
                    target_filename = os.path.join(target_path, self._originals_subdir_name, photo['originalfilename'])
                else:
                    target_filename = os.path.join(target_path, photo['originalfilename'])

                try:
                    shutil.copyfile(source_filename, target_filename)
                except FileNotFoundError:
                    log.error("Export has failed for %s", photo)
                    failed_direct_access.append((photo['uuid'], photo['adjusted'],))

            # Export missing originals and adjusted photos using AppleScript call of Apple Photos application
            uuid_list = tuple(photo['uuid'] for photo in folder['photos'] if photo['adjusted'])
            self._export_media(uuid_list, uuid_list_originals=failed_direct_access, target_path=target_path)

    def _run_applescript(self, apple_script):
        proc = subprocess.Popen(['osascript', '-'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        proc.communicate(apple_script)

    def _run_export_applescript(self, uuid_list, options):
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

    def _move_temp_files(self, target_path):
        # Move fresh Photos's export to the target directory
        files = os.listdir(self._temp_directory)
        for f in files:
            shutil.move(os.path.join(self._temp_directory, f), target_path)

    def _export_media(self, uuid_list, target_path, uuid_list_originals=None):
        # Export the last version of photos
        if uuid_list:
            self._run_export_applescript(uuid_list, 'with GPS without using originals')
            self._move_temp_files(target_path)

        # If needed, export also missing originals
        if uuid_list_originals:
            # Export modified originals to the sub-directory
            lst = [uuid[0] for uuid in uuid_list_originals if uuid[1]]
            if lst:
                self._run_export_applescript(lst, 'with using originals')
                self._move_temp_files(os.path.join(target_path, self._originals_subdir_name))
            # Export unmodified originals directly to the target directory
            lst = [uuid[0] for uuid in uuid_list_originals if not uuid[1]]
            if lst:
                self._run_export_applescript(lst, 'with using originals')
                self._move_temp_files(target_path)

    def export_photos(self, album_tree, target_path):
        """Exports album tree to the specific target directory."""
        for folder in album_tree:
            self._export_internal(target_path, folder)
