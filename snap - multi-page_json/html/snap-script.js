function $(t) {
	var a = "string" == typeof t ? document.getElementById(t) : t;
	return a.on = function(t, e) {
		"content loaded" == t && (t = window.attachEvent ? "load" : "DOMContentLoaded"), a.addEventListener ? a.addEventListener(t, e, !1) : a.attachEvent("on" + t, e)
	}, a.all = function(t) {
		return $(a.querySelectorAll(t))
	}, a.each = function(t) {
		for (var e = 0, n = a.length; e < n; ++e) t($(a[e]), e)
	}, a.getClasses = function() {
		return this.getAttribute("class").split(/\s+/)
	}, a.addClass = function(t) {
		var e = this.getAttribute("class");
		a.setAttribute("class", e ? e + " " + t : t)
	}, a.removeClass = function(e) {
		var t = this.getClasses().filter(function(t) {
			return t != e
		});
		this.setAttribute("class", t.join(" "))
	}, a
}

function search() {
	var n = $("search").value.toLowerCase();
	$("files").all("a").each(function(t) {
		var e = t.textContent.toLowerCase();
		".." != e && (n.length && ~e.indexOf(n) ? t.addClass("highlight") : t.removeClass("highlight"))
	})
}
$(window).on("content loaded", function() {
	$("search").on("keyup", search)
})
  
    // Configuration options
    const CONFIG = {
    	batchSize: 25, // Number of files/folders to process in each batch (folder navigation)
		navigationDelay: 200, // Delay in ms before navigation to allow CSS animations to complete (only applied on touch devices)

    	useFormattedDate: true, // Use formatted date instead of timestamp
    	useFormattedSize: true, // Use formatted size instead of bytes
        jsonFallback: 'directories.json', // Default JSON file path if it's not defined on the html meta tag
    	
		all: '>* ', // Search pattern to search for all items
    	folder: '>*folder ', // Search pattern to search for folders only
    	file: '>*file ', // Search pattern to search for files only

		// Simulate caching failure if set to false
		indexedDB: true,
		memoryCache: true
    };

    // Add a utility function to detect coarse pointer at the top level
    function hasCoarsePointer() {
    	return window.matchMedia('(pointer: coarse)').matches;
    }

    /*
     * CACHE AND FETCH PROCESS:
     * 1. Check if IndexedDB cache exists via getCachedVersion()
     * 2. If meta tag has version info:
     *    a. Compare cached version with current version
     *    b. If versions match AND cached data exists, use cached data
     *    c. If versions don't match OR no cache exists, fetch JSON and save to IndexedDB
     * 3. If no version in meta tag (legacy mode):
     *    a. Always fetch new data and save to cache
     * 4. For subsequent navigation after initial load:
     *    a. Try to use cached data first
     *    b. Only fetch again if cache retrieval fails
     * 5. Opera browser: Known issues with IndexedDB implementation may cause errors
     *    a. Falls back to in-memory cache when IndexedDB operations fail
     */

	/*
	 * Each folder navigation attempt:
	 * Tries IndexedDB first (fails)
	 * Tries memory cache as fallback (fails, returns undefined)
	 * Falls back to fetching the JSON file again
	 * Attempts to cache but fails again
	 * Repeats this cycle for every navigation
	 */

    // IndexedDB setup and helper functions
    const DB_NAME = 'directoryCache';
    const STORE_NAME = 'directories';
    const DB_VERSION = 1;

    // In-memory cache as fallback
    const memoryCache = new Map();

    // Only override memory cache methods if memory cache is disabled
    if (!CONFIG.memoryCache) {
        memoryCache.get = () => undefined;  // Returns undefined instead of throwing
        memoryCache.set = () => {};         // Does nothing but doesn't throw
    }

    function openDB() {
		if (!CONFIG.indexedDB) {
			return Promise.reject(new Error("IndexedDB failure"));
		}
        return new Promise((resolve, reject) => {
            try {
                const request = indexedDB.open(DB_NAME, DB_VERSION);
                
                request.onerror = () => reject(request.error);
                request.onsuccess = () => resolve(request.result);
                
                request.onupgradeneeded = (event) => {
                    const db = event.target.result;
                    if (!db.objectStoreNames.contains(STORE_NAME)) {
                        db.createObjectStore(STORE_NAME);
                    }
                };
            } catch (e) {
                reject(e);
            }
        });
    }

    function getFromCache(key) {
        return new Promise((resolve, reject) => {
            openDB().then(db => {
                try {
                    const transaction = db.transaction(STORE_NAME, 'readonly');
                    const store = transaction.objectStore(STORE_NAME);
                    const request = store.get(key);
                    
                    request.onerror = () => {
                        // Fall back to memory cache
                        if (memoryCache.has(key)) {
                            resolve(memoryCache.get(key));
                        } else {
                            reject(request.error);
                        }
                    };
                    
                    request.onsuccess = () => resolve(request.result);
                } catch (e) {
                    // Fall back to memory cache
                    if (memoryCache.has(key)) {
                        resolve(memoryCache.get(key));
                    } else {
                        reject(e);
                    }
                }
            }).catch(error => {
                // If IndexedDB fails, try memory cache
                if (memoryCache.has(key)) {
                    resolve(memoryCache.get(key));
                } else {
                    reject(error);
                }
            });
        });
    }

    function saveToCache(key, data) {
        return new Promise((resolve, reject) => {
            openDB().then(db => {
                try {
                    const transaction = db.transaction(STORE_NAME, 'readwrite');
                    const store = transaction.objectStore(STORE_NAME);
                    const request = store.put(data, key);
                    
                    request.onerror = () => {
                        // Fall back to memory cache
                        try {
                            memoryCache.set(key, data);
                            resolve(true);
                        } catch (e) {
                            console.warn('Memory cache failed, continuing without cache');
                            resolve(true);
                        }
                    };
                    
                    request.onsuccess = () => resolve(request.result);
                } catch (e) {
                    // Fall back to memory cache
                    try {
                        memoryCache.set(key, data);
                        resolve(true);
                    } catch (e) {
                        console.warn('Memory cache failed, continuing without cache');
                        resolve(true);
                    }
                }
            }).catch(error => {
                // If IndexedDB fails, try memory cache
                try {
                    memoryCache.set(key, data);
                    resolve(true);
                } catch (e) {
                    console.warn('Memory cache failed, continuing without cache');
                    resolve(true);
                }
            });
        });
    }

    // Flag to track if initial load is complete
    let initialLoadComplete = false;
	let usingMemoryCache = false;

    // Add a new function to get cached version
    async function getCachedVersion() {
        try {
            // Try from IndexedDB first
            const cachedData = await getFromCache(CONFIG.jsonPath);
            return cachedData?.version || null;
        } catch (error) {
            // console.warn('Error getting cached version from IndexedDB:', error);

            // Try from memory cache
            const memoryCachedData = memoryCache.get(CONFIG.jsonPath);
            return memoryCachedData?.version || null;
        }
    }

    // Preload the JSON data on page load
    async function preloadDirectoryData() {
        // Get the JSON path from meta tag or use fallback
        const jsonPathMeta = document.querySelector('meta[name="jsonPath"]');
        CONFIG.jsonPath = jsonPathMeta ? jsonPathMeta.getAttribute('content') : CONFIG.jsonFallback;
        
        // Get version from meta tag
        const jsonVersionMeta = document.querySelector('meta[name="jsonVersion"]');
        const currentVersion = jsonVersionMeta ? jsonVersionMeta.getAttribute('content') : null;
        
        try {
            if (currentVersion) {
                // Version-based caching
                // Get cached version
                const cachedVersion = await getCachedVersion();
                
                // If versions match, use cached data
                if (cachedVersion && cachedVersion === currentVersion) {
                    try {
                        // Try IndexedDB first
                        const cachedData = await getFromCache(CONFIG.jsonPath);
                        if (cachedData) {
                            initialLoadComplete = true;
                            return cachedData;
                        }
                    } catch (cacheError) {
                        // Try memory cache
                        const memoryCachedData = memoryCache.get(CONFIG.jsonPath);
                        if (memoryCachedData) {
                            initialLoadComplete = true;
                            return memoryCachedData;
                        }
                    }
                }
            }
            
            // If versions don't match or no cache, fetch new data
            const response = await fetch(CONFIG.jsonPath);
            const data = await response.json();

            // Try to save to cache but don't let it block the app if it fails
            try {
                await saveToCache(CONFIG.jsonPath, data);
            } catch (cacheError) {
                console.warn('Failed to save to cache, continuing without caching:', cacheError);
                // Still try memory cache as last resort
                memoryCache.set(CONFIG.jsonPath, data);
            }
            
            initialLoadComplete = true;
            return data;
        } catch (error) {
            console.error('Error preloading directory data:', error);
            
            // Try one more time to get from cache in case the fetch failed
            try {
                // Try IndexedDB
                const cachedData = await getFromCache(CONFIG.jsonPath);
                if (cachedData) {
                    initialLoadComplete = true;
                    return cachedData;
                }
            } catch (cacheError) {
                // Try memory cache
                const memoryCachedData = memoryCache.get(CONFIG.jsonPath);
                if (memoryCachedData) {
                    initialLoadComplete = true;
                    return memoryCachedData;
                }
                
                // If both fetch and cache fail, we have a serious problem
                console.error('Unable to fetch data or access any cache:', cacheError);
            }
            
            initialLoadComplete = true;
            throw error;
        }
    }

    // Modified fetchDirectoryData function
    async function fetchDirectoryData() {
        // If initial load is not complete, wait for it
        if (!initialLoadComplete) {
            try {
                return await preloadDirectoryData();
            } catch (error) {
                // If preload failed, try to get from cache one more time
                try {
                    const cachedData = await getFromCache(CONFIG.jsonPath);
                    if (cachedData) return cachedData;
                } catch (cacheError) {
                    console.warn('IndexedDB cache access failed:', cacheError);
                    
                    // Try memory cache
                    const memoryCachedData = memoryCache.get(CONFIG.jsonPath);
                    if (memoryCachedData) return memoryCachedData;
                }
                
                // If all else fails, make one direct fetch attempt as a last resort
                try {
                    const response = await fetch(CONFIG.jsonPath);
                    const data = await response.json();
                    // Store in memory cache for future use
                    memoryCache.set(CONFIG.jsonPath, data);
                    return data;
                } catch (fetchError) {
                    console.error('Final fetch attempt failed:', fetchError);
                    throw error; // Re-throw the original error if all attempts fail
                }
            }
        }
        
        // For subsequent calls, use the cached data
        try {
            // Try IndexedDB
            const cachedData = await getFromCache(CONFIG.jsonPath);
            if (cachedData) return cachedData;
            
            // If cache is empty, fetch again
            return await preloadDirectoryData();
        } catch (error) {
           //  console.warn('Error fetching directory data from IndexedDB cache:', error);
            
            // Try memory cache
            const memoryCachedData = memoryCache.get(CONFIG.jsonPath);
            if (memoryCachedData) return memoryCachedData;
            
            // If cache access fails, try a direct fetch
            try {
                const response = await fetch(CONFIG.jsonPath);
                const data = await response.json();
                // Store in memory cache for future use
                memoryCache.set(CONFIG.jsonPath, data);
                return data;
            } catch (fetchError) {
                console.error('Both cache and fetch failed:', fetchError);
                throw fetchError;
            }
        }
    }

    document.addEventListener('DOMContentLoaded', function() {
    	// Initialize folder navigation flag
    	window.isFolderNavigation = false;
    	
    	// Start preloading the JSON data immediately and chain the hash handling
    	preloadDirectoryData()
    		.then(() => {
    			// Only handle the hash after preload is complete
    			return handleInitialHash();
    		});
    	
    	// Session storage for search
    	const searchInput = document.getElementById('search');
    	
    	// Add event listener for Enter key to blur the search input
    	searchInput.addEventListener('keydown', function(event) {
    		if (event.key === 'Enter') {
    			this.blur();
    		}
    	});
    	
    	// Function to update the datalist of #search attribute based on pointer type
    	function updateSearchDatalist() {
    		if (hasCoarsePointer()) {
    			// Add the datalist attribute for touch devices
    			searchInput.setAttribute('list', 'search-patterns');
    		} else {
    			// Remove the datalist attribute for non-touch devices
    			searchInput.removeAttribute('list');
    		}
    	}
    	
    	// Initial update
    	updateSearchDatalist();
    	
    	// Set up a media query to detect changes in pointer type
    	const mediaQuery = window.matchMedia('(pointer: coarse)');
    	
    	// Add a listener for changes in the media query
    	if (mediaQuery.addEventListener) {
    		// Modern browsers
    		mediaQuery.addEventListener('change', updateSearchDatalist);
    	} else {
    		// Older browsers (mainly for IE)
    		mediaQuery.addListener(updateSearchDatalist);
    	}

    	// Handle special search patterns defined in CONFIG
    	let isSpecialSearchActive = false;

    	searchInput.addEventListener('input', function(e) {
    		// Check if the input starts with any of our special patterns
    		const startsWithAllPattern = this.value.startsWith(CONFIG.all);
    		const startsWithFolderPattern = this.value.startsWith(CONFIG.folder);
    		const startsWithFilePattern = this.value.startsWith(CONFIG.file);
    		
    		// Determine if any special pattern is active
    		const isAnySpecialPattern = startsWithAllPattern || startsWithFolderPattern || startsWithFilePattern;
    		
    		// If we're already in special search mode and the input changes, cancel any ongoing batch processing
    		if (isSpecialSearchActive && isAnySpecialPattern) {
    			// Cancel any ongoing batch processing
    			nano = true;
    		}
    		
    		// Only reset to root when ENTERING special search mode
    		if (!isSpecialSearchActive && isAnySpecialPattern) {
    			isSpecialSearchActive = true;
    			
    			// Go back to root
    			resetToRoot();
    		}
    		
    		// Handle special search patterns
    		if (isAnySpecialPattern && isSpecialSearchActive) {
    			let searchTerm, searchType;
    			
    			if (startsWithFolderPattern) {
    				searchTerm = this.value.substring(9).trim(); // Get everything after ">*folder "
    				searchType = 'folder';
    			} else if (startsWithFilePattern) {
    				searchTerm = this.value.substring(7).trim(); // Get everything after ">*file "
    				searchType = 'file';
    			} else {
    				searchTerm = this.value.substring(3).trim(); // Get everything after ">* "
    				searchType = 'all';
    			}
    			
    			if (searchTerm) {
    				performSpecialSearch(searchTerm, searchType);
    			} else {
    				// If there's no search term after the prefix, revert to normal display
    				resetToNormalDisplay();
    			}
    		} else if (!isAnySpecialPattern && isSpecialSearchActive) {
    			// If the input no longer starts with any special pattern but was in special search mode,
    			// deactivate special search and go back to root
    			isSpecialSearchActive = false;
    			
    			// Cancel any ongoing batch processing
    			nano = true;
    			
    			// Go back to root and run search
    			resetToRoot(true);
    		}
    		
    		// Existing code for saving search text
    		sessionStorage.setItem('searchText', this.value);
    	});

    	// Load saved search text from sessionStorage
    	const savedSearch = sessionStorage.getItem('searchText');
    	if (savedSearch) {
    		// Check if the saved search starts with any special pattern
    		if (savedSearch.startsWith(CONFIG.all) || 
    			savedSearch.startsWith(CONFIG.folder) || 
    			savedSearch.startsWith(CONFIG.file)) {
    			// Clear the special pattern from session storage
    			sessionStorage.removeItem('searchText');
    			searchInput.value = '';
    		} else {
    			// Load the normal search text
    			searchInput.value = savedSearch;
    			search(); // Call search when restoring saved text
    		}
    	}

    	// ==========================

    	// Show date/show size slider
    	const filesDiv = document.querySelector('#files');
    	const dateToggle = document.querySelector('.date-toggle');
    	const sizeToggle = document.querySelector('.size-toggle');

    	// Load saved states from sessionStorage
    	const showDate = sessionStorage.getItem('showDate') === 'true';
    	const showSize = sessionStorage.getItem('showSize') === 'true';

    	// Set initial states
    	dateToggle.checked = showDate;
    	sizeToggle.checked = showSize;
    	if (showDate) {
    		disableSliderTransition('slider-date');
    		filesDiv.classList.add('show-date');
    	} else {
    		filesDiv.classList.remove('show-date');
    	}

    	if (showSize) {
    		disableSliderTransition('slider-size');
    		filesDiv.classList.add('show-size');
    	} else {
    		filesDiv.classList.remove('show-size');
    	}

		function disableSliderTransition(sliderId) {
			const slider = document.querySelector(`#${sliderId}`);
			
			slider.style.transition = '0s';
			
			const sliderStyle = document.createElement('style');
			sliderStyle.textContent = `#${sliderId}::before { transition: 0s }`;
			document.head.appendChild(sliderStyle);
			
			setTimeout(() => {
				slider.style.removeProperty('transition');
				document.head.removeChild(sliderStyle);
			}, 50);
		}

    	dateToggle.addEventListener('change', function() {
    		filesDiv.classList.toggle('show-date', this.checked);
    		sessionStorage.setItem('showDate', this.checked);
    	});

    	sizeToggle.addEventListener('change', function() {
    		filesDiv.classList.toggle('show-size', this.checked);
    		sessionStorage.setItem('showSize', this.checked);
    	});

    	// Helper function to apply toggle classes based on session storage
    	function applyToggleClasses(container) {
    		const showDate = sessionStorage.getItem('showDate') === 'true';
    		const showSize = sessionStorage.getItem('showSize') === 'true';

    		if (showDate) container.classList.add('show-date');
    		if (showSize) container.classList.add('show-size');
    	}

    	// ==========================

    	// Store the original HTML content when the page loads
    	const rootContainer = document.querySelector('[data-path="root"]');
    	const originalContent = rootContainer.innerHTML;
    	let targetPath = 'root';
    	let pathHistory = []; // Keep track of the navigation path

    	// Apply initial classes based on session storage
    	applyToggleClasses(rootContainer);

		// Add this near the top with other state variables
		let isNavigating = false;

    	// Add click event listener to all directory links
    	document.addEventListener('click', function(e) { // RIPE
    		const linkElement = e.target.closest('a');
    		if (!linkElement) return;

    		// Only handle clicks on links inside .directory-path and #files
    		if (linkElement.closest('.directory-path') || linkElement.closest('#files')) {
    			e.preventDefault(); // Prevent default link behavior
    		}

    		// Check if we're in any special search mode
    		const searchInput = document.getElementById('search');
    		const isSpecialAllSearch = searchInput && searchInput.value.startsWith(CONFIG.all);
    		const isSpecialFolderSearch = searchInput && searchInput.value.startsWith(CONFIG.folder);
    		const isSpecialFileSearch = searchInput && searchInput.value.startsWith(CONFIG.file);
    		const isAnySpecialSearch = isSpecialAllSearch || isSpecialFolderSearch || isSpecialFileSearch;

    		// Cancel any ongoing batch processing
    		nano = true;

    		// Handle directory navigation
    		if (linkElement.classList.contains('icon-directory') || linkElement.closest('.directory-path')) {

				if (isNavigating) return;

    			const folderName = linkElement.getAttribute('href');

    			// Only apply delay if pointer is coarse (touch device)
    			const delay = hasCoarsePointer() ? CONFIG.navigationDelay : 0;

    			// Special handling for search link
    			if (folderName === '#search') {
    				return;
    			}
				
    			// Clear search bar when an item is clicked
    			// This ensures we stop any ongoing search operations before navigation
    			isAnySpecialSearch && resetSearchState();

				if (hasCoarsePointer()) {
					isNavigating = true;
					setTimeout(() => {
						isNavigating = false;
					}, CONFIG.navigationDelay);
				}
				
    			// Add a small delay before navigation to allow CSS animations to complete (only on touch devices)
    			setTimeout(() => {
    				// Check if this is the root link (~ symbol)
    				if (linkElement.getAttribute('href') === '/') {
    					// Go back to root and run search
    					resetToRoot(true, true);
    					return;
    				}

    				if (folderName === '..') {
    					if (pathHistory.length > 0) {
    						pathHistory.pop();
    						logPathHistory('<');
    					}

    					if (pathHistory.length === 0) {
    						// If we're back at root
    						resetToRoot(true);
    						return;
    					}

    					// Set flag for normal folder navigation
    					window.isFolderNavigation = true;
    					RIPE(pathHistory[pathHistory.length - 1]);
    					return;
    				}

    				// Handle path navigation
    				if (linkElement.closest('.directory-path')) {
    					const pathLinks = Array.from(document.querySelector('.directory-path').getElementsByTagName('a'));
    					const clickedIndex = pathLinks.indexOf(linkElement);
    					if (clickedIndex !== -1) {
    						pathHistory = pathHistory.slice(0, clickedIndex);
    						logPathHistory('🍞');
    					}
					} else if (isAnySpecialSearch) {
    					// If we're in search results and clicking on a directory, construct the full path
    					// Fetch the full path structure
    					fetchDirectoryData()
    						.then(data => {
    							// Reset path history
    							pathHistory = [];
    							
    							// Construct the full path by parsing the folder path
								// Call the function with folderName
								buildPathHistory(folderName, data, pathHistory);
    							
    							// Log the path we're about to navigate to
    							logPathHistory('>');
    							
    							// Navigate to the folder
    							window.isFolderNavigation = true;
    							RIPE(folderName);
    						})
    				} else {
    					// Normal directory navigation
    					// Check if this folder is already the last item in path history
    					if (pathHistory.length === 0 || pathHistory[pathHistory.length - 1] !== folderName) {
    						pathHistory.push(folderName);
    						logPathHistory('>');
    					}
    				}
    				// Set flag for normal folder navigation
    				window.isFolderNavigation = true;
    				RIPE(folderName);
    			}, delay);
    		} else {
    			// For non-directory items, always update the display with current path
    			// Only apply delay if pointer is coarse (touch device)
    			const delay = hasCoarsePointer() ? CONFIG.navigationDelay : 0;

				if (hasCoarsePointer()) {
					isNavigating = true;
					setTimeout(() => {
						isNavigating = false;
					}, CONFIG.navigationDelay);
				}

    			setTimeout(() => {
    				// If we're in special search mode and clicked on a file, navigate to its parent folder
    				if (isAnySpecialSearch && linkElement.closest('li') && !linkElement.classList.contains('icon-directory')) {
    					// Get the parent directory from the href attribute
    					const parentDir = linkElement.getAttribute('href');
						// Store the name of the clicked item to highlight it later
						const clickedItemName = linkElement.getAttribute('title');
    					
    					// Special case: if parentDir is ".", navigate to root
    					if (parentDir === ".") {
    						// Store the name of the clicked item to highlight it later
    						lastClickedItemName = linkElement.getAttribute('title');
    						
    						// Clear search bar before navigation
    						resetSearchState();

    						// Navigate to root
    						resetToRoot(false, false, false, true);
    						
    						return;
    					}
    					
    					// Regular case: navigate to parent directory
    					// Fetch the full path structure
    					fetchDirectoryData()
    						.then(data => {
    							// Reset path history
    							pathHistory = [];
    							
								// Construct the full path by parsing the folder path
								// Call the function with parentDir
								buildPathHistory(parentDir, data, pathHistory);
								
								// Log the path we're about to navigate to
								logPathHistory('>');

    							// Update the directory path immediately
    							const directoryPath = document.querySelector('.directory-path');
    							let pathHtml = '<a href="/">~</a> / ';
    							pathHistory.forEach(folder => {
    								// Extract the last meaningful part of the path while preserving full folder names
    								const displayName = folder.split(/[\/\\]/).pop(); // Split by both forward and back slashes and take last part
    								pathHtml += `<a href="${folder}">${displayName}</a> / `;
    							});
    							directoryPath.innerHTML = pathHtml;

    							// Clear search bar before navigation
    							resetSearchState();
    						
    							// Navigate to the parent directory
    							window.isFolderNavigation = true;
    							RIPE(parentDir).then(() => {
    								// After navigation completes, find and highlight the clicked item
    								highlightAndScrollToItem('[data-path]', clickedItemName);
    							});
    						});
    				}
    				// Only run default behavior if we're not handling a special search file click
    				else if (targetPath === 'root') {
    					// For root items, restore the original content (happens at resetToRoot)
    					resetToRoot(true); // null for no log message, true to run search
    				} else {
						// For non root items, restore the original content
						logPathHistory('-');
						window.isFolderNavigation = true;
						RIPE(targetPath);
					}
    			}, delay);
    		}
    	});

		// Supposed to be called navigateToFolder but changed it cuz who needs maintainability anyways
    	function RIPE(folderPath) {

    		// Cancel any ongoing batch processing
			// Supposed to be named cancelBatchProcessing but changed it cuz who needs maintainability anyways
    		nano = true;

    		// Return a Promise that resolves when navigation is complete
    		return new Promise((resolve, reject) => {
    			// Fetch the directories.json file
    			fetchDirectoryData()
    				.then(data => {
    					// Update to access directories through the new structure
    					const dirContents = data.directories[folderPath];
    					if (dirContents) {
    						// Get the container - use a more robust selector
    						const container = document.querySelector('[data-path]');

    						if (!container) {
    							console.error('Container not found for path:', targetPath);
    							reject('Container not found');
    							return;
    						}

    						// Update the data-path attribute
    						container.setAttribute('data-path', folderPath);

    						// Apply show-date/show-size classes
    						applyToggleClasses(container);

    						targetPath = folderPath;

    						// Update the directory path
    						const directoryPath = document.querySelector('.directory-path');
    						let pathHtml = '<a href="/">~</a> / ';
    						
    						pathHistory.forEach(folder => {
    							// Extract the last meaningful part of the path while preserving full folder names
    							const displayName = folder.split(/[\/\\]/).pop(); // Split by both forward and back slashes and take last part
    							pathHtml += `<a href="${folder}">${displayName}</a> / `;
    						});
    						directoryPath.innerHTML = pathHtml;

    						// Clear existing list items
    						container.innerHTML = '';

    						// Reset cancel flag for this new navigation
    						nano = false;

    						// Update batch processing with configuration
    						async function processBatch(items, startIndex, container) {
    							// Check if processing should be canceled
    							if (nano) {
    								return;
    							}
    							
    							const batch = items.slice(startIndex, startIndex + CONFIG.batchSize);
    							if (batch.length === 0) return;

    							const batchHTML = batch.map(item => `
                                <li><a href="${item.type === 'directory' ? item.path : targetPath}" 
                                    class="${item.type === 'directory' ? 'icon icon-directory' : item.icon_classes}" 
                                    title="${item.name}">
                                    <span class="name">${item.name}</span>
                                    <span class="date">${CONFIG.useFormattedDate ? item.date_formatted : item.date}</span>
                                    <span class="size">${CONFIG.useFormattedSize ? item.size_formatted : item.size}</span>
                                </a></li>`).join('');

    							container.insertAdjacentHTML('beforeend', batchHTML);

    							return new Promise(resolve => {
    								requestAnimationFrame(() => {
    									resolve(processBatch(items, startIndex + CONFIG.batchSize, container));
    								});
    							});
    						}

    						processBatch(dirContents, 0, container).then(() => {
    							// Call the search function after content is loaded
    							search();
    							// Resolve the promise when navigation is complete
    							resolve();
    						});
    					} else {
    						reject('Directory contents not found');
    					}

    				})
    		});
    	}

    	// Add a counter to track search operations
    	let searchOperationCounter = 0;

    	// Function to perform the special search
    	function performSpecialSearch(itemName, searchType = 'all') {
    		// Skip search if the search term is ".." (used for navigation)
    		if (itemName === "..") return;
    		
    		// Increment the counter for this search operation
    		const currentSearchOperation = ++searchOperationCounter;
    		
    		// If we're in a folder, filter the current view
    		if (targetPath !== 'root') {
    			filterCurrentView(itemName, searchType);
    			return;
    		}
    		
    		// If we're at root, we need to fetch all directories to search
    		return fetchDirectoryData()
    			.then(data => {
    				// Check if this search operation has been superseded by a newer one
    				if (currentSearchOperation !== searchOperationCounter) {
    					return;
    				}
    				
    				// Find all items matching the search term across all directories
    				const matchingItems = [];
    				const searchLower = itemName.toLowerCase();
    				
    				// Update to access directories through the new structure
    				const directories = data.directories || {};
    				
    				// Search through all directories in the data
    				for (const dirPath in directories) {
    					// Check again if this search operation has been superseded
    					if (currentSearchOperation !== searchOperationCounter) {
    						return;
    					}
    					
    					const dirContents = directories[dirPath];
    					
    					// Filter items that match the search term exactly and match the type if specified
    					const matches = dirContents.filter(item => {
    						// Check if item type matches the search type filter
    						if (searchType === 'folder' && item.type !== 'directory') return false;
    						if (searchType === 'file' && item.type === 'directory') return false;
    						
    						const nameLower = item.name.toLowerCase();
    						// Check for exact match or if the search term is at least 3 characters
    						// and is found as a complete word within the name
    						return nameLower === searchLower || 
    							   (searchLower.length >= 3 && 
    								new RegExp(`\\b${escapeRegExp(searchLower)}\\b`, 'i').test(nameLower));
    					});
    					
    					// Add directory path information to each match
    					matches.forEach(item => {
    						item.parentDir = dirPath;
    						matchingItems.push(item);
    					});
    				}
    				
    			// Final check before displaying results
    			if (currentSearchOperation !== searchOperationCounter) {
    				return;
    			}
    			
    			// Update the directory path to include "search"
    			const directoryPath = document.querySelector('.directory-path');
    			directoryPath.innerHTML = '<a href="/">~</a> / <a href="#search">Search Results</a> / ';
    			
    			// Display the matching items
    			return displayMatchingItems(matchingItems, currentSearchOperation);
    		})
    	}
    	
    	// Helper function to escape special characters in regex
    	function escapeRegExp(string) {
    		return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    	}

    	// Function to filter the current view based on the search term
    	function filterCurrentView(itemName, searchType = 'all') {
    		// Skip filtering if the search term is ".." (used for navigation)
    		if (itemName === "..") return;
    		
    		const container = document.querySelector('[data-path]');
    		const allItems = container.querySelectorAll('li');
    		const searchLower = itemName.toLowerCase();
    		
    		// Update the directory path to include "search"
    		const directoryPath = document.querySelector('.directory-path');
    		const targetPathHtml = directoryPath.innerHTML;
    		
    		// Only add the search link if it's not already there
    		if (!targetPathHtml.includes('<a href="#search">Search Results</a>')) {
    			// Find the last slash in the path
    			const lastSlashIndex = targetPathHtml.lastIndexOf('/');
    			if (lastSlashIndex !== -1) {
    				// Insert the search link before the last slash
    				const newPathHtml = targetPathHtml.substring(0, lastSlashIndex) + 
    									' / <a href="#search">Search Results</a>' + 
    									targetPathHtml.substring(lastSlashIndex);
    				directoryPath.innerHTML = newPathHtml;
    			}
    		}
    		
    		// Show only items that match the search term
    		allItems.forEach(item => {
    			const nameElement = item.querySelector('.name');
    			if (nameElement) {
    				// Check if item type matches the search type filter
    				const isDirectory = item.querySelector('a').classList.contains('icon-directory');
    				if (searchType === 'folder' && !isDirectory) {
    					item.style.display = 'none';
    					return;
    				}
    				if (searchType === 'file' && isDirectory) {
    					item.style.display = 'none';
    					return;
    				}
    				
    				const name = nameElement.textContent;
    				const nameLower = name.toLowerCase();
    				
    				// Check for exact match or if the search term is at least 3 characters
    				// and is found as a complete word within the name
    				const isMatch = nameLower === searchLower || 
    							   (searchLower.length >= 3 && 
    								new RegExp(`\\b${escapeRegExp(searchLower)}\\b`, 'i').test(nameLower));
    				
    				if (isMatch) {
    					item.style.display = '';
    				} else {
    					item.style.display = 'none';
    				}
    			}
    		});
    	}
    	
    	// Add a global flag to track if batch processing should be canceled
    	let nano = false;

    	// Function to display matching items from all directories
    	function displayMatchingItems(items, searchOperationId) {
    		const container = document.querySelector('[data-path]');
    		if (!container) return;
    		
    		// Reset cancel flag at the start of a new display operation
    		nano = false;
    		
    		// Clear existing content
    		container.innerHTML = '';
    		
    		// Group items by parent directory for better organization
    		const groupedItems = {};
    		items.forEach(item => {
    			if (!groupedItems[item.parentDir]) {
    				groupedItems[item.parentDir] = [];
    			}
    			groupedItems[item.parentDir].push(item);
    		});
    		
    		// Flatten the grouped items into a single array with headers
    		const processQueue = [];
    		
    		for (const dirPath in groupedItems) {
    			// Format directory path - replace backslashes with forward slashes with spaces
    			const formattedDirPath = dirPath === 'root' ? 
    				'Root Directory' : 
    				dirPath.replace(/\\/g, ' / ').replace(/\//g, '<span> / </span>');
    			
    			// Add directory header
    			processQueue.push({
    				isHeader: true,
    				dirPath: dirPath,
    				content: formattedDirPath
    			});
    			
    			// Add items from this directory
    			groupedItems[dirPath].forEach(item => {
    				processQueue.push({
    					isHeader: false,
    					item: item
    				});
    			});
    		}
    		
    		// Process items in batches
    		let currentIndex = 0;
    		
    		function processNextBatch() {
    			// Check if processing should be canceled or if this search operation is outdated
    			if (nano || searchOperationId !== searchOperationCounter) {
    				return;
    			}
    			
    			if (currentIndex >= processQueue.length) return;
    			
    			// Process just one item at a time to prevent lag
    			const queueItem = processQueue[currentIndex];
				/*
				if (queueItem.isHeader) {
    				const dirHeader = document.createElement('li');
    				dirHeader.className = 'directory-header';
    				
    				// Create an anchor element for the directory header
    				const dirLink = document.createElement('a');
    				dirLink.href = queueItem.dirPath;
    				
    				// Set the inner HTML based on the directory path
    				dirLink.innerHTML = queueItem.content === "." ? 
    					`<span>--</span>~ <span> / </span>` : 
    					`<span>--</span>~ <span> / </span>${queueItem.content}`;
    				
    				dirHeader.appendChild(dirLink);
    				container.appendChild(dirHeader);
				*/
    			if (queueItem.isHeader) {
    				const dirHeader = document.createElement('li');
    				dirHeader.className = 'directory-header';
    				dirHeader.innerHTML = queueItem.content === "." ? 
    					`~ <span> / </span>` : 
    					`~ <span> / </span>${queueItem.content}`;
    				container.appendChild(dirHeader);
    			} else {
    				const item = queueItem.item;
    				const li = document.createElement('li');
    				li.innerHTML = `
                        <a href="${item.type === 'directory' ? item.path : item.parentDir}" 
                           class="${item.type === 'directory' ? 'icon icon-directory' : item.icon_classes}" 
                           title="${item.name}">
                           <span class="name">${item.name}</span>
                           <span class="date">${CONFIG.useFormattedDate ? item.date_formatted : item.date}</span>
                           <span class="size">${CONFIG.useFormattedSize ? item.size_formatted : item.size}</span>
                        </a>
                    `;
    				container.appendChild(li);
    			}
    			
    			currentIndex++;
    			
    			// Schedule the next batch
    			return requestAnimationFrame(processNextBatch);
    		}
    		
    		// Start processing
    		return processNextBatch();
    	}
    	
    	// Function to reset to normal display
    	function resetToNormalDisplay() {
    		if (targetPath === 'root') {
    			// Restore original content for root
    			const container = document.querySelector('[data-path]');
    			container.innerHTML = originalContent;
    			applyToggleClasses(container);
    			search(); // Apply normal search if there's text in the search box
    		} else {
    			// Reload current folder
    			RIPE(targetPath);
    		}
    	}

    	// Function to reset to root directory
    	function resetToRoot(runSearch = false, fromBreadcrumb = false, fromHashChange = false, highlightItem = false) {
			
    		// Clear URL hash using pushState to avoid page jump
    		if (window.location.hash) {
    			history.pushState("", document.title, window.location.pathname + window.location.search);
    		}

    		// Reset path history
    		pathHistory = [];
    		
    		// Cancel any ongoing batch processing
    		nano = true;
			
    		// Restore root content
    		const container = document.querySelector('[data-path]');
    		container.innerHTML = originalContent;
    		container.setAttribute('data-path', 'root');
    		document.querySelector('.directory-path').innerHTML = '<a href="/">~</a> / ';
    		targetPath = 'root';
    		
    		// Apply toggle classes to the root container
    		applyToggleClasses(container);
    		
			logPathHistory(fromBreadcrumb ? '🍞' : (fromHashChange ? '#' : '-'));

    		// Optionally run search if needed
    		if (runSearch) {
    			search();
    		}

			if (highlightItem && lastClickedItemName) {
				highlightAndScrollToItem('[data-path]', lastClickedItemName, 'lastClickedItemName');
			}
    	}

		function buildPathHistory(inputPath, data, pathHistory) {
			// Split the path into components
			const pathComponents = inputPath.split(/[\/\\]/);
			
			// Build the path history by adding each component
			let targetPathSegment = '';
			pathComponents.forEach((segment) => {
				if (segment.trim() === '') return; // Skip empty segments
				
				// Build the cumulative path
				if (targetPathSegment === '') {
					targetPathSegment = segment;
				} else {
					// Use the same separator that was in the original path
					const separator = inputPath.includes('/') ? '/' : '\\';
					targetPathSegment += separator + segment;
				}
				
				// Only add valid paths that exist in our data.directories and not already in path history
				if (data.directories && data.directories[targetPathSegment] && 
				    !pathHistory.includes(targetPathSegment)) {
					pathHistory.push(targetPathSegment);
				}
			});
		}

		function resetSearchState() {
			// Clear the search input field
			searchInput.value = '';
			
			// Remove stored search text from session storage
			sessionStorage.removeItem('searchText');
			
			// Reset the special search flag
			isSpecialSearchActive = false;
		}

		// Add this function near other utility functions
		function highlightAndScrollToItem(containerSelector, itemName, resetVariable = null) {
			const container = document.querySelector(containerSelector);
			if (!container) return;
			
			setTimeout(() => {
				const items = container.querySelectorAll('li a');
				items.forEach(item => {
					if (item.getAttribute('title') === itemName) {
						item.classList.add('highlight');
						item.scrollIntoView({ behavior: 'smooth', block: 'center' });
					}
				});
				
				// Reset variable if provided
				if (resetVariable !== null) {
					window[resetVariable] = null;
				}
			}, 100);
		}

    	// Improved function to log path history with auto-expanded groups and console clearing
		function logPathHistory(action, fromHashChange = false) {
			console.clear();

			const searchInput = document.getElementById('search');
			if (
				searchInput &&
				(searchInput.value.startsWith(CONFIG.all) ||
					searchInput.value.startsWith(CONFIG.folder) ||
					searchInput.value.startsWith(CONFIG.file))
			) {
				console.log('%cRegEx detected, in special search mode', 'font-style: italic');
			}
			
			if (
				!(searchInput &&
				(searchInput.value.startsWith(CONFIG.all) ||
					searchInput.value.startsWith(CONFIG.folder) ||
					searchInput.value.startsWith(CONFIG.file)))
			) {
				console.group(`[${action}] Current path`);
				console.log('~ /');
			}

			if (pathHistory.length > 0) {
				return fetchDirectoryData().then((data) => {
					let lastDirId = '';
					
					pathHistory.forEach((path, index) => {
						const displayName = path.split(/[\/\\]/).pop();
						const segments = path.split(/[\/\\]/);
						let currentPath = '';
						let dirEntry = null;
		
						for (let i = 0; i < segments.length; i++) {
							if (i === 0) {
								currentPath = segments[0];
								dirEntry = data.directories['.']?.find((entry) => entry.path === currentPath);
							} else {
								currentPath = segments.slice(0, i + 1).join('\\');
								const parentPath = segments.slice(0, i).join('\\');
								const dirContents = data.directories[parentPath] || [];
								dirEntry = dirContents.find((entry) => entry.path === currentPath);
							}
						}
		
						const dirId = dirEntry?.directory_id || 'unknown';
						console.log(`${displayName} {#${dirId}} / `);
		
						if (index === pathHistory.length - 1) {
							lastDirId = dirId;
						}
					});
		
					console.groupEnd();
					if (!fromHashChange) appendURLHash(lastDirId);
				});
			} else {
				console.groupEnd();
				return Promise.resolve(); // Return a resolved promise when there's no path history
			}
		}
				
		function appendURLHash(directoryId) {
			if (directoryId && directoryId !== 'unknown') {
				let baseUrl = window.location.href.split('#')[0];
				window.location.href = `${baseUrl}#${directoryId}`;
			} else {
				history.pushState("", document.title, window.location.pathname + window.location.search);
			}
		}

		// Function to find path by directory ID
		async function findPathByDirectoryId(directoryId) {
			const data = await fetchDirectoryData();
			
			// Function to search recursively through directories
			function searchDirectories(directories, targetId) {
				for (const [path, entries] of Object.entries(directories)) {
					// Skip the special "." entry
					if (path === '.') {
						for (const entry of entries) {
							if (entry.directory_id === targetId) {
								return entry.path;
							}
						}
						continue;
					}
					
					// Check entries in current directory
					for (const entry of entries) {
						if (entry.directory_id === targetId) {
							return entry.path;
						}
					}
				}
				return null;
			}
			
			return searchDirectories(data.directories, directoryId);
		}

		// Function to handle initial hash navigation
		async function handleInitialHash() {

			// Check if there's a hash in the URL
			if (window.location.hash) {
				const directoryId = window.location.hash.substring(1); // Remove the # character
				try {
					// Find the path associated with this directory ID
					const path = await findPathByDirectoryId(directoryId);
					if (path) {
						// Reset path history
						pathHistory = [];
						
						// Build the path history for breadcrumb navigation
						const data = await fetchDirectoryData();
						buildPathHistory(path, data, pathHistory);
						
						// Log the navigation
						logPathHistory('#', true);

						// Navigate to the folder
						return RIPE(path, true);
					}
				} catch (error) {
					console.error('Error handling initial hash:', error);
				}
			}
			return Promise.resolve(); // Return a resolved promise if no hash navigation needed
		};

		// Function to handle hash changes during navigation
		function handleHashChange() {
			// Check if this is a normal folder navigation and return early if so
			if (window.isFolderNavigation) {
				// Reset the flag for future navigations
				window.isFolderNavigation = false;
				return;
			}

			const hash = window.location.hash;
			if (hash) {
				const directoryId = hash.substring(1); // Remove the # character
				return findPathByDirectoryId(directoryId).then(path => {
					if (path) {
						// Reset path history
						pathHistory = [];
						
						// Build the path history for breadcrumb navigation
						return fetchDirectoryData().then(data => {
							buildPathHistory(path, data, pathHistory);
							
							return logPathHistory('#', true, true).then(() => {
								// Navigate to the folder
								return RIPE(path);
							});
						}).catch(error => {
							console.error('Error building path history:', error);
						});
					}
				}).catch(error => {
					console.error('Error handling hash change:', error);
				});
			} else {
				// If there's no hash, return to root
				return resetToRoot(true, false, true);
			}
		}
		
		// Add event listener for hash changes
		window.addEventListener('hashchange', handleHashChange);
		
		logPathHistory('-');
	})