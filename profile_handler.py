import os
import logging
import psycopg2
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler # ConversationHandler   

# --- Conversation States ---
#    ,     
PROFILE_STATE = 0 
# PROFILE_EDIT_STATE = range(2) #    ,   
# PROFILE_EDIT_STATE = 1 


#  
logger = logging.getLogger(__name__)

# --- .    ---
#  db_handler.py     ,  circular import      
def connect_db():
    """Render    """
    DATABASE_URL = os.environ.get("DATABASE_URL") 
    try:
        if not DATABASE_URL:
            logger.error("DATABASE_URL environment variable is not set.")
            return None
            
        conn = psycopg2.connect(DATABASE_URL, sslmode='require') 
        return conn
    except Exception as e:
        logger.error(f"  : {e}")
        return None

# --- .   (  ) ---
#  bot.py    : profile_menu
async def handle_wallet_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ইউজারের প্রোফাইল তথ্য দেখেন ও সেভ করেন"""
    user_id = update.effective_user.id
    status = None
    conn = connect_db()
    
    #    / 
    if conn:
        cursor = conn.cursor()
        try:
            #   SELECT    
            cursor.execute("""
                SELECT 
                    is_premium, expiry_date, premium_balance, free_income, 
                    refer_balance, salary_balance, total_withdraw, wallet_address, 
                    expiry_date, referrer_id 
                FROM users 
                WHERE user_id = %s
                """, (user_id,))
            status = cursor.fetchone()
        except Exception as e:
            logger.error(f"Error fetching profile: {e}")
            status = None
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    #     
    if status and len(status) >= 10:
        is_premium = status[0]
        expiry_date = status[1]
        premium_balance = status[2]
        free_income = status[3]
        refer_balance = status[4]
        salary_balance = status[5]
        total_withdraw = status[6]
        wallet_address = status[7]
        verify_expiry_date = status[8] #     ,    verify_expiry_date
        referrer_id = status[9]

        #  
        premium_status = " Active" if is_premium and expiry_date and expiry_date >= datetime.now().date() else " Inactive"
        expiry_date_text = expiry_date.strftime("%Y-%m-%d") if expiry_date else "N/A"

        #  
        verify_status = " Not Verified"
        if verify_expiry_date and verify_expiry_date >= datetime.now().date():
            verify_status = " Verified (Expires: " + verify_expiry_date.strftime("%Y-%m-%d") + ")"

        #    ( )
        message = (
            f" **  ** \n"
            f"** :** `{user_id}`\n\n"
            f"**  :** {premium_status}\n"
            f"**  :** {expiry_date_text}\n"
            f"**  :** {verify_status}\n\n"
            f"**  :**\n"
            f" Premium Balance: ** {premium_balance:.2f}**\n"
            f" Free Income: ** {free_income:.2f}**\n"
            f" Refer Balance: ** {refer_balance:.2f}**\n"
            f" Salary Balance: ** {salary_balance:.2f}**\n\n"
            f"***"
            f" ** :** ** {total_withdraw:.2f}**\n"
            f" ** :** `{wallet_address or '  '}`\n"
        )
        
        #  
        keyboard = [
            [InlineKeyboardButton("   ", callback_data='set_wallet')], 
            [InlineKeyboardButton(" ", callback_data='menu_home')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
    else:
        #    
        message = ",           /start "
        reply_markup = None
        # ConversationHandler-    error ,     

    
    #   (Callback Query )
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        
        # 'set_wallet'   
        if query.data == 'set_wallet':
            await query.edit_message_text(
                " **    ** (:  // )\n\n"
                "  /cancel "
            )
            return PROFILE_STATE #  
            
        # অন্যান্য কলব্যাক ক্যোয়ারি হ্যান্ডেল করুন (যেমন 'menu' বাটন)
    else: 
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    elif update.message:
        await update.message.reply_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return ConversationHandler.END

# --2- .     ---
#  bot.py      : handle_profile_input
async def handle_profile_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """     """
    user_id = update.effective_user.id
    wallet_address = update.message.text.strip()
    
    #  
    if not wallet_address or len(wallet_address) < 5:
        await update.message.reply_text("        ")
        return PROFILE_STATE #   
        
    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        try:
            #     
            cursor.execute(
                """UPDATE users SET wallet_address = %s WHERE user_id = %s""",
                (wallet_address, user_id)
            )
            conn.commit()
            
            await update.message.reply_text(
                f" **!**\n\n"
                f"      : `{wallet_address}`",
                parse_mode='Markdown'
            )
            
            return ConversationHandler.END #  
            
        except Exception as e:
            logger.error(f"Error saving wallet address for {user_id}: {e}")
            await update.message.reply_text("      ")
            return ConversationHandler.END #  
            
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
                
    else:
        await update.message.reply_text("   ")
        return ConversationHandler.END #  
