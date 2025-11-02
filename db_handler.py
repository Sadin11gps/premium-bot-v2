import os
import psycopg2
import logging

logger = logging.getLogger(__name__)

# ডেটাবেস সংযোগের URL এনভায়রনমেন্ট ভেরিয়েবল থেকে নেওয়া
DATABASE_URL = os.environ.get("DATABASE_URL")

def connect_db():
    """ডেটাবেসের সাথে সংযোগ স্থাপন করে।"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        logger.error(f"Error connecting to database: {e}")
        return None

def create_table_if_not_exists():
    """ইউজার, উইথড্র রিকোয়েস্ট, এবং অন্যান্য প্রয়োজনীয় টেবিল তৈরি করে।"""
    conn = connect_db()
    if conn:
        try:
            cur = conn.cursor()
            # 1. ইউজার টেবিল
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username VARCHAR(50),
                    first_name VARCHAR(50),
                    balance NUMERIC(10, 2) DEFAULT 0.00,
                    wallet_address VARCHAR(100),
                    referred_by BIGINT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # 2. উইথড্র রিকোয়েস্ট টেবিল (Withdrawal Requests)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS withdraw_requests (
                    request_id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    amount NUMERIC(10, 2) NOT NULL,
                    wallet_address VARCHAR(100) NOT NULL,
                    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'completed', 'rejected'
                    requested_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # 3. VERIFICATION টেবিল (যদি আপনার ভেরিফিকেশন সিস্টেম থাকে)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS verification_requests (
                    verify_id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    txn_id VARCHAR(50) UNIQUE NOT NULL,
                    amount NUMERIC(10, 2),
                    status VARCHAR(20) DEFAULT 'pending', 
                    method VARCHAR(10),
                    requested_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            conn.commit()
            logger.info("Database tables checked/completed successfully.")
        except Exception as e:
            logger.error(f"Error creating tables: {e}")
        finally:
            conn.close()

# --- হ্যান্ডলারের জন্য প্রয়োজনীয় অন্যান্য DB ফাংশন ---

def get_user_balance(user_id):
    """ইউজারের বর্তমান ব্যালেন্স দেয়।"""
    conn = connect_db()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
            result = cur.fetchone()
            return result[0] if result else 0.00
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return 0.00
        finally:
            conn.close()

def update_balance(user_id, amount_change):
    """ইউজারের ব্যালেন্স পরিবর্তন করে।"""
    conn = connect_db()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE users SET balance = balance + %s WHERE user_id = %s",
                (amount_change, user_id)
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Error updating balance: {e}")
        finally:
            conn.close()
            
def get_user_data(user_id):
    """উইথড্র এবং প্রোফাইল হ্যান্ডলারের জন্য ইউজারের ডেটা (যেমন: ওয়ালেট) দেয়।"""
    conn = connect_db()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT username, first_name, wallet_address FROM users WHERE user_id = %s",
                (user_id,)
            )
            result = cur.fetchone()
            if result:
                return {
                    'username': result[0], 
                    'first_name': result[1],
                    'wallet_address': result[2] 
                }
            return {}
        except Exception as e:
            logger.error(f"Error getting user data: {e}")
            return {}
        finally:
            conn.close()
            
# --- WITHDRAWAL ফাংশন ---

def record_withdraw_request(user_id, amount, wallet_address):
    """নতুন উত্তোলন অনুরোধ ডেটাবেসে সংরক্ষণ করে।"""
    conn = connect_db()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO withdraw_requests (user_id, amount, wallet_address) VALUES (%s, %s, %s) RETURNING request_id",
                (user_id, amount, wallet_address)
            )
            request_id = cur.fetchone()[0]
            conn.commit()
            return request_id
        except Exception as e:
            logger.error(f"Error recording withdrawal request: {e}")
            return None
        finally:
            conn.close()
            
def get_pending_withdrawals():
    """অ্যাডমিনের জন্য পেন্ডিং উত্তোলন অনুরোধগুলির তালিকা দেয়।"""
    conn = connect_db()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT request_id, user_id, amount, wallet_address, requested_at
                FROM withdraw_requests
                WHERE status = 'pending'
                ORDER BY requested_at ASC;
                """
            )
            return cur.fetchall()
        except Exception as e:
            logger.error(f"Error fetching pending withdrawals: {e}")
            return []
        finally:
            conn.close()

def update_withdraw_status(request_id, status):
    """উত্তোলন অনুরোধের অবস্থা আপডেট করে।"""
    conn = connect_db()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE withdraw_requests SET status = %s WHERE request_id = %s AND status = 'pending' RETURNING user_id",
                (status, request_id)
            )
            user_id = cur.fetchone()[0] if cur.rowcount > 0 else None
            conn.commit()
            # টাকা ফেরত দেওয়ার জন্য user_id ফেরত দেওয়া হয়
            return (True, user_id) if user_id else (False, None)
        except Exception as e:
            logger.error(f"Error updating withdrawal status: {e}")
            return (False, None)
        finally:
            conn.close()
            
# --- VERIFICATION ফাংশন (যদি আপনার ভেরিফিকেশন সিস্টেম ব্যবহার করে) ---
def record_verification_request(user_id, txn_id, amount, method):
    """নতুন ভেরিফিকেশন অনুরোধ ডেটাবেসে সংরক্ষণ করে।"""
    conn = connect_db()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO verification_requests (user_id, txn_id, amount, method) VALUES (%s, %s, %s, %s) RETURNING verify_id",
                (user_id, txn_id, amount, method)
            )
            verify_id = cur.fetchone()[0]
            conn.commit()
            return verify_id
        except Exception as e:
            logger.error(f"Error recording verification request: {e}")
            return None
        finally:
            conn.close()

def update_verification_status(verify_id, status):
    """ভেরিফিকেশন অনুরোধের অবস্থা আপডেট করে।"""
    conn = connect_db()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE verification_requests SET status = %s WHERE verify_id = %s AND status = 'pending' RETURNING user_id, amount",
                (status, verify_id)
            )
            result = cur.fetchone()
            user_id = result[0] if result else None
            amount = result[1] if result else 0.00
            conn.commit()
            return (True, user_id, amount) if user_id else (False, None, 0.00)
        except Exception as e:
            logger.error(f"Error updating verification status: {e}")
            return (False, None, 0.00)
        finally:
            conn.close()
