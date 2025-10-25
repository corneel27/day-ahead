// Download and Upload functionality for configuration files

// Get current active tab (options or secrets)
function getCurrentTab() {
  const activeTab = document.querySelector('.tab-button.chosen');
  return activeTab ? activeTab.dataset.tab : 'options';
}

// Download JSON file
function downloadJSON() {
  const currentTab = getCurrentTab();
  const filename = `${currentTab}.json`;
  
  // Get current JSON data from the editor
  fetch(`/api/settings/${filename}`)
    .then(response => response.json())
    .then(data => {
      const jsonStr = JSON.stringify(data, null, 2);
      const blob = new Blob([jsonStr], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      
      showMessage(`Downloaded ${filename}`, 'success');
    })
    .catch(error => {
      console.error('Download error:', error);
      showMessage('Failed to download file', 'error');
    });
}

// Show upload modal
function showUploadModal() {
  const modal = document.getElementById('upload-modal');
  modal.style.display = 'flex';
  
  // Reset modal state
  document.getElementById('file-preview').style.display = 'none';
  document.getElementById('file-name').textContent = '';
  document.getElementById('json-paste-area').value = '';
  
  // Set first tab as active
  document.querySelectorAll('.upload-tab-btn').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.upload-tab-content').forEach(content => content.classList.remove('active'));
  document.querySelector('[data-upload-tab="file"]').classList.add('active');
  document.getElementById('upload-tab-file').classList.add('active');
}

// Hide upload modal
function hideUploadModal() {
  const modal = document.getElementById('upload-modal');
  modal.style.display = 'none';
}

// Handle file selection
function handleFileSelect(file) {
  if (!file) return;
  
  if (!file.name.endsWith('.json')) {
    showMessage('Please select a JSON file', 'error');
    return;
  }
  
  const reader = new FileReader();
  reader.onload = function(e) {
    try {
      const jsonData = JSON.parse(e.target.result);
      document.getElementById('file-preview').style.display = 'block';
      document.getElementById('file-name').textContent = file.name;
      
      // Store the parsed data for upload
      window.uploadedJSON = jsonData;
    } catch (error) {
      showMessage('Invalid JSON file', 'error');
      console.error('JSON parse error:', error);
    }
  };
  reader.readAsText(file);
}

// Upload and apply JSON
function uploadAndApply() {
  const currentTab = getCurrentTab();
  const activeUploadTab = document.querySelector('.upload-tab-btn.active').dataset.uploadTab;
  
  let jsonData;
  
  if (activeUploadTab === 'file') {
    jsonData = window.uploadedJSON;
    if (!jsonData) {
      showMessage('Please select a file first', 'error');
      return;
    }
  } else {
    // Paste tab
    const jsonText = document.getElementById('json-paste-area').value.trim();
    if (!jsonText) {
      showMessage('Please paste JSON content', 'error');
      return;
    }
    
    try {
      jsonData = JSON.parse(jsonText);
    } catch (error) {
      showMessage('Invalid JSON format', 'error');
      console.error('JSON parse error:', error);
      return;
    }
  }
  
  // Upload to server
  const filename = `${currentTab}.json`;
  fetch(`/api/settings/${filename}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(jsonData)
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      showMessage(`${filename} uploaded and saved successfully`, 'success');
      hideUploadModal();
      
      // Reload the page to show the new configuration
      setTimeout(() => {
        location.reload();
      }, 1000);
    } else {
      showMessage(data.error || 'Failed to upload configuration', 'error');
    }
  })
  .catch(error => {
    console.error('Upload error:', error);
    showMessage('Failed to upload configuration', 'error');
  });
}

// Show message
function showMessage(message, type) {
  const messageArea = document.getElementById('message-area');
  messageArea.textContent = message;
  messageArea.className = `message ${type}`;
  messageArea.style.display = 'block';
  
  setTimeout(() => {
    messageArea.style.display = 'none';
  }, 5000);
}

// Initialize upload/download functionality
function initializeUploadDownload() {
  // Download button
  const btnDownload = document.getElementById('btn-download');
  if (btnDownload) {
    btnDownload.addEventListener('click', downloadJSON);
  }
  
  // Upload button
  const btnUpload = document.getElementById('btn-upload');
  if (btnUpload) {
    btnUpload.addEventListener('click', showUploadModal);
  }
  
  // Modal close button
  const modalClose = document.querySelector('.modal-close');
  if (modalClose) {
    modalClose.addEventListener('click', hideUploadModal);
  }
  
  // Modal cancel button
  const btnUploadCancel = document.getElementById('btn-upload-cancel');
  if (btnUploadCancel) {
    btnUploadCancel.addEventListener('click', hideUploadModal);
  }
  
  // Modal confirm button
  const btnUploadConfirm = document.getElementById('btn-upload-confirm');
  if (btnUploadConfirm) {
    btnUploadConfirm.addEventListener('click', uploadAndApply);
  }
  
  // Close modal on outside click
  const modal = document.getElementById('upload-modal');
  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        hideUploadModal();
      }
    });
  }
  
  // Upload tab switching
  document.querySelectorAll('.upload-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const tabName = btn.dataset.uploadTab;
      
      // Update tab buttons
      document.querySelectorAll('.upload-tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      
      // Update tab content
      document.querySelectorAll('.upload-tab-content').forEach(c => c.classList.remove('active'));
      document.getElementById(`upload-tab-${tabName}`).classList.add('active');
    });
  });
  
  // File input handling
  const modalFileInput = document.getElementById('modal-file-input');
  if (modalFileInput) {
    modalFileInput.addEventListener('change', (e) => {
      if (e.target.files.length > 0) {
        handleFileSelect(e.target.files[0]);
      }
    });
  }
  
  // Browse button
  const btnBrowseFile = document.getElementById('btn-browse-file');
  if (btnBrowseFile) {
    btnBrowseFile.addEventListener('click', () => {
      modalFileInput.click();
    });
  }
  
  // Drag and drop
  const dropZone = document.getElementById('drop-zone');
  if (dropZone) {
    dropZone.addEventListener('click', () => {
      modalFileInput.click();
    });
    
    dropZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropZone.classList.add('drag-over');
    });
    
    dropZone.addEventListener('dragleave', () => {
      dropZone.classList.remove('drag-over');
    });
    
    dropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropZone.classList.remove('drag-over');
      
      if (e.dataTransfer.files.length > 0) {
        handleFileSelect(e.dataTransfer.files[0]);
      }
    });
  }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeUploadDownload);
} else {
  initializeUploadDownload();
}
