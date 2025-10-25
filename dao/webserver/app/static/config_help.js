// Help system for configuration fields
let helpData = {};

// Load help data
async function loadHelpData() {
  try {
    const response = await fetch('/static/config_help.json');
    helpData = await response.json();
  } catch (error) {
    console.error('Failed to load help data:', error);
  }
}

// Get help text for a specific field
function getHelpText(category, field) {
  if (helpData[category] && helpData[category][field]) {
    return helpData[category][field];
  }
  return 'No help available for this field yet. Please check the documentation.';
}

// Format help text with support for line breaks, lists, bold, italic, and inline code
function formatHelpText(text) {
  // First, protect inline code (text between backticks) from other formatting
  const codeBlocks = [];
  let formatted = text.replace(/`([^`]+)`/g, (match, code) => {
    const index = codeBlocks.length;
    codeBlocks.push(code);
    return `\x00CODEBLOCK${index}\x00`;
  });
  
  // Convert newlines to <br>
  formatted = formatted.replace(/\n/g, '<br>');
  
  // Convert bullet points (lines starting with • or -) to list items
  formatted = formatted.replace(/^[•\-]\s+(.+?)(<br>|$)/gm, '<li>$1</li>');
  
  // Wrap consecutive <li> items in <ul>
  formatted = formatted.replace(/(<li>.*?<\/li>)+/g, match => {
    return '<ul>' + match + '</ul>';
  });
  
  // Convert **text** to bold
  formatted = formatted.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  
  // Convert *text* or _text_ to italic
  formatted = formatted.replace(/\*(.+?)\*|_(.+?)_/g, '<em>$1$2</em>');
  
  // Restore inline code blocks with <code> tags
  formatted = formatted.replace(/\x00CODEBLOCK(\d+)\x00/g, (match, index) => {
    return '<code>' + codeBlocks[parseInt(index)] + '</code>';
  });
  
  return formatted;
}

// Create help icon
function createHelpIcon(category, field) {
  const icon = document.createElement('span');
  icon.className = 'help-icon material-icons';
  icon.textContent = 'help_outline';
  icon.title = getHelpText(category, field);
  icon.onclick = (e) => {
    e.stopPropagation();
    showHelpTooltip(e.target, category, field);
  };
  return icon;
}

// Show help tooltip
function showHelpTooltip(element, category, field) {
  // Remove any existing tooltips
  const existing = document.querySelectorAll('.help-tooltip');
  existing.forEach(t => t.remove());
  
  const tooltip = document.createElement('div');
  tooltip.className = 'help-tooltip';
  tooltip.innerHTML = `
    <div class="help-tooltip-header">
      <span class="material-icons">help</span>
      <span>${field.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</span>
      <span class="help-tooltip-close material-icons">close</span>
    </div>
    <div class="help-tooltip-content">
      ${formatHelpText(getHelpText(category, field))}
    </div>
  `;
  
  document.body.appendChild(tooltip);
  
  // Position tooltip with viewport boundary checking
  const rect = element.getBoundingClientRect();
  const tooltipRect = tooltip.getBoundingClientRect();
  const viewportHeight = window.innerHeight;
  const viewportWidth = window.innerWidth;
  
  // Calculate initial position (below the element)
  let top = rect.bottom + window.scrollY + 5;
  let left = rect.left + window.scrollX;
  
  // Check if tooltip would go below viewport
  if (rect.bottom + tooltipRect.height + 5 > viewportHeight) {
    // Position above the element instead
    top = rect.top + window.scrollY - tooltipRect.height - 5;
    
    // If it still doesn't fit above, position at the top of viewport
    if (top < window.scrollY) {
      top = window.scrollY + 10;
    }
  }
  
  // Check if tooltip would go beyond right edge of viewport
  if (left + tooltipRect.width > viewportWidth) {
    left = viewportWidth - tooltipRect.width - 10;
  }
  
  // Check if tooltip would go beyond left edge of viewport
  if (left < window.scrollX) {
    left = window.scrollX + 10;
  }
  
  tooltip.style.top = `${top}px`;
  tooltip.style.left = `${left}px`;
  
  // Close button
  tooltip.querySelector('.help-tooltip-close').onclick = () => {
    tooltip.remove();
  };
  
  // Close on click outside
  setTimeout(() => {
    document.addEventListener('click', function closeTooltip(e) {
      if (!tooltip.contains(e.target) && e.target !== element) {
        tooltip.remove();
        document.removeEventListener('click', closeTooltip);
      }
    });
  }, 100);
}

// Add help icons to all form groups
function initializeHelp() {
  document.querySelectorAll('[data-help-category][data-help-field]').forEach(label => {
    const category = label.dataset.helpCategory;
    const field = label.dataset.helpField;
    
    if (!label.querySelector('.help-icon')) {
      const helpIcon = createHelpIcon(category, field);
      label.appendChild(helpIcon);
    }
  });
}

// Initialize help system when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', async () => {
    await loadHelpData();
    initializeHelp();
  });
} else {
  loadHelpData().then(initializeHelp);
}
