import os
import logging
import psycopg2
import psycopg2.errors
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler
import profile_handler
import refer_handler
# import task_handler  # WIP
# import withdraw_handler # WIP

# লগিং সেটআপ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# # ----------------------------------------------------
# # ১. ডেটাবেস, টোকেন ও কনস্ট্যান্ট ভেরিয়েবল
# # ----------------------------------------------------
# # সিকিউরিটি আপগ্রেড: গোপন তথ্য পরিবেশ ভেরিয়েবল
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

# গ্লোবাল কনস্ট্যান্ট (যা refer_handler.py ব্যবহার করে) - CRITICAL FIX #1
REFERRAL_BONUS_JOINING = 40.00 
# # ----------------------------------------------------

# # ----------------------------------------------------
# # ২. ডেটাবেস কানেকশন এবং ইউজার টেবিল তৈরি/তৈরি
# # ----------------------------------------------------

def connect_db():
    """Render ডেটাবেসের সাথে যুক্ত হয়"""
    if not BOT_TOKEN or not DATABASE_URL:
        logger.error("পরিবেশ ভেরিয়েবল (BOT_TOKEN বা DATABASE_URL) সেট করা হয়নি।")
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        logger.error(f"ডেটাবেস সংযোগে ব্যর্থতা: {e}")
        return None

def create_table_if_not_exists():
    """ইউজার টেবিল তৈরি করে যদি এটি বিদ্যমান না থাকে"""
    conn = connect_db()
    if conn is None:
        return

    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                balance NUMERIC(10, 2) DEFAULT 0.00,
                free_income NUMERIC(10, 2) DEFAULT 0.00,
                refer_balance NUMERIC(10, 2) DEFAULT 0.00,
                salary_balance NUMERIC(10, 2) DEFAULT 0.00,
                total_withdraw NUMERIC(10, 2) DEFAULT 0.00,
                is_premium BOOLEAN DEFAULT FALSE,
                expiry_date TIMESTAMP,
                referrer_id BIGINT,
                join_date TIMESTAMP DEFAULT NOW()
            );
        """)
        conn.commit()
        logger.info("ইউজার টেবিল সফলভাবে চেক/তৈরি হয়েছে।")
    except Exception as e:
        logger.error(f"টেবিল তৈরি করতে সমস্যা: {e}")
    finally:
        cursor.close()
        conn.close()

# # ----------------------------------------------------
# # ৩. ইউজার রেজিস্ট্রেশন এবং রেফারেল বোনাস লজিক
# # ----------------------------------------------------

def register_user(user_id, username, referrer_id=None):
    """
    নতুন ইউজারকে রেজিস্টার করে এবং রেফারারকে বোনাস দেয়।
    """
    conn = connect_db()
    if not conn:
        return False

    cursor = conn.cursor()
    
    try:
        # ১. ইউজারকে খুঁজে বের করা
        cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
        existing_user = cursor.fetchone()

        if existing_user:
            cursor.close()
            conn.close()
            return True

        # ২. নতুন ইউজার রেজিস্টার করা
        cursor.execute(
            """
            INSERT INTO users (user_id, username, referrer_id)
            VALUES (%s, %s, %s);
            """,
            (user_id, username, referrer_id)
        )
        conn.commit()
        logger.info(f"New user registered: {user_id}")

        # ৩. রেফারারকে বোনাস দেওয়া (যদি থাকে)
        if referrer_id:
            cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (referrer_id,))
            if cursor.fetchone():
                cursor.execute(
                    "UPDATE users SET refer_balance = refer_balance + %s WHERE user_id = %s",
                    (REFERRAL_BONUS_JOINING, referrer_id) # REFERRAL_BONUS_JOINING ব্যবহার নিশ্চিত করা হয়েছে
                )
                conn.commit()
                logger.info(f"Referral bonus given to referrer: {referrer_id}")
            else:
                logger.warning(f"Referrer not found: {referrer_id}")
        
        return True

    except Exception as e:
        logger.error(f"User registration error: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

# # ----------------------------------------------------
# # ৪. ডেটাবেস থেকে ইউজারের স্ট্যাটাস নেওয়ার ফাংশন (Profile Handler এর জন্য) - CRITICAL FIX #2
# # ----------------------------------------------------

def get_user_status(user_id):
    """
    ডেটাবেস থেকে ইউজারের সমস্ত প্রোফাইল ডেটা (ব্যালেন্স, স্ট্যাটাস ইত্যাদি) প্রদান করে।
    """
    conn = connect_db()
    if not conn:
        return None

    cursor = conn.cursor()
    try:
        # সমস্ত প্রয়োজনীয় কলাম ফেচ করা
        cursor.execute(
            """
            SELECT balance, free_income, refer_balance, salary_balance, 
                   total_withdraw, is_premium, expiry_date
            FROM users 
            WHERE user_id = %s
            """,
            (user_id,)
        )
        status = cursor.fetchone()
        
        # যদি ইউজার না থাকে, তবে None রিটার্ন
        if not status:
            return None

        # ডেটা টুপল হিসেবে রিটার্ন
        return status
        
    except Exception as e:
        logger.error(f"Error fetching user status for {user_id}: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

# # ----------------------------------------------------
# # ৫. হ্যান্ডলার ফাংশন
# # ----------------------------------------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or f"user_{user_id}"
    
    # রেফারেল লজিক (যদি /start <referrer_id> থাকে)
    referrer_id = None
    if context.args:
        try:
            referrer_id = int(context.args[0])
            if referrer_id == user_id: # নিজেকে রেফার করা যাবে না
                referrer_id = None 
        except ValueError:
            referrer_id = None

    # ইউজার রেজিস্টার করা
    register_user(user_id, username, referrer_id)
    
    # স্বাগত মেসেজ
    welcome_message = f"স্বাগতম, {user.first_name}!\n\nআপনি প্রধান মেনুতে আছেন।"
    
    await update.message.reply_text(
        welcome_message,
        reply_markup=main_menu_keyboard
    )

# # ----------------------------------------------------
# # ৬. বাটন ডিজাইন
# # ----------------------------------------------------

# ক) মূল মেনুর বাটন (Reply Keyboard) - আপনার দেওয়া স্ক্রিনশট অনুযায়ী
main_menu_keyboard = ReplyKeyboardMarkup([
    ["🏠 প্রধান মেনু (Home)", "👤 PROFILE 👤", "🏦 WITHDRAW 🏦"],
    ["⭐ প্রিমিয়াম সার্ভিস", "🏅 TASK 🏅", "🎁 REFER 🎁"],
    ["✅ VERIFY ✅", "📜 HISTORY 📜", "📞 সাপোর্ট"]
], resize_keyboard=True)


# # ৭. বোটের প্রধান রান ফাংশন
def main():
    # ইউজার টেবিল তৈরি নিশ্চিত করা - CRITICAL FIX #3
    create_table_if_not_exists()
    
    # টেলিগ্রাম অ্যাপ্লিকেশন শুরু করা
    application = Application.builder().token(BOT_TOKEN).build()

    # কমান্ড হ্যান্ডলার
    application.add_handler(CommandHandler("start", start_command))
    
    # প্রোফাইল হ্যান্ডলার
    application.add_handler(MessageHandler(filters.Regex("👤 PROFILE 👤"), profile_handler.profile_command))
    
    # রেফারেল হ্যান্ডলার
    application.add_handler(MessageHandler(filters.Regex("🎁 REFER 🎁"), refer_handler.refer_command))
    
    # অন্যান্য মেসেজ হ্যান্ডলার (যদি প্রয়োজন হয়)
    # application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # পোলিং মোডে বট চালানো
    logger.info("Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
