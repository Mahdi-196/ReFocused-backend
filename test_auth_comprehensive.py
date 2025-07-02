#!/usr/bin/env python3
"""
Comprehensive Authentication Test Suite for ReFocused Backend

This script tests:
1. User registration and login
2. All endpoints with valid authentication
3. All endpoints without authentication (should fail)
4. Token refresh functionality
5. Auth status checking

Run this script to verify all authentication is working correctly.
"""

import asyncio
import aiohttp
import json
import sys
import time
from datetime import datetime, date
from typing import Dict, List, Optional, Any
import uuid

# Configuration
BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api/v1"

# Test user data
TEST_USER = {
    "email": f"test_{int(time.time())}@example.com",
    "password": "TestPassword123!",
    "name": "Test User"
}

class AuthTester:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.user_id: Optional[int] = None
        self.results = {
            "registration": None,
            "login": None,
            "auth_status": None,
            "token_refresh": None,
            "protected_endpoints_with_auth": {},
            "protected_endpoints_without_auth": {},
            "public_endpoints": {}
        }

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def log_success(self, test_name: str, details: str = ""):
        print(f"✅ {test_name}: {details}")
        
    def log_error(self, test_name: str, error: str):
        print(f"❌ {test_name}: {error}")
        
    def log_info(self, message: str):
        print(f"ℹ️  {message}")

    async def make_request(self, method: str, endpoint: str, data: Dict = None, 
                          use_auth: bool = False, headers: Dict = None) -> Dict:
        """Make HTTP request with optional authentication"""
        url = f"{API_BASE}{endpoint}"
        request_headers = headers or {}
        
        if use_auth and self.access_token:
            request_headers["Authorization"] = f"Bearer {self.access_token}"
            
        # Add timezone header for calendar endpoints
        if "/calendar" in endpoint or "/mood" in endpoint or "/habits" in endpoint:
            request_headers["X-User-Timezone"] = "America/New_York"

        try:
            async with self.session.request(
                method, url, json=data, headers=request_headers
            ) as response:
                try:
                    response_data = await response.json()
                except:
                    response_text = await response.text()
                    response_data = {"message": response_text, "raw_response": response_text}
                
                return {
                    "status_code": response.status,
                    "data": response_data if response_data else {},
                    "success": 200 <= response.status < 300
                }
        except Exception as e:
            return {
                "status_code": 0,
                "data": {"error": str(e)},
                "success": False
            }

    async def test_registration(self) -> bool:
        """Test user registration"""
        self.log_info("Testing user registration...")
        
        result = await self.make_request("POST", "/auth/register", TEST_USER)
        self.results["registration"] = result
        
        if result["success"]:
            self.log_success("Registration", f"User created: {TEST_USER['email']}")
            # Some registration endpoints return tokens immediately
            if result["data"] and "access_token" in result["data"]:
                self.access_token = result["data"]["access_token"]
                self.refresh_token = result["data"].get("refresh_token")
                self.log_info(f"Got tokens from registration: access_token length = {len(self.access_token) if self.access_token else 0}")
            else:
                self.log_info("No tokens returned from registration, will need to login separately")
            return True
        else:
            self.log_error("Registration", f"Status: {result['status_code']}, Error: {result['data']}")
            return False

    async def test_login(self) -> bool:
        """Test user login"""
        self.log_info("Testing user login...")
        
        login_data = {
            "email": TEST_USER["email"],
            "password": TEST_USER["password"]
        }
        
        result = await self.make_request("POST", "/auth/login", login_data)
        self.results["login"] = result
        
        if result["success"]:
            self.access_token = result["data"]["access_token"]
            self.refresh_token = result["data"].get("refresh_token")
            if "user" in result["data"]:
                self.user_id = result["data"]["user"]["id"]
            self.log_success("Login", f"Tokens received, expires_in: {result['data'].get('expires_in', 'N/A')}")
            return True
        else:
            self.log_error("Login", f"Status: {result['status_code']}, Error: {result['data']}")
            return False

    async def test_auth_status(self) -> bool:
        """Test authentication status endpoint"""
        self.log_info("Testing auth status...")
        
        result = await self.make_request("GET", "/auth/status", use_auth=True)
        self.results["auth_status"] = result
        
        if result["success"] and result["data"]:
            authenticated = result["data"].get("authenticated", False)
            user_info = result["data"].get("user", {})
            self.log_success("Auth Status", f"Authenticated: {authenticated}, User: {user_info.get('email', 'N/A') if user_info else 'N/A'}")
            return True
        else:
            self.log_error("Auth Status", f"Status: {result['status_code']}, Error: {result.get('data', 'No data')}")
            return False

    async def test_token_refresh(self) -> bool:
        """Test token refresh functionality"""
        if not self.refresh_token:
            self.log_error("Token Refresh", "No refresh token available")
            return False
            
        self.log_info("Testing token refresh...")
        
        refresh_data = {"refresh_token": self.refresh_token}
        result = await self.make_request("POST", "/auth/refresh", refresh_data)
        self.results["token_refresh"] = result
        
        if result["success"]:
            old_token = self.access_token
            self.access_token = result["data"]["access_token"]
            self.log_success("Token Refresh", f"New token received (different: {old_token != self.access_token})")
            return True
        else:
            self.log_error("Token Refresh", f"Status: {result['status_code']}, Error: {result['data']}")
            return False

    async def test_protected_endpoints_with_auth(self):
        """Test all protected endpoints with valid authentication"""
        self.log_info("Testing protected endpoints WITH authentication...")
        
        # Define test endpoints with sample data for POST/PUT operations
        endpoints_to_test = [
            # User endpoints
            ("GET", "/user/me"),
            ("GET", "/user/profile"),
            ("GET", "/user/stats"),
            
            # Goals endpoints
            ("GET", "/goals"),
            ("POST", "/goals", {
                "title": "Test Goal",
                "description": "Test goal description",
                "target_date": (datetime.now().date() + timedelta(days=30)).isoformat(),
                "priority": "medium"
            }),
            
            # Habits endpoints
            ("GET", "/habits"),
            ("GET", "/habits/completions"),
            ("GET", "/habits/streak-status"),
            ("GET", "/habits/dashboard/summary"),
            
            # Mood endpoints
            ("GET", "/mood/today"),
            ("GET", "/mood/entries"),
            ("GET", "/mood/"),
            
            # Calendar endpoints
            ("GET", "/calendar/entries"),
            ("GET", "/calendar/summary"),
            
            # Dashboard endpoints
            ("GET", "/dashboard/daily-entries"),
            ("GET", "/dashboard/entries"),
            
            # Study endpoints
            ("GET", "/study/sets"),
            
            # Statistics endpoints
            ("GET", "/statistics"),
            ("GET", "/statistics/detailed"),
            ("GET", "/statistics/debug/all"),
            
            # Journal endpoints
            ("GET", "/journal/collections"),
            ("GET", "/journal/entries"),
            ("GET", "/journal/gratitude"),
            ("GET", "/journal/stats"),
            ("GET", "/journal/health"),
            
            # Time endpoints
            ("GET", "/time/user-timezone"),
            ("GET", "/time/server-time"),
            
            # Content endpoints (should work without auth but testing with auth)
            ("GET", "/content/quote"),
        ]
        
        for endpoint_info in endpoints_to_test:
            method = endpoint_info[0]
            endpoint = endpoint_info[1]
            data = endpoint_info[2] if len(endpoint_info) > 2 else None
            
            result = await self.make_request(method, endpoint, data, use_auth=True)
            self.results["protected_endpoints_with_auth"][f"{method} {endpoint}"] = result
            
            if result["success"]:
                self.log_success(f"{method} {endpoint}", f"Status: {result['status_code']}")
            else:
                self.log_error(f"{method} {endpoint}", f"Status: {result['status_code']}, Error: {result['data']}")

    async def test_protected_endpoints_without_auth(self):
        """Test protected endpoints WITHOUT authentication - should fail"""
        self.log_info("Testing protected endpoints WITHOUT authentication (should fail)...")
        
        protected_endpoints = [
            ("GET", "/user/me"),
            ("GET", "/user/profile"),
            ("GET", "/goals"),
            ("GET", "/habits"),
            ("GET", "/mood/today"),
            ("GET", "/calendar/entries"),
            ("GET", "/dashboard/daily-entries"),
            ("GET", "/study/sets"),
            ("GET", "/statistics"),
            ("GET", "/journal/collections"),
        ]
        
        for method, endpoint in protected_endpoints:
            result = await self.make_request(method, endpoint, use_auth=False)
            self.results["protected_endpoints_without_auth"][f"{method} {endpoint}"] = result
            
            if result["status_code"] == 401:
                self.log_success(f"{method} {endpoint}", "Correctly rejected (401)")
            elif result["status_code"] == 403:
                self.log_success(f"{method} {endpoint}", "Correctly rejected (403)")
            else:
                self.log_error(f"{method} {endpoint}", f"Should have been rejected but got: {result['status_code']}")

    async def test_public_endpoints(self):
        """Test public endpoints that should work without authentication"""
        self.log_info("Testing public endpoints (should work without auth)...")
        
        public_endpoints = [
            ("GET", "/content/quote"),
        ]
        
        for method, endpoint in public_endpoints:
            result = await self.make_request(method, endpoint, use_auth=False)
            self.results["public_endpoints"][f"{method} {endpoint}"] = result
            
            if result["success"]:
                self.log_success(f"{method} {endpoint}", f"Status: {result['status_code']}")
            else:
                self.log_error(f"{method} {endpoint}", f"Status: {result['status_code']}, Error: {result['data']}")

    async def test_logout(self):
        """Test logout functionality"""
        self.log_info("Testing logout...")
        
        result = await self.make_request("POST", "/auth/logout", use_auth=True)
        
        if result["success"]:
            self.log_success("Logout", "Successfully logged out")
            # Test that subsequent requests fail
            test_result = await self.make_request("GET", "/user/me", use_auth=True)
            if test_result["status_code"] == 401:
                self.log_success("Post-logout auth check", "Token correctly invalidated")
            else:
                self.log_error("Post-logout auth check", "Token still valid after logout")
        else:
            self.log_error("Logout", f"Status: {result['status_code']}, Error: {result['data']}")

    def print_summary(self):
        """Print test results summary"""
        print("\n" + "="*80)
        print("🔒 AUTHENTICATION TEST SUMMARY")
        print("="*80)
        
        # Count successes and failures
        total_tests = 0
        successful_tests = 0
        
        # Registration and login
        if self.results["registration"] and self.results["registration"]["success"]:
            successful_tests += 1
        total_tests += 1
        
        if self.results["login"] and self.results["login"]["success"]:
            successful_tests += 1
        total_tests += 1
        
        # Protected endpoints with auth
        auth_endpoints = self.results["protected_endpoints_with_auth"]
        for endpoint, result in auth_endpoints.items():
            total_tests += 1
            if result["success"]:
                successful_tests += 1
        
        # Protected endpoints without auth (success means 401/403)
        no_auth_endpoints = self.results["protected_endpoints_without_auth"]
        for endpoint, result in no_auth_endpoints.items():
            total_tests += 1
            if result["status_code"] in [401, 403]:
                successful_tests += 1
        
        # Public endpoints
        public_endpoints = self.results["public_endpoints"]
        for endpoint, result in public_endpoints.items():
            total_tests += 1
            if result["success"]:
                successful_tests += 1
        
        print(f"📊 Overall Results: {successful_tests}/{total_tests} tests passed")
        print(f"🎯 Success Rate: {(successful_tests/total_tests)*100:.1f}%")
        
        if successful_tests == total_tests:
            print("🎉 ALL TESTS PASSED! Authentication system is working correctly.")
        else:
            print("⚠️  Some tests failed. Please review the errors above.")
        
        print("\n📋 Detailed Results:")
        print(f"✅ User Registration: {'PASS' if self.results['registration'] and self.results['registration']['success'] else 'FAIL'}")
        print(f"✅ User Login: {'PASS' if self.results['login'] and self.results['login']['success'] else 'FAIL'}")
        print(f"✅ Protected Endpoints (with auth): {sum(1 for r in auth_endpoints.values() if r['success'])}/{len(auth_endpoints)} passed")
        print(f"✅ Protected Endpoints (without auth): {sum(1 for r in no_auth_endpoints.values() if r['status_code'] in [401, 403])}/{len(no_auth_endpoints)} correctly rejected")
        print(f"✅ Public Endpoints: {sum(1 for r in public_endpoints.values() if r['success'])}/{len(public_endpoints)} passed")

    async def run_all_tests(self):
        """Run the complete test suite"""
        print("🚀 Starting Comprehensive Authentication Test Suite")
        print(f"📧 Test User: {TEST_USER['email']}")
        print(f"🔗 Base URL: {BASE_URL}")
        print("-" * 80)
        
        try:
            # Step 1: Register new user
            if not await self.test_registration():
                self.log_error("Test Suite", "Registration failed, stopping tests")
                return
            
            # Step 2: Login (if registration didn't provide tokens)
            if not self.access_token:
                if not await self.test_login():
                    self.log_error("Test Suite", "Login failed, stopping tests")
                    return
            
            # Step 3: Test auth status
            try:
                await self.test_auth_status()
            except Exception as e:
                self.log_error("Auth Status Test", f"Error: {str(e)}")
            
            # Step 4: Test token refresh
            try:
                await self.test_token_refresh()
            except Exception as e:
                self.log_error("Token Refresh Test", f"Error: {str(e)}")
            
            # Step 5: Test protected endpoints with auth
            try:
                await self.test_protected_endpoints_with_auth()
            except Exception as e:
                self.log_error("Protected Endpoints With Auth Test", f"Error: {str(e)}")
            
            # Step 6: Test protected endpoints without auth
            try:
                await self.test_protected_endpoints_without_auth()
            except Exception as e:
                self.log_error("Protected Endpoints Without Auth Test", f"Error: {str(e)}")
            
            # Step 7: Test public endpoints
            try:
                await self.test_public_endpoints()
            except Exception as e:
                self.log_error("Public Endpoints Test", f"Error: {str(e)}")
            
            # Step 8: Test logout
            try:
                await self.test_logout()
            except Exception as e:
                self.log_error("Logout Test", f"Error: {str(e)}")
            
        except Exception as e:
            self.log_error("Test Suite", f"Unexpected error: {str(e)}")
            import traceback
            traceback.print_exc()
        
        finally:
            # Print summary
            self.print_summary()

# Import timedelta for goal creation
from datetime import timedelta

async def main():
    """Main entry point"""
    print("🔐 ReFocused Backend Authentication Test Suite")
    print("=" * 80)
    
    async with AuthTester() as tester:
        await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main()) 