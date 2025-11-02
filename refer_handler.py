import os
import psycopg2
import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# --- ১. ডেটাবেস সংযোগ ফাংশন (Circular Import ফিক্স) ---
# bot.py থেকে import না করে এখানে নিজস্ব সংযোগ তৈরি করা হলো
def connect_db():
    DATABASE_URL = os.environ.get("DATABASE_URL")
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        return conn
    except Exception as e:
        logger.error(f"Database connection error in refer_handler: {e}")
        return None

# ফ্রেচিং দ্য রেফারাল বোনাস কনস্ট্যান্ট
REFERRAL_BONUS_JOINING = 40.00 

# --- ২. রেফারাল কমান্ড হ্যান্ডলার ---
async def refer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the 📢 REFER 'button'
    """
    user = update.effective_user
    user_id = user.id
    
    conn = connect_db()
    
    if not conn:
        await update.message.reply_text("❌ দুঃখিত! ডেটাবেস সংযোগে সমস্যা হচ্ছে।")
        return

    cursor = conn.cursor()
    message = ""
    
    try:
        # ১. ইউজারের রেফারাল ব্যালেন্স ফ্রেচ করা
        cursor.execute(
            "SELECT refer_balance FROM users WHERE user_id = %s",
            (user_id,)
        )
        result = cursor.fetchone()
        
        if result:
            refer_balance = result[0]
        else:
            refer_balance = 0.00
            
        # ২. মোট রেফারালের সংখ্যা গণনা করা
        cursor.execute(
            "SELECT COUNT(user_id) FROM users WHERE referrer_id = %s",
            (user_id,)
        )
        referral_count = cursor.fetchone()[0]
        
        # রেফারাল লিংক তৈরি করা
        referral_link = f"https://t.me/{context.bot.username}?start={user_id}"

        # ৩. মেসেজ তৈরি করা (আপনার ইমোজি ও স্টাইল অনুযায়ী)
        message = (
            "🚀 রেফার করে উপার্জন করুন এবং বোটের \n"
            "যত বৈশিষ্টে তত বেশী ইনকাম করুন 💰\n"
            "🔥 **REFER REWARDS** 🔥\n"
            "\n"
            "1️⃣ **NEW **MEMBER JOINING**:\n"
            f"   **REWARD**:: **{REFERRAL_BONUS_JOINING:.2f} ৳**\n"
            "2️⃣ PREMIUM SUBSCRIPTION\n"
            "   **REWARD** : **25%**\n"
            "\n"
            f"🆕 **FREE MEMBERS**:: **{referral_count}**\n"
            "👑 **PREMIUM MEMBES**:: **0**\n"
            f"📌 **TOTAL REFERALS**:: **{referral_count}**\n"
            "\n"
            f"💲 **YOUR REFER BALANCE**:: **{refer_balance:.2f} ৳**\n"
            "\n"
            f"🔗 **YOUR REFER LINK** 🔗\n"
            f"`{referral_link}`\n"
            "\n"
            "👉 এই লিঙ্ককে বন্ধুদের সঙ্গে শেয়ার করুন"
        )
        
    except Exception as e:
        logger.error(f"Referral data fetch error: {e}")
        message = "❌ রেফারেল তথ্য দেখাতে সমস্যা হচ্ছে।"
    finally:
        if conn:
            conn.close()
            
    await update.message.reply_text(
        message, 
        parse_mode='Markdown'
    )
