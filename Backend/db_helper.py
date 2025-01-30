import mysql.connector

# Establish a global connection
global cnx
cnx = mysql.connector.connect(
    host="localhost",
    user="root",
    password="root",
    database="himalaya-db"
)

def insert_order_item(food_item, quantity, order_id):
    """
    Inserts an item into the `order_items` table using a stored procedure.
    """
    try:
        cursor = cnx.cursor()

        # Call the stored procedure `insert_order_item`
        cursor.callproc("insert_order_item", [food_item, quantity, order_id])

        cnx.commit()
        cursor.close()

        print("Order item inserted successfully!")
        return 1
    except mysql.connector.Error as err:
        print(f"Error in inserting order item: {err}")
        cnx.rollback()
        return -1
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        cnx.rollback()
        return -1


def get_total_order_price(order_id):
    """
    Retrieves the total price for a given order by calling a stored function.
    """
    try:
        cursor = cnx.cursor()

        # Properly format the query and use placeholders
        query = f"SELECT get_total_order_price({order_id})"
        cursor.execute(query)

        result = cursor.fetchone()[0]  # Fetch the first (and only) row's first column value

        cursor.close()
        return result
    except mysql.connector.Error as err:
        print(f"Error in getting total order price: {err}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None


def get_next_order_id():
    """
    Retrieves the next available order ID by finding the max `order_id` in the `orders` table.
    """
    try:
        cursor = cnx.cursor()

        query = "SELECT MAX(order_id) FROM orders"
        cursor.execute(query)

        result = cursor.fetchone()[0]  # Fetch the first (and only) row's first column value

        cursor.close()

        # Return the next order ID (default to 1 if no orders exist)
        return result + 1 if result else 1
    except mysql.connector.Error as err:
        print(f"Error in getting next order ID: {err}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None


def insert_order_tracking(order_id, status):
    """
    Inserts a new order tracking entry.
    """
    try:
        cursor = cnx.cursor()

        # Insert a new tracking record
        insert_query = "INSERT INTO order_tracking (order_id, status) VALUES (%s, %s)"
        cursor.execute(insert_query, (order_id, status))
        cnx.commit()

        cursor.close()
        print("Order tracking inserted successfully!")
    except mysql.connector.Error as err:
        print(f"Error in inserting order tracking: {err}")
        cnx.rollback()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        cnx.rollback()


def get_order_status(order_id: int):
    """
    Retrieves the status of an order by order ID.
    """
    try:
        cursor = cnx.cursor()

        # Query to get the order status
        query = "SELECT status FROM order_tracking WHERE order_id = %s"
        cursor.execute(query, (order_id,))

        result = cursor.fetchone()  # Fetch the first (and only) row

        cursor.close()

        # Return the status if found, otherwise None
        return result[0] if result else None
    except mysql.connector.Error as err:
        print(f"Error in getting order status: {err}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None
