import { createSystemModule } from './modules/system.js';
import { createAccountModule } from './modules/account.js';
import { createJobModule } from './modules/job.js';
import { createLicenseModule } from './modules/license.js';

document.addEventListener('alpine:init', () => {
    Alpine.data('appData', () => ({
        ...createSystemModule(),
        ...createAccountModule(),
        ...createJobModule(),
        ...createLicenseModule(),

        init() {
            this.initSystem();
            this.fetchAccounts();
            this.fetchJobs();
            this.fetchSystemStatus();
            this.fetchLicenseInfo();
            setInterval(() => {
                this.fetchJobs();
                this.fetchSystemStatus();
            }, 5000);
        },

        // UI Helpers that need shared state
        viewJobDetail(job) { this.selectedJob = job; },
        openEditModal(job) { this.editingJob = JSON.parse(JSON.stringify(job)); },
        async openFolder(id) { await fetch(`/api/jobs/${id}/open_folder`, { method: 'POST' }); },
        async openVideo(id) { await fetch(`/api/jobs/${id}/open_video`, { method: 'POST' }); },
    }));
});
