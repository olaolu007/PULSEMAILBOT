from sqlalchemy import update
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler
from database import get_user, is_connected, save_user, disconnect_user
from email_service import  test_SMTP_connection
from handlers import SEND_RECEIVER, SEND_MESSAGE,SEND_PREVIEW,SEND_SUBJECT, CONNECT_EMAIL, CONNECT_PASSWORD, main_menu_keyboard
from handlers import validate_email
import asyncio


user_data = {}



async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    user = get_user(telegram_id)
    
    message = (
        update.callback_query.message if update.callback_query else update.message
    )
    
    Welcome_message = (
        "📬 Welcome to PulseMail Bot 🚀\n"
        "Your all-in-one Telegram email assistant designed to make sending emails fast, simple, and reliable — directly from here.\n\n"
        "✨ *What you can do:*\n"
        "📤 Send professional emails in seconds\n"
        "• ✏️ Edit your message before sending\n"
        "• 👀 Preview emails before delivery\n"
        "• 🔐 Secure login with your SMTP account\n"
        "• ⚡️ Fast and lightweight email processing\n\n"
        "💡 *How it works:*\n"
        "Just tap 'Send Email', enter the receiver, subject, and message — then review your email before sending it instantly.\n\n"
        "🔒 *Your data is safe*:\n"
        "We only use your email credentials to send messages through secure SMTP connection. Nothing is stored without your permission.\n\n"
        "👇 Choose an option below to get started:\n"
    )
    keyboard = []
    if user :
        email,app_password,is_connected= user
        is_connected = bool(is_connected)
        text = (
            " *Welcome Back*\n\n"
            f"Status: {'Connected' if is_connected else 'Not Connected'}\n"
            f"Account: {email}\n\n"
            "Choose an action below"
        )
        
        if is_connected:
            keyboard = [
            [InlineKeyboardButton("📤 Compose", callback_data = "send_start")],
            [InlineKeyboardButton("📥 Inbox", callback_data="inbox_command")],
            [InlineKeyboardButton("⚙ Settings", callback_data="settings_command")],
            [InlineKeyboardButton("🚪 Disconnect", callback_data="disconnect")]   
        ]
            
        else:
            keyboard = [
                [InlineKeyboardButton("📤 Connect Email", callback_data="connect_start")]
            ]     
    else:
        text = (
            "*Welcome*\n\n"
            "Status: Not Connected\n\n"
            "Connect your email to start sending messages..."
        )
        keyboard = [
            [InlineKeyboardButton("📤 Connect Email",callback_data ="connect_start")]
        ]
    await update.message.reply_text(
        f"{Welcome_message}\n\n"
        f"{text}\n\n"
        f"👇 Choose an option below to get started:",
        reply_markup = InlineKeyboardMarkup(keyboard),
        parse_mode = "Markdown")
    

async def connect_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        
        await query.edit_message_text("Send your email address")
        return CONNECT_EMAIL
    
  
async def disconnect_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    telegram_id = str(query.from_user.id)
    
    disconnect_user(telegram_id)
    
    context.user_data.clear()
    
    keyboard = [
        [
            InlineKeyboardButton("📤 Connect Email", callback_data="connect_start")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        " You have logged out successfully. \n\n"
        " To continue using PulseMail Bot, "
        "you need to reconnect your email again. \n\n"
        "👇 Click the button below to connect again. ",
        reply_markup=reply_markup
    )
    return ConversationHandler.END
   
     
async def connect_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()
    
    if not validate_email(email):
        await update.message.reply_text("Invalid email format. Please enter a valid email address.")
        return CONNECT_EMAIL
    
    context.user_data["email"] = email
    await update.message.reply_text("Send your app password: ")
    return CONNECT_PASSWORD

async def connect_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    
    msg = update.message
    password = msg.text.strip()
    email = context.user_data["email"]
    
    try:
        await msg.delete()
    except:
        pass
    
    processing_msg = await update.message.reply_text("Testing SMTP connection...")
    try:
        result = await asyncio.to_thread (test_SMTP_connection, email, password)
        if result.get("status"):
        
            save_user(
            telegram_id,
            email,
            password,
            1
        )
            context.user_data.clear()
        
            await processing_msg.reply_text("Email Connected Successfully!")
        
            await processing_msg.reply_text("Main Menu", reply_markup=main_menu_keyboard())
            return ConversationHandler.END
        else:
            context.user_data.clear()
            await processing_msg.reply_text(f"SMTP Connection Failed\n\n"
                                        f"reason: {result.get('error')}")
            return ConversationHandler.END
    except Exception as e: 
        context.user_data.clear()
        await processing_msg.reply_text(f"An error occurred while testing SMTP connection.\n\n"
                                        f"Please try again later.")
        return ConversationHandler.END
    


        


