/**
 * Home Assistant Entity Search Module
 * Provides autocomplete and search functionality for HA entities
 */

class HAEntitySearch {
  constructor() {
    this.entities = null;
    this.cacheTimeout = 5 * 60 * 1000; // 5 minutes
    this.lastFetch = null;
    this.searchDebounceTimer = null;
    this.searchDebounceDelay = 300; // 300ms debounce
  }

  /**
   * Fetch all entities from Home Assistant via backend proxy
   */
  async fetchEntities(forceRefresh = false) {
    try {
      const now = Date.now();
      
      // Use cached data if available and fresh
      if (!forceRefresh && this.entities && this.lastFetch && 
          (now - this.lastFetch) < this.cacheTimeout) {
        return this.entities;
      }

      console.log('Fetching Home Assistant entities...');
      const response = await fetch('/api/ha/entities');
      
      console.log('Response status:', response.status);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('Error response:', errorText);
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }
      
      const data = await response.json();
      
      if (data.error) {
        console.error('API returned error:', data.error);
        throw new Error(data.error);
      }
      
      this.entities = data;
      this.lastFetch = now;
      
      console.log(`Loaded ${this.entities.length} Home Assistant entities`);
      return this.entities;
    } catch (error) {
      console.error('Error fetching HA entities:', error);
      console.error('Error details:', {
        message: error.message,
        stack: error.stack
      });
      throw error;
    }
  }

  /**
   * Search entities by domain and/or pattern
   * @param {string} domain - Entity domain (e.g., 'sensor', 'binary_sensor')
   * @param {string} pattern - Search pattern
   */
  async searchEntities(domain = '', pattern = '') {
    try {
      const params = new URLSearchParams();
      if (domain) params.append('domain', domain);
      if (pattern) params.append('pattern', pattern);
      
      const url = `/api/ha/entities/search?${params}`;
      console.log('Searching entities:', url);
      
      const response = await fetch(url);
      
      console.log('Search response status:', response.status);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('Search error response:', errorText);
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }
      
      const data = await response.json();
      
      if (data.error) {
        console.error('Search API returned error:', data.error);
        throw new Error(data.error);
      }
      
      console.log(`Found ${data.length} matching entities`);
      return data;
    } catch (error) {
      console.error('Error searching HA entities:', error);
      console.error('Search error details:', {
        message: error.message,
        domain: domain,
        pattern: pattern
      });
      throw error;
    }
  }

  /**
   * Filter entities by domain from cached data
   */
  filterByDomain(domain) {
    if (!this.entities) return [];
    return this.entities.filter(e => e.domain === domain);
  }

  /**
   * Create autocomplete dropdown for an input field
   * @param {HTMLInputElement} inputElement - The input field
   * @param {string} domain - Optional: filter by domain
   * @param {object} options - Additional options
   */
  attachAutocomplete(inputElement, domain = '', options = {}) {
    if (!inputElement) {
      console.warn('Cannot attach autocomplete to null element');
      return;
    }

    // Default options
    const config = {
      minChars: 2,
      maxResults: 50,
      placeholder: 'Type to search entities...',
      ...options
    };

    // Check if already wrapped
    if (inputElement.parentElement?.classList.contains('entity-autocomplete-wrapper')) {
      console.warn('Autocomplete already attached to this element');
      return;
    }

    const wrapper = document.createElement('div');
    wrapper.className = 'entity-autocomplete-wrapper';
    
    const dropdown = document.createElement('div');
    dropdown.className = 'entity-autocomplete-dropdown';
    
    // Wrap input element
    inputElement.parentNode.insertBefore(wrapper, inputElement);
    wrapper.appendChild(inputElement);
    wrapper.appendChild(dropdown);
    
    // Add search icon
    const searchIcon = document.createElement('span');
    searchIcon.className = 'material-icons entity-search-icon';
    searchIcon.textContent = 'search';
    searchIcon.title = 'Search Home Assistant entities';
    wrapper.appendChild(searchIcon);
    
    let currentFocus = -1;
    
    // Input event handler with debouncing
    inputElement.addEventListener('input', (e) => {
      const value = e.target.value;
      
      // Clear previous timer
      if (this.searchDebounceTimer) {
        clearTimeout(this.searchDebounceTimer);
      }
      
      dropdown.innerHTML = '';
      currentFocus = -1;
      
      if (value.length < config.minChars) {
        dropdown.style.display = 'none';
        return;
      }
      
      // Show loading state
      const loadingDiv = document.createElement('div');
      loadingDiv.className = 'entity-search-loading';
      loadingDiv.textContent = 'Searching';
      dropdown.appendChild(loadingDiv);
      dropdown.style.display = 'block';
      
      // Debounce search
      this.searchDebounceTimer = setTimeout(async () => {
        try {
          const results = await this.searchEntities(domain, value);
          
          dropdown.innerHTML = '';
          
          if (results.length === 0) {
            const noResultsDiv = document.createElement('div');
            noResultsDiv.className = 'entity-no-results';
            noResultsDiv.textContent = 'No entities found';
            dropdown.appendChild(noResultsDiv);
            return;
          }
          
          // Limit results
          const limitedResults = results.slice(0, config.maxResults);
          
          limitedResults.forEach((entity, index) => {
            const item = document.createElement('div');
            item.className = 'entity-autocomplete-item';
            item.dataset.entityId = entity.entity_id;
            
            // Create entity display
            const entityId = document.createElement('div');
            entityId.className = 'entity-id';
            entityId.textContent = entity.entity_id;
            
            const friendlyName = document.createElement('div');
            friendlyName.className = 'entity-friendly-name';
            friendlyName.textContent = entity.friendly_name;
            
            item.appendChild(entityId);
            item.appendChild(friendlyName);
            
            // Add state and unit if available
            if (entity.state && entity.state !== 'unknown' && entity.state !== 'unavailable') {
              const stateInfo = document.createElement('div');
              stateInfo.className = 'entity-state-info';
              stateInfo.textContent = entity.unit ? 
                `${entity.state} ${entity.unit}` : entity.state;
              item.appendChild(stateInfo);
            }
            
            // Mouse events
            item.addEventListener('mouseenter', () => {
              this.removeActive(dropdown);
              item.classList.add('active');
              currentFocus = index;
            });
            
            item.addEventListener('click', () => {
              inputElement.value = entity.entity_id;
              dropdown.style.display = 'none';
              inputElement.dispatchEvent(new Event('change', { bubbles: true }));
              inputElement.focus();
            });
            
            dropdown.appendChild(item);
          });
          
          // Add result count footer
          if (results.length > config.maxResults) {
            const footer = document.createElement('div');
            footer.className = 'entity-search-footer';
            footer.textContent = `Showing ${config.maxResults} of ${results.length} results. Type more to refine.`;
            dropdown.appendChild(footer);
          }
          
        } catch (error) {
          console.error('Autocomplete error:', error);
          dropdown.innerHTML = '';
          const errorDiv = document.createElement('div');
          errorDiv.className = 'entity-search-error';
          errorDiv.textContent = 'Error loading entities. Check Home Assistant connection.';
          dropdown.appendChild(errorDiv);
        }
      }, this.searchDebounceDelay);
    });
    
    // Keyboard navigation
    inputElement.addEventListener('keydown', (e) => {
      const items = Array.from(dropdown.querySelectorAll('.entity-autocomplete-item'));
      if (items.length === 0) return;
      
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        currentFocus++;
        if (currentFocus >= items.length) currentFocus = 0;
        this.addActive(dropdown, items, currentFocus);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        currentFocus--;
        if (currentFocus < 0) currentFocus = items.length - 1;
        this.addActive(dropdown, items, currentFocus);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (currentFocus > -1 && items[currentFocus]) {
          items[currentFocus].click();
        }
      } else if (e.key === 'Escape') {
        dropdown.style.display = 'none';
        currentFocus = -1;
      }
    });
    
    // Focus event - show hint
    inputElement.addEventListener('focus', () => {
      const value = inputElement.value;
      if (value.length >= config.minChars && dropdown.children.length > 0) {
        dropdown.style.display = 'block';
      }
    });
    
    // Close on click outside
    document.addEventListener('click', (e) => {
      if (!wrapper.contains(e.target)) {
        dropdown.style.display = 'none';
        currentFocus = -1;
      }
    });
  }

  /**
   * Helper method to add active class to item
   */
  addActive(dropdown, items, index) {
    this.removeActive(dropdown);
    if (items[index]) {
      items[index].classList.add('active');
      items[index].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }

  /**
   * Helper method to remove active class from all items
   */
  removeActive(dropdown) {
    const items = dropdown.querySelectorAll('.entity-autocomplete-item');
    items.forEach(item => {
      item.classList.remove('active');
    });
  }

  /**
   * Attach autocomplete to multiple fields based on domain mapping
   * @param {Object} fieldDomainMap - Map of field IDs to domains
   * Example: { 'battery-entity-level': 'sensor', 'solar-pv-switch': 'input_boolean' }
   */
  attachMultiple(fieldDomainMap) {
    Object.entries(fieldDomainMap).forEach(([fieldId, domain]) => {
      const element = document.getElementById(fieldId);
      if (element) {
        this.attachAutocomplete(element, domain);
      } else {
        console.warn(`Element with ID '${fieldId}' not found`);
      }
    });
  }

  /**
   * Pre-fetch entities on page load for faster autocomplete
   */
  async prefetch() {
    try {
      await this.fetchEntities();
      return true;
    } catch (error) {
      console.warn('Could not pre-fetch HA entities:', error);
      return false;
    }
  }
}

// Export singleton instance
const haEntitySearch = new HAEntitySearch();

// Auto-initialize on page load
if (typeof window !== 'undefined') {
  window.haEntitySearch = haEntitySearch;
}
