import os
import sys
import re
import json
import ctypes
import threading
import subprocess
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

try:
    from google.oauth2 import service_account
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
except ImportError:
    service_account = None
    Credentials = None
    InstalledAppFlow = None
    Request = None
    build = None

###########################################################################################

# Generates a txt file for detected file formats that did not have a defined icon preset
LOG_UNDEFINED_FORMATS = False

# Use default icon preset for undefined file types
USE_DEFAULT_PRESET = True

# Define preset icons for different file types
ICON_PRESETS = {
    'default': ['accurip', 'ass', 'bin', 'cfg', 'cue', 'm3u', 'iso', 'mds', 'xspf', 'ani', 'cur', 'eot', 'inf', 'moc', 'sample', 'scr', 'skel', 'ttf', 'woff', 'woff2'],
    'video': ['avi', 'f4v', 'flv', 'm4v', 'mkv', 'mov', 'mp4', 'mpg', 'rmvb', 'ts', 'vob', 'webm', 'wmv', 'm2ts'],
    'image': ['bmp', 'gif', 'jfif', 'jpeg', 'jpg', 'png', 'ico', 'webp', 'svg'],
    'text': ['log', 'nfo', 'txt', 'csv'],
    'text-html': ['html', 'mhtml', 'css', 'json', 'py'],
    'application-pdf': ['pdf'],
    'application-javascript': ['js'],
    'application-x-7z-compressed': ['7z', 'zip', 'rar'],
    'application-x-shockwave-flash': ['swf'],
    'bat': ['bat'],
    'docx': ['docx'],
    'xlsx': ['xlsx'],
    'db': ['db'],
    'exe': ['exe'],
    'ini': ['ini'],

    'lossy': ['m4a', 'mp3', 'opus', 'wma'],
    'lossless': ['flac'],
    'lossless-alt': ['wav', 'ape', 'ogg', 'wv'],
}

EXTENSION_TO_PRESET = {
    ext.lower(): f'icon-{preset.lower()}'
    for preset, extensions in ICON_PRESETS.items()
    for ext in extensions
}

# Keep as false to keep file size low
JSON_OUTPUT = {
    'keep_raw_date': False,
    'keep_raw_size': False
}

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

###########################################################################################

missing_icons = set()

def log_missing_icon(extension):
    """Add a file extension to the set of missing icons."""
    if extension:
        missing_icons.add(extension)

def write_missing_icons_log():
    """Write all missing icon extensions to a text file."""
    if not missing_icons:
        return
    with open('missing_icons.txt', 'w', encoding='utf-8') as f:
        for ext in sorted(missing_icons):
            f.write(f"{ext}\n")

def get_icon_preset(extension):
    """Determine the icon preset for a given file extension via fast dictionary lookup."""
    if not extension:
        return 'icon-default' if USE_DEFAULT_PRESET else ''
    preset = EXTENSION_TO_PRESET.get(extension.lower())
    if preset:
        return preset
    if LOG_UNDEFINED_FORMATS:
        log_missing_icon(extension)
    return 'icon-default' if USE_DEFAULT_PRESET else ''

def format_size(size):
    """Convert size in bytes to human readable format with 2 decimal points."""
    if not size:
        return "N/A"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"

def format_date(timestamp):
    """Convert Unix timestamp to readable date format."""
    if not isinstance(timestamp, (int, float)):
        return "N/A"
    return datetime.fromtimestamp(timestamp).strftime('%d/%m/%Y %I:%M %p')

def get_volume_label(drive_path):
    """Retrieve volume label for a drive using Windows kernel32."""
    volume_name_buffer = ctypes.create_unicode_buffer(1024)
    path = drive_path + "\\" if not drive_path.endswith("\\") else drive_path
    success = ctypes.windll.kernel32.GetVolumeInformationW(
        ctypes.c_wchar_p(path),
        volume_name_buffer,
        ctypes.sizeof(volume_name_buffer),
        None, None, None, None, 0
    )
    return volume_name_buffer.value if success else ""

def scan_tree(root_path, excluded_files, progress_bar=None):
    """Single-pass recursive directory scan collecting cached stats and cumulative sizes."""
    total_files = 0
    total_folders = 0

    def _scan(current_path, rel_path, is_root=False):
        nonlocal total_files, total_folders
        if progress_bar is not None:
            progress_bar.update(1)

        subdirs = []
        files = []
        direct_size = 0

        try:
            entries = list(os.scandir(current_path))
        except OSError:
            entries = []

        for entry in entries:
            name = entry.name
            if is_root and name in excluded_files:
                continue
            try:
                if entry.is_dir():
                    try:
                        mtime = entry.stat().st_mtime
                    except OSError:
                        mtime = 0
                    subdirs.append((name, mtime))
                elif entry.is_file():
                    try:
                        stat = entry.stat()
                        size = stat.st_size
                        mtime = stat.st_mtime
                    except OSError:
                        size = 0
                        mtime = 0
                    direct_size += size
                    files.append((name, size, mtime))
                    total_files += 1
            except OSError:
                continue

        subdirs.sort(key=lambda x: x[0])
        files.sort(key=lambda x: x[0])

        node = {
            'relpath': rel_path,
            'subdirs': subdirs,
            'files': files,
            'direct_size': direct_size,
            'total_size': direct_size,
            'children': {}
        }

        for subdir_name, _ in subdirs:
            total_folders += 1
            child_rel = subdir_name if rel_path == '.' else os.path.join(rel_path, subdir_name)
            child_path = os.path.join(current_path, subdir_name)
            child_node = _scan(child_path, child_rel, is_root=False)
            node['children'][subdir_name] = child_node
            node['total_size'] += child_node['total_size']

        return node

    root_node = _scan(root_path, '.', is_root=True)
    return root_node, total_files, total_folders

def assemble_directory_data(root_node, version):
    """Assemble JSON data structure from in-memory tree with top-down ID generation."""
    keep_raw_date = JSON_OUTPUT['keep_raw_date']
    keep_raw_size = JSON_OUTPUT['keep_raw_size']

    subdirs_data = {
        "version": version,
        "directories": {}
    }
    if root_node.get('gdrive_id'):
        subdirs_data["gdrive_id"] = root_node["gdrive_id"]

    def _assemble(node, parent_id="", depth=0, is_root=True):
        rel_path = node['relpath']
        letter = chr(ord('a') + depth)
        items = []

        parent_entry = {
            "type": "directory",
            "name": "..",
            "date_formatted": "",
            "size_formatted": "",
            "path": ".."
        }
        if is_root or keep_raw_date:
            parent_entry["date"] = ""
        if is_root or keep_raw_size:
            parent_entry["size"] = ""
        items.append(parent_entry)

        for idx, subdir_info in enumerate(node['subdirs']):
            subdir_name = subdir_info[0]
            mtime = subdir_info[1]
            gdrive_id = subdir_info[2] if len(subdir_info) > 2 else None

            child_node = node['children'][subdir_name]
            child_id = f"{parent_id}{letter}{idx + 1}"
            child_rel = child_node['relpath']
            child_size = child_node['total_size']

            dir_entry = {
                "type": "directory",
                "name": subdir_name,
                "date_formatted": format_date(mtime) if mtime else "N/A",
                "size_formatted": format_size(child_size),
                "path": child_rel,
                "directory_id": child_id
            }
            if gdrive_id:
                dir_entry["gdrive_id"] = gdrive_id
            if is_root or keep_raw_date:
                dir_entry["date"] = mtime if mtime else "N/A"
            if is_root or keep_raw_size:
                dir_entry["size"] = child_size

            items.append(dir_entry)

        for file_counter, file_info in enumerate(node['files'], start=1):
            fname = file_info[0]
            fsize = file_info[1]
            fmtime = file_info[2]
            gdrive_id = file_info[3] if len(file_info) > 3 else None

            ext = fname.split('.')[-1] if '.' in fname else ''
            icon_preset = get_icon_preset(ext)
            icon_classes = f"icon icon-{ext}"
            if icon_preset:
                icon_classes += f" {icon_preset}"

            file_entry = {
                "type": "file",
                "name": fname,
                "date_formatted": format_date(fmtime) if fmtime else "N/A",
                "size_formatted": format_size(fsize) if fsize else "N/A",
                "icon_classes": icon_classes,
                "item_id": file_counter
            }
            if gdrive_id:
                file_entry["gdrive_id"] = gdrive_id
            if is_root or keep_raw_date:
                file_entry["date"] = fmtime if fmtime else "N/A"
            if is_root or keep_raw_size:
                file_entry["size"] = fsize if fsize else "N/A"

            items.append(file_entry)

        subdirs_data["directories"][rel_path] = items

        for idx, subdir_info in enumerate(node['subdirs']):
            subdir_name = subdir_info[0]
            child_node = node['children'][subdir_name]
            child_id = f"{parent_id}{letter}{idx + 1}"
            _assemble(child_node, parent_id=child_id, depth=depth + 1, is_root=False)

    _assemble(root_node, parent_id="", depth=0, is_root=True)
    return subdirs_data

def get_credentials_dir():
    """Locate the .credentials directory next to the script or in the working directory."""
    script_dir_creds = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.credentials')
    if os.path.isdir(script_dir_creds):
        return script_dir_creds
    cwd_creds = os.path.join(os.getcwd(), '.credentials')
    if os.path.isdir(cwd_creds):
        return cwd_creds
    return script_dir_creds

def find_credentials(credentials_dir):
    """Scan credentials directory for service account or OAuth client secrets."""
    if not os.path.isdir(credentials_dir):
        return []

    found = []
    rejected_web = []
    try:
        entries = sorted(os.scandir(credentials_dir), key=lambda e: e.name)
    except OSError:
        return []

    for entry in entries:
        if not entry.is_file() or not entry.name.endswith('.json'):
            continue
        if entry.name == 'token.json' or entry.name.startswith('token_'):
            continue
        try:
            with open(entry.path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                continue
            if data.get('type') == 'service_account':
                found.append({
                    'type': 'service_account',
                    'path': entry.path,
                    'name': entry.name,
                    'client_email': data.get('client_email', '')
                })
            elif 'installed' in data:
                found.append({
                    'type': 'desktop_oauth',
                    'path': entry.path,
                    'name': entry.name
                })
            elif 'web' in data:
                rejected_web.append(entry.name)
        except Exception:
            continue

    if rejected_web:
        print("\nNotice: Unsupported 'Web application' credential(s) detected:")
        for w_name in rejected_web:
            print(f"  - {w_name}")
        print("Google Drive scanning requires a 'Desktop app' credential.")
        print("In Google Cloud Console: APIs & Services > Credentials > Create Credentials > OAuth client ID > Application type: Desktop app.\n")

    return found

def copy_to_clipboard(text):
    """Copy text string to Windows clipboard using native clip utility."""
    try:
        subprocess.run(['clip'], input=text.encode('utf-8'), check=True)
        return True
    except Exception:
        return False

class AuthPrompt(str):
    """Prompt string that copies the authorization URL to the clipboard when formatted."""
    def __init__(self, *args, **kwargs):
        super().__init__()
        self._copied_url = None

    def format(self, *args, **kwargs):
        url = kwargs.get('url', '')
        if url and url != self._copied_url:
            self._copied_url = url
            copied = copy_to_clipboard(url)
            notice = "The authorization URL has been copied to your clipboard!\n" if copied else "Could not copy directly to clipboard.\n"
        else:
            notice = ""

        template = (
            "\n" + "=" * 70 + "\n"
            "Desktop OAuth Authorization\n"
            "=" * 70 + "\n"
            f"{notice}\n"
            "Instructions:\n"
            "1. Open your browser and paste the copied URL into the address bar.\n"
            "2. Sign in and grant read-only Drive permissions.\n"
            "3. Return to this terminal once authorized.\n\n"
            "Direct URL:\n{url}\n"
            + "=" * 70 + "\n\n"
            "Waiting for browser authorization..."
        )
        return template.format(url=url)

def authenticate_google_drive(cred_info, credentials_dir):
    """Authenticate and build Google Drive v3 resource."""
    if build is None:
        print("Error: Google API libraries are required for cloud scanning.")
        print("Install them with: pip install -r requirements.txt")
        sys.exit(1)

    cred_type = cred_info['type']
    cred_path = cred_info['path']

    if cred_type == 'service_account':
        creds = service_account.Credentials.from_service_account_file(cred_path, scopes=SCOPES)
        return build('drive', 'v3', credentials=creds), creds

    if cred_type == 'desktop_oauth':
        # Unique token cache per credential file prevents collision between multiple desktop accounts
        base_name = os.path.splitext(cred_info['name'])[0]
        token_filename = f"token_{base_name}.json"
        token_path = os.path.join(credentials_dir, token_filename)
        legacy_token = os.path.join(credentials_dir, 'token.json')

        creds = None
        if os.path.exists(token_path):
            try:
                creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            except Exception:
                creds = None
        elif os.path.exists(legacy_token):
            try:
                creds = Credentials.from_authorized_user_file(legacy_token, SCOPES)
            except Exception:
                creds = None

        if creds and creds.valid and not os.path.exists(token_path):
            try:
                with open(token_path, 'w', encoding='utf-8') as token_file:
                    token_file.write(creds.to_json())
            except OSError:
                pass

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    print(f"Notice: Cached token could not be refreshed ({e}). Re-authenticating...")
                    creds = None

            if not creds or not creds.valid:
                flow = InstalledAppFlow.from_client_secrets_file(cred_path, SCOPES)
                creds = flow.run_local_server(
                    port=0,
                    open_browser=False,
                    authorization_prompt_message=AuthPrompt(),
                    success_message="Authentication complete! You may close this tab."
                )

            try:
                with open(token_path, 'w', encoding='utf-8') as token_file:
                    token_file.write(creds.to_json())
            except OSError as e:
                print(f"Notice: Could not cache token to '{token_path}': {e}")

        return build('drive', 'v3', credentials=creds), creds

    raise ValueError(f"Unknown credential type: {cred_type}")

def parse_folder_id(input_str):
    """Extract Google Drive folder ID from a URL or raw ID string."""
    cleaned = input_str.strip()
    match = re.search(r'folders/([a-zA-Z0-9_-]+)', cleaned)
    if match:
        return match.group(1)
    match_query = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', cleaned)
    if match_query:
        return match_query.group(1)
    return cleaned

def verify_folder(service, folder_id):
    """Verify that the folder exists and is accessible. Returns folder dict or None."""
    try:
        folder = service.files().get(
            fileId=folder_id,
            fields='id, name, mimeType',
            supportsAllDrives=True
        ).execute()
        if folder.get('mimeType') != 'application/vnd.google-apps.folder':
            print(f"Error: '{folder.get('name')}' is a file, not a folder.")
            return None
        return folder
    except Exception as e:
        print(f"Error: Could not access folder '{folder_id}': {e}")
        return None

def select_folder_service_account(service):
    """Find folders shared with the service account and prompt for target folder."""
    print("Searching for folders shared with the service account...")
    try:
        results = service.files().list(
            q="mimeType = 'application/vnd.google-apps.folder' and sharedWithMe = true and trashed = false",
            fields="files(id, name)",
            pageSize=50,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        shared_folders = results.get('files', [])
    except Exception as e:
        print(f"Could not list shared folders: {e}")
        shared_folders = []

    if len(shared_folders) == 1:
        single = shared_folders[0]
        prompt = f"Found 1 shared folder: '{single['name']}'\nPress Enter to use it, or paste a folder URL/ID within the shared folder: "
        user_input = input(prompt).strip()
        if not user_input:
            return single['id'], single['name']
        folder_id = parse_folder_id(user_input)
        folder = verify_folder(service, folder_id)
        if folder:
            return folder['id'], folder['name']

    elif len(shared_folders) > 1:
        print("\nAvailable shared folders:")
        for idx, fld in enumerate(shared_folders, start=1):
            print(f"  [{idx}] {fld['name']}")
        while True:
            user_input = input("\nEnter folder number, or paste a folder URL/ID within the shared folders: ").strip()
            if not user_input:
                continue
            if user_input.isdigit():
                choice = int(user_input)
                if 1 <= choice <= len(shared_folders):
                    selected = shared_folders[choice - 1]
                    return selected['id'], selected['name']
                print(f"Please enter a number between 1 and {len(shared_folders)}.")
                continue
            folder_id = parse_folder_id(user_input)
            folder = verify_folder(service, folder_id)
            if folder:
                return folder['id'], folder['name']

    while True:
        user_input = input("Enter Google Drive folder URL or ID: ").strip()
        if not user_input:
            continue
        folder_id = parse_folder_id(user_input)
        folder = verify_folder(service, folder_id)
        if folder:
            return folder['id'], folder['name']

def select_folder_desktop_oauth(service):
    """Prompt for folder URL or ID directly to avoid accidental personal drive scanning."""
    while True:
        user_input = input("Enter Google Drive folder URL or ID: ").strip()
        if not user_input:
            continue
        folder_id = parse_folder_id(user_input)
        folder = verify_folder(service, folder_id)
        if folder:
            return folder['id'], folder['name']

def select_target_folder(service, cred_type):
    """Prompt user to choose or input target folder based on credential type."""
    if cred_type == 'service_account':
        return select_folder_service_account(service)
    return select_folder_desktop_oauth(service)

def parse_gdrive_timestamp(iso_str):
    """Convert Google Drive ISO 8601 timestamp string to Unix timestamp."""
    if not iso_str:
        return 0
    try:
        clean_str = iso_str.replace('Z', '+00:00')
        return datetime.fromisoformat(clean_str).timestamp()
    except Exception:
        return 0

def parse_drive_items(items):
    """Parse Google Drive API items into sorted subdirectories and files with duplicate name handling."""
    seen_dirs = {}
    seen_files = {}
    raw_subdirs = []
    files = []
    direct_size = 0

    for item in items:
        name = item.get('name', 'Untitled')
        mime = item.get('mimeType', '')
        mtime = parse_gdrive_timestamp(item.get('modifiedTime'))
        item_id = item.get('id', '')

        if mime == 'application/vnd.google-apps.folder':
            count = seen_dirs.get(name, 0)
            seen_dirs[name] = count + 1
            unique_name = name if count == 0 else f"{name} ({count + 1})"
            raw_subdirs.append((unique_name, mtime, item_id))
        else:
            size_str = item.get('size')
            size = int(size_str) if size_str and str(size_str).isdigit() else 0
            direct_size += size

            count = seen_files.get(name, 0)
            seen_files[name] = count + 1
            unique_name = name if count == 0 else f"{name} ({count + 1})"
            files.append((unique_name, size, mtime, item_id))

    raw_subdirs.sort(key=lambda x: x[0])
    files.sort(key=lambda x: x[0])
    return raw_subdirs, files, direct_size

def scan_gdrive_tree(creds, root_folder_id, progress_bar=None, max_workers=8):
    """Scan Google Drive starting from root_folder_id using concurrent threads for subfolders."""
    _thread_local = threading.local()

    def get_service():
        if not hasattr(_thread_local, 'service'):
            _thread_local.service = build('drive', 'v3', credentials=creds, cache_discovery=False)
        return _thread_local.service

    def _list_folder_items(folder_id):
        service = get_service()
        items = []
        page_token = None
        query = f"'{folder_id}' in parents and trashed = false"
        while True:
            response = service.files().list(
                q=query,
                pageSize=1000,
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageToken=page_token
            ).execute()
            items.extend(response.get('files', []))
            page_token = response.get('nextPageToken')
            if not page_token:
                break
        return items

    def _fetch_folder(folder_id, rel_path):
        if progress_bar is not None:
            progress_bar.update(1)

        try:
            items = _list_folder_items(folder_id)
        except Exception as e:
            print(f"\nWarning: Failed to list items for folder '{rel_path}': {e}")
            items = []

        raw_subdirs, files, direct_size = parse_drive_items(items)

        subdirs = [(name, mtime, gid) for name, mtime, gid in raw_subdirs]
        node = {
            'relpath': rel_path,
            'subdirs': subdirs,
            'files': files,
            'direct_size': direct_size,
            'total_size': direct_size,
            'children': {},
            'gdrive_id': folder_id
        }
        return node, raw_subdirs

    visited_folder_ids = {root_folder_id}
    root_node, root_raw_subdirs = _fetch_folder(root_folder_id, '.')

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        pending_futures = {}

        for subdir_name, _, child_id in root_raw_subdirs:
            if child_id in visited_folder_ids:
                empty_node = {
                    'relpath': subdir_name,
                    'subdirs': [],
                    'files': [],
                    'direct_size': 0,
                    'total_size': 0,
                    'children': {},
                    'gdrive_id': child_id
                }
                root_node['children'][subdir_name] = empty_node
                continue
            visited_folder_ids.add(child_id)
            fut = executor.submit(_fetch_folder, child_id, subdir_name)
            pending_futures[fut] = (root_node, subdir_name)

        while pending_futures:
            done, _ = wait(pending_futures.keys(), return_when=FIRST_COMPLETED)
            for fut in done:
                parent_node, subdir_name = pending_futures.pop(fut)
                child_node, child_raw_subdirs = fut.result()
                parent_node['children'][subdir_name] = child_node

                for sub_name, _, sub_id in child_raw_subdirs:
                    sub_rel = os.path.join(child_node['relpath'], sub_name)
                    if sub_id in visited_folder_ids:
                        empty_node = {
                            'relpath': sub_rel,
                            'subdirs': [],
                            'files': [],
                            'direct_size': 0,
                            'total_size': 0,
                            'children': {},
                            'gdrive_id': sub_id
                        }
                        child_node['children'][sub_name] = empty_node
                        continue
                    visited_folder_ids.add(sub_id)
                    new_fut = executor.submit(_fetch_folder, sub_id, sub_rel)
                    pending_futures[new_fut] = (child_node, sub_name)

    total_files = 0
    total_folders = 0

    def _accumulate_totals(node, is_root=True):
        nonlocal total_files, total_folders
        if not is_root:
            total_folders += 1
        total_files += len(node['files'])

        for child in node['children'].values():
            node['total_size'] += _accumulate_totals(child, is_root=False)
        return node['total_size']

    _accumulate_totals(root_node, is_root=True)
    return root_node, total_files, total_folders

def write_output(root_node, header_title, total_files, total_folders):
    """Generate snap.html snippet with embedded DOM JSON cache from assembled tree."""
    total_size = root_node['total_size']
    print(f"Processed {total_files} files in {total_folders} folders ({format_size(total_size)}).")

    date_ran = datetime.now().strftime('%d/%m/%Y %I:%M %p')
    version = datetime.now().strftime('%y%m%d.%H%M')

    subdirs_data = assemble_directory_data(root_node, version)
    root_content = subdirs_data["directories"]["."]

    html_content = [f'''      <div class="header">
        <h1>
          {header_title}
        </h1>
        <span>{total_files} files in {total_folders} folders ({format_size(total_size)})</span>
        <span class="info">Generated with <a href="https://github.com/4163/snap" target="_blank">snap</a> at {date_ran}</span>
        <span class="info">Search patterns:</span>
        <div class="info">
          <span>Everything: [ >* item-name ]</span>
          <span>Folders only: [ >*folder item-name ]</span>
          <span>Files only: [ >*file item-name ]</span>
        </div>
      </div>
''']

    html_content.append('      <ul id="files" class="view-tiles" data-path="root">')
    for item in root_content:
        if item["type"] == "directory":
            if item["name"] == "..":
                continue
            html_content.append(
                f'        <li><a href="{item["path"]}" class="icon icon-directory" title="{item["name"]}">'
                f'<span class="name">{item["name"]}</span>'
                f'<span class="date">{item["date_formatted"]}</span>'
                f'<span class="size">{item["size_formatted"]}</span></a></li>'
            )
        else:
            html_content.append(
                f'        <li><a href="/" class="{item["icon_classes"]}" title="{item["name"]}">'
                f'<span class="name">{item["name"]}</span>'
                f'<span class="date">{item["date_formatted"]}</span>'
                f'<span class="size">{item["size_formatted"]}</span></a></li>'
            )
    html_content.append('      </ul>')
    html_content.append('')

    minified_json = json.dumps(subdirs_data, separators=(',', ':'))
    html_content.append(f'      <script id="dom-cache" type="application/json">{minified_json}</script>')
    html_content.append('')

    print("Writing HTML file...")
    with open('snap.html', 'w', encoding='utf-8') as f:
        f.write('\n'.join(html_content))

    if LOG_UNDEFINED_FORMATS:
        write_missing_icons_log()

    print("Processing complete!")
    print("\nDone!\nPress 'Enter' to exit.")
    input()

def run_local_scan():
    """Execute local filesystem scan and generate outputs."""
    excluded_files = {'snap.py', 'snap.html', 'directories.json'}

    print("Scanning directories...")
    pbar = tqdm(desc="Scanning directories", unit=" dir") if tqdm is not None else None
    root_node, total_files, total_folders = scan_tree('.', excluded_files, progress_bar=pbar)
    if pbar is not None:
        pbar.close()

    script_path = os.path.abspath(__file__)
    drive_letter, _ = os.path.splitdrive(script_path)
    folder_name = os.path.basename(os.path.dirname(script_path))
    drive_label = get_volume_label(drive_letter + "\\")
    drive_name = drive_letter.rstrip(":\\")
    header_title = f"{drive_label} {drive_name}:/{folder_name}".strip()

    write_output(root_node, header_title, total_files, total_folders)

def run_cloud_scan(selected_cred, credentials_dir):
    """Execute Google Drive scan and generate outputs."""
    service, creds = authenticate_google_drive(selected_cred, credentials_dir)
    folder_id, folder_name = select_target_folder(service, selected_cred['type'])

    print(f"\nScanning Google Drive folders for '{folder_name}'...")
    pbar = tqdm(desc="Scanning folders", unit=" dir") if tqdm is not None else None
    root_node, total_files, total_folders = scan_gdrive_tree(creds, folder_id, progress_bar=pbar)
    if pbar is not None:
        pbar.close()

    header_title = f"Google Drive: {folder_name}"
    write_output(root_node, header_title, total_files, total_folders)

def truncate_middle(text, max_len=32):
    """Truncate middle of string if exceeding max_len."""
    if len(text) <= max_len:
        return text
    half = (max_len - 3) // 2
    return text[:half] + "..." + text[-(max_len - 3 - half):]

def format_cred_entry(cred):
    """Format credential label placing the type first and truncating long names."""
    if cred['type'] == 'service_account':
        email = cred.get('client_email', '')
        short_email = email.replace('.iam.gserviceaccount.com', '') if email else ''
        fname = truncate_middle(cred['name'], 24)
        detail = f"{short_email} ({fname})" if short_email else fname
        return f"[Service Account] {detail}"
    fname = truncate_middle(cred['name'], 36)
    return f"[Desktop OAuth]   {fname}"

def main():
    """Main entry point. Dispatches to Google Drive or local scan."""
    credentials_dir = get_credentials_dir()
    creds = find_credentials(credentials_dir)

    if not creds:
        run_local_scan()
        return

    print("Credentials detected in .credentials:")
    for idx, cred in enumerate(creds, start=1):
        print(f"  [{idx}] {format_cred_entry(cred)}")

    local_option_num = len(creds) + 1
    print(f"  [{local_option_num}] [Local Directory] Current directory (.)")

    while True:
        choice = input(f"\nSelect scan source [1]: ").strip()
        if not choice or choice == "1":
            run_cloud_scan(creds[0], credentials_dir)
            return
        if choice == str(local_option_num):
            run_local_scan()
            return
        if choice.isdigit():
            c = int(choice)
            if 1 <= c <= len(creds):
                run_cloud_scan(creds[c - 1], credentials_dir)
                return
        print(f"Please enter a valid option (1-{local_option_num}).")

def generate_html():
    """Entry point preserving existing signature."""
    main()

if __name__ == '__main__':
    main()
