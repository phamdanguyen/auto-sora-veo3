export const createAccountModule = (context) => ({
    accounts: [],
    newAccount: { platform: 'sora', email: '', password: '', proxy: '' },
    refreshingAccounts: false,
    checkingCredits: false,

    async fetchAccounts() {
        const res = await fetch('/api/accounts/');
        this.accounts = await res.json();
        this.stats.activeAccounts = this.accounts.filter(a =>
            a.credits_remaining === null || a.credits_remaining > 0
        ).length;
    },

    async addAccount() {
        await fetch('/api/accounts/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(this.newAccount)
        });
        this.showAddAccountModal = false;
        this.newAccount = { platform: 'sora', email: '', password: '', proxy: '' };
        this.fetchAccounts();
    },

    async deleteAccount(id) {
        if (!confirm('Are you sure you want to delete this account?')) return;
        try {
            const res = await fetch(`/api/accounts/${id}`, { method: 'DELETE' });
            if (res.ok) this.fetchAccounts();
            else this.showToast("Failed to delete account", "error");
        } catch (e) { this.showToast(`Error: ${e}`, "error"); }
    },

    async loginAccount(id) {
        const acc = this.accounts.find(a => a.id === id);
        if (!acc) return;
        if (acc.login_mode === 'manual') {
            if (confirm(`Account ${acc.email} is in MANUAL mode.\n\nUse Manual Login?`)) this.globalManualLogin();
            return;
        }
        if (!confirm(`Start Auto-Login for: ${acc.email}?`)) return;
        acc.token_status = 'logging_in';
        try {
            const res = await fetch(`/api/accounts/${id}/login`, { method: 'POST' });
            const data = await res.json();
            if (res.ok && data.ok) this.showToast(`✅ Login successful`, 'success');
            else this.showToast(`❌ Login failed: ${data.detail || 'Error'}`, 'error');
        } catch (e) { this.showToast(`❌ Login error: ${e}`, 'error'); }
        finally { this.fetchAccounts(); }
    },

    async checkAllCredits() {
        this.checkingCredits = true;
        try {
            const response = await fetch('/api/accounts/check_credits', { method: 'POST' });
            const result = await response.json();
            const toastType = (result.expired > 0 || result.failed > 0) ? 'error' : 'success';
            this.showToast(`✅ Updated: ${result.updated} | ⚠️ Expired: ${result.expired}`, toastType);
            if (result.expired > 0) {
                const expiredList = result.details.filter(d => d.status === 'expired').map(d => d.email).join('\n  - ');
                alert(`⚠️ ${result.expired} accounts expired:\n\n  - ${expiredList}\n\nPlease Re-Login!`);
            }
            await this.fetchAccounts();
        } catch (error) { this.showToast('Failed to check credits', 'error'); }
        finally { this.checkingCredits = false; }
    },

    async globalManualLogin() {
        if (!confirm("Start GLOBAL MANUAL Login?")) return;
        try {
            const res = await fetch('/api/accounts/global_manual_login', { method: 'POST' });
            const data = await res.json();
            if (res.ok && data.ok) this.showToast(`✅ Login Successful`, 'success');
            else this.showToast(`❌ Login failed`, 'error');
        } catch (e) { alert(`❌ Error: ${e}`); }
        finally { this.fetchAccounts(); }
    },

    async toggleLoginMode(acc) {
        const newMode = (acc.login_mode === 'manual') ? 'auto' : 'manual';

        try {
            const res = await fetch(`/api/accounts/${acc.id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ login_mode: newMode })
            });

            if (res.ok) {
                this.showToast(`Switched to ${newMode.toUpperCase()} mode`, 'success');
                this.fetchAccounts();
            } else {
                this.showToast('Failed to update mode', 'error');
            }
        } catch (e) {
            this.showToast('Error: ' + e, 'error');
        }
    },

    async refreshAllAccounts() {
        this.refreshingAccounts = true;
        try {
            const res = await fetch('/api/accounts/refresh_all', { method: 'POST' });
            const data = await res.json();
            this.showToast(`Refresh Complete! Total: ${data.total} | Valid: ${data.valid}`, 'success');
        } catch (e) {
            this.showToast(`Refresh failed: ${e}`, 'error');
        } finally {
            this.refreshingAccounts = false;
            this.fetchAccounts();
        }
    },
});
