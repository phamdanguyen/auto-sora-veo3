export const createLicenseModule = (context) => ({
    licenseInfo: { status: 'loading', hardware_id: '', expiration: '', message: '', days_remaining: null },
    newLicenseKey: '',

    async fetchLicenseInfo() {
        try {
            const res = await fetch('/api/system/license');
            const data = await res.json();
            if (data.ok) this.licenseInfo = data.license;
        } catch (e) { this.licenseInfo.status = 'error'; }
    },

    async updateLicense() {
        if (!this.newLicenseKey) return alert("⚠️ Please enter key");
        const res = await fetch('/api/system/license/update?key=' + encodeURIComponent(this.newLicenseKey.trim()), { method: 'POST' });
        const data = await res.json();
        if (data.ok) {
            alert("✅ License Updated!");
            this.newLicenseKey = '';
            this.fetchLicenseInfo();
        } else alert("❌ Update Failed");
    }
});
