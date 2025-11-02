import os
import psycopg2
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler
import datetime
from datetime import timedelta
from telegram.ext.filters import TEXT # এটি আপনার স্ক্রিনশট অনুযায়ী রাখা হয়েছে

logger = logging.getLogger(__name__)

# --- ১. ডেটাবেস সংযোগ ফাংশন (Circular Import ফিক্স) ---
def connect_db():
    DATABASE_URL = os.environ.get("DATABASE_URL")
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return None

# --- ২. কনভার্সেশন স্টেটস ও কনস্ট্যান্ট ---
SELECT_METHOD, SUBMIT_TNX = range(2)

# কনস্ট্যান্ট ও সেটিংস (আপনার স্ক্রিনশট অনুযায়ী)
VERIFY_AMOUNT = 50.00
VERIFY_DAYS = 30
PAYMENT_NUMBER = "01338553254" # বকিশ/নগদ (আপনার স্ক্রিনশট অনুযায়ী)

# --- ৩. সাহায্যকারী ফাংশন ---

# **Circular Import ফিক্সের জন্য ডামি/ফিক্সড menu_home**
async def menu_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # এই ফাংশনটি bot.py-এ থাকার কথা। Circular Import এড়াতে এটি এখানে ডামি রাখা হলো।
    # যদি এটি মেসেজ হ্যান্ডেল করে তবে update.message ব্যবহার হবে।
    # যদি এটি Callback Query থেকে আসে, তবে context.bot.send_message ব্যবহার হবে।
    try:
        await update.message.reply_text("🔙 প্রধান মেনু")
    except AttributeError:
        # যদি এটি একটি Callback Query থেকে আসে
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🔙 প্রধান মেনু"
        )
    return ConversationHandler.END


# format_verify_status (DB সংযোগ এখানে স্থানীয়ভাবে ব্যবহার করা হয়েছে)
def format_verify_status(user_id):
    """
    ইউজারের ভেরিফাই স্ট্যাটাস চেক করে মেসেজ ও বাটন তৈরি করে।
    """
    conn = connect_db()
    if not conn:
        return "❌ দুঃখিত! ডেটাবেস সংযোগে সমস্যা হচ্ছে।", None
    
    cursor = conn.cursor()
    message = ""
    reply_markup = None
    
    try:
        cursor.execute(
            """
            SELECT is_premium, expiry_date, verify_expiry
            FROM users 
            WHERE user_id = %s
            """, (user_id,)
        )
        status = cursor.fetchone()
        
        if status:
            is_premium, expiry_date, verify_expiry = status
            now = datetime.datetime.now(datetime.timezone.utc)
            
            # ১. যদি প্রিমিয়াম থাকে (আপনার স্ক্রিনশট লজিক)
            if is_premium and expiry_date and expiry_date > now:
                remaining_time = expiry_date - now
                days = remaining_time.days
                message += (
                    f"✨ **PREMIUM USER** ✨\n"
                    f"**PREMIUM TIME** : **{days}** দিন বাকি\n"
                    "আপনার অ্যাকাউন্ট **ভেরিফাইড** আছে, প্রিমিয়াম সময় বাড়াতে VERIFY করুন।\n"
                )
            
            # ২. যদি ভেরিফাই থাকে (আপনার স্ক্রিনশট লজিক)
            elif verify_expiry and verify_expiry > now:
                remaining_time = verify_expiry - now
                days = remaining_time.days
                message += (
                    f"✅ **ভেরিফাইড ইউজার** ✅\n"
                    f"Verify Time: **{days}** দিন বাকি\n"
                    "আপনার উইথড্র অপশনটি চালু আছে।"
                )
                
            # ৩. যদি ভেরিফাই না করা থাকে (আপনার স্ক্রিনশট লজিক)
            else:
                message += (
                    "⚠️ **আপনার একাউন্টটি ভেরিফাই করা নেই!**\n"
                    "আপনার Withdraw অপশনটি ভেরিফাই না করলে লক থাকবে। দয়া করে ভেরিফাই করুন।"
                )
                # VERIFY বাটন তৈরি
                keyboard = [
                    [InlineKeyboardButton("✅ VERIFY", callback_data="verify_start")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

    except Exception as e:
        logger.error(f"Error formatting verify status for user {user_id}: {e}")
        message = "ভেরিফাই স্ট্যাটাস আনতে সমস্যা হচ্ছে।"
    finally:
        if conn:
            conn.close()
            
    return message, reply_markup


# --- ৪. মূল হ্যান্ডলার ফাংশন (আপনার স্ক্রিনশট অনুযায়ী ফ্লো) ---

# ১. VERIFY কমান্ড হ্যান্ডলার (ENTRY POINT)
async def verify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """VERIFY বাটন চাপলে ইউজারের স্ট্যাটাস দেখায়"""
    user_id = update.effective_user.id
    
    message, reply_markup = format_verify_status(user_id)
    
    await update.message.reply_text(
        message, 
        reply_markup=reply_markup, 
        parse_mode='Markdown'
    )
    
    return ConversationHandler.END


# ২. VERIFY বাটন চাপলে (Callback)
async def start_verify_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """VERIFY বাটন চাপলে পেমেন্ট মেথড দেখায়"""
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton(f"💸 Bkash - {PAYMENT_NUMBER}", callback_data="method_Bkash")],
        [InlineKeyboardButton(f"💰 Nagad - {PAYMENT_NUMBER}", callback_data="method_Nagad")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # আপনার স্ক্রিনশট অনুযায়ী স্টাইল
    text = f"**Method সিলেক্ট করুন**"
    
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    return SELECT_METHOD


# ৩. Tnx ID গ্রহণের ফর্ম (Callback)
async def submit_tnx_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """পেমেন্ট মেথড সিলেক্ট করার পর Tnx ID রিকোয়েস্ট করে"""
    query = update.callback_query
    await query.answer("পেমেন্ট ইনস্ট্রাকশন...")
    
    method = query.data.split('_')[1]
    context.user_data['payment_method'] = method
    
    # আপনার স্ক্রিনশট অনুযায়ী আসল মেসেজ স্টাইল
    message = (
        f"⛔ এই **{method}** Personal নাম্বারে **৳{VERIFY_AMOUNT:.2f}** টাকা পরিশোধ করুন এবং **trxID পূরণ** করুন।\n"
        f"🚫 অন্য কোনো **{method}** Personal নাম্বারে টাকা পাঠাবেন না!\n"
        f"👇 এই নম্বরে টাকা পাঠানোর পর **trX ID** টি কপি করে এখানে মেসেজ দিন।"
    )
    
    # পূর্বের মেসেজ এডিট করা
    await context.bot.edit_message_text(
        chat_id=query.message.chat_id,
        message_id=query.message.message_id,
        text=message,
        parse_mode='Markdown'
    )
    
    return SUBMIT_TNX

# ৪. Tnx ID হ্যান্ডলিং ও DB এন্ট্রি (Message)
async def handle_tnx_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ইউজারের পাঠানো Tnx ID গ্রহণ করে এবং DB-তে রিকোয়েস্ট সেভ করে"""
    user = update.effective_user
    tnx_id = update.message.text.strip()
    method = context.user_data.get('payment_method')
    # ADMIN_ID ENV থেকে লোড করা হচ্ছে (আপনার অন্যান্য ফাইলে যেমন ছিল)
    admin_id = os.environ.get("ADMIN_ID") 
    
    if not method:
        await update.message.reply_text("❌ দুঃখিত, পেমেন্ট মেথড খুঁজে পাওয়া যায়নি। আবার চেষ্টা করুন।")
        return ConversationHandler.END

    conn = connect_db()
    if not conn:
        await update.message.reply_text("❌ দুঃখিত, বর্তমানে ডেটাবেস সংযোগে সমস্যা হচ্ছে। পরে চেষ্টা করুন।")
        return ConversationHandler.END
    
    cursor = conn.cursor()
    request_id = None
    
    try:
        # ১. ভেরিফাই রিকোয়েস্ট সেভ করা 
        cursor.execute(
            """
            INSERT INTO verify_requests (user_id, username, amount, method, tnx_id, status)
            VALUES (%s, %s, %s, %s, %s, 'pending')
            RETURNING request_id;
            """, (user.id, user.username, VERIFY_AMOUNT, method, tnx_id)
        )
        request_id = cursor.fetchone()[0]
        conn.commit()
        
        # ২. অ্যাডমিন নোটিফিকেশন মেসেজ তৈরি (আপনার স্ক্রিনশট অনুযায়ী স্টাইল)
        admin_message = (
            f"🔔 **নতুন ভেরিফাই রিকোয়েস্ট!** 🔔\n"
            f"👤 **ইউজার** : **{user.first_name}**\n"
            f"🆔 **ইউজার ID** : `{user.id}`\n"
            f"🗓️ **Date** : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"💳 **Method** : {method}\n"
            f"💸 **Amount** : **{VERIFY_AMOUNT:.2f} ৳**\n"
            f"🔑 **Tnx ID** : `{tnx_id}`"
        )
        
        # ৩. অ্যাডমিন বাটন তৈরি
        keyboard = [
            [
                InlineKeyboardButton("✅ ACCEPT", callback_data=f"verify_accept_{request_id}_{user.id}"),
                InlineKeyboardButton("❌ REJECT", callback_data=f"verify_reject_{request_id}_{user.id}")
            ]
        ]
        admin_markup = InlineKeyboardMarkup(keyboard)

        # ৪. অ্যাডমিনকে মেসেজ পাঠানো
        if admin_id:
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_message,
                reply_markup=admin_markup,
                parse_mode='Markdown'
            )
        
        # ৫. ইউজারকে ধন্যবাদ মেসেজ পাঠানো (আপনার স্ক্রিনশট অনুযায়ী স্টাইল)
        user_thanks_message = (
            "🎉 **ধন্যবাদ!** আপনার VERIFY রিকোয়েস্টটি সফলভাবে জমা দেওয়া হয়েছে।\n"
            f"**📝 Status**: **pending**\n"
            f"⏳ দয়া করে অপেক্ষণ করুন।"
        )
        await update.message.reply_text(
            user_thanks_message,
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error saving verify request: {e}")
        await update.message.reply_text("❌ দুঃখিত, রিকোয়েস্ট সেভ করতে সমস্যা হয়েছে। আবার চেষ্টা করুন।")
    finally:
        if conn:
            conn.close()
            
    return ConversationHandler.END


# ৫. কথোপকথন বাতিল হ্যান্ডলার
async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ব্যবহারকারী কথোপকথন বাতিল করলে Home Menu-তে ফেরত যায়।"""
    await menu_home(update, context) # ফিক্সড menu_home কল করা হলো
    return ConversationHandler.END


# ৬. অ্যাডমিন ভেরিফাই কলব্যাক হ্যান্ডলার
async def admin_verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """অ্যাডমিন ACCEPT/REJECT বাটন চাপলে এই ফাংশনটি কাজ করে"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    action = data[1] 
    request_id = int(data[2])
    target_user_id = int(data[3])
    requester_name = query.effective_user.first_name 

    conn = connect_db()
    if not conn:
        await query.message.reply_text("DB সংযোগ ব্যর্থ।")
        return

    cursor = conn.cursor()
    
    try:
        # ১. রিকোয়েস্ট স্ট্যাটাস চেক
        cursor.execute("SELECT status FROM verify_requests WHERE request_id = %s", (request_id,))
        current_status = cursor.fetchone()[0]
        
        if current_status != 'pending':
            await context.bot.edit_message_text(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                text=f"🚫 রিকোয়েস্টটি ইতিমধ্যেই **{current_status}** করা হয়েছে!\nBy: {requester_name}",
                parse_mode='Markdown'
            )
            return

        # ২. রিকোয়েস্ট স্ট্যাটাস আপডেট
        cursor.execute("UPDATE verify_requests SET status = %s WHERE request_id = %s", (action, request_id))
        conn.commit()
        
        user_message = ""
        
        if action == 'accept':
            # ৩. যদি ACCEPT হয়: EXPIRY DATE সেট করা
            new_expiry_date = datetime.datetime.now(datetime.timezone.utc) + timedelta(days=VERIFY_DAYS)
            
            cursor.execute(
                """
                UPDATE users 
                SET verify_expiry = %s
                WHERE user_id = %s
                """, (new_expiry_date, target_user_id)
            )
            conn.commit()
            
            # ইউজারকে জানানো (আপনার স্টাইল)
            user_message = (
                f"✅ **অভিনন্দন!** আপনার ভেরিফাই রিকোয়েস্টটি **ACCEPT** করা হয়েছে।\n"
                f"💰 মেয়াদ: **{VERIFY_DAYS} দিন**\n"
                f"আপনি এখন সফলভাবে উইথড্র করতে পারবেন।"
            )
            
            # অ্যাডমিন মেসেজ আপডেট
            admin_new_text = f"✅ রিকোয়েস্টটি **ACCEPT** করা হয়েছে!\nBy: {requester_name}"

        elif action == 'reject':
            # ৪. যদি REJECT হয়: 
            user_message = (
                f"❌ **দুঃখিত!** আপনার ভেরিফাই রিকোয়েস্টটি **REJECT** করা হয়েছে।\n"
                f"⚠️ **কারণ**: আপনার Tnx ID টি সঠিক নয়।\n"
                f" অনুগ্রহ করে সঠিক Tnx ID দিয়ে আবার চেষ্টা করুন।"
            )
            
            # অ্যাডমিন মেসেজ আপডেট
            admin_new_text = f"❌ রিকোয়েস্টটি **REJECT** করা হয়েছে!\nBy: {requester_name}"

        # ৫. অ্যাডমিন মেসেজ এডিট করা
        await context.bot.edit_message_text(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            text=admin_new_text,
            parse_mode='Markdown'
        )
        
        # ৬. টার্গেট ইউজারকে মেসেজ পাঠানো
        await context.bot.send_message(
            chat_id=target_user_id,
            text=user_message,
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error processing admin verify callback: {e}")
        await query.message.reply_text("প্রসেসিং এ বড় ধরনের সমস্যা হয়েছে। লগ চেক করুন।")
    finally:
        if conn:
            conn.close()


# ৭. কনভার্সেশন হ্যান্ডলার তৈরি (আপনার স্ক্রিনশট অনুযায়ী)
# এখানে MessageHandler-এর জন্য filters.TEXT আমদানি করা হয়েছিল
from telegram.ext import CallbackQueryHandler

verify_conversation_handler = ConversationHandler(
    entry_points=[
        # আপনার স্ক্রিনশট অনুযায়ী, দুটি এন্ট্রি পয়েন্ট থাকতে পারে: মেসেজ এবং কলব্যাক
        MessageHandler(TEXT, verify_command), # মেসেজ হ্যান্ডলিং
        CallbackQueryHandler(start_verify_flow, pattern='^verify_start$')
    ],
    states={
        SELECT_METHOD: [
            CallbackQueryHandler(submit_tnx_form, pattern='^method_(Bkash|Nagad)$')
        ],
        SUBMIT_TNX: [
            MessageHandler(TEXT, handle_tnx_submission)
        ]
    },
    fallbacks=[
        CallbackQueryHandler(cancel_conversation, pattern='^cancel$'),
        MessageHandler(TEXT, cancel_conversation) # কোনো টেক্সট মেসেজ পেলে বাতিল
    ]
)
