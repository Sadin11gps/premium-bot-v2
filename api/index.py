import sys
import os
import json

# প্রজেক্টের রুট ডিরেক্টরি path-এ যোগ করুন যাতে bot.py import করা যায়
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# আপনার bot.py ফাইল থেকে application অবজেক্টটি import করুন
from bot import application

# Vercel-এর অনুরোধ হ্যান্ডেল করার জন্য হ্যান্ডলার ফাংশন
async def handler(request, response):
    """
    Vercel serverless function entry point.
    Handles incoming webhook requests from Telegram.
    """
    try:
        # Vercel-এর request অবজেক্ট থেকে body ডেটা পড়ুন
        body_bytes = await request.body()
        body_str = body_bytes.decode('utf-8')
        
        # JSON ডেটা পার্স করুন
        update_json = json.loads(body_str)
        
        # python-telegram-bot লাইব্রেরিকে আপডেটটি দিন
        await application.update_webhook_request(update_json)
        
        # Telegram-কে জানান যে অনুরোধটি সফল হয়েছে
        response.set_status(200)
        return response
        
    except Exception as e:
        # যদি কোনো সমস্যা হয়, তা Vercel লগে দেখান
        print(f"Error handling request: {e}")
        response.set_status(500) # Internal Server Error
        return response
