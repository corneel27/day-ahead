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

// Format help text with support for line breaks, lists, bold, and italic
function formatHelpText(text) {
  // Convert newlines to <br>
  let formatted = text.replace(/\n/g, '<br>');
  
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
  
  // Position tooltip
  const rect = element.getBoundingClientRect();
  tooltip.style.top = `${rect.bottom + window.scrollY + 5}px`;
  tooltip.style.left = `${rect.left + window.scrollX}px`;
  
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
