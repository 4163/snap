Take a snapshot/create a copy of your folders/files (file list) and turn it into a navigatable HTML file list.

Made specifically for my personal use on Windows systems. There are no plans to support other operating systems.

The snap.py scripts are a mess and are patchwork after patchwork, I didn't bother properly cleaning and doing proper semantics on them (they could be more optimized and faster but meh). It's not as if the snap-script.js files are beautifully written, they are awful.

Do not rename 'snap.py' when using to avoid having snap.py in your file list output.

Multi Page - JSON
- Recommended for public websites, has good performance and maintainability

- Requires the use of a server because CORS policy blocks JSON fetches.
- Requires JavaScript.
- (Optional) Access to IdexedDB or In-Memory Cache.

1.
	Copy and run snap.py to wherever/whatever you want to create a file list of.
	It will ask if you want to minfy the JS file, choose whichever you prefer (minified JS is smaller in size).
	After running and going through the setup, this will generate your JSON file and snap.html which has HTML snippets.

2.
	Define JSON file location in the HTML head via a meta element:
	<meta name="jsonPath" content="directories_a.json">,
	<meta name="jsonPath" content="directories_b.json"> etc.

	If no JSON file location is defined, snap will use a fallback JSON file. In this case directories.json.

3.
	Define the JSON version in the head via a meta element:
	<meta name="jsonVersion" content="250402.1021">

	The JSON version can be found at the generated snap.html.

If a JSON verion is defined it will;
	Compare the meta JSON version with the JSON file used.
		a. If the JSON versions are identical, prevent fetching the JSON file on page load.
		b. If the JSON versions are NOT identical keep fetching the JSON file on page load.
		c. Loop.
		
If a JSON verion is NOT defined it will;
	Keep fetching the JSON file on page load.
	
Directory caching process:
	a. Once JSON is fetched tries to save JSON data in IndexedDB and uses that for subsequent navigations;
	b. If IndexedDB cannot be accessed use In-Memory Cache for subsequent navigations.
	C. If In-Memory Cache fails, do fetch requests to the JSON file for every action (Very slow).

4.
	Repalce the entire <div class="header">contents...</content> block from your page.

	This can be found at the generated snap.html.

5. Repalce the entire <ul id="files" class="view-tiles" data-path="root">contents...</ul> block from your page.

	This can be found at the generated snap.html.

Multi Page - DOM
- Can be used for public websites, a bit easier to setup and maintain with less performance
- If database/file list is big (html file size of a few megabytes), page may load slow or freeze for a bit on page load.

- Requires JavaScript.
- (Optional) Access to In-Memory Cache.

1.
	Copy and run snap.py to wherever/whatever you want to create a file list of.
	After running your snap.html which has HTML snippets.

2.
	Repalce the entire <div class="header">contents...</content> block from your page.

	This can be found at the generated snap.html.

3. Repalce the entire <ul id="files" class="view-tiles" data-path="root">contents...</ul> block from your page.

	This can be found at the generated snap.html.

4. Repalce the entire <script id="dom-cache" type="application/json"></script> block from your page.

	This can be found at the generated snap.html.

	Notice that depending on your text/code editor of choice these contains thousands of text/lines.
	I have provided '_empty-script-block.html' files which contains empty script blocks for this purpose.

Singe File - DOM
- Recommended to be used for offline snapshots/archives of your file list. 
- Not recommended to be used for public websites, less performance and close to zero maintanability/customization.

- Requires JavaScript.

1.
	Copy and run snap.py to whatever you want to create a file list of.

Others

Each file format needs to be defined in the snap.py script under the ICON_PRESETS dictionary on top (case sensitive).

By default any file format not defined will have no icon or can be set use the default icon. This can be changed in the snap.py script under the USE_DEFAULT_PRESET variable.

CSS:
Feel free to edit or mess the CSS/HTML stylings but keep the necessary IDs, classes, and data variables used.

To use custom icons for specific file formats you can edit the snap-style.css file.
Add a new icon type under the /*hocchan union archive*/ comment.

Afterwards define a new icon type with the file formats it will use. This can be done in snap.py under the ICON_PRESETS dictionary.
'X' is defined as the 'icon-X' defined in snap-style.css with 'icon-' part omitted.

// WIP
snap-script.js settings / structure,
file type icons customization,
other things of note too tired to remember rn,
readme md formatting.