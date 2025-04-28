import os
import json
import time
import threading
from datetime import datetime

import subprocess
import sys

def ensure_package(import_name, pip_name=None):
    if pip_name is None:
        pip_name = import_name
    try:
        __import__(import_name)
        return False  # No installation needed
    except ImportError:
        confirmation = input(f"{pip_name} not found. Install it? (y/n): ")
        if confirmation.lower() != 'y':
            print(f"Cannot continue without {pip_name}. Exiting. Press 'Enter' to exit.")
            input()
            sys.exit(1)
            
        print(f"Installing {pip_name}...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", pip_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True  # Installation was needed

# Track if anything was installed
installed_anything = False

installed_anything |= ensure_package('tqdm')
installed_anything |= ensure_package('win32api', 'pywin32')

# If we installed anything, ask the user to rerun
if installed_anything:
    input("\nInstallation complete. Please run the script again.\nPress 'Enter' to exit.")
    sys.exit()

# Now safe to import
from tqdm import tqdm
import win32api

# Use default icon preset for undefined file types
USE_DEFAULT_PRESET = True

# Define preset icons for different file types
ICON_PRESETS = {
    'default': ['accurip', 'ass', 'bin', 'cfg', 'cue', 'm3u', 'iso', 'ISO', 'mds', 'MDS', 'xspf'],
    'video': ['avi', 'f4v', 'flv', 'm4v', 'mkv', 'mov', 'mp4', 'MP4', 'mpg', 'rmvb', 'ts', 'vob', 'VOB', 'webm', 'wmv', 'm2ts'],
    'image': ['bmp', 'gif', 'jfif', 'jpeg', 'jpg', 'JPG', 'png', 'ico', 'webp'],
    'text': ['log', 'nfo', 'txt'],
    'text-html': ['html', 'mhtml', 'css'],
    'lossy': ['m4a', 'mp3', 'opus', 'wma', 'Mp3'],
    'lossless': ['flac'],
    'lossless-alt': ['wav', 'ape', 'ogg'],
    'application-pdf': ['pdf'],
    'application-javascript': ['js'],
    'application-x-7z-compressed': ['7z', 'zip', 'rar'],
    'application-x-shockwave-flash': ['swf'],
}

# Keep as false to keep file size low
JSON_OUTPUT = {
    'keep_raw_date': False,
    'keep_raw_size': False
}

def get_icon_preset(extension):
    """Determine the icon preset for a given file extension"""
    for preset, extensions in ICON_PRESETS.items():
        if extension in extensions:
            return f'icon-{preset}'
    return 'icon-default' if USE_DEFAULT_PRESET else ''  # Use default preset based on setting

def get_directory_size(path, excluded_files=None):
    """Calculate total size of a directory including all subdirectories"""
    if excluded_files is None:
        excluded_files = []
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        filtered_files = [f for f in filenames if f not in excluded_files]
        for filename in filtered_files:
            file_path = os.path.join(dirpath, filename)
            if os.path.isfile(file_path):
                total_size += os.path.getsize(file_path)
    return total_size

def get_directory_id(path):
    """Generate a directory ID based on the full path hierarchy"""
    if path == "." or path == "..":
        return ""
        
    # Split the path into components
    parts = path.split(os.sep)
    if parts[0] == '.':
        parts = parts[1:]  # Remove the leading '.' if present
        
    # Build the ID by tracking level and index for each part
    current_id = []
    for level, _ in enumerate(parts):
        # For each level, we need to find this directory's index among its siblings
        parent_path = os.path.join(*parts[:level]) if level > 0 else "."
        siblings = sorted([d for d in os.listdir(parent_path) 
                         if os.path.isdir(os.path.join(parent_path, d))])
        index = siblings.index(parts[level])
        
        # Generate this level's ID component
        letter = chr(ord('a') + level)
        current_id.append(f"{letter}{index + 1}")
    
    return "".join(current_id)

def process_directory(path, is_root=False, level=0, index=0):
    """Process a directory and return its content"""
    excluded_files = ['snap.py', 'snap.html', 'directories.json'] if is_root else []
    items = os.listdir(path)
    
    if is_root:
        items = [item for item in items if item not in excluded_files]
        
    result = []
    
    # Add parent directory entry
    result.append({
        "type": "directory",
        "name": "..",
        "date": "",
        "date_formatted": "",
        "size": "",
        "size_formatted": "",
        "path": ".."
    })
    
    # Process directories first
    for item in sorted(items):
        full_path = os.path.join(path, item)
        if os.path.isdir(full_path):
            mtime = os.path.getmtime(full_path)
            dir_size = get_directory_size(full_path, excluded_files)
            relative_path = os.path.relpath(full_path, '.')
            directory_id = get_directory_id(relative_path) if item != ".." else ""
            result.append({
                "type": "directory",
                "name": item,
                "date": mtime if mtime else "N/A",
                "date_formatted": format_date(mtime) if mtime else "N/A",
                "size": dir_size,
                "size_formatted": format_size(dir_size),
                "path": relative_path,
                "directory_id": directory_id
            })
    
    # Process files
    for item in sorted(items):
        full_path = os.path.join(path, item)
        if os.path.isfile(full_path):
            extension = item.split('.')[-1] if '.' in item else ''
            icon_preset = get_icon_preset(extension)
            icon_classes = f'icon icon-{extension}'
            if icon_preset:
                icon_classes += f' {icon_preset}'
            
            file_size = os.path.getsize(full_path)
            file_date = os.path.getmtime(full_path)
            
            result.append({
                "type": "file",
                "name": item,
                "date": file_date if file_date else "N/A",
                "date_formatted": format_date(file_date) if file_date else "N/A",
                "size": file_size if file_size else "N/A",
                "size_formatted": format_size(file_size) if file_size else "N/A",
                "icon_classes": icon_classes
            })
    
    return result

def format_size(size):
    """Convert size in bytes to human readable format with 2 decimal points"""
    if not size:
        return "N/A"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"

def format_date(timestamp):
    """Convert Unix timestamp to readable date format"""
    if not isinstance(timestamp, (int, float)):
        return "N/A"
    from datetime import datetime
    return datetime.fromtimestamp(timestamp).strftime('%d/%m/%Y %I:%M %p')

def animate_message(message, stop_event):
    """Display an animated message with cycling dots until stopped"""
    while not stop_event.is_set():
        for i in range(4):
            if stop_event.is_set():
                break
            dots = '.' * i
            # Print message with varying dots, then return to start of line
            sys.stdout.write(f"\r{message}{dots}{' ' * (3-i)}")
            sys.stdout.flush()
            time.sleep(0.3)
    # Clear the line for the next message
    sys.stdout.write("\r" + " " * (len(message) + 3) + "\r")
    sys.stdout.flush()

def generate_html():
    """Generate the HTML for root directory and JSON for subdirectories"""
    excluded_files = ['snap.py', 'snap.html', 'directories.json']
    
    # Create a stop event for the animation
    animation_stop = threading.Event()
    
    # Start animation in a separate thread
    animation_thread = threading.Thread(
        target=animate_message, 
        args=("Processing root directory", animation_stop)
    )
    animation_thread.daemon = True
    animation_thread.start()
    
    try:
        # Process root directory with level 0 (will give 'a' prefixed IDs)
        root_content = process_directory('.', is_root=True, level=0)
    finally:
        # Stop the animation
        animation_stop.set()
        animation_thread.join()
    
    print("Counting directories and files...")
    
    # Get script path and extract drive letter and folder name
    script_path = os.path.abspath(__file__)
    drive_letter, _ = os.path.splitdrive(script_path)
    folder_name = os.path.basename(os.path.dirname(script_path))
    
    # Get drive label
    drive_label = win32api.GetVolumeInformation(drive_letter + "\\")[0]
    drive_name = drive_letter.rstrip(":\\")
    
    # First do a quick walk to count directories for the progress bar
    print("Calculating statistics...")
    all_dirs = []
    for dirpath, dirnames, _ in os.walk('.'):
        all_dirs.append(dirpath)
    
    # Count total files, folders and size
    total_files = 0
    total_folders = -1  # Start at -1 to not count the root directory
    total_size = 0
    
    for dirpath, dirnames, filenames in tqdm(os.walk('.'), total=len(all_dirs), desc="Processing directories"):
        total_folders += len(dirnames)  # Count all subdirectories
        
        # Filter out excluded files before counting
        filtered_files = [f for f in filenames if f not in excluded_files]
        total_files += len(filtered_files)
        
        for filename in filtered_files:
            file_path = os.path.join(dirpath, filename)
            if os.path.isfile(file_path):
                total_size += os.path.getsize(file_path)
    
    # Get current date/time in the same format as file dates
    date_ran = datetime.now().strftime('%d/%m/%Y %I:%M %p')
    
    # Get version timestamp in YYMMDD.HHMM format
    version = datetime.now().strftime('%y%m%d.%H%M')
    
    # Initialize html_content with the header
    html_content = [f'''      <div class="header">
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
    
    # Add the files list after the header
    html_content.append('      <ul id="files" class="view-tiles" data-path="root">')
    for item in root_content:
        if item["type"] == "directory":
            # Skip the parent directory entry in HTML output
            if item["name"] == "..":
                continue
                
            html_content.append(
                f'        <li><a href="{item["path"]}" class="icon icon-directory" title="{item["name"]}">'
                f'<span class="name">{item["name"]}</span>'
                f'<span class="date">{item["date_formatted"]}</span>'
                f'<span class="size">{item["size_formatted"]}</span></a></li>'
            )
        else:  # file
            size_formatted = format_size(item["size"]) if item["size"] != "N/A" else "N/A"
            html_content.append(
                f'        <li><a href="/" class="{item["icon_classes"]}" title="{item["name"]}">'
                f'<span class="name">{item["name"]}</span>'
                f'<span class="date">{item["date_formatted"]}</span>'
                f'<span class="size">{size_formatted}</span></a></li>'
            )
    html_content.append('      </ul>')
    # Add a script tag with empty JSON data for client-side use
    html_content.append('')
    html_content.append('      <script id="dom-cache" type="application/json"></script>')
    html_content.append('')
    
    # Use constants for date and size preferences
    keep_raw_date = JSON_OUTPUT['keep_raw_date']
    keep_raw_size = JSON_OUTPUT['keep_raw_size']
    
    # Always minify without asking
    should_minify = True
    
    # Process and store subdirectories in JSON
    subdirs_data = {
        "version": version,
        "directories": {}
    }
    
    # Start with level 1 for actual subdirectories
    current_level = 1
    # Add the root directory to the JSON data
    subdirs_data["directories"]["."] = root_content
    
    # Process remaining directories with progress bar
    print("Processing subdirectories...")
    remaining_dirs = [d for d in all_dirs if d != '.']
    for root in tqdm(remaining_dirs, desc="Creating file structure data"):
        directory_content = process_directory(root, level=current_level)
        current_level += 1
        
        # Remove unneeded fields based on user preferences
        for item in directory_content:
            if not keep_raw_date and "date" in item:
                del item["date"]
            if not keep_raw_size and "size" in item:
                del item["size"]
        
        subdirs_data["directories"][os.path.relpath(root, '.')] = directory_content
    
    # Minify the JSON data
    minified_json = json.dumps(subdirs_data, separators=(',', ':'))
    
    # Replace the empty script tag with one containing the JSON data
    html_content[html_content.index('      <script id="dom-cache" type="application/json"></script>')] = f'      <script id="dom-cache" type="application/json">{minified_json}</script>'
    
    # Write HTML to file
    print("Writing HTML file...")
    with open('snap.html', 'w', encoding='utf-8') as f:
        f.write('\n'.join(html_content))
    
    # Print summary of choices
    print("Processing complete!")
    
    # Final message and wait for user to press Enter
    print("\nDone!\nPress 'Enter' to exit.")
    input()

if __name__ == '__main__':
    generate_html()