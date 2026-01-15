"""
Test script for Phase 4 API endpoints
Quick validation of new routers
"""
from fastapi.testclient import TestClient
from app.main import app
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize TestClient with the app
client = TestClient(app)

def test_accounts_endpoints():
    """Test Accounts Router"""
    print("\n=== Testing Accounts Router ===")

    # Test GET /api/accounts/ (list accounts)
    response = client.get("/api/accounts/")
    print(f"GET /api/accounts/ -> {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    print(f"  Accounts: {len(response.json())}")

    # Test POST /api/accounts/ (create account) - should fail with 400 if email exists
    response = client.post("/api/accounts/", json={
        "platform": "sora",
        "email": "test@example.com",
        "password": "test123",
        "proxy": None
    })
    print(f"POST /api/accounts/ -> {response.status_code}")
    # Could be 200 (created) or 400 (already exists)
    assert response.status_code in [200, 400], f"Expected 200 or 400, got {response.status_code}"

    print("✓ Accounts endpoints OK")


def test_jobs_endpoints():
    """Test Jobs Router"""
    print("\n=== Testing Jobs Router ===")

    # Test GET /api/jobs/ (list jobs)
    response = client.get("/api/jobs/")
    print(f"GET /api/jobs/ -> {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    print(f"  Jobs: {len(response.json())}")

    # Test GET /api/jobs/?category=active
    response = client.get("/api/jobs/?category=active")
    print(f"GET /api/jobs/?category=active -> {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    print(f"  Active jobs: {len(response.json())}")

    # Test POST /api/jobs/ (create job)
    response = client.post("/api/jobs/", json={
        "prompt": "Test job for Phase 4",
        "duration": 5,
        "aspect_ratio": "16:9"
    })
    print(f"POST /api/jobs/ -> {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    job_data = response.json()
    job_id = job_data["id"]
    print(f"  Created job ID: {job_id}")

    # Test GET /api/jobs/{job_id}
    response = client.get(f"/api/jobs/{job_id}")
    print(f"GET /api/jobs/{job_id} -> {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    # Test PUT /api/jobs/{job_id}
    response = client.put(f"/api/jobs/{job_id}", json={
        "prompt": "Updated test job"
    })
    print(f"PUT /api/jobs/{job_id} -> {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    # Test DELETE /api/jobs/{job_id}
    response = client.delete(f"/api/jobs/{job_id}")
    print(f"DELETE /api/jobs/{job_id} -> {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    print("✓ Jobs endpoints OK")


def test_system_endpoints():
    """Test System Router"""
    print("\n=== Testing System Router ===")

    # Test GET /api/system/queue_status
    response = client.get("/api/system/queue_status")
    print(f"GET /api/system/queue_status -> {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    status = response.json()
    print(f"  Queue size: {status.get('queue_size', 0)}")
    print(f"  Active jobs: {status.get('active_count', 0)}")

    # Test POST /api/system/pause
    response = client.post("/api/system/pause")
    print(f"POST /api/system/pause -> {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    # Test POST /api/system/resume
    response = client.post("/api/system/resume")
    print(f"POST /api/system/resume -> {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    print("✓ System endpoints OK")


def main():
    """Run all tests"""
    print("=" * 60)
    print("Phase 4 API Endpoints Test")
    print("=" * 60)

    try:
        test_accounts_endpoints()
        test_jobs_endpoints()
        test_system_endpoints()

        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        print("\nPhase 4 API Layer Refactoring: SUCCESS")
        print("New routers are working correctly!")

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
