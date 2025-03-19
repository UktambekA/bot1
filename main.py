import os
import logging
import pandas as pd
import tempfile
import requests
from io import BytesIO
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters, ContextTypes

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
TOKEN = os.getenv('TOKEN')
EXCEL_URL = os.getenv('EXCEL')

# Define conversation states
(START, NAME, CHOOSE_STORE, SHOP_ID, OWNER_NAME, OWNER_PHONE, 
 PRODUCT_IMAGE, PRODUCT_CODE, PRODUCT_COLOR, BADGE_QUANTITY, 
 PRODUCT_SIZE_RANGE, PRODUCT_PRICE, CONFIRM_PRODUCT, NEXT_ACTION, 
 CHOOSE_RECIPIENT) = range(15)

# Pagination constants
ITEMS_PER_PAGE = 10

# Global data store
user_data_store = {}

# Excel data cache
excel_data = {
    'stores': None,
    'colors': None,
    'recipients': None
}

# Function to load Excel data
def load_excel_data():
    try:
        response = requests.get(EXCEL_URL)
        response.raise_for_status()
        
        # Save to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xls') as temp_file:
            temp_file.write(response.content)
            temp_path = temp_file.name
        
        # Read Excel file with pandas
        stores_df = pd.read_excel(temp_path, sheet_name=0)
        colors_df = pd.read_excel(temp_path, sheet_name=1)
        recipients_df = pd.read_excel(temp_path, sheet_name=2)
        
        # Clean up temp file
        os.unlink(temp_path)
        
        # Store data in cache
        excel_data['stores'] = stores_df
        excel_data['colors'] = colors_df
        excel_data['recipients'] = recipients_df
        
        return True
    except Exception as e:
        logger.error(f"Error loading Excel data: {e}")
        return False

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_data_store[user_id] = {}
    
    await update.message.reply_text(
        "Welcome to the Indenim Bot! Please enter your name:"
    )
    return NAME

async def process_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_data_store[user_id]['name'] = update.message.text
    
    # Load Excel data
    await update.message.reply_text("Loading store data, please wait...")
    if not excel_data['stores'] or excel_data['stores'] is None:
        success = load_excel_data()
        if not success:
            await update.message.reply_text("Failed to load store data. Please try again later.")
            return ConversationHandler.END
    
    # Initialize page for stores pagination
    context.user_data['stores_page'] = 0
    
    # Show first page of stores
    await show_stores_page(update, context)
    return CHOOSE_STORE

async def show_stores_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display a paginated list of stores"""
    current_page = context.user_data.get('stores_page', 0)
    stores = excel_data['stores']
    total_stores = len(stores)
    total_pages = (total_stores + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE  # Ceiling division
    
    # Calculate start and end indices for current page
    start_idx = current_page * ITEMS_PER_PAGE
    end_idx = min(start_idx + ITEMS_PER_PAGE, total_stores)
    
    # Create keyboard with store options for current page
    keyboard = []
    for index in range(start_idx, end_idx):
        store_name = stores.iloc[index, 0]  # Assuming store name is in the first column
        keyboard.append([InlineKeyboardButton(store_name, callback_data=f"store_{index}")])
    
    # Add navigation buttons if needed
    nav_buttons = []
    if current_page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data="store_prev_page"))
    if current_page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data="store_next_page"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Determine if this is a new message or an edit to an existing message
    if update.callback_query:
        await update.callback_query.edit_message_text(
            f"Please select a store/market (Page {current_page + 1}/{total_pages}):",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            f"Please select a store/market (Page {current_page + 1}/{total_pages}):",
            reply_markup=reply_markup
        )

async def store_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    # Handle pagination navigation
    if query.data == "store_prev_page":
        context.user_data['stores_page'] -= 1
        await show_stores_page(update, context)
        return CHOOSE_STORE
    elif query.data == "store_next_page":
        context.user_data['stores_page'] += 1
        await show_stores_page(update, context)
        return CHOOSE_STORE
    
    # Handle store selection
    user_id = update.effective_user.id
    store_index = int(query.data.split('_')[1])
    store_name = excel_data['stores'].iloc[store_index, 0]  # Assuming store name is in the first column
    user_data_store[user_id]['store'] = store_name
    
    await query.edit_message_text(f"Selected store: {store_name}\n\nPlease enter the shop ID:")
    return SHOP_ID

async def process_shop_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_data_store[user_id]['shop_id'] = update.message.text
    
    await update.message.reply_text("Please enter the name of the shop owner:")
    return OWNER_NAME

async def process_owner_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_data_store[user_id]['owner_name'] = update.message.text
    
    await update.message.reply_text("Please enter the phone number of the shop owner:")
    return OWNER_PHONE

async def process_owner_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_data_store[user_id]['owner_phone'] = update.message.text
    
    # Initialize products list
    if 'products' not in user_data_store[user_id]:
        user_data_store[user_id]['products'] = []
    
    await update.message.reply_text("Now let's add products. Please send a product image:")
    return PRODUCT_IMAGE

async def process_product_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    
    # Create a new product entry
    current_product = {}
    
    # Get the largest photo (best quality)
    photo_file = await update.message.photo[-1].get_file()
    file_id = update.message.photo[-1].file_id
    
    # Store the file_id for later use
    current_product['image_file_id'] = file_id
    
    # Add current product to context for temporary storage
    context.user_data['current_product'] = current_product
    
    await update.message.reply_text("Please enter the product code:")
    return PRODUCT_CODE

async def process_product_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    context.user_data['current_product']['code'] = update.message.text
    
    # Initialize page for colors pagination
    context.user_data['colors_page'] = 0
    
    # Show first page of colors
    await show_colors_page(update, context)
    return PRODUCT_COLOR

async def show_colors_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display a paginated list of colors"""
    current_page = context.user_data.get('colors_page', 0)
    colors = excel_data['colors']
    total_colors = len(colors)
    total_pages = (total_colors + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE  # Ceiling division
    
    # Calculate start and end indices for current page
    start_idx = current_page * ITEMS_PER_PAGE
    end_idx = min(start_idx + ITEMS_PER_PAGE, total_colors)
    
    # Create keyboard with color options for current page
    keyboard = []
    for index in range(start_idx, end_idx):
        color_name = colors.iloc[index, 0]  # Assuming color name is in the first column
        keyboard.append([InlineKeyboardButton(color_name, callback_data=f"color_{index}")])
    
    # Add navigation buttons if needed
    nav_buttons = []
    if current_page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data="color_prev_page"))
    if current_page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data="color_next_page"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Determine if this is a new message or an edit to an existing message
    if update.callback_query:
        await update.callback_query.edit_message_text(
            f"Please select a product color (Page {current_page + 1}/{total_pages}):",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            f"Please select a product color (Page {current_page + 1}/{total_pages}):",
            reply_markup=reply_markup
        )

async def color_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    # Handle pagination navigation
    if query.data == "color_prev_page":
        context.user_data['colors_page'] -= 1
        await show_colors_page(update, context)
        return PRODUCT_COLOR
    elif query.data == "color_next_page":
        context.user_data['colors_page'] += 1
        await show_colors_page(update, context)
        return PRODUCT_COLOR
    
    # Handle color selection
    user_id = update.effective_user.id
    color_index = int(query.data.split('_')[1])
    color_name = excel_data['colors'].iloc[color_index, 0]  # Assuming color name is in the first column
    context.user_data['current_product']['color'] = color_name
    
    await query.edit_message_text(f"Selected color: {color_name}\n\nPlease enter the badge quantity:")
    return BADGE_QUANTITY

async def process_badge_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    context.user_data['current_product']['badge_quantity'] = update.message.text
    
    await update.message.reply_text("Please enter the product size range:")
    return PRODUCT_SIZE_RANGE

async def process_size_range(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    context.user_data['current_product']['size_range'] = update.message.text
    
    await update.message.reply_text("Please enter the product price:")
    return PRODUCT_PRICE

async def process_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    context.user_data['current_product']['price'] = update.message.text
    
    # Format product information for confirmation
    product = context.user_data['current_product']
    
    # Create a formatted message with all product details
    confirmation_message = "*Product Details:*\n\n"
    confirmation_message += f"📝 *Code:* {product['code']}\n"
    confirmation_message += f"🎨 *Color:* {product['color']}\n"
    confirmation_message += f"🏷️ *Badge Quantity:* {product['badge_quantity']}\n"
    confirmation_message += f"📏 *Size Range:* {product['size_range']}\n"
    confirmation_message += f"💰 *Price:* {product['price']}\n\n"
    confirmation_message += "Is this information correct?"
    
    # Create Yes/No inline keyboard
    keyboard = [
        [InlineKeyboardButton("✅ Yes", callback_data="confirm_yes"),
         InlineKeyboardButton("❌ No", callback_data="confirm_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send message with product image if available
    if 'image_file_id' in product:
        await update.message.reply_photo(
            photo=product['image_file_id'],
            caption=confirmation_message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            confirmation_message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    return CONFIRM_PRODUCT

async def confirm_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if query.data == "confirm_yes":
        # Add the confirmed product to the user's products list
        if 'products' not in user_data_store[user_id]:
            user_data_store[user_id]['products'] = []
        
        user_data_store[user_id]['products'].append(context.user_data['current_product'])
        
        # Clear the current product from context
        context.user_data['current_product'] = {}
        
        # Create keyboard for next action
        keyboard = [
            [KeyboardButton("Add same product with different color")],
            [KeyboardButton("Add new product")],
            [KeyboardButton("Save to file")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        
        # await query.edit_message_text("Product added successfully!")
        await query.delete_message()

        await update.get_bot().send_message(
            chat_id=user_id,
            text="What would you like to do next?",
            reply_markup=reply_markup
        )
        return NEXT_ACTION
    
    elif query.data == "confirm_no":
        # Ask if user wants to restart from color selection or from beginning
        keyboard = [
            [InlineKeyboardButton("Change Color", callback_data="edit_color")],
            [InlineKeyboardButton("Start New Product", callback_data="edit_new")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.delete_message()
        await update.get_bot().send_message(
            chat_id=user_id,
            text="What would you like to change?",
            reply_markup=reply_markup
        )
        return CONFIRM_PRODUCT
    
    # Handle edit choices
    elif query.data == "edit_color":
        # Keep the current product details but go back to color selection
        # Initialize page for colors pagination
        context.user_data['colors_page'] = 0
        
        # Show first page of colors
        await show_colors_page(update, context)
        return PRODUCT_COLOR
    
    elif query.data == "edit_new":
        # Start a completely new product
        context.user_data['current_product'] = {}
        await query.delete_message()
        await update.get_bot().send_message(
            chat_id=user_id,
            text="Let's add a new product. Please send a product image:",
            reply_markup=reply_markup
        )
        return PRODUCT_IMAGE

async def process_next_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    action = update.message.text
    
    if action == "Add same product with different color":
        # Copy the last product details except color
        last_product = user_data_store[user_id]['products'][-1].copy()
        context.user_data['current_product'] = {
            'image_file_id': last_product['image_file_id'],
            'code': last_product['code'],
            'badge_quantity': last_product['badge_quantity'],
            'size_range': last_product['size_range'],
            'price': last_product['price']
        }
        
        # Initialize page for colors pagination
        context.user_data['colors_page'] = 0
        
        # Show first page of colors
        await show_colors_page(update, context)
        return PRODUCT_COLOR
        
    elif action == "Add new product":
        await update.message.reply_text("Please send a product image:")
        return PRODUCT_IMAGE
        
    elif action == "Save to file":
        # Store the data in context for later use when recipient is selected
        products_data = user_data_store[user_id]['products']
        
        # Prepare data for DataFrame
        data = []
        for product in products_data:
            data.append({
                'User Name': user_data_store[user_id]['name'],
                'Store': user_data_store[user_id]['store'],
                'Shop ID': user_data_store[user_id]['shop_id'],
                'Owner Name': user_data_store[user_id]['owner_name'],
                'Owner Phone': user_data_store[user_id]['owner_phone'],
                'Product Code': product['code'],
                'Product Color': product['color'],
                'Badge Quantity': product['badge_quantity'],
                'Size Range': product['size_range'],
                'Price': product['price'],
                'Image File ID': product['image_file_id']
            })
        
        # Create DataFrame and store in context
        df = pd.DataFrame(data)
        context.user_data['order_dataframe'] = df
        
        # Initialize page for recipients pagination
        context.user_data['recipients_page'] = 0
        
        await update.message.reply_text("Please select a recipient for this order:")
        
        # Show recipients list
        await show_recipients_page(update, context)
        return CHOOSE_RECIPIENT

async def show_recipients_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display a paginated list of recipients"""
    current_page = context.user_data.get('recipients_page', 0)
    recipients = excel_data['recipients']
    total_recipients = len(recipients)
    total_pages = (total_recipients + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE  # Ceiling division
    
    # Calculate start and end indices for current page
    start_idx = current_page * ITEMS_PER_PAGE
    end_idx = min(start_idx + ITEMS_PER_PAGE, total_recipients)
    
    # Create keyboard with recipient options for current page
    keyboard = []
    for index in range(start_idx, end_idx):
        recipient_name = recipients.iloc[index, 0]  # 'ism' column
        recipient_id = recipients.iloc[index, 1]    # 'telegram_id' column
        keyboard.append([InlineKeyboardButton(recipient_name, callback_data=f"recipient_{index}")])
    
    # Add navigation buttons if needed
    nav_buttons = []
    if current_page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data="recipient_prev_page"))
    if current_page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data="recipient_next_page"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Add option to skip recipient selection
    keyboard.append([InlineKeyboardButton("Skip - Send only to me", callback_data="recipient_skip")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Determine if this is a new message or an edit to an existing message
    if update.callback_query:
        await update.callback_query.edit_message_text(
            f"Please select a recipient (Page {current_page + 1}/{total_pages}):",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            f"Please select a recipient (Page {current_page + 1}/{total_pages}):",
            reply_markup=reply_markup
        )

async def recipient_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    # Handle pagination navigation
    if query.data == "recipient_prev_page":
        context.user_data['recipients_page'] -= 1
        await show_recipients_page(update, context)
        return CHOOSE_RECIPIENT
    elif query.data == "recipient_next_page":
        context.user_data['recipients_page'] += 1
        await show_recipients_page(update, context)
        return CHOOSE_RECIPIENT
    
    # Get the DataFrame stored earlier
    df = context.user_data['order_dataframe']
    
    # Save to Excel
    output_filename = f"order_{user_id}.xlsx"
    df.to_excel(output_filename, index=False)
    
    # Send file to current user
    document = open(output_filename, 'rb')
    await query.delete_message()
    await update.get_bot().send_document(
        chat_id=user_id,
        document=document,
        caption="Here is your order file."
    )
    
    # If a recipient was selected (not skipped), send to them as well
    if query.data != "recipient_skip":
        recipient_index = int(query.data.split('_')[1])
        recipient_name = excel_data['recipients'].iloc[recipient_index, 0]
        recipient_id = excel_data['recipients'].iloc[recipient_index, 1]
        
        try:
            # Reopen the file for the second send
            document = open(output_filename, 'rb')
            await update.get_bot().send_document(
                chat_id=int(recipient_id),
                document=document,
                caption=f"New order from {user_data_store[user_id]['name']} for {user_data_store[user_id]['store']}"
            )
            await update.get_bot().send_message(
                chat_id=user_id,
                text=f"Order has been sent to {recipient_name}."
            )
        except Exception as e:
            logger.error(f"Failed to send file to recipient: {e}")
            await update.get_bot().send_message(
                chat_id=user_id,
                text=f"Could not send the file to {recipient_name}. Please forward it manually."
            )
    
    # Clear user data
    user_data_store.pop(user_id, None)
    
    await update.get_bot().send_message(
        chat_id=user_id,
        text="Thank you! Your order has been saved. Type /start to place a new order."
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_data_store.pop(user_id, None)
    
    await update.message.reply_text("Operation cancelled. Type /start to begin again.")
    return ConversationHandler.END

def main() -> None:
    # Create the Application
    application = Application.builder().token(TOKEN).build()

    # Add conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_name)],
            CHOOSE_STORE: [CallbackQueryHandler(store_choice, pattern=r'^store_')],
            SHOP_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_shop_id)],
            OWNER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_owner_name)],
            OWNER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_owner_phone)],
            PRODUCT_IMAGE: [MessageHandler(filters.PHOTO, process_product_image)],
            PRODUCT_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_product_code)],
            PRODUCT_COLOR: [CallbackQueryHandler(color_choice, pattern=r'^color_')],
            BADGE_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_badge_quantity)],
            PRODUCT_SIZE_RANGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_size_range)],
            PRODUCT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_price)],
            CONFIRM_PRODUCT: [CallbackQueryHandler(confirm_product, pattern=r'^(confirm_|edit_)')],
            NEXT_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_next_action)],
            CHOOSE_RECIPIENT: [CallbackQueryHandler(recipient_choice, pattern=r'^recipient_')],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)

    # Start the Bot
    application.run_polling()

if __name__ == "__main__":
    main()