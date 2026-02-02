"""
Database Connection Manager for BridgeOS
==========================================

This module provides centralized database connection management using connection pooling.
All database operations in the application should use this module instead of creating
direct connections.

Connection Pool Configuration:
- Minimum connections: 5 (always kept warm and ready)
- Maximum connections: 20 (Railway PostgreSQL Starter limit)
- Connections are reused across requests for efficiency

Usage Examples:
    # Method 1: Using context manager (RECOMMENDED)
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        user = cur.fetchone()
    # Auto-commits on success, auto-rollbacks on error, auto-returns connection
    
    # Method 2: Manual connection management (for complex operations)
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users")
        users = cur.fetchall()
        conn.commit()
        cur.close()
    finally:
        return_connection(conn)

Author: BridgeOS Team
Last Updated: January 2025
"""

import os
from psycopg2 import pool
from contextlib import contextmanager
from typing import Optional

# Global connection pool - initialized once at application startup
_connection_pool: Optional[pool.SimpleConnectionPool] = None


def init_connection_pool(min_conn: int = 5, max_conn: int = 20) -> None:
    """
    Initialize the PostgreSQL connection pool.
    
    This should be called ONCE at application startup (in bot.py and dashboard.py).
    Creates a pool of reusable database connections that are shared across all
    database operations.
    
    Args:
        min_conn (int): Minimum number of connections to maintain. These connections
                       are kept open and ready for immediate use. Default: 5
        max_conn (int): Maximum number of connections allowed. Railway PostgreSQL
                       Starter plan limits this to 20. Default: 20
    
    Raises:
        Exception: If DATABASE_URL environment variable is not set
        psycopg2.Error: If unable to connect to the database
    
    Example:
        # In bot.py or dashboard.py
        import db_connection
        db_connection.init_connection_pool(min_conn=5, max_conn=20)
    
    Note:
        - Call this only once per application instance
        - Railway Starter plan: max 20 connections total
        - Railway Pro plan: max 100 connections total
    """
    global _connection_pool
    
    # Prevent double initialization
    if _connection_pool is not None:
        print("⚠️  Connection pool already initialized. Skipping...")
        return
    
    # Get database URL from environment
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise Exception(
            "DATABASE_URL not found in environment variables. "
            "Please set it in Railway dashboard or local .env file."
        )
    
    try:
        # Create the connection pool (thread-safe for Flask)
        _connection_pool = pool.ThreadedConnectionPool(
            minconn=min_conn,
            maxconn=max_conn,
            dsn=database_url
        )
        print(f"✅ Database connection pool initialized ({min_conn}-{max_conn} connections)")
        print(f"   Pool can handle ~{max_conn * 10} requests/second efficiently")
        
    except Exception as e:
        print(f"❌ Failed to initialize connection pool: {e}")
        raise


def get_db_connection():
    """
    Get a database connection from the pool.
    
    This function retrieves an available connection from the pool. If all connections
    are in use, it will wait for one to become available (with Railway's default timeout).
    
    IMPORTANT: Always return the connection using return_connection() when done,
    preferably in a try-finally block or use get_db_cursor() context manager instead.
    
    Returns:
        psycopg2.connection: A database connection from the pool
    
    Raises:
        Exception: If connection pool is not initialized
        pool.PoolError: If all connections are exhausted and timeout is reached
    
    Example:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM users")
            results = cur.fetchall()
            conn.commit()
            cur.close()
        finally:
            return_connection(conn)  # CRITICAL: Always return!
    
    Note:
        Consider using get_db_cursor() context manager instead for automatic
        connection management.
    """
    global _connection_pool
    
    # Auto-initialize if not done yet (lazy initialization)
    if _connection_pool is None:
        print("⚠️  Connection pool not initialized. Auto-initializing with defaults...")
        init_connection_pool()
    
    try:
        # Get connection from pool
        conn = _connection_pool.getconn()
        return conn
        
    except pool.PoolError as e:
        # All connections are in use and timeout reached
        error_msg = (
            f"Connection pool exhausted: {e}\n"
            "This usually means:\n"
            "1. Too many concurrent database operations\n"
            "2. Connections not being returned to pool (check for missing finally blocks)\n"
            "3. Need to increase max_conn limit (upgrade Railway plan)"
        )
        print(f"❌ {error_msg}")
        raise Exception(error_msg)
    
    except Exception as e:
        print(f"❌ Error getting connection from pool: {e}")
        raise


def return_connection(conn) -> None:
    """
    Return a connection back to the pool for reuse.
    
    After finishing database operations, always return the connection to the pool
    so it can be reused by other operations. This is critical for preventing
    connection exhaustion.
    
    Args:
        conn: The connection object to return (obtained from get_db_connection())
    
    Example:
        conn = get_db_connection()
        try:
            # ... do database work
        finally:
            return_connection(conn)  # Always in finally block!
    
    Note:
        - This does NOT close the connection, just returns it to the pool
        - The connection remains open and ready for the next request
        - This is much faster than closing and reopening connections
    """
    global _connection_pool
    
    if _connection_pool and conn:
        try:
            _connection_pool.putconn(conn)
        except Exception as e:
            print(f"⚠️  Error returning connection to pool: {e}")


@contextmanager
def get_db_cursor(commit: bool = True):
    """
    Context manager for database operations (RECOMMENDED METHOD).
    
    This is the preferred way to interact with the database. It automatically:
    - Gets a connection from the pool
    - Creates a cursor
    - Commits the transaction on success (if commit=True)
    - Rolls back the transaction on error
    - Closes the cursor
    - Returns the connection to the pool
    
    All of this happens automatically - you just write your queries!
    
    Args:
        commit (bool): Whether to auto-commit on success. Default: True
                      Set to False for read-only operations (slight performance gain)
    
    Yields:
        psycopg2.cursor: A database cursor ready to execute queries
    
    Raises:
        Any exception from the database operation (after automatic rollback)
    
    Examples:
        # Simple query
        with get_db_cursor() as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            user = cur.fetchone()
        
        # Insert with auto-commit
        with get_db_cursor() as cur:
            cur.execute(
                "INSERT INTO users (user_id, data) VALUES (%s, %s)",
                (user_id, user_data)
            )
        # Automatically committed!
        
        # Read-only query (no commit needed)
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT COUNT(*) FROM users")
            count = cur.fetchone()[0]
    
    Benefits:
        ✅ Automatic connection management (no leaks!)
        ✅ Automatic commit on success
        ✅ Automatic rollback on error
        ✅ Cleaner, shorter code
        ✅ Impossible to forget to return connection
    """
    conn = get_db_connection()
    cur = None
    
    try:
        # Create cursor
        cur = conn.cursor()
        
        # Yield cursor to the caller
        yield cur
        
        # If we get here, operation succeeded
        if commit:
            conn.commit()
            
    except Exception as e:
        # Operation failed - rollback any changes
        if conn:
            conn.rollback()
        
        # Re-raise the exception so caller knows it failed
        raise e
        
    finally:
        # Always clean up
        if cur:
            cur.close()
        
        # Always return connection to pool (even if error occurred)
        return_connection(conn)


def close_all_connections() -> None:
    """
    Close all connections in the pool and destroy the pool.
    
    This should be called during application shutdown to cleanly close all database
    connections. After calling this, you must call init_connection_pool() again
    before making any database operations.
    
    Example:
        # In bot.py
        try:
            app.run_polling()
        finally:
            db_connection.close_all_connections()
    
    Note:
        - Called automatically on application shutdown (if you add it to finally block)
        - Railway will also close connections when your app restarts
        - Not critical but good practice for clean shutdown
    """
    global _connection_pool
    
    if _connection_pool:
        try:
            _connection_pool.closeall()
            _connection_pool = None
            print("✅ All database connections closed cleanly")
        except Exception as e:
            print(f"⚠️  Error closing connection pool: {e}")
    else:
        print("⚠️  Connection pool was not initialized, nothing to close")


def get_pool_status() -> dict:
    """
    Get current status of the connection pool (for monitoring/debugging).
    
    Returns:
        dict: Dictionary with pool statistics:
            - initialized (bool): Whether pool is initialized
            - min_conn (int): Minimum connections configured
            - max_conn (int): Maximum connections configured
            - Note: psycopg2.pool doesn't expose current usage stats
    
    Example:
        status = db_connection.get_pool_status()
        print(f"Pool initialized: {status['initialized']}")
        print(f"Max connections: {status['max_conn']}")
    
    Note:
        psycopg2.pool doesn't provide detailed usage statistics.
        For production monitoring, consider using PostgreSQL's pg_stat_activity view.
    """
    global _connection_pool
    
    if _connection_pool:
        return {
            'initialized': True,
            'min_conn': _connection_pool.minconn,
            'max_conn': _connection_pool.maxconn,
            'note': 'psycopg2.pool does not expose current connection count'
        }
    else:
        return {
            'initialized': False,
            'min_conn': None,
            'max_conn': None
        }


# Module-level docstring for help()
__all__ = [
    'init_connection_pool',
    'get_db_connection',
    'return_connection',
    'get_db_cursor',
    'close_all_connections',
    'get_pool_status'
]


if __name__ == '__main__':
    """
    Simple test of the connection pool.
    Run this file directly to test: python db_connection.py
    """
    print("Testing db_connection module...")
    print("-" * 50)
    
    # Test 1: Initialize pool
    print("\n1. Testing pool initialization...")
    try:
        init_connection_pool(min_conn=2, max_conn=5)
        print("   ✅ Pool initialized successfully")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        exit(1)
    
    # Test 2: Get status
    print("\n2. Testing pool status...")
    status = get_pool_status()
    print(f"   Status: {status}")
    
    # Test 3: Use context manager
    print("\n3. Testing context manager (get_db_cursor)...")
    try:
        with get_db_cursor(commit=False) as cur:
            cur.execute("SELECT 1 as test")
            result = cur.fetchone()
            print(f"   ✅ Query successful: {result}")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
    
    # Test 4: Manual connection management
    print("\n4. Testing manual connection management...")
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT version()")
        version = cur.fetchone()[0]
        print(f"   ✅ PostgreSQL version: {version[:50]}...")
        cur.close()
        return_connection(conn)
    except Exception as e:
        print(f"   ❌ Failed: {e}")
    
    # Test 5: Close pool
    print("\n5. Testing pool cleanup...")
    close_all_connections()
    
    print("-" * 50)
    print("✅ All tests completed!")