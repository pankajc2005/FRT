// Dashboard Logic
document.addEventListener('DOMContentLoaded', function() {
    initClock();
    initActivityPoll();
    initStatusPoll();
    setupSearch();
    setupModals();
    setupFileUpload();
});

// 1. Clock & Header Info
function initClock() {
    const timeEl = document.getElementById('system-time');
    if (!timeEl) return;

    function update() {
        const now = new Date();
        timeEl.textContent = now.toLocaleTimeString('en-US', { 
            hour: '2-digit', 
            minute: '2-digit',
            second: '2-digit'
        });
    }
    setInterval(update, 1000);
    update();
}

// 2. Polling for Activity (Simulated WebSocket)
function initActivityPoll() {
    const activityList = document.getElementById('activity-list');
    if (!activityList) return;

    function fetchActivity() {
        fetch('/api/recent_activity')
            .then(res => res.json())
            .then(data => {
                if (data.length === 0) return;
                
                activityList.innerHTML = ''; 
                
                data.forEach(item => {
                    const li = document.createElement('li');
                    li.className = 'activity-item';
                    li.innerHTML = `
                        <span class="activity-time">${item.time}</span>
                        <div class="activity-icon">
                            <i class="fas ${item.icon}"></i>
                        </div>
                        <div class="activity-details">
                            <strong>${item.user}</strong> ${item.action} 
                            <span class="${item.status_class}">${item.target}</span>
                        </div>
                    `;
                    activityList.appendChild(li);
                });
            })
            .catch(err => console.error('Activity poll failed', err));
    }

    // Poll every 5 seconds
    setInterval(fetchActivity, 5000);
    fetchActivity();
}

// 3. System Status Polling
function initStatusPoll() {
    function checkStatus() {
        fetch('/api/status')
            .then(res => res.json())
            .then(data => {
                updateStatusDot('camera-status', data.camera);
                updateStatusDot('model-status', data.model);
                updateStatusDot('sync-status', data.sync);
            })
            .catch(err => console.error('Status poll failed', err));
    }
    
    function updateStatusDot(id, status) {
        const el = document.getElementById(id);
        if (!el) return;
        el.className = 'status-dot'; // reset
        if (status === 'active' || status === 'ok') el.classList.add('active');
        else if (status === 'warning') el.classList.add('warning');
        else el.classList.add('danger');
    }

    setInterval(checkStatus, 10000);
}

// 4. Search Functionality
function setupSearch() {
    const searchInput = document.getElementById('dashboard-search');
    if (!searchInput) return;

    let debounceTimer;
    searchInput.addEventListener('input', (e) => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            const query = e.target.value;
            if (query.length > 2) {
                // Perform search
                console.log('Searching for:', query);
                // In a real app, this would filter the table or show a dropdown
            }
        }, 300);
    });
}

// 5. Modals
function setupModals() {
    // Generic modal closer
    document.querySelectorAll('.modal-backdrop').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.remove('active');
            }
        });
    });
}

function openCaptureModal() {
    document.getElementById('capture-modal').classList.add('active');
    startWebcamPreview();
}

function closeCaptureModal() {
    document.getElementById('capture-modal').classList.remove('active');
    stopWebcamPreview();
}

// Webcam Logic (Placeholder)
let stream = null;
function startWebcamPreview() {
    const video = document.getElementById('webcam-preview');
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        navigator.mediaDevices.getUserMedia({ video: true })
            .then(function(s) {
                stream = s;
                video.srcObject = stream;
                video.play();
            });
    }
}

function stopWebcamPreview() {
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
        stream = null;
    }
}

function capturePhoto() {
    const video = document.getElementById('webcam-preview');
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    
    canvas.toBlob(blob => {
        const formData = new FormData();
        formData.append('image', blob, 'capture.jpg');
        
        performFaceSearch(formData);
        closeCaptureModal();
    }, 'image/jpeg');
}

// 6. File Upload & Face Search
function setupFileUpload() {
    const fileInput = document.getElementById('file-upload');
    if (!fileInput) return;

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            const file = e.target.files[0];
            const formData = new FormData();
            formData.append('image', file);
            
            // Show preview
            const reader = new FileReader();
            reader.onload = function(e) {
                updateQueryPreview(e.target.result);
            }
            reader.readAsDataURL(file);
            
            performFaceSearch(formData);
        }
    });
}

function updateQueryPreview(imgSrc) {
    const container = document.querySelector('.face-preview-container');
    container.innerHTML = `<img src="${imgSrc}" style="width:100%; height:100%; object-fit:cover; border-radius: 0.5rem;">`;
}

function performFaceSearch(formData) {
    // Show loading state
    const resultsTable = document.querySelector('.dashboard-table tbody');
    resultsTable.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:2rem;">Processing image... <i class="fas fa-spinner fa-spin"></i></td></tr>';

    fetch('/api/face_search', {
        method: 'POST',
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        if (data.match) {
            // Update results table with match
            const person = data.person;
            resultsTable.innerHTML = `
                <tr>
                    <td>
                        <img src="/data/images/${person.image_filename}" 
                             style="width: 40px; height: 40px; border-radius: 50%; object-fit: cover;">
                    </td>
                    <td>
                        <div style="font-weight: 600;">${person.name}</div>
                        <div style="font-size: 0.75rem; color: #6b7280;">ID: ${person.id.substring(0,8)}</div>
                    </td>
                    <td>
                        <span class="match-score">${data.confidence}%</span>
                    </td>
                    <td>
                        <span class="risk-badge risk-high">High</span>
                    </td>
                    <td>
                        <div style="font-size: 0.85rem;">${person.submitted_gender || '-'} / ${person.predicted_age || '-'}y</div>
                    </td>
                    <td>
                        <a href="/person/${person.id}" class="btn-dashboard btn-outline" style="padding: 0.25rem 0.5rem; text-decoration:none;">
                            View
                        </a>
                    </td>
                </tr>
            `;
        } else {
            resultsTable.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:2rem; color: #9ca3af;">${data.message || 'No match found.'}</td></tr>`;
        }
    })
    .catch(err => {
        console.error('Search failed', err);
        resultsTable.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:2rem; color: red;">Error processing request.</td></tr>';
    });
}

