
import json
import os
import win32com.client
import win32api
import win32con


INPUT_FILE = "directories.json"
INJECT_FILE = "inject.json"
OUTPUT_FILE = "directories-output_(injected).json"
OUTPUT_LIST = "injected-list.html"

def load_json_wo_version(path):
	with open(path, 'r', encoding='utf-8') as f:
		data = json.load(f)
	# Remove 'version' key if present
	data.pop('version', None)
	return data

import random
import datetime
def save_json(data, path):
	# Add a new version field: date + random 6-digit hash
	rand_hash = f"{random.randint(0, 999999):06d}"
	# Write version key first, then directories, with '.' as the first directory
	out = {'version': rand_hash}
	data['version'] = rand_hash  # propagate to merged for HTML output
	if 'directories' in data:
		dirs = data['directories']
		ordered_dirs = {}
		# Ensure '.' is first, then the rest sorted by Windows logic
		dir_keys = list(dirs.keys())
		from functools import cmp_to_key
		def cmp_str(a, b):
			return win_strcmp_logical(a, b)
		if '.' in dir_keys:
			ordered_keys = ['.'] + sorted([k for k in dir_keys if k != '.'], key=cmp_to_key(cmp_str))
		else:
			ordered_keys = sorted(dir_keys, key=cmp_to_key(cmp_str))
		for k in ordered_keys:
			items = dirs[k]
			# Directories first, then files, both sorted by Windows logic
			dir_items = [item for item in items if item.get('type') == 'directory']
			file_items = [item for item in items if item.get('type') == 'file']
			dir_items = win_logical_sort(dir_items)
			file_items = win_logical_sort(file_items)
			ordered_dirs[k] = dir_items + file_items
		out['directories'] = ordered_dirs
	for k, v in data.items():
		if k not in ('version', 'directories'):
			out[k] = v
	with open(path, 'w', encoding='utf-8') as f:
		json.dump(out, f, indent=2, ensure_ascii=False)

def logical_sort_key(name):
	# Use StrCmpLogicalW via pywin32 for Windows Explorer-like sorting
	# We'll use a COM object to access StrCmpLogicalW for sorting
	# But for key function, we use a wrapper that sorts using StrCmpLogicalW
	return name

def win_strcmp_logical(a, b):
	# Use StrCmpLogicalW from shlwapi.dll via pywin32
	import ctypes
	shlwapi = ctypes.windll.shlwapi
	StrCmpLogicalW = shlwapi.StrCmpLogicalW
	StrCmpLogicalW.restype = ctypes.c_int
	StrCmpLogicalW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
	return StrCmpLogicalW(a, b)

def win_logical_sort(items):
	# Sort using StrCmpLogicalW
	def cmp(a, b):
		return win_strcmp_logical(a['name'], b['name'])
	from functools import cmp_to_key
	return sorted(items, key=cmp_to_key(lambda a, b: win_strcmp_logical(a['name'], b['name'])))


def merge_directories(base, inject):
	merged = dict()
	for dir_key in base.keys() | inject.keys():
		base_items = base.get(dir_key, [])
		inject_items = inject.get(dir_key, [])
		# Build lookup for existing items by (type, name)
		base_lookup = {(item['type'], item['name']): item for item in base_items}
		inject_lookup = {(item['type'], item['name']): item for item in inject_items}
		# Start with all base items (preserve all fields)
		merged_items = list(base_items)
		# Append new inject items not present in base
		for key, item in inject_lookup.items():
			if key not in base_lookup:
				merged_items.append(item)
		# Sort using Windows logical sort
		merged_items = win_logical_sort(merged_items)
		# Reassign item_id fields for files (type=="file") sequentially after sorting
		file_id = 1
		for item in merged_items:
			if item.get('type') == 'file':
				item['item_id'] = file_id
				file_id += 1
		merged[dir_key] = merged_items
	return merged


def make_root_ul(merged):
	# Only use the root directory (".")
	import datetime
	root_items = merged['directories'].get('.', [])
	# Directories first, then files, both sorted using Windows logic
	dir_items = [item for item in root_items if item.get('type') == 'directory' and item.get('name') != '..']
	file_items = [item for item in root_items if item.get('type') == 'file']
	dir_items = win_logical_sort(dir_items)
	file_items = win_logical_sort(file_items)

	# Count files and folders (recursively)
	def count_files_folders(dirs):
		file_count = 0
		folder_count = 0
		size_total = 0
		for k, items in dirs.items():
			for item in items:
				if item.get('type') == 'directory' and item.get('name') != '..':
					folder_count += 1
				elif item.get('type') == 'file':
					file_count += 1
					try:
						sz = item.get('size', 0)
						if isinstance(sz, str):
							sz = float(sz) if sz not in ("N/A", "") else 0
						size_total += sz
					except Exception:
						pass
		return file_count, folder_count, size_total

	file_count, folder_count, size_total = count_files_folders(merged['directories'])

	def format_size(size):
		if not size:
			return "N/A"
		for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
			if size < 1024.0:
				return f"{size:.2f} {unit}"
			size /= 1024.0
		return f"{size:.2f} PB"

	now = datetime.datetime.now().strftime('%d/%m/%Y %I:%M %p')
	version = merged.get('version', '')
	lines = []
	lines.append(f'    <meta name="jsonVersion" content="{version}">')
	lines.append('')
	lines.append(f'        <span>{file_count} files in {folder_count} folders ({format_size(size_total)})</span>')
	lines.append('')
	lines.append(f'        <span class="info">Generated with <a href="https://github.com/4163/snap" target="_blank">snap</a> at {now}</span>')
	lines.append('')
	lines.append('      <ul id="files" class="view-tiles" data-path="root">')
	for item in dir_items:
		lines.append(
			f'        <li><a href="{item["path"]}" class="icon icon-directory" title="{item["name"]}"><span class="name">{item["name"]}</span><span class="date">{item.get("date_formatted", "")}</span><span class="size">{item.get("size_formatted", "")}</span></a></li>'
		)
	for item in file_items:
		lines.append(
			f'        <li><a href="/" class="{item.get("icon_classes", "icon icon-default")}" title="{item["name"]}"><span class="name">{item["name"]}</span><span class="date">{item.get("date_formatted", "")}</span><span class="size">{item.get("size_formatted", "")}</span></a></li>'
		)
	lines.append('      </ul>')
	lines.append('')
	return '\n'.join(lines)

def main():
	base = load_json_wo_version(INPUT_FILE)
	inject = load_json_wo_version(INJECT_FILE)
	merged = {}
	merged['directories'] = merge_directories(base.get('directories', {}), inject.get('directories', {}))
	save_json(merged, OUTPUT_FILE)
	# Write HTML list for root
	with open(OUTPUT_LIST, 'w', encoding='utf-8') as f:
		f.write(make_root_ul(merged))

if __name__ == '__main__':
	main()
