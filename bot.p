import os
import logging
import psycopg2
import psycopg2.errors # ডেটাবেস মাইগ্রেশনের জন্য দরকার
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# **মডুলার ফাইলগুলি আমদানি করা**
import profile_handler 
import refer_handler 
# import task_handler  # WIP
# import withdraw_handler # WIP

# লগিং সেটআপ
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# -----------------
# ১. ডেটাবেস, টোকেন ও কনস্ট্যান্ট ভেরিয়েবল
# -----------------
# সিকিউরিটি আপডেট: গোপন তথ্য পরিবেশ ভেরিয়েবল থেকে নেওয়া হচ্ছে
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
DATABASE_URL = os.environ.get("DATABASE_URL") 

# বোনাস কনস্ট্যান্ট (আপনার দেওয়া মান অনুযায়ী)
REFERRAL_BONUS_JOINING = 40.00 

# -----------------
# ২. ডেটাবেস কানেকশন ও ইউজার টেবিল তৈরি/পড়া
# -----------------

def connect_db():
    """Render ডেটাবেসের সাথে যুক্ত হয়"""
    try:
        # যদি BOT_TOKEN বা DATABASE_URL না পাওয়া যায়, তবে এরর দেওয়া হবে (Render এর ক্ষেত্রে)
        if not DATABASE_URL:
            logger.error("DATABASE_URL environment variable is not set.")
            return None
            
        conn = psycopg2.connect(DATABASE_URL, sslmode='require') 
        return conn
    except Exception as e:
        logger.error(f"ডেটাবেস সংযোগে সমস্যা: {e}")
        return None

def create_table_if_not_exists():
    """ইউজারদের ডেটা সংরক্ষণের জন্য টেবিল তৈরি ও কলামগুলো যাচাই করে (মাইগ্রেশন সহ)"""
    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        try:
            # ১. প্রধান টেবিল তৈরি করা (যদি না থাকে)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    status TEXT DEFAULT 'start',
                    is_premium BOOLEAN DEFAULT FALSE,
                    expiry_date DATE,
                    
                    premium_balance DECIMAL(10, 2) DEFAULT 0.00,
                    free_income DECIMAL(10, 2) DEFAULT 0.00,
                    refer_balance DECIMAL(10, 2) DEFAULT 0.00,
                    salary_balance DECIMAL(10, 2) DEFAULT 0.00,
                    total_withdraw DECIMAL(10, 2) DEFAULT 0.00,
                    
                    wallet_address TEXT,
                    referrer_id BIGINT DEFAULT NULL
                );
            """)
            conn.commit()
            
            # ২. অনুপস্থিত কলামগুলো যোগ করা (মাইগ্রেশন ফিক্স)
            columns_to_add = [
                ('premium_balance', 'DECIMAL(10, 2) DEFAULT 0.00'),
                ('free_income', 'DECIMAL(10, 2) DEFAULT 0.00'),
                ('refer_balance', 'DECIMAL(10, 2) DEFAULT 0.00'),
                ('salary_balance', 'DECIMAL(10, 2) DEFAULT 0.00'),
                ('total_withdraw', 'DECIMAL(10, 2) DEFAULT 0.00'),
                ('wallet_address', 'TEXT'),
                ('referrer_id', 'BIGINT DEFAULT NULL')
            ]
            
            for column_name, column_type in columns_to_add:
                try:
                    # ALTER TABLE... ADD COLUMN IF NOT EXISTS শুধুমাত্র PostgreSQL 9.6+ এ কাজ করে
                    # তাই সহজভাবে এটি করার জন্য চেষ্টা করা হচ্ছে
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_type};")
                    conn.commit()
                    logger.info(f"কলাম যুক্ত হলো: {column_name}")
                except psycopg2.errors.DuplicateColumn:
                    # কলাম আগে থেকেই আছে
                    conn.rollback() 
                except Exception as e:
                    # অন্য কোনো এরর
                    logger.warning(f"কলাম {column_name} যোগ করতে অন্য সমস্যা: {e}")
                    conn.rollback()


            conn.commit()
            logger.info("ইউজার টেবিল তৈরি/যাচাই ও মাইগ্রেশন সম্পন্ন হয়েছে।")
        except Exception as e:
            logger.error(f"টেবিল তৈরি বা মাইগ্রেশনে গুরুতর সমস্যা: {e}")
        finally:
            cursor.close()
            conn.close()

# ----------------------------------------------------
# ৩. ইউজার রেজিস্ট্রেশন ও রেফারেল বোনাস লজিক
# ----------------------------------------------------
def register_user(user_id, referrer_id=None):
    """নতুন ইউজারকে রেজিস্টার করে এবং রেফারিকে বোনাস প্রদান করে (যদি থাকে)"""
    conn = connect_db()
    if not conn:
        return False

    cursor = conn.cursor()
    
    # ১. ইউজারকে খুঁজে বের করা: ইউজার কি আগেই রেজিস্টার করা?
    cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
    existing_user = cursor.fetchone()

    if existing_user:
        cursor.close()
        conn.close()
        return True

    # ২. নতুন ইউজার রেজিস্টার করা
    try:
        cursor.execute("""
            INSERT INTO users (user_id, status, referrer_id) 
            VALUES (%s, %s, %s)
        """, (user_id, 'start', referrer_id))
        
        conn.commit()
        logger.info(f"New user {user_id} registered. Referrer ID: {referrer_id}")

        # ৩. রেফারিকে বোনাস দেওয়া (যদি referrer_id বৈধ হয়)
        if referrer_id:
            cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (referrer_id,))
            if cursor.fetchone():
                # রেফারিকে রেফার ব্যালেন্সে জয়েনিং বোনাস যোগ করা
                cursor.execute(
                    "UPDATE users SET refer_balance = refer_balance + %s WHERE user_id = %s",
                    (REFERRAL_BONUS_JOINING, referrer_id)
                )
                conn.commit()
                logger.info(f"Referral joining bonus of {REFERRAL_BONUS_JOINING} BDT given to referrer {referrer_id}")
            else:
                logger.warning(f"Referrer ID {referrer_id} not found in database.")

        return True

    except Exception as e:
        logger.error(f"User registration or referral update failed for {user_id}: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

# -----------------
# ৪. বাটন ডিজাইন
# -----------------

# ক) মূল মেনুর বাটন (Reply Keyboard) - সমস্ত বাটন যুক্ত করা হয়েছে
main_menu_keyboard = [
    ["🏠 প্রধান মেনু (Home)", "👤 PROFILE 👤", "🏦 WITHDRAW 🏦"],
    ["⭐️ প্রিমিয়াম সার্ভিস", "🏅 TASK 🏅", "📢 REFER 🎁"], 
    ["💾 VERIFY ✅", "📜 HISTORY 📜"],
    ["💡 কিভাবে কাজ করে?", "📞 সাপোর্ট"]
]
main_menu_markup = ReplyKeyboardMarkup(main_menu_keyboard, resize_keyboard=True, one_time_keyboard=False)

# খ) প্রিমিয়াম বাটন (Inline Keyboard) - একক বাটন
premium_inline_keyboard = [
    [InlineKeyboardButton("✨ PREMIUM SERVICE ⭐️", callback_data='premium_service_main')], 
]
premium_inline_markup = InlineKeyboardMarkup(premium_inline_keyboard)

# -----------------
# ৫. হ্যান্ডলার ফাংশন
# -----------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start কমান্ড হ্যান্ডলার। রেফারেল লিংক হ্যান্ডল করে।"""
    user = update.effective_user
    referrer_id = None
    
    # ১. রেফারেল আইডি চেক করা (ডিপ-লিঙ্কিং)
    if context.args and len(context.args) > 0:
        try:
            potential_referrer_id = int(context.args[0])
            
            # নিজের রেফারেল লিঙ্ক দিয়ে নিজে জয়েন করতে পারবে না
            if potential_referrer_id != user.id:
                referrer_id = potential_referrer_id
            else:
                logger.info(f"Self-referral attempt blocked for user {user.id}")

        except ValueError:
            pass

    # ২. ইউজারকে রেজিস্টার করা ও রেফারেল লজিক চালানো
    register_user(user.id, referrer_id)

    # ৩. মেসেজ তৈরি ও পাঠানো
    message = (
        f"👋 স্বাগতম, **{user.first_name}**!\n\n"
        f"আমরা আপনাকে অনলাইনে সহজে উপার্জন করার একটি সুযোগ দিচ্ছি।\n"
        f"আমাদের প্রিমিয়াম এবং ফ্রি টাস্কগুলো সম্পন্ন করে আপনি উপার্জন শুরু করতে পারেন।\n\n"
        f"🚀 **শুরু করার জন্য নিচের মেনু ব্যবহার করুন।**\n"
        f"👤 প্রোফাইল তৈরি করতে বাটনটি ব্যবহার করুন।\n"
        f"📢 রেফার করে অতিরিক্ত বোনাস পেতে পারেন (প্রতি সফল জয়েনিংয়ে **{REFERRAL_BONUS_JOINING} BDT**!)।"
    )

    await update.message.reply_text(
        message,
        reply_markup=main_menu_markup,
        parse_mode='Markdown'
    )


async def premium_service_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """⭐️ প্রিমিয়াম সার্ভিস বাটনে ক্লিক করলে ইনলাইন বাটন দেখায়"""
    await update.message.reply_text(
        "আমাদের প্রিমিয়াম সেকশনে আপনাকে স্বাগতম। নিচে প্রদত্ত বাটনটি ব্যবহার করুন:",
        reply_markup=premium_inline_markup
    )


async def handle_button_clicks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """সাধারণ মেনু বাটন হ্যান্ডলার"""
    text = update.message.text
    
    if text == "🏠 প্রধান মেনু (Home)":
        await update.message.reply_text("আপনি প্রধান মেনুতে আছেন।", reply_markup=main_menu_markup)
    elif text == "💡 কিভাবে কাজ করে?":
        await update.message.reply_text("এই বটটি একটি প্রিমিয়াম কন্টেন্ট অ্যাক্সেস প্রদানকারী বট। আপনি প্রিমিয়াম প্ল্যান কিনে আমাদের এক্সক্লুসিভ চ্যানেলে যুক্ত হতে পারেন।")
    elif text == "📞 সাপোর্ট":
        await update.message.reply_text("সাপোর্টের জন্য এই ইউজারনেমে যোগাযোগ করুন: @Your_Support_Username")
    else:
        await update.message.reply_text("দুঃখিত, আমি এই কমান্ডটি বুঝিনি। দয়া করে মেনু বাটন ব্যবহার করুন।")
    
async def handle_inline_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ইনলাইন বাটনে ক্লিক করলে কী হবে তা পরিচালনা করে"""
    query = update.callback_query
    await query.answer() 
    
    data = query.data
    
    if data == 'premium_service_main':
        await query.edit_message_text(
            "✨ প্রিমিয়াম মেনু:\n\n"
            "এখনো কোনো কাজ শুরু হয়নি। পরবর্তী ধাপে এর লজিক যোগ হবে।"
        )


# -----------------
# ৬. মূল ফাংশন
# -----------------

def main():
    """বট অ্যাপ্লিকেশন শুরু করে"""
    
    # ডেটাবেস সংযোগ না পেলে বট চলতে পারবে না
    if not BOT_TOKEN or not DATABASE_URL:
        logger.error("BOT_TOKEN or DATABASE_URL is missing. Please check Render environment variables.")
        return

    create_table_if_not_exists()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # হ্যান্ডলার যুক্ত করা:
    application.add_handler(CommandHandler("start", start_command))
    
    # মডুলার এবং রেজেক্স হ্যান্ডলার:
    
    # ১. প্রোফাইল হ্যান্ডলার
    application.add_handler(MessageHandler(filters.Regex("^👤 PROFILE 👤$"), profile_handler.profile_command))

    # ২. প্রিমিয়াম সার্ভিস হ্যান্ডলার
    application.add_handler(MessageHandler(filters.Regex("^⭐️ প্রিমিয়াম সার্ভিস$"), premium_service_button))
    
    # ৩. রেফার হ্যান্ডলার (এখন কাজ করবে)
    application.add_handler(MessageHandler(filters.Regex("^📢 REFER 🎁$"), refer_handler.refer_command)) 

    # ৪. অন্যান্য WIP হ্যান্ডলার
    # application.add_handler(MessageHandler(filters.Regex("^🏦 WITHDRAW 🏦$"), withdraw_handler.withdraw_command))
    # application.add_handler(MessageHandler(filters.Regex("^🏅 TASK 🏅$"), task_handler.task_command))
    # application.add_handler(MessageHandler(filters.Regex("^💾 VERIFY ✅$"), verify_handler.verify_command))
    # application.add_handler(MessageHandler(filters.Regex("^📜 HISTORY 📜$"), history_handler.history_command))
    
    # ৫. অবশিষ্ট টেক্সট মেসেজ এবং অন্যান্য হ্যান্ডলার
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_button_clicks))
    application.add_handler(CallbackQueryHandler(handle_inline_callbacks))
    
    logger.info("বট চলছে... (Polling Mode)")
    application.run_polling(poll_interval=3)

if __name__ == '__main__':
    main()
