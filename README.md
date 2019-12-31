# photos-export
Export photos from Apple Photos photo library.

This Python script is exporting photos from Apple Photos application and placing copies in a directory structure according to the album folders you have created inside the Photos.

- It exports originals and the current version of the pictures.

- Contains Samba auto-mount/unmount feature which enables to export pictures directly to Samba share.

- Includes OS anti-sleep protection using **caffeinate** call.

## Requirements

Requires Python 3.7 (or newer).

## Notes

- Uses **~/.photos_export_mountpoint/** directory as a mount point if the Samba URL is used.
