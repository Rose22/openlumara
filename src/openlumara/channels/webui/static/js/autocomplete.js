// =============================================================================
// Command Autocomplete System
// =============================================================================

let commandPrefix = '/';
let allCommands = {};
let autocompleteVisible = false;
let selectedIndex = -1;
let currentItems = [];
let autocompleteContainer = null;

// Initialize autocomplete on load
document.addEventListener('DOMContentLoaded', () => {
    initAutocomplete();
});

async function initAutocomplete() {
    try {
        const prefixRes = await fetch('/api/command_prefix');
        if (prefixRes.ok) {
            commandPrefix = await prefixRes.json();
        }
    } catch (e) {
        console.warn('Failed to fetch command prefix, defaulting to /', e);
    }

    try {
        const commandsRes = await fetch('/api/commands');
        if (commandsRes.ok) {
            allCommands = await commandsRes.json();
        }
    } catch (e) {
        console.warn('Failed to fetch commands', e);
    }

    // Create autocomplete container
    autocompleteContainer = document.createElement('div');
    autocompleteContainer.className = 'autocomplete-container';
    autocompleteContainer.innerHTML = `
        <div class="autocomplete-dropdown" id="autocomplete-dropdown">
            <div class="autocomplete-empty">Loading commands...</div>
        </div>
    `;
    
    // Insert above input area
    const inputArea = document.querySelector('.upload-queue-container');
    if (inputArea) {
        inputArea.style.position = 'relative';
        inputArea.parentNode.insertBefore(autocompleteContainer, inputArea);
    }

    // Event listeners (use global inputField from variables.js)
    if (inputField) {
        inputField.addEventListener('input', handleInput);
        inputField.addEventListener('keydown', handleKeydown);
    }
    document.addEventListener('click', handleClickOutside);
}

function handleInput(e) {
    const value = e.target.value;
    const trimmed = String(value.trim());

    // Check if starts with prefix
    if (!trimmed.startsWith(commandPrefix) || value.length === 0) {
        hideAutocomplete();
        return;
    }

    // Get typed text after prefix
    const typedText = trimmed.toLowerCase();
    const typedTextWithoutPrefix = trimmed.slice(commandPrefix.length).toLowerCase();

    // Filter commands
    let matchingCommands = [];

    // 1. Loop through categories (core, chats, etc.)
    for (const [category, commandsObj] of Object.entries(allCommands)) {

        // 2. Loop through the inner object (the actual commands)
        // We use Object.entries because commandsObj is { "/cmd": "desc" }
        for (const [cmdName, cmdDesc] of Object.entries(commandsObj)) {

            const nameLower = cmdName.toLowerCase();
            const descLower = (cmdDesc || '').toLowerCase();

            if (nameLower.startsWith(typedText) || descLower.includes(typedTextWithoutPrefix)) {
                // 3. Push a standardized object so the rest of your code works!
                matchingCommands.push({
                    name: cmdName,
                    description: cmdDesc,
                    category: category
                });
            }
        }
    }

    if (matchingCommands.length === 0) {
        hideAutocomplete();
        return;
    }

    showAutocomplete(matchingCommands, typedTextWithoutPrefix);
}


function showAutocomplete(items, typedText) {
    currentItems = items;
    selectedIndex = -1;
    
    const dropdown = document.getElementById('autocomplete-dropdown');
    
    // Group by category
    const grouped = {};
    for (const item of items) {
        if (!grouped[item.category]) grouped[item.category] = [];
        grouped[item.category].push(item);
    }

    // Build HTML
    let html = '';
    for (const [category, cmds] of Object.entries(grouped)) {
        html += `<div class="autocomplete-category">${category}</div>`;
        for (const cmd of cmds) {
            const escapedName = escapeHtml(cmd.name);
            const escapedDesc = escapeHtml(cmd.description || '');
            const highlightedName = highlightMatch(escapedName, typedText);
            html += `
                <div class="autocomplete-item" data-index="${items.indexOf(cmd)}" data-name="${escapedName}">
                    <span class="cmd-name">${highlightedName}</span>
                    <span class="cmd-desc">${escapedDesc}</span>
                </div>
            `;
        }
    }

    dropdown.innerHTML = html;
    dropdown.classList.add('show');
    autocompleteVisible = true;
    
    // Focus first item after render
    requestAnimationFrame(() => {
        const firstItem = dropdown.querySelector('.autocomplete-item');
        if (firstItem) {
            selectedIndex = parseInt(firstItem.dataset.index);
            selectItem(selectedIndex);
        }
    });
}

function hideAutocomplete() {
    const dropdown = document.getElementById('autocomplete-dropdown');
    if (dropdown) {
        dropdown.classList.remove('show');
    }
    autocompleteVisible = false;
    selectedIndex = -1;
    currentItems = [];
}

function handleKeydown(e) {
    if (!autocompleteVisible) return;

    const dropdown = document.getElementById('autocomplete-dropdown');
    if (!dropdown) return;

    const items = dropdown.querySelectorAll('.autocomplete-item');
    if (items.length === 0) return;

    if (e.key === 'ArrowDown') {
        e.preventDefault();
        selectedIndex = (selectedIndex + 1) % items.length;
        selectItem(selectedIndex);
        scrollToSelected(items[selectedIndex]);
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        selectedIndex = (selectedIndex - 1 + items.length) % items.length;
        selectItem(selectedIndex);
        scrollToSelected(items[selectedIndex]);
    } else if (e.key === 'Enter') {
        e.preventDefault();
        e.stopPropagation();
        if (selectedIndex >= 0 && selectedIndex < currentItems.length) {
            selectCommand(currentItems[selectedIndex]);
        }
    } else if (e.key === 'Escape') {
        e.preventDefault();
        hideAutocomplete();
    }
}

function selectItem(index) {
    const dropdown = document.getElementById('autocomplete-dropdown');
    if (!dropdown) return;
    
    const items = dropdown.querySelectorAll('.autocomplete-item');
    items.forEach(item => item.classList.remove('selected'));
    
    if (index >= 0 && index < items.length) {
        selectedIndex = index;
        items[index].classList.add('selected');
    }
}

function scrollToSelected(element) {
    if (!element) return;
    const container = element.parentElement;
    const itemTop = element.offsetTop;
    const itemBottom = itemTop + element.offsetHeight;
    const containerTop = container.scrollTop;
    const containerBottom = containerTop + container.clientHeight;
    
    if (itemTop < containerTop) {
        container.scrollTop = itemTop;
    } else if (itemBottom > containerBottom) {
        container.scrollTop = itemBottom - container.clientHeight;
    }
}

function selectCommand(cmd) {
    if (!inputField) return;
    
    const currentValue = inputField.value;
    const prefixIndex = currentValue.indexOf(commandPrefix);
    const afterPrefix = currentValue.slice(prefixIndex + commandPrefix.length);
    
    // Replace everything after prefix with command name + space
    const newValue = cmd.name + ' ';
    inputField.value = newValue;
    inputField.focus();
    
    hideAutocomplete();
    autoResize(inputField);
}

function handleClickOutside(e) {
    if (autocompleteVisible && autocompleteContainer && !autocompleteContainer.contains(e.target) && e.target !== inputField) {
        hideAutocomplete();
    }
}

function highlightMatch(text, match) {
    if (!match) return text;
    // escapeRegex is defined in utils.js
    const regex = new RegExp(`(${escapeRegex(match)})`, 'gi');
    return text.replace(regex, '<mark>$1</mark>');
}
