import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

def setup_database():
    """Create the PostgreSQL database if it doesn't exist"""
    try:
        # Connect to PostgreSQL server
        conn = psycopg2.connect(
            dbname='postgres',
            user='postgres',
            password='password',
            host='localhost',
            port='5432'
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        
        # Create cursor
        cur = conn.cursor()
        
        # Check if database exists
        cur.execute("SELECT 1 FROM pg_database WHERE datname = 'refocused-local-testing'")
        exists = cur.fetchone()
        
        if not exists:
            # Create database
            cur.execute('CREATE DATABASE "refocused-local-testing"')
            print("Database 'refocused-local-testing' created successfully!")
        else:
            print("Database 'refocused-local-testing' already exists.")
            
        # Close cursor and connection
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"Error setting up database: {e}")
        raise

if __name__ == "__main__":
    setup_database() 