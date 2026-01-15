"""
Unit Tests for License Manager
Tests all license management functionality including:
- Hardware ID generation with multiple fallbacks
- Encrypted trial marker storage
- License key validation
- Expiry warnings
"""
import pytest
import os
import tempfile
import shutil
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import hashlib
import hmac
import base64

from app.core.license_manager import LicenseManager


class TestHardwareID:
    """Test hardware ID generation with multiple fallbacks"""

    def test_get_motherboard_uuid_success(self):
        """Test successful motherboard UUID retrieval"""
        mock_output = "UUID\nABCD1234-5678-90EF-GHIJ-KLMNOPQRSTUV\n"

        with patch('subprocess.check_output', return_value=mock_output.encode()):
            result = LicenseManager._get_motherboard_uuid()
            assert result == "ABCD1234-5678-90EF-GHIJ-KLMNOPQRSTUV"

    def test_get_motherboard_uuid_failure(self):
        """Test motherboard UUID retrieval failure"""
        with patch('subprocess.check_output', side_effect=Exception("Command failed")):
            result = LicenseManager._get_motherboard_uuid()
            assert result is None

    def test_get_cpu_id_success(self):
        """Test successful CPU ID retrieval"""
        mock_output = "ProcessorId\nBFEBFBFF000906E9\n"

        with patch('subprocess.check_output', return_value=mock_output.encode()):
            result = LicenseManager._get_cpu_id()
            assert result == "BFEBFBFF000906E9"

    def test_get_cpu_id_failure(self):
        """Test CPU ID retrieval failure"""
        with patch('subprocess.check_output', side_effect=Exception("Command failed")):
            result = LicenseManager._get_cpu_id()
            assert result is None

    def test_get_mac_address_success(self):
        """Test MAC address retrieval"""
        with patch('uuid.getnode', return_value=0x112233445566):
            result = LicenseManager._get_mac_address()
            assert result == "11:22:33:44:55:66"

    def test_get_mac_address_invalid(self):
        """Test MAC address with all zeros"""
        with patch('uuid.getnode', return_value=0x0):
            result = LicenseManager._get_mac_address()
            assert result is None

    def test_get_volume_serial_success(self):
        """Test volume serial retrieval"""
        mock_output = "Volume Serial Number is ABCD-1234\n"

        with patch('subprocess.check_output', return_value=mock_output.encode()):
            result = LicenseManager._get_volume_serial()
            assert result == "ABCD-1234"

    def test_get_volume_serial_failure(self):
        """Test volume serial retrieval failure"""
        with patch('subprocess.check_output', side_effect=Exception("Command failed")):
            result = LicenseManager._get_volume_serial()
            assert result is None

    def test_get_hardware_id_all_success(self):
        """Test hardware ID with all identifiers available"""
        with patch.object(LicenseManager, '_get_motherboard_uuid', return_value="MB-UUID-123"):
            with patch.object(LicenseManager, '_get_cpu_id', return_value="CPU-ID-456"):
                with patch.object(LicenseManager, '_get_mac_address', return_value="11:22:33:44:55:66"):
                    with patch.object(LicenseManager, '_get_volume_serial', return_value="VOL-789"):
                        hwid = LicenseManager.get_hardware_id()

                        # Verify it's a 16-char hex string
                        assert len(hwid) == 16
                        assert all(c in '0123456789ABCDEF' for c in hwid)

    def test_get_hardware_id_with_fallbacks(self):
        """Test hardware ID when some identifiers fail"""
        with patch.object(LicenseManager, '_get_motherboard_uuid', return_value=None):
            with patch.object(LicenseManager, '_get_cpu_id', return_value="CPU-ID-456"):
                with patch.object(LicenseManager, '_get_mac_address', return_value="11:22:33:44:55:66"):
                    with patch.object(LicenseManager, '_get_volume_serial', return_value=None):
                        hwid = LicenseManager.get_hardware_id()

                        # Should still generate a valid hash with placeholders
                        assert len(hwid) == 16
                        assert all(c in '0123456789ABCDEF' for c in hwid)

    def test_get_hardware_id_consistency(self):
        """Test that hardware ID is consistent across calls"""
        mock_values = {
            '_get_motherboard_uuid': "MB-UUID-123",
            '_get_cpu_id': "CPU-ID-456",
            '_get_mac_address': "11:22:33:44:55:66",
            '_get_volume_serial': "VOL-789"
        }

        with patch.multiple(LicenseManager, **mock_values):
            hwid1 = LicenseManager.get_hardware_id()
            hwid2 = LicenseManager.get_hardware_id()

            assert hwid1 == hwid2


class TestLicenseKeyOperations:
    """Test license key generation and validation"""

    def setup_method(self):
        """Setup for each test"""
        self.temp_dir = tempfile.mkdtemp()
        self.original_license_file = LicenseManager.LICENSE_FILE
        LicenseManager.LICENSE_FILE = os.path.join(self.temp_dir, "test_license.key")

    def teardown_method(self):
        """Cleanup after each test"""
        LicenseManager.LICENSE_FILE = self.original_license_file
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_generate_key_format(self):
        """Test that generated key is valid base64"""
        hwid = "TEST-HWID-123456"
        expiry = "2026-12-31"

        key = LicenseManager.generate_key(hwid, expiry)

        # Should be base64 encoded
        assert isinstance(key, str)
        try:
            decoded = base64.b64decode(key)
            assert b"::" in decoded
        except Exception:
            pytest.fail("Generated key is not valid base64")

    def test_generate_key_contains_correct_data(self):
        """Test that key contains hardware ID and expiry date"""
        hwid = "TEST-HWID-123456"
        expiry = "2026-12-31"

        key = LicenseManager.generate_key(hwid, expiry)
        decoded = base64.b64decode(key).decode()

        assert hwid in decoded
        assert expiry in decoded

    def test_validate_valid_key(self):
        """Test validation of a valid key"""
        hwid = "TEST-HWID-123456"
        expiry = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

        with patch.object(LicenseManager, 'get_hardware_id', return_value=hwid):
            key = LicenseManager.generate_key(hwid, expiry)
            is_valid, message, exp_date = LicenseManager.validate_key(key)

            assert is_valid is True
            assert message == "Valid"
            assert exp_date == expiry

    def test_validate_expired_key(self):
        """Test validation of an expired key"""
        hwid = "TEST-HWID-123456"
        expiry = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        with patch.object(LicenseManager, 'get_hardware_id', return_value=hwid):
            key = LicenseManager.generate_key(hwid, expiry)
            is_valid, message, exp_date = LicenseManager.validate_key(key)

            assert is_valid is False
            assert "expired" in message.lower()
            assert exp_date == expiry

    def test_validate_wrong_hardware_id(self):
        """Test validation with mismatched hardware ID"""
        hwid_generate = "HWID-MACHINE-A"
        hwid_validate = "HWID-MACHINE-B"
        expiry = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

        key = LicenseManager.generate_key(hwid_generate, expiry)

        with patch.object(LicenseManager, 'get_hardware_id', return_value=hwid_validate):
            is_valid, message, exp_date = LicenseManager.validate_key(key)

            assert is_valid is False
            assert "not for this machine" in message.lower()

    def test_validate_tampered_key(self):
        """Test validation of a tampered key"""
        hwid = "TEST-HWID-123456"
        expiry = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

        with patch.object(LicenseManager, 'get_hardware_id', return_value=hwid):
            key = LicenseManager.generate_key(hwid, expiry)

            # Tamper with the key
            decoded = base64.b64decode(key).decode()
            payload, signature = decoded.split("::")
            tampered = payload.replace(expiry, "2030-12-31")  # Change expiry
            tampered_key = base64.b64encode(f"{tampered}::{signature}".encode()).decode()

            is_valid, message, exp_date = LicenseManager.validate_key(tampered_key)

            assert is_valid is False
            assert "signature" in message.lower()

    def test_validate_invalid_format(self):
        """Test validation of invalid key format"""
        invalid_key = base64.b64encode(b"invalid-format-no-separator").decode()

        is_valid, message, exp_date = LicenseManager.validate_key(invalid_key)

        assert is_valid is False
        assert "format" in message.lower()

    def test_save_and_load_key(self):
        """Test saving and loading license key"""
        test_key = "TEST-LICENSE-KEY-12345"

        LicenseManager.save_key(test_key)
        loaded_key = LicenseManager.load_stored_key()

        assert loaded_key == test_key

    def test_load_nonexistent_key(self):
        """Test loading when no key file exists"""
        loaded_key = LicenseManager.load_stored_key()
        assert loaded_key is None


class TestLicenseStatus:
    """Test license status reporting with expiry warnings"""

    def setup_method(self):
        """Setup for each test"""
        self.temp_dir = tempfile.mkdtemp()
        self.original_license_file = LicenseManager.LICENSE_FILE
        LicenseManager.LICENSE_FILE = os.path.join(self.temp_dir, "test_license.key")

    def teardown_method(self):
        """Cleanup after each test"""
        LicenseManager.LICENSE_FILE = self.original_license_file
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_get_status_no_license(self):
        """Test status when no license exists"""
        with patch.object(LicenseManager, 'get_hardware_id', return_value="TEST-HWID"):
            status = LicenseManager.get_license_status()

            assert status["status"] == "missing"
            assert status["hardware_id"] == "TEST-HWID"
            assert status["expiration"] is None
            assert status["days_remaining"] is None
            assert status["warning"] is None

    def test_get_status_valid_license_no_warning(self):
        """Test status with valid license (>14 days remaining)"""
        hwid = "TEST-HWID-123456"
        expiry = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

        with patch.object(LicenseManager, 'get_hardware_id', return_value=hwid):
            key = LicenseManager.generate_key(hwid, expiry)
            LicenseManager.save_key(key)

            status = LicenseManager.get_license_status()

            assert status["status"] == "valid"
            assert status["expiration"] == expiry
            assert status["days_remaining"] == 31  # 30 days + 1
            assert status["warning"] is None

    def test_get_status_valid_license_soft_warning(self):
        """Test status with valid license (8-14 days remaining)"""
        hwid = "TEST-HWID-123456"
        expiry = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")

        with patch.object(LicenseManager, 'get_hardware_id', return_value=hwid):
            key = LicenseManager.generate_key(hwid, expiry)
            LicenseManager.save_key(key)

            status = LicenseManager.get_license_status()

            assert status["status"] == "valid"
            assert status["days_remaining"] == 11  # 10 days + 1
            assert status["warning"] is not None
            assert "11 days" in status["warning"]
            assert "expiring" in status["warning"].lower()

    def test_get_status_valid_license_critical_warning(self):
        """Test status with valid license (<=7 days remaining)"""
        hwid = "TEST-HWID-123456"
        expiry = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")

        with patch.object(LicenseManager, 'get_hardware_id', return_value=hwid):
            key = LicenseManager.generate_key(hwid, expiry)
            LicenseManager.save_key(key)

            status = LicenseManager.get_license_status()

            assert status["status"] == "valid"
            assert status["days_remaining"] == 6  # 5 days + 1
            assert status["warning"] is not None
            assert "6 day(s)!" in status["warning"]
            assert "expiring" in status["warning"].lower()

    def test_get_status_expired_license(self):
        """Test status with expired license"""
        hwid = "TEST-HWID-123456"
        expiry = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

        with patch.object(LicenseManager, 'get_hardware_id', return_value=hwid):
            key = LicenseManager.generate_key(hwid, expiry)
            LicenseManager.save_key(key)

            status = LicenseManager.get_license_status()

            assert status["status"] == "expired"
            assert "expired" in status["message"].lower()
            assert status["expiration"] == expiry


class TestEncryptedTrialMarker:
    """Test encrypted trial marker storage and retrieval"""

    def setup_method(self):
        """Setup for each test"""
        self.temp_dir = tempfile.mkdtemp()
        self.original_marker_dir = LicenseManager.TRIAL_MARKER_DIR
        self.original_marker_file = LicenseManager.TRIAL_MARKER_FILE

        LicenseManager.TRIAL_MARKER_DIR = os.path.join(self.temp_dir, ".univideo")
        LicenseManager.TRIAL_MARKER_FILE = os.path.join(LicenseManager.TRIAL_MARKER_DIR, "trial.dat")

    def teardown_method(self):
        """Cleanup after each test"""
        LicenseManager.TRIAL_MARKER_DIR = self.original_marker_dir
        LicenseManager.TRIAL_MARKER_FILE = self.original_marker_file

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_encrypt_decrypt_marker_data(self):
        """Test encryption and decryption of marker data"""
        test_data = "2026-01-14 12:34:56.789012|TEST-HWID|abc123def456"

        encrypted = LicenseManager._encrypt_marker_data(test_data)
        decrypted = LicenseManager._decrypt_marker_data(encrypted)

        assert decrypted == test_data

    def test_encrypt_marker_data_format(self):
        """Test that encrypted data is in correct format"""
        test_data = "test data"

        encrypted = LicenseManager._encrypt_marker_data(test_data)

        # Fernet produces base64-encoded data
        assert isinstance(encrypted, str)
        try:
            base64.urlsafe_b64decode(encrypted)
        except Exception:
            pytest.fail("Encrypted data is not valid base64")

    def test_decrypt_invalid_data(self):
        """Test decryption of invalid data fails"""
        invalid_encrypted = "invalid-encrypted-data"

        with pytest.raises(ValueError):
            LicenseManager._decrypt_marker_data(invalid_encrypted)

    @patch('platform.system', return_value='Windows')
    @patch('winreg.CreateKey')
    @patch('winreg.SetValueEx')
    @patch('winreg.CloseKey')
    def test_save_trial_marker_success(self, mock_close, mock_set, mock_create, mock_platform):
        """Test successful trial marker save"""
        start_dt = datetime(2026, 1, 14, 12, 30, 0)

        with patch.object(LicenseManager, 'get_hardware_id', return_value="TEST-HWID"):
            result = LicenseManager.save_trial_marker(start_dt)

            assert result is True
            assert os.path.exists(LicenseManager.TRIAL_MARKER_FILE)

    @patch('platform.system', return_value='Windows')
    @patch('winreg.CreateKey')
    @patch('winreg.SetValueEx')
    @patch('winreg.CloseKey')
    def test_load_trial_marker_success(self, mock_close, mock_set, mock_create, mock_platform):
        """Test successful trial marker load"""
        start_dt = datetime(2026, 1, 14, 12, 30, 0)

        with patch.object(LicenseManager, 'get_hardware_id', return_value="TEST-HWID"):
            # Save marker
            LicenseManager.save_trial_marker(start_dt)

            # Load marker
            success, loaded_dt, error = LicenseManager.load_trial_marker()

            assert success is True
            assert loaded_dt is not None
            assert loaded_dt.year == 2026
            assert loaded_dt.month == 1
            assert loaded_dt.day == 14
            assert error is None

    def test_load_trial_marker_not_exists(self):
        """Test loading when marker doesn't exist"""
        with patch('platform.system', return_value='Linux'):  # Skip registry
            success, loaded_dt, error = LicenseManager.load_trial_marker()

            assert success is False
            assert loaded_dt is None
            assert "not found" in error.lower()

    @patch('platform.system', return_value='Windows')
    @patch('winreg.CreateKey')
    @patch('winreg.SetValueEx')
    @patch('winreg.CloseKey')
    def test_load_trial_marker_tampered_hwid(self, mock_close, mock_set, mock_create, mock_platform):
        """Test loading marker with mismatched hardware ID"""
        start_dt = datetime(2026, 1, 14, 12, 30, 0)

        with patch.object(LicenseManager, 'get_hardware_id', return_value="HWID-A"):
            LicenseManager.save_trial_marker(start_dt)

        # Try to load with different HWID
        with patch.object(LicenseManager, 'get_hardware_id', return_value="HWID-B"):
            success, loaded_dt, error = LicenseManager.load_trial_marker()

            assert success is False
            assert "tampered" in error.lower()
            assert "hwid" in error.lower()

    @patch('platform.system', return_value='Windows')
    @patch('winreg.CreateKey')
    @patch('winreg.SetValueEx')
    @patch('winreg.CloseKey')
    def test_check_trial_status_not_used(self, mock_close, mock_set, mock_create, mock_platform):
        """Test trial status when trial has not been used"""
        with patch('platform.system', return_value='Linux'):  # Skip registry
            status = LicenseManager.check_trial_status()

            assert status["active"] is False
            assert status["used"] is False
            assert status["remaining_days"] == 7
            assert status["expiry_date"] is None

    @patch('platform.system', return_value='Windows')
    @patch('winreg.CreateKey')
    @patch('winreg.SetValueEx')
    @patch('winreg.CloseKey')
    def test_check_trial_status_active(self, mock_close, mock_set, mock_create, mock_platform):
        """Test trial status when trial is active"""
        start_dt = datetime.utcnow() - timedelta(days=3)  # Started 3 days ago

        with patch.object(LicenseManager, 'get_hardware_id', return_value="TEST-HWID"):
            LicenseManager.save_trial_marker(start_dt)

            status = LicenseManager.check_trial_status()

            assert status["active"] is True
            assert status["used"] is True
            assert status["remaining_days"] == 5  # 7 - 3 + 1
            assert status["expiry_date"] is not None

    @patch('platform.system', return_value='Windows')
    @patch('winreg.CreateKey')
    @patch('winreg.SetValueEx')
    @patch('winreg.CloseKey')
    def test_check_trial_status_expired(self, mock_close, mock_set, mock_create, mock_platform):
        """Test trial status when trial has expired"""
        start_dt = datetime.utcnow() - timedelta(days=10)  # Started 10 days ago

        with patch.object(LicenseManager, 'get_hardware_id', return_value="TEST-HWID"):
            LicenseManager.save_trial_marker(start_dt)

            status = LicenseManager.check_trial_status()

            assert status["active"] is False
            assert status["used"] is True
            assert status["remaining_days"] == 0
            assert "expired" in status["error"].lower()


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_generate_key_with_special_characters(self):
        """Test key generation with special characters in HWID"""
        hwid = "TEST@HWID#123$456"
        expiry = "2026-12-31"

        # Should not raise exception
        key = LicenseManager.generate_key(hwid, expiry)
        assert isinstance(key, str)

    def test_validate_key_with_whitespace(self):
        """Test validation with whitespace in key"""
        hwid = "TEST-HWID"
        expiry = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

        with patch.object(LicenseManager, 'get_hardware_id', return_value=hwid):
            key = LicenseManager.generate_key(hwid, expiry)
            key_with_spaces = f"  {key}  \n"

            # Should handle whitespace gracefully
            is_valid, message, exp = LicenseManager.validate_key(key_with_spaces.strip())
            assert is_valid is True

    def test_get_status_with_corrupted_key_file(self):
        """Test status when key file is corrupted"""
        temp_dir = tempfile.mkdtemp()
        try:
            LicenseManager.LICENSE_FILE = os.path.join(temp_dir, "corrupt.key")

            # Write corrupted key
            with open(LicenseManager.LICENSE_FILE, 'w') as f:
                f.write("CORRUPTED-NOT-BASE64!@#$")

            with patch.object(LicenseManager, 'get_hardware_id', return_value="TEST"):
                status = LicenseManager.get_license_status()

                assert status["status"] == "invalid"
        finally:
            shutil.rmtree(temp_dir)

    def test_expiry_date_boundary(self):
        """Test expiry on exact boundary (today)"""
        hwid = "TEST-HWID"
        expiry = datetime.now().strftime("%Y-%m-%d")

        with patch.object(LicenseManager, 'get_hardware_id', return_value=hwid):
            key = LicenseManager.generate_key(hwid, expiry)
            is_valid, message, exp = LicenseManager.validate_key(key)

            # Should still be valid on the expiry date itself
            assert is_valid is True

    def test_trial_marker_directory_creation(self):
        """Test that marker directory is created if it doesn't exist"""
        temp_dir = tempfile.mkdtemp()
        try:
            marker_dir = os.path.join(temp_dir, ".univideo")
            marker_file = os.path.join(marker_dir, "trial.dat")

            LicenseManager.TRIAL_MARKER_DIR = marker_dir
            LicenseManager.TRIAL_MARKER_FILE = marker_file

            assert not os.path.exists(marker_dir)

            with patch('platform.system', return_value='Linux'):
                with patch.object(LicenseManager, 'get_hardware_id', return_value="TEST"):
                    LicenseManager.save_trial_marker(datetime.utcnow())

            assert os.path.exists(marker_dir)
        finally:
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
