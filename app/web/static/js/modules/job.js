export const createJobModule = (context) => ({
    jobs: [],
    selectedJob: null,
    editingJob: null,
    newJob: { prompt: '', duration: '5', aspect_ratio: '16:9', quantity: 1, image_path: null },
    uploadingImage: false,
    selectedIds: [],

    async fetchJobs() {
        let url = `/api/jobs/?category=${this.currentTab === 'history' ? 'history' : 'active'}`;
        const res = await fetch(url);
        this.jobs = await res.json();
        if (this.selectedJob) {
            const updated = this.jobs.find(j => j.id === this.selectedJob.id);
            if (updated) this.selectedJob = updated;
        }
    },

    async addJob() {
        const count = parseInt(this.newJob.quantity) || 1;
        for (let i = 0; i < count; i++) {
            await fetch('/api/jobs/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    prompt: this.newJob.prompt,
                    duration: this.newJob.duration,
                    aspect_ratio: this.newJob.aspect_ratio,
                    image_path: this.newJob.image_path
                })
            });
        }
        this.showAddJobModal = false;
        this.newJob = { prompt: '', duration: '5', aspect_ratio: '16:9', quantity: 1, image_path: null };
        this.fetchJobs();
        this.currentTab = 'jobs';
    },

    async updateJob() {
        if (!this.editingJob) return;
        await fetch(`/api/jobs/${this.editingJob.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(this.editingJob)
        });
        this.editingJob = null;
        this.fetchJobs();
        this.showToast('Job updated', 'success');
    },

    openEditModal(job) {
        this.editingJob = JSON.parse(JSON.stringify(job));
    },

    async deleteJob(id) {
        if (!confirm('Are you sure you want to delete this job?')) return;
        try {
            const res = await fetch(`/api/jobs/${id}`, { method: 'DELETE' });
            if (res.ok) {
                this.fetchJobs();
                if (this.selectedJob?.id === id) this.selectedJob = null;
                this.showToast('Job deleted', 'success');
            } else {
                this.showToast('Delete failed', 'error');
            }
        } catch (e) {
            console.error(e);
            this.showToast('Delete error', 'error');
        }
    },

    async duplicateJob(job) {
        try {
            await fetch('/api/jobs/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    prompt: job.prompt,
                    duration: job.duration || 5,
                    aspect_ratio: job.aspect_ratio || "16:9",
                    image_path: job.image_path || null
                })
            });
            this.showToast("Job duplicated!", "success");
            this.fetchJobs();
        } catch (e) { this.showToast("Failed to duplicate", "error"); }
    },

    async batchAction(action, ids = null) {
        const targetIds = ids || this.selectedIds;
        if (targetIds.length === 0) return;
        if (action !== 'start_selected' && !ids && !confirm(`Perform '${action}'?`)) return;
        const res = await fetch('/api/jobs/bulk_action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action, job_ids: targetIds })
        });
        if (res.ok) { this.selectedIds = []; this.fetchJobs(); }
        else this.showToast('Batch action failed', 'error');
    },

    async handleFileUpload(event) {
        const file = event.target.files[0];
        if (!file) return;
        this.uploadingImage = true;
        const formData = new FormData();
        formData.append('file', file);
        try {
            const res = await fetch('/api/jobs/upload', { method: 'POST', body: formData });
            if (res.ok) {
                const data = await res.json();
                this.newJob.image_path = data.path;
                this.showToast('Image uploaded', 'success');
            }
        } catch (e) { this.showToast('Upload error', 'error'); }
        finally { this.uploadingImage = false; }
    },

    async retryTask(jobId, taskType) {
        console.log("retryTask", jobId, taskType);
        if (taskType === 'generate') {
            if (confirm('Retry Generate will restart the entire job (deducting new credits). Continue?')) {
                this.retryJob(jobId);
            }
        } else if (taskType === 'download' || taskType === 'poll') {
            await fetch('/api/jobs/bulk_action', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    action: 'retry_download_selected',
                    job_ids: [jobId]
                })
            });
            this.fetchJobs();
        }
    },

    async retryJob(id) {
        const res = await fetch(`/api/jobs/${id}/retry`, { method: 'POST' });
        if (!res.ok) {
            const data = await res.json(); // Safely try to get error
            this.showToast('Failed to retry: ' + (data.detail || res.statusText), 'error');
            return;
        }
        this.fetchJobs();
    },

    async runTask(jobId, taskName) {
        const res = await fetch(`/api/jobs/${jobId}/tasks/${taskName}/run`, { method: 'POST' });
        const data = await res.json();
        if (data.ok) {
            this.fetchJobs();
        } else {
            this.showToast('Failed to run task: ' + (data.detail || 'Unknown error'), 'error');
        }
    },

    async cancelJob(id) {
        if (!confirm('Are you sure you want to CANCEL this job?')) return;
        await fetch(`/api/jobs/${id}/cancel`, { method: 'POST' });
        this.fetchJobs();
        if (this.selectedJob && this.selectedJob.id === id) this.selectedJob = null;
    },

    toggleAll(e) {
        if (e.target.checked) {
            this.selectedIds = this.jobs.map(j => j.id);
        } else {
            this.selectedIds = [];
        }
    },
});
