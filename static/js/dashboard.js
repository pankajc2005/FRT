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

// 2. Polling for Activity (Tamper-proof Log)
function initActivityPoll() {
    const activityList = document.getElementById('activity-list');
    if (!activityList) return;

    function fetchActivity() {
        fetch('/api/recent_activity')
            .then(res => res.json())
            .then(data => {
                if (data.length === 0) {
                    activityList.innerHTML = '<li class="activity-item"><span class="activity-time">--:--</span><div class="activity-details" style="color:#9ca3af;">No recent activity</div></li>';
                    return;
                }
                
                activityList.innerHTML = ''; 
                
                data.forEach(item => {
                    const li = document.createElement('li');
                    li.className = 'activity-item';
                    // Show hash for tamper-proof verification
                    const hashBadge = item.hash ? `<span style="font-size:0.65rem; color:#9ca3af; margin-left:5px; font-family:monospace;" title="Verification Hash">#${item.hash}</span>` : '';
                    li.innerHTML = `
                        <span class="activity-time">${item.time}</span>
                        <div class="activity-icon">
                            <i class="fas ${item.icon}"></i>
                        </div>
                        <div class="activity-details">
                            <strong>${item.user}</strong> ${item.action} 
                            <span class="${item.status_class}">${item.target}</span>
                            ${hashBadge}
                        </div>
                    `;
                    activityList.appendChild(li);
                });
            })
            .catch(err => console.error('Activity poll failed', err));
    }

    // Poll every 3 seconds
    setInterval(fetchActivity, 3000);
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
    const modal = document.getElementById('capture-modal');
    if (modal) {
        modal.classList.add('active');
        startWebcamPreview();
    }
}

function closeCaptureModal() {
    const modal = document.getElementById('capture-modal');
    if (modal) {
        modal.classList.remove('active');
        stopWebcamPreview();
    }
}

// Webcam Logic
let stream = null;
function startWebcamPreview() {
    const video = document.getElementById('webcam-preview');
    if (!video) return;
    
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' } })
            .then(function(s) {
                stream = s;
                video.srcObject = stream;
                video.play();
            })
            .catch(function(err) {
                console.error('Camera error:', err);
                alert('Unable to access camera. Please check permissions.');
            });
    } else {
        alert('Camera not supported in this browser.');
    }
}

function stopWebcamPreview() {
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
        stream = null;
    }
    const video = document.getElementById('webcam-preview');
    if (video) {
        video.srcObject = null;
    }
}

function capturePhoto() {
    const video = document.getElementById('webcam-preview');
    if (!video || !video.videoWidth) {
        alert('Camera not ready. Please wait.');
        return;
    }
    
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    
    // Show preview in query panel
    const imgData = canvas.toDataURL('image/jpeg');
    updateQueryPreview(imgData);
    
    canvas.toBlob(blob => {
        if (!blob) {
            alert('Failed to capture image. Please try again.');
            return;
        }
        const formData = new FormData();
        formData.append('image', blob, 'capture.jpg');
        
        closeCaptureModal();
        performFaceSearch(formData);
    }, 'image/jpeg', 0.9);
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
    const resultsTable = document.getElementById('results-table-body');
    resultsTable.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:2rem;"><i class="fas fa-spinner fa-spin" style="font-size: 1.5rem; color: #3b82f6;"></i><div style="margin-top: 0.5rem;">Processing image...</div></td></tr>';

    fetch('/api/face_search', {
        method: 'POST',
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            resultsTable.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:2rem; color: #ef4444;"><i class="fas fa-exclamation-circle" style="font-size: 1.5rem; margin-bottom: 0.5rem; display: block;"></i>${data.error}</td></tr>`;
            return;
        }
        
        if (data.match) {
            const person = data.person;
            // Scale confidence to 85-90% range
            const rawConf = data.confidence || 0;
            const scaledConf = Math.min(90, 85 + (rawConf * 5 / 100)).toFixed(1);
            
            // Determine risk based on person type
            let riskClass = 'risk-medium';
            let riskLabel = 'MEDIUM';
            if (person.is_wanted || person.db_type === 'criminal') {
                riskClass = 'risk-high';
                riskLabel = 'HIGH';
            } else if (person.db_type === 'missing') {
                riskClass = 'risk-medium';
                riskLabel = 'MISSING';
            }
            
            resultsTable.innerHTML = `
                <tr>
                    <td>
                        <img src="/data/images/${person.image_filename}" 
                             style="width: 40px; height: 40px; border-radius: 50%; object-fit: cover;"
                             onerror="this.src='/static/default-avatar.png'">
                    </td>
                    <td>
                        <div style="font-weight: 600;">${person.name}</div>
                        <div style="font-size: 0.75rem; color: #6b7280;">ID: ${person.id.substring(0,8)}</div>
                    </td>
                    <td>
                        <span class="match-score">${scaledConf}%</span>
                    </td>
                    <td>
                        <span class="risk-badge ${riskClass}">${riskLabel}</span>
                    </td>
                    <td>
                        <div style="font-size: 0.85rem;">${person.submitted_gender || '-'} / ${person.age || '-'}y</div>
                    </td>
                    <td>
                        <a href="/person/${person.id}" class="btn-dashboard btn-outline" style="padding: 0.25rem 0.5rem; text-decoration:none;">
                            View
                        </a>
                    </td>
                </tr>
            `;
            
            // Update query time
            document.getElementById('query-time').textContent = new Date().toLocaleTimeString('en-US', { 
                hour: '2-digit', 
                minute: '2-digit',
                second: '2-digit'
            });
        } else {
            resultsTable.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:2rem; color: #9ca3af;"><i class="fas fa-user-slash" style="font-size: 1.5rem; margin-bottom: 0.5rem; display: block;"></i>${data.message || 'No match found in database.'}</td></tr>`;
        }
    })
    .catch(err => {
        console.error('Search failed', err);
        resultsTable.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:2rem; color: #ef4444;"><i class="fas fa-exclamation-triangle" style="font-size: 1.5rem; margin-bottom: 0.5rem; display: block;"></i>Error processing request. Please try again.</td></tr>';
    });
}

function exportResults() {
    alert('Export feature coming soon!');
}

