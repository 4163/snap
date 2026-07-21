# snap

## Used In
> **Hocchan Archive / Drives**  
> https://hocchan.netlify.app/archive/drive/g

## _Create an HTML copy of your file list_
Take a snapshot of folders/files and turn it into a navigatable HTML file list.

This project is provided as-is. It's primarily built for my workflow, thus Windows only, there are no plans to support other operating systems.

The `📄snap.py` files are a mess and contain a lot of patchwork, I didn't bother properly cleaning as that would require a lot of structure rewrites (in short, they could be more readable and faster). The same can especially be said for the `📄snap-script.js` files, they are awful.

> Do not rename `📄snap`.py when using to avoid having *snap.py* listed in your file list output.

`📄snap.py` requires [Python](https://www.python.org/downloads/) to run, and when running for the first time it may ask you to install some dependencies which are required, just type `y` to automatically install them and re-open the file.

#### References:
[Multi Page - JSON](#multi-page---json)  
[Multi Page - DOM](#multi-page---dom)  
[Single File - DOM](#single-file---dom)

### Multi Page - JSON
- Recommended for public websites, has good performance and maintainability
- Requires the use of a server because CORS policy blocks JSON fetches.
- Requires JavaScript.
- (Optional) Access to IndexedDB or In-Memory Cache.

#### 1. Generate JSON and HTML snippets:
**a.** Copy and run `📄snap.py` to wherever/whatever you want to create a file list of.  
**b.** It will ask if you want to minify the JSON file, choose whichever you prefer (minified JSON is smaller in size).  
**c.** After running and going through the setup, this will generate your `📄JSON` file and `📄snap.html` which has HTML snippets.

#### 2. For your individual snap pages:
**a.** Define JSON file location in the HTML head via a `meta` element.  
![json file location](https://i.imgur.com/V6yTKih.png)

If no JSON file location is defined, the page will use a fallback JSON file (in this case `📄directories.json` is defined as the fallback in `📄snap-script.js` under object `CONFIG`), so be sure to set a `jsonPath`.  
![json file location](https://i.imgur.com/z3S6F04.png)

**b.** Define the JSON version in the head via a `meta` element.  
![json version](https://i.imgur.com/TSY4f9s.png)

The JSON version can be found at the generated `📄snap.html`.

**c.** Replace the entire `<div class="header">...</div>` block from your page.  
![html header](https://i.imgur.com/3eRewHH.png)

This can be found at the generated `📄snap.html`.

**d.** Replace the entire `<ul id="files" class="view-tiles" data-path="root">...</ul>` block from your page.  
![html ul](https://i.imgur.com/sI2L4Fy.png)

Again, this can be found at the generated `📄snap.html`.
	
#### If a JSON version is defined:
- Compare the meta `jsonVersion` with the `📄JSON` file used.
- If the JSON versions are identical, prevent fetching the `📄JSON` file on page load.
- If the JSON versions are NOT identical keep fetching the `📄JSON` file on page load.
- Loop.

#### If a JSON version is NOT defined:
- Keep fetching the `📄JSON` file on page load.
    
#### Directory caching process:
- Once `📄JSON` is fetched tries to save JSON data in IndexedDB and uses that for subsequent navigations;
- If IndexedDB cannot be accessed use In-Memory Cache for subsequent navigations.
- If In-Memory Cache fails, do fetch requests to the `📄JSON` file for every action/navigation (Very slow).

### Multi Page - DOM
- Can be used for public websites, a bit easier to setup and maintain with less performance
- If database/file list is big (html file size of a few megabytes), page may load slow or freeze for a bit on page load.
- Requires JavaScript.
- (Optional) Access to In-Memory Cache.

#### 1. Generate HTML snippet:
**a.** Copy and run `📄snap.py` to wherever/whatever you want to create a file list of.  
**b.** After running this will generate your `📄snap.html` which has HTML snippets.

#### 2. For your individual snap pages:
**a.** Replace the entire `<div class="header">...</div>` block from your page.  
![html header](https://i.imgur.com/7OoFk1S.png)

This can be found at the generated `📄snap.html`.

**b.** Replace the entire `<ul id="files" class="view-tiles" data-path="root">...</ul>` block from your page.  
![html ul](https://i.imgur.com/5nTlnbO.png)

This can be found at the generated `📄snap.html`.

**c.** Replace the entire `<script id="dom-cache" type="application/json">...</script>` block from your page.  
![html dom cache/json](https://i.imgur.com/bheLy1k.png)

Again, this can be found at the generated `📄snap.html`.

*Notice that depending on your text or code editor, this may display several hundred lines, as these blocks contain thousands of characters.  
I have provided `📄_empty-script-block.html` files which contain empty script blocks for this purpose.*  
![json version](https://i.imgur.com/Io2Ru9o.png)
  
![json version](https://i.imgur.com/TTzumaR.png)

#### Directory caching process:
- If In-Memory Cache fails, script reads from  `<script id="dom-cache" type="application/json">...</script>` for every action/navigation.

### Single File - DOM
- Recommended to be used for offline snapshots/archives of your file list. 
- Not recommended to be used for public websites, less performance and close to zero maintainability/customization.
- If database/file list is big (html file size of a few megabytes), page may load slow or freeze for a bit on page load.
- Requires JavaScript.

#### Generate HTML file list
**-** Copy and run `📄snap.py` to whatever you want to create a file list of.

#### Directory caching process:
- If In-Memory Cache fails, script reads from  `<script id="dom-cache" type="application/json">...</script>` for every action/navigation.

### Others
Feel free to edit or mess the CSS/HTML stylings but keep the necessary IDs, classes, and data variables used.

#### Custom icons:
On `📄snap-style.css` add a new icon type under the `/*hocchan union archive*/` comment;  
![json version](https://i.imgur.com/hHoQoLy.png)

On `📄snap.py` under the `ICON_PRESETS` dictionary, define a new icon type with the file formats it will use;  
![json version](https://i.imgur.com/yROWc6n.png)

`'A': ['B'],`
`'A'` is the `.icon-A` defined in `📄snap-style.css` with the `.icon-` part omitted.
And `'B'` is the file format(s) that will use that icon preset.

By default any file format not defined will have no icon or can be set to use the default icon preset. This can be done in the `📄snap.py` script by changing the `USE_DEFAULT_PRESET` variable to true.  
![json version](https://i.imgur.com/osw8i9Z.png)

If you somehow want to edit the HTML/CSS/JS for the *snap Single File - DOM version* (why). The CSS is minified, just beautify it. And the JS is encoded as Base64, decode that and then beautify it as that is also minified, or alternatively just use/edit the Multi Page - DOM JS and Base64 encode it as that uses the same JS script.
