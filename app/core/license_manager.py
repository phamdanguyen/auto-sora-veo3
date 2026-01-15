import hashlib
import hmac
import base64
import subprocess
import platform
import os
import uuid as uuid_lib
from datetime import datetime, timezone, timedelta
from cryptography.fernet import Fernet

class LicenseManager:
    SECRET_SALT = b"UniVideo_SuperSecret_Salt_2024"  # Change this for production!
    LICENSE_FILE = "license.key"
    TRIAL_MARKER_DIR = os.path.join(os.path.expanduser("~"), ".univideo")
    TRIAL_MARKER_FILE = os.path.join(TRIAL_MARKER_DIR, "trial.dat")

    # Derived encryption key from SECRET_SALT (for marker encryption)
    _MARKER_KEY = base64.urlsafe_b64encode(hashlib.sha256(SECRET_SALT + b"_MARKER").digest())

    @staticmethod
    def _get_cpu_id():
        """Get CPU identifier (Windows only)."""
        try:
            if platform.system() == "Windows":
                output = subprocess.check_output("wmic cpu get processorid", shell=True).decode()
                lines = [line.strip() for line in output.split('\n') if line.strip()]
                if len(lines) > 1:
                    return lines[1]
        except:
            pass
        return None

    @staticmethod
    def _get_mac_address():
        """Get primary MAC address."""
        try:
            mac = ':'.join(['{:02x}'.format((uuid_lib.getnode() >> elements) & 0xff)
                           for elements in range(0,8*6,8)][::-1])
            return mac if mac != '00:00:00:00:00:00' else None
        except:
            return None

    @staticmethod
    def _get_volume_serial():
        """Get system volume serial number (Windows only)."""
        try:
            if platform.system() == "Windows":
                output = subprocess.check_output("vol c:", shell=True).decode()
                for line in output.split('\n'):
                    if 'Serial Number is' in line:
                        return line.split('Serial Number is')[1].strip()
        except:
            pass
        return None

    @staticmethod
    def _get_motherboard_uuid():
        """Get motherboard UUID (original method)."""
        try:
            if platform.system() == "Windows":
                cmd = "wmic csproduct get uuid"
                uuid = subprocess.check_output(cmd).decode().split('\n')[1].strip()
                return uuid
            else:
                return None
        except:
            return None

    @classmethod
    def get_hardware_id(cls):
        """
        Get composite hardware ID with multiple fallbacks.
        Format: MB_UUID:CPU_ID:MAC:VOL_SERIAL
        Returns a hash of available identifiers.
        """
        identifiers = []

        # Try all methods
        mb_uuid = cls._get_motherboard_uuid()
        cpu_id = cls._get_cpu_id()
        mac = cls._get_mac_address()
        vol_serial = cls._get_volume_serial()

        # Build identifier string (use placeholders for missing values)
        identifiers = [
            mb_uuid or "NO_MB",
            cpu_id or "NO_CPU",
            mac or "NO_MAC",
            vol_serial or "NO_VOL"
        ]

        # Create a composite hash
        composite = ":".join(identifiers)
        hw_hash = hashlib.sha256(composite.encode()).hexdigest()[:16].upper()

        return hw_hash

    @classmethod
    def generate_key(cls, hardware_id, expiration_date_str):
        """
        Generate a signed license key.
        expiration_date_str format: YYYY-MM-DD
        """
        payload = f"{hardware_id}|{expiration_date_str}"
        signature = hmac.new(cls.SECRET_SALT, payload.encode(), hashlib.sha256).hexdigest()
        key_data = f"{payload}::{signature}"
        return base64.b64encode(key_data.encode()).decode()

    @classmethod
    def validate_key(cls, key_str):
        """
        Validate the key string.
        Returns: (is_valid, message, expiration_date_str)
        """
        try:
            decoded = base64.b64decode(key_str).decode()
            if "::" not in decoded:
                return False, "Invalid Key Format", None
            
            payload, signature = decoded.split("::")
            
            # 1. Verify Signature
            expected_signature = hmac.new(cls.SECRET_SALT, payload.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected_signature):
                return False, "Invalid Signature", None
            
            # 2. Extract Data
            hardware_id, expiration_date_str = payload.split("|")
            
            # 3. Verify Hardware ID
            current_hwid = cls.get_hardware_id()
            if hardware_id != current_hwid:
                return False, f"Key not for this machine (ID: {hardware_id})", None
            
            # 4. Verify Expiration
            try:
                exp_date = datetime.strptime(expiration_date_str, "%Y-%m-%d").date()
                now_utc = datetime.now(timezone.utc).date()
                
                if now_utc > exp_date:
                    return False, f"Key expired on {expiration_date_str}", expiration_date_str
                
                return True, "Valid", expiration_date_str
                
            except ValueError:
                return False, "Invalid Date Format in Key", None

        except Exception as e:
            return False, f"Validation Error: {str(e)}", None

    @classmethod
    def save_key(cls, key_str):
        with open(cls.LICENSE_FILE, "w", encoding="utf-8") as f:
            f.write(key_str)

    @classmethod
    def load_stored_key(cls):
        if not os.path.exists(cls.LICENSE_FILE):
             return None
        with open(cls.LICENSE_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()

    @classmethod
    def get_license_status(cls):
        """
        Check stored license and return status dict with expiry warnings.
        """
        key = cls.load_stored_key()
        hwid = cls.get_hardware_id()

        if not key:
            return {
                "status": "missing",
                "hardware_id": hwid,
                "message": "No license found",
                "expiration": None,
                "days_remaining": None,
                "warning": None
            }

        is_valid, message, expiry = cls.validate_key(key)

        status_code = "valid" if is_valid else "invalid"
        if "expired" in message.lower():
            status_code = "expired"

        # Calculate days remaining and warnings
        days_remaining = None
        warning = None

        if is_valid and expiry:
            try:
                exp_date = datetime.strptime(expiry, "%Y-%m-%d").date()
                now_date = datetime.now(timezone.utc).date()
                days_remaining = (exp_date - now_date).days + 1

                # Generate warning if expiring soon
                if days_remaining <= 7:
                    warning = f"License expiring in {days_remaining} day(s)!"
                elif days_remaining <= 14:
                    warning = f"License expiring in {days_remaining} days"
            except:
                pass

        return {
            "status": status_code,
            "hardware_id": hwid,
            "message": message,
            "expiration": expiry,
            "days_remaining": days_remaining,
            "warning": warning
        }

    # ========== ENCRYPTED TRIAL MARKER METHODS ==========

    @classmethod
    def _encrypt_marker_data(cls, data_str):
        """Encrypt marker data using Fernet."""
        try:
            fernet = Fernet(cls._MARKER_KEY)
            return fernet.encrypt(data_str.encode()).decode()
        except Exception as e:
            raise ValueError(f"Encryption failed: {e}")

    @classmethod
    def _decrypt_marker_data(cls, encrypted_str):
        """Decrypt marker data using Fernet."""
        try:
            fernet = Fernet(cls._MARKER_KEY)
            return fernet.decrypt(encrypted_str.encode()).decode()
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")

    @classmethod
    def save_trial_marker(cls, start_datetime):
        """
        Save encrypted trial marker with verification hash.
        Format: timestamp|hardware_id|hash
        """
        try:
            os.makedirs(cls.TRIAL_MARKER_DIR, exist_ok=True)

            hwid = cls.get_hardware_id()
            timestamp = start_datetime.strftime("%Y-%m-%d %H:%M:%S.%f")

            # Create verification hash
            verification_data = f"{timestamp}|{hwid}"
            verification_hash = hmac.new(
                cls.SECRET_SALT,
                verification_data.encode(),
                hashlib.sha256
            ).hexdigest()

            # Data to encrypt
            marker_data = f"{timestamp}|{hwid}|{verification_hash}"

            # Encrypt and save
            encrypted = cls._encrypt_marker_data(marker_data)

            with open(cls.TRIAL_MARKER_FILE, "w", encoding="utf-8") as f:
                f.write(encrypted)

            # Also save to Windows Registry as backup (harder to delete)
            if platform.system() == "Windows":
                try:
                    import winreg
                    key_path = r"Software\UniVideo"
                    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
                    winreg.SetValueEx(key, "TrialMarker", 0, winreg.REG_SZ, encrypted)
                    winreg.CloseKey(key)
                except:
                    pass  # Non-critical if registry fails

            return True
        except Exception as e:
            print(f"Failed to save trial marker: {e}")
            return False

    @classmethod
    def load_trial_marker(cls):
        """
        Load and verify encrypted trial marker.
        Returns: (success, start_datetime, error_message)
        """
        encrypted_data = None

        # Try loading from file first
        if os.path.exists(cls.TRIAL_MARKER_FILE):
            try:
                with open(cls.TRIAL_MARKER_FILE, "r", encoding="utf-8") as f:
                    encrypted_data = f.read().strip()
            except:
                pass

        # Fallback to Windows Registry
        if not encrypted_data and platform.system() == "Windows":
            try:
                import winreg
                key_path = r"Software\UniVideo"
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
                encrypted_data, _ = winreg.QueryValueEx(key, "TrialMarker")
                winreg.CloseKey(key)
            except:
                pass

        if not encrypted_data:
            return False, None, "No trial marker found"

        # Decrypt and verify
        try:
            decrypted = cls._decrypt_marker_data(encrypted_data)
            parts = decrypted.split("|")

            if len(parts) != 3:
                return False, None, "Invalid marker format"

            timestamp_str, stored_hwid, stored_hash = parts

            # Verify hardware ID
            current_hwid = cls.get_hardware_id()
            if stored_hwid != current_hwid:
                return False, None, "Marker tampered (HWID mismatch)"

            # Verify hash
            verification_data = f"{timestamp_str}|{stored_hwid}"
            expected_hash = hmac.new(
                cls.SECRET_SALT,
                verification_data.encode(),
                hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(stored_hash, expected_hash):
                return False, None, "Marker tampered (hash mismatch)"

            # Parse datetime
            try:
                start_dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                start_dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")

            return True, start_dt, None

        except Exception as e:
            return False, None, f"Marker verification failed: {e}"

    @classmethod
    def check_trial_status(cls):
        """
        Check trial status and return detailed information.
        Returns: dict with status, remaining_days, expiry_date, error
        """
        success, start_dt, error = cls.load_trial_marker()

        if not success:
            return {
                "active": False,
                "used": False,
                "remaining_days": 7,
                "expiry_date": None,
                "error": error
            }

        # Calculate expiry
        expiry_dt = start_dt + timedelta(days=7)
        now = datetime.utcnow()

        if now < expiry_dt:
            remaining = (expiry_dt - now).days + 1
            return {
                "active": True,
                "used": True,
                "remaining_days": remaining,
                "expiry_date": expiry_dt.strftime("%Y-%m-%d"),
                "error": None
            }
        else:
            return {
                "active": False,
                "used": True,
                "remaining_days": 0,
                "expiry_date": expiry_dt.strftime("%Y-%m-%d"),
                "error": f"Trial expired on {expiry_dt.strftime('%Y-%m-%d')}"
            }
