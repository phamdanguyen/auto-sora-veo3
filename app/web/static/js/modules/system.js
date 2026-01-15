export const createSystemModule = (context) => ({
    currentTab: window.location.pathname.replace('/', '') || 'dashboard',
    sidebarCollapsed: false,
    showAddAccountModal: false,
    showAddJobModal: false,
    systemStatus: { paused: false, queue_info: {}, active_jobs: [] },
    stats: { activeAccounts: 0, pendingJobs: 0, completedJobs: 0 },
    toast: { show: false, message: '', type: 'success' },

    showToast(message, type = 'success') {
        this.toast = { show: true, message, type };
        setTimeout(() => this.toast.show = false, 3000);
    },

    initSystem() {
        this.$watch('currentTab', (value) => {
            const path = value === 'dashboard' ? '/' : '/' + value;
            if (window.location.pathname !== path) {
                history.pushState(null, '', path);
            }
        });
        window.addEventListener('popstate', () => {
            this.currentTab = window.location.pathname.replace('/', '') || 'dashboard';
        });
    },

    async fetchSystemStatus() {
        try {
            const res = await fetch('/api/system/queue_status');
            if (res.ok) {
                const status = await res.json();
                if (status.paused && !this.systemStatus.paused) alert('🛑 HỆ THỐNG TẠM DỪNG: ' + status.pause_reason);
                this.systemStatus = status;
                if (status.db_stats) {
                    this.stats.completedJobs = status.db_stats.completed;
                    this.stats.pendingJobs = status.db_stats.pending;
                }
            }
        } catch (e) { console.error(e); }
    },

    formatDate: (d) => d ? new Date(d).toLocaleString('vi-VN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '-',

    async toggleSystemPause(pause) {
        const res = await fetch(pause ? '/api/system/pause' : '/api/system/resume', { method: 'POST' });
        if (res.ok) this.fetchSystemStatus();
    },

    async systemReset() {
        if (!confirm('⚠️ SYSTEM RESET\n\n- Clear busy account flags\n- Reset "processing" jobs to "pending"\n\nUse this only if jobs are stuck. Continue?')) return;

        const res = await fetch('/api/system/reset', { method: 'POST' });
        const data = await res.json();

        if (data.ok) {
            this.showToast(`System reset complete. Reset ${data.reset_count} jobs.`, 'success');
            // Assuming context has fetchJobs, but circular dependency might be issue if strictly module.
            // In spread operator component, 'this' refers to the merged object, so this.fetchJobs() should work if available.
            if (this.fetchJobs) this.fetchJobs();
        } else {
            this.showToast('System reset failed.', 'error');
        }
    },

    async startWorkers() {
        try {
            const res = await fetch('/api/settings/start_workers', { method: 'POST' });
            if (res.ok) {
                this.showToast('System started! Workers are running.', 'success');
            } else {
                this.showToast('Failed to start system.', 'error');
            }
        } catch (e) {
            this.showToast('Error starting system: ' + e, 'error');
        }
    }
});
