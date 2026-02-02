"""
Migration script: Convert single worker to workers array
Run once after deploying multi-worker changes
"""

import database

def migrate_managers():
    """Convert manager['worker'] to manager['workers'] array"""
    all_users = database.get_all_users()
    migrated_count = 0
    
    for user_id, user_data in all_users.items():
        if user_data.get('role') == 'manager':
            # Check if old format exists
            if 'worker' in user_data:
                old_worker_id = user_data['worker']
                
                # Initialize workers array
                if 'workers' not in user_data:
                    user_data['workers'] = []
                
                # Convert to new format
                if old_worker_id:  # If there was a worker connected
                    user_data['workers'].append({
                        'worker_id': old_worker_id,
                        'bot_id': 'bot1',  # Assume bot1 for existing users
                        'status': 'active',
                        'registered_at': user_data.get('created_at', '2026-01-01T00:00:00Z')
                    })
                
                # Remove old field
                del user_data['worker']
                
                # Save updated user
                database.save_user(user_id, user_data)
                migrated_count += 1
                print(f"✅ Migrated manager {user_id}")
    
    print(f"\n🎉 Migration complete! Migrated {migrated_count} managers")

def migrate_workers():
    """Add bot_id to workers who don't have it"""
    all_users = database.get_all_users()
    migrated_count = 0
    
    for user_id, user_data in all_users.items():
        if user_data.get('role') == 'worker':
            # Add bot_id if missing
            if 'bot_id' not in user_data:
                user_data['bot_id'] = 'bot1'  # Assume bot1 for existing workers
                database.save_user(user_id, user_data)
                migrated_count += 1
                print(f"✅ Migrated worker {user_id}")
    
    print(f"\n🎉 Migration complete! Migrated {migrated_count} workers")

if __name__ == '__main__':
    print("🔄 Starting migration to multi-worker format...\n")
    
    import db_connection
    db_connection.init_connection_pool(min_conn=5, max_conn=20)
    
    try:
        migrate_managers()
        migrate_workers()
        print("\n✅ All migrations successful!")
    finally:
        db_connection.close_all_connections()