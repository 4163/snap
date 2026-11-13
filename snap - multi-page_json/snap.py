import os
import sys
import json
import ctypes
from datetime import datetime

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

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

        for idx, (subdir_name, mtime) in enumerate(node['subdirs']):
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
            if is_root or keep_raw_date:
                dir_entry["date"] = mtime if mtime else "N/A"
            if is_root or keep_raw_size:
                dir_entry["size"] = child_size

            items.append(dir_entry)

        for file_counter, (fname, fsize, fmtime) in enumerate(node['files'], start=1):
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
            if is_root or keep_raw_date:
                file_entry["date"] = fmtime if fmtime else "N/A"
            if is_root or keep_raw_size:
                file_entry["size"] = fsize if fsize else "N/A"

            items.append(file_entry)

        subdirs_data["directories"][rel_path] = items

        for idx, (subdir_name, _) in enumerate(node['subdirs']):
            child_node = node['children'][subdir_name]
            child_id = f"{parent_id}{letter}{idx + 1}"
            _assemble(child_node, parent_id=child_id, depth=depth + 1, is_root=False)

    _assemble(root_node, parent_id="", depth=0, is_root=True)
    return subdirs_data

def get_valid_yes_no(prompt):
    """Get a valid yes/no response from the user."""
    while True:
        response = input(prompt).strip().lower()
        if response in ['y', 'n']:
            return response == 'y'
        print("Invalid input. Please enter 'y' or 'n'.")

def generate_html():
    """Scan directories, generate snap.html snippet, and serialize directories.json."""
    excluded_files = {'snap.py', 'snap.html', 'directories.json'}

    print("Scanning directories...")
    pbar = tqdm(desc="Scanning directories", unit=" dir") if tqdm is not None else None
    root_node, total_files, total_folders = scan_tree('.', excluded_files, progress_bar=pbar)
    if pbar is not None:
        pbar.close()

    total_size = root_node['total_size']
    print(f"Processed {total_files} files in {total_folders} folders ({format_size(total_size)}).")

    script_path = os.path.abspath(__file__)
    drive_letter, _ = os.path.splitdrive(script_path)
    folder_name = os.path.basename(os.path.dirname(script_path))
    drive_label = get_volume_label(drive_letter + "\\")
    drive_name = drive_letter.rstrip(":\\")

    date_ran = datetime.now().strftime('%d/%m/%Y %I:%M %p')
    version = datetime.now().strftime('%y%m%d.%H%M')

    subdirs_data = assemble_directory_data(root_node, version)
    root_content = subdirs_data["directories"]["."]

    html_content = [f'''    <meta name="jsonVersion" content="{version}">

      <div class="header">
        <h1>
          {drive_label} {drive_name}:/{folder_name}
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

    print("Writing HTML file...")
    with open('snap.html', 'w', encoding='utf-8') as f:
        f.write('\n'.join(html_content))

    print("\nOutput preferences:")
    should_minify = get_valid_yes_no("Would you like to minify the JSON output? (y/n): ")

    print("Writing JSON file...")
    with open('directories.json', 'w', encoding='utf-8') as f:
        if should_minify:
            json.dump(subdirs_data, f, separators=(',', ':'))
        else:
            json.dump(subdirs_data, f, indent=2)

    print(f"\n- JSON format: {'minified' if should_minify else 'pretty printed'}")
    print("\nProcessing complete!")

    if LOG_UNDEFINED_FORMATS:
        write_missing_icons_log()

    print("\nDone!\nPress 'Enter' to exit.")
    input()

if __name__ == '__main__':
    generate_html()
