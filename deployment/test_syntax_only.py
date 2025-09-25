#!/usr/bin/env python3
"""
Test script to check syntax and import issues without database
"""
import sys
import traceback

def test_auth_syntax():
    """Test if auth.py can be imported without syntax errors"""
    print("🔧 Testing auth.py syntax and imports...")

    try:
        # Set minimal environment to avoid database connection
        import os
        os.environ.update({
            "SECRET_KEY": "test-key",
            "GOOGLE_CLIENT_ID": "test-id",
            "GOOGLE_CLIENT_SECRET": "test-secret",
            "DATABASE_URL": "postgresql://test:test@localhost/test",  # Won't be used
        })

        # Try importing the auth module directly
        from app.api.v1.endpoints import auth
        print("✅ auth.py imports successfully - no syntax errors")
        return True

    except SyntaxError as e:
        print(f"❌ SYNTAX ERROR in auth.py: {e}")
        print(f"File: {e.filename}, Line: {e.lineno}")
        print(f"Text: {e.text}")
        traceback.print_exc()
        return False

    except ImportError as e:
        print(f"❌ IMPORT ERROR: {e}")
        traceback.print_exc()
        return False

    except Exception as e:
        print(f"❌ OTHER ERROR: {e}")
        traceback.print_exc()
        return False

def test_module_structure():
    """Test basic module structure"""
    print("\n🔧 Testing module structure...")

    try:
        # Test if we can import basic modules
        from app.core import config
        print("✅ config.py imports successfully")

        from app.api.v1 import api
        print("✅ api.py imports successfully")

        return True

    except Exception as e:
        print(f"❌ Module structure error: {e}")
        traceback.print_exc()
        return False

def main():
    """Run syntax tests"""
    print("🚀 Running syntax and import tests...")
    print("=" * 50)

    # Test basic syntax first
    syntax_ok = test_auth_syntax()

    if not syntax_ok:
        print("\n❌ Critical syntax errors found in auth.py")
        print("Must fix syntax errors before proceeding")
        return False

    # Test module structure
    structure_ok = test_module_structure()

    print("\n" + "=" * 50)
    if syntax_ok and structure_ok:
        print("✅ All syntax tests passed")
        return True
    else:
        print("❌ Some tests failed")
        return False

if __name__ == "__main__":
    # Suppress database connection attempts
    import os
    os.environ["SKIP_DB_INIT"] = "true"

    success = main()
    sys.exit(0 if success else 1)