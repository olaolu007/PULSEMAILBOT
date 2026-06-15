from turtle import back
import time
import sqlite3
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from commands import  start_command, connect_start, connect_email, connect_password, disconnect_email
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import init_db, init_last_seen, DB_NAME, get_notif_email, save_notif_email
from handlers import (inbox_next, 
                      back_to_message, 
                      back_to_message, 
                      read_email, 
                      refresh_inbox, 
                      reply_email, 
                      show_more_inbox,
                      inbox_command,
                      inbox_prev, 
                      CONNECT_EMAIL,
                      CONNECT_PASSWORD,
                      SEND_MESSAGE,
                      SEND_RECEIVER,
                      SEND_SUBJECT,
                      SEND_PREVIEW, 
                      send_message,
                      send_receiver,
                      send_start,
                      send_subject, 
                      cancel,
                      edit_message, 
                      confirm_send,
                      edit_receiver,
                      edit_subject, 
                      edit_preview_message, 
                      back_to_receiver, 
                      back_to_subject, 
                      back_to_preview, 
                      home, 
                      handle_template_selection,
                      check_new_emails,
                      open_notif_email,
                      help_command,
                      help_commands,
                      help_writing,
                      help_shortcuts,
                      settings_about,
                      settings_command,
                      settings_notifications,
                      settings_account,
                      settings_signature,
                      settings_signature_remove,
                      settings_signature_input
                      )

from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    connect_handler = ConversationHandler(entry_points=[CallbackQueryHandler(connect_start, pattern="connect_start")],
                                        states={
                                            CONNECT_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND,connect_email)], 
                                            CONNECT_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND,connect_password)],},
                                        
                                      fallbacks=[CommandHandler("cancel", cancel),
                                               ]
                                      )


    send_handler = ConversationHandler(
        entry_points=[CommandHandler("send", send_start),
                      CallbackQueryHandler(send_start, pattern="send_start"),
                      CallbackQueryHandler(reply_email, pattern="reply_email")
                      ],
        states={
            SEND_RECEIVER: [MessageHandler(filters.TEXT & ~filters.COMMAND,send_receiver)], 
            SEND_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND,send_subject),
                           CallbackQueryHandler(back_to_receiver, pattern="^back_to_receiver$"),
                           CallbackQueryHandler(cancel, pattern="^cancel$")
                           ],
            SEND_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND,send_message),
                           CallbackQueryHandler(back_to_subject, pattern="^back_to_subject$"),
                           CallbackQueryHandler(cancel, pattern="^cancel$")
                           ],
            SEND_PREVIEW: [
                CallbackQueryHandler(confirm_send, pattern="^confirm_send$"),

                CallbackQueryHandler(edit_preview_message, pattern="^edit_preview_message$"), 
                CallbackQueryHandler(cancel, pattern="^cancel$"),
                CallbackQueryHandler(edit_receiver, pattern="^edit_receiver$"),
                CallbackQueryHandler(edit_subject, pattern="^edit_subject$"),
                CallbackQueryHandler(edit_message, pattern="^edit_message$"),
                CallbackQueryHandler(back_to_message, pattern="^back_to_message$"),
                CallbackQueryHandler(back_to_preview, pattern="^back_to_preview$")  
            ]
            },
                                      fallbacks=[CommandHandler("cancel", cancel)],
                                      allow_reentry=True,
                                      
                                      )
    
   
    
    app.add_handler(connect_handler)
    app.add_handler(send_handler)
    app.add_handler(CallbackQueryHandler(handle_template_selection, pattern = "^template_")) 
  

    app.add_handler(CommandHandler("start",start_command))
    app.add_handler(CallbackQueryHandler(start_command, pattern="^start_command$"))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(disconnect_email, pattern="disconnect"))
    app.add_handler(CallbackQueryHandler(home, pattern="^home$"))
    
    conn = sqlite3.connect(DB_NAME)
    init_last_seen(conn)
    conn.commit()
    conn.close()
    
    app.job_queue.run_repeating(check_new_emails, interval= 30, first=10, data=app)
    
    app.add_handler(CallbackQueryHandler(open_notif_email,pattern="^notif:"))
    
    app.add_handler(CallbackQueryHandler(inbox_command, pattern="inbox_command"))
    app.add_handler(CallbackQueryHandler(show_more_inbox, pattern="show_more_inbox"))
    app.add_handler(CallbackQueryHandler(inbox_next, pattern="^inbox_next$"))
    app.add_handler(CallbackQueryHandler(inbox_prev, pattern="^inbox_prev$"))
    app.add_handler(CallbackQueryHandler(back, pattern="^back$"))
    app.add_handler(CallbackQueryHandler(refresh_inbox, pattern="^refresh_inbox$"))

    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(help_commands, pattern="^help_commands$"))
    app.add_handler(CallbackQueryHandler(help_writing, pattern="^help_writing$"))
    app.add_handler(CallbackQueryHandler(help_shortcuts, pattern="^help_shortcuts$"))
    
    app.add_handler(CallbackQueryHandler(settings_command,          pattern="^settings$"))
    app.add_handler(CallbackQueryHandler(settings_account,          pattern="^settings_account$"))
    app.add_handler(CallbackQueryHandler(settings_notifications,    pattern="^settings_notifications$"))
    app.add_handler(CallbackQueryHandler(settings_signature,        pattern="^settings_signature$"))
    app.add_handler(CallbackQueryHandler(settings_signature_remove, pattern="^settings_signature_remove$"))
    app.add_handler(CallbackQueryHandler(settings_about,            pattern="^settings_about$"))
    
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,read_email))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, settings_signature_input))
    

    
    print("Bot is running...")
    
    app.run_polling()

    
if __name__ == "__main__":
    main()