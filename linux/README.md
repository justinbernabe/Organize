# File Organizer — Linux Web App

Web-based file organizer that runs on a Linux server. Accessible from any browser at `http://server:8080`. Sorts files into category folders, fixes timestamps from filenames, and supports scheduled recurring runs.

## Quick Start

```bash
# 1. Clone and enter the directory
git clone https://github.com/yourusername/Organize.git
cd Organize/linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
python3 server.py
```

Open `http://localhost:8080` (or `http://your-server-ip:8080` from another machine).

## Usage

1. **Add a folder** — Click "+ Add Folder" on the dashboard, enter the path (e.g. `/mnt/usb/media`)
2. **Organize** — Click "Organize" to run immediately. Progress streams live via WebSocket.
3. **Preview** — Click "Preview" for a dry run showing what would happen without moving anything.
4. **Schedule** — Add a cron expression when adding a folder (e.g. `0 */6 * * *` for every 6 hours).
5. **Settings** — Toggle file moving, timestamp setting, dry run mode, and name scheme.

## What it does

- Normalizes folder names (Pics → images, Vids → videos, etc.)
- Sorts files into `images/`, `videos/`, `audio/`, `text/`, `misc/` by extension
- Extracts dates from filenames (YYYY-MM-DD, YYYYMMDDTHHMMSS, etc.) and sets mtime
- Propagates directory timestamps to match newest child file
- On Linux, mtime is fully writable. btime (creation time) is not writable on ext4 but mtime is what Finder shows over SMB anyway.

## Install as a systemd service (auto-start on boot)

```bash
# 1. Copy files to /opt/file-organizer (or wherever you prefer)
sudo mkdir -p /opt/file-organizer
sudo cp -r . /opt/file-organizer/
sudo pip install -r /opt/file-organizer/requirements.txt

# 2. Edit the service file if needed (change User, paths)
sudo cp systemd/file-organizer.service /etc/systemd/system/

# 3. Enable and start
sudo systemctl daemon-reload
sudo systemctl enable file-organizer
sudo systemctl start file-organizer

# 4. Check status
sudo systemctl status file-organizer
```

The service runs on port 8080 by default. Set the `PORT` environment variable in the service file to change it.

## Configuration

Settings are stored in `~/.config/file-organizer/config.json` (for the user running the service). This includes:

- Watched folders and their schedules
- File categories and extension mappings
- Folder normalization mappings
- Toggle for file moving, timestamp setting, dry run

Run logs are stored in `~/.config/file-organizer/run_log.json`.

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/folders` | List configured folders |
| POST | `/api/folders` | Add a folder `{path, schedule?, enabled?}` |
| DELETE | `/api/folders/{id}` | Remove a folder |
| POST | `/api/organize/{id}` | Trigger organize (async, streams via WebSocket) |
| POST | `/api/preview/{id}` | Dry run, returns planned operations |
| GET | `/api/settings` | Get current settings |
| PUT | `/api/settings` | Update settings `{settings: {...}}` |
| GET | `/api/logs` | Recent run logs |
| WS | `/ws/progress` | WebSocket for live progress events |

## Requirements

- Python 3.9+
- FastAPI, Uvicorn, APScheduler (installed via requirements.txt)
