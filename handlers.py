from asyncio.log import logger
from html import escape
from multiprocessing import context
import random
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, CommandHandler, MessageHandler, filters
from email_service import send_email, fetch_inbox, send_email_reply
import asyncio
import re
import telegram
import uuid

from database import  (get_user, 
                       is_connected, 
                       init_db, 
                       get_inbox_cooldown, 
                       set_inbox_cooldown, 
                       get_remaining_cooldown,
                       get_dynamic_cooldown, 
                       create_expiry, 
                       remaining_time,
                       get_all_connected_users,
                       get_last_seen,
                       set_last_seen,
                       init_last_seen,
                       get_notif_email,
                       save_notif_email,
                       get_notification_status,
                       set_notification_status,
                       set_signature,
                       get_signature
)

(CONNECT_EMAIL,CONNECT_PASSWORD,
SEND_RECEIVER, SEND_SUBJECT, SEND_MESSAGE, SEND_PREVIEW) = range (6)

def validate_email(email: str) -> bool:
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None

def clean_header(text: str) -> str:
    return re.sub(r'[\r\n]+', ' ', text).strip()

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏠 Home", callback_data="home"),
            InlineKeyboardButton("📥 Inbox", callback_data="inbox_command"),
            InlineKeyboardButton("✉️ Compose", callback_data="send_start")
        ]
    ])

def strip_html(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text).strip()    


async def send_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    context.user_data["send_mode"] = "normal"
    context.user_data["editing"] = None
    
    user = get_user(telegram_id)
    
    if not user:
        await update.message.reply_text("Please connect your email first ")
        return
    if not is_connected(telegram_id):
        await update.message.reply_text("Your email is not connected. Please connect your email first")
        return
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("Enter Receiver Email:")
    else:
        await update.message.reply_text("Enter Receiver Email:")
    return SEND_RECEIVER

async def send_receiver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    receiver = update.message.text.strip()
    text = update.message.text.strip()
    if not validate_email(receiver):
        await update.message.reply_text("Invalid email format. Please enter a valid email address.")
        return SEND_RECEIVER
    
    context.user_data["receiver"] = receiver
    if context.user_data.get("editing") == "receiver":
        context.user_data.pop("editing", None)
        await show_preview(update, context)
        return SEND_PREVIEW

    await update.message.reply_text("Enter Subject: ",
        reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅ Back", callback_data="back_to_receiver")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]))
    return SEND_SUBJECT

async def send_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["subject"] = update.message.text
    if context.user_data.get("editing") == "subject":
        context.user_data.pop("editing", None)
        await show_preview(update, context)
        return SEND_PREVIEW
    
    await update.message.reply_text("Enter Message: ",
        reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅ Back", callback_data="back_to_subject")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]))
    return SEND_MESSAGE

async def send_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["message"] = update.message.text


    if context.user_data.get("editing") == "message":
        context.user_data.pop("editing", None)
        
    receiver = context.user_data.get("receiver")
    subject = context.user_data.get("subject")
    message = context.user_data.get("message")

    if not receiver or not subject or not message:
        await update.message.reply_text("Missing data.")
        return ConversationHandler.END

    await show_preview(update, context)

    return SEND_PREVIEW

   
async def show_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    receiver = context.user_data["receiver"]
    subject = context.user_data["subject"]
    body = context.user_data["message"]
    
    preview = (
        f" PREVIEW EMAIL\n\n"
        f" To: {receiver}\n"
        f"SUBJECT: {subject}\n\n"
        f"{body}"
    )
    
    keyboard = [
    [
        InlineKeyboardButton("📤 Send", callback_data="confirm_send"),
    ],
    [
        InlineKeyboardButton("✏ Edit Message", callback_data="edit_preview_message"),
        InlineKeyboardButton("⬅ Back", callback_data="back_to_message")
    ],
    [
        InlineKeyboardButton("🏠 Home", callback_data="home"),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel")
    ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text(
            preview,reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text(
            preview,reply_markup=reply_markup
        )
    return SEND_PREVIEW

async def confirm_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    telegram_id = update.effective_user.id
    user = get_user(telegram_id)

    if not user:
        await query.edit_message_text("❌ User data not found. Please connect your email first.")
        return ConversationHandler.END

    if context.user_data.get("processing"):
        await query.answer("Already processing your email. Please wait.", show_alert=True)
        return ConversationHandler.END

    context.user_data["processing"] = True

    try:
        receiver = clean_header(context.user_data["receiver"])
        subject  = clean_header(context.user_data["subject"])
        body     = context.user_data["message"]

        signature = get_signature(telegram_id)
        if signature:
            body = f"{body}\n\n--\n{signature}"
        
        context.user_data["sender_email"] = user[0]
        context.user_data["app_password"] = user[1]
        context.user_data["receiver"]     = receiver
        context.user_data["subject"]      = subject
        context.user_data["body"]         = body

    except KeyError as e:
        await query.edit_message_text(f"❌ Missing email field: {e}. Please compose your email again.")
        return ConversationHandler.END

    await query.edit_message_text(
        "📧 Choose a template for your email:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏢 Corporate",       callback_data="template_corporate")],
            [InlineKeyboardButton("🏡 Real Estate",     callback_data="template_real_estate")],
            [InlineKeyboardButton("🛒 E-Commerce",      callback_data="template_ecommerce")],
            [InlineKeyboardButton("🚀 Web3",            callback_data="template_web3")],
            [InlineKeyboardButton("📄 No Template",     callback_data="template_plain")],
            [InlineKeyboardButton("🏠 Home",            callback_data="home")],
        ])
    )
    return ConversationHandler.END

BASE = 60
       
async def inbox_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    await query.answer()
    
    telegram_id = str(update._effective_user.id)
    
    user = get_user(telegram_id)
    email, password, is_connected = user
    
    if not is_connected:
        await query.edit_message_text(" Email Not Active")
        return
    
    raw_expiry = get_inbox_cooldown(telegram_id)
    expiry = float(raw_expiry) if raw_expiry else None
    
    if expiry and expiry > time.time():
            await show_inbox_cooldown(update, context, expiry)
            return
    msg = await query.message.reply_text(" Loading Inbox.....")
    try:
        emails = await asyncio.to_thread(fetch_inbox, email, password)
        context.user_data["fail_count"] = 0
        
    except Exception as e:
        print(" Inbox Error", e)
        
        fail_count = context.user_data.get("fail_count", 0) + 1
        context.user_data["fail_count"] = fail_count
        
        cooldown = get_dynamic_cooldown(fail_count)
        expiry = create_expiry(cooldown)
        set_inbox_cooldown(telegram_id, expiry)
        
        await msg.delete()
        await show_more_inbox(update, context, expiry)
        return
    await msg.delete()
    expiry = time.time() + BASE
    set_inbox_cooldown(telegram_id, expiry)
    context.user_data["inbox_list"] = emails
    context.user_data["inbox_page"] = 0
    
    await show_more_inbox(update, context)
    
  
    
    
     
    
  
    
PAGE_SIZE = 5  
async def show_more_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
   
    await query.answer()

    emails = context.user_data.get("inbox_list", [])
    page = context.user_data.get("inbox_page", 0)

    start = page * PAGE_SIZE
    end = start + PAGE_SIZE

    text = "*INBOX*\n\n"

    page_emails = emails[start:end]
    
    for i, mail in enumerate(page_emails):
        real_index = start + i + 1
        text += f"{real_index}. {mail['subject']} - {mail['from']}\n"

    keyboard = []

    row = []

    if page > 0:
        row.append(
            InlineKeyboardButton("⬅ Back", callback_data="inbox_prev")
        )

    if end < len(emails):
        row.append(
            InlineKeyboardButton("➡ Show More", callback_data="inbox_next")
        )
    if row:
        keyboard.append(row)
    keyboard.append([
        InlineKeyboardButton("🏠 Home", callback_data="home"),
         InlineKeyboardButton("Refresh", callback_data="refresh_inbox")
    ])
    
    if query:
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def inbox_prev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["inbox_page"] = max(0, context.user_data.get("inbox_page", 0) - 1)
    return await show_more_inbox(update, context)

async def inbox_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()


    context.user_data["inbox_page"] += 1
    return await show_more_inbox(update, context)
  
async def read_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if not text.isdigit():
        return
    
    index = int(text) - 1
    
    emails = context.user_data.get("inbox_list", [])
    
    if index < 0 or index >= len(emails):
        await update.message.reply_text(" Invalid Email Number.")
        return
    
    mail = emails[index]
    
    context.user_data["selected_email"] = {
        "from": mail["from"],
        "subject": mail["subject"],
        "body": mail["body"],
        "message_id" : mail.get("message_id") if isinstance(mail, dict) else None,
        "references" : mail.get("references", "")
    }
    
    
    message = (
        f" *Email Detail*\n\n"
        f"From: {mail['from']}\n"
        f"Subject: {mail['subject']}\n\n"
        f"{mail['body']}"
    )
    
    
    keyboard = [
        [InlineKeyboardButton("↩ Reply", callback_data="reply_email")],
        [
        InlineKeyboardButton("⬅ Back to Inbox", callback_data="back_to_inbox"),
        InlineKeyboardButton("🔄 Refresh", callback_data="refresh_inbox")
    ],
    [InlineKeyboardButton("🏠 Home", callback_data="home")]
    ]
    
    await update.message.reply_text(
        message,reply_markup=InlineKeyboardMarkup(keyboard),parse_mode="Markdown"
    )
 
async def open_notif_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    notif_keys = query.data.split(":", 1)[1]
    mail = get_notif_email(notif_keys)

    telegram_id = str(update.effective_user.id)
    user = get_user(telegram_id)

    if not user:
        await query.edit_message_text("❌ User not found. Please reconnect your email.")
        return

    email_user, password, is_connected = user

    if not is_connected:
        await query.edit_message_text("❌ Email not connected.")
        return

    await query.edit_message_text("📬 Loading email...")

    inbox = await asyncio.to_thread(fetch_inbox, email_user, password)

    if not mail:
        await query.edit_message_text("❌ Email not found. It may have been deleted.")
        return

    context.user_data["selected_email"] = {
        "from":       mail["from"],
        "subject":    mail["subject"],
        "body":       mail["body"],
        "message_id": mail.get("message_id"),
        "references": mail.get("references", "")
    }

    message = (
        f"📧 *Email Detail*\n\n"
        f"*From:* {mail['from']}\n"
        f"*Subject:* {mail['subject']}\n\n"
        f"{strip_html(mail['body'])}"
    )

    keyboard = [
        [InlineKeyboardButton("↩️ Reply",          callback_data="reply_email")],
        [InlineKeyboardButton("📥 Open Inbox",      callback_data="inbox_command")],
        [InlineKeyboardButton("🏠 Home",            callback_data="home")],
    ]

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    
async def reply_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    email_data = context.user_data.get("selected_email")

    if not isinstance(email_data, dict):
        await query.edit_message_text("❌ Invalid email selected. Please reopen inbox.")
        return ConversationHandler.END

    context.user_data["reply_to"] = {
        "message_id": email_data.get("message_id", ""),
        "references":  email_data.get("references", "")
    }
    context.user_data["receiver"] = clean_header(email_data.get("from", ""))
    context.user_data["subject"]  = clean_header(email_data.get("subject", ""))
    context.user_data["mode"]     = "reply"

    await query.edit_message_text(
        f"↩️ Replying to: {email_data.get('from')}\n\n"
        f"Subject: {email_data.get('subject')}\n\n"
        f"Enter your message:"
    )

    return SEND_MESSAGE

async def edit_preview_message(update: Update, context : ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
         [InlineKeyboardButton("✉ Edit Receiver", callback_data="edit_receiver")],
        [InlineKeyboardButton("📝 Edit Subject", callback_data="edit_subject")],
        [InlineKeyboardButton("✏ Edit Message", callback_data="edit_message")],
        [InlineKeyboardButton("⬅ Back", callback_data="back_to_preview")],
        [InlineKeyboardButton("🏠 Home", callback_data="home")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    await query.edit_message_text(
            "What would you like to edit?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    return SEND_PREVIEW

async def edit_receiver(update: Update, context : ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["editing"] = "receiver"
    await query.edit_message_text("REENTER YOUR RECEIVER: ")
    return SEND_RECEIVER

async def edit_subject(update: Update, context : ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["editing"] = "subject"
    await query.edit_message_text("REENTER YOUR SUBJECT: ")
    return SEND_SUBJECT

async def edit_message(update: Update, context : ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["editing"] = "message"
    await query.edit_message_text("REENTER YOUR MESSAGE: ")
    return SEND_MESSAGE
   
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data.clear()

    await query.edit_message_text(
        "❌ Operation cancelled.",
        reply_markup=main_menu_keyboard()
    )

    return ConversationHandler.END

async def back_to_receiver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "Enter Receiver Email:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ])
    )

    return SEND_RECEIVER  

async def back_to_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "Enter Subject:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅ Back", callback_data="back_to_receiver")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ])
    )

    return SEND_SUBJECT 

async def back_to_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "Enter Message:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅ Back", callback_data="back_to_subject")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ])
    )

    return SEND_MESSAGE   
 
async def back_to_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    return await show_preview(update, context) 

async def back_to_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    context.user_data["inbox_index"] = max(0, context.user_data.get("inbox_index", 0) - 5)
    
    return await inbox_command(update, context)

async def refresh_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["inbox_index"] = 0

    return await inbox_command(update, context)    

async def home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data.clear()

    user = get_user(str(update.effective_user.id))

    if user:
        email, password, is_connected = user
        is_connected = bool(is_connected)

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
        text = (
            "🏠 *HOME*\n\n"
            f"Account: {email}\n"
            f"Status: {'Connected' if is_connected else 'Not Connected'}\n\n"
            "Choose an option below:"
        )

        if is_connected:
            keyboard = [
                [InlineKeyboardButton("📤 Compose", callback_data="send_start")],
                [InlineKeyboardButton("📥 Inbox", callback_data="inbox_command")],
                [InlineKeyboardButton("⚙ Settings", callback_data="settings")],
                [InlineKeyboardButton("🚪 Disconnect", callback_data="disconnect")]
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("Connect Email", callback_data="connect_start")]
            ]
    else:
        text = (
            "🏠 *Home*\n\n"
            "No account connected yet."
        )
        keyboard = [
            [InlineKeyboardButton("Connect Email", callback_data="connect_start")]
        ]

    await query.edit_message_text(
        Welcome_message + "\n\n" + text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

 
MAX = 300
async def show_inbox_cooldown(update, context, expiry):
    print(f"Debug Expiry: {expiry}")
    print(f"Debug time.time(): {time.time()}")
    print(f"Debug remaining: {expiry - time.time()}")
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    
    message = query.message
    expiry = float(expiry)
    deadline = time.time() + MAX
    
    while True:
        remaining = expiry - time.time()
        if remaining <= 0:
            await message.edit_text(
            "✅ Inbox is now available!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 Open Inbox", callback_data="inbox_command")],
                [InlineKeyboardButton("🏠 Home", callback_data="home")]
            ])
        )
            return

        minutes, seconds = divmod(int(remaining), 60)
        
        try:
            await message.edit_text(
        f"⏳ Inbox Rate Limit Active\n\n"
        f"Try again in: {minutes}m {seconds}s",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Home", callback_data="home")]
        ])
         )
        except BadRequest:
            pass
        
        if time.time() >= deadline:
            return
        
        await asyncio.sleep(2)
            


async def handle_template_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    template_map = {
        "template_corporate":   ("template", "corporate"),
        "template_real_estate": ("template", "real_estate"),
        "template_ecommerce":   ("template", "ecommerce"),
        "template_web3":        ("template", "web3"),
        "template_plain":       ("plain",    None),
    }

    selected = query.data
    if selected not in template_map:
        await query.edit_message_text("❌ Unknown template selected.")
        return

    email_format, template_name = template_map[selected]

    sender_email = context.user_data.get("sender_email")
    app_password = context.user_data.get("app_password")
    receiver     = context.user_data.get("receiver")
    subject      = context.user_data.get("subject")
    body         = context.user_data.get("body")

    print(f"DEBUG body: {repr(body)}")
    
    if not all([sender_email, app_password, receiver, subject, body]):
        await query.edit_message_text("❌ Missing email data. Please compose your email again.")
        return

    msg = await query.message.reply_text("📤 Sending email...")
    mode = context.user_data.get("mode")
    reply_to = context.user_data.get("reply_to")
    if mode == "reply" and reply_to:
        result = await asyncio.to_thread(
            send_email_reply,
            sender_email,
            app_password,
            receiver,
            subject,
            body,
            reply_to
            
        )
    else:
        result = await asyncio.to_thread(
            send_email,
            sender_email,
            app_password,
            receiver,
            subject,
            body,
            email_format,
            template_name
    )

    await msg.delete()

    if result["status"]:
        keyboard = [
            [InlineKeyboardButton("📧 Compose", callback_data="send_start")],
            [InlineKeyboardButton("📥 Inbox",              callback_data="inbox_command")],
            [InlineKeyboardButton("⚙️ Settings",           callback_data="settings")],
            [InlineKeyboardButton("🔌 Disconnect",         callback_data="disconnect")],
        ]
        await query.edit_message_text(
            "✅ *Email Sent Successfully*\n\n"
            "Your message has been delivered successfully.\n\n"
            "📧 Status: Connected\n"
            "What would you like to do next?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(
            f"❌ {result['message']}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔁 Try Again", callback_data="send_email")],
                [InlineKeyboardButton("🏠 Home",      callback_data="home")],
            ])
        )
        
    context.user_data.clear()
    
    
async def check_new_emails(context: ContextTypes.DEFAULT_TYPE):
    users = get_all_connected_users()
    
    for telegram_id, email_user, app_password in users:
        try:
            notif_status = get_notification_status(telegram_id)
            if not notif_status:
                continue
            inbox = await asyncio.to_thread(fetch_inbox, email_user, app_password)

            if not inbox:
                continue

            
            if inbox[0].get("from") == "system":
                continue

            latest_id = inbox[0].get("message_id")
            last_seen  = get_last_seen(telegram_id)

            if last_seen is None:
                
                set_last_seen(telegram_id, latest_id)
                continue

            if latest_id and latest_id != last_seen:
                
                new_emails = []
                for mail in inbox:
                    if mail.get("message_id") == last_seen:
                        break
                    new_emails.append(mail)
                    
            
                for mail in reversed(new_emails):
                    notif_keys = str(random.randint(10000000, 99999999))
                    save_notif_email(
                        notif_keys,
                        telegram_id,
                        mail ["from"],
                        mail ["subject"],
                        mail ["body"],
                        mail.get("message_id", "")   
                    )
                    cb = f"notif:{notif_keys}"

                    await context.bot.send_message(
                        chat_id=telegram_id,
                        text=(
                            f"NEW EMAIL\n\n"
                            f"FROM {mail['from']}\n"
                            f"SUBJECT{mail['subject']}\n\n"
                            f"{escape(strip_html(mail['body'])[:200])}..."
                        ),
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("📬 Open Email", callback_data=cb)],
                            [InlineKeyboardButton(" Open Inbox", callback_data="inbox_command")],
                            [InlineKeyboardButton("Home", callback_data="home")]
                        ])
                    )

                set_last_seen(telegram_id, latest_id)

        except Exception:
            logger.exception("Notification check failed for user %s", telegram_id)
            
            
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💡 *PulseMail Tips*\n\n"
        "What would you like to learn?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Commands List",      callback_data="help_commands")],
            [InlineKeyboardButton("✍️ Email Writing Tips", callback_data="help_writing")],
            [InlineKeyboardButton("⌨️ Keyboard Shortcuts", callback_data="help_shortcuts")],
            [InlineKeyboardButton("🏠 Home",               callback_data="home")],
        ]),
        parse_mode="Markdown"
    )


async def help_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "📋 *Commands List*\n\n"
        "/start — Start the bot and see the main menu\n"
        "/help — Tips on how to use bot\n"
        "📌 *Button Commands*\n\n"
        "📥 Inbox — View your latest 20 emails\n"
        "📧 Send Email — Compose a new email\n"
        "🔔 Notifications — Get alerted on new emails\n"
        "⚙️ Settings — Manage your account preferences\n"
        "🔌 Disconnect — Unlink your email account\n"
        "🏠 Home — Return to the main menu",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="help")],
            [InlineKeyboardButton("🏠 Home", callback_data="home")],
        ]),
        parse_mode="Markdown"
    )


async def help_writing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "✍️ *Email Writing Tips*\n\n"
        "1️⃣ *Keep subject lines clear*\n"
        "Use specific subjects like 'Meeting at 3PM Friday' instead of 'Hello'\n\n"
        "2️⃣ *Start with a greeting*\n"
        "Always open with 'Dear [Name]' or 'Hi [Name]' for a professional tone\n\n"
        "3️⃣ *Be concise*\n"
        "Keep your message short and to the point — no one likes long emails\n\n"
        "4️⃣ *Use templates*\n"
        "PulseMail offers Corporate, Real Estate, E-Commerce and Web3 templates "
        "to make your emails look professional instantly\n\n"
        "5️⃣ *End with a closing*\n"
        "Always close with 'Regards', 'Yours sincerely' or 'Thank you'\n\n"
        "6️⃣ *Double check the receiver*\n"
        "Always verify the email address before hitting send",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="help")],
            [InlineKeyboardButton("🏠 Home", callback_data="home")],
        ]),
        parse_mode="Markdown"
    )


async def help_shortcuts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "⌨️ *Keyboard Shortcuts*\n\n"
        "📥 *Inbox*\n"
        "• Type a number (1-20) to open that email\n"
        "• Tap ⬅️ Prev / Next ➡️ to navigate pages\n"
        "• Tap 🔄 Refresh to reload your inbox\n\n"
        "📧 *Composing*\n"
        "• Tap ✏️ Edit to change receiver, subject or message\n"
        "• Tap ⬅️ Back to go to the previous step\n"
        "• Tap ❌ Cancel to abort at any step\n\n"
        "↩️ *Replying*\n"
        "• Open any email and tap ↩️ Reply to reply directly\n"
        "• Your reply is automatically threaded in Gmail\n\n"
        "🔔 *Notifications*\n"
        "• Tap 📬 Open Email on a notification to read it instantly\n"
        "• Tap 📥 Open Inbox to see all emails",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="help")],
            [InlineKeyboardButton("🏠 Home", callback_data="home")],
        ]),
        parse_mode="Markdown"
    ) 
    

SETTINGS_SIGNATURE = "SETTINGS_SIGNATURE"

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    telegram_id = str(update.effective_user.id)
    notif_status = get_notification_status(telegram_id)
    notif_label  = "🔔 Notifications: ON" if notif_status else "🔕 Notifications: OFF"

    await query.edit_message_text(
        "⚙️ *Settings*\n\nManage your PulseMail preferences.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 Account",          callback_data="settings_account")],
            [InlineKeyboardButton(notif_label,           callback_data="settings_notifications")],
            [InlineKeyboardButton("📧 Email Signature",  callback_data="settings_signature")],
            [InlineKeyboardButton("ℹ️ About",            callback_data="settings_about")],
            [InlineKeyboardButton("🏠 Home",             callback_data="home")],
        ]),
        parse_mode="Markdown"
    )


async def settings_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    telegram_id = str(update.effective_user.id)
    user = get_user(telegram_id)

    if not user:
        await query.edit_message_text("❌ No account found. Please connect your email first.")
        return

    email, _, is_connected = user
    status = "✅ Connected" if is_connected else "❌ Not Connected"

    await query.edit_message_text(
        f"👤 *Account*\n\n"
        f"📧 Email: {email}\n"
        f"Status: {status}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔌 Disconnect", callback_data="disconnect")],
            [InlineKeyboardButton("⬅️ Back",       callback_data="settings")],
            [InlineKeyboardButton("🏠 Home",        callback_data="home")],
        ]),
        parse_mode="Markdown"
    )


async def settings_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    telegram_id  = str(update.effective_user.id)
    notif_status = get_notification_status(telegram_id)

    
    new_status  = 0 if notif_status else 1
    set_notification_status(telegram_id, new_status)

    notif_label = "🔔 ON" if new_status else "🔕 OFF"

    await query.edit_message_text(
        f"🔔 *Notifications*\n\n"
        f"Email alerts are now *{notif_label}*",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="settings")],
            [InlineKeyboardButton("🏠 Home", callback_data="home")],
        ]),
        parse_mode="Markdown"
    )


async def settings_signature(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    telegram_id = str(update.effective_user.id)
    signature   = get_signature(telegram_id)

    current = f"Current signature:\n{signature}" if signature else "No signature set yet."

    await query.edit_message_text(
        f"📧 *Email Signature*\n\n"
        f"{current}\n\n"
        f"Type your new signature below or tap Remove to clear it:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑 Remove Signature", callback_data="settings_signature_remove")],
            [InlineKeyboardButton("⬅️ Back",            callback_data="settings")],
            [InlineKeyboardButton("🏠 Home",            callback_data="home")],
        ]),
        parse_mode="Markdown"
    )

    context.user_data["awaiting_signature"] = True
    return SETTINGS_SIGNATURE


async def settings_signature_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_signature"):
        return

    telegram_id = str(update.effective_user.id)
    signature   = update.message.text.strip()

    set_signature(telegram_id, signature)
    context.user_data.pop("awaiting_signature", None)
    
    await update.message.reply_text(
        f"✅ Signature saved:\n\n{signature}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back to Settings", callback_data="settings")],
            [InlineKeyboardButton("🏠 Home",             callback_data="home")],
        ]),
        parse_mode="Markdown"
    )


async def settings_signature_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    telegram_id = str(update.effective_user.id)
    set_signature(telegram_id, "")

    await query.edit_message_text(
        "🗑 Signature removed.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back to Settings", callback_data="settings")],
            [InlineKeyboardButton("🏠 Home",             callback_data="home")],
        ])
    )


async def settings_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "ℹ️ *About PulseMail*\n\n"
        "📬 *PulseMail Bot*\n"
        "Version: 1.0\n\n"
        "PulseMail lets you send, receive and manage\n"
        "your Gmail directly from Telegram.\n\n"
        "Built with ❤️ using python-telegram-bot",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💡 Help & Tips", callback_data="help")],
            [InlineKeyboardButton("⬅️ Back",        callback_data="settings")],
            [InlineKeyboardButton("🏠 Home",         callback_data="home")],
        ]),
        parse_mode="Markdown"
    )
