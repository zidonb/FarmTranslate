from flask import Flask, request, jsonify
import hmac
import hashlib
import json
from datetime import datetime
import subscription_manager
from config import load_config

app = Flask(__name__)

def verify_signature(payload_body, signature_header, secret):
    """
    Verify Lemon Squeezy webhook signature
    """
    computed_signature = hmac.new(
        secret.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(computed_signature, signature_header)

@app.route('/webhook/lemonsqueezy', methods=['POST'])
def lemonsqueezy_webhook():
    """
    Handle Lemon Squeezy webhook events
    """
    try:
        # Get config
        config = load_config()
        webhook_secret = config['lemonsqueezy']['webhook_secret']
        
        # Get raw payload and signature
        payload_body = request.get_data()
        signature_header = request.headers.get('X-Signature')
        
        if not signature_header:
            print("ERROR: No signature header")
            return jsonify({"error": "No signature"}), 401
        
        # Verify signature
        if not verify_signature(payload_body, signature_header, webhook_secret):
            print("ERROR: Invalid signature")
            return jsonify({"error": "Invalid signature"}), 401
        
        # Parse JSON payload
        data = request.json
        
        # Extract event info
        event_name = data['meta']['event_name']
        custom_data = data['meta'].get('custom_data', {})
        telegram_id = custom_data.get('telegram_id')
        
        if not telegram_id:
            print(f"WARNING: No telegram_id in webhook for event {event_name}")
            return jsonify({"status": "success", "note": "no telegram_id"}), 200
        
        print(f"Processing event: {event_name} for telegram_id: {telegram_id}")
        
        # Handle different event types
        if event_name == 'subscription_created':
            handle_subscription_created(telegram_id, data)
        
        elif event_name == 'subscription_updated':
            handle_subscription_updated(telegram_id, data)
        
        elif event_name == 'subscription_cancelled':
            handle_subscription_cancelled(telegram_id, data)
        
        elif event_name == 'subscription_resumed':
            handle_subscription_resumed(telegram_id, data)
        
        elif event_name == 'subscription_expired':
            handle_subscription_expired(telegram_id, data)
        
        elif event_name == 'subscription_paused':
            handle_subscription_paused(telegram_id, data)
        
        elif event_name == 'subscription_unpaused':
            handle_subscription_unpaused(telegram_id, data)
        
        elif event_name == 'subscription_payment_success':
            handle_subscription_payment_success(telegram_id, data)
        
        elif event_name == 'subscription_payment_failed':
            handle_subscription_payment_failed(telegram_id, data)
        
        elif event_name == 'subscription_payment_recovered':
            handle_subscription_payment_recovered(telegram_id, data)
        
        else:
            print(f"Unhandled event: {event_name}")
        
        # Always respond with 200 to acknowledge receipt
        return jsonify({"status": "success"}), 200
    
    except Exception as e:
        print(f"ERROR processing webhook: {e}")
        # Still return 200 to avoid retries for our own errors
        return jsonify({"status": "error", "message": str(e)}), 200

def handle_subscription_created(telegram_id: str, data: dict):
    """Handle subscription_created event"""
    attrs = data['data']['attributes']
    
    subscription_data = {
        'status': 'active',
        'lemon_subscription_id': data['data']['id'],
        'lemon_customer_id': str(attrs['customer_id']),
        'started_at': attrs['created_at'],
        'renews_at': attrs['renews_at'],
        'ends_at': attrs.get('ends_at'),
        'cancelled_at': None,
        'plan': 'monthly',
        'customer_portal_url': attrs['urls']['customer_portal']
    }
    
    subscription_manager.save_subscription(telegram_id, subscription_data)
    print(f"✅ Subscription created for {telegram_id}: {subscription_data['lemon_subscription_id']}")

def handle_subscription_updated(telegram_id: str, data: dict):
    """Handle subscription_updated event"""
    attrs = data['data']['attributes']
    
    # Get existing subscription
    subscription = subscription_manager.get_subscription(telegram_id)
    if not subscription:
        print(f"WARNING: Subscription not found for {telegram_id}, creating new")
        handle_subscription_created(telegram_id, data)
        return
    
    # Update relevant fields
    subscription['renews_at'] = attrs['renews_at']
    subscription['ends_at'] = attrs.get('ends_at')
    subscription['customer_portal_url'] = attrs['urls']['customer_portal']
    
    # Update status if changed
    if attrs['cancelled']:
        subscription['status'] = 'cancelled'
        if not subscription.get('cancelled_at'):
            subscription['cancelled_at'] = datetime.utcnow().isoformat()
    
    subscription_manager.save_subscription(telegram_id, subscription)
    print(f"✅ Subscription updated for {telegram_id}")

def handle_subscription_cancelled(telegram_id: str, data: dict):
    """Handle subscription_cancelled event"""
    attrs = data['data']['attributes']
    
    subscription = subscription_manager.get_subscription(telegram_id)
    if not subscription:
        print(f"WARNING: Subscription not found for {telegram_id}")
        return
    
    subscription['status'] = 'cancelled'
    subscription['cancelled_at'] = datetime.utcnow().isoformat()
    subscription['ends_at'] = attrs.get('ends_at')
    
    subscription_manager.save_subscription(telegram_id, subscription)
    print(f"⚠️ Subscription cancelled for {telegram_id}, access until: {attrs.get('ends_at')}")

def handle_subscription_resumed(telegram_id: str, data: dict):
    """Handle subscription_resumed event"""
    subscription = subscription_manager.get_subscription(telegram_id)
    if not subscription:
        print(f"WARNING: Subscription not found for {telegram_id}")
        return
    
    subscription['status'] = 'active'
    subscription['cancelled_at'] = None
    subscription['ends_at'] = None
    
    subscription_manager.save_subscription(telegram_id, subscription)
    print(f"✅ Subscription resumed for {telegram_id}")

def handle_subscription_expired(telegram_id: str, data: dict):
    """Handle subscription_expired event"""
    subscription = subscription_manager.get_subscription(telegram_id)
    if not subscription:
        print(f"WARNING: Subscription not found for {telegram_id}")
        return
    
    subscription['status'] = 'expired'
    
    subscription_manager.save_subscription(telegram_id, subscription)
    print(f"❌ Subscription expired for {telegram_id}")

def handle_subscription_paused(telegram_id: str, data: dict):
    """Handle subscription_paused event (payment failures)"""
    subscription = subscription_manager.get_subscription(telegram_id)
    if not subscription:
        print(f"WARNING: Subscription not found for {telegram_id}")
        return
    
    subscription['status'] = 'paused'
    
    subscription_manager.save_subscription(telegram_id, subscription)
    print(f"⏸️ Subscription paused for {telegram_id}")

def handle_subscription_unpaused(telegram_id: str, data: dict):
    """Handle subscription_unpaused event"""
    subscription = subscription_manager.get_subscription(telegram_id)
    if not subscription:
        print(f"WARNING: Subscription not found for {telegram_id}")
        return
    
    subscription['status'] = 'active'
    
    subscription_manager.save_subscription(telegram_id, subscription)
    print(f"▶️ Subscription unpaused for {telegram_id}")

def handle_subscription_payment_success(telegram_id: str, data: dict):
    """Handle subscription_payment_success event"""
    subscription = subscription_manager.get_subscription(telegram_id)
    if subscription:
        # Update renewal date from parent subscription if available
        print(f"✅ Payment successful for {telegram_id}")

def handle_subscription_payment_failed(telegram_id: str, data: dict):
    """Handle subscription_payment_failed event"""
    print(f"⚠️ Payment failed for {telegram_id}")

def handle_subscription_payment_recovered(telegram_id: str, data: dict):
    """Handle subscription_payment_recovered event"""
    subscription = subscription_manager.get_subscription(telegram_id)
    if subscription and subscription['status'] == 'paused':
        subscription['status'] = 'active'
        subscription_manager.save_subscription(telegram_id, subscription)
    print(f"✅ Payment recovered for {telegram_id}")

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)