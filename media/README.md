# Media

Relaxation scenes and audio go here (royalty-free, credited).

- Images: `media/scenes/<scene-id>.jpg|webp`. Audio: `media/audio/<scene-id>-nature.mp3`, `media/audio/music-<name>.mp3`.
- Scene ids are listed in `data/simulated/relax_scenes.json`. The server finds files by these names (`server/features/relax/router.py`); images may be .webp/.jpg/.png, audio .mp3/.ogg/.m4a/.wav.
- The current files are generated locally by `scripts/make_relax_media.py` (see `CREDITS.md`).
- Add every file's author, licence and source to `media/CREDITS.md`.
- Everything is bundled or served locally: never link to remote media.
- Keep files small (images < 500 KB, audio < 5 MB) so the repo stays clonable.
