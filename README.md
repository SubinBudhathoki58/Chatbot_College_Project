# Chatbot College Project

An NLP-powered food ordering chatbot built with Dialogflow and FastAPI. Users can place orders, modify them, track delivery status, and complete purchases using natural language conversation.

## Overview

This is a conversational AI system designed for restaurant food ordering. Instead of navigating through menus, customers just chat with the bot naturally:
- "I want 2 momos and 1 sekuwa"
- "Add one more order"
- "Where's my order?"
- "Complete my order"

The chatbot handles the entire flow without any clicks or form filling.

## How It Works

The chatbot processes user input through Dialogflow's NLP engine, which extracts intent and parameters (food items, quantities). The backend (FastAPI) then:
1. Manages the order in memory during the conversation
2. Saves completed orders to MySQL database
3. Tracks order status for customers

```
User Input → Dialogflow NLP → Extract Intent & Items → FastAPI Backend → MySQL Database
                                                              ↓
                                                      Order Validation & Storage
                                                              ↓
                                                      Response to User
```

## Features

**Order Management**
- Add items to cart during conversation
- Remove items if needed
- Get order summary anytime
- Complete and submit orders with tracking

**Natural Language Processing**
- Understands various ways of ordering ("Give me...", "I want...", "Please add...")
- Recognizes food items and quantities
- Handles typos and variations

**Order Tracking**
- Unique order IDs for each purchase
- Real-time status updates (in progress, ready, delivered)
- Price calculation with tax/delivery

**Session Management**
- Individual conversation sessions per user
- Order persistence during chat
- Automatic cleanup after completion

## Tech Stack

| Component | Technology |
|-----------|-----------|
| NLP Engine | Google Dialogflow |
| Backend API | FastAPI (Python) |
| Database | MySQL |
| Frontend | Vanilla JavaScript + HTML/CSS |
| Deployment | Cloud Run / Heroku |

## Project Structure

```
Chatbot_College_Project/
├── Backend/
│   ├── main.py              # FastAPI server & webhook handler
│   ├── db_helper.py         # Database operations
│   ├── generic_helper.py    # Utility functions
│   └── requirements.txt     # Python dependencies
├── frontend/                # React/vanilla JS interface
├── Database/                # SQL scripts & schema
├── DialogFlow intents/      # Intent configurations
└── README.md
```

## Backend Implementation

The backend uses FastAPI to handle Dialogflow webhooks:

```python
@app.post("/")
async def handle_request(request: Request):
    payload = await request.json()
    intent = payload['queryResult']['intent']['displayName']
    parameters = payload['queryResult']['parameters']
    # Route to appropriate handler
```

**Key Functions:**
- `add_to_order()` - Add items to current order
- `remove_from_order()` - Remove items
- `complete_order()` - Save order to database
- `track_order()` - Get order status

**Database Helpers:**
- `insert_order_item()` - Save items to orders table
- `get_total_order_price()` - Calculate final bill
- `get_order_status()` - Retrieve tracking info

## Getting Started

### Prerequisites
- Python 3.8+
- MySQL 5.7+
- Dialogflow account
- Node.js (for frontend)

### Backend Setup

1. Clone the repository
```bash
git clone https://github.com/SubinBudhathoki58/Chatbot_College_Project.git
cd Chatbot_College_Project/Backend
```

2. Install dependencies
```bash
pip install -r requirements.txt
```

3. Configure database connection in `db_helper.py`
```python
cnx = mysql.connector.connect(
    host="localhost",
    user="root",
    password="your_password",
    database="pandeyji_eatery"
)
```

4. Run the server
```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`

### Database Setup

Import the SQL schema:
```bash
mysql -u root -p pandeyji_eatery < Database/schema.sql
```

This creates:
- `orders` table - Order records
- `order_items` table - Items in each order
- `order_tracking` table - Delivery status

### Dialogflow Configuration

1. Create a new agent in Dialogflow
2. Set webhook URL to your FastAPI backend
3. Create intents:
   - `order.add` - For adding items
   - `order.remove` - For removing items
   - `order.complete` - For checkout
   - `track.order` - For status updates

## API Endpoints

**Health Check**
```
GET /
Response: {"status": "ok", "message": "Chatbot backend is running"}
```

**Process User Input**
```
POST /
Content-Type: application/json

Dialogflow Webhook Request → Processed Intent → Fulfillment Response
```

## Usage Example

**User:** "I want 2 momos and 1 sekuwa"
```json
Intent: order.add - context: ongoing-order
Parameters: {
  "food-item": ["momos", "sekuwa"],
  "number": [2, 1]
}
Response: "So far you have: 2 momos, 1 sekuwa. Do you need anything else?"
```

**User:** "Complete my order"
```json
Intent: order.complete - context: ongoing-order
Response: "Awesome! We have placed your order. Order ID: 5. Total: Rs. 450"
```

**User:** "Track my order 5"
```json
Intent: track.order - context: ongoing-tracking
Response: "Your order #5 is in progress. Estimated delivery: 30 mins"
```

## Database Schema

**orders table**
- order_id (Primary Key)
- order_date
- total_price
- status

**order_items table**
- order_item_id (Primary Key)
- order_id (Foreign Key)
- food_item
- quantity
- price

**order_tracking table**
- tracking_id (Primary Key)
- order_id
- status ('in progress', 'ready', 'delivered')
- updated_at

## Deployment

### Option 1: Heroku
```bash
heroku login
heroku create your-app-name
git push heroku main
```

### Option 2: Google Cloud Run
```bash
gcloud builds submit --tag gcr.io/PROJECT_ID/chatbot
gcloud run deploy chatbot --image gcr.io/PROJECT_ID/chatbot
```

Update Dialogflow webhook with the deployed URL.

### Option 3: AWS Elastic Beanstalk
```bash
eb init
eb create
eb deploy
```

## Known Issues & Troubleshooting

**Issue:** "Database connection error"
- Check MySQL is running
- Verify credentials in `db_helper.py`
- Ensure database `pandeyji_eatery` exists

**Issue:** "Intent not recognized"
- Verify Dialogflow intents are configured correctly
- Check webhook URL is publicly accessible
- Test webhook in Dialogflow console

**Issue:** "Orders not saving"
- Check database tables exist
- Verify stored procedures are created
- Check MySQL user has INSERT permissions

## Learning Resources

This project demonstrates:
- **NLP & Conversational AI** - How Dialogflow processes natural language
- **Web API Development** - Building REST APIs with FastAPI
- **Database Design** - SQL schema for order management
- **Webhook Integration** - Handling Dialogflow webhooks
- **Full-Stack Development** - Frontend, backend, and database integration
- **Session Management** - Maintaining conversation state

## Future Enhancements

- Add payment gateway integration
- Implement user authentication
- Add order history for registered users
- Real-time delivery tracking with maps
- Multi-language support
- Restaurant recommendation system
- Loyalty points program
- Admin dashboard for order management

## Contributors

Subin Budhathoki

## License

Open source - feel free to use and modify

## Questions?

For issues or questions, open an issue on GitHub or contact the maintainer.
